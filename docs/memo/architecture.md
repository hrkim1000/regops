# Memo — early architecture sketch (superseded)

> **Superseded 2026-07-30 by [RegOps.md](../RegOps.md) § Architecture. Not authoritative.**
>
> Kept for provenance only. This draft contradicts three architecture rules and must not be
> cited or copied from:
>
> - The **External Regulation Sources** block is a second source catalog. The only catalog is
>   [import-source-map.md](../import-source-map.md).
> - It lists **ISO** and **IEC** as ingestion sources. They are Tier D — source text is never
>   ingested; only the recognition record is stored, with a deep link to the official copy.
> - It lists **IMDRF** and **ICH**, which are outside the 8 cells. ICH is pharma, explicitly
>   out of scope.
>
> It also predates the scope grid, the Tier A/B/C/D split, the L1–L5 layering, and the
> trust machinery (WORM archive, ClauseDiff, evidence-verification agent, confidence score).

```text
                               RegOps Platform

                    AI-powered Regulatory Intelligence Platform

                                     Users
──────────────────────────────────────────────────────────────────────────────
 RA Specialist | QA | Developer | Manufacturer | Consultant | Auditor | Customer
──────────────────────────────────────────────────────────────────────────────

                              AI Applications
──────────────────────────────────────────────────────────────────────────────

      1. Regulatory Monitoring
      • Regulation change monitoring
      • Version comparison
      • Alerting
      • Impact analysis
      • Subscription

──────────────────────────────────────────────────────────────────────────────

      2. Regulatory Assistant
      • RAG Search
      • Regulatory Q&A
      • Citation
      • Requirement explanation
      • Cross-region comparison

──────────────────────────────────────────────────────────────────────────────

      3. Compliance Intelligence
      • Gap Analysis
      • Requirement Mapping
      • Control Mapping
      • Evidence Collection
      • Compliance Score

──────────────────────────────────────────────────────────────────────────────

      4. Regulatory SaaS
      • Customer Workspace
      • Multi-tenant
      • APIs
      • Report Generation
      • White-label Service

──────────────────────────────────────────────────────────────────────────────

                     Shared Regulatory Knowledge Layer
──────────────────────────────────────────────────────────────────────────────

 Regulatory Library
 Regulation Parser
 Regulation Normalizer
 Requirement Extractor
 Interpretation Engine
 Version Management
 Cross-reference Engine
 Knowledge Graph
 Embedding Service
 Regulatory RAG Index
 Metadata Repository
 Document Repository

──────────────────────────────────────────────────────────────────────────────

                          External Regulation Sources
──────────────────────────────────────────────────────────────────────────────

FDA
MFDS
EU MDR
EU Cosmetic Regulation
China NMPA
ISO
IEC
IMDRF
ICH
Guidance
Standards
Official Notices
PDF
RSS
API
```
