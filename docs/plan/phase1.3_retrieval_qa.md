# Phase 1.3 — Retrieval & citation-enforced Q&A

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W5–W10 · **Status:** ⬜ planned
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

- [ ] `clause_embeddings` in the `assistant` service. Coupling the embedding lifecycle to the clause lifecycle would make a model swap a `regulation` migration
- [ ] pgvector, `nomic-embed-text` 768-dim, HNSW cosine — pinned regardless of generation provider
- [ ] **Embed at 조 level with 항/호/목 rolled in; cite at the finest clause actually used**
- [ ] **Annex table rows are not embedded** — served by exact match. Embedding every ingredient row is wasteful; embedding the whole annex is useless for retrieval. Embed the annex's *title and header* so "화장품에 쓸 수 없는 원료 목록이 있나?" still retrieves it, after which the lookup is relational
- [ ] **The annex-storage decision is taken** — [ADR-0014](../design/ADR-0014-annex-row-granularity.md), 2026-08-06. There is **no `annex_rows` table**: a row is a `Clause` with `path_segments = [별표N, 표M, 행K]` and its columns in `clauses.row_columns` (`jsonb`, keyed by the table's own header labels). Exact-match lookup is a `row_columns ->> '원료명'` predicate against `clauses`, already proven on the real corpus — `갈라민트리에치오다이드` → `별표1/표1/행1`. 1,944 rows are in the store today, so no separate index is needed for scale
- [ ] Re-embedding path on model change, isolated to this service

### Retrieval (pipeline — deterministic)

- [ ] Hybrid: BM25 + vector, fused ranking
- [ ] Identifier lookups (제5조, § 892.2050) resolve exactly, not fuzzily
- [ ] Cell scoping — retrieval is bounded by the active cell(s). **Cross-cell is an explicit mode, never the default** ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 9): a cosmetic question answered from device regulation is a confident wrong answer. Build the mode here, because [phase1.6](phase1.6_evaluation.md)'s golden set scores cross-domain questions against it
- [ ] Version pinning: retrieval targets a specific `DocumentVersion`, never "latest" implicitly

### Generation (agent) & verification (agent)

- [ ] Citation produced **with** the claim and constraining it — not attached afterwards. Citation is a property of generation, not a downstream step
- [ ] `Citation = (document_id, document_version_id, clause_path, effective_date)`, pinned to an immutable version
- [ ] **No citation possible → return "needs verification."** Never emit an unsourced answer
- [ ] **Evidence-verification agent as a separate pass with the power to fail an answer** — catches the mis-citation case where the clause exists and was retrieved but does not support the claim
- [ ] Confidence score per answer; below threshold routes to human review
- [ ] **Every answer states the version and effective date it relied on** — rendered, e.g. *"시행일 2026-04-02 기준"* ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 8)
- [ ] **Effective-date straddling is called out, not silently resolved.** The API returns `조문시행일자` per clause, so a document routinely holds in-force provisions beside amended-but-not-yet-effective ones. Where retrieved clauses straddle the boundary, say so rather than picking one — mixing them is wrong in the way that costs a customer an approval
- [ ] **Track the "needs verification" rate per domain from the first golden-set run** ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 7). It is two-sided: near 0% means the threshold is too permissive and the hallucination gate is about to be missed; too high means the product is unusable however honest it is. Treat a sudden move either way as a regression
- [ ] `answers`, `answer_citations`, `verification_results`, `queries` — all recording `llm_provider` / `llm_model`
- [ ] Superseded-citation queue surfaced as a product feature, not a maintenance chore

## Acceptance criteria

- [ ] An answer with no supporting clause returns "needs verification" — never a hedged prose answer
- [ ] A stored answer's citation resolves to the same clause text after the document is amended; the citation is flagged superseded, not rewritten
- [ ] A deliberately mis-cited answer is failed by the verification pass — fixture test
- [ ] Sub-threshold confidence routes to review and does not reach the user as final
- [ ] Identifier lookup for a known clause returns it at rank 1
- [ ] Annex ingredient lookup returns the exact row, not a nearest-neighbour paragraph
- [ ] An answer whose retrieved clauses straddle an effective-date boundary says so, rather than silently choosing one
- [ ] Every `answers` row carries provider/model provenance
- [ ] The "needs verification" rate is reported per domain alongside the two gates — **a system that refuses everything passes citation accuracy and hallucination rate cleanly**, so the gates are not self-guarding

## Risks & open questions

- **Embedding granularity vs annex scale** — **decided in [phase1.1](phase1.1_normalization.md) by W4 and inherited here.** This file no longer owns it; the two files previously deferred it to each other.
- **[ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 4 — golden query set composition.** Must include identifier lookups, paraphrased conceptual queries, and cross-domain questions, or the accuracy number measures the easy half. Owned by [phase1.6](phase1.6_evaluation.md).
- **Model pinning.** Changing the generation model without a golden-set regression is how citation quality silently degrades; the pin is a release gate, not a preference.

## Deviations & decisions

_None yet._
