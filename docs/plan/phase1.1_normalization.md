# Phase 1.1 — Normalization

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W3–W6 · **Status:** ⬜ planned
- **Governed by:** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
- **Depends on:** [phase1.0](phase1.0_ingestion.md)
- **Service:** `regulation` (L2)

---

## Goal

Turn archived bytes into an addressable, diffable clause store. **This is the critical path** —
ADR-0002 calls the clause model the most expensive thing in RegOps to change later, because altering
it after ingestion means re-parsing the archive and invalidating every stored citation.

This phase also carries both architecture falsifiers. They are not milestones to pass; they are
tests designed to fail loudly if the shared-pipeline bet is wrong.

## Scope

**In:** parser profiles, clause segmentation, `DocumentVersion`, `ClauseDiff`, `ChangeEvent`
emission, renumbering resolution.

**Out:** IR extraction (1.2), embeddings (1.3), alert routing (1.4). Multilingual is *modelled* here
but not exercised — both gated cells are Korean-only.

## Tasks

### Clause schema — W3–4, do not defer

- [ ] `clauses(document_version_id, clause_path, path_segments, level, ordinal, heading, text)`
- [ ] **Domain-neutral** — no SaMD-only or Cosmetic-only column. 조/항/호 and Part/Subpart/§ are both ordered hierarchical paths
- [ ] `DocumentVersion` per `(document, version, language)` with a shared `version_group_id`
- [ ] Immutable once written; `parser_version` recorded

### Parser profiles

- [ ] Hierarchy mode — 조/항/호/목 from 본문조회
- [ ] **Table mode** — fixed-width box-drawing annexes (`┌ ├ │ ┬ ┼` at consistent offsets), one `Clause` per row with `path_segments = [별표N, row]`. Mechanical and deterministic; **no LLM in the parsing path**
- [ ] Both modes used by both domains — the split is prose vs table, not SaMD vs Cosmetic

### Diffing

- [ ] `clause_diffs(from_version_id, to_version_id, clause_path, change_kind, from_clause_id, to_clause_id, similarity)`
- [ ] `change_kind ∈ added | removed | modified | renumbered | moved`
- [ ] **Renumbering resolved explicitly, never reported as delete + add.** Primary signal is the authority's own: `조문변경여부`, `조문이동이전`, `조문이동이후` from law.go.kr. Content-similarity matching is the fallback for sources exposing nothing
- [ ] Low-confidence renumber matches queue for RA review
- [ ] Diffs computed **within one language** — KO for MFDS
- [ ] `ChangeEvent` emitted from `ClauseDiff`, fanned out to every claiming cell

### Citation support

- [ ] Superseded-citation detection: when a diff touches a cited clause path, mark citations `superseded` and queue re-verification. **Never rewrite a citation**

## Falsifiers — escalate, do not work around

- [ ] **Annex representation (W3–4).** Can a 화장품 안전기준 규정 limit-table row be expressed as a `Clause` with `path_segments`? Must be answered *before* the W5–6 check, not during it. Failing this falsifies [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 3
- [ ] **Cross-domain (W5–6).** Does Cosmetic parse without forking Normalization or Section Parsing? A Cosmetic-only column on `Clause`, a second pre-IR stage, or a domain-forked parser all falsify [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 3 — and Phase 2's six-cell build rests on it

> The live API test on 2026-07-29 did **not** trigger the falsifier: the same box-drawing annexes
> appear on the SaMD side, and 별표 3 of the cosmetic 고시 is pure prose. Re-run against real
> ingestion rather than treating the spike as settled.

## Acceptance criteria

- [ ] 화장품법 and 의료기기법 both parse to clauses through one pipeline, no domain branch
- [ ] A renumbered-but-unchanged clause reports `renumbered`, never delete + add — integration test
- [ ] An annex limit-table row round-trips as a `Clause` and is addressable by `clause_path`
- [ ] A change event for the FD&C Act pattern fans out to every claiming cell and no others
- [ ] Amending a cited clause flags the citation superseded and leaves its text resolvable

## Risks & open questions

- **Annex scale** ([ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 2) — 별표 1 of 화장품 안전기준 규정 alone is 340,074 chars / 7,367 lines. One `Clause` per row means tens of thousands of rows per 고시. Feeds phase 1.3's embedding-granularity decision; needs an answer before the W5–6 retrieval index.
- **Multilingual is modelled, not built.** First real exercise is the EU spike. Do not let Korean-only assumptions leak into the schema.

## Deviations & decisions

_None yet._
