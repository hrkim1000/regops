# Phase 0 — Foundation

- **Roadmap:** precedes M1 · **Weeks:** W0–W2 · **Status:** ⬜ planned
- **Governed by:** [ADR-0001](../design/ADR-0001-platform-foundation.md), [ADR-0005](../design/ADR-0005-service-architecture.md), [ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md)
- **Unblocks:** everything

---

## Goal

Stand up the stack the roadmap assumes but never specifies. RegOps.md opens at the first connector;
there is no repository scaffold, no compose file, no database, and no shared library. Phase 0 is the
gap between "the architecture is decided" and "there is somewhere to put the first connector."

Keep it minimal. Every service scaffolded here is one more thing to operate at 6.5 FTE, and
[ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) already flags four Phase 1
deployment units as the real cost.

## Scope

**In:** monorepo layout, Docker Compose stack, `regops_shared`, migration baseline, `platform-core`
(auth · RBAC · audit trail), CI, and the Tier D guard.

**Out:** any regulation logic. No connectors, no parsers, no LLM calls. `regulation`, `monitoring`
and `assistant` are scaffolded as health-check-only services; their content is phases 1.0–1.4.

## Tasks

### Repository & stack

- [ ] Monorepo layout: `services/{platform-core,regulation,monitoring,assistant}/`, `shared/`, `frontend/`
- [ ] `docker-compose.yml` — postgres, redis, minio, pgadmin, flower + `app` and `local-llm` profiles
- [ ] Assign and record service host ports (CLAUDE.md § Service Architecture leaves them open)
- [ ] `.env.example` refreshed to match; confirm `.env.dev` / `.env.test` load per `STAGE`
- [ ] `GET /health` on every service; `frontend.depends_on` gates on it

### Shared library

- [ ] `shared/regops_shared/` installable (`pip install -e /shared`)
- [ ] `models/` — canonical ORM base; every table modelled once, owner re-exports
- [ ] `auth/` — `create_access_token`, `decode_token`, `get_current_principal()`, `require_roles()`
- [ ] `llm/get_llm_client()` — provider from settings (`ollama` | `claude`); embeddings pinned to `nomic-embed-text` 768-dim
- [ ] `db/`, `celery/make_celery()`, `storage/` (MinIO), `logging/` structlog JSON
- [ ] Audit-trail writer against the `platform-core` table — **not** a service call

### Database

- [ ] Alembic single history in `shared/alembic/versions/`, `0001` baseline via `create_all`
- [ ] `cells` seeded with exactly 8 rows (`authority` × `domain`), UNIQUE constraint
- [ ] `shared/alembic/regops_schema.sql` authoritative dump, reconciled with the applied migration
- [ ] `tenant_id` present on tenant-scoped tables from `0001` ([ADR-0005](../design/ADR-0005-service-architecture.md) decision 2)

### platform-core

- [ ] Users, roles, sessions, `audit_log` (append-only)
- [ ] JWT HS256 issuance and signing; `TokenPayload` requires `id, email, role, exp, type`
- [ ] RBAC enum `viewer | ra | admin` — no `developer`, `qa`, or `clinical_expert`
- [ ] Response envelope `{code, status, message, data, meta}` enforced by a shared handler

### CI & guards

- [ ] Lint/typecheck: `ruff`, `mypy`, `tsc --noEmit`
- [ ] pytest wired per service with `tests/unit` · `tests/integration` split
- [ ] **Tier D archive scan** — CI fails on known standard identifiers (ISO 13485, IEC 62304, …) appearing in archive or fixture paths (risk 5, development-plan.md § 9)
- [ ] Secret scan: no `.env*` beyond `.env.example`, no real tokens in fixtures

## Acceptance criteria

- [ ] `docker compose up -d` brings the stack healthy from a clean checkout
- [ ] `docker compose run --rm migrate` applies to head on a fresh DB and is idempotent on a live one
- [ ] Login end-to-end issues a JWT; a `viewer` is 403'd on an `ra` route, verified by test
- [ ] `cells` contains exactly 8 rows and rejects a 9th
- [ ] An LLM call through `get_llm_client()` succeeds against Ollama and records provider/model
- [ ] CI green: lint, typecheck, unit tests, Tier D scan, secret scan

## Risks & open questions

- **Four services at 6.5 FTE** — ADR-0009 records this as the real cost and names `monitoring` as
  the cheapest reversal. Decide in W1 whether to open with four or merge `monitoring` into
  `regulation` until W7; do not defer this to W8.
- **ADR-0005 open question 1** — whether `regulation` and `assistant` stay split. Same W1 decision.
- **ADR-0005 open question 3** — audit-trail immutability: append-only by convention, or enforced
  (no UPDATE grant, hash chaining)? Part 11 expects tamper-evidence; convention will not survive an
  audit. Cheapest to settle before `0001`.

## Deviations & decisions

<!-- Log deviations from this plan as work lands. Architecture changes go in an ADR, linked here. -->

_None yet._
