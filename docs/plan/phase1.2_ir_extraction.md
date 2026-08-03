# Phase 1.2 — IR extraction

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W3–W8 · **Status:** ⬜ planned
- **Governed by:** [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md), [ADR-0008](../design/ADR-0008-service-composition.md) decisions 2 · 5
- **Depends on:** [phase1.1](phase1.1_normalization.md)
- **Service:** `regulation` — the **Requirement Extraction agent**, RegOps' first LLM unit

---

## Goal

Turn clauses into atomic, cited obligations. IR is the product's load-bearing abstraction: gap
analysis maps IRs to controls, answers cite the clauses IRs point at, and change alerts are graded
by which IRs an amendment touches. An imprecise IR definition degrades all three at once.

This is the first place an LLM writes a row, so it is also where provenance and the human gate get
built for real.

## Scope

**In:** extraction rule sets per domain, the draft → locked lifecycle, clause classification,
re-derivation on amendment.

**Out:** control mapping (2.2), semantic enrichment and cross-references (2.1). Interpretation is
**not** a separate unit — structuring obligation · bearer · scope · evidence *is* IR extraction
([ADR-0008](../design/ADR-0008-service-composition.md) decision 6).

## Tasks

### Atomicity rules — W3–4, critical path

- [ ] One IR = **one bearer + one modal + one required action**, conditions attached rather than split out
- [ ] Modal inventory fixed per language: KO `하여야 한다 / 해야 한다 / -도록 한다 / 금지한다 / 아니 된다`; EN `shall / must / is required to / may not`
- [ ] Permissive forms (`할 수 있다`, `may`) yield **no IR** — recorded as context on a related IR
- [ ] Conjunction of obligations in one clause yields one IR each, all citing that clause

### Schema

- [ ] `irs(id, domain_profile, bearer, modal, statement, condition_text, taxonomy_code, status, supersedes_ir_id, stale_since, extraction_run_id, locked_by, locked_at)`
- [ ] `status ∈ draft | locked | stale | superseded`
- [ ] `ir_citations(ir_id, document_version_id, clause_path, effective_date, superseded_at)`
- [ ] `ir_standard_citations(ir_id, standard_reference_id)` — resolves to a deep link, never stored text. **Depends on `standard_references`, created in [phase1.0](phase1.0_ingestion.md)**; this FK previously pointed at a table no phase built
- [ ] `extraction_runs(id, rule_version, prompt_version, llm_provider, llm_model, started_at)`
- [ ] `clause_classifications(clause_id, kind, exclusion_reason, classified_by, classified_at)`

### The domain branch

- [ ] `domain_profile` selects an **extraction rule set** — modal inventory, obligation taxonomy, prompt — and nothing else. Same tables, same stages, same lifecycle
- [ ] SaMD taxonomy: design control · risk · V&V · postmarket
- [ ] Cosmetic taxonomy: ingredient · labelling · claims · GMP · notification

### Invariants

- [ ] **An IR without a citation does not exist** — extraction that cannot attach `(document_version_id, clause_path)` is *rejected*, not stored with a null citation. There is no draft state for an uncited IR
- [ ] **LLM proposes, human locks.** Extraction produces `status = draft`; an `ra` reviews and locks. Only `locked` IRs are visible to answer generation, impact grading, and gap analysis
- [ ] Every IR records `llm_provider`, `llm_model`, `prompt_version`, `rule_version`, `extraction_run_id`; locking records signer and timestamp
- [ ] **Non-obligation clauses are marked reviewed, not skipped** — definitions, scope statements and headings classify as `excluded` with a reason, so coverage is provable rather than assumed
- [ ] **Amendments re-derive, never mutate.** A diff touching a cited clause marks the IR `stale`; re-extraction produces a **new** IR with `supersedes` pointing at the frozen old one

## Acceptance criteria

- [ ] The atomicity rule is operative, not advisory — measured as inter-rater agreement on IR count over a fixed clause sample. **Requires two raters, and Phase 1 staffs 1 RA** (development-plan.md § 7, risk 7). Either the part-time second RA is funded, or this degrades to same-rater test–retest at ≥ 2 weeks' separation — which detects an ambiguous *rule* but not a rater's consistent private interpretation of it. Choose deliberately and record it; do not discover at W9 that the criterion was never runnable
- [ ] An uncited extraction is rejected; no null-citation row can be written
- [ ] A `viewer` cannot lock; an `ra` can — negative-path test
- [ ] A draft IR is invisible to retrieval and impact grading
- [ ] Amending a cited clause marks the IR stale and produces a superseding IR, old one intact
- [ ] Every `irs` row carries a non-null `llm_provider` / `llm_model`
- [ ] Every clause in a processed version is either obligation-bearing or `excluded` with a reason — no unclassified remainder

## Risks & open questions

- **[ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 3 — conditional obligations by product class.** One parameterised IR or one per class? Parameterised is smaller; per-class maps to controls more directly. Applicability itself is Compliance-owned (2.2), tenant-scoped — the IR only carries the condition.
- **Open question 5 — extraction determinism.** Same clause, same rule and model version should yield the same IRs; LLM sampling makes this approximate. Decide: pin temperature to 0 and treat any delta as a regression, or accept variance and gate on golden-set score only.
- **Ground-truth markup is a phase 1.6 dependency landing at W7–8** and must be built **blind** to extractor output. Sequencing matters — see [phase1.6](phase1.6_evaluation.md).

## Deviations & decisions

_None yet._
