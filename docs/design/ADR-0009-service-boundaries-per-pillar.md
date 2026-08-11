# ADR-0009 — Service boundaries per pillar, phased

- **Status:** Proposed
- **Date:** 2026-07-30
- **Depends on:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md), [ADR-0005](ADR-0005-service-architecture.md), [ADR-0007](ADR-0007-context-map-and-applicability.md), [ADR-0008](ADR-0008-service-composition.md)
- **Supersedes:** [ADR-0005](ADR-0005-service-architecture.md) decision 1 (three backend services plus a frontend)
- **Updates:** [ADR-0008](ADR-0008-service-composition.md) decision 6 — Alert and Impact move to `monitoring`

---

## Context

ADR-0005 drew three backend services from ownership and failure isolation, and explicitly rejected
one-service-per-pipeline-stage. That reasoning holds. But it left one thing unassigned: **the
alerting surface has no owner.** Decision 3's table ownership list contains no
`alert_subscriptions`, `alerts`, or `deliveries` — while decision 2 lists "alert subscriptions"
among tenant-scoped data and the closing section defers "alert/ticket integrations" to a later
phase. Monitoring is RegOps.md pillar 01 and a Phase 1 deliverable, so the gap is load-bearing.

Aligning services to the four product pillars closes it. Two decompositions were considered and
rejected on the way here — eighteen stage-services ([memo/agent.md](../memo/agent.md), answered in
ADR-0008), and a variant placing crawl and diff in Monitoring (rejected below). Both cut through the
clause store; the boundary that works cuts *after* it.

## Decisions

### 1. Services follow product pillars, and arrive by phase

| Phase | Services | Added because |
|---|---|---|
| **1** | `platform-core` · `regulation` · **`monitoring`** · `assistant` | monitoring is a Phase 1 pillar with its own tables and its own failure mode |
| **2** | + `compliance` | gap analysis and control mapping arrive with requirements attached (ADR-0007) |
| **3** | + `tenancy` | provisioning, billing, partner gateway — see decision 4 |

`platform-core` (identity, roles, audit trail), `regulation` (L1–L3), and `assistant` (retrieval,
generation, verification) keep the ownership and rationale ADR-0005 gave them. Only the count and
the monitoring boundary change.

**`compliance` and `tenancy` are not built now.** ADR-0005's warning stands — a boundary drawn
before its requirements are known is a boundary drawn wrong. They are named here so that Phase 1
table ownership does not have to be undone later, not so that they can be scaffolded early.

### 2. The clause store has one writer, and the seam is `change_events`

This is the decision that makes the split safe.

```text
REGULATION                                      │  MONITORING
  crawl → archive → parse → version → diff      │
    → emit change_event                         │
    → extract IR                                │
                       change_events ───────────┼──>  subscription matching
                       (one-way read, raw SQL)  │     impact grading
                                                │     alert composition & delivery
                                                │     ticket integration · daily briefing
```

Everything that **writes** the clause store is `regulation`: crawl, archive, parse, version, diff,
change-event emission, IR extraction. `monitoring` begins where writing ends. It reads
`change_events` by raw SQL per the cross-service convention and never writes a regulation table.

Two properties follow, and both are the point:

- **No mid-transaction seam.** The ingestion chain commits incrementally inside one service
  (ADR-0003, ADR-0005 decision 6). Nothing in it crosses a boundary.
- **Independent failure.** A wedged scraper does not stop alert delivery for changes already
  detected; a failing Jira integration or mail relay does not stop ingestion.

The scaling profiles also diverge — ingestion is network- and CPU-bound against a fixed source list,
delivery is I/O-bound fan-out that grows with tenants and subscriptions.

### 3. `monitoring` owns the alerting tables

Filling the ADR-0005 decision 3 gap:

```text
monitoring : alert_subscriptions · alerts · alert_deliveries
```

All three are **tenant-scoped** and carry `tenant_id` from the first migration (ADR-0005 decision 2).
Impact grading writes onto `alerts` rather than into a table of its own until there is a reason to
separate it.

`change_events` and `structure_drift_alerts` stay in `regulation`. The latter is scraper
structure-drift adjudication (ADR-0003 decision 6), an ingestion concern despite the name — it is
not an end-user alert and must not migrate to `monitoring`.

### 4. Multi-tenancy is not a service; the Phase 3 service is `tenancy`

A "SaaS Service" cannot own multi-tenancy, because ADR-0005 decision 2 already puts `tenant_id` on
tenant-scoped tables across every service. Every service is tenant-aware; boxing tenancy would mean
the other services are not, which is not a design that works.

What is genuinely a Phase 3 service is the surface *around* tenancy: **provisioning, billing, API
keys, white-label configuration**. The partner API is a separate question — it is a gateway concern
and belongs with ADR-0005 open question 4 (whether the frontend needs a BFF), not with this service.

### 5. The Product context ships with `compliance`

ADR-0007 defines four bounded contexts; **Product** has no service in the pillar decomposition.
It goes with `compliance` in Phase 2: both are tenant-scoped, both exist to answer applicability
(`Product × Regulation → Compliance`), and ADR-0007 already groups them.

Until then, per ADR-0007, an IR applies to a **cell**, not a product — so Phase 1 `monitoring` can
only route on cell subscription. That is a known limitation of Phase 1 alerting, not a defect in
this boundary: routing gets sharper when Product exists, and the seam does not move.

A context is not a service (ADR-0007 decision 1), so four contexts against six eventual services is
expected, not a mismatch.

## Rejected alternative — crawl and diff in `monitoring`

Proposed on the grounds that crawl + diff *is* change detection. Rejected: it crosses the clause
store three times in one run.

```text
crawl(M) ──> parse/version(R) ──> diff(M) ──> alert(M)
      └─ M→R ─┘                └─ R→M ─┘
```

- **crawl writes `sources`, `source_schedules`, `fetch_observations`** — regulation-owned. Two
  services writing one table is worse than the seam it was meant to avoid; the convention permits
  cross-service *reads* by raw SQL, not writes.
- **diff writes `clause_diffs`** and must resolve renumbering explicitly rather than reporting
  delete + add (ADR-0002, glossary). That requires document-structure knowledge. An alerting service
  has no business understanding clause numbering schemes.
- **`change_events` ownership splits** from the documents they describe, leaving `regulation`
  without its own change history.

[ADR-0003](ADR-0003-ingestion-and-change-detection.md) is titled *ingestion and change detection*:
the repository already treats them as one concern, and this variant halves that ADR. Change
**detection** is a property of the document pipeline; change **notification** is the product
feature. The pillar boundary belongs between them.

## Consequences

- The alerting surface has an owner and named tables for the first time.
- ADR-0008's taxonomy is unaffected — agent / pipeline / shared is defined *inside* a service, so
  moving a unit between services does not change its kind. Only the "Home" column of decision 6
  moves: Alert and Impact to `monitoring`.
- **Four deployment units in Phase 1 at 6.5 FTE for 16 weeks.** This is the real cost. It sharpens
  ADR-0005 open question 1 from "do regulation and assistant merge" into "how many units can this
  team operate" — a week-1 decision, and the first place to give ground if Phase 1 runs hot.
- Splitting `monitoring` later would mean migrating three tenant-scoped tables and rewriting their
  reads as raw SQL under Phase 2 pressure. The same "cheap now, tedious later" argument ADR-0005
  decision 3 used for embeddings applies here.

## Open questions

1. ~~**What is "interpretation"?**~~ — **resolved**, and it turned out to be two things. Structuring
   a requirement into obligation · bearer · scope · evidence is IR extraction, **absorbed** into the
   requirement agent ([ADR-0008](ADR-0008-service-composition.md) decision 6). The graph vocabulary
   and edges beneath obligations are the `semantic enrichment` layer
   ([ADR-0010](ADR-0010-semantic-enrichment-and-graph-model.md)) — in `regulation`, split into the
   Cross-reference pipeline and the Ontology Mapping agent, built in Phase 2. The name itself is
   retired either way: interpretation is a legal act (ADR-0010 decision 1).
2. ~~**Does `monitoring` survive a Phase 1 scope cut?**~~ — **resolved 2026-08-11: it stays its own
   service.** Taken at the W7 deadline the
   [decision brief](decision-2026-08-05-lapsed-service-boundaries.md) set, immediately before
   [phase1.4](../plan/phase1.4_monitoring.md) starts building into the boundary — which is the last
   moment the reversal is still three tables and one seam.

   The seam is what decides it: everything that *writes* the clause store is `regulation`, and
   `monitoring` begins where writing ends, reading `change_events` one-way by raw SQL. That is an
   ownership boundary, not a pipeline stage — the test CLAUDE.md sets — and it was already built and
   respected through phases 1.0–1.3 without anything crossing it.

   **The accepted cost is a fourth deployment unit at 6.5 FTE**, which the Consequences section
   above names as the real price of this design and which nothing in Phase 1 needs for scaling. It
   is accepted deliberately rather than overlooked. If operating four units becomes the dominant
   cost, revisit it with evidence from the pilot — but the cheap window closes here, so a later
   merge means migrating three tenant-scoped tables and rewriting their reads under Phase 2
   pressure.
3. **Partner API placement** — inherited from ADR-0005 open question 4, unresolved here.
