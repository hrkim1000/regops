# ADR-0022 — Re-extraction drift is a measured rate, not a per-row defect

- **Status:** Accepted
- **Date:** 2026-09-09
- **Amends:** [ADR-0017](ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 1,
  second half — *"a difference is investigated as a defect rather than absorbed as variance"*
- **Confirms:** that same decision's own caveat — *"temperature 0 is greedy decoding, not
  determinism"* — and [ADR-0008](ADR-0008-service-composition.md), *"no agent output is terminal"*
- **Forced by:** an unintended second pass over the MFDS SaMD 별표 corpus on 2026-09-08, which
  produced 43 paired extractions at an identical fingerprint that nobody had scheduled

---

## Context

ADR-0017 decision 1 pinned sampling to 0, stamped it on `extraction_runs.temperature`, and said two
runs over the same clause at the same `(rule_version, prompt_version, llm_model)` are *expected* to
produce the same IRs, with any difference investigated as a defect. The same decision also said,
in as many words, that this is **a target with a known limit, not a guarantee** — batching,
quantization and GPU non-determinism can all move the output.

What was missing was the size of the limit. Without it, "investigate any difference" cannot be
priced: it is either a rare alarm worth chasing or a standing tax on every re-run, and which one it
is decides whether re-extraction can serve as a regression test at all.

The 별표 batch answered it by accident. Every one of the 53 targeted versions ran **twice** — once
from 15:54 to 19:32, then the identical sequence again — at rule version 1.5.0, prompt version
1.3.0, `gemma3:4b`, temperature 0, `domain_profile = samd` throughout, and neither pass a resume.
43 of those pairs completed cleanly on both passes. That is a controlled A/B that would have been
expensive to schedule deliberately.

### The measurement

| | |
| --- | --- |
| paired runs, identical fingerprint and profile | 43 |
| identical IR count on both passes | **37** |
| differing IR count | **6** |
| IRs, pass 1 → pass 2 | 248 → 255 |
| absolute churn (Σ&#124;Δ&#124; ÷ Σ pass 1) | **11.7%** |

The six that moved, and by how much:

```
admrul:97658#별표2      68 clauses    47 → 61   +14
admrul:41382#별표1      47 clauses    16 →  9    -7
admrul:38024#별표10    191 clauses    12 → 16    +4
admrul:37100#별표2      46 clauses    23 → 21    -2
admrul:92599#별표1      19 clauses    10 →  9    -1
law:009740#별표2        51 clauses    19 → 18    -1
```

Drift runs in both directions and does not scale with document size — the largest swing is on a
68-clause annex, while the 191-clause one moved by 4.

**The evidence is counts, not content.** The second pass cleared the first pass's drafts, as
designed, so no text-level comparison is possible after the fact. Two runs can agree on the number
and disagree on the rows, which makes **37 an upper bound on agreement and 6 a lower bound on
drift**. Every figure above is the optimistic end of its range.

### Why the old rule cannot stand as written

At roughly one document in seven, "investigate the difference as a defect" prescribes an
investigation that terminates, every time, at a cause ADR-0017 had already named and accepted:
greedy decoding over a quantized 4B model is not bit-reproducible. A rule whose every invocation
ends at a known and accepted cause is not a rule — it is a backlog.

### What determinism was protecting, and which half still needs it

ADR-0017 gave two reasons, and they have not aged the same way.

- **Amendment churn** — *"re-derivation re-extracts a clause and supersedes the old IR; under
  sampled decoding that churns IRs whose obligation did not change."* This is now carried
  structurally rather than by determinism. `rederive_version` iterates
  `_stale_targets(session, version)` — the IRs whose cited clause the diff actually touched — so an
  amendment never re-extracts a clause it did not change. An unchanged obligation is not re-run, so
  it cannot drift.
- **The audit story** — *"an obligation asserted by a model is defensible if a reviewer can re-run
  the extraction and get the row back."* This is the half the measurement damages, and it should
  not have rested here to begin with. What makes a locked IR defensible is the citation it carries,
  the fingerprint stamped on its run, and the RA who locked it — ADR-0008's *"no agent output is
  terminal"*. Regenerating the row is evidence about the model, not about the obligation.

## Decisions

### 1. Temperature stays pinned at 0 and stamped on the run

Unchanged from ADR-0017. It costs nothing, it minimizes drift rather than eliminating it, and the
value belongs on the row rather than in a constant so that a run which sampled can be told apart
from one that did not.

### 2. A re-extraction delta is not, by itself, a defect

The expectation of row-for-row reproduction is withdrawn. A second pass at the same fingerprint that
returns a different IR set is a quantized model behaving as one, and it is recorded rather than
investigated.

### 3. What is a defect is a **change in the drift rate**, and any drift that reaches a locked IR

Two things replace the per-row rule, and they are the two that carry consequences.

- **Rate.** Drift is a property of a fingerprint and is measured as one, on a fixed sample, in the
  phase 1.6 harness alongside the golden-set score. 11.7% absolute churn over 43 별표 pairs is the
  first datum. A later fingerprint whose rate moves materially is a regression — a statement about
  the *change*, which is measurable, rather than about any single row, which is not.
- **Reach.** A locked IR is a human assertion in the audit trail. Drift that would rewrite one is a
  defect whatever the rate, and the existing rules already prevent it: a locked IR is never mutated
  in place ([ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) decision 5), and
  re-derivation supersedes rather than overwrites. Nothing new is needed; it is stated so that
  decision 2 is not read as licence for drift to reach review output.

### 4. Re-extracting a version already completed at the same fingerprint requires an explicit redo

`_resumable_run` deliberately treats a run after a `COMPLETED` one as *"a deliberate redo"* and
starts clean. That is right when a person asked for it. It is wrong when the second dispatch was a
duplicate message, because the two are indistinguishable at the task boundary — and the difference
between them, here, was five hours of GPU time and a cleared set of drafts.

`extract_document_version` therefore takes an explicit `force`. Without it, a version already fully
classified at the current fingerprint is a no-op that logs and returns; with it, the redo proceeds
exactly as today. The API endpoint and an operator dispatch pass it. A redelivered message carries
whatever the original dispatch carried, which is the point: a duplicate of a non-forced dispatch
stays non-forced.

## Consequences

- The phase 1.6 report gains a drift figure per fingerprint, reported beside the golden-set score
  and **not** a gate — a gate on drift would fail a model for being a model.
- `extract_document_version` grows a parameter, and the completed-at-same-fingerprint case becomes
  a logged no-op rather than a silent redo.
- Re-extraction is no longer usable as a regression test for the extractor. Golden-set scoring,
  which compares against fixed expected output rather than against a previous run, is — and is
  already the mechanism phase 1.6 uses.
- ADR-0017 decision 1 stays in force in every other respect. This amends one sentence of it and
  confirms the caveat it already carried.

## What this does not decide

**Content-level agreement is still unmeasured.** Everything above rests on IR counts, because the
second pass cleared the first pass's drafts before anything could compare them. The interesting
question — when two passes agree on the count, do they agree on the obligations? — needs a run that
retains both sides, which nothing currently does. Until that runs, treat 37/43 as the ceiling.

**Why every version ran twice is unresolved.** The doubling is systematic rather than random: 50 of
53 versions ran exactly two `samd` passes, in the same order both times. Three candidate causes have
been ruled out. It is not a domain fan-out — all 110 runs carry `domain_profile = samd`. It is not
the Redis visibility timeout, which `make_celery` sets to 24 hours on producer and consumer alike
for exactly this failure mode. And the duplicates did not exist at dispatch: a queue inspection at
13:40 found 53 messages over 52 distinct versions.

Operator triggers from the review UI explain part of it and are worth recording as the shape of the
thing: `audit_log` holds seven `extraction.triggered` rows between 13:10 and 13:21, all with
`"domain": null`, and one version (`law:014826#별표0`) was triggered twice within a minute — which
together with the batch dispatch is exactly the threefold queue entry observed that afternoon. Seven
clicks do not account for fifty doubled versions, so the cause of the rest is still open.

Decision 4 makes a recurrence cheap rather than expensive, which is the right response to a cause
that is not yet known — but it is a mitigation, not an explanation.
