---
name: service-endpoint
description: Use when adding or changing a FastAPI endpoint or Celery task in any service — response envelope, RBAC, cross-service raw SQL, API naming/versioning, error handling, and the pluggable LLM seam.
---

# Service Endpoints & Tasks

## API shape

- URL-versioned: `/api/v1/...` on the service; the browser reaches it via the Next.js
  `/api/<svc>/*` rewrite (a version-pinned alias).
- Plural resource nouns (`/documents/{id}`); explicit verbs for nested actions
  (`POST .../generate`); query params + JSON bodies in `snake_case`.
- **Every response wears the envelope** `{code, status, message, data, meta}`.
  List endpoints put pagination in `meta`. Errors: `status:"error"`, `data:null` (optional
  diagnostics ride inside `data`), message carries the reason.

## Auth / RBAC

- JWT HS256 issued by audit-log; `TokenPayload` requires `id, email, role, exp, type`.
- Gate writes with `Depends(require_roles([...]))`, reads with `get_current_user`.
  Roles: `developer | qa | clinical_expert | ra | admin`. Lock/finality actions are
  admin-only; approvals validate signer employment.

## Data access

- Own tables: service ORM models (re-exported from `regops_shared.models`).
- **Other services' tables: raw SQL via `sqlalchemy.text()`** — never import a foreign ORM
  model onto this service's `Base`. Batch lookups with `= ANY(:ids)`.
- `auto_answer()`-style helpers `flush()` but never `commit()` — the caller commits.

## Errors & logging

- Specific exception types only (never bare `except:`); log with ids/inputs/operation context.
- Raise `HTTPException` with actionable messages; health check at `GET /health`.
- No magic literals — constants in `shared/regops_shared/` or the service's `app/commons/constants.py`.

## Celery

- One queue per service (queue name = service folder name). Cross-service dispatch **by task
  name** via `send_task("svc.task_name", args=[...], queue="svc")` — never import another
  service's task graph.
- Long work: API returns `202 {id, task_id}` immediately; the worker commits incrementally so
  progress is visible and the task is resumable/idempotent (skip already-done rows on retry).

## LLM seam

- `regops_shared.llm.get_llm_client()` — provider from `settings.llm_provider`
  (`ollama` | `claude`); embeddings are **always** Ollama `nomic-embed-text` (768-dim, fixed).
- Service-local overrides (e.g. `TESTGEN_LLM_PROVIDER`) must not touch the global provider.
- Record provenance (`llm_provider` / `llm_model`) on any row an LLM produced.

## Dev loop

Code is bind-mounted: `docker compose restart <svc>` (and `<svc>-worker`) to reload; check
`docker compose logs <svc> --tail=30` for startup errors.
