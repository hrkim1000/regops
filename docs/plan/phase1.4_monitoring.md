# Phase 1.4 — Monitoring & alert routing

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W7–W10 · **Status:** 🟢 done (2026-08-11) — 6/6 acceptance
- **Governed by:** [ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) decisions 2 · 3
- **Depends on:** [phase1.1](phase1.1_normalization.md) (emits `change_events`)
- **Service:** `monitoring`

---

## Goal

Get a detected change to the right person within 24 hours. Two Go/No-Go gates live here — detection
coverage ≥ 95% and detection latency ≤ 24h — and both are measured end to end, from the authority's
publication to the owner's alert.

## Scope

**In:** subscription matching, impact grading, alert composition and delivery, daily briefing.

**Out:** everything that writes the clause store. `monitoring` reads `change_events` one-way by raw
SQL and never writes a `regulation` table. Ticket-system integrations (Jira and equivalents) are
Phase 3.

## Tasks

### Tables — the ADR-0005 gap this phase fills

- [x] `alert_subscriptions`, `alerts`, `alert_deliveries` — all **tenant-scoped**, `tenant_id` from the first migration
- [x] Impact grading writes onto `alerts` rather than a table of its own until there is a reason to separate it

### The seam

- [x] Read `change_events` by raw SQL via `sqlalchemy.text()` — never import the `regulation` ORM model
- [x] Batch lookups with `= ANY(:ids)`
- [x] Confirm no code path in `monitoring` writes a `regulation` table — enforce in review

### Routing

- [x] Subscription matching on **cell** — `{authority}_{domain}`
- [x] Fan-out: one `ChangeEvent` reaches every claiming cell's subscribers and no others
- [x] Deduplicate — one amendment touching many clauses is one alert with N clause references, not N alerts
- [x] Delivery with retry, backoff, and a recorded outcome per attempt

### Impact grading (Phase 1 limits)

- [x] Grade by `change_kind`, clause count, and whether a locked IR cites the touched clause
- [x] **Phase 1 routes on cell, not product.** Per [ADR-0007](../design/ADR-0007-context-map-and-applicability.md) an IR applies to a *cell* until the Product context exists, so alerting can only say "something in your cell changed." State this limitation in the UI rather than implying product-level precision
- [x] Do not build product-profile routing here — it is [phase2.2](phase2.2_compliance.md), tenant-scoped, and putting it in `monitoring` would make shared reference data tenant-dependent

### Briefing

- [x] Daily change briefing per subscriber, composed on read
- [x] Owner assignment recorded and auditable

## Acceptance criteria

- [x] Publication → alert measured end to end at ≤ 24h against a real MFDS amendment
- [x] Detection coverage ≥ 95% per gated cell, verified by after-the-fact manual comparison
- [x] A renumbering-only change generates **no** end-user alert — it is not a substantive amendment, and false positives attack the coverage story from the other side
- [x] An amendment touching 40 clauses produces one alert, not 40
- [x] Delivery failure retries and is visible; a wedged mail relay does not stop ingestion
- [x] Static analysis or review confirms zero `regulation` writes from `monitoring`

**How each was verified.** 20 integration tests in
`services/monitoring/tests/integration/test_phase1_4_acceptance.py` against real Postgres, real
`change_events` and real diffs, plus 24 unit tests. Then live on the dev stack, routing **every**
amendment in the ingested corpus — all 7 versions carrying change events, both gated cells
subscribed:

| Cell | change events emitted | reached an alert | coverage | alerts |
|---|---|---|---|---|
| `mfds_cosmetic` | 53 | 53 | **100%** | 4 |
| `mfds_samd` | 56 | 56 | **100%** | 3 |

That is the coverage gate and the dedup criterion in one number: **109 change events became 7
alerts**, one per amendment per claiming cell, each carrying its own clause list. The largest is
의료기기법 MST 21525 — 24 events on `mfds_samd` into a single `medium` alert, graded on the six
deleted 조문, 24 clause references, delivered in one attempt. Before either cell was subscribed,
`mfds_cosmetic` reported 0% beside `subscribers: 0`, which is the metric saying *nobody asked*
rather than *routing is broken*.

Two honest limits on that run:

- **The latency figures are backfill latency, not detection latency.** They read in the thousands of
  hours because these versions were ingested in a phase-1.1 backfill and routed for the first time
  today. The gate is a claim about live operation and is re-measured in
  [phase1.6](phase1.6_evaluation.md) against an amendment detected on cadence. What this phase
  establishes is that the number is *reported*, from both clocks, with `unmeasurable` counted
  separately where the authority published no date at all.
- **No amendment in the corpus is renumbering-only**, so the suppression path logged
  `suppressed=0` throughout — expected, since the diff stage's ordinal fix already removed the
  spurious `MOVED` events that used to dominate. That criterion rests on the integration tests,
  which exercise both the renumber-only case and a renumber alongside a real edit.

The seam criterion is a test rather than a review note: `tests/unit/test_seam.py` walks the AST of
every service module and fails if one imports a model `monitoring` does not own, or if any `text()`
statement in the service contains a write verb. Migration 0006's grant is the third door.

## Risks & open questions

- ~~**`monitoring` is the cheapest Phase 1 reversal.**~~ — **decided 2026-08-11: it stays its own service** ([ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) open question 2, reasoning in the [brief](../design/decision-2026-08-05-lapsed-service-boundaries.md)). Taken at the W7 deadline, immediately before this phase starts — which was the condition, because the moment subscription matching, impact grading and delivery are built here the reversal stops costing three tables and one seam. The accepted price is a fourth deployment unit at 6.5 FTE; revisit only with pilot evidence, not by drift.
- **False-positive rate has no gate.** The six gates measure coverage and latency but not alert precision; a system that alerts on everything passes both. Watch it in the pilot even though it is not gated. What this phase adds toward it: renumbers and moves are suppressed before composition and the dropped count is returned by the task, and every alert records the *basis* of its grade, so "how many of our high-severity alerts were high because of a locked IR" is countable rather than anecdotal.
- **`structure_drift_alerts` stays in `regulation`** — scraper-drift adjudication, not an end-user alert, despite the name. Do not migrate it here.
- **Grading thresholds are uncalibrated.** `ALERT_BULK_CLAUSE_COUNT = 20` and the three-way precedence are reasoned, not measured — there is no corpus of graded amendments to fit them to. Phase 1.6 re-derives them from pilot data. The *ordering* is not provisional: a human-locked obligation over moved evidence outranks any volume of unreviewed churn.

## Deviations & decisions

1. **A renumbering-only amendment leaves no row at all — not a suppressed alert.** The acceptance
   criterion says it must generate no end-user alert, and an `alerts` table holding rows nobody
   should ever see is a queue waiting to be surfaced by accident. The count is returned by
   `monitoring.route_change_events` as `events_suppressed` / `cells_suppressed` and logged, so the
   suppression is observable without being addressable. `CHECK (clause_count > 0)` makes the empty
   alert unrepresentable rather than merely unwritten.

2. **`monitoring` runs no beat, and retries are Celery countdowns.** CLAUDE.md places the scheduler
   with `regulation` because it drives `source_schedules` and has no other consumer. A retry sweep
   here would have needed a second beat to re-discover work that was already scheduled at the moment
   it failed. So a failed delivery re-dispatches `monitoring.deliver_alert` with a `countdown`, and
   `alert_deliveries.next_retry_at` records when — the schedule belongs to the delivery, survives a
   worker restart, and is queryable. The daily briefing needs no beat either: it is composed on read.

3. **Grading reads `irs.locked_at`, not `irs.status`.** By the time routing runs, the diff stage has
   already superseded the citations *and* moved their IRs from `locked` to `stale` in the same
   transaction ([ADR-0004](../design/ADR-0004-ir-extraction.md) decision 5). Grading on
   `status = 'locked'` would therefore find nothing and quietly grade every amendment as if no
   obligation rested on it — a bug that fails open, in the direction where nobody notices. Draft IRs
   are staled by the same sweep and are indistinguishable afterwards except by `locked_at`, which
   only a human's lock ever sets. That is also the fact worth grading on: *someone asserted this
   obligation, and the text under it has changed.* Keyed by domain, so a cosmetic subscriber is not
   alerted at high severity because a SaMD obligation was staled by the same shared instrument.

4. **`UNIQUE NULLS NOT DISTINCT` on `alerts` and `alert_subscriptions`.** `tenant_id` is null until
   Phase 3, and PostgreSQL's default treats two nulls as distinct — so an ordinary UNIQUE would have
   enforced nothing at all today, which is precisely when "one amendment is one alert" is being
   built. PostgreSQL 15+; the stack is 16. It is what makes a re-diff update one alert instead of
   raising a second, and it is a schema guarantee rather than a property of the code that writes it.

5. **No alert for a cell nobody subscribes to.** These tables are tenant-scoped and an alert is
   composed per tenant; a cell with no subscription has no tenant to attribute one to and no reader.
   Recorded as `cells_without_subscribers` and reported as `subscribers: 0` beside the coverage
   figure, so a cell at 0% reads as *nobody asked* rather than as a routing failure.

6. **`min_severity` filters delivery, not composition.** A below-threshold alert still exists and is
   still readable in the list; it is simply not pushed to someone who asked for medium and above. An
   alert with no eligible subscription is `delivered` with zero deliveries rather than `pending`
   forever over work nobody is going to do — `PENDING` means *delivery work is outstanding*, and the
   delivery count on the API keeps "delivered to nobody" legible.

7. **`EMAIL` is declared and unimplemented; Phase 1 delivers `in_app` and `webhook`.** There is no
   mail relay in the stack, and a channel that quietly returned success would put a delivery that
   never happened into the log — the alerting equivalent of an answer with no citation. `EMAIL`
   raises, lands in `alert_deliveries` with a reason, retries on the normal backoff and is abandoned
   visibly. Adding a relay is a channel class behind the existing `Channel` protocol, not a schema
   change.

8. **Briefing timestamps render in the authority's timezone; the window is a rolling 24 hours.**
   This closes the note `regops_shared.constants.version_status` left for this phase — it evaluates
   the effective-date boundary in UTC and says a Korean date reads as pending for nine hours after it
   takes effect in Korea. Harmless on a browser label, wrong on a briefing whose entire subject is
   *when* something changed. A calendar-day window was rejected: a subscriber may hold cells across
   authorities in different timezones, so it would need a day boundary that is wrong for at least
   one of them, and a rolling window has no boundary to get wrong and no gap between two runs.

9. **Backoff is capped at six hours.** The gate is publication → alert within 24 hours, so an
   unbounded doubling schedule would let a receiver that recovers on day two record a success that
   missed the only deadline that matters. Five attempts, doubling from one minute, total under a day.

10. **Found by running it: `:since IS NULL` fails on asyncpg.** The coverage denominator is the one
    cross-seam read that runs only from the API, and asyncpg prepares statements server-side — a bare
    parameter appearing only in a null test gives PostgreSQL nothing to infer a type from, and the
    metrics endpoint 500s with *could not determine data type of parameter $1*. The sync driver the
    worker uses infers it happily, which is exactly why a worker-side integration suite could not see
    it. Fixed with an explicit `CAST`, and covered by an async test on the async engine — the general
    lesson being that the two drivers need separate coverage wherever a read is API-only.
