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

## Phase map

| Phase | File | Roadmap | Weeks | Status |
|---|---|---|---|---|
| 0 | [phase0_foundation.md](phase0_foundation.md) | pre-M1 | W0–W2 | 🟢 done (4 items deferred to 1.5 / CI) |
| 1.0 | [phase1.0_ingestion.md](phase1.0_ingestion.md) | Phase 1 · M0–4 | W1–W4 | 🟢 done (2026-08-05) — 8/8 acceptance, W3 recon complete |
| 1.1 | [phase1.1_normalization.md](phase1.1_normalization.md) | Phase 1 | W3–W6 | ⬜ planned |
| 1.2 | [phase1.2_ir_extraction.md](phase1.2_ir_extraction.md) | Phase 1 | W3–W8 | ⬜ planned |
| 1.3 | [phase1.3_retrieval_qa.md](phase1.3_retrieval_qa.md) | Phase 1 | W5–W10 | ⬜ planned |
| 1.4 | [phase1.4_monitoring.md](phase1.4_monitoring.md) | Phase 1 | W7–W10 | ⬜ planned |
| 1.5 | [phase1.5_frontend.md](phase1.5_frontend.md) | Phase 1 | W7–W12 | 🟡 foundation + regulation browser built early |
| 1.6 | [phase1.6_evaluation.md](phase1.6_evaluation.md) | Phase 1 | W2–W16 | ⬜ planned |
| 2.0 | [phase2.0_tier_c_scale.md](phase2.0_tier_c_scale.md) | Phase 2 · M5–12 | — | ⬜ planned |
| 2.1 | [phase2.1_semantic_graph.md](phase2.1_semantic_graph.md) | Phase 2 | — | ⬜ planned |
| 2.2 | [phase2.2_compliance.md](phase2.2_compliance.md) | Phase 2 | — | ⬜ planned |
| 3.0 | [phase3.0_saas.md](phase3.0_saas.md) | Phase 3 · M13–24 | — | ⬜ planned |

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

Two checks are falsifiers, not milestones — if either fails, escalate rather than working around it:

| Check | Phase | What it falsifies |
|---|---|---|
| Annex row → `Clause` with `path_segments` (W3–4) | 1.1 | ADR-0004 decision 3 — the shared-pipeline claim |
| Cross-domain: Cosmetic parses without forking Normalization (W5–6) | 1.1 | ADR-0002 decision 3 — Phase 2's six-cell build rests on it |

## Decisions due, with the window that closes them

A decision left unmade is taken by whatever gets built first. These have deadlines, not owners' preferences:

| Decision | Due | Closes because |
|---|---|---|
| Four services, or fold `monitoring` into `regulation`? ([brief](../design/decision-2026-08-05-lapsed-service-boundaries.md)) | **lapsed — confirm by W7** | 1.4 starts at W7; after that the reversal is no longer three tables and one seam |
| Do `regulation` and `assistant` stay split? ([brief](../design/decision-2026-08-05-lapsed-service-boundaries.md)) | **lapsed — confirm by W5** | 1.3 builds `assistant` from W5; separating later means moving the embedding tables |
| Annex storage — does `annex_rows` exist, and who owns it? (ADR-0006 open question 3) | **W4** | 1.3's retrieval index is built on it at W5–6. [ADR-0012](../design/ADR-0012-annex-version-identity.md) settled the *container* (an annex is a child Document); the row granularity inside it is still open |
| ~~Unresolvable effective dates~~ | **taken** | [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) — null plus the retained raw 부칙 phrase |
| Diff inline, or split as its own stage? (ADR-0003 open question 4) | **W3–4** | It is a stage boundary in the 1.1 pipeline |

The first two were scoped as W1 decisions; phase 0 and phase 1.0 both closed without taking them.
A [decision brief](../design/decision-2026-08-05-lapsed-service-boundaries.md) sets out the cost
curve for each so they can be taken rather than deferred a third time — the W5 one now falls inside
[phase1.1](phase1.1_normalization.md)'s own window.

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
| [design/](../design/) | ADR-0001 – ADR-0010; a plan file cites them, never contradicts them |
