# Phase 2.1 — Semantic enrichment & knowledge graph

- **Roadmap:** Phase 2 (M5–12) · **Status:** ⬜ planned
- **Governed by:** [ADR-0010](../design/ADR-0010-semantic-enrichment-and-graph-model.md), [ADR-0008](../design/ADR-0008-service-composition.md)
- **Depends on:** [phase1.2](phase1.2_ir_extraction.md); schema decided in Phase 1
- **Service:** `regulation`

---

## Goal

Build the layer beneath obligations: defined terms, concepts, and resolved cross-references. **The
knowledge graph is the asset** — LLMs are replaceable, but regulation–product–control mapping data
accumulates value.

The raw material is the clauses IR extraction deliberately excludes. 화장품법 제2조 defines the terms
every other clause is written in, yields zero IRs, and is currently discarded.

## Scope

**In:** `concepts`, `concept_labels`, `concept_relations`, `clause_concepts`, `clause_references`,
`enrichment_runs`; the Cross-reference pipeline and the Ontology Mapping agent.

**Out:** applicability and control mapping (2.2). Enrichment produces vocabulary and edges, never
obligations or applicability statements.

## Tasks

### Schema — frozen by the M8 checkpoint

- [ ] `concepts(id, canonical_label, scope_cell_id, status, definition_document_version_id, definition_clause_path)` — **citation mandatory**
- [ ] `concept_labels(concept_id, label, language, is_canonical)`
- [ ] `concept_relations(from_concept_id, to_concept_id, relation, confidence, reviewed_by, reviewed_at)`
- [ ] `clause_concepts(clause_id, concept_id, role, confidence, derived_by, enrichment_run_id, reviewed_by, reviewed_at)`
- [ ] `clause_references(id, from_clause_id, reference_text, to_document_id, to_clause_path, resolution_kind, confidence, enrichment_run_id)`
- [ ] `enrichment_runs` mirroring `extraction_runs`
- [ ] `derived_by ∈ deterministic | llm`; `resolution_kind ∈ resolved | ambiguous | unresolved`
- [ ] All **shared, not tenant-scoped** — 화장품법's definitions are the same for every customer

### Cross-reference (pipeline — deterministic)

- [ ] Match explicit markers: `제5조에 따른`, "as specified in Annex III"
- [ ] Resolve against `clause_path`; **clause text retained verbatim**, resolution stored beside it
- [ ] Unresolved references **retained**, not dropped — an unresolvable reference is a data-quality signal
- [ ] Staleness propagation: an amendment to a *referenced* clause reaches IRs citing the *referring* clause

### Ontology Mapping (agent — LLM)

- [ ] Concept identification and entity mentions from definition and scope clauses
- [ ] Records `llm_provider`, `llm_model`, `prompt_version`, `rule_version`, `enrichment_run_id`
- [ ] Graded gate — deterministic rows ungated; LLM rows above threshold sampled for RA review; below threshold **invisible until reviewed**

### Graph storage

- [ ] **Edge tables in Postgres, not a graph database.** A second store adds a deployment unit, a backup surface, and a second place Part 11 consistency must be proven — against a workload bounded by 8 cells
- [ ] Impact propagation as a recursive CTE
- [ ] **Falsification criterion:** if traversal depth or fan-out makes recursive CTEs impractical at real corpus size, this decision is wrong and a graph store is justified. Measure before switching

## Invariants

- [ ] **No enrichment row is ever a citation.** Retrieval may follow an edge to *find* a clause; the answer cites the clause
- [ ] **Cross-region equivalence is a claim with a confidence, never an identity.** 임상시험 / clinical investigation / 临床试验 are not merged into one node — that would assert legal equivalence between jurisdictions
- [ ] Comparison across regions presents **both sides with both citations**; an equivalence edge never satisfies a citation requirement

## Acceptance criteria

- [ ] Graph schema frozen at M8
- [ ] A defined term resolves from its definition clause to every clause using it
- [ ] `제5조에 따른` resolves to the referenced clause; an unresolvable reference is recorded, not dropped
- [ ] Amending a referenced clause marks the referring IR stale via traversal
- [ ] No answer cites an enrichment row — enforced by test
- [ ] A cross-region query returns both jurisdictions' clauses with their own citations, never a substitution
- [ ] Sub-threshold LLM edges are invisible to retrieval until reviewed

## Risks & open questions

- **Open question 1 — concept identity across versions.** When an amendment rewrites a definition: same concept with a new defining clause, or a new concept superseding the old? Consistency with [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 5 argues supersede-never-mutate, at the cost of churn on every definitional amendment.
- **Open question 3 — confidence threshold and sampling rate.** Needs golden-set evidence; cannot be guessed.
- **Open question 4 — does retrieval actually use enrichment edges?** [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) specifies graph context expansion without specifying edge types. Decide early enough that the golden set can measure whether the edges help at all.
- **A second RA review surface** on top of IR locking. The graded gate is what keeps it bounded.

## Deviations & decisions

_None yet._
