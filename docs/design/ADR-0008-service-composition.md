# ADR-0008 — Service composition: agents, pipelines, and shared

- **Status:** Proposed
- **Date:** 2026-07-30
- **Depends on:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md), [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md), [ADR-0005](ADR-0005-service-architecture.md), [ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md)
- **Resolves:** the three-way collision on the word "agent"; supersedes the flat list in [memo/agent.md](../memo/agent.md)
- **Updated by:** [ADR-0009](ADR-0009-service-boundaries-per-pillar.md) — decision 6 now homes Alert and Impact in `monitoring`. The taxonomy itself is unaffected: agent · pipeline · shared is defined *inside* a service, so moving a unit between services does not change its kind.

---

## Context

ADR-0005 settled **how many** services there are and rejected one-per-pipeline-stage. It never said
what a service is *made of*, so the next question arrived unanswered: a draft
([memo/agent.md](../memo/agent.md)) listed eighteen peer "Agents" — Crawler, Parser, Normalizer,
Version, Diff, Embedding, Audit, Alert, Report, Q&A and more — flat, with no owner, no phase, and no
indication which involve an LLM.

The word is already overloaded. RegOps uses "agent" for two specific things: the **Import Agent**,
one generic domain-independent ingestion path serving all 8 cells (import-agent.md, RegOps.md § Scope),
and the **evidence-verification agent**, a defined LLM pass ([ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md)
decision 6). A third meaning — "any stage" — makes the term carry no information.

This is not a style complaint. Two obligations attach to LLM-driven code and to nothing else:
every row an LLM produced records `llm_provider` and `llm_model` (ADR-0005 decision 7), and no
generated result reaches a user without a separate verification pass (ADR-0006). A flat list where
`Diff Agent` and `Q&A Agent` look alike is a list where those obligations cannot be checked.

## Decisions

### 1. A service is composed of agents, pipelines, and shared

The service remains the deployment unit. Agents and pipelines are units *inside* one; shared is a
library imported by all of them.

| Kind | Determinism | Deployment | Governed by |
|---|---|---|---|
| **agent** | non-deterministic — invokes an LLM | Celery task on the **owning service's** queue | records `llm_provider`/`llm_model`; output must pass a verification gate (decision 5) |
| **pipeline** | deterministic | Celery chain on the owning service's queue | idempotent, resumable, incremental commit (ADR-0003, ADR-0005 decision 6) |
| **shared** | n/a — no runtime of its own | imported, never deployed | `regops_shared`; holds contracts, owns no service state (decision 4) |

Neither agents nor pipelines are deployment boundaries. They are named, independently schedulable,
independently retryable units within a service — which is what the memo was reaching for, and what
ADR-0005 left unspecified.

### 2. Three tests decide what earns the name "agent"

A unit is an agent only if **all three** hold:

1. it invokes an LLM, so its output is non-deterministic;
2. it writes a row that must carry `llm_provider` / `llm_model`;
3. its output cannot be trusted without a separate check — the evidence-verification pass
   (ADR-0006) or a human lock (ADR-0004).

Fail any one and it is a pipeline stage. Calling deterministic code an agent is not a harmless
inflation: it hides which rows need provenance and which outputs need verifying, and those are
exactly the two things a 21 CFR Part 11 audit asks to see enumerated.

The converse also binds — **a module named `*_agent` that never calls `get_llm_client()` is a
defect**, catchable in review.

### 3. "Import Agent" is a pipeline, and the name is grandfathered

The Import Agent satisfies none of the three tests: fetch → archive → parse → normalize is
deterministic. It is a pipeline. The name predates this ADR, is load-bearing in
[import-agent.md](../import-agent.md) and [RegOps.md](../RegOps.md), and renaming a spec mid-Phase 1
buys nothing — so it is retained as a proper noun that confers **no agent obligations**.

It stays **singular**. The memo split it into Import + Crawler + Parser + Normalizer, which
contradicts import-agent.md's central conclusion: one generic Import Agent, with per-cell variation
isolated into **Connectors** and **Parser Profiles**. Those two concepts are the actual internal
structure and were missing from the list entirely.

### 4. `shared` holds contracts, not behaviour

| `regops_shared` holds | Rule |
|---|---|
| canonical ORM models (`models/`) | every table modelled once; the owner re-exports (db-migration skill) |
| the LLM seam (`llm.get_llm_client()`) | provider from settings; embeddings pinned to `nomic-embed-text` 768-dim |
| auth (`get_current_principal()` → `decode_token()`) | stateless per-service JWT verification |
| the audit-trail writer | append-only table in platform-core — **not a service** (ADR-0005 decision 4) |
| constants | no magic literals in service code |

**Shared never calls a service.** It has no queue, no endpoint, and no state of its own; a
dependency pointing outward from `shared` is the signal that something belongs in a service instead.

This is why the memo's **Audit Agent** does not exist. ADR-0005 decision 4 rejected it by name:
routing every write through an audit *service* makes the audit trail a synchronous dependency on the
write path of everything. It is a shared writer against a platform-core table.

### 5. No agent output is terminal

Every agent output passes one of exactly two gates before it reaches a user or flows downstream:

| Agent output | Gate |
|---|---|
| generated answer | evidence-verification agent, then confidence score; below threshold → human review (ADR-0006) |
| extracted IR | human **lock** by an `ra` — only locked IRs flow downstream (ADR-0004, ADR-0005 decision 5) |

An agent that writes a user-visible row unilaterally is a design error. This is the property the
flat list erased, and it is the reason the taxonomy exists rather than being a naming preference.

### 6. Where the proposed agents land

Mapped against the definitions in [memo/agent.md](../memo/agent.md) § agent 정리.

| Proposed | Kind | Home | Phase |
|---|---|---|---|
| Import Agent | **pipeline** | `regulation` | P1 |
| Parser Agent | **pipeline** — a Parser Profile *inside* Import, not a peer | `regulation` | P1 |
| Version Agent, Diff Agent | **pipeline** | `regulation` | P1 |
| Requirement Extraction Agent | **agent** — IR extraction, gated by human lock | `regulation` | P1 |
| Interpretation Agent | **absorbed** into Requirement Extraction — see below | — | — |
| Ontology Mapping Agent | **agent** — ADR-0010 | `regulation` | P2 |
| Cross-reference Agent | **pipeline** — deterministic markers, ADR-0010 | `regulation` | P2 |
| Embedding Agent | **pipeline** | `assistant` — not `regulation` (ADR-0005 decision 3) | P1 |
| Retrieval Agent | **pipeline** — hybrid search is deterministic | `assistant` | P1 |
| Reasoning Agent | **agent** — citation-enforced generation | `assistant` | P1 |
| Citation Agent | **not a separate unit** — see below | `assistant` | P1 |
| *(missing)* evidence-verification agent | **agent** — ADR-0006 decision 6 | `assistant` | P1 |
| Alert Agent | application feature, not a unit of either kind | `monitoring` + frontend | P1 |
| Impact Analysis Agent | undecided — blocked on the Product context | `monitoring` | P2 |
| Audit Agent | **shared** — run tables plus a shared writer, see below | `shared` | P1 |
| Requirement Mapping, Gap Analysis, Evidence, Report | Phase 2 surface; kind decided when built | `compliance` | P2 |

**Interpretation is absorbed, not renamed.** Defined as structuring a requirement's meaning into
obligation, bearer, scope and evidence, it *is* IR extraction — ADR-0004 decision 1 already produces
exactly those fields. Splitting identification from structuring into two LLM passes was considered
and rejected: it doubles LLM cost and creates an intermediate artefact that has no citation yet,
which ADR-0004 decision 2 forbids ("an IR without a citation does not exist").

The graph-vocabulary work that *was* proposed under this name is
[ADR-0010](ADR-0010-semantic-enrichment-and-graph-model.md) `semantic enrichment`, whose two units —
Ontology Mapping and Cross-reference — appear above under their own names.

**Citation is a property of generation, not a downstream step.** ADR-0006 specifies
*citation-enforced* generation: the citation is produced with the claim and constrains it. A
separate agent that attaches citations after reasoning inverts that into generate-then-justify,
which is the mis-citation failure mode ADR-0006 exists to prevent.

**`Evidence Agent` and the evidence-verification agent are different things.** The former links
evidence documents and records that satisfy a requirement — gap analysis, Phase 2, `compliance`. The
latter is the pass every generated answer must survive (ADR-0006 decision 6), and it was absent from
the proposed list. Losing it would remove a trust invariant, so it is added above.

**Audit is agent-execution provenance, not the platform audit trail.** As defined — agent run
history and decision process — it is `extraction_runs` / `enrichment_runs` plus the provenance
columns on every LLM-written row (decision 2), which Part 11 requires. That is distinct from
`audit_log` (users and actions) in platform-core. Neither is an agent, and neither is a service
(ADR-0005 decision 4).

**Impact is deferred, not assigned.** Per [ADR-0007](ADR-0007-context-map-and-applicability.md) an IR
currently applies to a *cell*, not a *product*, so impact grading has nothing to grade against until
the Product context exists. Whether it is agent or pipeline depends on whether grading is
LLM-proposed or rule-derived — a question ADR-0007's build answers.

## Consequences

- The naming rule is mechanically checkable: `*_agent` without `get_llm_client()`, or an
  LLM-written row without `llm_provider`, fails review.
- The set of outputs needing verification becomes enumerable — three agents in Phase 1, not eighteen
  ambiguous boxes. That list is what a Part 11 audit and the CSA validation package both ask for.
- **No new deployment units, no new queues, no new raw-SQL seams.** ADR-0005's cost argument is
  untouched because nothing here crosses a service boundary.
- Cost: the taxonomy must be applied when the first service code is written. RegOps is greenfield
  ([ADR-0001](ADR-0001-platform-foundation.md)) — no service code exists yet, so there is nothing to
  retrofit. This is the cheapest moment it will ever be.

## Rejected alternative — eighteen services

Considered and rejected, for the reason ADR-0005 decision 1 gave and
[ADR-0009](ADR-0009-service-boundaries-per-pillar.md) carries forward: fetch, parse, diff and IR
extraction all mutate the clause store, so each split puts a raw-SQL seam in the middle of one
transaction-shaped workflow — which the conventions forbid. Eighteen deployment units at 6.5 FTE for
16 weeks also means eighteen migration coordination points and eighteen debugging hops, and
`Audit Agent` would additionally reinstate the synchronous audit dependency ADR-0005 decision 4
removed. The memo's instinct — that these are real, separately-named units — is right; the inference
that they must therefore be services is not.

## Open questions

1. **Rename `import-agent.md` → `import-pipeline.md`?** Decision 3 grandfathers the name; a rename
   would remove the last ambiguity at the cost of churn across RegOps.md, the source map, and the
   glossary. Low priority, but it should be decided rather than drift.
2. **Is Phase 2 control mapping an agent?** If mappings are LLM-proposed they need a lock analogous
   to IR locking; if rule-derived from IR attributes they are a pipeline. ADR-0007's build decides.
3. **Does `assistant` merging into `regulation` (ADR-0005 open question 1) change anything here?**
   It should not — the taxonomy is intra-service by construction — but the Embedding ownership split
   in decision 6 assumes the two stay separate.
