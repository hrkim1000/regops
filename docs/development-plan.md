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

Regulatory scope is fixed at two product domains x four regulatory regions (8 cells total):

| Domain | MFDS (Korea) | FDA (US) | EU (EC) | NMPA (China) |
|---|---|---|---|---|
| SaMD | 의료기기법, 디지털의료제품법, SW/AI review guidelines | FD&C Act, 21 CFR 820 (QMSR)/11/803/806/807, SaMD & AI/ML guidance | MDR (EU) 2017/745, IVDR (EU) 2017/746, MDCG guidance, EUDAMED | Regulations for the Supervision and Administration of Medical Devices, software & AI device registration guidance, YY standards |
| Cosmetic | 화장품법, 안전기준 규정, 기능성화장품 심사 규정 | FD&C Act, MoCRA, FPLA, 21 CFR 700/701/710/740 | Regulation (EC) No 1223/2009, CPNP, CosIng, SCCS opinions | CSAR, registration/filing measures, IECIC |

The authoritative per-cell inventory of laws, guidance, and official source URLs is docs/import-source-map.md. Connectors are built against that file; the table above is the summary.

In scope:
- The 8 domain x region cells above, and nothing outside them
- Tier A/B data ingestion in initial build; Tier C in expansion
- Clause-level normalization, diffing, retrieval, and evidence-aware answer generation
- RBAC, audit logging, and traceability primitives required for regulated workflows
- PoC and expansion metrics, with stage gates tied to measurable outcomes

Permanently out of scope (reopening requires an explicit scope decision):
- Product domains other than SaMD and Cosmetic: pharmaceuticals, biologics, hardware-only medical devices, food and health supplements
- Regulators other than MFDS, FDA, EU, and NMPA: PMDA, Health Canada, MHRA, TGA, ASEAN ACD, EMA drug procedures
- Tier D source-text ingestion (metadata and citation links only)

Out of scope until Phase 3 readiness:
- Full coverage of all 8 cells from day one (Phase 1 gates 2 cells; Phase 2 completes the matrix)
- Immediate replacement of incumbent suite tooling

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
- Connectors per scope cell: MFDS, openFDA/Federal Register, EUR-Lex/EC, NMPA — one connector + parser profile per domain x region
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

Gated cells: **MFDS SaMD + MFDS Cosmetic.** Holding the regulator constant and varying the domain is the only way to test the architecture's central claim — that Import → Normalization → Section Parsing is fully shared and only IR extraction branches by domain (see import-agent.md). If that claim is wrong, Phase 2 builds six cells on a broken assumption. Both cells are also Tier A (국가법령정보 API, MFDS RSS), so ingestion is not on the critical path for a trust-metric PoC.

Non-gated spike: **EU SaMD**, run in parallel at reduced depth to expose multilingual normalization and the first Tier C source (MDCG guidance) before Phase 2 commits to them. The spike does not count toward exit criteria and may use Tier C.

Goals:
- Validate technical feasibility and user value in 2 of the 8 scope cells, covering both product domains
- Prove trust metrics around detection and citation quality
- De-risk cross-jurisdiction normalization via the EU spike

Deliverables:
- Tier A/B ingestion connectors and source archive
- Monitoring dashboard and citation-enforced Q&A
- Golden query set and evaluation harness (per domain — SaMD and Cosmetic sets are scored separately)
- EU spike findings memo: multilingual and Tier C effort estimate for Phase 2

Exit criteria (6 gates — **No-Go if 4 or more fall short**):
- Detection coverage >= 95%
- Detection latency <= 24h
- Citation accuracy >= 90%
- Hallucination rate <= 2%
- Research time savings >= 30%
- Pilot retention >= 60%

Each gate is measured **per gated cell**. A cell that misses is not offset by the other passing. Measurement methods are defined in RegOps.md § Go/No-Go quantitative gates.

### Phase 2 (Month 5-12): Internal Scale

Goals:
- Complete the scope matrix (remaining 6 cells) and drive operational adoption
- Add compliance gap analysis and IR mapping depth

Deliverables:
- Tier C ingestion pipeline with resilience controls
- Multilingual normalization for Chinese (NMPA) and EU languages, source text retained alongside
- Regulatory graph expansion and control mapping workflow
- Re-derivation path: when an amendment invalidates existing IR-to-control mappings, the affected
  mappings are recomputed and flagged for RA review rather than silently retained
- SOP/technical-document integration for impact analysis

**Mid-phase checkpoint (M8)** — Phase 2 carries the two hardest new capabilities (Tier C scraping,
knowledge graph) across an 8-month span. Do not run it without an interim gate:
- 4 of 8 cells live and independently passing the Phase 1 trust gates
- Graph schema frozen
- Tier C connector health monitoring in production
- Miss any of these and re-plan the back half rather than continuing to M12

Exit criteria — technical (per cell, all 8):
- Detection coverage >= 95%
- Detection latency <= 24h
- Citation accuracy >= 90%
- Hallucination rate <= 2%

The Phase 1 thresholds do not retire at M4. Scaling from 2 to 8 cells while adding Tier C scraping
and two new source languages is exactly when detection coverage and citation quality degrade, so
every cell must clear them independently before Phase 2 closes.

Exit criteria — adoption:
- Regulatory research time reduced by >= 40%
- Gap analysis lead time reduced by >= 50%
- Missed amendment impact analyses = 0, verified by quarterly retrospective audit: an RA-selected
  sample of actual amendments in each cell is checked against what the system detected. Without a
  defined audit this metric is unfalsifiable
- Monthly active users >= 300 (denominator: target user population must be stated at Phase 2 kickoff)

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

## 6. Near-Term Sprint Plan (Phase 1, 16 Weeks)

Critical path: source map → parser profiles → clause schema → IR extraction rules → retrieval index
→ citation-enforced generation. Everything downstream of clause schema slips one-for-one with it;
the dashboard and alert routing are the only branches that can absorb slack.

Weeks 1-2:
- Confirm source priority list, legal constraints, and architecture boundaries
- Finalize data contracts for the two gated cells (MFDS SaMD, MFDS Cosmetic)

Weeks 3-4:
- Implement first ingestion connectors and source archiving
- Define IR extraction rules and clause schema — **critical path, do not defer**
- Start EU SaMD spike (multilingual + Tier C exposure), runs in background through W12

Weeks 5-6:
- Build normalization pipeline and versioned clause store
- Add baseline retrieval index and observability metrics
- First cross-domain check: confirm the shared pipeline holds for Cosmetic without forking
  Normalization or Section Parsing. If it forks, escalate immediately — this is the architecture bet

Weeks 7-8:
- Deliver monitoring dashboard alpha and alert routing
- Add citation-enforced answer generation path

Weeks 9-10:
- Add evidence-verification checks and confidence gating
- Conduct RA review rounds against both golden query sets (SaMD and Cosmetic scored separately)

Weeks 11-12:
- Freeze build; pilot onboarding (20-30 users) and baseline capture
- EU spike findings memo: multilingual and Tier C effort estimate for Phase 2

Weeks 13-16 (M4 — pilot and evaluation):
- Four weeks of real pilot usage — the retention gate requires 4 consecutive weeks of measurement
  and cannot be compressed
- Blind accuracy assessment by RA staff against both golden sets
- Per-cell metric collection against all 6 gates
- Phase 1 Go/No-Go report and Phase 2 backlog

---

## 7. Ownership Model

Staffing per phase (FTE, from RegOps.md § Organization):

| Role | Scope | P1 | P2 | P3 |
|---|---|--:|--:|--:|
| Regulatory domain (RA/QA) | IR quality, golden set design, acceptance criteria | 1 | 3 | 6 |
| Data engineering | Connectors, ingestion reliability, normalization throughput | 2 | 4 | 7 |
| AI/ML engineering | Retrieval quality, citation precision, confidence calibration | 2 | 4 | 8 |
| Product/frontend | Workflow UX, dashboard, alert/action loop | 1 | 3 | 6 |
| Security/compliance | Audit controls, validation package, policy gates | 0.5 | 1 | 3 |
| **Total** | | **6.5** | **15** | **30** |

Phase 1 budget: KRW 450M (see executive-summary.md § Decision Request).

Note the Phase 1 RA allocation of 1 FTE against risk 7 — a second RA reviewer is needed to separate
golden-set authorship from blind accuracy assessment.

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
- **Tier D clean**: no standard or pharmacopoeia body text in the archive or index. Standards are
  present as metadata only (number, edition, recognition number, effective/withdrawal date,
  harmonized status) plus a deep link to the official copy. This holds even where a regulation makes
  the standard legally binding — QMSR incorporates ISO 13485:2016 by reference; cite the
  requirement, link the standard, store neither
- **No connector on a login-gated portal** (EU CPNP, EUDAMED and equivalents). They are notification
  systems, not published regulation

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

5. Tier D copyright breach during development (rated High in RegOps.md)
- A developer saving an ISO/IEC PDF into the archive is an execution failure, not just a policy one
- Mitigation: Tier D check in the feature DoD, archive scan in CI for known standard identifiers,
  Tier D rule stated in CLAUDE.md and import-source-map.md

6. Hallucination reaching a user as apparent fact (rated High in RegOps.md)
- The product's core failure mode: a wrong regulatory interpretation becomes an approval delay
- Mitigation: citation enforcement, evidence-verification agent, sub-threshold human review,
  hallucination rate gated per cell in both Phase 1 and Phase 2

7. Key-person dependency on the single RA domain expert
- One person is simultaneously golden-set designer, blind accuracy assessor, and final signoff on
  regulatory interpretation — a single point of failure across the entire quality gate, and the
  assessor-designer overlap also weakens the blind assessment
- Mitigation: budget a second RA reviewer from Phase 1 (even part-time or contracted) so golden-set
  authorship and accuracy assessment are separated; document IR authoring conventions early

8. Cross-domain architecture assumption proves false
- If Normalization or Section Parsing has to fork for Cosmetic, Phase 2's six-cell build is invalid
- Mitigation: the W5-6 cross-domain check and the MFDS Cosmetic gated cell exist to surface this
  at M1-2 rather than M8

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
3. Deliver first ingestion run for the Phase 1 gated cells (MFDS SaMD + MFDS Cosmetic) public sources
4. Build initial golden query set and RA scoring rubric
5. Start pilot recruitment and usage baseline capture
