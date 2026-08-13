# Phase 0 — Foundation

- **Roadmap:** precedes M1 · **Weeks:** W0–W2 · **Status:** 🟢 done (2026-07-30)
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

- [x] Monorepo layout: `services/{platform-core,regulation,monitoring,assistant}/`, `shared/`, `frontend/`
- [x] `docker-compose.yml` — postgres, redis, minio, pgadmin, flower + `app` and `local-llm` profiles
- [x] Assign and record service host ports (CLAUDE.md § Service Architecture leaves them open)
- [x] `.env.example` refreshed to match; `.env.dev` loads per `STAGE`
- [x] `.env.test` — created with the first integration suite that needed a separate DB; gitignored, and `STAGE=test REGOPS_DB_NAME=regops_test` is the documented way in
- [x] `GET /health` on every service
- [x] `frontend.depends_on` gates on it — done in [phase1.5](phase1.5_frontend.md) once the frontend existed

### Shared library

- [x] `shared/regops_shared/` installable (`pip install -e /shared`)
- [x] `models/` — canonical ORM base; every table modelled once, owner re-exports
- [x] `auth/` — `create_access_token`, `decode_token`, `get_current_principal()`, `require_roles()`
- [x] `llm/get_llm_client()` — provider from settings (`ollama` | `claude`); embeddings pinned to `nomic-embed-text` 768-dim
- [x] `db/`, `celery/make_celery()`, `storage/` (MinIO), `logging/` structlog JSON
- [x] Audit-trail writer against the `platform-core` table — **not** a service call

### Database

- [x] Alembic single history in `shared/alembic/versions/`, `0001` baseline (explicit DDL — see Deviations)
- [x] `cells` seeded with exactly 8 rows (`authority` × `domain`), UNIQUE constraint
- [x] `shared/alembic/regops_schema.sql` authoritative dump, reconciled with the applied migration
- [x] n/a — **no tenant-scoped table exists yet.** `users`, `sessions`, `audit_log` and `cells` are all shared. The `tenant_id` rule binds from the first tenant-scoped table, which is phase 2.2

### platform-core

- [x] Users, roles, sessions, `audit_log` (append-only)
- [x] JWT HS256 issuance and signing; `TokenPayload` requires `id, email, role, exp, type`
- [x] RBAC enum `viewer | ra | admin` — no `developer`, `qa`, or `clinical_expert`
- [x] Response envelope `{code, status, message, data, meta}` enforced by a shared handler

### CI & guards

- [x] Lint/typecheck: `ruff` (clean), `mypy` (16 files, no issues)
- [x] `tsc --noEmit` — wired into CI in [phase1.5](phase1.5_frontend.md) once the frontend existed
- [x] pytest wired with `tests/unit` · `tests/integration` split; suites exist for `shared` and `platform-core` (the stub services have the dirs but no tests yet)
- [x] **Tier D archive scan** — CI fails on known standard identifiers (ISO 13485, IEC 62304, …) appearing in archive or fixture paths (risk 5, development-plan.md § 9)
- [x] Secret scan: no `.env*` beyond `.env.example`, no real tokens in fixtures

## Acceptance criteria

- [x] `docker compose up -d` brings the stack healthy from a clean checkout
- [x] `docker compose run --rm migrate` applies to head on a fresh DB and is idempotent on a live one
- [x] Login end-to-end issues a JWT; a `viewer` is 403'd on an `ra` route, verified by test
- [x] `cells` contains exactly 8 rows and rejects a 9th
- [x] An LLM call through `get_llm_client()` succeeds against Ollama and records provider/model
- [x] Green **locally**: ruff, ruff format, mypy, 32 tests, Tier D scan, secret check
- [x] Green on GitHub Actions (run on `ee1a9a5`) — red on the first run; see Deviation 6

## Risks & open questions

- 🟢 ~~**Four services at 6.5 FTE — the W1 decision has lapsed and defaulted by construction.**~~ —
  **closed 2026-08-11: four services, `monitoring` stays its own**
  ([ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) open question 2). Phase 0
  scaffolded all four, so "open with four" was the de facto answer for months before anyone chose
  it; it was confirmed on the merits at the W7 deadline, before [phase1.4](phase1.4_monitoring.md)
  built into the boundary. The outcome matches the default, which is exactly why it needed taking —
  a decision that agrees with the drift is still a decision, and this one now has a date and a
  reason instead of a scaffold.
- 🟢 ~~**ADR-0005 open question 1** — whether `regulation` and `assistant` stay split.~~ —
  **closed 2026-08-05: they stay split**, before [phase1.3](phase1.3_retrieval_qa.md) built
  `assistant` at W5 and made the reversal mean moving the embedding tables and rebuilding the index.
  The accepted cost is that `assistant` reads `clauses` constantly and every such read is raw SQL.
- ~~**ADR-0005 open question 3**~~ — **resolved** in
  [ADR-0011](../design/ADR-0011-audit-trail-immutability.md): enforced, not conventional.

## Deviations & decisions

<!-- Architecture changes go in an ADR, linked here. -->

**1. Audit-trail immutability resolved → [ADR-0011](../design/ADR-0011-audit-trail-immutability.md).**
Enforced at the database, not by convention. The build surfaced a defect in the first attempt: the
`REVOKE` was a no-op because the app connected as the table owner, and **a table owner bypasses its
own grants** — `UPDATE audit_log` succeeded. Fixed by adding a non-owner `regops_app` role
(`infra/postgres/init/01-app-role.sh`); services connect as it, migrations as the owner. Verified:
the app role now gets `permission denied`, and a superuser edit is caught by the hash chain at the
exact `seq`.

**2. Baseline is explicit DDL, not `create_all`.** The db-migration skill describes a baseline built
by `create_all`. `0001` writes the DDL directly instead, because it must also seed the 8 cells and
apply the audit grants — neither of which `create_all` can express. It still uses
`IF NOT EXISTS` throughout, so it is fresh-DB safe and idempotent either way.

**3. `passlib` replaced with `bcrypt` directly.** passlib 1.7.4 raises
`ValueError: password cannot be longer than 72 bytes` against bcrypt ≥ 4.1 during backend probing.
`hash_password` / `verify_password` now call `bcrypt` and normalise input to bcrypt's documented
72-byte limit rather than erroring at the boundary.

**4. Port block moved to `2xxxx`.** The README had inherited another local stack's ports
(Flower 15555, pgAdmin 15051, MinIO 19001) verbatim, so the two stacks could not run together.
RegOps now uses postgres 25432 · redis 26379 · minio 29000/29001 · pgadmin 25051 · flower 25555 ·
services 28000–28003. Ollama stays shared on 11434.

**5. pytest uses `--import-mode=importlib`.** Four services each own a `tests/` directory, which
collides under the default prepend import mode.

**6. The Tier D guard failed its own first CI run, and the reason mattered more than the fix.**
`scripts/tier_d_scan.py` necessarily contains every marker string it searches for, so once it was
committed it matched its own source. It had passed locally because the scan enumerated
`git ls-files` — tracked files only — and the script was still untracked when it ran. **A guard that
only sees history cannot stop something entering it**: any newly added file passed until the commit
that made it visible, which is the opposite of what this guard is for. Now scans tracked *plus*
untracked-but-not-ignored, so local and CI see the same set, with self-exclusion by path rather than
by obfuscating the markers. Verified both directions — clean on the repo, exits 1 on a planted
fixture containing standard front matter.
