# RegOps AI Platform

**An AI knowledge layer that keeps life sciences companies ahead of every regulatory change, with the source citation attached**


A citation-traceable knowledge layer that turns fragmented medical device, and cosmetic regulations into monitored change alerts, sourced answers, and mapped compliance gaps.

## tag : Regulation, made queryable

## Architecture


## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js · React · TypeScript · Tailwind CSS |
| Backend | FastAPI · Python 3.12 · `regops_shared` library |
| Database | PostgreSQL (single DB, Alembic migrations) |
| Vector search | pgvector · `nomic-embed-text` 768-dim HNSW *(built — phase 3: `regulation_embeddings` migration 0011; Regulation Search + grounded Q&A)* |
| Queue | Redis · Celery (per-domain queues) |
| Storage | MinIO (local) / S3 (cloud) |
| LLM (generation) | Ollama (dev) / Anthropic Claude (test) — pluggable |
| LLM (embeddings) | Ollama · `nomic-embed-text` |
| Auth | JWT · RBAC — shipped roles `qa` / `ra` / `admin` (ADR-0005); `developer` / `clinical_expert` are platform-phase targets |

---

## Quick start

```bash
# 1. Copy env template
cp .env.example .env.dev

# 2. Start infrastructure (db, redis, minio, pgadmin, flower)
STAGE=dev docker compose up -d

# 3. Optional: run Ollama inside Docker
STAGE=dev docker compose --profile local-llm up -d

# 4. Start the app layer (platform-core, regulation + worker, migrate, frontend)
STAGE=dev docker compose --profile app up -d
```


**Monitoring**: Flower `:15555` · pgAdmin `:15051` · MinIO console `:19001`.

---

## Documentation

Core docs live under [docs/](docs/)

| Doc | Description |
|---|---|
| [docs/RegOps.md](docs/RegOps.md) | Platform architecture, phased roadmap, metrics, and decision requests |
| [docs/development-plan.md](docs/development-plan.md) | Execution-oriented development plan with workstreams, milestones, and quality gates |
| [docs/executive-summary.md](docs/executive-summary.md) | 1-page leadership summary for funding and stage-gate decisions |

---

## Regulatory standards

| Standard | Coverage |
|---|---|
| **IEC 62304** | SaMD lifecycle, change control, problem resolution, Safety Class A/B/C |
| **ISO 14971** | Risk management — hazards, harms, risk controls, SOUP risk |
| **ISO 13485** | QMS — SOP, training, CAPA, change control, DHF |
| **MFDS GMP** | GMP checklist, submission readiness, two-approver gate for Safety Class B/C |
| **FDA** | 510(k), PCCP (future expansion) |

---

## RBAC roles

Shipped enum (Phase 1, ADR-0005): `qa` | `ra` | `admin`.

| Role | Key permissions |
|---|---|
| `ra` | IR review/edit, Lock, amend, publish — the write gates |
| `admin` | Everything `ra` can, plus settings, prompt overrides, user management |

---

## License

Private / proprietary. All rights reserved.
