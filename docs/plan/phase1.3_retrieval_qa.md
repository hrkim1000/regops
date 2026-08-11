# Phase 1.3 — Retrieval & citation-enforced Q&A

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W5–W10 · **Status:** 🟢 done (2026-08-11) — 9/9 acceptance
- **Governed by:** [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md), [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 4
- **Depends on:** [phase1.1](phase1.1_normalization.md), [phase1.2](phase1.2_ir_extraction.md)
- **Service:** `assistant`

---

## Goal

Answer a regulatory question with the clause that supports it, the version it came from, and the
date it took effect — or refuse. This is the pillar the product is judged on: **verifiability, not
generation quality.**

Two of the six Go/No-Go gates are measured here (citation accuracy ≥ 90%, hallucination rate ≤ 2%).

## Scope

**In:** embeddings, hybrid retrieval, citation-enforced generation, the evidence-verification agent,
confidence scoring and human-review routing.

**Out:** graph context expansion over enrichment edges — the edges do not exist until phase 2.1.
Retrieval in Phase 1 is hybrid search over clauses only.

## Tasks

### Embeddings — `assistant` owns them, not `regulation`

- [x] `clause_embeddings` in the `assistant` service. Coupling the embedding lifecycle to the clause lifecycle would make a model swap a `regulation` migration
- [x] pgvector, `nomic-embed-text` 768-dim, HNSW cosine — pinned regardless of generation provider
- [x] **Embed at 조 level with 항/호/목 rolled in; cite at the finest clause actually used**
- [x] **Annex table rows are not embedded** — served by exact match. Embedding every ingredient row is wasteful; embedding the whole annex is useless for retrieval. Embed the annex's *title and header* so "화장품에 쓸 수 없는 원료 목록이 있나?" still retrieves it, after which the lookup is relational
- [x] **The annex-storage decision is taken** — [ADR-0014](../design/ADR-0014-annex-row-granularity.md), 2026-08-06. There is **no `annex_rows` table**: a row is a `Clause` with `path_segments = [별표N, 표M, 행K]` and its columns in `clauses.row_columns` (`jsonb`, keyed by the table's own header labels). Exact-match lookup is a `row_columns ->> '원료명'` predicate against `clauses`, already proven on the real corpus — `갈라민트리에치오다이드` → `별표1/표1/행1`. 1,944 rows are in the store today, so no separate index is needed for scale
- [x] Re-embedding path on model change, isolated to this service

### Retrieval (pipeline — deterministic)

- [x] Hybrid: BM25 + vector, fused ranking
- [x] Identifier lookups (제5조, § 892.2050) resolve exactly, not fuzzily
- [x] Cell scoping — retrieval is bounded by the active cell(s). **Cross-cell is an explicit mode, never the default** ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 9): a cosmetic question answered from device regulation is a confident wrong answer. Build the mode here, because [phase1.6](phase1.6_evaluation.md)'s golden set scores cross-domain questions against it
- [x] Version pinning: retrieval targets a specific `DocumentVersion`, never "latest" implicitly

### Generation (agent) & verification (agent)

- [x] Citation produced **with** the claim and constraining it — not attached afterwards. Citation is a property of generation, not a downstream step
- [x] `Citation = (document_id, document_version_id, clause_path, effective_date)`, pinned to an immutable version
- [x] **No citation possible → return "needs verification."** Never emit an unsourced answer
- [x] **Evidence-verification agent as a separate pass with the power to fail an answer** — catches the mis-citation case where the clause exists and was retrieved but does not support the claim
- [x] Confidence score per answer; below threshold routes to human review
- [x] **Every answer states the version and effective date it relied on** — rendered, e.g. *"시행일 2026-04-02 기준"* ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 8)
- [x] **Effective-date straddling is called out, not silently resolved.** The API returns `조문시행일자` per clause, so a document routinely holds in-force provisions beside amended-but-not-yet-effective ones. Where retrieved clauses straddle the boundary, say so rather than picking one — mixing them is wrong in the way that costs a customer an approval
- [x] **Track the "needs verification" rate per domain from the first golden-set run** ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 7). It is two-sided: near 0% means the threshold is too permissive and the hallucination gate is about to be missed; too high means the product is unusable however honest it is. Treat a sudden move either way as a regression
- [x] `answers`, `answer_citations`, `verification_results`, `queries` — all recording `llm_provider` / `llm_model`
- [x] Superseded-citation queue surfaced as a product feature, not a maintenance chore

## Acceptance criteria

- [x] An answer with no supporting clause returns "needs verification" — never a hedged prose answer
- [x] A stored answer's citation resolves to the same clause text after the document is amended; the citation is flagged superseded, not rewritten
- [x] A deliberately mis-cited answer is failed by the verification pass — fixture test
- [x] Sub-threshold confidence routes to review and does not reach the user as final
- [x] Identifier lookup for a known clause returns it at rank 1
- [x] Annex ingredient lookup returns the exact row, not a nearest-neighbour paragraph
- [x] An answer whose retrieved clauses straddle an effective-date boundary says so, rather than silently choosing one
- [x] Every `answers` row carries provider/model provenance
- [x] The "needs verification" rate is reported per domain alongside the two gates — **a system that refuses everything passes citation accuracy and hallucination rate cleanly**, so the gates are not self-guarding

All nine are covered by `services/assistant/tests/integration/test_phase1_3_acceptance.py` (24 cases)
against real Postgres, a real `vector` extension and a real HNSW index, with the model stubbed. The
deterministic halves — passage assembly, query parsing, fusion, the mechanical citation check,
verdict reading and routing — carry 69 further unit cases.

## What was built

| Unit | Kind | Module |
| --- | --- | --- |
| Passage assembly | pure function | `app/passages.py` |
| Embedding | pipeline | `app/embedding.py` |
| Cross-boundary reads | raw SQL, read-only | `app/store.py` |
| Hybrid retrieval | pipeline | `app/retrieval.py` |
| Citation-enforced generation | **agent** | `app/generate.py` + `app/prompts.py` |
| Evidence verification | **agent** | `app/verify.py` |
| Orchestration, scoring, routing | pipeline | `app/ask.py` |
| Superseded-citation sweep | pipeline | `app/supersede.py` |

`GET /api/v1/index/coverage`, `POST /api/v1/queries`, `GET /api/v1/answers?superseded=true` and
`GET /api/v1/metrics/answers` are the four surfaces phase 1.5's UI builds on.

## Risks & open questions

- **Embedding granularity vs annex scale** — **decided in [phase1.1](phase1.1_normalization.md) by W4 and inherited here.** This file no longer owns it; the two files previously deferred it to each other.
- **[ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 4 — golden query set composition.** Must include identifier lookups, paraphrased conceptual queries, and cross-domain questions, or the accuracy number measures the easy half. Owned by [phase1.6](phase1.6_evaluation.md).
- **Model pinning.** Changing the generation model without a golden-set regression is how citation quality silently degrades; the pin is a release gate, not a preference.
- **Lexical/vector merge weighting is a starting point, not a measurement** (ADR-0006 open question 2, still open). `RETRIEVAL_LEXICAL_WEIGHT = 1.2` against `RETRIEVAL_VECTOR_WEIGHT = 1.0` encodes the identifier-density argument, but nothing has measured it. Phase 1.6 tunes it against the golden set.
- **Reranking** (ADR-0006 open question 1, still open) was not added. Deciding it in advance was explicitly out of order; the golden set decides whether a cross-encoder pass buys more than it costs.
- **Retrieval has no relevance floor, and `no_retrieval` therefore never fires.** Hybrid search
  always returns something, so a question with no answer in the active cell is answered from the
  nearest noise instead of refused. Measured 2026-08-11 and owned by
  [phase1.6](phase1.6_evaluation.md) § Risks, with the numbers. The final state is still correct —
  verification rejects it — so this is a latency and cost problem, not a correctness one.
- **Short 서식 titles look over-represented on paraphrased queries.** Spot-checking the completed index, *"화장품 안전성 정보는 언제 보고해야 하나"* returned three `form` passages — relevant, but the 조 that carries the obligation is what the question wants. 1,018 of 7,640 passages are forms, and a form passage is a title and little else, which is short enough to score well on cosine against a short query. This is an *observation, not a diagnosis*: fixing it by eye against three hand-picked questions is exactly the guess-with-a-decimal-point that the merge weighting above is deferred to avoid. It belongs to [phase1.6](phase1.6_evaluation.md), measured per query shape.

## Deviations & decisions

1. **The database image changed to `pgvector/pgvector:pg16`.** Stock `postgres:16-alpine` carries no
   pgvector, so `CREATE EXTENSION vector` had nowhere to come from. Same PostgreSQL major version
   reading the same data directory, so the 26,254-clause corpus survived the swap untouched — but
   Debian/glibc collates text differently from Alpine/musl, so migration 0005 **reindexes every
   table once** and refreshes the database's collation version. Doing it in the migration rather
   than in a runbook means a developer who pulls this change and runs the documented
   `docker compose run --rm migrate` gets a consistent database without having to know why.

2. **A third answer status, `needs_review`.** ADR-0006's schema sketch names two
   (`answered | needs_verification`), but the plan also requires that sub-threshold confidence
   "routes to review and does not reach the user as final". Those are different states with
   different causes: `needs_verification` means something was found *wrong* (no citation, a
   fabricated one, or a rejected claim), `needs_review` means nothing was found wrong but not
   enough was found right. Collapsing them would make the monitored "needs verification" rate
   uninterpretable, because a threshold change would move it without any citation having failed.

3. **`ANSWER_CONFIDENCE_THRESHOLD` is 0.7, derived rather than chosen.** With the weights at
   0.7 verification / 0.3 retrieval rank, 0.7 is exactly the line between *every claim only
   `partial`, cited at rank 1* (0.65 → review) and *every claim `supported`, cited at the worst
   surviving rank* (0.7375 → final). Moving either weight means re-deriving this number, not
   nudging it. Phase 1.6 re-calibrates against the golden set.

4. **A GIN full-text index was added to `clauses`, which `regulation` owns.** The lexical arm needs
   it and `assistant` reads the clause store one-way by raw SQL, the same way `monitoring` reads
   `change_events`. It adds no column and changes no ownership; it lives in the shared migration
   history like every other index.

5. **The lexical arm ORs prefix terms instead of ANDing them.** PostgreSQL ships no Korean stemmer,
   so the `simple` configuration indexes 화장품 and 화장품의 as different tokens and
   `plainto_tsquery`'s AND semantics matched almost nothing. Each token is queried as a prefix, and
   Korean tokens are also queried with one trailing character stripped, so both directions of the
   particle problem are covered. It trades precision for recall deliberately — the vector arm is
   there to catch paraphrase, and `ts_rank_cd` sorts out how many terms actually hit.

6. **Annex row terms have a five-character floor, measured rather than guessed.** The first
   implementation used three, and 화장품 / 안전성 / 평가 all prefix-matched column values across
   별표 1 and 별표 2 — an ingredient lookup came back as a list of unrelated table rows. Real 원료명
   run far longer (갈라민트리에치오다이드 is eleven), so the floor costs nothing real. The store also
   matches the *reverse* direction (`term ILIKE value || '%'`) so a typed 갈라민트리에치오다이드**는**
   still finds the bare name, guarded by a minimum column-value length so a 등급 cell holding `2`
   cannot prefix-match every question containing a number.

7. **`LLM_TIMEOUT_SECONDS` and `OLLAMA_NUM_CTX` were wired up.** Both were already in `.env.dev` and
   neither was read by anything: the client hard-coded a 120-second timeout and never set a context
   window. The first killed a real generation call mid-answer and surfaced as an `httpx.ReadTimeout`
   with no `answers` row, which reads like a retrieval bug. The second matters more than it looks:
   Ollama truncates an over-long prompt silently, and a generator that loses the tail of its passage
   list cites a clause it can no longer see — a fabricated citation manufactured by configuration
   rather than by the model.

8. **`regulation`'s diff task now notifies `assistant` by task name.** An amendment moves an
   answer's evidence exactly as it stales an IR, but into a different lifecycle in another service's
   table (ADR-0006 decision 10). `regulation` does not write `answer_citations`; it sends
   `assistant.supersede_answer_citations` with the version id, and `assistant` reads `clause_diffs`
   one-way and flags its own rows. Two string constants are the entire coupling.

9. **The `migrate` compose service now honours `REGOPS_DB_NAME`.** It had a hard-coded
   `.../regops` DSN, so the documented `REGOPS_DB_NAME=regops_test docker compose run --rm migrate`
   silently re-migrated the development database and left the test one behind. Found by needing it.

10. **`MAX_PASSAGE_CHARS` is a hard cap on every passage, and it is 1,200 rather than 2,000.**
    Splitting long articles at 항 boundaries left three shapes unbounded — a whole 서식 with an
    embedded table, a table with long column labels, and a single oversized 항 — and the first
    corpus-wide run produced passages of up to **21,588 characters**. Ollama answers an over-long
    embedding request with **HTTP 500** rather than truncating, so those were not degraded vectors,
    they were 38 versions that never got indexed at all. The cap is now enforced on every passage
    whatever its kind, cutting on line boundaries and falling back to a character cut for a
    box-drawing table rendered as one enormous line. The number came down because the
    character-to-token conversion is *worse* for Korean than for English, not better: a hangul
    syllable is three UTF-8 bytes and BPE usually spends more than one token on it, so 2,000
    characters of 고시 text overran the 2,048-token window. `EMBEDDING_PASSAGE_VERSION` moved to
    `1.3.1`, which is what made the whole corpus re-embed — the re-embedding path doing its job.

11. **`model_unavailable` was added to the closed refusal inventory** (2026-08-11, while building
    [phase1.5](phase1.5_frontend.md)'s workbench — deviation 10 there). Generation and verification
    calls were unguarded, so a model timeout propagated out of the Celery task and left the query
    row with no answer at all: the monitored rate silently excluded every failure, which is the one
    direction that makes it look healthy. Both are now caught and recorded, and the verification
    side matters more — an answer whose claims were never checked must not reach a reader as though
    they had been. Two cases were added to the acceptance suite (24 now, from 22).

12. **The generation prompt had no bound, and `MAX_PASSAGE_CHARS` was not one** (2026-08-11, found
    by a user question that appeared to hang). That constant caps what gets *embedded*; a retrieval
    hit carries the raw clause text, which had no cap at all. One live question in `mfds_samd`
    produced eight hits totalling **185,161 characters — a single 별표 clause contributing
    130,603** — about 58,000 tokens against a 32,768 window, which Ollama truncates silently. The
    visible symptom was a 187-second timeout; the invisible one was a model citing passages whose
    text was cut away before it ever saw them, which is where at least some of the observed
    `fabricated_citation` rate came from. `MAX_PROMPT_BLOCK_CHARS` now bounds every block, the
    stored passage is preferred where the vector arm supplied one (it is bounded *and* it is the
    unit that was actually scored), and the citable list is capped at 24 paths. Same question after:
    **185,861 → 10,311 prompt characters, 187s timeout → 112s completed.**

13. **The answer text is composed from the validated claims; the free-text field is gone.** Found
    while measuring the above, and it is a real hole in decision 4 rather than a performance tweak:
    every citation check applied to `claims`, and the page rendered `answer` — so the one string a
    reader actually read was the one string nothing validated. Composing it from the surviving
    claims means every rendered sentence carries a citation and faces verification. It also roughly
    halves output tokens, which at the measured ~3 tokens/second is the difference between an answer
    and a timeout. `ANSWER_PROMPT_VERSION` → `1.3.1`.

14. **`model_unavailable` needed its own copy, not the shared defect sentence.** Reported from the
    UI: a refusal caused by an unreachable model rendered as *"모델이 잘못된 응답을 냈다는 뜻입니다"*
    when the model had not responded at all. Refusal reasons now carry three tones — `expected`
    (the product working), `regression` (the model misbehaved), `infrastructure` (never reached) —
    and one accurate sentence each.

15. **Both services' `tests/conftest.py` now claim the `app` package.** Every service names its
    package `app`, which was harmless while only `regulation` had a unit suite. The documented gate
    `python -m pytest shared/tests services/*/tests/unit -q` imported one service's `app` and handed
    it to the other. Each conftest now evicts a cached `app` that does not live under its own
    service root.
