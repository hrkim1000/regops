# Local Development — Ports and Access

Where every local service lives and **where its credential comes from**. Values are not restated
here: `docs/**` is published to the shared `startup` repository (CLAUDE.md § Doc sync), and a
credential written into a published document cannot be unpublished. Every entry below names the
file that holds the value instead.

Run `python scripts/local_access.py` for the filled-in table. It reads the same sources this page
names — so it cannot drift from them — and prints to your terminal rather than writing a file that
would later be committed by accident.

---

## Ports

The `2xxxx` block is deliberate — RegOps runs alongside another local stack without colliding
(phase 0 deviation 4). Ollama is the one exception: a single host-native instance is shared.

| Surface | URL | Profile |
|---|---|---|
| **frontend** | <http://localhost:23000> | `app` |
| platform-core | <http://localhost:28000> | `app` |
| regulation | <http://localhost:28001> | `app` |
| monitoring | <http://localhost:28002> | `app` |
| assistant | <http://localhost:28003> | `app` |
| PostgreSQL | `localhost:25432` | always |
| Redis | `localhost:26379` | always |
| MinIO API / console | `localhost:29000` / <http://localhost:29001> | always |
| pgAdmin | <http://localhost:25051> | always |
| Flower | <http://localhost:25555> | always |
| Ollama | `localhost:11434` | `local-llm` (or host-native) |

```bash
docker compose --profile app up -d          # everything
docker compose ps                            # what is actually running
docker compose logs frontend --tail=30       # when a surface does not answer
```

## Where each credential comes from

| Surface | Identity | Source of truth |
|---|---|---|
| **frontend login** | an application user in `users` | seeded by `scripts/seed_user.py` at any role, from `REGOPS_SEED_EMAIL` / `REGOPS_SEED_PASSWORD` / `REGOPS_SEED_ROLE` (`REGOPS_ADMIN_*` still works and implies `admin`). The four dev accounts (`admin`, two `ra`, `viewer`) are asserted by `services/platform-core/tests/integration/test_phase0_acceptance.py`, which is where their fixtures live |
| **Playwright E2E** | `e2e-ra@example.com` (`ra`) + the existing `viewer` | seeded the same way, then exported as `REGOPS_E2E_RA_PASSWORD` / `REGOPS_E2E_VIEWER_PASSWORD` — the suite reads them from the environment and refuses to start without them, so **no password reaches the repository**. The `ra` half is the suite's own principal rather than a person's account, because assigning an alert owner is written to the audit chain and the chain should say an automated run did it ([frontend/e2e/README.md](../frontend/e2e/README.md)) |
| **MinIO console** | root user | `docker-compose.yml` → `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`, with local defaults inline. The same two variables drive the **server** and every **service client**, so they cannot drift apart |
| **pgAdmin** | login | `docker-compose.yml` → `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_PASSWORD` |
| **PostgreSQL (owner)** | `regops` | `docker-compose.yml` → `POSTGRES_PASSWORD`. Migrations connect as this role |
| **국가법령정보 OPEN API** | account `OC` | `.env.dev` → `LAW_GO_KR_OC`, read through `Settings.law_go_kr_oc`. Self-designated and passed in the query string; the API **echoes it back inside response bodies**, so it is in `source_credentials` and the WORM archive refuses any payload containing it |
| **govinfo (api.data.gov)** | issued key | `.env.dev` → `GOVINFO_API_KEY`, read through `Settings.govinfo_api_key`. Free from <https://api.data.gov/signup/>, one key across every api.data.gov service. `DEMO_KEY` works at 10 requests/hour — enough to probe, not to ingest |
| **PostgreSQL (app)** | `regops_app` | `REGOPS_APP_DB_PASSWORD`. Services connect as this least-privilege role — it holds no `UPDATE`/`DELETE` on `audit_log` ([ADR-0011](design/ADR-0011-audit-trail-immutability.md)) |
| **국가법령정보 API** | `OC` query parameter | `.env.dev` → `LAW_GO_KR_OC`. **The only real secret in the list** |
| Flower | none | unauthenticated; local only |

### The two mechanisms, and why they are not interchangeable

Compose reads variables from **two independent places**, and mixing them up is what produced two
defects in phase 1.0:

- **`environment:` in `docker-compose.yml`** interpolates `${VAR}` from your **shell or the
  project-root `.env`** — never from `.env.dev`/`.env.test`. It also **wins over `env_file:`**.
- **`env_file: .env.${STAGE}`** is injected into the container and supplies everything the
  `environment:` block does not pin.

So a `DATABASE_URL` or `MINIO_SECRET_KEY` written into `.env.test` is silently ignored, because
compose pins both. Anything else there — `JWT_SECRET`, `LLM_*`, `LAW_GO_KR_OC` — does take effect.

Select the test database with its own knob rather than fighting that precedence:

```bash
REGOPS_DB_NAME=regops_test docker compose run --rm migrate          # once, to head
STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation \
    python -m pytest tests/integration -q
```

The `migrate` service reads the same knob, so the test database is migrated with the same command
that migrates the development one. It did not always — the DSN was hard-coded to `regops` until
phase 1.3, so that first line silently re-migrated development and left the test database behind.

## The database image is pgvector's, not stock postgres

`db` runs `pgvector/pgvector:pg16` rather than `postgres:16-alpine`, because phase 1.3 stores clause
embeddings and `CREATE EXTENSION vector` needs the extension present in the image. Same PostgreSQL
major version, same data directory — but Debian/glibc where the old image was Alpine/musl, and the
two collate text differently. Migration 0005 reindexes every table once and refreshes the collation
version for exactly that reason; if you are restoring an older volume by hand, do the same.

## Changing a credential

| Want to change | Do this |
|---|---|
| MinIO / pgAdmin / Postgres password | set the variable in your **shell or project-root `.env`**, then `docker compose down -v` — existing volumes were initialised with the old value and will not re-read it |
| App login password | `REGOPS_RESET_EMAIL=… REGOPS_RESET_PASSWORD=… docker compose exec -T platform-core python /scripts/reset_password.py`. `seed_user.py` deliberately **will not** reset a password — re-running a seeder must not be able to rotate a credential as a side effect — and `platform-core` exposes no change-password endpoint, so this script is the only path. **Do not delete and re-seed the user instead:** the id is referenced by `queries.asked_by`, `irs.locked_by`, `alerts.owner_id` and every `audit_log` row naming them as actor, and a new id orphans all of it |
| Add a user at a given role | `REGOPS_SEED_EMAIL=… REGOPS_SEED_PASSWORD=… REGOPS_SEED_ROLE=viewer\|ra\|admin docker compose exec -T platform-core python /scripts/seed_user.py`. Idempotent; exits non-zero if the email exists at a different role |
| `LAW_GO_KR_OC` | edit `.env.dev` and restart `regulation`. The account is authorised by **egress IP**, so a network change breaks it too — that failure returns HTTP 200 with an error body and is filed as an `auth_failure` drift alert |

## pgAdmin — connecting to the database

> **The host is `db`, not `localhost`.** pgAdmin runs *inside* the compose network, so it resolves
> the service name. `localhost:25432` is the **host-side** port mapping and is unreachable from
> within the container — entering it is the usual reason a manual registration fails with
> "connection refused".

Three connections are pre-registered from `infra/pgadmin/servers.json`, so normally there is
nothing to set up: open <http://localhost:25051>, expand the **RegOps** group, click a server, and
enter the password when prompted.

| Registered server | Database | Role | Use it for |
|---|---|---|---|
| RegOps dev (regops) | `regops` | `regops` (owner) | everyday inspection; full read/write |
| RegOps test (regops_test) | `regops_test` | `regops` (owner) | the integration database — truncated and rewritten by tests, so keep no work here |
| RegOps dev (regops_app, least privilege) | `regops` | `regops_app` | what the services actually connect as |

The third exists to be *tried*, not just documented. Connected as `regops_app`, an
`UPDATE audit_log …` is refused — that is [ADR-0011](design/ADR-0011-audit-trail-immutability.md)'s
append-only guarantee holding at the database rather than by convention. As `regops` the same
statement succeeds, because a table owner bypasses its own grants; that is exactly why services do
not connect as the owner.

### If the servers are not listed

The import runs when pgAdmin initialises its config volume. A volume created before this file
existed will not have them:

```bash
docker compose stop pgadmin && docker compose rm -f pgadmin
docker volume rm regops_regops_pgadmindata     # discards saved pgAdmin state only
docker compose up -d pgadmin
```

### Registering by hand

Right-click **Servers → Register → Server**:

| Tab | Field | Value |
|---|---|---|
| General | Name | anything |
| Connection | Host name/address | **`db`** |
| Connection | Port | **`5432`** — the in-network port, not 25432 |
| Connection | Maintenance database | `regops` (or `regops_test`) |
| Connection | Username | `regops`, or `regops_app` for the least-privilege view |
| Connection | Password | see *Where each credential comes from* above |

### Worth knowing once connected

- **`regops` and `regops_test` are separate databases on one server.** The test suite truncates
  `regops_test`; if a query returns nothing unexpectedly, check which one is selected.
- **Annexes are rows in `documents`**, not a sub-table — a 고시 with four 별표 is five rows
  ([ADR-0012](design/ADR-0012-annex-version-identity.md)). Filter `parent_document_id is null` for
  instruments only.
- **`document_versions.raw_object_key` is a MinIO key, not a path on disk.** The bytes live in the
  `regops-archive` bucket; the database only points at them.

## Security notes

- **Everything except `LAW_GO_KR_OC` is a local-dev default.** They are committed in
  `docker-compose.yml` with that stated, and must not be reused anywhere but a developer machine.
- **`.env*` is never committed** except `.env.example`, enforced by a CI check. The `guard_env`
  hook additionally blocks the agent from writing any `.env.*` file at all.
- **The archive refuses to store a credential.** 국가법령정보 echoes the `OC` key back inside 목록
  responses, so `archive_bytes` rejects any payload containing a configured source credential —
  a credential in the WORM archive could never be removed ([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 13).
- **This page names sources, not values,** because it is published to the shared `startup`
  repository. Keep it that way.
