# Phase 1.2 — IR extraction

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W3–W8 · **Status:** 🟢 done (2026-08-07) — 7/7 acceptance
- **Governed by:** [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md), [ADR-0008](../design/ADR-0008-service-composition.md) decisions 2 · 5, [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md)
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

- [x] One IR = **one bearer + one modal + one required action**, conditions attached rather than split out
- [x] Modal inventory fixed per language: KO `하여야 한다 / 해야 한다 / -도록 한다 / 금지한다 / 아니 된다`; EN `shall / must / is required to / may not`
- [x] Permissive forms (`할 수 있다`, `may`) yield **no IR** — recorded as context on a related IR
- [x] Conjunction of obligations in one clause yields one IR each, all citing that clause

### Schema

- [x] `irs(id, domain_profile, bearer, modal, statement, condition_text, taxonomy_code, status, supersedes_ir_id, stale_since, extraction_run_id, locked_by, locked_at)`
- [x] `status ∈ draft | locked | stale | superseded`
- [x] `ir_citations(ir_id, document_version_id, clause_path, effective_date, superseded_at)`
- [x] `ir_standard_citations(ir_id, standard_reference_id)` — resolves to a deep link, never stored text. **Depends on `standard_references`, created in [phase1.0](phase1.0_ingestion.md)**; this FK previously pointed at a table no phase built
- [x] `extraction_runs(id, rule_version, prompt_version, llm_provider, llm_model, started_at)`
- [x] `clause_classifications(clause_id, kind, exclusion_reason, classified_by, classified_at)`

### The domain branch

- [x] `domain_profile` selects an **extraction rule set** — modal inventory, obligation taxonomy, prompt — and nothing else. Same tables, same stages, same lifecycle
- [x] SaMD taxonomy: design control · risk · V&V · postmarket
- [x] Cosmetic taxonomy: ingredient · labelling · claims · GMP · notification

### Invariants

- [x] **An IR without a citation does not exist** — extraction that cannot attach `(document_version_id, clause_path)` is *rejected*, not stored with a null citation. There is no draft state for an uncited IR
- [x] **LLM proposes, human locks.** Extraction produces `status = draft`; an `ra` reviews and locks. Only `locked` IRs are visible to answer generation, impact grading, and gap analysis
- [x] Every IR records `llm_provider`, `llm_model`, `prompt_version`, `rule_version`, `extraction_run_id`; locking records signer and timestamp
- [x] **Non-obligation clauses are marked reviewed, not skipped** — definitions, scope statements and headings classify as `excluded` with a reason, so coverage is provable rather than assumed
- [x] **Amendments re-derive, never mutate.** A diff touching a cited clause marks the IR `stale`; re-extraction produces a **new** IR with `supersedes` pointing at the frozen old one

## Acceptance criteria

- [x] The atomicity rule is operative, not advisory — measured as inter-rater agreement on IR count over a fixed clause sample. **Requires two raters, and Phase 1 staffs 1 RA** (development-plan.md § 7, risk 7). Either the part-time second RA is funded, or this degrades to same-rater test–retest at ≥ 2 weeks' separation — which detects an ambiguous *rule* but not a rater's consistent private interpretation of it. Choose deliberately and record it; do not discover at W9 that the criterion was never runnable — **decided: test–retest, deviation 3**
- [x] An uncited extraction is rejected; no null-citation row can be written
- [x] A `viewer` cannot lock; an `ra` can — negative-path test
- [x] A draft IR is invisible to retrieval and impact grading
- [x] Amending a cited clause marks the IR stale and produces a superseding IR, old one intact
- [x] Every `irs` row carries a non-null `llm_provider` / `llm_model`
- [x] Every clause in a processed version is either obligation-bearing or `excluded` with a reason — no unclassified remainder

Covered by `services/regulation/tests/integration/test_phase1_2_acceptance.py` (10 tests, all
green against the real stack) plus `tests/unit/test_extraction_rules.py`,
`test_extraction_agent.py`, `test_ir_api.py` and `test_ir_agreement.py`.

## Risks & open questions

- ~~**[ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 3 — conditional obligations by product class.**~~ **Closed** by [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 2: **one parameterised IR**, restriction in `condition_text`. Applicability is Compliance-owned and tenant-scoped (2.2); fanning out per class here would have the shared reference layer decide applicability for every tenant.
- ~~**Open question 5 — extraction determinism.**~~ **Closed** by [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 1: temperature pinned to 0, stored on the run, delta treated as a regression. Greedy decoding is not determinism, so it is a measured target — see deviation 5.
- **Ground-truth markup is a phase 1.6 dependency landing at W7–8** and must be built **blind** to extractor output. Sequencing matters — see [phase1.6](phase1.6_evaluation.md). `scripts/ir_agreement.py` is built and tested but has **no markup to run against yet**; the measurement is not a claim about quality until 1.6 supplies one.
- **Recall against clauses that phrase an obligation outside the modal inventory is untested.** See deviation 2 — the design is faithful to ADR-0004 decision 1 and the exposure is real, and 1.6's markup is what will size it.

## Deviations & decisions

1. **Extraction is not chained off the parse stage.** Every other stage in `regulation` runs on
   every fetch; this one calls an LLM per obligation-bearing clause and the gated corpus is 25,729
   clauses, so auto-running it on each poll would spend a full extraction to discover nothing
   changed. A first extraction is triggered explicitly — `POST /api/v1/document-versions/{id}/extract`
   or the `regulation.extract_document_version` task — and amendments are covered by the targeted
   re-derivation sweep the diff stage enqueues. *Cost of the choice:* a newly ingested document has
   no IRs until someone asks, so "coverage" now has two meanings (ingested vs. extracted) and the
   `/coverage` endpoint reports the second.

2. **A clause with no inventory modal never reaches the LLM.** ADR-0004 decision 1 fixes a *closed*
   modal inventory, so "does this clause state an obligation" is a regex question and the model is
   asked only to restate duties in clauses whose modals were already found. This is what makes the
   atomicity rule operative rather than advisory, and it makes the IR count reproducible at
   temperature 0. **The recall exposure is real and stated rather than hidden:** an obligation
   phrased outside the inventory is invisible to extraction. It is still *classified* — `excluded`
   with `no_obligation` — so it appears in coverage as examined-and-empty and phase 1.6's blind
   markup can contradict it. If it does, the fix is to widen the inventory in ADR-0004, not to
   loosen the gate here.

3. **The atomicity criterion runs as same-rater test–retest, not inter-rater.** Phase 1 staffs one
   RA (development-plan.md § 7, risk 7) and no second rater is funded, so the criterion as written
   is not runnable. `scripts/ir_agreement.py` implements both modes, labels which one ran, and
   **prints the caveat with the score**: test–retest detects an unstable rule and an unstable
   reader, but not a reader's consistent private interpretation of an ambiguous rule — the same
   misreading returns both times and scores as perfect agreement. A passing number is necessary,
   never sufficient. Floor is 0.80 exact agreement on IR count over a *declared* sample, and the
   script exits non-zero below it so it can gate a release. Revisit if a second RA is funded.

4. **`clause_classifications` is keyed per (clause, domain profile), not per clause.** ADR-0004's
   schema sketch shows `clause_classifications(clause_id, kind, …)` with no domain. 인체적용제품의
   위해성평가에 관한 규정 is claimed by both gated cells for real, and a clause bearing a duty under
   the SaMD taxonomy may bear none under the Cosmetic one — one shared row would force the two
   readings to agree, which is the domain branch decision 3 keeps separate. Same reason
   `extraction_runs` carries `domain_profile`: a version claimed by both cells is two runs.

5. **Temperature 0 is enforced where it is enforceable, and measured where it is not.** The value
   used is stored on `extraction_runs.temperature` rather than assumed from a constant, and the
   acceptance suite asserts the client was actually called with it. Greedy decoding is still not
   determinism — batching, quantization and a provider-side model update all move output — so the
   claim is a regression target scored per `(rule_version, prompt_version, llm_model)` in 1.6, not
   a guarantee. Recorded in [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md).

6. **The uncited-IR invariant is a database trigger, not only extractor code.** A FK cannot express
   "at least one" in that direction, so migration 0004 adds a `DEFERRABLE INITIALLY DEFERRED`
   constraint trigger checked from both sides — inserting an IR that never gets a citation, and
   deleting the last citation off one that exists. Deferred because an IR necessarily precedes its
   citations inside one transaction. Two bugs were found *by* building it this way rather than by
   review: PL/pgSQL prepares a SQL `CASE` whole, so `OLD.ir_id` type-checked against the `irs`
   trigger and failed every legitimate insert; and a deferred check must skip rows deleted later in
   the same transaction, or ordinary "unlink then delete" cleanup raises a spurious violation.

7. **A stale IR whose clause was removed stays stale.** Re-derivation supersedes an IR only when it
   produces a successor. "This obligation no longer exists" is the highest-impact thing an amendment
   can say and it is an RA's call, not a sweep's — so those IRs stay `stale` and visible as work,
   counted as `unresolved` on the sweep rather than folded into `superseded`.

8. **`migrate` cannot target the test database.** The compose `migrate` service hard-codes
   `DATABASE_URL` to `…/regops`, so `REGOPS_DB_NAME=regops_test docker compose run --rm migrate`
   silently migrates the *dev* database and the integration suite then fails on missing tables.
   Worked around with an explicit override:
   `docker compose run --rm -e DATABASE_URL=postgresql+asyncpg://regops:regops@db:5432/regops_test migrate`.
   Pre-existing and not fixed here — it belongs with the CI work deferred from phase 0.
