# ADR-0007 — Context map and applicability

- **Status:** Proposed
- **Date:** 2026-07-29
- **Depends on:** [ADR-0002](ADR-0002-canonical-regulation-model.md), [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md), [ADR-0005](ADR-0005-service-architecture.md)
- **Resolves:** ADR-0003 open deferral (product-profile routing, decision 8), ADR-0005 open question 2 (applicability has no owner)
- **Blocks:** Phase 2 gap analysis — it cannot start without this

---

## Context

Two product pillars have no model. RegOps.md pillar 01 routes changes against "product, market, and
business-unit profiles so only the affected organizations are notified"; pillar 03 delivers an
"IR-to-control matrix". ADR-0003 decision 8 deferred the first ("routing to product profiles sits
above this and is out of scope here") and ADR-0005 open question 2 recorded that the second has no
owning service.

The consequence is concrete: **an IR currently applies to a `cell`, not to a product.** So alerting
can only say "something in your cell changed" — which is the noise problem the monitoring pillar
exists to eliminate — and gap analysis has no way to state which obligations are even in scope.

The prior platform (MedOps) used a nine-domain decomposition. Four carry over, because RegOps' core
domain is different: MedOps' core was *product-development compliance* (engineering → clinical →
quality → submission) for one company's own device; RegOps' core is *regulatory knowledge and
applicability*, sold to others.

## Decisions

### 1. Four bounded contexts — and a context is not a service

| Context | Owns | Tenancy |
|---|---|---|
| **Platform Core** | identity, roles, audit trail | shared |
| **Regulation** | Source, Document, Clause, ClauseDiff, ChangeEvent, StandardReference, IR | **shared reference data** |
| **Product** | product profiles — the attributes applicability is decided against | **tenant-scoped** |
| **Compliance** | applicability statements, control mappings, gap findings, corrective actions | **tenant-scoped** |

Deliberately excluded, with reasons:

- **AI Engineering is not a context.** It has no ubiquitous language or invariants of its own — its
  rules ("no answer without evidence", citation enforcement) are Regulation and Compliance invariants
  that it executes. ADR-0005 made `assistant` a *service* for failure isolation, which is a
  deployment boundary, not a modelling one. Treating RAG as a domain pulls domain rules into the LLM
  layer, where they are hardest to audit.
- **Quality is upstream and external** — see decision 5.
- **Engineering and Clinical are out of scope entirely.** No repos, no `software_versions`, no
  clinical gates. RegOps *cites* ISO 14971; it does not run approvals against it.

**Four contexts, four Phase 1 services** ([ADR-0009](ADR-0009-service-boundaries-per-pillar.md);
three at the time this ADR was written). Product and Compliance get their own models and language
immediately but live inside the `regulation` service until Phase 2 gap analysis gives them a reason
to split — at which point ADR-0009 decision 5 ships them together as `compliance`. Conflating
context with service is how a 6.5-FTE team ends up operating nine deployments.

### 2. The context boundary is the tenancy boundary

ADR-0005 decision 2 split shared from tenant-scoped data on pragmatic grounds. The context map
explains *why* the line falls there, and makes it a rule rather than a judgement:

> 화장품법 is the same 화장품법 for every customer. **Regulation is shared because it is a fact about
> the world. Product and Compliance are tenant-scoped because they are facts about a customer.**

This yields a hard constraint: **applicability must not live in the Regulation context.** Putting it
there would make shared reference data tenant-dependent, and Phase 3's multi-tenant model collapses —
every customer would need their own copy of the regulation corpus.

### 3. Applicability = Product × Regulation → Compliance

An IR is a fact about a regulation. Whether it applies to *your* product is a fact about you. The
determination is therefore a Compliance-context artefact that *references* both sides and mutates
neither.

```text
   Regulation                Product                    Compliance
   (shared)                  (tenant)                   (tenant)
   IR ─────────────┐    ┌─── ProductProfile
                   ▼    ▼
              ApplicabilityStatement ──< entries (applicable | excluded | undetermined + justification)
                        │
                        └──< ControlMapping ──→ (external control ref, decision 5)
```

### 4. Applicability is evaluated from typed attributes, and `undetermined` is first-class

A product profile is a set of **typed attributes keyed by domain**, not free text, because
applicability conditions have to be evaluable:

| `cosmetic` | `samd` |
|---|---|
| 제품 유형 (일반 / 기능성) · 기능성 종류 · 사용 부위 · 사용 원료 · 제조 or 책임판매 · 판매 지역 | 등급 (1–4) · 품목분류 · AI 탑재 여부 · 소프트웨어 독립형 여부 · 판매 지역 |

Each IR carries applicability conditions captured at extraction (ADR-0004's `condition_text`).
Evaluation yields one of three states — never two:

- `applicable` — condition satisfied
- `excluded` — condition demonstrably not satisfied, **with a recorded justification**
- `undetermined` — cannot be decided from the profile

**`undetermined` must not collapse into either neighbour**, and the asymmetry is the reason. Wrongly
marking an obligation *excluded* hides a legal duty and produces a confidently incomplete gap report;
wrongly marking it *applicable* produces noise. The failure costs are not symmetric, so the system
never guesses — `undetermined` routes to RA adjudication, exactly as "needs verification" does for
answers (ADR-0006 decision 7).

Evaluation is a **rule engine, not an LLM judgement.** An LLM may *propose* the condition structure
during extraction; deciding whether a given product meets it must be deterministic and replayable, or
the resulting Statement of Applicability cannot be defended in an audit.

### 5. Quality is an upstream external context, reached through an anti-corruption layer

Phase 2 integrates customer SOPs and technical documents for gap analysis. We **consume** them; we do
not own or manage them.

`ControlMapping` references an external control by `(system, external_id, external_version, url)` and
stores our own minimal projection — title, owner, last-reviewed date. The customer's document model,
lifecycle and states stay on their side of the boundary.

Without this ACL, their QMS schema leaks into our IR model, and every customer's QMS differs. That
is how a multi-tenant product acquires per-customer schema.

### 6. Aggregates, each with a named invariant owner

The invariants exist across ADR-0002/0004/0006 but nothing said *what enforces them*. Naming the
aggregate names the transaction boundary:

| Aggregate | Root | Invariant it enforces |
|---|---|---|
| `DocumentVersion` + its `Clause`s | DocumentVersion | immutable once written; clauses never edited in place (ADR-0002 dec 4, 6) |
| `IR` + its `Citation`s | IR | **≥ 1 citation or the IR does not exist**; `locked` is terminal — amendments supersede (ADR-0004 dec 2, 5) |
| `StandardReference` | itself | no body text can be stored — structurally, not by policy (ADR-0002 dec 2) |
| `ProductProfile` | itself | attributes conform to the domain's typed schema |
| `ApplicabilityStatement` + entries | statement | every in-scope IR has exactly one entry; `excluded` requires a justification |
| `ControlMapping` | itself | references an external control, never embeds one (decision 5) |
| `Answer` + its `Citation`s | Answer | every claim cites a retrieved clause (ADR-0006 dec 4) |

### 7. Two names are overloaded; both are resolved here

- **Citation** — `ir_citations` (derivation provenance) and `answer_citations` (evidence for a
  generated claim) are *different concepts sharing a shape*. Already separated in ADR-0006 dec 10;
  recorded here as a context boundary, since they live in Regulation and `assistant` respectively.
- **Document** — a regulation Document (Regulation context) and a customer's internal SOP are not the
  same thing. The latter is a **`ControlDocument`** in the Compliance context. Never `Document`.

### 8. Change routing, finally closed

`ChangeEvent` (Regulation) → the IRs citing the changed clauses → the `ApplicabilityStatement`
entries referencing those IRs → the owning tenant and assigned owner.

This is what turns "something in your cell changed" into "IR-142 applies to your 기능성화장품 A and
its cited clause was amended, effective 2026-10-01" — and it is the closure of ADR-0003 decision 8.

An IR whose entry is `excluded` still generates a **re-review prompt**, not silence: an amendment can
turn a previously excluded obligation into an applicable one, and that transition is precisely the
gap the product exists to catch.

## Schema additions

```sql
product_profiles(id, tenant_id, domain, name, attributes_jsonb, created_at)   -- attributes typed per domain
applicability_statements(id, tenant_id, product_profile_id, cell_id, generated_at, status)
applicability_entries(statement_id, ir_id, state, justification, decided_by, decided_at)
   -- state: applicable | excluded | undetermined
control_documents(id, tenant_id, system, external_id, external_version, title, owner, url)
control_mappings(id, tenant_id, ir_id, control_document_id, rationale, confirmed_by, confirmed_at)
gap_findings(id, tenant_id, statement_id, ir_id, kind, severity, opened_at, closed_at)
```

## Open questions

1. **Applicability rule expression** — how is a condition stored so it is both human-reviewable and
   machine-evaluable? A small DSL, a JSON predicate tree, or structured attribute constraints?
   Reviewability by RA is non-negotiable, which argues against anything code-like.
2. **Product profile versioning** — a product changes (new ingredient, reclassified device). Does the
   Statement of Applicability version with it, or is it regenerated? Regeneration is simpler;
   versioning preserves what was assessed at submission time, which is what an auditor asks for.
   Leaning versioned.
3. **Multi-market products** — one product sold in KR and EU has different applicable sets. One
   statement per `(product, cell)` or one spanning statement? The schema above assumes per-cell.
4. **Who owns Product** — it is tenant-scoped and small in Phase 2, but if product data grows (BOM,
   ingredient lists, formulations) it may outgrow the `regulation` service. Revisit at Phase 2 exit.

## What this unblocks

Phase 2 gap analysis and impact-scoped alerting. With this, the seven ADRs cover the full Phase 1–2
path: platform foundation, canonical model, ingestion, IR extraction, service architecture,
retrieval, and applicability.
