# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**RegOps** — AI-powered Regulatory platform for SaMD and Cosmetic Product. A citation-traceable
knowledge layer that turns fragmented SaMD and cosmetic regulations into monitored change alerts,
sourced answers, and mapped compliance gaps.

This file is the **constitution**: always-loaded invariants — scope, architecture rules, service
boundaries. Task-specific *procedures* live in `.claude/skills/` and are auto-invoked on demand:
[db-migration](.claude/skills/db-migration/SKILL.md) ·
[frontend-page](.claude/skills/frontend-page/SKILL.md) ·
[glossary](.claude/skills/glossary/SKILL.md) ·
[release-and-commit](.claude/skills/release-and-commit/SKILL.md) ·
[service-endpoint](.claude/skills/service-endpoint/SKILL.md) ·
[testing](.claude/skills/testing/SKILL.md).
Guardrails are in `.claude/settings.json` hooks; delegation in `.claude/agents/`.

## Code Style Guidelines

- All documentation and code comments must be written in English

## Standard Workflow

1. First think through the problem, read the relevant docs in `docs/` and any existing code, and write a plan using the TodoWrite tool.
2. The plan should have a list of todo items that you can check off as you complete them.
3. Before you begin working, check in with me and I will verify the plan.
4. Then, begin working on the todo items, marking them as complete as you go.
5. Give a high-level explanation of changes at each step.
6. Make every change as simple as possible — smallest possible impact on the codebase.
7. Finally, provide a summary of the changes made.

Commit or push **only when explicitly asked** — with one standing exception: **when a phase slice is
finished, commit it and push to `origin` without asking** (2026-08-11). Every gate green first, and
the phase file, `docs/plan/README.md` and the root `README.md` status rows move in the same commit —
a commit whose docs claim a phase is done while its code is in the next one makes the history lie.

**The `startup` sync follows every `origin` push** (2026-08-21) — same content, whole repository, and
onto the `hrkim` branch only. It used to be a per-occasion ask on the grounds that another account's
repository is a different kind of action from pushing to your own; that is still true of the
*target*, which is why the branch rule and the no-`--force` rule below did not move with it. See
[Repo sync to `startup`](#repo-sync-to-startup).

## Plan Documentation

- Plans live in `docs/plan/`, one file per phase: `phase0_foundation.md` … `phase3.0_saas.md`.
  Start at [docs/plan/README.md](docs/plan/README.md) for the phase map and critical path.
- **The integer part of a plan number is the roadmap phase.** `phase1.3` is the fourth build slice
  of roadmap Phase 1 (months 0–4), so "Phase 2" means months 5–12 everywhere — in RegOps.md, in
  development-plan.md, in every ADR, and in the plan files. There is no second numbering scheme.
- **After completing each step, update the corresponding phase plan file.** Mark items `[x]` and
  record deviations in that file's *Deviations & decisions* section.
- A decision that changes architecture goes in an **ADR**, not a plan file.

## Project Overview

RegOps covers **two product domains × four regulatory regions** and delivers four application
pillars on one shared knowledge layer:

1. Regulatory change monitoring & alerting
2. Regulatory Q&A / RAG assistant (citation-enforced)
3. Compliance gap analysis & control mapping
4. SaaS productization for external customers

**Current state: phase 0 and 1.0 – 1.5 are done; 1.6 is partial.**
The compose stack, `regops_shared`, `platform-core` (auth · RBAC · audit chain) and the `regulation`
L1–L2 pipeline exist and run — ingest → parse → diff → change events → IR, with a clause store of
25,729 clauses over 526 documents of the gated corpus, and draft → locked IRs behind the Requirement
Extraction agent. `assistant` now answers: pgvector index over 조-level passages, hybrid
BM25 + vector retrieval, citation-enforced generation, and an evidence-verification pass that can
fail an answer. `monitoring` routes: cell subscriptions, one alert per amendment with its clause
list, impact grading, delivery with per-attempt retry, a briefing composed on read, and the coverage
and latency metrics the two gates are measured with. The `frontend` carries **both pillar surfaces**:
a read-only regulation browser, the IR review + lock surface, a submission-document view derived from
the clause tree, the Q&A workbench (ask, cited answer, superseded-citation queue), and the monitoring
dashboard (change feed, clause-level old-vs-new diffs, owner assignment, subscriptions, and the two
gate metrics), and a Playwright E2E suite runs both journeys against the live stack and the real
model — 10 tests, invariants rather than model wording, deliberately **not** a CI gate. The one
1.5 acceptance row still open is the pilot usability review, which needs people. `scripts/evaluation`
is the 1.6 harness:
golden sets of 162 items per gated cell across six axes (seeded, **not yet RA-signed**), the blind
markup denominators, a resumable scored run, and the Go/No-Go report. Two of the six gates are
machine-measurable; **the other four are reported as 미측정 with their reasons** — they need a person
or a pilot, and a defaulted gate would move the decision rather than the number.
Architecture is settled through [ADR-0001 – ADR-0017](docs/design/); anything below still marked
*target* describes what to build, not what runs. Read the relevant ADR before writing new code.

Phase 1 (PoC, 4 months) gates two of the eight cells — MFDS SaMD + MFDS Cosmetic — with a
non-gated EU SaMD spike, and ships pillars 1 and 2 only.

## Repo Map

```text
docs/                     # product/strategy docs — the working set
  RegOps.md               # architecture overview — Scope, Data Strategy tiers, 5 layers, roadmap
  import-source-map.md    # SINGLE SOURCE OF TRUTH for per-cell regulation sources (8 cells)
  import-agent.md         # Import Agent spec — how sources are fetched/normalized/parsed
  development-plan.md     # delivery plan, workstreams, stage gates
  local-development.md    # local ports + where each credential lives (values are NOT restated)
  executive-summary.md    # 1-page exec summary
  regulation-library-structure.md   # per-cell library layout example
  design/                 # ADRs — ADR-000N-<slug>.md, numbered from 0001
  plan/                   # build plans, one per phase — phase0 … phase3.0; see plan/README.md
  data/<region>/          # READ-ONLY raw source research (mfds, fda, eu, china, other)
  memo/                   # superseded drafts — never authoritative, may contradict the rules
  reference/              # READ-ONLY, DO NOT CONSULT — parked material
  eval/                   # phase 1.6 evaluation corpus — golden sets, ground-truth markup, gates
```

### Read-only directories

- **`docs/data/`** — raw source research. Consult it for facts; **never edit it.** Corrections
  belong in `import-source-map.md`, which is what connectors are built against. Do not treat
  anything in here as a scope or roadmap statement.
- **`docs/memo/`** — superseded drafts, kept for provenance. **Never cite as authoritative.**
  Contents predate or contradict the current rules; the live statement is in `RegOps.md`,
  `import-source-map.md`, or an ADR. Do not "fix" a memo — supersede it.
- **`docs/reference/`** — parked material. **Do not read it and do not cite it** when answering
  questions or making changes. It is retained for provenance only.

## Architecture rules (non-negotiable)

- **Scope is 8 cells.** Every source, connector, parser profile, and IR belongs to exactly one
  `{authority}_{domain}` cell. `authority` ∈ mfds|fda|eu|nmpa, `domain` ∈ samd|cosmetic.
  No other spellings ("Medical Device", "Device", "MDR"). Nothing outside the 8 cells.

  | Domain | MFDS (Korea) | FDA (US) | EU (EC) | NMPA (China) |
  |---|---|---|---|---|
  | **SaMD** | gated PoC | Phase 2 | spike (non-gated) | Phase 2 |
  | **Cosmetic** | gated PoC | Phase 2 | Phase 2 | Phase 2 |

- **`docs/import-source-map.md` is the only source catalog.** Never create a second list of
  sources in another doc — copy it and one copy silently goes stale. Reference it instead.
- **Tier D is never ingested.** ISO/IEC standards and pharmacopoeias (ISO 13485, ISO 14971,
  IEC 62304, IEC 62366, ISO 27001, USP-NF, Ph.Eur.) prohibit source-text storage and AI
  training. Store only the recognition record — number, edition, recognition number, effective
  and withdrawal dates, harmonized status — and deep-link the official copy. This holds even
  when a regulation makes the standard legally binding (QMSR incorporates ISO 13485:2016 by
  reference): cite the requirement, link the standard, store neither.
- **No answer without evidence.** Generation is citation-enforced: clause-level citation plus
  document version and effective date, or the answer is returned as "needs verification."
  Every generated result passes a separate evidence-verification agent; every answer carries a
  confidence score, and below threshold it routes to human review.
- **Source and version metadata are preserved end to end**, with an immutable (WORM) archive of
  the fetched original and a full audit trail of every retrieval and generation.
- **Login-gated notification portals are not ingestion sources** (EU CPNP, EUDAMED, and the
  like). They are reference-only; do not attach connectors.
- **The knowledge graph is the asset.** LLMs are replaceable and must stay behind a pluggable
  seam; regulation–product–control mapping data is what accumulates value. Pin model versions
  and regression-test against the golden query set before changing them.

## Service Architecture

*Target — [ADR-0009](docs/design/ADR-0009-service-boundaries-per-pillar.md). Services follow the
product pillars and arrive by phase. Boundaries come from ownership and failure isolation, never
from pipeline stages.*

| Service | Phase | Owns |
| --- | --- | --- |
| `platform-core` | 1 | identity, roles, sessions, audit trail |
| `regulation` | 1 | L1–L3 — ingest → parse → version → diff → change event → IR, plus the semantic layer |
| `monitoring` | 1 | subscription matching, impact grading, alert composition and delivery |
| `assistant` | 1 | retrieval, citation-enforced generation, evidence verification |
| `frontend` | 1 | Next.js App Router UI, reaching services via `/api/<svc>/*` rewrites |
| `compliance` | 2 | Product + Compliance contexts — applicability, control mapping, gap findings |
| `tenancy` | 3 | provisioning, billing, API keys, white-label configuration |

Ports are assigned (phase0 deviation 4 — the `2xxxx` block, so RegOps can run alongside another
local stack). Services: platform-core `28000` · regulation `28001` · monitoring `28002` ·
assistant `28003`. Infrastructure: postgres `25432` · redis `26379` · minio `29000`/console `29001` ·
pgAdmin `25051` · flower `25555`. Ollama stays shared on `11434`.

### The seam

Everything that **writes the clause store** is `regulation`. `monitoring` begins where writing
ends, reading `change_events` one-way by raw SQL. Multi-tenancy is cross-cutting — every service is
tenant-aware, so it is never boxed into one service.

`assistant` sits on the same seam from the other side: it **reads** the clause store one-way by raw
SQL and writes only its own tables. `clause_embeddings` references `clauses` and is owned by
`assistant` anyway — coupling the embedding lifecycle to the clause lifecycle would make swapping
the embedding model a `regulation` migration, and the model is the replaceable part.

```text
regulation                                      │  monitoring
  crawl → archive → parse → version → diff      │
    → emit change_event → extract IR            │
                       change_events ───────────┼──>  match · grade · alert
                                                │
  clauses ──────────────────────────────────────┼──>  assistant
                                                │       embed · retrieve · generate · verify
```

### Table ownership

Reads across a boundary are raw SQL; never import another service's ORM model.

```text
platform-core : users · roles · sessions · audit_log
regulation    : cells · sources · source_schedules · fetch_observations
                source_discovery_runs · documents · document_cells
                document_versions · attachments · clauses
                clause_diffs · change_events · structure_drift_alerts
                standard_references · irs · ir_citations · extraction_runs
                ir_standard_citations · clause_classifications
                concepts · concept_labels · concept_relations
                clause_concepts · clause_references · enrichment_runs
monitoring    : alert_subscriptions · alerts · alert_deliveries
assistant     : clause_embeddings · queries · answers · answer_citations
                verification_results
```

**`annex_rows` does not exist and must not be created**
([ADR-0014](docs/design/ADR-0014-annex-row-granularity.md), closing ADR-0006 open question 3). An
annex table row is a `Clause` with `path_segments = [별표N, 표M, 행K]` and its columns in
`clauses.row_columns` (`jsonb`, because every table has a different column set). One store, so
`ir_citations` needs no branch for annexes and nothing has to be kept in sync. Rows are still **not
embedded** and still served by exact match — that is ADR-0006 decisions 1–2, a *retrieval* decision,
unaffected by where rows are stored.

`attachments` is the authority's own file links per version (별표서식파일링크 and the like), kept as
an archival copy and as the fallback for an empty `별표내용`. It is **not** where annex content
lives: annex text arrives inline and becomes a child `Document`.

Regulation data is **shared reference data**; only the mapping layer is tenant-scoped. Tenant-scoped
tables carry `tenant_id` from the first migration ([ADR-0005](docs/design/ADR-0005-service-architecture.md) decision 2).

## Service Composition — agents, pipelines, shared

*[ADR-0008](docs/design/ADR-0008-service-composition.md). A service is composed of these three; none
of them is a deployment boundary.*

| Kind | Determinism | Governed by |
| --- | --- | --- |
| **agent** | non-deterministic — invokes an LLM | records `llm_provider`/`llm_model`; output must pass a gate |
| **pipeline** | deterministic | idempotent, resumable, incremental commit |
| **shared** | no runtime of its own | `regops_shared`; holds contracts, owns no service state |

**Three tests decide what earns the name "agent"**: it invokes an LLM, *and* writes a row carrying
provenance, *and* cannot be trusted without a separate check. Fail one and it is a pipeline.
A module named `*_agent` that never calls `get_llm_client()` is a defect.

| Unit | Kind | Service | Phase |
| --- | --- | --- | --- |
| Import (incl. Parser Profiles), Version, Diff | pipeline | `regulation` | 1 |
| Requirement Extraction | **agent** | `regulation` | 1 |
| Cross-reference | pipeline | `regulation` | 2 |
| Ontology Mapping | **agent** | `regulation` | 2 |
| Embedding, Retrieval | pipeline | `assistant` | 1 |
| Reasoning (citation-enforced generation) | **agent** | `assistant` | 1 |
| Evidence verification | **agent** | `assistant` | 1 |

**No agent output is terminal.** A generated answer passes the evidence-verification agent and a
confidence score; an extracted IR is locked by an `ra`. Only locked IRs flow downstream.

## Celery Queue Architecture

*Target.* One queue per service, queue name = service folder name. Cross-service dispatch **by task
name only**: `send_task("svc.task_name", args=[...], queue="svc")` — never import another service's
task graph.

The ingestion chain (fetch → archive → parse → diff → emit) runs on the `regulation` queue,
committing incrementally so progress is visible and a retry skips completed rows. **The scheduler
(beat) lives with `regulation` and nowhere else** — it drives `source_schedules` and has no other
consumer. `monitoring` needed a delivery retry and did *not* get a second beat for it: a failed
delivery re-dispatches `monitoring.deliver_alert` with a Celery `countdown`, so the backoff belongs
to the delivery, is recorded on the row as `next_retry_at`, and survives a worker restart. A sweep
would have spent a periodic query re-discovering work that was already scheduled.

**Extraction is deliberately *not* chained off parse.** Every other stage is deterministic and cheap
enough to run on every fetch; extraction calls an LLM per obligation-bearing clause over a 25,729-
clause corpus, so auto-running it would spend a full extraction to discover nothing changed. A first
extraction is explicit — `POST /api/v1/document-versions/{id}/extract`, or the
`regulation.extract_document_version` task. Amendments are covered by the targeted
`regulation.rederive_stale_irs` sweep the diff stage enqueues by name when it stales an IR
(phase1.2 deviation 1). Chaining it is a plausible-looking "fix" that is not one.

**Embedding is not chained off parse either, and for the same reason.** A first index build is
explicit — `POST /api/v1/document-versions/{id}/embed`, or `assistant.embed_index` over the versions
whose index is missing or built under a different model. Answering runs on the `assistant` queue
too: `POST /api/v1/queries` writes the question row synchronously and returns `202`, and
`assistant.answer_query` does the model-bound work.

**The diff stage tells `assistant` an amendment landed, by task name.** An amendment moves an
answer's evidence exactly as it stales an IR, but into a different lifecycle in another service's
table ([ADR-0006](docs/design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 10).
So `regulation` never writes `answer_citations`; it sends `assistant.supersede_answer_citations` with
the version id, and `assistant` reads `clause_diffs` one-way and flags its own rows.

**It tells `monitoring` the same way, and the events are already committed when it does.** The diff
stage sends `monitoring.route_change_events` with the version id; `monitoring` reads `change_events`
joined to `clause_diffs` one-way and composes its own alerts. It is dispatched even when every diff
was a renumber — deciding that an amendment is not worth alerting on is a judgement `monitoring`
makes, grades and counts, not one to make silently on the writing side.

## Shared Library

*Target.* `shared/regops_shared/` is an installable package used by all services. It holds
contracts, not behaviour, and **never calls a service**.

- `models/` — canonical ORM models; every table modelled once, the owning service re-exports
- `llm/` — `get_llm_client()`, provider from settings (`ollama` | `claude`); embeddings always
  Ollama `nomic-embed-text` 768-dim, fixed regardless of generation provider
- `auth/` — `get_current_principal()` → `decode_token()`, stateless per-service JWT verification
- `db/` — async engine for FastAPI, **sync** engine (`sync_session()`) for Celery workers: a prefork
  worker has no long-lived event loop, and an asyncpg pool cached across `asyncio.run()` calls binds
  to a loop that has already closed
- `storage/` — MinIO plus the WORM archive: `archive_bytes()` is content-addressed and write-once,
  and never overwrites an existing object
- audit-trail writer — append-only table in `platform-core`; audit is **not** a service
- constants — no magic literals in service code

Migrations live in `shared/alembic/versions/` as one history; `shared/alembic/regops_schema.sql` is
the authoritative dump and is updated in the same change.

## Commands

```bash
docker compose --profile app up -d         # infra + services + regulation/assistant/monitoring workers
docker compose run --rm migrate            # alembic upgrade head, then exits
docker compose exec -T regulation python /scripts/seed_sources.py    # idempotent source registry
docker compose exec -T <svc> python -m pytest tests/unit -q
docker compose logs <svc> --tail=30

# integration — separate database, selected by REGOPS_DB_NAME (never by DATABASE_URL in
# .env.test: compose sets it under `environment:`, which wins over `env_file:`)
REGOPS_DB_NAME=regops_test docker compose run --rm migrate            # once, to head
STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm <svc> \
    python -m pytest tests/integration -q

# host-side gates
ruff check . && ruff format --check . && mypy shared/regops_shared --ignore-missing-imports
python -m pytest shared/tests services/*/tests/unit scripts/evaluation/tests -q
python scripts/tier_d_scan.py

# phase 1.6 evaluation harness — runs inside the stack; docs/eval is mounted at /eval
E="docker compose exec -T -w /scripts regulation python -m evaluation.cli"
$E validate                # golden-set composition + every expected clause path against the corpus
$E run --per-axis 3        # a bounded scored pass that spreads across axes; resumable
$E score && $E polls       # per-axis scores; scheduled polls versus polls that ran
$E gates --out /eval/go-no-go.md
```

From `frontend/`:

```bash
npm run typecheck && npm run lint     # both wired into CI

# E2E against the running stack and the real model. Not a CI gate: a live answer takes minutes and
# is worded differently every run, so a red build would as often mean "the model was slow" as "the
# product broke". Needs the two seeded principals — see frontend/e2e/README.md.
REGOPS_E2E_RA_PASSWORD=… REGOPS_E2E_VIEWER_PASSWORD=… npm run e2e
```

## Repo sync to `startup`

Two remotes: `origin` (github.com/hrkim1000/regops — the real repo) and `startup`
(github.com/kimhwangdata/startup-doc — a shared repo owned by another account).

**Standing since 2026-08-21: every commit to `origin/main` is followed by a `startup` sync, and the
sync publishes the whole repository** — code, `.claude/`, this file, and `docs/` in full. That
replaces both the docs-only filter and the per-occasion ask. What did **not** change:

- **`startup` pushes go to the `hrkim` branch only. Never to `startup/main`.**
- **Never `--force`.** It is another account's repository; a rejected push is a signal to look at
  why, not something to overpower.
- **`.env*` is untracked and stays untracked.** The path filter used to be a second thing keeping
  credentials out of a shared repo. It is gone, so `.gitignore` is now the only one.
- `git subtree` is still wrong: it would rewrite the paths, and `startup` mirrors this repo's
  layout as it is.

Publish `main`'s committed tree as a snapshot commit parented on the startup tip:

```bash
set -e
git fetch startup hrkim
BASE=$(git rev-parse FETCH_HEAD)          # pin it NOW — see the warning below

COMMIT=$(git commit-tree 'main^{tree}' -p "$BASE" -m "chore: sync RegOps repository")

# Verify before pushing: right parent, and a genuine fast-forward. The `&&` is deliberate —
# the safety check must gate the push even if someone drops the `set -e`.
git rev-parse --short "$COMMIT" "${COMMIT}^"
git merge-base --is-ancestor "$BASE" "$COMMIT" && git push startup "$COMMIT":hrkim
```

It publishes **committed** state, so "commit to `origin` first" is now structural rather than a rule
to remember. `git push startup main:hrkim` is not an equivalent shortcut and does not work: `hrkim`
carries its own snapshot lineage, so pushing `main` onto it is a non-fast-forward and would need the
`--force` that is forbidden. Parenting on the startup tip is what keeps the push a fast-forward.

Two exclusions went away with the filter, and the reasons they existed did not. **`docs/data/`**
(raw source research) and **`docs/memo/`** (superseded drafts that contradict the current rules) now
reach the shared repo, where a reader has none of the context this file gives. They are still
authoritative for nothing — the live statement is in `RegOps.md`, `import-source-map.md`, or an ADR.

> **`FETCH_HEAD` is a session-global symbol and any other `git fetch` overwrites it.** Capture it
> into `BASE` immediately, and never read it again later in the procedure. This bit twice on
> 2026-08-05: a `git fetch origin` earlier in the session left `FETCH_HEAD` pointing at *this*
> repo's `main`, so `-p FETCH_HEAD` built the sync commit on the wrong lineage (caught only because
> the push was rejected), and a `git ls-tree FETCH_HEAD` audit read the local repo while reporting
> on the remote one — producing a confident, entirely false claim that code had been published to a
> third-party repository. Pin the SHA, and verify the parent before pushing rather than after.
>
> That warning outlived the procedure it was written for: the temporary index and its `git add` are
> gone with the path filter, but `FETCH_HEAD` is still what the parent is read from, and the audit
> that reported on the wrong repository was a `git ls-tree`, not a `git add`.

## Terminology Conventions

Always use the abbreviation; give the full name in parentheses only when first explained — e.g.
`SaMD (Software as a Medical Device)`. Full definitions in
[.claude/skills/glossary](.claude/skills/glossary/SKILL.md).

| Term | Definition |
| --- | --- |
| **cell** | One `{authority}_{domain}` pair — the unit of scope, connector, parser profile, and coverage. Exactly 8 |
| **SaMD** | Software as a Medical Device |
| **IR** | InfoRequirement — one atomic regulatory obligation with a **mandatory citation**. Never "Information Requirement" |
| **Citation** | `(document_id, document_version_id, clause_path, effective_date)` — pinned to an immutable version, never "current" |
| **ChangeEvent** | Emitted from a ClauseDiff, routed to every claiming cell |
| **StandardReference** | A Tier D standard as metadata only — no body text and no table that could hold it |
| **Tier A/B/C/D** | Source collectability: A public API · B static/RSS · C scraping · **D copyright-protected, never ingested** |
| **needs verification** | The mandatory response when a citation cannot be produced |

Prior-platform terminology (SW Profile DB, git-agent, component/device release, clinical HITL gates,
per-section signoff, Tele/FA/DDH) does **not** apply to RegOps and must not appear in RegOps
documents or code — see [ADR-0001](docs/design/ADR-0001-platform-foundation.md).

## Development Guidelines

### Error Handling

- Use specific exception types; never bare `except:`
- Log with ids, inputs, and operation context before re-raising
- `GET /health` per service
- Helper functions `flush()` but never `commit()` — the caller commits

### Code Quality

- Type hints throughout; all FastAPI path operations typed
- Constants in `shared/regops_shared/` or a service-level `constants.py` — no magic literals
- Follow existing patterns; do not introduce new abstractions without discussion

### Security

- **Never** commit or print `.env*` contents (real keys live there; `.env.example` is the template).
- No real emails/passwords/tokens in code, tests, fixtures, or docs — placeholders only.
- JWT issued/signed by `platform-core`; verified statelessly per service via the shared
  `get_current_principal()` → `decode_token()`.
- RBAC roles are `viewer | ra | admin` ([ADR-0005](docs/design/ADR-0005-service-architecture.md)
  decision 5); `compliance` arrives in Phase 2. Restricted actions are the ones where a human
  assertion enters the audit trail: **locking an IR** and **resolving a structure-drift alert**.
- PHI/PII: encrypted at rest + transit, anonymized in logs; RBAC re-checked server-side on
  every endpoint.

## API Design

- URL-versioned `/api/v1/...`; the browser reaches it via the Next.js `/api/<svc>/*` rewrite.
- Plural resource nouns (`/documents/{id}`), explicit verbs for nested actions
  (`POST .../generate`), `snake_case` params and bodies.
- **Every response wears the envelope** `{code, status, message, data, meta}` — list endpoints put
  pagination in `meta`; errors use `status:"error"`, `data:null`, with the reason in `message`.
- Long work returns `202 {id, task_id}` immediately and the worker commits incrementally.

Detail in [.claude/skills/service-endpoint](.claude/skills/service-endpoint/SKILL.md).

## Testing

| Layer | Share | Coverage | Runs against |
| --- | --- | --- | --- |
| Unit | 70% | ≥80% | mocks only — never call a real LLM |
| Integration | 20% | ≥70% | real Postgres + Redis + Celery; RBAC exercised |
| E2E | 10% | critical paths | Playwright |

Non-negotiable cases — cheaper to catch in CI than in an audit: **Tier D** (no standard body text
anywhere), **citation immutability** (flagged superseded, never rewritten), **cell isolation**
(fan-out to every claiming cell and no others), **renumbering** (never delete+add), and
**cross-domain** (one parse pipeline for SaMD and Cosmetic).

Golden-query-set regression is a release gate, scored per domain and per gated cell. Report failures
verbatim — never paper over a red test. Detail in
[.claude/skills/testing](.claude/skills/testing/SKILL.md).
