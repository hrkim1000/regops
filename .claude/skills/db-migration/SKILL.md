---
name: db-migration
description: Use when adding or changing database schema — Alembic migration conventions, shared ORM models as the single source of truth, regops_schema.sql maintenance, and how to apply/verify against the Docker stack.
---

# Database Migrations

## Rules

1. **Shared models are canonical.** Every table's ORM model lives in
   `shared/regops_shared/models/`; a service that owns the table re-exports it
   (`from regops_shared.models.x import *`). Never define a second model for the same table.
2. **One migration history** in `shared/alembic/versions/`, sequentially numbered
   `000N_<slug>.py` (`revision="000N"`, `down_revision="000N-1"`). Check the current head
   before numbering.
3. **Fresh-DB safe + idempotent.** The baseline builds the schema via `create_all` from the
   models, so structural migrations use `IF NOT EXISTS` / `IF EXISTS` — they must no-op on a
   fresh DB and apply cleanly on the live one. Additive preferred; no back-compat backfill
   unless the plan calls for it.
4. **Update `shared/alembic/regops_schema.sql`** (the authoritative dump) in the same change —
   edit the affected CREATE TABLE block to match, or regenerate via a targeted `pg_dump` splice.
5. **Cross-service references are plain `Uuid` columns** — DB-level FK in the migration if
   needed, but **no ORM `ForeignKey` to another service's table** (SQLAlchemy can't resolve it
   on this service's metadata at runtime).

## Apply & verify (dev stack)

```bash
docker compose run --rm migrate            # one-shot: alembic upgrade head, then exits
# verify head + columns:
docker compose exec -T <any-service> python -c "..."   # raw SQL against information_schema
docker compose restart <owning-service> <owning-service>-worker
```

## Checklist

- [ ] Model updated in `shared/regops_shared/models/` (+ service re-export if new)
- [ ] Migration `000N` written (docstring: what + why + fresh-DB note), head bumped
- [ ] `regops_schema.sql` matches
- [ ] `docker compose run --rm migrate` applied; columns verified via information_schema
- [ ] Owning service + worker restarted; affected tests green
