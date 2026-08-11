# ADR-0004 — IR extraction and domain branching

- **Status:** Accepted — built in [phase1.2](../plan/phase1.2_ir_extraction.md) (2026-08-07)
- **Date:** 2026-07-29
- **Depends on:** [ADR-0002](ADR-0002-canonical-regulation-model.md) (canonical model), [ADR-0003](ADR-0003-ingestion-and-change-detection.md) (ingestion)
- **Resolves:** ADR-0002 open question 2 (IR versioning vs. re-derivation)
- **Critical path:** development-plan.md § 6 — "define IR extraction rules and clause schema" at W3-4

---

## Scope of this contract

Unlike ADR-0003, **this ADR's full scope is Phase 1 scope.** Both gated cells are MFDS but they are
*different domains* — `mfds_samd` and `mfds_cosmetic` — so the domain branch defined here is
exercised in full during the PoC. This is deliberate: the branch is the architectural bet, and
Phase 1 exists to test it (development-plan.md § 5).

Region-specific extraction (FDA, EU, NMPA) is deferred; the rules below are written to be keyed by
domain, not by region.

## Context

import-agent.md claims Import → Normalization → Section Parsing is shared across domains and only
IR extraction branches. ADR-0002 encoded that by keeping `Clause` domain-neutral and putting
`domain_profile` on `IR` alone. This ADR defines what that branch actually contains — and states
what would prove the claim false.

IR is also the product's load-bearing abstraction: gap analysis maps IRs to controls, Q&A answers
cite the clauses IRs point at, and change alerts are graded by which IRs an amendment touches. An
imprecise IR definition degrades all three at once.

## Decisions

### 1. Atomicity is a written rule, not a judgement call

"One atomic regulatory obligation" is unusable as stated — two reviewers reading the same clause
will produce different IR counts, and every downstream count (coverage, gap, impact) becomes
non-comparable between people and between extraction runs.

An IR is **one obligation = one bearer + one modal + one required action**, with conditions attached
rather than split out:

| Input | Yields |
|---|---|
| One clause, three `해야 한다` obligations | **3 IRs**, each citing the same clause |
| One obligation whose conditions span 조 + 부칙 | **1 IR** citing both |
| A definition, scope statement, or heading | **0 IRs** — see decision 6 |
| "A 하여야 하며, B 하여야 한다" | **2 IRs** — conjunction of obligations, not one compound |

Modal inventory is per-language and fixed at W3-4: KO `하여야 한다 / 해야 한다 / -도록 한다 /
금지한다 / 아니 된다`; EN `shall / must / is required to / may not`. Permissive forms (`할 수 있다`,
`may`) are **not** obligations and yield no IR — they are recorded as context on a related IR where
one exists.

### 2. An IR without a citation does not exist

Extraction that cannot attach at least one `(document_version_id, clause_path)` is **rejected, not
stored with a null citation**. There is no draft state for an uncited IR.

This is the same invariant as "no answer without evidence," applied one layer earlier — an uncited
IR would launder an unsourced claim into gap analysis, where it would look like a finding.

### 3. The branch is a rule set, not a code path

`domain_profile` selects an **extraction rule set** — modal inventory, obligation taxonomy, and
prompt — and nothing else. Same tables, same pipeline stages, same lifecycle, same storage.

What legitimately differs between SaMD and Cosmetic:

| | `samd` | `cosmetic` |
|---|---|---|
| Typical obligation shape | process/lifecycle duties (documentation, verification, change control) | substance/labelling duties (concentration limits, prohibited ingredients, claim restrictions) |
| Taxonomy | design control · risk · V&V · postmarket | ingredient · labelling · claims · GMP · notification |
| Tabular annexes | present but sparse (의료기기 기준규격: ~3% table lines) | **table-dense** (화장품 안전기준 별표 1·2: 35–43% table lines) — ingredient tables carry obligations in rows |

**Falsification criterion.** If Cosmetic extraction requires a domain-specific column on `Clause`, a
second pre-IR pipeline stage, or a separate parser before Section Extraction, the shared-pipeline
claim in ADR-0002 decision 3 has failed. Escalate at the W5-6 cross-domain check rather than adding
the column — Phase 2 plans six more cells on this assumption.

The likeliest breaker is the tabular-annex row above: an ingredient limit table is an obligation
carrier whose natural unit is a *row*, not a prose clause. If that cannot be represented as clauses
with `path_segments`, it is a genuine finding, not a workaround to code around quietly.

> **Tested against the live API on 2026-07-29 — the falsifier did NOT trigger.** See the
> [reconnaissance memo](spike-2026-07-29-mfds-source-recon.md) § live API test.
>
> 행정규칙 본문조회 returns `<별표단위>` with **`<별표내용>` inline** — annex text arrives through the
> same call as the body, so no HWP/PDF path is required for ingestion. The tables are
> **fixed-width box-drawing text** (`┌ ├ │ ┬ ┼` at consistent offsets), not structured rows: 별표 2
> of 화장품 안전기준 규정 carries 원료명 / **사용한도** / 비고 / CAS No. as text columns.
>
> **Why the bet survives:** the same box-drawing annexes appear on the SaMD side (의료기기 기준규격,
> 311 box-drawing lines) and 별표 3 of the *cosmetic* 고시 is 0% table — pure prose. So the parsing
> split is **prose vs. table, a content type present in both domains** — not SaMD vs. Cosmetic.
> Section Extraction needs a table-mode strategy alongside the 조/항/호/목 hierarchy mode, and both
> domains use both. No domain-specific column on `Clause`, no pre-IR stage, no domain-forked parser.
> That is a shared pipeline with two content strategies, which is what decision 3 claims.
>
> **Re-run against real ingestion on 2026-08-06 — still NOT triggered.** The spike tested one API
> response; this ran the built pipeline over the whole archived corpus (293 documents, 10,036
> clauses). Both cells use the same three profiles, selected by document shape — `law_structured`
> for 법령, `admrul_text` for 고시, `annex` for 별표/서식/별지 — with no domain-conditional code, no
> domain-specific column on `Clause`, and no second pre-IR stage. A limit-table row round-trips as
> `별표2/표1/행1` and answers an exact-match 원료명 lookup. Detail in
> [phase1.1](../plan/phase1.1_normalization.md) § Falsifiers.
>
> One thing the spike did **not** predict: 고시 bodies carry no clause structure at all, so a third
> profile was needed to segment them out of flat text. That is a 법령-vs-고시 split — a source shape
> both gated cells have — not a domain fork, so decision 3 survives it.

### 4. The LLM proposes; a human locks; only locked IRs flow

Extraction is LLM-assisted and produces `status = draft`. An RA reviews and locks. **Only `locked`
IRs are visible to gap analysis, answer generation, and impact grading** — draft IRs are inert.

Every IR records `llm_provider`, `llm_model`, `prompt_version`, `rule_version` and the
`extraction_run` that produced it (`.claude/skills/service-endpoint` § LLM seam). Locking records
the signer and timestamp.

This is the Part 11 story as much as a quality story: a regulatory obligation asserted by a model
and never reviewed is exactly the artefact an auditor will ask about first.

### 5. Amendments re-derive into a new IR version; they never mutate in place

*(Resolves ADR-0002 open question 2.)*

When a `ClauseDiff` touches a clause an IR cites, the IR is marked `stale` and re-extracted. The
result is a **new IR** with `supersedes` pointing at the old one. The old IR is retained, frozen.

Mutating a locked IR in place would silently change the meaning of every control mapping and every
answer that already referenced it, while the audit trail still showed a single approved record. Cost
of the chosen route: control mappings must be carried forward explicitly. The carry-forward is
proposed automatically and **confirmed by RA** — an amendment that narrows an obligation may
invalidate the mapping that satisfied it, and that is precisely the gap the product exists to find.

### 6. Non-obligation clauses are marked reviewed, not skipped

Definitions, scope statements and headings produce no IR. If they are simply absent, "50 IRs from
200 clauses" is uninterpretable — it cannot be distinguished from 150 missed obligations.

Every clause is therefore classified: `obligation_bearing` or `excluded` with a reason. Coverage is
then provable — *this clause was examined and deliberately yielded nothing* — rather than assumed.
Gap analysis completeness claims rest on this.

### 7. Quality is measured per domain, against a golden set

Precision (extracted IRs that are genuine obligations), recall (genuine obligations that were
extracted), and citation correctness, scored **separately for SaMD and Cosmetic** — a shared score
would hide one domain failing behind the other passing.

Recall requires a hand-built ground truth: RA marks up a sample of 화장품법 and 의료기기법 clauses
independently of the extractor. That markup is a Phase 1 deliverable, not a nice-to-have — without
it, recall is unmeasurable and the gap analysis pillar has no evidence base.

## Schema additions

```sql
irs(id, domain_profile, bearer, modal, statement, condition_text,
    taxonomy_code, status, supersedes_ir_id, stale_since,
    extraction_run_id, locked_by, locked_at)
extraction_runs(id, rule_version, prompt_version, llm_provider, llm_model, started_at)
clause_classifications(clause_id, kind, exclusion_reason, classified_by, classified_at)
ir_citations(ir_id, document_version_id, clause_path, effective_date, superseded_at)  -- ADR-0002
```

`status ∈ draft | locked | stale | superseded`.

## Open questions

1. ~~**Tabular annex representation**~~ — **resolved** by the live API test (2026-07-29). Annex text
   is inline in `<별표내용>`; the parsing split is prose vs. table, and both content types occur in
   both domains, so decision 3 stands. What remains is *implementation*, not an open architectural
   question: a fixed-width box-drawing table parser keyed on `│` column offsets, emitting one
   `Clause` per row with `path_segments = [별표N, row]`. Mechanical and deterministic — no LLM in the
   parsing path.
2. ~~**Annex scale vs. clause granularity**~~ — **closed by
   [ADR-0014](ADR-0014-annex-row-granularity.md).** The "tens of thousands of rows" estimate counted
   *physical lines*; a logical row wraps across several of them. Measured over the whole gated
   corpus: **1,999 data rows**, 1,937 of them in 별표-kind annexes. One `Clause` per row is one
   ordinary table with an index, so rows live in `clauses` and no separate store is created.
   Embedding is unaffected — decisions 1–2 of
   [ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md) still exclude rows from the
   index and serve them by exact match.
3. ~~**Conditional obligations by product class**~~ — **closed by
   [ADR-0017](ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 2.** One
   parameterised IR, with the restriction in `condition_text`. Not because it is smaller: *which*
   products a duty binds is Compliance-owned and tenant-scoped (ADR-0007, phase 2.2), and fanning
   out per class here would have the shared reference layer making an applicability decision on
   every tenant's behalf.
4. ~~**Cross-references**~~ (`제5조에 따른`, "as specified in Annex III") — **resolved** in
   [ADR-0010](ADR-0010-semantic-enrichment-and-graph-model.md) decision 7: neither option exactly.
   The clause text is retained verbatim and the resolution is stored beside it in
   `clause_references`, produced by a deterministic pipeline rather than at extraction time — so
   this ADR's W3-4 scope is unchanged. Staleness propagation via the referring clause is confirmed
   correct and becomes the mechanism behind impact grading.
5. ~~**Extraction determinism**~~ — **closed by
   [ADR-0017](ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 1.**
   Temperature is pinned to 0, stored on `extraction_runs`, and a delta at the same
   `(rule_version, prompt_version, llm_model)` is treated as a regression. Greedy decoding is not
   determinism, so it is a measured target rather than a guarantee — which is why the value used is
   stored rather than assumed.

## What this unblocks

W3-4 IR extraction rules and the clause schema. Next: retrieval and citation-enforced generation,
then service decomposition and the RBAC role set that `.claude/skills/service-endpoint` currently
defers.
