# RegOps Platform Architecture

---

## RegOps Platform

> **RegOps** — AI-powered Regulatory platform for Medical Device, Cosmetic Product.  
A citation-traceable knowledge layer that turns fragmented medical device, and cosmetic regulations into monitored change alerts, sourced answers, and mapped compliance gaps.

Pillars: regulatory change monitoring · regulatory Q&A assistant · compliance gap analysis · external SaaS productization

---

## Vision — four application pillars on top of a single regulatory knowledge layer

**01. Regulatory change monitoring & alerting**
Collect and normalize source texts from regulatory authorities and extract change sets (diffs). Match them against product, market, and business-unit profiles so only the affected organizations are notified automatically.
*Deliverables: daily change briefing, impact grading, tickets with assigned owners*

**02. Regulatory Q&A / RAG assistant**
Answer natural-language queries together with the supporting clause, document version, and effective date. Answers without evidence are never generated — they are returned as "needs verification."
*Deliverables: answers with citations, deep links to source text, audit trail of query history*

**03. Compliance gap analysis & control mapping**
Decompose regulatory obligations into structured requirements and map them to internal SOPs, controls, and technical documents. On amendment, automatically derive the scope of impact and the non-compliant items.
*Deliverables: requirement–control matrix, gap report, list of corrective actions*

**04. SaaS productization for external customers**
Convert internally validated workflows into a multi-tenant offering. Commercialize with domestic pharma and medical device companies plus CRO/consulting firms as the primary target.
*Deliverables: tenant isolation, validation package, partner API*

> 01–03 are the internal value-validation stages; 04 extends the same core outward — not a separate product, just a different deployment form of the same knowledge layer.

---

## Data Strategy — data sources fall into four tiers, and the last tier is never crossed

| Tier | Category | Sources | Constraints |
|---|---|---|---|
| **A** | Public APIs — collectable immediately | openFDA (drugs, devices, MAUDE, 510(k), PMA), Federal Register API, Regulations.gov API, Health Canada MDALL, Korea National Law Information OPEN API, Public Data Portal MFDS datasets | Most of openFDA is CC0 — commercial redistribution permitted |
| **B** | Static files / RSS — batch collection | EMA public JSON (refreshed twice daily), FDA Orange/Purple Book, FDA AI medical device list, MFDS RSS (notices, legislative notices, amendments) | License terms must be checked individually |
| **C** | Scraping — requires fragility management | FDA guidance DB, warning letters, Form 483, EUDAMED (no official API), PMDA, NMPA, MHRA, TGA, MDCG guidance, ICH·IMDRF PDFs | Structure-change detection and recovery pipeline are mandatory |
| **D** | Copyright-protected — **source text collection prohibited** | Standards and pharmacopoeias such as ISO 13485 / 14971, IEC 62304 / 60601 / 62366, ISO 27001, USP-NF, Ph.Eur. | ISO explicitly prohibits use for AI training → handle only metadata, revision history, and citations, and link to the official copy |

> Stating Tier D as the product boundary is not a risk but a basis for trust — **regulated customers buy only when "what we do not collect" can be written into the contract.**

> Tier D source text is never ingested. ISO explicitly prohibits using standard content for AI training. Instead we handle only metadata such as standard number, revision history, and harmonized-standard status.

---

## Architecture — five layers, from ingestion to applications

**L1. Ingestion**
API connectors · RSS · scraping workers · change-detection scheduler · immutable source archive (WORM)

**L2. Normalization**
Document parsing · clause-level segmentation · multilingual translation (with source text alongside) · version management · clause-level diff extraction

**L3. Regulatory Knowledge Graph**
Link regulatory authorities, laws/notices, clauses, requirements, product families, markets, and internal SOPs/controls as entities. Compute impact-propagation paths on amendment.

**L4. AI layer (Retrieval & Reasoning)**
Hybrid search (BM25 + vector) · graph-based context expansion · citation-enforced generation · evidence-verification agent · answer confidence score

**L5. Applications**
Monitoring dashboard · Q&A assistant · gap analysis workbench · alert/ticket integration · multi-tenant SaaS portal · public API

### Requirements common to all layers

- Source and version metadata must be preserved
- Audit trail for all retrieval and generation history
- 21 CFR Part 11 electronic records and signatures
- Role-based access control (RBAC)
- Regional data residency
- Model version pinning and regression testing

> **Core design principle** — the knowledge graph (L3) is the asset. LLMs are replaceable, but regulation–product–control mapping data becomes irreplaceable as it accumulates.

---
## Trust by Design — in the regulatory space, AI competes on verifiability, not generation quality

### Five design principles

1. No answer without evidence — return "needs verification" when a citation is not possible
2. Present the clause-level citation together with the document version and effective date
3. Every generated result must pass a separate evidence-verification agent
4. Every answer carries a confidence score; anything below the threshold routes to human review
5. Preserve a full audit trail of queries, answers, and evidence

### GxP validation — the gate that must be cleared before selling externally

- **CSA-based validation** — the FDA finalized the Computer Software Assurance guidance in September 2025. The risk-based approach reduces documentation burden, but supplier deliverable requirements remain
- **21 CFR Part 11 compliance** — tamper-evident audit trails, electronic signature controls, user activity logging. SOC 2 and ISO 27001 alone are not sufficient
- **Quality agreement & audit rights** — data retention policy, archive integrity, a structure for accepting customer audits, change management documentation
- **Data residency** — GDPR, Korea's Personal Information Protection Act, China's data regulations — storage location by region must be answerable at the contract level

*Sources: CNN (2025-07-23) and FDA announcements (Elsa 4.0 · HALO, 2026-05-06), Sidley GoodLifeSci (2026-05-20), FDA CSA final guidance (Federal Register, 2025-09-24), industry practice for GxP supplier qualification assessment*

---

## Roadmap — three stages: validate narrowly, expand broadly, then sell outward

### Phase 1 · months 0–4 — PoC
**Narrow the scope to validate the technical and value hypotheses**

- Target: two regulatory areas — EU MDR + MFDS medical devices
- Ingest Tier A/B sources only (API · RSS)
- Implement only two features: monitoring + Q&A
- Pilot users: 20–30 people in one business unit
- Outcome: Go/No-Go decision on expansion

### Phase 2 · months 5–12 — internal expansion
**Company-wide rollout + gap analysis capability**

- Expand regulatory coverage: FDA · EMA · PMDA · NMPA
- Build the Tier C scraping pipeline
- Implement the knowledge graph + control mapping
- Integrate internal SOPs and technical documents
- Outcome: adoption as a company-wide standard tool, measured ROI

### Phase 3 · months 13–24 — external SaaS
**Multi-tenant commercialization and market entry**

- Transition to multi-tenant architecture
- GxP validation package · SOC 2 certification
- Secure pilot customers among domestic pharma and medical device companies
- Build partner (CRO · consulting) channels
- Outcome: paying customers and ARR

> At the end of each stage, quantitative gates must be cleared before the next stage's budget is released — **a stage-gated approval structure.**

---

## Phase 1 (PoC) detail — 4 months, 2 regulatory areas, 2 features

| Timing | Stage | Key activities |
|---|---|---|
| M1 | Foundation | Finalize data source priorities · openFDA / National Law Information API connectors · source archive · pilot user interviews |
| M2 | Normalization & indexing | Clause-level parsing · multilingual handling · change diff logic · hybrid search index · build a 200-item golden query set for evaluation |
| M3 | Feature implementation | Monitoring dashboard · alert routing · citation-enforced Q&A · evidence-verification agent · confidence scoring |
| M4 | Pilot & evaluation | 20–30 real users · quantitative metric measurement · blind accuracy assessment by RA staff · Phase 2 expansion design and Go/No-Go report |

### Go / No-Go quantitative gates

| Metric | Threshold | Measurement method |
|---|---|---|
| Detection coverage | ≥ 95% | Share of actual amendments/announcements in the target regulatory areas that the system captured (verified by after-the-fact manual comparison) |
| Detection latency | ≤ 24 hours | Elapsed time from the authority's publication to the owner's alert |
| Citation accuracy | ≥ 90% | Share of cited clauses that actually support the given answer (blind assessment by RA staff) |
| Hallucination rate | ≤ 2% | Share of outputs citing non-existent clauses/documents or contradicting the source text |
| Research time savings | ≥ 30% | Reduction in time spent versus the existing manual process for the same query type |
| Pilot retention rate | ≥ 60% | Share of pilot users who voluntarily used the system at least once a week (for 4 consecutive weeks) |

> The purpose of the PoC is numbers, not a demo. If four or more of the six metrics fall short, we call No-Go and redesign the approach.

---

## Organization — keep regulatory expertise and engineering on the same team

| Role | Scope | Phase 1 | Phase 2 | Phase 3 |
|---|---|---:|---:|---:|
| Regulatory domain (RA/QA) | Requirement structuring, golden set design, answer accuracy validation, validation documentation | 1 | 3 | 6 |
| Data engineering | Connectors, scraping pipeline, normalization, knowledge graph loading | 2 | 4 | 7 |
| AI / ML engineering | Retrieval & ranking, citation-enforced generation, evidence-verification agent, evaluation harness | 2 | 4 | 8 |
| Product / frontend | Workbench UX, alert & ticket integration, multi-tenant portal | 1 | 3 | 6 |
| Security / compliance | Part 11 compliance, SOC 2, data residency, customer audit response | 0.5 | 1 | 3 |
| **Total (FTE)** | | **6.5** | **15** | **30** |

*Assumption: Phase 1 can start entirely with internal reassignment or part-time allocation. Regulatory domain staff are seconded from the internal RA organization, and Phase 3 security/compliance runs in parallel with external consulting.*

---

## Success Metrics — what gets measured changes by stage

| Phase 1 · technical trust | Target |
|---|---:|
| Detection coverage | ≥ 95% |
| Detection latency | ≤ 24 hours |
| Citation accuracy | ≥ 90% |
| Hallucination rate | ≤ 2% |
| Pilot retention rate | ≥ 60% |

| Phase 2 · operational impact | Target |
|---|---:|
| Regulatory research time | 40% reduction |
| Gap analysis lead time | 50% shorter |
| Missed amendment impact analyses | 0 |
| Monthly active users | 300+ |
| Regulatory authorities covered | 6+ countries |

| Phase 3 · business results | Target |
|---|---:|
| Paying customers | 8+ companies |
| Annual recurring revenue (ARR) | KRW 2B+ |
| Net revenue retention (NRR) | ≥ 110% |
| Validation audits passed | 100% |
| Partner channel share | 30%+ |

> **Reference benchmark** — 78% of life sciences executives said AI would significantly change their organization, yet only 22% succeeded in company-wide rollout and only 9% confirmed meaningful return on investment.
> → The gate structure in this plan is the mechanism for landing in that 22%/9% band.

*Source: Deloitte 2026 Life Sciences Executive Outlook (280 C-level respondents, surveyed Aug–Sep 2025). Phase 2 and 3 targets are internally set values.*

---

## Risk & Mitigation — six key risks and responses

| Risk | Level | Description | Mitigation |
|---|---|---|---|
| Copyright infringement | High | ISO standards and pharmacopoeias prohibit AI training and source-text storage | Write the Tier D no-source-text principle into both the architecture and the contract. Provide only metadata, revision history, and deep links to the official copy |
| Misjudgment from AI hallucination | High | Incorrect regulatory interpretation translates directly into approval delays or non-compliance | Citation enforcement + evidence-verification agent + human review below the confidence threshold. State in the UI that final judgment rests with the human |
| Fragile scraping pipeline | Medium | No official APIs for PMDA, NMPA, EUDAMED, etc. | Phase 1 uses API sources only. Tier C is introduced in Phase 2 together with structure-change detection, alerting, and manual fallback |
| Suite bundling competition (Veeva et al.) | Medium | Existing customers choose bundles for integration convenience | Enter as a complement for "change detection and impact analysis" rather than a head-on replacement, and secure references before Veeva's agentic features ship |
| Underestimating GxP validation cost | Medium | Part 11, quality agreements, and customer audit response are organizational capabilities that precede the product | Assign quality staff from Phase 2 and pre-allocate certification and consulting costs in the Phase 3 budget |
| Potential EU AI Act applicability to ourselves | Watch | AI embedded in medical devices applies from 2028-08-02; transparency obligations from 2026-08-02 | Document the product itself to a level that can support a high-risk classification. Turn the dual position — subject of regulation and tool for regulatory response — into a marketing asset |

---

## Decision Request — decisions requested today

**01. Approve Phase 1 PoC kickoff and a KRW 450M budget**
4 months, targeting two regulatory areas: EU MDR + MFDS medical devices

**02. Assign one full-time domain expert from the RA organization**
Requirement structuring and accuracy evaluation are impossible without a regulatory expert

**03. Designate one pilot business unit**
Secure 20–30 real users — a precondition for measuring the retention metric

**04. Agree the Go/No-Go gate criteria in advance**
No-Go is confirmed if four or more of the six quantitative metrics fall short

### The next 30 days upon approval

- Form the task force and hold kickoff (W1)
- Complete data source prioritization and legal review (W2)
- First run of the openFDA and National Law Information connectors (W3)
- Begin pilot user interviews and golden query set design (W4)
