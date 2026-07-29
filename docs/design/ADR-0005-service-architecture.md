# ADR-0005 — Service architecture and decomposition

- **Status:** Proposed
- **Date:** 2026-07-29
- **Depends on:** [ADR-0001](ADR-0001-platform-foundation.md) (greenfield), [ADR-0003](ADR-0003-ingestion-and-change-detection.md), [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md)
- **Unblocks:** the RBAC role set that `.claude/skills/service-endpoint` currently defers

---

## Context

Phase 1 is **6.5 FTE for 16 weeks** (development-plan.md § 7). At that size the dominant
architectural risk is not under-decomposition — it is sprawl. Every service boundary buys isolation
and costs a raw-SQL seam, a queue, a deployment unit, a migration coordination point and a debugging
hop. The conventions in `.claude/skills` (FastAPI, one Celery queue per service, shared canonical
models, cross-service access by raw SQL only) describe how services talk; they do not say how many
there should be.

Phase 3 is a multi-tenant external SaaS, so boundaries drawn now should not have to be redrawn then.

## Decisions

### 1. Three backend services plus a frontend — not one per pipeline stage

| Service | Owns | Why it is separate |
|---|---|---|
| **platform-core** | identity, roles, sessions, audit trail | Different security posture and change cadence; every other service depends on it and nothing depends on them |
| **regulation** | the whole ingest → parse → diff → IR pipeline | These stages share one datastore and one failure mode. Splitting them would put a raw-SQL seam in the middle of a single transaction-shaped workflow |
| **assistant** | retrieval, generation, evidence verification | Different scaling profile (LLM latency, embedding throughput) and a different failure mode: an LLM provider outage must not stop ingestion, and a scraper wedge must not stop Q&A |
| **frontend** | Next.js App Router UI | Reaches services through `/api/<svc>/*` rewrites (`.claude/skills/frontend-page`) |

**Boundaries follow ownership and failure isolation, not pipeline stages.** Fetch, parse, diff and
IR extraction all mutate the clause store; making them separate services would mean every parse
writes through a foreign-service seam, which the conventions forbid for good reason.

The one boundary genuinely worth its cost is regulation ↔ assistant, because their outages are
independent and their scaling curves diverge.

### 2. Regulation data is shared; only the mapping layer is tenant-scoped

This is the decision that makes Phase 3 tractable, and it costs nothing now.

| Not tenant-scoped — one copy for everyone | Tenant-scoped |
|---|---|
| `sources`, `documents`, `document_versions`, `clauses`, `clause_diffs`, `change_events`, `standard_references`, `irs` | control mappings, internal SOPs, product profiles, queries, answers, alert subscriptions |

화장품법 is the same 화장품법 for every customer. The knowledge layer is common reference data; what
differs per tenant is *which obligations apply to them* and *what they have done about it*.

Tenant-scoped tables therefore carry a `tenant_id` from the first migration, defaulted to a single
internal tenant in Phase 1. No isolation machinery is built now — but retrofitting a discriminator
onto customer data at Month 13 is a data migration under commercial pressure, and adding a defaulted
column now is nearly free.

### 3. Table ownership is explicit, and reads across it are raw SQL

Per `.claude/skills/db-migration`: canonical models live in `shared/regops_shared/models/`, the
owning service re-exports them, and no service imports another's ORM model.

```text
platform-core : users · roles · sessions · audit_log
regulation    : cells · sources · source_schedules · fetch_observations
                documents · document_cells · document_versions · clauses
                clause_diffs · change_events · structure_drift_alerts
                standard_references · irs · ir_citations · extraction_runs
                clause_classifications
assistant     : clause_embeddings · queries · answers · answer_citations
                verification_results
```

**`assistant` owns the embeddings, not `regulation`.** They are a retrieval artefact: re-embedding
on a model change is an assistant concern, and coupling the embedding lifecycle to the clause
lifecycle would make an embedding-model swap a regulation-service migration.

### 4. The audit trail is a table in platform-core, not a service

The audit trail must record actions from every service, which makes "call the audit service" a
synchronous dependency on the write path of everything. A shared append-only table written through
`regops_shared` gives the same record with no hop and no outage coupling.

Auth is also issued by platform-core — not, as in the prior platform, by the audit component. Those
are unrelated responsibilities that were fused by accident.

### 5. RBAC roles for Phase 1: `viewer | ra | admin`

*(Unblocks the deferral in `.claude/skills/service-endpoint`.)*

| Role | Can |
|---|---|
| `viewer` | read alerts, answers, citations; run queries |
| `ra` | everything `viewer` can, plus review and **lock IRs**, adjudicate structure-drift alerts, confirm control-mapping carry-forward, sign ground-truth markup |
| `admin` | everything `ra` can, plus users, settings, prompt and model configuration |

Locking an IR (ADR-0004 decision 4) and resolving a drift alert (ADR-0003 decision 6) are the
restricted actions — both are points where a human assertion enters the audit trail.

The prior platform's `developer`, `qa` and `clinical_expert` roles do not apply: there are no
clinical gates and no repo-linked development workflow in RegOps. `compliance` arrives in Phase 2
with gap analysis, when there is a control-mapping surface to gate.

### 6. Long work is `202` + task, one queue per service

The ingestion chain (fetch → archive → parse → diff → emit) runs as Celery tasks on the
`regulation` queue, committing incrementally so progress is visible and a retry skips completed rows
(ADR-0003). Cross-service dispatch is `send_task("svc.name", queue="svc")` by name only.

The scheduler (beat) lives with `regulation` — it drives `source_schedules` and has no other
consumer. A standalone scheduler service would be a deployment unit that owns no data.

### 7. The LLM seam is a library, not a service

`regops_shared.llm.get_llm_client()` with the provider from settings. Swapping Ollama for Claude
must not require touching a service. Embeddings stay pinned to `nomic-embed-text` 768-dim
regardless of the generation provider, because changing them invalidates the whole index.

Any row an LLM produced records `llm_provider` and `llm_model` — IRs (ADR-0004) and answers alike.

## Not services in Phase 1

Gap analysis and control mapping (Phase 2), alert/ticket integrations, the multi-tenant portal and
partner API (Phase 3). Each would be a boundary drawn before its requirements are known.

## Open questions

1. **Do `regulation` and `assistant` merge for Phase 1?** Two services is less to operate at 6.5 FTE,
   and the split can be made when the assistant's scaling profile actually diverges. Argument
   against: separating later means moving the embedding tables and rewriting reads as raw SQL —
   cheap now, tedious later. Leaning split; worth a week-1 decision, not a week-8 one.
2. **Applicability has no owner yet.** No service holds product profiles or IR-applicability
   determination, because no ADR defines them — see the note below. Likely `regulation` (it is
   reference-data shaped) or a fourth service if it turns out tenant-heavy.
3. **Audit trail retention and immutability** — append-only by convention, or enforced (no UPDATE
   grant, periodic hash-chaining)? 21 CFR Part 11 expects tamper-evidence; convention alone will not
   survive an audit.
4. **Does the frontend need a BFF?** Three services behind Next.js rewrites is manageable; a fourth
   or a chatty page may argue for aggregation.

## Deferred and still missing: applicability

RegOps.md pillar 01 routes changes by "product, market, and business-unit profiles"; pillar 03
delivers an IR-to-control matrix. Neither has a model. ADR-0003 decision 8 explicitly deferred
product-profile routing, and ADR-0004 open question 2 left conditional-by-class obligations open.

Until it exists, an IR applies to a *cell*, not to a *product* — so alerting can only say "something
in your cell changed," which is the noise problem the monitoring pillar exists to solve, and gap
analysis has no way to state which IRs are in scope. Candidate **ADR-0007**, and it should land
before Phase 2 gap analysis.
