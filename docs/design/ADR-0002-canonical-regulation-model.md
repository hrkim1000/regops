# ADR-0002 — Canonical regulation data model

- **Status:** Proposed
- **Date:** 2026-07-29
- **Depends on:** [ADR-0001](ADR-0001-platform-foundation.md) (Accepted — greenfield)
- **Critical path:** development-plan.md § 6 places clause schema and IR extraction rules at W3-4,
  with everything downstream slipping one-for-one

---

## Context

This model is the most expensive thing in RegOps to change later: altering it after ingestion means
re-parsing the WORM archive and invalidating every stored citation. It also settles the architecture
bet — that Import → Normalization → Section Parsing is fully shared across domains and only IR
extraction branches (import-agent.md). If one clause model cannot represent 화장품법 and 의료기기법
without forking, Phase 2's six-cell build rests on a false assumption, and this document is the
cheapest place to discover that.

Constraints inherited from CLAUDE.md § Architecture rules: 8-cell identity, `import-source-map.md`
as the single source catalog, Tier D metadata-only, citation-enforced generation, WORM archive plus
audit trail, no connectors on login-gated portals.

## Entities

```text
Cell ──< Source ──< Document* ──< DocumentVersion ──< Clause
                        │              │                 │
                        │              └──< ClauseDiff >─┘
                        │
                        └──< IR ──< Citation ─→ (DocumentVersion, clause_path)
                                 └──< IRControlMapping   (Phase 2)

StandardReference   — Tier D, metadata only, no body text, never a DocumentVersion
ChangeEvent         — emitted from ClauseDiff, routed by Cell + product profile
```

`*` Document↔Cell is many-to-many. See decision 1.

## Decisions

### 1. Document↔Cell is M:N, not 1:N

The FD&C Act is a Primary Law in **both** `fda_samd` and `fda_cosmetic`. 21 CFR Part 11 applies to
SaMD and is cited in cosmetic eQMS contexts. Modelling `Document.cell_id` as a scalar would force
duplicate ingestion of the same statute, duplicate versions, duplicate diffs, and two divergent
citation targets for one clause.

`document_cells (document_id, cell_id)` — a document is ingested once and *claimed* by one or more
cells. Change events fan out to every claiming cell.

### 2. Tier D is a different entity, not a flagged Document

`StandardReference` carries: standard number, edition, issuing body, recognition/OJ citation number,
effective date, withdrawal date, harmonized/recognized status, official URL. It has **no
`DocumentVersion` and no body text**, and no table in which body text could be stored.

Enforcing Tier D as a column flag on `Document` would mean the archive *can* hold standard text and
only policy prevents it. Making it a separate entity with nowhere to put the text makes the rule
structural. An IR may cite a `StandardReference` (a requirement can be "conform to IEC 62304") but
such a citation resolves to a deep link, never to stored text.

This holds even where a regulation makes the standard legally binding — QMSR incorporates
ISO 13485:2016 by reference; cite the requirement, link the standard, store neither.

### 3. Clause is domain-neutral; only IR carries a domain profile

`Clause` models an ordered hierarchical path and nothing domain-specific:

| field | meaning |
|---|---|
| `clause_path` | rendered address — `제2장/제8조/제1항/제3호`, `Part 892/Subpart C/§892.2050(b)(2)` |
| `path_segments` | ordered array backing `clause_path`, for prefix queries and tree ops |
| `level` | depth |
| `ordinal` | sibling order |
| `text` | clause body in this version and language |
| `heading` | optional caption |

화장품법's 조/항/호 and 21 CFR's part/subpart/section/paragraph are both ordered hierarchical paths;
neither needs a domain-specific field. **Falsification criterion:** if the W5-6 cross-domain check
requires a Cosmetic-only column on `Clause`, or a second parser stage before Section Extraction, the
shared-pipeline assumption has failed and Phase 2 must be re-planned. Escalate immediately rather
than adding the column.

Domain divergence lives in `IR.domain_profile` (`samd` | `cosmetic`) and the extraction rules keyed
by it — exactly where import-agent.md says the branch belongs.

### 4. A citation names an immutable version, never "current"

`Citation = (document_id, document_version_id, clause_path, effective_date)`.

Pointing a citation at a Document and resolving "latest" at read time means a stored answer's
evidence silently changes when the regulation is amended — which destroys the audit trail the
product is sold on. Citations are pinned to a `DocumentVersion`, which is immutable once written.

Superseded citations are *detected and flagged*, never rewritten: when a `ClauseDiff` touches a
clause path that existing citations point at, those citations are marked `superseded` and the
answers carrying them are queued for re-verification. That queue is a product feature (it is how
"missed amendment impact analyses = 0" becomes measurable), not a maintenance chore.

### 5. DocumentVersion is per (document, version, language)

> **Not exercised in Phase 1.** Both gated cells are MFDS and Korean-only, so multilingual handling
> is modelled here but not built. The EU spike is where it first gets touched, at reduced depth.

EU acts publish in 24 languages; NMPA is Chinese-only; MFDS is Korean. Storing one version row with
N text columns makes diffing language-dependent in a single row and blocks per-language parser
profiles.

`DocumentVersion(document_id, version_label, language, ...)` with a shared `version_group_id`
joining language variants of the same act. **Diffs are computed within one language** — the
authoritative one per cell (EN for EU, KO for MFDS, ZH for NMPA, EN for FDA). Other languages are
retained for citation display and source-alongside rendering, not for change detection.

### 6. WORM archive is content-addressed; re-fetch with an unchanged hash creates nothing

`raw_object_key = sha256(bytes)`. A `DocumentVersion` references the blob; the blob is written once
and never mutated. A scheduled re-fetch that yields the same hash records a `fetch_observation`
(proving the source was checked at time T) but creates no new version — so "we looked and nothing
changed" is auditable without version churn.

A new hash creates a new `DocumentVersion`, which triggers parse → diff → `ChangeEvent`.

### 7. Clause identity survives renumbering via an explicit mapping, not heuristics

`clause_path` is the join key for diffing, but amendments renumber clauses. Diffing on path alone
reports a renumbered-but-unchanged clause as delete+add, which would generate false change alerts —
directly attacking the detection-coverage and false-positive story.

`ClauseDiff` records `change_kind ∈ {added, removed, modified, renumbered, moved}`, and renumbering
is resolved by content similarity plus explicit mapping rows, reviewed by RA when confidence is low.
This is a Phase 1 requirement, not a refinement: MFDS 고시 renumber routinely.

## Schema sketch

Illustrative, not final — column types settle when the migration is written.

```sql
cells(id, authority, domain, UNIQUE(authority, domain))          -- exactly 8 rows, seeded
sources(id, cell_id, block, ordinal, title, url_template, tier, ingestible, ...)
  -- url_template holds a credential placeholder, never a resolved URL (ADR-0003 dec 13)
documents(id, canonical_key, title, doc_type, issuing_authority)
document_cells(document_id, cell_id)                             -- M:N, decision 1
document_versions(id, document_id, version_group_id, version_label, language,
                  effective_date, published_date, retrieved_at,
                  raw_object_key, parser_version)                -- immutable
clauses(id, document_version_id, clause_path, path_segments, level, ordinal, heading, text)
clause_diffs(id, from_version_id, to_version_id, clause_path, change_kind,
             from_clause_id, to_clause_id, similarity)
change_events(id, clause_diff_id, cell_id, severity, detected_at)
standard_references(id, number, edition, body, recognition_number,
                    effective_date, withdrawal_date, status, official_url)   -- no text column
irs(id, domain_profile, statement, status, locked_at, llm_provider, llm_model)
ir_citations(ir_id, document_version_id, clause_path, effective_date, superseded_at)
ir_standard_citations(ir_id, standard_reference_id)
```

`irs.llm_provider` / `llm_model` follow the provenance convention in `.claude/skills/service-endpoint`
— any row an LLM produced records what produced it.

## Open questions

1. **Embedding granularity** — clause, paragraph, or sliding window? Affects retrieval quality and
   index size; needs measurement against the golden query set, not a guess. Blocks the retrieval ADR,
   not this one.
2. ~~**IR versioning**~~ — resolved in [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md)
   decision 5: re-derive as a new IR with a `supersedes` link, never mutate a locked IR in place.
   Control mappings are carried forward on RA confirmation rather than automatically.
3. **`canonical_key` derivation** — what makes 화장품법 the same Document across a title change?
   **Phase 1 needs only the MFDS answer** (법령ID / 고시번호). *(Later: ELI URI for EU, CFR citation
   for FDA; NMPA has no stable identifier and may need a curated key — deferred.)*
4. ~~**Effective date vs. published date for diff ordering**~~ — resolved in
   [ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 5: three separate dates
   (`retrieved_at`, `published_at`, `effective_date`), none substituting for another.
   `effective_date` is parse-derived and overridable per clause for staged application; alerting
   uses the clause-level date where present.

## What this unblocks

Connector data contracts (W1-2), parser profiles and clause schema (W3-4), and the retrieval index.
Next: an ingestion and change-detection contract ADR, then IR extraction and domain branching.
