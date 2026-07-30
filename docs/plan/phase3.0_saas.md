# Phase 3.0 — External SaaS

- **Roadmap:** Phase 3 (M13–24) · **Status:** ⬜ planned
- **Governed by:** [ADR-0005](../design/ADR-0005-service-architecture.md) decision 2, [ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) decision 4
- **Depends on:** Phase 2 exit
- **Service:** `tenancy` — the last service

---

## Goal

Turn the validated internal platform into a multi-tenant product. The architecture work was done in
Phase 1: tenant-scoped tables have carried `tenant_id` since the first migration, so this phase
builds the surface around tenancy rather than retrofitting the discriminator under commercial
pressure.

## Scope

**In:** tenant provisioning, billing, API keys, white-label configuration, the validation package,
partner channel.

**Out:** multi-tenancy itself — it is cross-cutting. Every service is tenant-aware; `tenancy` owns
the lifecycle around tenants, not their isolation.

## Tasks

### `tenancy` service

- [ ] Tenant provisioning and lifecycle
- [ ] Billing and plan boundaries
- [ ] API keys and rate limiting
- [ ] White-label configuration
- [ ] **Not** tenant isolation — that is enforced in every service by `tenant_id`

### Isolation hardening

- [ ] Row-level enforcement audited across every tenant-scoped table
- [ ] Cross-tenant leakage tests as a release gate, not a one-off audit
- [ ] Regulation data confirmed **shared** — one copy of 화장품법 for everyone; only the mapping layer is per-tenant
- [ ] Regional data residency — storage location by region answerable at contract level (GDPR, Korea PIPA, China data regulations)

### Partner API

- [ ] Public API surface, versioned `/api/v1/`
- [ ] Resolve [ADR-0005](../design/ADR-0005-service-architecture.md) open question 4 — does the frontend need a BFF, and does the partner API share it
- [ ] Partner onboarding docs and sandbox

### GxP validation package

- [ ] **CSA-based validation** — risk-based per the FDA's September 2025 final guidance; supplier deliverable requirements remain
- [ ] **21 CFR Part 11** — tamper-evident audit trails, electronic signature controls, user activity logging. SOC 2 and ISO 27001 alone are not sufficient
- [ ] Resolve [ADR-0005](../design/ADR-0005-service-architecture.md) open question 3 if still open — audit-trail immutability enforced, not conventional
- [ ] Quality agreement, data retention policy, archive integrity, customer audit acceptance structure
- [ ] SOC 2 certification

### Commercial

- [ ] Pilot customer onboarding — domestic pharma and medical device companies
- [ ] CRO / consulting partner channel enablement
- [ ] Position as a complement for change detection and impact analysis rather than a head-on suite replacement; secure references before incumbent agentic features ship

## Acceptance criteria

- [ ] Paying customers ≥ 8
- [ ] ARR ≥ KRW 2B
- [ ] NRR ≥ 110%
- [ ] Validation audits passed = 100%
- [ ] Partner channel share ≥ 30%
- [ ] Zero cross-tenant data exposure across the full test suite

## Risks & open questions

- **Risk — underestimating GxP validation cost.** Part 11, quality agreements and customer audit response are organizational capabilities that precede the product. Quality staff from Phase 2, certification and consulting costs pre-allocated in the Phase 3 budget.
- **EU AI Act applicability to RegOps itself.** AI embedded in medical devices applies from 2028-08-02; transparency obligations from 2026-08-02. Document the product to a level that supports a high-risk classification, and turn the dual position — subject of regulation *and* tool for regulatory response — into a marketing asset.
- **Suite bundling competition.** Existing customers choose bundles for integration convenience; the entry wedge is change detection and impact analysis, not replacement.

## Deviations & decisions

_None yet._
