---
name: testing
description: Use when writing or running tests — the testing pyramid, per-layer conventions (mock LLM in unit, real stack in integration, Playwright E2E), coverage targets, and the exact commands.
---

# Testing Strategy

## Pyramid & targets

| Layer | Share | Coverage | Runs against |
| --- | --- | --- | --- |
| Unit | 70% | ≥80% | mocks only — no network/DB; patch the LLM client (`_get_ollama_client` / `get_llm_client`) |
| Integration | 20% | ≥70% | real Postgres + Redis + Celery via Docker Compose; RBAC exercised |
| E2E | 10% | critical paths | Playwright (frontend); staging-like env |

Security tests: OWASP Top 10 · API tests: all endpoints.

## Conventions

- Suites split `tests/unit/` · `tests/integration/` · `tests/e2e/` per service.
- Unit: validate agents/validators/pure helpers in isolation; mock GitLab webhook/release
  payloads for the git-agent; never call a real LLM.
- Integration: verify the cross-service pipelines through the DB (e.g. release poll →
  SW Profile DB → staleness re-evaluation); remember callers of `auto_answer()` must
  `await db.commit()`.
- E2E: checklist derivation → auto-answer → generation → per-section signoff → package;
  include signer-employment (403) and flagged-section gating.

## Commands

```bash
# services (inside the compose stack)
docker compose exec -T <svc> python -m pytest tests/unit -q
docker compose exec -T <svc> python -m pytest tests/integration -q   # stack must be up

# frontend (from frontend/)
npm run typecheck && npm run lint
npm run e2e            # Playwright (e2e:ui for the interactive runner)
```

## Quality gates

All tests pass before merge · coverage never decreases · no critical vulns ·
API < 200 ms, webhook response < 1 s. Report failures verbatim — never paper over a red test.
