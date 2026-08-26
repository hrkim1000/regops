# RegOps Phase Plan

Build plans, one file per phase. Each decomposes the roadmap in
[development-plan.md](../development-plan.md) into checkable tasks with acceptance criteria — it
does **not** restate the roadmap, the metrics, or the source catalog.

## Numbering

**The integer part is the roadmap phase.** `phase1.3` is the fourth build slice of roadmap Phase 1
(months 0–4). "Phase 2" therefore means months 5–12 everywhere in this repository — in RegOps.md, in
development-plan.md, in every ADR, and here. There is no second numbering scheme.

`phase0` is the exception: it precedes M1 and appears in no roadmap document, because RegOps.md
starts at the first connector and assumes a stack already exists. It does not.

**A letter suffix is a slice of the slice above it** — `phase2.0a` is part of `phase2.0`, not a
phase between 2.0 and 2.1. It exists so that a slice can be decomposed after the fact without
renumbering everything after it: 2.1 and 2.2 are cited from ADRs and from the root README, and
shifting them to make room would break links to buy nothing.

## Phase map

| Phase | File | Roadmap | Weeks | Status |
|---|---|---|---|---|
| 0 | [phase0_foundation.md](phase0_foundation.md) | pre-M1 | W0–W2 | 🟢 done — the 4 deferred items all closed in 1.5 |
| 1.0 | [phase1.0_ingestion.md](phase1.0_ingestion.md) | Phase 1 · M0–4 | W1–W4 | 🟢 done (2026-08-05) — 8/8 acceptance, W3 recon complete |
| 1.1 | [phase1.1_normalization.md](phase1.1_normalization.md) | Phase 1 | W3–W6 | 🟢 done (2026-08-06) — 9/9 acceptance, both falsifiers not triggered |
| 1.2 | [phase1.2_ir_extraction.md](phase1.2_ir_extraction.md) | Phase 1 | W3–W8 | 🟢 done (2026-08-07) — 7/7 acceptance |
| 1.3 | [phase1.3_retrieval_qa.md](phase1.3_retrieval_qa.md) | Phase 1 | W5–W10 | 🟢 done (2026-08-11) — 9/9 acceptance |
| 1.4 | [phase1.4_monitoring.md](phase1.4_monitoring.md) | Phase 1 | W7–W10 | 🟢 done (2026-08-11) — 6/6 acceptance, 100% detection coverage on both gated cells |
| 1.5 | [phase1.5_frontend.md](phase1.5_frontend.md) | Phase 1 | W7–W12 | 🟢 done (2026-08-14) — regulation browser · clause view · IR review + lock · 제출 서류 · Q&A workbench · monitoring dashboard · **Playwright E2E, 10 tests green against the live stack and the real model**; the usability review is **미측정** (needs pilot users) |
| 1.6 | [phase1.6_evaluation.md](phase1.6_evaluation.md) | Phase 1 | W2–W16 | 🟡 harness + golden sets built (2026-08-13); **reviewer packet + pilot runbook written (2026-08-14)** and a second reviewer available — so the human and pilot halves are prepared to the start line but not run. 4 of 6 gates still **미측정**; report recommends `INCOMPLETE` |
| 2.0 | [phase2.0_tier_c_scale.md](phase2.0_tier_c_scale.md) | Phase 2 · M5–12 | — | ⬜ planned — **umbrella**: keeps Tier C and multilingual; adds **four** cells via 2.0a (FDA) and 2.0c (NMPA). ~~2.0b (EU)~~ moved to Phase 4, 2026-08-24 (deviations 1–2) |
| 2.0a | [phase2.0a_fda.md](phase2.0a_fda.md) | Phase 2 · M5–12 | — | 🟡 **48/61 — the build is largely done; the gates are not** (2026-08-26). Three connectors live (`ecfr_part`, `federal_register`, `govinfo_uscode`), two new parser profiles (`cfr_structured`, `usc_text`), English extraction and retrieval, the first real `document_cells` M:N, and FDA golden sets seeded on the three generated axes. **4 of 9 acceptance criteria met** — the structural ones; the four per-cell trust gates need signed golden sets and Phase 1 Go. Decided here: [ADR-0018](../design/ADR-0018-fda-source-model.md), [ADR-0019](../design/ADR-0019-announced-amendments.md), [ADR-0020](../design/ADR-0020-ir-rejection.md). Blocked on people (an FDA-side `ra`) and on FDA (`fda.gov` refuses our agent, so the Guidance block and Tier D freshness are out) |
| 2.1 | [phase2.1_semantic_graph.md](phase2.1_semantic_graph.md) | Phase 2 | — | ⬜ planned |
| 2.2 | [phase2.2_compliance.md](phase2.2_compliance.md) | Phase 2 | — | ⬜ planned |
| 3.0 | [phase3.0_saas.md](phase3.0_saas.md) | Phase 3 · M13–24 | — | ⬜ planned |
| 4.0 | file written when the slice starts | Phase 4 · after M24 | — | ⬜ planned — `eu_samd` + `eu_cosmetic`, **moved here from 2.0b on 2026-08-24**. Completes the 8-cell matrix; carries `version_group_id` and ELI keys |

Legend: 🟢 done · 🟡 in progress / partial · ⬜ planned · 🔴 blocked

Week ranges overlap because the slices run in parallel — see the critical path below.

## Critical path

```text
source map ─→ parser profiles ─→ clause schema ─→ IR extraction rules
                                      │
                                      └─→ retrieval index ─→ citation-enforced generation
```

Everything downstream of **clause schema** slips one-for-one with it. The monitoring dashboard and
alert routing (1.4) and the frontend (1.5) are the only branches that can absorb slack.

Two checks are falsifiers, not milestones — if either fails, escalate rather than working around it.
**Both were run on 2026-08-06 against the whole ingested corpus (526 documents, 25,729 clauses) and
neither triggered** — see [phase1.1](phase1.1_normalization.md) § Falsifiers:

| Check | Phase | What it falsifies | Result |
|---|---|---|---|
| Annex row → `Clause` with `path_segments` (W3–4) | 1.1 | ADR-0004 decision 3 — the shared-pipeline claim | 🟢 not triggered |
| Cross-domain: Cosmetic parses without forking Normalization (W5–6) | 1.1 | ADR-0002 decision 3 — Phase 2's four-cell build rests on it (EU is Phase 4) | 🟢 not triggered |

## Decisions due, with the window that closes them

A decision left unmade is taken by whatever gets built first. These have deadlines, not owners' preferences:

### Closed — Phase 1

| Decision | Due | Closes because |
|---|---|---|
| ~~Four services, or fold `monitoring` into `regulation`?~~ | **taken 2026-08-11** | **Four — `monitoring` stays its own service.** [ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) open question 2; reasoning in the [brief](../design/decision-2026-08-05-lapsed-service-boundaries.md). Taken at the W7 deadline, before [phase1.4](phase1.4_monitoring.md) built into the boundary |
| ~~Do `regulation` and `assistant` stay split?~~ | **taken 2026-08-05** | **Yes — split retained.** [ADR-0005](../design/ADR-0005-service-architecture.md) open question 1; reasoning in the [brief](../design/decision-2026-08-05-lapsed-service-boundaries.md) |
| ~~Annex storage — does `annex_rows` exist, and who owns it?~~ | **taken 2026-08-06** | **No `annex_rows`.** [ADR-0014](../design/ADR-0014-annex-row-granularity.md) — an annex table row is a `Clause`, columns typed per table in `jsonb`. Closes ADR-0006 open question 3 and ADR-0004 open question 2 |
| ~~Unresolvable effective dates~~ | **taken** | [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) — null plus the retained raw 부칙 phrase |
| ~~Diff inline, or split as its own stage?~~ | **taken 2026-08-06** | **Split.** [ADR-0015](../design/ADR-0015-diff-stage-boundary.md) — its own task, dispatched by name, so a profile improvement re-diffs the archive without re-fetching. Closes ADR-0003 open question 4 |
| ~~How are 시행예정 versions keyed, and where do staged dates live?~~ | **taken 2026-08-06** | **One version per MST; staged dates stay in `effective_date_phrase`.** [ADR-0016](../design/ADR-0016-pending-effect-versions.md) — and it partly withdraws ADR-0003 open question 2, because `조문시행일자` is constant per document |
| ~~Class-restricted obligation: one parameterised IR, or one per class?~~ | **taken 2026-08-07** | **One parameterised IR**, restriction in `condition_text`. [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 2 — applicability is Compliance-owned and tenant-scoped, so per-class fan-out would decide it for every tenant in the shared layer. Closes ADR-0004 open question 3 |
| ~~Extraction determinism: pin temperature, or gate on the golden set only?~~ | **taken 2026-08-07** | **Pin to 0, store it on the run, treat a delta as a regression.** [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 1. Closes ADR-0004 open question 5 |
| ~~FDA: what is a `Document`, which surface owns versions, and is guidance extracted?~~ | **taken 2026-08-24** | **A `Document` is a CFR Part; the eCFR owns identity and the version spine; guidance is stored, citable and never extracted.** [ADR-0018](../design/ADR-0018-fda-source-model.md), on live probes in [spike-2026-08-24](../design/spike-2026-08-24-fda-source-recon.md). Closes ADR-0002 open question 3 for `authority = fda` and all three ADRs [phase2.0a](phase2.0a_fda.md) required before its build. **Retires that slice's Risk 1** — the eCFR publishes its own section-level change history, so the latency gate does not depend on reconciling two surfaces |

The two **service-boundary** decisions at the top of that table were scoped as W1 decisions and
lapsed twice in silence. The
[decision brief](../design/decision-2026-08-05-lapsed-service-boundaries.md) set out the cost curve
for each; on 2026-08-05 the first was **taken** (split retained) and the second **held to W7 on
purpose** — a recorded choice to wait, which is not the same as another lapse. **Both are now
taken:** the hold ran to its date and closed on 2026-08-11 with `monitoring` kept as its own
service, before [phase1.4](phase1.4_monitoring.md) wrote anything into the boundary. That timing was
the whole condition — once 1.4 builds subscription matching and delivery inside it, `monitoring`
stops being three tables and one seam, and the reversal stops being cheap whether or not anyone
noticed.

**Every Phase 1 decision is now closed.** A new one goes in with its deadline the moment it is
identified, not when it becomes urgent — that is what the two silent lapses cost. Which is why the
next five are already below, before anyone has started the slice they belong to.

### [phase2.0a](phase2.0a_fda.md), the FDA cells — five closed 2026-08-24, one open

| Decision | Due | Closes because |
|---|---|---|
| **Who is the FDA-side `ra`?** | **before the first IR is locked or a golden set signed** | The last *Prerequisite* standing, and the only one that needs a person rather than a sentence. IR locking and golden-set sign-off need someone who reads 21 CFR; the second reviewer secured for [1.6](phase1.6_evaluation.md) has a packet but the MFDS sets are still unsigned, so this adds two cells to a queue that has not drained. **Not blocking W0 or the connectors** — blocking the point where a human assertion enters the audit trail |
| ~~Does 2.0a start before Phase 1 Go is called?~~ | **taken 2026-08-24** | **Yes — the dependency is amended, not waived.** A Phase 2 slice may *start* on the machine-measurable half; **Phase 1 Go is still required before any Phase 2 cell is declared gated.** The four `미측정` gates need a person or a pilot, not engineering, so blocking the build on them would idle it without making one gate measurable sooner. Amended text and reason in the [2.0 header](phase2.0_tier_c_scale.md); the boundary in [2.0a](phase2.0a_fda.md) *Deviations* 4 |
| ~~EU SaMD spike — run it, or drop it~~ | **taken 2026-08-24** | **Neither — the whole EU group moved to Phase 4.** The spike goes with it, never run: its purpose was to meet a second authority cheaply before one was gated, and the FDA reconnaissance spent that purpose. `eu_samd` + `eu_cosmetic` leave 2.0b for a new Phase 4 after M24 ([RegOps.md](../RegOps.md) § Roadmap). **Scope is still 8 cells; only the timing changed.** Cost: 2.0c (NMPA) becomes the first multilingual exercise *and* full-weight Tier C *and* a curated `canonical_key` — the concentration the 2.0a/b/c decomposition was written to avoid; see [2.0](phase2.0_tier_c_scale.md) *Deviations* 2 |
| ~~FDA `canonical_key`~~ | **taken 2026-08-24** | **A `Document` is a CFR Part; the key is the citation the eCFR already publishes.** [ADR-0018](../design/ADR-0018-fda-source-model.md) decisions 1–3. Closes [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) open question 3 for `authority = fda` |
| ~~eCFR and Federal Register — one Document or two?~~ | **taken 2026-08-24** | **One.** The eCFR owns identity and the version spine; a Federal Register rule is provenance on the version. [ADR-0018](../design/ADR-0018-fda-source-model.md) decisions 4–8. The premise that the two gates read different surfaces was measured and is **wrong** — the eCFR publishes its own section-level change history |
| ~~Is FDA guidance extracted, or citable-only?~~ | **taken 2026-08-24** | **Citable-only, excluded at `doc_type` level** with a new `ExclusionReason.NON_BINDING`, and the coverage denominator is defined over obligation-bearing `doc_type`s so it cannot read as a hole. [ADR-0018](../design/ADR-0018-fda-source-model.md) decisions 9–10 |

## Working with these files

- **After completing each step, update the corresponding phase file.** Mark items `[x]`.
- Record deviations and decisions in the file's *Deviations & decisions* section — that log is what
  makes a Go/No-Go report writable at M4.
- A decision that changes architecture goes in an **ADR**, not a plan file. Link it from here.
- Keep the Status column above in sync; it is mirrored in the root [README.md](../../README.md).

## Governing documents

| Document | Role |
|---|---|
| [development-plan.md](../development-plan.md) | The roadmap these files decompose — milestones, exit criteria, staffing, risk register |
| [RegOps.md](../RegOps.md) | Scope, data tiers, five layers, Go/No-Go gate definitions |
| [import-source-map.md](../import-source-map.md) | The single source catalog — never copied into a plan file |
| [design/](../design/) | ADR-0001 – ADR-0019; a plan file cites them, never contradicts them |
