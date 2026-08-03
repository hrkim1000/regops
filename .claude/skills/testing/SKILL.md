---
name: testing
description: Use when writing or running tests — the testing pyramid, per-layer conventions (mock LLM in unit, real stack in integration, Playwright E2E), coverage targets, and the exact commands.
---

# Testing Strategy

> **Target conventions — no code or compose stack exists yet** (greenfield, [ADR-0001](../../../docs/design/ADR-0001-platform-foundation.md)).

## Pyramid & targets

| Layer | Share | Coverage | Runs against |
| --- | --- | --- | --- |
| Unit | 70% | ≥80% | mocks only — no network/DB; patch the LLM client (`_get_ollama_client` / `get_llm_client`) |
| Integration | 20% | ≥70% | real Postgres + Redis + Celery via Docker Compose; RBAC exercised |
| E2E | 10% | critical paths | Playwright (frontend); staging-like env |

Security tests: OWASP Top 10 · API tests: all endpoints.

## Conventions

- Suites split `tests/unit/` · `tests/integration/` · `tests/e2e/` per service.
- Unit: validate parsers/validators/pure helpers in isolation; use recorded source fixtures per
  cell rather than live fetches; never call a real LLM.
- Integration: verify the pipeline through the DB — fetch → WORM archive → parse → clause diff →
  change event; assert an unchanged re-fetch records a `fetch_observation` and creates **no** new
  version. Callers of helpers that only `flush()` must `await db.commit()`.
- E2E: change detection → alert routing, and question → retrieval → cited answer. Include the
  **"needs verification"** path (no citation available) and a superseded-citation re-verification.

## Non-negotiable test cases

These encode invariants that are cheaper to catch in CI than in an audit:

- **Tier D**: no standard body text anywhere in the archive or index; `StandardReference` rows
  resolve to a link. A fixture that tries to store standard text must fail.
- **Citation immutability**: an answer's stored citation still resolves to the same clause text
  after the document is amended; the citation is flagged superseded, not rewritten.
- **Cell isolation**: a change event fans out to every claiming cell (FD&C Act → both `fda_samd`
  and `fda_cosmetic`) and to no others.
- **Renumbering**: a renumbered-but-unchanged clause reports `renumbered`, never delete+add.
- **Cross-domain**: the same parse → clause pipeline handles a SaMD and a Cosmetic fixture with no
  domain-specific branch before IR extraction (the ADR-0002 architecture bet).

## Commands

```bash
# services (inside the compose stack)
docker compose exec -T <svc> python -m pytest tests/unit -q

# integration: a separate database, selected by REGOPS_DB_NAME.
# NOT by DATABASE_URL in .env.test — compose sets it under `environment:`, which wins over
# `env_file:`, so a DATABASE_URL there is silently ignored.
REGOPS_DB_NAME=regops_test docker compose run --rm migrate          # once, to head
STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm <svc> \
    python -m pytest tests/integration -q

# frontend (from frontend/)
npm run typecheck && npm run lint
npm run e2e            # Playwright (e2e:ui for the interactive runner)
```

## Quality gates

All tests pass before merge · coverage never decreases · no critical vulns · API < 200 ms.
Report failures verbatim — never paper over a red test.

Regression on the **golden query set** is a release gate, scored per domain (SaMD and Cosmetic sets
are separate) and per gated cell. Citation accuracy and hallucination rate are measured there, not
inferred from unit coverage.
