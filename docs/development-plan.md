# RegOps Development Plan

---

## 1. Objective

Build RegOps as a citation-traceable regulatory platform for life sciences teams, with a staged path from internal validation to external SaaS.

Primary outcomes:
- Detect regulatory changes and route actionable alerts
- Answer regulatory questions with clause-level citations and version metadata
- Map InfoRequirement (IR) to internal controls and documents for gap analysis
- Prepare a validated, multi-tenant SaaS operating model

---

## 2. Scope and Non-Scope

In scope:
- Tier A/B data ingestion in initial build; Tier C in expansion
- Clause-level normalization, diffing, retrieval, and evidence-aware answer generation
- RBAC, audit logging, and traceability primitives required for regulated workflows
- PoC and expansion metrics, with stage gates tied to measurable outcomes

Out of scope (until Phase 3 readiness):
- Full global regulator scraping coverage from day one
- Immediate replacement of incumbent suite tooling
- Tier D source-text ingestion (metadata and citation links only)

---

## 3. Delivery Principles

- No answer without evidence; unanswered queries return needs verification
- Every generated result is auditable to source document, version, and retrieval context
- Keep the knowledge graph and IR mapping as the long-lived asset
- Ship in small increments with explicit Go/No-Go checkpoints
- Keep regulatory experts embedded in the delivery loop

---

## 4. Workstreams

1. Data and Ingestion
- Connectors for openFDA, Federal Register, MFDS, and selected public APIs/RSS
- Immutable source archive and scheduled change detection
- Tier C scraper framework with structure-change monitoring (Phase 2)

2. Normalization and Knowledge Layer
- Parsing, clause segmentation, multilingual support, and version control
- Clause-level diff extraction and amendment traceability
- Regulatory graph entities and impact-propagation links

3. Retrieval and AI
- Hybrid retrieval (BM25 + vector) and graph context expansion
- Citation-enforced generation with confidence scoring
- Evidence-verification step and human-review routing below threshold

4. Applications and Integrations
- Monitoring dashboard and alert routing
- Regulatory Q&A workbench with citation links and history
- Gap analysis workspace and action tracking
- API and partner integration surface

5. Platform and Compliance
- RBAC and service-level authorization checks
- Audit trail, model version pinning, and regression harness
- Part 11 readiness controls, validation artifacts, and tenancy boundaries

---

## 5. Milestone Plan (24 Months)

### Phase 1 (Month 0-4): PoC Validation

Goals:
- Validate technical feasibility and user value in two regulatory areas
- Prove trust metrics around detection and citation quality

Deliverables:
- Tier A/B ingestion connectors and source archive
- Monitoring dashboard and citation-enforced Q&A
- Golden query set and evaluation harness

Exit criteria:
- Detection coverage >= 95%
- Detection latency <= 24h
- Citation accuracy >= 90%
- Hallucination rate <= 2%
- Pilot retention >= 60%

### Phase 2 (Month 5-12): Internal Scale

Goals:
- Expand regulator coverage and operational adoption
- Add compliance gap analysis and IR mapping depth

Deliverables:
- Tier C ingestion pipeline with resilience controls
- Regulatory graph expansion and control mapping workflow
- SOP/technical-document integration for impact analysis

Exit criteria:
- Regulatory research time reduced by >= 40%
- Gap analysis lead time reduced by >= 50%
- Missed amendment impact analyses = 0
- Monthly active users >= 300

### Phase 3 (Month 13-24): External SaaS

Goals:
- Productize as multi-tenant offering with validation package
- Establish partner/API channel and initial ARR

Deliverables:
- Tenant isolation, billing/ops boundaries, and API governance
- Validation package and external audit readiness process
- Pilot customer onboarding and partner channel enablement

Exit criteria:
- Paying customers >= 8
- ARR >= KRW 2B
- NRR >= 110%
- Validation audits passed = 100%

---

## 6. Near-Term Sprint Plan (First 12 Weeks)

Weeks 1-2:
- Confirm source priority list, legal constraints, and architecture boundaries
- Finalize data contracts for first connectors

Weeks 3-4:
- Implement first ingestion connectors and source archiving
- Define IR extraction rules and clause schema

Weeks 5-6:
- Build normalization pipeline and versioned clause store
- Add baseline retrieval index and observability metrics

Weeks 7-8:
- Deliver monitoring dashboard alpha and alert routing
- Add citation-enforced answer generation path

Weeks 9-10:
- Add evidence-verification checks and confidence gating
- Conduct RA review rounds against golden query set

Weeks 11-12:
- Pilot onboarding (20-30 users), issue triage, and metric collection
- Prepare Phase 1 Go/No-Go report and Phase 2 backlog

---

## 7. Ownership Model

- Regulatory domain (RA/QA): IR quality, golden set design, acceptance criteria
- Data engineering: connectors, ingestion reliability, normalization throughput
- AI/ML engineering: retrieval quality, citation precision, confidence calibration
- Product/frontend: workflow UX, dashboard, and alert/action loop
- Security/compliance: audit controls, validation package, and policy gates

Decision rights:
- Product scope: product lead + domain lead
- Regulatory interpretation conflicts: domain lead final signoff
- Release readiness in regulated scope: QA/compliance gate required

---

## 8. Quality Gates and Definition of Done

Feature-level DoD:
- Unit/integration tests pass
- Retrieval and citation acceptance checks pass
- Audit logs emitted for critical actions
- RBAC enforced and negative-path checks included

Release-level gates:
- No unresolved Sev-1 defects
- Regression pass on golden query set
- Updated runbook, rollback notes, and KPI snapshot attached

---

## 9. Risk Register (Execution-Focused)

1. Source instability (especially scraping targets)
- Mitigation: schema-drift detection, connector health alerts, manual fallback playbooks

2. Citation quality regression under model change
- Mitigation: model pinning, evaluation baselines, canary rollout for retrieval/generation

3. Underestimated compliance workload
- Mitigation: parallel validation workstream from Phase 2 start, explicit artifact owners

4. Adoption risk despite technical success
- Mitigation: pilot champion program, workflow integrations, measurable time-saving goals

---

## 10. Reporting Cadence

Weekly:
- Build status by workstream, blocker log, and risk trend

Bi-weekly:
- KPI dashboard update (coverage, latency, citation quality, adoption)

Stage gate review:
- End-of-phase decision memo with metric evidence and budget recommendation

---

## 11. Immediate Next Actions (Next 30 Days)

1. Form cross-functional task force and approve Phase 1 backlog
2. Complete source/legal review for Tier A/B connector list
3. Deliver first ingestion run for openFDA + MFDS-related public sources
4. Build initial golden query set and RA scoring rubric
5. Start pilot recruitment and usage baseline capture
