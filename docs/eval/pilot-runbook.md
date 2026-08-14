# Pilot runbook — the four weeks, and the two things that cannot be repaired afterwards

The operating procedure for the phase 1.6 pilot. Everything here is **prepared and not run**: the
instrumentation exists and is tested, the templates are drawn, and no users have been onboarded. This
file is what turns that into a start date.

Two gates depend entirely on it — **pilot retention** (≥ 60% voluntary use for four consecutive
weeks) and **research-time savings** (≥ 30% against the manual process for the same query type). Both
are currently 미측정, and both become measurable the day this runbook is executed.

---

## Two constraints that are not recoverable

Read these before scheduling anything. Everything else in this file can be adjusted mid-flight;
these two cannot be repaired after the fact, only re-run from the beginning.

**1. The baseline is captured before anyone gets access.** Research-time savings is a comparison
against the manual process. Once an analyst has used the workbench, their "manual" time is
contaminated — they now know where the answer is. A baseline captured after access is not a
baseline, and the 30% becomes unfalsifiable.

**2. The cohort is fixed before week 1 starts.** A cohort assembled afterwards out of whoever kept
using the system scores 100% every time, because the people who stopped are not in it. Dropping one
non-returner is the single easiest way to manufacture a passing retention number, and it is
invisible in the result.

A third constraint is merely expensive rather than fatal: **the four weeks cannot be compressed.**
Four consecutive weeks is four consecutive weeks; the scorer intersects across *every* week in the
window rather than counting active weeks, so a user active in weeks 1, 2 and 4 has not cleared the
bar. Any slip upstream eats the measurement window, not the build — protect it.

---

## The sequence

```text
W-1   freeze the build          ── no deploys during the window
W-1   capture the baseline      ── BEFORE access. Constraint 1
W0    fix the cohort            ── BEFORE week 1. Constraint 2
W0    onboard
W1-4  four consecutive weeks    ── weekly check, no intervention
W4    capture measured_minutes  ── same query types, same method
W4    measure
```

### W-1 · Freeze the build

The pilot measures one build. A deploy mid-window means the four weeks measured two different
products and the retention figure describes neither.

Record the commit and stop deploying:

```bash
git rev-parse HEAD          # record this in the pilot log
```

Fixes for outright breakage are still allowed — a broken product measures nothing either. Record any
such deploy with its date, so a retention dip has something to be read against.

### W-1 · Capture the research-time baseline

Time RA staff doing the **same query types** by hand, on the same corpus, **before** they have access
to the workbench.

Fill `ground_truth/research_time_baseline.template.json`:

| Field | What it must hold |
| --- | --- |
| `query_types` | The matched types, named — e.g. *identifier lookup, conceptual obligation search*. Comparing an identifier lookup against a manual conceptual search compares two different tasks |
| `sample_size` | How many queries the average came from. **A mean over three queries is not a baseline** |
| `baseline_minutes` | The manual time to a usable answer |
| `baseline_captured_at` | The date — which must be before the first onboarding |

`measured_minutes` stays empty until W4. It is **not** the harness's `elapsed_seconds`: the gate is
the analyst's time to a *usable* answer, which includes reading the citations and deciding whether to
trust them. Time it the same way you timed the baseline.

Rename to `research_time_baseline.json` once both halves exist.

### W0 · Fix the cohort

Seed an account per participant, then record **every** onboarded user id — including the ones you
suspect will never come back:

```bash
REGOPS_SEED_EMAIL=<user>@<org> REGOPS_SEED_PASSWORD=<value> REGOPS_SEED_ROLE=viewer \
    docker compose exec -T platform-core python /scripts/seed_user.py
```

Fill `ground_truth/pilot_cohort.template.json` with `cohort_fixed_at`, the business unit (one unit,
per the plan), and the `platform-core` user **uuid** of every participant. Rename to
`pilot_cohort.json`.

After this file is written, **nobody is added and nobody is removed.** If a participant leaves the
company mid-pilot, leave them in and record it in the pilot log — the retention figure is then
reported with that note rather than quietly improved.

### W0 · Onboard

The instrumentation reads `queries.asked_by`, so **use means a question asked** — a session opened is
not use. What onboarding has to convey, beyond the login:

- **The ScopeBar cell is the scope of every answer.** A cosmetic question asked in the device cell is
  answered from device regulation, and cross-cell search is a checkbox worded as the risk it carries.
- **확인 필요 is the product working, not an error.** No unsourced answer is ever emitted. A reader
  who reads a refusal as a failure will stop asking, and retention will measure that instead.
- **Every answer carries its clause, version and effective date, and the citation is a link.** The
  citation is the deliverable; the prose is the summary of it.
- **Answers take time on this regime.** At the pinned `gemma3:4b`, generation plus verification runs
  into minutes and often reaches the 4-minute poll ceiling, after which the question is still
  recorded and reachable at its own URL. Say so at onboarding rather than letting each participant
  discover it — see the caveat at the end of this file.

### W1–W4 · Run the four weeks

Check weekly. **Do not intervene** — a reminder to use the system converts voluntary use into
prompted use, and voluntary is the word in the gate.

```bash
E="docker compose exec -T -w /scripts regulation python -m evaluation.cli"
$E gates --out /eval/go-no-go.$(date +%F).md      # retention line reports weekly active counts
```

Weeks are ISO weeks over complete weeks, oldest first, read from `queries.asked_by`. A week nobody
used the system produces no rows at all — which the scorer records as an empty week rather than
skipping it, because a silent gap would otherwise shorten the window.

Keep a plain log beside the run: dated notes of outages, any emergency deploy, anyone who left. The
retention number is a single figure; the log is what makes it interpretable afterwards.

### W4 · Measure

```bash
$E gates --out /eval/go-no-go.md
```

Retention and research-time savings stop rendering as 미측정 and become numbers with a method behind
them. If the reviewer packet has also come back, the four human-gated measurements land in the same
report — see [reviewer-packet.md](reviewer-packet.md).

---

## What a small cohort does to the number

The gate is written for 20–30 users in one business unit. A smaller pilot still produces a *real*
measurement — the scorer does not care how many users there are — but the figure carries more
sampling noise, and one person's holiday moves it further than it should.

**Report the cohort size beside the percentage, always.** `n=7, 5 retained (71%)` is honest and
useful; `71%` alone implies a precision the pilot did not have. The report prints the cohort size
from `pilot_cohort.json` for exactly this reason — do not quote the percentage without it.

---

## The caveat this pilot carries, recorded rather than discovered

The pinned regime is `ollama` / `gemma3:4b` at `LLM_TIMEOUT_SECONDS=180`, and at that regime the
model misses its own ceiling on most questions: over the bounded runs so far, **80%+ of answers were
refusals, most of them `model_unavailable`** — the model not responding in time, rather than the
product declining for lack of evidence.

That matters here more than anywhere else in the phase, because **retention is a UX outcome**. A
participant who waits three minutes and gets 확인 필요 learns not to come back, and the retention gate
will faithfully record that — as a fact about this hardware, not about whether the product is worth
using.

Staying at the pinned regime is a recorded choice (2026-08-14): it keeps every number already
measured comparable, and changing the model changes the regime rather than improving it. The cost is
that a retention figure measured here bounds the product from below and should be read that way. If
the figure disappoints, **compare a second regime before concluding anything about the product** —
that comparison is [phase1.6](../plan/phase1.6_evaluation.md) § Risks' standing recommendation, and
it is a comparison, not a fix.
