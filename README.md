# RegOps

**AI-powered Regulatory platform for SaMD and Cosmetic Product**

A citation-traceable knowledge layer that turns fragmented SaMD and cosmetic regulations into
monitored change alerts, sourced answers, and mapped compliance gaps — with the source citation
attached to every claim.

> In the regulatory space, AI competes on **verifiability**, not generation quality.
> No answer without evidence: when a clause-level citation cannot be produced, the answer is
> returned as *"needs verification."*

---

## What it does

| Pillar | What the platform automates |
|---|---|
| **Change monitoring** | Collect and normalize authority source texts → clause-level diffs → route to affected owners. Daily change briefing, impact grading, owner-assigned tickets |
| **Q&A / RAG assistant** | Natural-language queries answered with the supporting clause, document version, and effective date. Deep links to source text, full query audit trail |
| **Gap analysis** | Decompose obligations into structured requirements → map to internal SOPs and controls → derive impact scope on amendment. IR-to-control matrix, gap report, corrective actions |
| **SaaS productization** | The same knowledge layer deployed multi-tenant — tenant isolation, validation package, partner API |

---

## Scope

**Two product domains × four regulatory regions.** Everything else is explicitly out of scope —
not "later," but not modeled at all until the scope decision is revisited.

| Domain | MFDS (Korea) | FDA (US) | EU (EC) | NMPA (China) |
|---|---|---|---|---|
| **SaMD** | ● gated PoC | Phase 2 | ○ spike | Phase 2 |
| **Cosmetic** | ● gated PoC | Phase 2 | Phase 2 | Phase 2 |

● gated PoC cell · ○ non-gated spike

Out of scope: pharmaceuticals and biologics, hardware-only devices, food and supplements; every
authority outside the four above (PMDA, Health Canada, MHRA, TGA, ASEAN ACD, EMA drug procedures).

The authoritative per-cell inventory of laws, guidance, and source URLs is
[docs/import-source-map.md](docs/import-source-map.md) — the single source catalog.

---

## Architecture

**Five layers, ingestion to applications** — see [docs/RegOps.md](docs/RegOps.md) for the full spec
and [docs/design/](docs/design/) for the ADRs.

```text
L1 Ingestion      Tier A/B/C → fetch → sha256 → WORM archive (immutable)
                  Tier D  ✕  never ingested — recognition record + deep link only
L2 Normalization  parse → clause segmentation → DocumentVersion → ClauseDiff → ChangeEvent
L3 Knowledge graph  clause · IR · concept · cross-reference · product · control
L4 Retrieval      hybrid search → graph expansion → citation-enforced generation
                  → evidence verification → confidence score
L5 Applications   monitoring · Q&A · gap analysis · multi-tenant portal
```

Services follow the product pillars and arrive by phase
([ADR-0009](docs/design/ADR-0009-service-boundaries-per-pillar.md)):

| Service | Phase | Role |
|---|---|---|
| `platform-core` | 1 | Identity, roles, sessions, audit trail |
| `regulation` | 1 | L1–L3 — ingest, parse, version, diff, change events, IR extraction |
| `monitoring` | 1 | Subscription matching, impact grading, alert delivery |
| `assistant` | 1 | Retrieval, citation-enforced generation, evidence verification |
| `frontend` | 1 | Next.js / React / TypeScript |
| `compliance` | 2 | Applicability, control mapping, gap findings |
| `tenancy` | 3 | Provisioning, billing, partner gateway |

Everything that writes the clause store is `regulation`; `monitoring` begins where writing ends,
reading `change_events` one-way.

### Agents, pipelines, and shared

A service is composed of these three, and none is a deployment boundary
([ADR-0008](docs/design/ADR-0008-service-composition.md)). An **agent** invokes an LLM, records
`llm_provider`/`llm_model`, and cannot be trusted without a separate gate — everything else is a
deterministic **pipeline**.

| Phase 1 agents | Gate |
|---|---|
| Requirement Extraction (`regulation`) | human lock by an `ra` — only locked IRs flow downstream |
| Reasoning (`assistant`) | evidence-verification agent, then confidence score |
| Evidence verification (`assistant`) | the gate itself — can fail an answer |

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js · React · TypeScript · Tailwind CSS |
| Backend | FastAPI · Python 3.12 · `regops_shared` library |
| Database | PostgreSQL (single DB, Alembic migrations) |
| Vector search | pgvector · `nomic-embed-text` 768-dim HNSW cosine |
| Queue | Redis · Celery (one queue per service) |
| Storage | MinIO (local) / S3 (cloud) — content-addressed WORM archive |
| LLM (generation) | Ollama (dev) / Anthropic Claude (test) — pluggable behind `get_llm_client()` |
| LLM (embeddings) | Ollama · `nomic-embed-text` — pinned regardless of generation provider |
| Auth | JWT · RBAC (`viewer` / `ra` / `admin`) |

---

## Quick start

> Phase 0 is built: the stack comes up, migrations apply, and login works end to end.
> Regulation logic starts at [phase1.0](docs/plan/phase1.0_ingestion.md).

```bash
# 1. Copy the env template and fill in real values
cp .env.example .env.dev

# 2. Start infrastructure (db, redis, minio, pgadmin, flower)
STAGE=dev docker compose up -d

# 3. Apply migrations — seeds the 8 cells, sets up the append-only audit trail
docker compose run --rm migrate

# 4. Start the services
STAGE=dev docker compose --profile app up -d

# 5. Optional: run Ollama inside Docker instead of natively
STAGE=dev docker compose --profile local-llm up -d
```

**Monitoring**: Flower `:25555` · pgAdmin `:25051` · MinIO console `:29001`.
**Services**: platform-core `:28000` · regulation `:28001` · monitoring `:28002` · assistant `:28003`.

---

## Documentation

| Doc | Description |
|---|---|
| [docs/RegOps.md](docs/RegOps.md) | Platform architecture, scope, data tiers, phased roadmap, metrics |
| [docs/import-source-map.md](docs/import-source-map.md) | **Single source catalog** — per-cell laws, guidance, and source URLs |
| [docs/import-agent.md](docs/import-agent.md) | Import Agent spec — how sources are fetched, normalized, parsed |
| [docs/local-development.md](docs/local-development.md) | **Local ports and where each credential comes from** |
| [docs/development-plan.md](docs/development-plan.md) | Execution plan — workstreams, milestones, quality gates |
| [docs/plan/README.md](docs/plan/README.md) | **Phase plan** — one build file per phase (`phase0` … `phase3.0`), with the critical path |
| [docs/eval/README.md](docs/eval/README.md) | **Evaluation corpus** — golden sets, ground-truth markup, and the rules that make a gate number defensible |
| [docs/executive-summary.md](docs/executive-summary.md) | 1-page leadership summary for stage-gate decisions |
| [docs/regulation-library-structure.md](docs/regulation-library-structure.md) | Per-cell library layout |

### Architecture Decision Records

| ADR | Decision |
|---|---|
| [ADR-0001](docs/design/ADR-0001-platform-foundation.md) | Platform foundation — greenfield, what does not carry over |
| [ADR-0002](docs/design/ADR-0002-canonical-regulation-model.md) | Canonical regulation data model — Document, Version, Clause, Citation |
| [ADR-0003](docs/design/ADR-0003-ingestion-and-change-detection.md) | Ingestion and change detection |
| [ADR-0004](docs/design/ADR-0004-ir-extraction-and-domain-branching.md) | IR extraction and domain branching |
| [ADR-0005](docs/design/ADR-0005-service-architecture.md) | Service architecture, tenancy split, RBAC roles |
| [ADR-0006](docs/design/ADR-0006-retrieval-and-citation-enforced-generation.md) | Retrieval and citation-enforced generation |
| [ADR-0007](docs/design/ADR-0007-context-map-and-applicability.md) | Context map and applicability |
| [ADR-0008](docs/design/ADR-0008-service-composition.md) | Service composition — agents, pipelines, shared |
| [ADR-0009](docs/design/ADR-0009-service-boundaries-per-pillar.md) | Service boundaries per pillar, phased |
| [ADR-0010](docs/design/ADR-0010-semantic-enrichment-and-graph-model.md) | Semantic enrichment and the knowledge graph model |
| [ADR-0011](docs/design/ADR-0011-audit-trail-immutability.md) | Audit-trail immutability — grants plus hash chain |
| [ADR-0012](docs/design/ADR-0012-annex-version-identity.md) | Annexes are child Documents, not attachments on a version |
| [ADR-0013](docs/design/ADR-0013-unresolvable-effective-dates.md) | An unresolvable effective date is null plus the raw phrase |
| [ADR-0014](docs/design/ADR-0014-annex-row-granularity.md) | Annex table rows are Clauses; there is no `annex_rows` table |
| [ADR-0015](docs/design/ADR-0015-diff-stage-boundary.md) | Diff is its own stage, dispatched by task name |
| [ADR-0016](docs/design/ADR-0016-pending-effect-versions.md) | 시행예정 versions: MST is the version, staged dates are not clause-level |
| [ADR-0017](docs/design/ADR-0017-extraction-determinism-and-conditional-obligations.md) | Extraction determinism, and conditional obligations stay one IR |

---

## Data strategy

Sources fall into four tiers, and the last tier is never crossed.

| Tier | Category | Constraint |
|---|---|---|
| **A** | Public APIs — openFDA, Federal Register, Regulations.gov, 국가법령정보 OPEN API | Collectable immediately; most of openFDA is CC0 |
| **B** | Static files / RSS — EUR-Lex, CosIng, EU Safety Gate, MFDS RSS | License terms checked individually |
| **C** | Scraping — FDA guidance DB, warning letters, EUDAMED, NMPA notices, IECIC | Structure-change detection and recovery pipeline mandatory |
| **D** | **Copyright-protected — source text collection prohibited** | ISO 13485/14971, IEC 62304/60601/62366, ISO 27001, USP-NF, Ph.Eur. |

**Tier D is the product boundary.** ISO explicitly prohibits use of standard content for AI
training, so RegOps stores only the recognition record — number, edition, recognition number,
effective and withdrawal dates, harmonized status — and deep-links the official copy. This holds
even where a regulation makes the standard legally binding: cite the requirement, link the standard,
store neither.

> Stating what we do **not** collect is not a limitation but a basis for trust — regulated customers
> buy only when it can be written into the contract.

---

## RBAC roles

Phase 1 enum ([ADR-0005](docs/design/ADR-0005-service-architecture.md) decision 5):
`viewer` | `ra` | `admin`. `compliance` arrives in Phase 2 with gap analysis.

| Role | Key permissions |
|---|---|
| `viewer` | Read alerts, answers, citations; run queries |
| `ra` | Everything `viewer` can, plus **lock IRs**, adjudicate structure-drift alerts, confirm control-mapping carry-forward, sign ground-truth markup |
| `admin` | Everything `ra` can, plus users, settings, prompt and model configuration |

The restricted actions are the ones where a human assertion enters the audit trail.

---

## License

Private / proprietary. All rights reserved.

---

## Status

Build state by workstream. Update the **State** column as work lands — keep it in sync with
[docs/development-plan.md](docs/development-plan.md).

| Component | Reference | State |
|---|---|---|
| Scope, data tiers, roadmap | [docs/RegOps.md](docs/RegOps.md) | 🟢 settled |
| Source catalog — 8 cells | [docs/import-source-map.md](docs/import-source-map.md) | 🟢 settled |
| MFDS source reconnaissance | [spike-2026-07-29](docs/design/spike-2026-07-29-mfds-source-recon.md) | 🟢 done — live API verified |
| Service-boundary decisions | [brief-2026-08-05](docs/design/decision-2026-08-05-lapsed-service-boundaries.md) | 🟢 both taken — `assistant` split retained (2026-08-05); `monitoring` stays its own service (2026-08-11, at the W7 deadline) |
| Architecture decisions | [ADR-0001 – ADR-0017](docs/design/) | 🟢 complete for Phase 1 — 0001, 0004, 0006 and 0012–0017 accepted; the rest proposed |
| Phase plan — 13 build files | [docs/plan/README.md](docs/plan/README.md) | 🟢 settled |
| Foundation — stack, shared lib, platform-core, audit chain | [phase0](docs/plan/phase0_foundation.md) | 🟢 done |
| Ingestion — MFDS SaMD + Cosmetic | [phase1.0](docs/plan/phase1.0_ingestion.md) | 🟢 done (2026-08-05) — 20 sources live, 8/8 acceptance |
| Normalization — clause schema, diff | [phase1.1](docs/plan/phase1.1_normalization.md) | 🟢 done (2026-08-06) — 25,729 clauses over 526 documents, 9/9 acceptance, both falsifiers not triggered |
| IR extraction | [phase1.2](docs/plan/phase1.2_ir_extraction.md) | 🟢 done (2026-08-07) — 7/7 acceptance; extraction is triggered, not chained off parse |
| Retrieval + citation-enforced Q&A | [phase1.3](docs/plan/phase1.3_retrieval_qa.md) | 🟢 done (2026-08-11) — 9/9 acceptance; hybrid retrieval, generation constrained to what retrieval returned, verification able to fail an answer |
| Monitoring + alert routing | [phase1.4](docs/plan/phase1.4_monitoring.md) | 🟢 done (2026-08-11) — 6/6 acceptance; 109 change events → 7 alerts, 100% detection coverage on both gated cells |
| Frontend — dashboard, Q&A workbench | [phase1.5](docs/plan/phase1.5_frontend.md) | 🟢 done (2026-08-14) — regulation browser · clause view · IR review + lock · 제출 서류 · Q&A workbench · monitoring dashboard · **Playwright E2E, 10 tests green against the live stack and the real model**; the usability review is **미측정**, it needs pilot users |
| Evaluation + pilot — the 6 gates | [phase1.6](docs/plan/phase1.6_evaluation.md) | 🟡 harness + golden sets built (2026-08-13) — 162 items per gated cell over six axes, seeded and **not yet RA-signed**; 2 of 6 gates machine-measurable, the other 4 reported **미측정** with reasons pending an RA and a pilot |
| Tier C + remaining 6 cells | [phase2.0](docs/plan/phase2.0_tier_c_scale.md) | ⬜ Phase 2 |
| Semantic enrichment + graph | [phase2.1](docs/plan/phase2.1_semantic_graph.md) | ⬜ Phase 2 |
| Compliance — applicability, gap analysis | [phase2.2](docs/plan/phase2.2_compliance.md) | ⬜ Phase 2 |
| External SaaS — tenancy, validation | [phase3.0](docs/plan/phase3.0_saas.md) | ⬜ Phase 3 |

> Legend: 🟢 done / settled · 🟡 partial · ⬜ planned.
>
> **The ADRs are the contract the code is built against**, not a description written after it
> ([ADR-0001](docs/design/ADR-0001-platform-foundation.md) — RegOps is greenfield). Where a row above
> is not 🟢, the ADR says what to build rather than what runs.
>
> **Phase 1 gates** — the PoC produces numbers, not a demo. Detection coverage ≥95% · detection
> latency ≤24h · citation accuracy ≥90% · hallucination rate ≤2% · research time savings ≥30% ·
> pilot retention ≥60%. No-Go if four or more of the six fall short.
