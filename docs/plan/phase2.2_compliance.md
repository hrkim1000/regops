# Phase 2.2 — Compliance: applicability, control mapping, gap analysis

- **Roadmap:** Phase 2 (M5–12) · **Status:** ⬜ planned
- **Governed by:** [ADR-0007](../design/ADR-0007-context-map-and-applicability.md), [ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) decision 5
- **Depends on:** [phase1.2](phase1.2_ir_extraction.md) (locked IRs)
- **Service:** `compliance` — splits out of `regulation` here

---

## Goal

Answer two questions the knowledge layer cannot: *does this obligation apply to us*, and *what have
we done about it*. This is pillar 03, and it is where the platform stops being a reference tool and
starts producing findings.

It is also where the tenancy line matters most. 화장품법 is the same 화장품법 for every customer; what
differs is which obligations apply to them and what they have done about it.

## Scope

**In:** the Product and Compliance bounded contexts, applicability, IR-to-control mapping, gap
findings, corrective actions, SOP and technical-document integration.

**Out:** the regulation corpus itself. `compliance` reads locked IRs; it never writes a `regulation`
table.

## Tasks

### Service split

- [ ] `compliance` becomes its own deployment unit, carrying the Product and Compliance contexts out of `regulation`
- [ ] **All tables tenant-scoped**, `tenant_id` carried from the Phase 1 migration — no retrofit
- [ ] Reads locked IRs by raw SQL across the boundary; drafts remain invisible

### Product context

- [ ] Product profiles — the attributes applicability is decided against: product type, device class, market, business unit
- [ ] **Applicability must not sit in the Regulation context**, or shared reference data becomes tenant-dependent and Phase 3 stops being tractable
- [ ] `Product × Regulation → Compliance` as the applicability relation

### Applicability

- [ ] Applicability statements per `(product, IR)` with a recorded basis
- [ ] Resolves [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 3 in practice — the IR carries the class condition; **Compliance evaluates it**
- [ ] Decide: LLM-proposed with an RA gate, or rule-derived from IR attributes. Rule-derived is auditable; LLM-proposed needs a lock analogous to IR locking

### Control mapping

- [ ] IR-to-control matrix against internal SOPs, controls, and technical documents
- [ ] **Re-derivation path** — when an amendment invalidates a mapping, affected mappings are recomputed and flagged for RA review rather than silently retained
- [ ] Carry-forward is **proposed automatically and confirmed by RA**. An amendment that narrows an obligation may invalidate the control that satisfied it, and that is precisely the gap the product exists to find

### Gap analysis

- [ ] Gap findings: obligations with no mapped control, or with a control invalidated by amendment
- [ ] Corrective action list with owners and status
- [ ] Coverage claims rest on `clause_classifications` — provable, not assumed

### Monitoring upgrade

- [ ] `monitoring` routes on **product** rather than cell once Product exists — the noise problem pillar 01 exists to solve
- [ ] Impact grading gains propagation paths from [phase2.1](phase2.1_semantic_graph.md)

### RBAC

- [ ] `compliance` role arrives here — there is now a control-mapping surface to gate

## Acceptance criteria

- [ ] Gap analysis lead time reduced ≥ 50%
- [ ] Missed amendment impact analyses = **0**, verified by quarterly retrospective audit: an RA-selected sample of real amendments per cell checked against what the system detected. Without a defined audit this metric is unfalsifiable
- [ ] Regulatory research time reduced ≥ 40%
- [ ] Monthly active users ≥ 300 — **denominator stated at Phase 2 kickoff**
- [ ] An amendment narrowing an obligation surfaces the affected mapping for review rather than carrying it forward
- [ ] No `compliance` table lacks `tenant_id`; no `regulation` write from `compliance`

## Risks & open questions

- **Applicability is the highest-liability inference in the product.** Getting "this does not apply to you" wrong is worse than a hallucinated answer, because there is no citation for the user to check. Whatever the mechanism, it needs a human gate and an audit record.
- **Internal document ingestion brings PII/PHI into scope** for the first time — encryption at rest and in transit, anonymized logs, RBAC re-checked server-side.
- **Risk 3 — underestimated compliance workload.** Assign quality staff from Phase 2 start with explicit artifact owners.

## Deviations & decisions

_None yet._
