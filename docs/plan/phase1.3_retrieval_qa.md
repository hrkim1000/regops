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
- [ ] **Annex table rows are not embedded** — served from a structured row store by exact match. Embedding every ingredient row is wasteful; embedding the whole annex is useless for retrieval
- [ ] Re-embedding path on model change, isolated to this service

### Retrieval (pipeline — deterministic)

- [ ] Hybrid: BM25 + vector, fused ranking
- [ ] Identifier lookups (제5조, § 892.2050) resolve exactly, not fuzzily
- [ ] Cell scoping — retrieval is bounded by the active cell(s)
- [ ] Version pinning: retrieval targets a specific `DocumentVersion`, never "latest" implicitly

### Generation (agent) & verification (agent)

- [ ] Citation produced **with** the claim and constraining it — not attached afterwards. Citation is a property of generation, not a downstream step
- [ ] `Citation = (document_id, document_version_id, clause_path, effective_date)`, pinned to an immutable version
- [ ] **No citation possible → return "needs verification."** Never emit an unsourced answer
- [ ] **Evidence-verification agent as a separate pass with the power to fail an answer** — catches the mis-citation case where the clause exists and was retrieved but does not support the claim
- [ ] Confidence score per answer; below threshold routes to human review
- [ ] `answers`, `answer_citations`, `verification_results`, `queries` — all recording `llm_provider` / `llm_model`
- [ ] Superseded-citation queue surfaced as a product feature, not a maintenance chore

## Acceptance criteria

- [ ] An answer with no supporting clause returns "needs verification" — never a hedged prose answer
- [ ] A stored answer's citation resolves to the same clause text after the document is amended; the citation is flagged superseded, not rewritten
- [ ] A deliberately mis-cited answer is failed by the verification pass — fixture test
- [ ] Sub-threshold confidence routes to review and does not reach the user as final
- [ ] Identifier lookup for a known clause returns it at rank 1
- [ ] Annex ingredient lookup returns the exact row, not a nearest-neighbour paragraph
- [ ] Every `answers` row carries provider/model provenance

## Risks & open questions

- **Embedding granularity vs annex scale** — inherited from [phase1.1](phase1.1_normalization.md). Must be settled before the W5–6 index build, not during it.
- **[ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 4 — golden query set composition.** Must include identifier lookups, paraphrased conceptual queries, and cross-domain questions, or the accuracy number measures the easy half. Owned by [phase1.6](phase1.6_evaluation.md).
- **Model pinning.** Changing the generation model without a golden-set regression is how citation quality silently degrades; the pin is a release gate, not a preference.

## Deviations & decisions

_None yet._
