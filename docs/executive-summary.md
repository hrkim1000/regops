# RegOps Executive Summary (1-Page)

## What RegOps Is

RegOps is a citation-traceable regulatory platform for medical device and cosmetic workflows.
It converts fragmented regulations into four business outcomes:
- change monitoring and alerting,
- evidence-backed regulatory Q&A,
- IR (InfoRequirement)-based compliance gap analysis,
- and external SaaS productization.

The strategic asset is the knowledge layer and IR mapping, not a single LLM model.

## Why This Matters Now

- Regulatory change velocity is increasing across FDA, EMA, PMDA, NMPA, and MFDS contexts.
- Manual interpretation creates delay, inconsistency, and audit risk.
- In regulated operations, trust requires evidence, version traceability, and auditable decisions.

RegOps is designed around verifiability: no answer without evidence, confidence-based review routing, and complete audit trail.

## Delivery Strategy (24 Months)

Phase 1 (Month 0-4): PoC validation
- Scope: EU MDR + MFDS medical devices, Tier A/B sources, monitoring + Q&A
- Goal: prove technical trust and user value

Phase 2 (Month 5-12): internal scale
- Scope: wider regulator coverage + Tier C scraping resilience + gap analysis depth
- Goal: company-wide adoption and measurable productivity impact

Phase 3 (Month 13-24): external SaaS
- Scope: multi-tenant operating model, validation package, partner/API channel
- Goal: paying customers and repeatable ARR growth

## Stage Gates (Decision by Numbers)

Phase 1 gates:
- Detection coverage >= 95%
- Detection latency <= 24h
- Citation accuracy >= 90%
- Hallucination rate <= 2%
- Pilot retention >= 60%

Phase 2 targets:
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
3. Run first openFDA + MFDS-related public source connector ingestion
4. Finalize golden query set and RA scoring rubric
5. Launch pilot recruitment and baseline measurement
