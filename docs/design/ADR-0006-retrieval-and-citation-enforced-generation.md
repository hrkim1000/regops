# ADR-0006 — Retrieval and citation-enforced generation

- **Status:** Proposed
- **Date:** 2026-07-29
- **Depends on:** [ADR-0002](ADR-0002-canonical-regulation-model.md), [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md), [ADR-0005](ADR-0005-service-architecture.md) (`assistant` service)
- **Resolves:** ADR-0002 open question 1 (embedding granularity), ADR-0004 open question 2 (annex scale)
- **Critical path:** development-plan.md § 6 — retrieval index at W5-6, citation-enforced generation at W7-8

---

## Context

This layer owns **two of the six Phase 1 gates outright**: citation accuracy ≥ 90% and hallucination
rate ≤ 2%. Neither is an ingestion problem — they are won or lost in what gets retrieved and how
generation is constrained.

The [live API test](spike-2026-07-29-mfds-source-recon.md) changed the shape of this problem. 화장품법
yields ~358 addressable units (74 조 / 126 항 / 151 호 / 7 목), but 별표 1 of 화장품 안전기준 규정
alone is **7,367 lines of ingredient table**. Those two are not the same retrieval problem, and
treating them as one is the main way this layer fails.

## Decisions

### 1. Embed coarse, cite fine

Embedding unit is the **조 (article)**, with its 항/호/목 rolled into one passage. Citation still
resolves to the finest clause the answer actually relies on.

A 호 embedded alone is unretrievable in practice — `3. 갈색` carries no meaning without its parent
항 and 조. Embedding at 호 level produces thousands of fragments that match nothing and dilute the
index. But citing at 조 level would violate the citation contract, which requires clause-level
precision (RegOps.md).

So the two granularities are deliberately different: **retrieval needs context, citation needs
precision.** The retrieved 조 passage carries its child clause paths, and generation cites whichever
child it used.

Long 조 exceeding the embedding window are split at 항 boundaries with the 조 heading prepended to
each fragment, so every fragment stays self-describing.

### 2. Ingredient tables are looked up, not embedded

**Do not embed table rows.** 별표 1 and 2 are 35–43% box-drawing table lines; the rows are
near-identical in structure and differ only in a substance name, a CAS number and a limit. That is
the worst possible input to a semantic index — thousands of vectors clustered so tightly that
similarity is noise.

The question a user actually asks is *"갈라민트리에치오다이드는 사용할 수 있나?"* or
*"CAS 65-29-2 의 사용한도는?"*. That is an **exact lookup**, not a semantic search.

So annex tables are parsed into a **structured row store** (substance · CAS · limit · condition ·
product type) and served by exact and prefix match on the identifier columns. What gets embedded is
the annex's *title and header* — enough for "화장품에 쓸 수 없는 원료 목록이 있나?" to retrieve the
annex, after which the lookup is relational.

Each row remains a `Clause` so it is independently citable (ADR-0004). Citability and embedding are
separate concerns; only the latter is skipped.

> **Path refined by [ADR-0014](ADR-0014-annex-row-granularity.md) decision 3** to
> `[별표N, 표M, 행K]`. The two-segment sketch assumed one table per annex; the corpus has 62 tables
> across 24 별표, so a row needs its table named to stay addressable when another is inserted ahead
> of it — and the 표 node is where the per-table column map lives.

### 3. Hybrid retrieval, split by what the query keys on

BM25 (or exact index) and vector search both run; results are merged.

| Query shape | Served by |
|---|---|
| 원료명, CAS No., 조문 번호, 고시 번호 | **lexical / exact** — these are identifiers, and an embedding of `65-29-2` is meaningless |
| "언제까지 신고해야 하나", "안전성 평가 의무가 있나" | **vector** — paraphrase-tolerant |
| "화장품법 제8조" | **lexical**, direct clause resolution |

The 별표 finding makes this concrete rather than theoretical: regulatory corpora are unusually
identifier-dense, so a vector-only design underperforms badly on exactly the questions RA staff ask
most.

### 4. Generation may only cite what retrieval returned

The generator receives the retrieved clause set and is constrained to cite from it. A citation that
names a clause **not in the retrieved set is rejected outright** — the answer is regenerated or
downgraded to "needs verification".

This kills the cheapest hallucination: a plausible-looking 조문 number the model produced from
memory. It is a mechanical check, not a judgement, and it runs before any model-based verification.

### 5. Two hallucination classes, both counted against the gate

| Class | Detection |
|---|---|
| **Fabricated citation** — clause does not exist, or was not retrieved | mechanical (decision 4) |
| **Mis-citation** — clause exists and was retrieved, but does not support the claim | evidence-verification agent |

The second is the dangerous one: it survives every structural check and looks correct to a reader
who does not open the citation. The ≤ 2% gate counts both, and the golden set must contain
mis-citation cases deliberately — otherwise the measured rate reflects only the easy class.

### 6. The evidence-verification agent is a separate pass with the power to fail an answer

It sees the answer and the cited clause text — **not** the original question phrasing, which biases
toward agreement — and judges whether the text supports each claim. It can reject.

A verifier that only annotates is theatre. Its verdict feeds the confidence score, and a rejected
claim forces "needs verification" rather than a caveat appended to a wrong answer.

### 7. "Needs verification" is a product output, and its rate is a monitored metric

Returning it is success, not failure — it is the promise in RegOps.md that no unsourced answer is
generated.

But the rate is a two-sided signal: near 0% means the threshold is too permissive and the
hallucination gate is about to be missed; too high means the product is unusable regardless of how
honest it is. Track it per domain from the first golden-set run, and treat a sudden move either way
as a regression.

### 8. Every answer states the version and effective date it relied on

An answer is scoped to `(document_version, effective_date)`, rendered with it — *"시행일 2026-04-02
기준"*.

The live API returns `조문시행일자` per clause, so a document routinely contains provisions in force
alongside provisions amended-but-not-yet-effective. An answer that silently mixes them is wrong in
the way that costs a customer an approval. Where the retrieved clauses straddle an effective-date
boundary, say so rather than picking one.

### 9. Retrieval is cell-scoped

A query in `mfds_cosmetic` does not retrieve `mfds_samd` clauses. Cross-cell retrieval is an explicit
mode, not the default — a cosmetic question answered from device regulation is a confident wrong
answer, the worst failure this product can produce.

### 10. Answer citations are not IR citations

Distinct tables, distinct lifecycles (ADR-0005 owns `answer_citations` in `assistant`;
`ir_citations` lives in `regulation`).

- IR citation → clause amended → IR goes **stale**, re-derived (ADR-0004 dec 5)
- Answer citation → clause amended → answer goes **superseded**, re-verified (ADR-0002 dec 4)

They share a shape and nothing else. Merging them would couple the answer log to the obligation
model and make an amendment rewrite history in both.

## Schema additions

```sql
clause_embeddings(clause_id, scope, vector, model, dim, created_at)   -- scope = 조-level passage
-- annex_rows: SUPERSEDED by ADR-0014. Annex rows are `clauses` with
-- path_segments = [별표N, 표M, 행K] and per-table columns in clauses.row_columns (jsonb).
-- The fixed column set below fits 별표 2 of one 고시 and nothing else.
queries(id, tenant_id, cell_id, text, asked_by, asked_at)
answers(id, query_id, text, confidence, status, llm_provider, llm_model,
        document_version_scope, effective_date_scope)                -- status: answered | needs_verification
answer_citations(answer_id, document_version_id, clause_path, superseded_at)
verification_results(answer_id, claim_index, verdict, reason, verifier_model)
```

## Open questions

1. **Reranking** — worth a cross-encoder pass over merged hybrid results, or does it cost more
   latency than it buys at this corpus size? Decide with the golden set, not in advance.
2. **Merge weighting** between lexical and vector results. Regulatory corpora are identifier-dense
   (decision 3), so the usual defaults probably over-weight vector. Needs tuning per domain.
3. ~~**Annex row-store vs. clause store duplication**~~ — **closed by
   [ADR-0014](ADR-0014-annex-row-granularity.md): there is no `annex_rows` table.** An annex table
   row is a `Clause` addressed by `clause_path` like any other, with per-table columns in a `jsonb`
   field, so `ir_citations` needs no branch and there is no second store to keep in sync. The
   `annex_rows` line in *Schema additions* below is superseded.

   Decisions 1 and 2 above are **untouched**: rows are still not embedded and are still served by
   exact match. That is a *retrieval* decision; where rows are *stored* is a separate one, and the
   two were being conflated. The original reasoning follows.

   > **The row count was measured on 2026-08-05, and it removes the premise.** This question leans
   > toward a separate store *conditionally* — "revisit if the row count makes sync a burden" — and
   > that condition is not met. The whole gated corpus holds **1,967 logical table rows**, 1,904 of
   > them in 별표-kind annexes, with 별표 1 사용할 수 없는 원료 alone accounting for 1,078. Earlier
   > estimates of "tens of thousands per 고시" counted *physical lines*: a row inside a box-drawing
   > table wraps across several, so line counts overstate rows by roughly 16×.
   >
   > 1,967 rows is one ordinary table with an index. Nothing about sync is a burden at that size, so
   > the argument that favoured `annex_rows` no longer applies and the duplication it accepts buys
   > nothing.
   >
   > **Decisions 1 and 2 above are untouched.** Annex rows are still not embedded and are still
   > served by exact match — that is a *retrieval* decision. Where the rows are *stored* is separate,
   > and the two were being conflated. [phase1.1](../plan/phase1.1_normalization.md) owns the
   > resolution, due W4, and leans toward rows living in `clauses` addressed by `clause_path` so the
   > citation contract needs no branch. Also unresolved and belonging in the same ADR: how per-table
   > columns are typed, since every table has a different column set.
4. **Golden query set composition** — must include identifier lookups, paraphrased conceptual
   questions, effective-date-straddling cases, and deliberate mis-citation traps. 200 items split
   across two domains is thin for that many axes.

## What this unblocks

W5-6 retrieval index and W7-8 citation-enforced generation. Next: the context map and applicability
model (Product and Compliance contexts), which Phase 2 gap analysis depends on.
