# RegOps Executive Summary (1-Page)

## What RegOps Is

RegOps is a citation-traceable regulatory platform for SaMD (Software as a Medical Device) and Cosmetic Product workflows.

Scope is fixed at two product domains x four regulatory regions:
- Domains: SaMD, Cosmetic
- Regions: MFDS (Korea), FDA (US), EU, NMPA (China)
- Out of scope: pharmaceuticals/biologics, hardware-only medical devices, and all other authorities (PMDA, Health Canada, MHRA, TGA, ASEAN)

It converts fragmented regulations into four business outcomes:
- change monitoring and alerting,
- evidence-backed regulatory Q&A,
- IR (InfoRequirement)-based compliance gap analysis,
- and external SaaS productization.

The strategic asset is the knowledge layer and IR mapping, not a single LLM model.

## Why This Matters Now

- Regulatory change velocity is increasing across MFDS, FDA, EU, and NMPA contexts for both SaMD and cosmetics.
- Manual interpretation creates delay, inconsistency, and audit risk.
- In regulated operations, trust requires evidence, version traceability, and auditable decisions.

RegOps is designed around verifiability: no answer without evidence, confidence-based review routing, and complete audit trail.

## Delivery Strategy (24 Months)

Phase 1 (Month 0-4): PoC validation
- Scope: 2 gated cells (MFDS SaMD + MFDS Cosmetic), Tier A/B sources, monitoring + Q&A
- One regulator, both domains: tests the shared-pipeline architecture before Phase 2 builds 4 more cells on it (FDA + NMPA; the 2 EU cells are Phase 4)
- ~~Plus a non-gated EU SaMD spike to de-risk multilingual and Tier C early~~ — **deferred to Phase 4 (2026-08-24), never run.** Multilingual and Tier C are now first met together in Phase 2's NMPA slice
- Goal: prove technical trust and user value

Phase 2 (Month 5-12): internal scale
- Scope: remaining 6 scope cells (FDA and NMPA SaMD, Cosmetic across all four regions) + Tier C scraping resilience + gap analysis depth
- Goal: company-wide adoption and measurable productivity impact

Phase 3 (Month 13-24): external SaaS
- Scope: multi-tenant operating model, validation package, partner/API channel
- Goal: paying customers and repeatable ARR growth

## Stage Gates (Decision by Numbers)

Phase 1 gates (6; No-Go if 4 or more fall short, measured per gated cell):
- Detection coverage >= 95%
- Detection latency <= 24h
- Citation accuracy >= 90%
- Hallucination rate <= 2%
- Research time savings >= 30%
- Pilot retention >= 60%

Phase 2 targets:
- All 8 cells independently clearing the Phase 1 technical gates
- Regulatory research time reduction >= 40%
- Gap analysis lead time reduction >= 50%
- Missed amendment impact analyses = 0
- MAU >= 300

Phase 3 targets:
- Paying customers >= 8
- ARR >= KRW 2B
- NRR >= 110%

## Key Risks and Controls

1. Copyright boundary breach
- Control: Tier D source text is never ingested; metadata and official links only.

2. AI misinterpretation risk
- Control: citation enforcement, evidence verification, human review below threshold.

3. Scraping fragility
- Control: phased rollout, structure-drift monitoring, manual fallback procedures.

4. Validation and audit burden
- Control: compliance workstream starts in parallel before external launch.

## Decision Request

1. Approve Phase 1 kickoff budget: KRW 450M
2. Assign 1 full-time RA domain expert
3. Designate pilot business unit (20-30 users)
4. Pre-approve Go/No-Go criteria before build execution

## Next 30 Days

1. Form cross-functional task force and finalize Phase 1 backlog
2. Complete source/legal review for Tier A/B connector list
3. Run first MFDS SaMD + MFDS Cosmetic public source connector ingestion
4. Finalize golden query set and RA scoring rubric
5. Launch pilot recruitment and baseline measurement
