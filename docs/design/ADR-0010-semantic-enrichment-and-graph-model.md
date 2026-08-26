# ADR-0010 — Semantic enrichment and the knowledge graph model

- **Status:** Proposed
- **Date:** 2026-07-30
- **Depends on:** [ADR-0002](ADR-0002-canonical-regulation-model.md), [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md), [ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md), [ADR-0008](ADR-0008-service-composition.md), [ADR-0009](ADR-0009-service-boundaries-per-pillar.md)
- **Resolves:** [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) open question 4 (cross-references), [ADR-0009](ADR-0009-service-boundaries-per-pillar.md) open question 1 (what "interpretation" is)
- **Related:** [ADR-0008](ADR-0008-service-composition.md) decision 6 — the same naming question seen from the taxonomy side, where Interpretation is absorbed into the requirement agent
- **Phase:** built in Phase 2; the model is decided in Phase 1 because IR extraction hardens at W3-4

---

## Context

RegOps.md L3 declares a Regulatory Knowledge Graph that links "regulatory authorities, laws/notices,
clauses, requirements, product families, markets, and internal SOPs/controls as entities" and
computes impact-propagation paths on amendment. **No ADR models it.** ADR-0002 is relational and
stops at ClauseDiff; ADR-0004 stops at a single IR and says nothing about relations between IRs or
between clauses; ADR-0007 covers only the `Product × Regulation → Compliance` axis.

There is a sharper way to see the gap. ADR-0004 decision 1 yields **zero IRs** for "a definition,
scope statement, or heading," and decision 6 records them as `excluded` with a reason so that
coverage stays provable. That is correct — they carry no obligation. But 화장품법 제2조 defines the
terms every other clause is written in, and discarding its meaning discards the vocabulary the rest
of the corpus depends on.

**The clauses IR extraction deliberately excludes are the raw material of the semantic layer.**
Definitions, scope statements, and cross-references are not waste; they are the other half of the
model, and nothing currently consumes them.

This layer was first proposed as an "Interpretation Agent." Two things came out of pinning that name
down, and decision 1 separates them.

## Decisions

### 1. `semantic enrichment` is the layer; `interpretation` is not its name

An earlier draft carried an *Interpretation Agent* that would structure a requirement's meaning into
obligation, bearer, scope and evidence. That is IR extraction — ADR-0004 decision 1 already produces
exactly those fields — so it is **absorbed into the requirement agent, not renamed into this ADR**
(ADR-0008 decision 6). This ADR covers the *other* thing the name was carrying: the vocabulary and
edges beneath obligations.

*(The draft was `docs/memo/`, which is superseded material and authoritative for nothing — CLAUDE.md
§ Read-only directories. It is not cited here; the argument below does not rest on it.)*

The name is independently unusable. In regulatory practice **interpretation is a legal act** —
issued by an authority or a qualified person, and carrying liability. Naming an LLM component for it
claims precisely the authority the product disclaims: RegOps.md § Risk commits to stating in the UI
that final judgment rests with the human. A component named for a legal act it cannot perform is the
pairing an auditor finds first.

`semantic enrichment` is therefore the **layer** name — it describes the operation, annotating
clause text with structure, and asserts nothing about legal meaning. Its two units take the names
already proposed for them: **Ontology Mapping** and **Cross-reference** (decision 4).

### 2. Scope — enrichment consumes what IR extraction excludes

| Transformation | Owner | Status |
|---|---|---|
| clause → obligation (bearer · modal · action · condition) | requirement agent, IR (ADR-0004) | decided |
| clause → obligation-bearing or excluded | `clause_classifications` (ADR-0004 decision 6) | decided |
| clause → retrieval vector | embedding pipeline, `assistant` (ADR-0006) | decided |
| clause → applies to our product | applicability (ADR-0007) | Phase 2 |
| **clause → defined terms, concepts, entity mentions, resolved cross-references** | **semantic enrichment** | **this ADR** |

Enrichment does **not** produce obligations, answers, or applicability statements. It produces the
vocabulary and the edges those three stand on. If a proposed enrichment output is an obligation, it
belongs in an IR and the atomicity rule in ADR-0004 decision 1 governs it.

### 3. The graph is edge tables in Postgres, not a graph database

RegOps' node population is bounded by the 8 cells — thousands of clauses per cell, not millions.
Impact propagation is a bounded traversal expressible as a recursive CTE.

A dedicated graph store would add a deployment unit, a second backup and retention surface, and a
second place the 21 CFR Part 11 audit trail has to be proven consistent — against a workload that
does not need it. The graph is a **projection over the relational model**, sharing its transactions,
its migrations, and its audit trail.

**Falsification criterion:** if Phase 2 impact propagation requires traversals whose depth or
fan-out makes recursive CTEs impractical at real corpus size, this decision is wrong and a graph
store is justified. Measure before switching; do not pre-emptively adopt one.

### 4. Two producers, split by ADR-0008's own test

Applying the three tests in ADR-0008 decision 2 splits this work in half:

| Unit | Kind | Because |
|---|---|---|
| **Cross-reference** | **pipeline** | `제5조에 따른`, "as specified in Annex III" are explicit textual markers. Matching and resolving them against `clause_path` is deterministic — no LLM, no provenance columns, no gate |
| **Ontology Mapping** | **agent** | mapping regulatory terms onto canonical concepts is LLM-proposed, non-deterministic, and unverifiable without review |

Both live in `regulation` (ADR-0009): they read the clause store and write into it, so they sit on
the same side of the `change_events` seam.

### 5. Every semantic assertion carries a citation and its provenance

ADR-0004 decision 2 — an IR without a citation does not exist — applies one layer out. An enrichment
row that cannot name the clause it was derived from is **rejected, not stored with a null citation**.

LLM-derived rows record `llm_provider`, `llm_model`, `prompt_version`, `rule_version` and their
`enrichment_run`, mirroring `extraction_runs` (ADR-0004 decision 4).

Locking every edge by hand is unaffordable, so the gate is graded rather than uniform:

| `derived_by` | Gate | Visible to |
|---|---|---|
| `deterministic` | none — the marker is in the text | everything |
| `llm`, confidence ≥ threshold | RA review sampled, not exhaustive | retrieval expansion and impact propagation |
| `llm`, confidence < threshold | RA review required | nothing until reviewed |

**No enrichment row is ever a citation.** Retrieval may follow an enrichment edge to *find* a
clause, but the answer cites the clause (ADR-0002 decision 4), never the edge that led to it. This
is what keeps enrichment from becoming an unverifiable inference layer beneath every answer — the
exact hallucination surface the product exists to remove.

### 6. Cross-region equivalence is a claim with a confidence, never an identity

The strongest temptation here is to merge 임상시험, "clinical investigation" and 临床试验 into one
concept node. **That would assert legal equivalence between jurisdictions, which is false in
general** and is the kind of claim RegOps must never make silently.

Concepts are scoped to the cell whose corpus defines them. Cross-region relations are separate,
directional, and weaker:

`relation ∈ equivalent | broader | narrower | related`, each with a confidence and an RA reviewer.

Comparison across regions presents **both sides with both citations**. It never substitutes one
region's clause for another's, and an equivalence edge never satisfies a citation requirement.

### 7. Cross-references resolve at enrichment, not at extraction

*(Resolves ADR-0004 open question 4.)*

ADR-0004 asked whether to resolve `제5조에 따른` at extraction or retain it as text. Neither, exactly:
the clause text is retained verbatim, and the resolution is stored **beside** it in
`clause_references`.

This keeps IR extraction unchanged — a W3-4 deliverable does not grow — and puts staleness
propagation where it belongs. ADR-0004 decision 5 already marks an IR `stale` when a ClauseDiff
touches a clause it cites; with resolved references, that propagation becomes a traversal: an
amendment to a *referenced* clause reaches the IRs that cite the *referring* clause. ADR-0004 noted
this "may be correct" — it is, and it is the mechanism behind monitoring's impact grading
(ADR-0009 decision 3).

Reference resolution is recorded per attempt, including failures. An unresolvable reference is a
data-quality signal, not something to silently drop.

## Schema sketch

Illustrative, in the manner of ADR-0002 — column types settle when the migration is written.

```sql
concepts(id, canonical_label, scope_cell_id, status,
         definition_document_version_id, definition_clause_path)   -- citation is mandatory
concept_labels(concept_id, label, language, is_canonical)
concept_relations(from_concept_id, to_concept_id, relation, confidence,
                  reviewed_by, reviewed_at)                        -- decision 6
clause_concepts(clause_id, concept_id, role, confidence, derived_by,
                enrichment_run_id, reviewed_by, reviewed_at)
clause_references(id, from_clause_id, reference_text, to_document_id, to_clause_path,
                  resolution_kind, confidence, enrichment_run_id)  -- unresolved rows retained
enrichment_runs(id, rule_version, prompt_version, llm_provider, llm_model, started_at)
```

`derived_by ∈ deterministic | llm`. `resolution_kind ∈ resolved | ambiguous | unresolved`.
All tables belong to `regulation` and are **shared, not tenant-scoped** (ADR-0005 decision 2) —
화장품법's definitions are the same for every customer.

## Consequences

- The `excluded` clauses from ADR-0004 decision 6 acquire a consumer; coverage stops meaning
  "examined and discarded."
- Impact propagation gains its mechanism. Monitoring's impact grading (ADR-0009 decision 3) has
  something to grade against beyond "a clause in your cell changed."
- No new service, no new datastore, no new deployment unit.
- Cost: a second review surface for RA on top of IR locking. Decision 5's graded gate is what keeps
  it bounded, and the threshold is a tuning parameter that has to be set with real data — not
  guessed now.
- Phase 1 is unaffected in build but constrained in design: `clause_references` must exist as a
  concept before W3-4 fixes the clause schema, or resolution has nowhere to land later.

## Open questions

1. ~~**Concept identity across versions.**~~ **Closed 2026-08-26 — there is no cross-version concept
   identity, because none is asserted.** A concept is pinned to the version that defines it, which
   `concepts.definition_document_version_id` already records. When an amendment rewrites a
   definition, the new version simply has its own concept row; nothing claims it is *the same
   concept* as the one before.

   The question assumed we owed an answer to "same or superseding". We do not, and asserting either
   would be a claim about legal continuity that no one has checked — the same objection this ADR
   already makes on the jurisdiction axis, where cross-region equivalence is *"a claim with a
   confidence, never an identity"*. Applied to the time axis it reads identically.

   This also removes the cost the question named. **Concept churn on every definitional amendment
   stops being a problem**, because churn is only a problem if something is trying to hold identity
   across the change. Concepts behave like clauses: each version has its own, and continuity is a
   question a reader asks, not a row the system asserts.
2. ~~**Does enrichment run per language or per version group?**~~ **Closed 2026-08-26 — the two
   units are the same unit, and stay so for the whole current roadmap.** A cell holds exactly one
   language today: `mfds_*` is `ko` (537 documents), `fda_*` is `en` (27). So *per language*, *per
   version group* and *per cell* all name the same partition, and enrichment produces identical
   output whichever it is written against.

   The question becomes real only when **one cell holds two languages**, and nothing on the roadmap
   creates that. EU — the 24-language case this was written for — moved to Phase 4, and the first
   multilingual exercise is now NMPA in 2.0c, which is Chinese-only. A second language *inside* one
   cell has no scheduled arrival.

   So this is not "unexercised, decide later"; it is "the distinction has no referent yet". When one
   appears, the choice is already narrowed by open question 1: a concept is pinned to the version
   that defines it, and a `version_group` is a set of versions — so the group is not a natural unit
   for a concept, and *per language* is the shape that fits.

   > **Recorded because it is what made this look live.** Three things in the current implementation
   > suggest a multilingual mechanism that is not there yet, and none is a defect while every cell
   > is single-language — see [ADR-0002](ADR-0002-canonical-regulation-model.md) decision 5's
   > annotation. In short: `version_group_id` is 1:1 with `document_id` (556 of each, no group spans
   > a document), `_version_group_for` takes a `language` argument it never reads, and
   > `AUTHORITATIVE_LANGUAGE` has **no consumer in the codebase**.
3. **Confidence threshold and sampling rate** for decision 5's middle tier. Needs golden-set
   evidence; unset until Phase 2.
4. **Does retrieval actually use enrichment edges?** ADR-0006 specifies hybrid search plus graph
   context expansion, but the expansion's edge types are unspecified. Deciding this earlier than
   Phase 2 would let the golden query set measure whether the edges help at all.
