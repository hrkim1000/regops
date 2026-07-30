# Phase 1.6 — Evaluation & pilot

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W7–W16 · **Status:** ⬜ planned
- **Governed by:** [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 7, [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md), [development-plan.md](../development-plan.md) § 5
- **Depends on:** all of 1.0–1.5
- **Owner:** Regulatory domain (RA/QA), with AI/ML for the harness

---

## Goal

Produce the numbers. **The purpose of the PoC is measurement, not a demo** — No-Go is called if four
or more of the six gates fall short. This phase exists to make that judgement defensible rather than
arguable.

Sequencing is the whole game here: two exercises are only valid if they happen **before** the thing
they measure.

## Scope

**In:** golden query sets, IR ground-truth markup, evaluation harness, pilot operation, the M4
Go/No-Go report.

**Out:** fixing what the measurements reveal — that is the Phase 2 backlog.

## Tasks

### Golden query set (W2 → W8)

- [ ] 200 items, built per domain — **SaMD and Cosmetic scored separately.** A shared score hides one domain failing behind the other passing
- [ ] Composition must include identifier lookups, paraphrased conceptual queries, and cross-domain questions. A set of only identifier lookups measures the easy half
- [ ] Include known-unanswerable questions — the "needs verification" path is a correct outcome and must be scored as one
- [ ] Authored by RA, with expected clause and expected answer recorded

### IR ground-truth markup (W7–8) — sequencing is load-bearing

- [ ] RA hand-marks obligations in a sample of 화장품법 and 의료기기법 clauses
- [ ] **Blind to extractor output.** Marking up after seeing extractor results inflates recall and produces a number that cannot be defended
- [ ] Runs in parallel with [phase1.2](phase1.2_ir_extraction.md) work, delivered before W9–10 scoring
- [ ] Without it, extraction **recall** is unmeasurable and the gap-analysis pillar has no evidence base

### Harness (W9–10)

- [ ] Automated regression over both golden sets; per-domain, per-cell reporting
- [ ] Extraction precision, recall, and citation correctness against the ground truth
- [ ] Citation accuracy and hallucination rate measured here — **not inferred from unit coverage**
- [ ] Model and prompt versions pinned and recorded with every run

### Pilot (W11–16)

- [ ] Freeze build at W11–12; onboard 20–30 users in one business unit; capture baseline
- [ ] **Four consecutive weeks of real usage — the retention gate cannot be compressed**
- [ ] Blind accuracy assessment by RA staff against both golden sets
- [ ] Research-time-savings measurement against the existing manual process for matched query types

### EU spike close-out (W12)

- [ ] Findings memo: multilingual normalization and Tier C effort estimate for Phase 2
- [ ] Does not count toward exit criteria

### Go/No-Go report (W16)

- [ ] Per-cell measurement against all six gates
- [ ] Deviations log consolidated from every phase file
- [ ] Phase 2 backlog and re-plan recommendation

## The six gates — measured per gated cell

| Gate | Threshold | Method |
|---|---|---|
| Detection coverage | ≥ 95% | Share of actual amendments captured, verified by after-the-fact manual comparison |
| Detection latency | ≤ 24h | Authority publication → owner alert |
| Citation accuracy | ≥ 90% | Share of cited clauses that actually support the answer, blind RA assessment |
| Hallucination rate | ≤ 2% | Outputs citing non-existent clauses or contradicting source text |
| Research time savings | ≥ 30% | Versus the manual process for the same query type |
| Pilot retention | ≥ 60% | Voluntary use ≥ 1×/week for 4 consecutive weeks |

**A cell that misses is not offset by the other passing.** No-Go if four or more fall short.

## Acceptance criteria

- [ ] Both golden sets complete and RA-signed before W9
- [ ] Ground-truth markup demonstrably blind — authored before extractor output was shown, with dates to prove it
- [ ] Harness reproduces a scored run from pinned model + prompt versions
- [ ] All six gates measured per cell with stated method, not estimated
- [ ] Go/No-Go report delivered at W16 with evidence attached

## Risks & open questions

- **Risk 7 — key-person dependency (development-plan.md § 9).** One RA is simultaneously golden-set designer, ground-truth marker, blind assessor, IR locker, and final signoff. That overlap makes both "blind" exercises non-blind in practice. At 1 FTE this risk is **accepted, not mitigated** — state it at kickoff rather than discovering it at M4. Budget a second RA reviewer, even part-time, to separate authorship from assessment.
- **Retention needs 4 uncompressible weeks.** Any slip upstream eats the measurement window, not the build. Protect W13–16.
- **Research-time-savings needs a baseline** captured before the pilot starts, or the 30% is unfalsifiable.

## Deviations & decisions

_None yet._
