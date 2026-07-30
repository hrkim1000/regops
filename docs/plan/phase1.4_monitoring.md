# Phase 1.4 — Monitoring & alert routing

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W7–W10 · **Status:** ⬜ planned
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

- [ ] `alert_subscriptions`, `alerts`, `alert_deliveries` — all **tenant-scoped**, `tenant_id` from the first migration
- [ ] Impact grading writes onto `alerts` rather than a table of its own until there is a reason to separate it

### The seam

- [ ] Read `change_events` by raw SQL via `sqlalchemy.text()` — never import the `regulation` ORM model
- [ ] Batch lookups with `= ANY(:ids)`
- [ ] Confirm no code path in `monitoring` writes a `regulation` table — enforce in review

### Routing

- [ ] Subscription matching on **cell** — `{authority}_{domain}`
- [ ] Fan-out: one `ChangeEvent` reaches every claiming cell's subscribers and no others
- [ ] Deduplicate — one amendment touching many clauses is one alert with N clause references, not N alerts
- [ ] Delivery with retry, backoff, and a recorded outcome per attempt

### Impact grading (Phase 1 limits)

- [ ] Grade by `change_kind`, clause count, and whether a locked IR cites the touched clause
- [ ] **Phase 1 routes on cell, not product.** Per [ADR-0007](../design/ADR-0007-context-map-and-applicability.md) an IR applies to a *cell* until the Product context exists, so alerting can only say "something in your cell changed." State this limitation in the UI rather than implying product-level precision
- [ ] Do not build product-profile routing here — it is [phase2.2](phase2.2_compliance.md), tenant-scoped, and putting it in `monitoring` would make shared reference data tenant-dependent

### Briefing

- [ ] Daily change briefing per subscriber, composed on read
- [ ] Owner assignment recorded and auditable

## Acceptance criteria

- [ ] Publication → alert measured end to end at ≤ 24h against a real MFDS amendment
- [ ] Detection coverage ≥ 95% per gated cell, verified by after-the-fact manual comparison
- [ ] A renumbering-only change generates **no** end-user alert — it is not a substantive amendment, and false positives attack the coverage story from the other side
- [ ] An amendment touching 40 clauses produces one alert, not 40
- [ ] Delivery failure retries and is visible; a wedged mail relay does not stop ingestion
- [ ] Static analysis or review confirms zero `regulation` writes from `monitoring`

## Risks & open questions

- **`monitoring` is the cheapest Phase 1 reversal.** If four services prove too many at 6.5 FTE, merging this back into `regulation` costs three tables and one seam. Decide in W1 (see [phase0](phase0_foundation.md)), not W8.
- **False-positive rate has no gate.** The six gates measure coverage and latency but not alert precision; a system that alerts on everything passes both. Watch it in the pilot even though it is not gated.
- **`structure_drift_alerts` stays in `regulation`** — scraper-drift adjudication, not an end-user alert, despite the name. Do not migrate it here.

## Deviations & decisions

_None yet._
