# RegOps Platform Architecture

---

## RegOps Platform

> **RegOps** — AI-powered Regulatory platform for SaMD (Software as a Medical Device) and Cosmetic Product.  
A citation-traceable knowledge layer that turns fragmented SaMD and cosmetic regulations into monitored change alerts, sourced answers, and mapped compliance gaps.

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
*Deliverables: IR (InfoRequirement)-to-control matrix, gap report, list of corrective actions*

**04. SaaS productization for external customers**
Convert internally validated workflows into a multi-tenant offering. Commercialize with domestic pharma and medical device companies plus CRO/consulting firms as the primary target.
*Deliverables: tenant isolation, validation package, partner API*

> 01–03 are the internal value-validation stages; 04 extends the same core outward — not a separate product, just a different deployment form of the same knowledge layer.

---

## Scope — two product domains × four regulatory regions

RegOps covers **two product domains** (SaMD, Cosmetic) across **four regulatory regions** (MFDS, FDA, EU, China NMPA). Everything else is explicitly out of scope. The eight cells below are the complete coverage target; a single Import Agent serves all of them, with the differences isolated into per-cell connectors and parser profiles.

| Domain | MFDS (Korea) | FDA (US) | EU (EC) | NMPA (China) |
|---|---|---|---|---|
| **SaMD** | 의료기기법 · 디지털의료제품법 · SW/AI device review guidelines | FD&C Act · 21 CFR 820 (QMSR)·11·803·806·807 · SaMD & AI/ML guidance | MDR (EU) 2017/745 · IVDR (EU) 2017/746 · MDCG guidance · EUDAMED | Regulations for the Supervision and Administration of Medical Devices · software & AI device registration guidance · YY standards |
| **Cosmetic** | 화장품법 · 안전기준 규정 · 기능성화장품 심사 규정 | FD&C Act · MoCRA · FPLA · 21 CFR 700·701·710·740 | Regulation (EC) No 1223/2009 · CPNP · CosIng · SCCS opinions | CSAR · registration/filing measures · IECIC |

> The authoritative per-cell inventory of laws, guidance, and official source URLs lives in [import-source-map.md](import-source-map.md) — one section per cell. This table is the summary; that file is what the connectors are built against.

### Out of scope

- **Product domains** — pharmaceuticals and biologics, non-software (hardware) medical devices, food and health supplements
- **Regions** — every authority outside the four above (PMDA, Health Canada, MHRA, TGA, ASEAN ACD, and EMA drug procedures). Not "later" — not modeled at all until the scope decision is revisited
- **Content** — Tier D copyright-protected standards and pharmacopoeia source text (see Data Strategy below)

> Scope discipline is what makes the Go/No-Go gates meaningful. Detection coverage ≥ 95% is measurable only because the denominator — 2 domains × 4 regions — is fixed and written down.

---

## Data Strategy — data sources fall into four tiers, and the last tier is never crossed

| Tier | Category | Sources | Constraints |
|---|---|---|---|
| **A** | Public APIs — collectable immediately | openFDA (devices, MAUDE, 510(k), PMA), Federal Register API, Regulations.gov API, Korea National Law Information OPEN API, Public Data Portal MFDS datasets | Most of openFDA is CC0 — commercial redistribution permitted |
| **B** | Static files / RSS — batch collection | EUR-Lex / EC cosmetics portal documents, CosIng, EU Safety Gate (RAPEX), FDA AI-enabled medical device list, FDA MoCRA pages, MFDS RSS (notices, legislative notices, amendments) | License terms must be checked individually |
| **C** | Scraping — requires fragility management | FDA guidance DB, warning letters, import alerts, Form 483, EUDAMED (no official API), MDCG guidance, NMPA notices and CSAR documents, IECIC, MFDS nedrug/emedi portals | Structure-change detection and recovery pipeline are mandatory |
| **D** | Copyright-protected — **source text collection prohibited** | Standards and pharmacopoeias such as ISO 13485 / 14971, IEC 62304 / 60601 / 62366, ISO 27001, USP-NF, Ph.Eur. | ISO explicitly prohibits use for AI training → handle only metadata, revision history, and citations, and link to the official copy |

> Stating Tier D as the product boundary is not a risk but a basis for trust — **regulated customers buy only when "what we do not collect" can be written into the contract.**

> Tier D source text is never ingested. ISO explicitly prohibits using standard content for AI training. Instead we handle only metadata such as standard number, revision history, and harmonized-standard status.

---

## Architecture — five layers, from ingestion to applications

```text
                        SCOPE — 8 cells, and nothing else
        ┌────────────┬──────────┬──────────┬──────────┬──────────┐
        │            │   MFDS   │   FDA    │    EU    │   NMPA   │
        ├────────────┼──────────┼──────────┼──────────┼──────────┤
        │  SaMD      │  ● P1    │    P2    │  ○ spike │    P2    │
        │  Cosmetic  │  ● P1    │    P2    │    P2    │    P2    │
        └────────────┴──────────┴──────────┴──────────┴──────────┘
          ● gated PoC cell   ○ non-gated spike   P2 · P3 = later phase
          Per-cell laws, guidance, and source URLs → import-source-map.md
          (the only source catalog — never restate it elsewhere)

  L1  INGESTION                        one Import Agent · per-cell connectors
 ══════════════════════════════════════════════════════════════════════════
      Tier A  public API     ┐
      Tier B  static / RSS   ├─→  fetch ─→ sha256 ─→ WORM archive (immutable)
      Tier C  scraping       ┘                └─ unchanged re-fetch records a
                                                 fetch_observation, no version
      change-detection scheduler drives every tier
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
      Tier D  ISO · IEC · USP-NF · Ph.Eur.        ✕  never ingested
              StandardReference: number, edition, recognition/OJ number,
              dates, status, official URL.  No body text, ever.
                                    │
                                    ▼
  L2  NORMALIZATION
 ══════════════════════════════════════════════════════════════════════════
      parse ─→ clause-level segmentation ─→ DocumentVersion
                                            (immutable, one per version+language)
      multilingual, source text retained alongside
      ClauseDiff ─→ ChangeEvent ─→ routed to every claiming cell
      renumbering resolved explicitly, never reported as delete + add
                                    │
                                    ▼
  L3  REGULATORY KNOWLEDGE GRAPH                              ← the asset
 ══════════════════════════════════════════════════════════════════════════
      authority · document · clause · IR (InfoRequirement)
      product family · market · internal SOP / control
      IR.domain_profile ∈ samd|cosmetic — the only branch by domain
      only locked IRs flow downstream · impact-propagation paths on amendment
                                    │
                                    ▼
  L4  RETRIEVAL & REASONING                    LLM behind a pluggable seam
 ══════════════════════════════════════════════════════════════════════════
      hybrid search (BM25 + vector) ─→ graph context expansion
        ─→ citation-enforced generation ─→ evidence-verification agent
                                        ─→ confidence score
      citation pinned to an immutable version, never "current"
      no citation → "needs verification"   ·   below threshold → human review
                                    │
                                    ▼
  L5  APPLICATIONS
 ══════════════════════════════════════════════════════════════════════════
      01 Change monitoring & alerting  P1 │ 02 Q&A / RAG assistant        P1
         daily change briefing            │    answers with citations
         impact grading                   │    deep links to source text
         owner-routed tickets             │    query audit trail
    ────────────────────────────────────────────────────────────────────────
      03 Gap analysis & control map    P2 │ 04 SaaS productization        P3
         IR-to-control matrix             │    tenant isolation
         gap report                       │    validation package
         corrective action list           │    partner API
                                    │
                                    ▼
      RA · QA · engineering owners        →  P3: external tenants, auditors
```

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

- Gated target: two of the eight scope cells — MFDS SaMD + MFDS Cosmetic (one regulator, both domains — this is what tests the shared-pipeline architecture before Phase 2 builds six more cells on it)
- Non-gated spike: EU SaMD at reduced depth, to expose multilingual normalization and the first Tier C source early
- Ingest Tier A/B sources only (API · RSS)
- Implement only two features: monitoring + Q&A
- Pilot users: 20–30 people in one business unit
- Outcome: Go/No-Go decision on expansion

### Phase 2 · months 5–12 — internal expansion
**Company-wide rollout + gap analysis capability**

- Complete the scope matrix: add FDA and NMPA, and add the Cosmetic domain across all four regions
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
| M1 | Foundation | Finalize data source priorities · MFDS SaMD + MFDS Cosmetic connectors (국가법령정보 API, MFDS RSS) · source archive · pilot user interviews |
| M2 | Normalization & indexing | Clause-level parsing · multilingual handling · change diff logic · hybrid search index · build a 200-item golden query set for evaluation |
| M3 | Feature implementation | Monitoring dashboard · alert routing · citation-enforced Q&A · evidence-verification agent · confidence scoring |
| M4 | Pilot & evaluation | 20–30 real users · quantitative metric measurement · blind accuracy assessment by RA staff · Phase 2 expansion design and Go/No-Go report |

### Go / No-Go quantitative gates

| Metric | Threshold | Measurement method |
|---|---|---|
| Detection coverage | ≥ 95% | Share of actual amendments/announcements in the target scope cells that the system captured (verified by after-the-fact manual comparison) |
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
| Scope cells covered | 8 of 8 (2 domains × 4 regions) |

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
| Fragile scraping pipeline | Medium | No official APIs for NMPA, EUDAMED, etc. | Phase 1 uses API sources only. Tier C is introduced in Phase 2 together with structure-change detection, alerting, and manual fallback |
| Suite bundling competition (Veeva et al.) | Medium | Existing customers choose bundles for integration convenience | Enter as a complement for "change detection and impact analysis" rather than a head-on replacement, and secure references before Veeva's agentic features ship |
| Underestimating GxP validation cost | Medium | Part 11, quality agreements, and customer audit response are organizational capabilities that precede the product | Assign quality staff from Phase 2 and pre-allocate certification and consulting costs in the Phase 3 budget |
| Potential EU AI Act applicability to ourselves | Watch | AI embedded in medical devices applies from 2028-08-02; transparency obligations from 2026-08-02 | Document the product itself to a level that can support a high-risk classification. Turn the dual position — subject of regulation and tool for regulatory response — into a marketing asset |

---

## Decision Request — decisions requested today

**01. Approve Phase 1 PoC kickoff and a KRW 450M budget**
4 months, gating two of the eight scope cells: MFDS SaMD + MFDS Cosmetic (plus a non-gated EU SaMD spike)

**02. Assign one full-time domain expert from the RA organization**
Requirement structuring and accuracy evaluation are impossible without a regulatory expert

**03. Designate one pilot business unit**
Secure 20–30 real users — a precondition for measuring the retention metric

**04. Agree the Go/No-Go gate criteria in advance**
No-Go is confirmed if four or more of the six quantitative metrics fall short

### The next 30 days upon approval

- Form the task force and hold kickoff (W1)
- Complete data source prioritization and legal review (W2)
- First run of the MFDS SaMD + MFDS Cosmetic public source connectors (W3)
- Begin pilot user interviews and golden query set design (W4)
