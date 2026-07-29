# ADR-0001 — Platform foundation: greenfield vs. extending the existing SaMD platform

- **Status:** **Accepted — Option A (greenfield, reuse conventions only)**, 2026-07-29
- **Date:** 2026-07-29
- **Deciders:** product lead + domain lead (per development-plan.md § 7 decision rights)
- **Blocks:** every subsequent design doc — table names, service boundaries, RBAC roles, and
  whether `regops_shared` exists at all depend on this

---

## Context

This repository contains strategy documents and no code (3 commits, docs only). But
`.claude/skills/` describes a **fully specified, apparently existing platform** — and it is not
the platform described in `docs/`.

Vocabulary overlap between the two, measured across both directories:

| Term | `.claude/` | `docs/` |
|---|:--:|:--:|
| SW Profile DB, git-agent, `software_versions`, device release | ✅ | ❌ |
| `clinical_expert`, 6 clinical gates (ISO 14971, CER), per-section signoff | ✅ | ❌ |
| `regops_shared`, audit-log service, ScopeBar, Tele/FA/DDH | ✅ | ❌ |
| cell, Cosmetic, NMPA, change monitoring, Tier D, import-source-map | ❌ | ✅ |

Zero overlap in both directions. `.claude/` describes a SaMD submission-and-traceability platform
for a medical imaging product: GitLab releases → software versions → device release → per-section
signoff → submission package, gated by clinical HITL approvals. `docs/` describes a regulatory
knowledge platform: 8 cells (SaMD·Cosmetic × MFDS·FDA·EU·NMPA), change monitoring, citation-traceable
Q&A, compliance gap analysis, and a Phase 3 external multi-tenant SaaS.

The two share real substance — **IR is the same concept in both**. The glossary defines it as "one
atomic regulatory obligation extracted from a regulation, with a mandatory citation," mapped M:N to
documents; RegOps.md defines the same thing mapped to SOPs and controls instead of SW Profile DB
fields. IR extraction with enforced citation is the hardest part of RegOps' L1–L3, and it may
already exist.

`.claude/` also references ADR-0002, ADR-0005 and ADR-0006, none of which exist in this repo —
further evidence the scaffolding was carried over from another codebase.

## Decision drivers

1. **Phase 1 is 16 weeks at 6.5 FTE**, and its gates are all detection and citation *quality* — not
   platform completeness. Weeks spent rebuilding auth, audit, migrations and a service skeleton are
   weeks not spent on the gates.
2. **Phase 3 is an external multi-tenant SaaS.** Whatever RegOps is coupled to in Phase 1 must be
   separable by Month 13, or the coupling becomes an extraction project.
3. **The 8-cell model has no home in the existing schema.** There is no region or domain axis in
   anything `.claude/` describes; it is shaped around one product in one jurisdiction.
4. **Cosmetics does not fit the clinical model.** An RBAC scheme built on `clinical_expert` and six
   ISO 14971 gates has no meaning for 화장품법 compliance.
5. **IR extraction may be reusable**, and it is the most expensive component to build well.

## Options

### A. Greenfield — reuse conventions only

New codebase. Inherit the stack conventions that are product-neutral and good: response envelope
`{code, status, message, data, meta}`, URL-versioned `/api/v1`, single Alembic history with shared
canonical models, pgvector at 768-dim with `nomic-embed-text`, the `get_llm_client()` provider seam,
Celery one-queue-per-service, Docker Compose dev loop. Discard the product-specific layer.

- **+** 8-cell model designed without constraint; cosmetics is a first-class domain, not a graft
- **+** RBAC designed for RA workflows from the start
- **+** Phase 3 SaaS extraction is a non-issue — nothing to extract from
- **+** Tier D enforcement can be built into the archive layer from commit one
- **−** Rebuilds auth, audit trail, migration baseline, service skeleton, frontend shell — real
  weeks against a 16-week Phase 1
- **−** Rebuilds IR extraction, the component most likely to already work

### B. Extend the existing platform

Add a Regulation Domain service to the existing codebase. Inherit `regops_shared`, its tables, its
RBAC, and its IR pipeline.

- **+** Fastest path to a first connector; auth/audit/migrations/LLM seam already working
- **+** IR extraction with citation enforcement and lock semantics already exists
- **+** One stack, one team, one dev loop
- **−** Grafting a region×domain axis onto a schema with neither
- **−** Cosmetics inside a clinically-gated RBAC model is a poor fit and will leak into UX
- **−** Phase 3 requires extracting RegOps from an internal product platform — the cost lands
  exactly when commercial pressure is highest
- **−** Couples RegOps' release cadence to another product's

### C. Greenfield + extract the shared core

Build RegOps greenfield, but lift the ingestion/normalization/IR core into a library both platforms
consume.

- **+** Keeps the expensive component shared without coupling the products
- **−** Requires coordination with the other platform's owners and a stable library contract before
  either side moves fast — a poor fit for a 16-week PoC, and a good fit for Phase 2

## Open questions — these decide it

The recommendation below is conditional. It cannot be finalized without:

1. **Does the existing platform ingest regulations and extract IRs at production quality today**, or
   does it consume IRs authored by hand? If ingestion is real and good, B's advantage is months, not
   weeks, and C becomes attractive.
2. **Is the existing platform multi-tenant capable**, or single-tenant internal? If single-tenant,
   B's Phase 3 cost is severe.
3. **Is the same team maintaining both?** If not, B trades build time for coordination cost.
4. **Does its clause/document model carry version and effective-date metadata per clause?** RegOps'
   citation contract requires it; a model without it cannot be reused for the Q&A pillar regardless
   of the other answers.

## Decision

**Option A — greenfield, reusing stack conventions only.** Taken 2026-07-29 without waiting on the
open questions below; the decision was made on the structural argument rather than on a build-speed
comparison, so the open questions no longer gate it. They are retained because question 1 still
determines whether **Option C** is worth revisiting at the Phase 2 boundary — if the existing
platform's IR extraction is production-quality, extracting it into a shared library once both sides
know the contract remains the better long-run answer than either side rebuilding it.

Consequences of A are listed below and are now action items, not hypotheticals.

## Recommendation (as argued before the decision)

**Option A**, unless the answer to open question 1 is a clear yes.

The deciding factor is not build speed — it is that RegOps' scope axis (8 cells, two domains, four
regions) and its Phase 3 destination (external multi-tenant SaaS) are both structurally absent from
the existing platform. Grafting them on means paying the modelling cost anyway, and then paying the
extraction cost again at Month 13.

If question 1 is a clear yes, revisit as **Option C** at the Phase 2 boundary: run Phase 1 greenfield
to hit the gates, then extract the shared IR core once both sides know what the contract should be.

## Consequences

**If A is chosen:**

- `.claude/skills/glossary` must be rewritten for RegOps. It currently auto-invokes on every document
  and pushes SW Profile DB / clinical_expert / device release terminology that has no meaning here —
  it will actively misdirect both people and agents.
- `.claude/skills/db-migration`, `service-endpoint`, `frontend-page`, `testing` are largely reusable;
  strip the product-specific examples and keep the conventions.
- RegOps ADRs are numbered from 0001 in `docs/design/`. The ADR-0002/0005/0006 references inside
  `.claude/skills/` belong to the other platform and should be removed with the glossary rewrite.
- RBAC roles must be defined for RegOps rather than inherited (`clinical_expert` and the six clinical
  gates do not apply; RA reviewer, approver and admin roles do).

**If B is chosen:**

- ADR-0002 must open with the region×domain axis grafting strategy, not with a clean model.
- A Phase 3 extraction plan becomes a Phase 2 deliverable, not a Phase 3 discovery.

**Either way:**

- The architecture rules already in CLAUDE.md hold: 8-cell identity, `import-source-map.md` as the
  single source catalog, Tier D metadata-only, citation-enforced generation, WORM archive plus audit
  trail, no connectors on login-gated portals.

## Next

On resolution, ADR-0002 defines the canonical regulation data model — Cell, Source, Document,
DocumentVersion, Clause, Amendment/Diff, Citation, IR — which development-plan.md § 6 puts on the
critical path at W3-4.
