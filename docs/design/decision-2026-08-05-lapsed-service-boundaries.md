# Decision brief — the two lapsed service-boundary decisions

- **Date:** 2026-08-05
- **Status:** **Decision 1 taken 2026-08-05** (split retained → [ADR-0005](ADR-0005-service-architecture.md)
  open question 1). **Decision 2 held, deliberately, until W7.**
- **Owner:** whoever owns the plan. Not the implementer.
- **Why now:** both were scoped as **W1** decisions. Phase 0 closed without taking them, phase 1.0
  closed without taking them, and [phase1.1](../plan/phase1.1_normalization.md) runs W3–W6 — so the
  first of the two now falls *inside* the current phase.

---

## Why this is a brief and not an ADR

An unmade decision is not the same as a made one, but it does not stay neutral either: **it is
taken by whatever gets built first.** Both of these have already drifted that way once — phase 0
scaffolded four services, which made "open with four" the de facto answer without anyone choosing
it.

The cost of reversing each is not constant. It rises at a known date, for a known reason. That is
what makes these deadlines rather than preferences, and it is the only part of this document that
actually matters.

---

## Decision 1 — do `regulation` and `assistant` stay split? · **TAKEN: yes**

**Source:** [ADR-0005](ADR-0005-service-architecture.md) open question 1 · **Due: W5** ·
**Decided 2026-08-05: they stay split.** Recorded in ADR-0005 open question 1; nothing below is
outstanding. Kept here for the reasoning, not as a pending item.

[phase1.3](../plan/phase1.3_retrieval_qa.md) builds `assistant` from W5. It owns
`clause_embeddings`, `queries`, `answers`, `answer_citations`, `verification_results`.

| When | Cost of merging them |
|---|---|
| **now** | change one table-ownership list; no data exists |
| after W5 | move the embedding tables between services, rewrite `assistant`'s reads of `clauses` as raw SQL, re-run the index build |
| after the pilot | as above, plus a migration against data the pilot is using |

**What pulls them apart.** Retrieval and generation fail differently from ingestion: a hung LLM
call must not stall the fetch scheduler, and the two scale on different axes. ADR-0005 leans split
for that reason.

**What pulls them together.** `assistant` reads `clauses` constantly, and every cross-service read
is raw SQL by rule — no ORM model may cross the boundary. At 6.5 FTE, a fourth deployment unit that
mostly reads one other service's tables is a real operating cost
([ADR-0009](ADR-0009-service-boundaries-per-pillar.md) names four Phase 1 units as the expensive
part of the design).

**Recommendation: keep them split, and record it.** The failure-isolation argument is the stronger
one, embeddings are genuinely `assistant`-owned state, and the reversal is cheapest *before* W5 in
either direction — but only if someone actually decides. Confirming costs nothing today; discovering
at W9 that nobody chose costs the index build.

---

## Decision 2 — four services, or fold `monitoring` into `regulation`? · **HELD to W7**

**Source:** [phase0](../plan/phase0_foundation.md) risks ·
[ADR-0009](ADR-0009-service-boundaries-per-pillar.md) · **Due: W7** ·
**Held 2026-08-05, deliberately.**

This is not a third lapse, and the difference is worth stating because it is the whole point of
writing the brief. The first two deferrals were silent — nobody chose, and the scaffold chose for
them. This one is a recorded decision to wait, with a date on it and a named reason: `monitoring`
is still a health-check-only scaffold, so no evidence has arrived that would change the answer, and
the reversal stays at three tables and one seam until [phase1.4](../plan/phase1.4_monitoring.md)
begins.

**What makes the hold safe, and what would void it.** It is safe only while nothing is built into
the boundary. The moment 1.4 writes subscription matching, impact grading or delivery inside
`monitoring`, the cheap reversal is gone whether or not anyone noticed. So: **W7 is not a reminder,
it is the last moment the hold is free.** If 1.4 is pulled forward, the decision moves with it.

`monitoring` owns three tables — `alert_subscriptions`, `alerts`, `alert_deliveries` — and reads
`change_events` one-way by raw SQL. Today it is a health-check-only scaffold.

| When | Cost of folding it in |
|---|---|
| **now** | three tables and one seam. ADR-0009 calls this the cheapest reversal in the design |
| after W7 | [phase1.4](../plan/phase1.4_monitoring.md) has built subscription matching, impact grading and delivery inside it |
| after the pilot | alert history exists and users depend on it |

**What pulls them apart.** The seam is clean and one-directional: everything that *writes* the
clause store is `regulation`; `monitoring` begins where writing ends. That is a genuine ownership
boundary, not a pipeline stage — which is exactly the test CLAUDE.md sets.

**What pulls them together.** Four services at 6.5 FTE is the cost ADR-0009 itself flags. Nothing
in `monitoring` needs independent scaling in Phase 1, and its only upstream dependency is a table
`regulation` writes.

**Recommendation: keep four, and record it** — but treat W7 as real. The seam is already built and
respected in phase 1.0 (`change_events` is written by `regulation` and read nowhere else), so the
split is currently free. What is *not* free is arriving at W8 having never decided, which is the
outcome the phase 0 risk entry explicitly warned about and which has now happened twice.

---

## What "taking the decision" requires

Not a discussion — a recorded outcome. For each:

1. Choose, with one sentence of reasoning.
2. Record it as an ADR amendment (both live in ADR-0005 / ADR-0009).
3. Update the *Decisions due* table in [plan/README](../plan/README.md) from "lapsed" to "taken",
   linking the ADR.
4. If the answer is "merge", do it **before** the phase that builds into the boundary — W5 for
   `assistant`, W7 for `monitoring`. A decision recorded but not executed is still the drift.

Either answer is defensible. Neither survives being left open a third time.
