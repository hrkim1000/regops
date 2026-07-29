---
name: glossary
description: Domain terminology and required abbreviations for RegOps — use when writing any document, comment, UI copy, or commit message that names domain concepts (cell, IR, clause, citation, Tier D, change event, SaMD, MFDS/FDA/EU/NMPA).
---

# Glossary & Terminology

Always use the abbreviation; give the full name in parentheses only when first explained.

## Scope vocabulary

| Term | Definition |
| --- | --- |
| **cell** | One `{authority}_{domain}` pair — the unit of scope, connector, parser profile, and coverage measurement. Exactly **8**: `authority ∈ mfds\|fda\|eu\|nmpa` × `domain ∈ samd\|cosmetic`. Never "Medical Device", "Device", or "MDR" as a domain value |
| **SaMD** | Software as a Medical Device |
| **MFDS / FDA / EU / NMPA** | Ministry of Food and Drug Safety (Korea) · Food and Drug Administration (US) · European Commission (EU) · National Medical Products Administration (China). The only four authorities in scope |
| **gated cell** | A Phase 1 cell carrying the Go/No-Go gates (MFDS SaMD, MFDS Cosmetic). A **spike** (EU SaMD) is explored but not gated |
| **Tier A/B/C/D** | Source collectability: A public API · B static/RSS · C scraping · **D copyright-protected — source text never ingested** |

## Data model

Defined in [ADR-0002](../../../docs/design/ADR-0002-canonical-regulation-model.md).

| Term | Definition |
| --- | --- |
| **Source** | A fetchable entry from `import-source-map.md`, the single source catalog. Carries tier, priority (subsection order), and whether it is ingestible at all |
| **Document** | A regulation or guidance identified stably across versions. **M:N with cell** — the FD&C Act belongs to both `fda_samd` and `fda_cosmetic` |
| **DocumentVersion** | An immutable fetched snapshot, one per `(document, version, language)`, referencing a content-addressed blob. Never mutated |
| **Clause** | The addressable unit inside a version: `clause_path`, ordered `path_segments`, level, ordinal, text. **Domain-neutral** — no SaMD-only or Cosmetic-only fields |
| **ClauseDiff** | Change between two versions; `change_kind ∈ added\|removed\|modified\|renumbered\|moved`. Renumbering is resolved explicitly, never reported as delete+add |
| **ChangeEvent** | Emitted from a ClauseDiff and routed to every claiming cell — the monitoring pillar's output |
| **Citation** | `(document_id, document_version_id, clause_path, effective_date)`. Pinned to an **immutable version, never "current"** — a stored answer's evidence must never silently change. Superseded citations are flagged and re-verified, never rewritten |
| **IR / InfoRequirement** | One atomic regulatory obligation extracted from one or more clauses, with a **mandatory citation**. Carries `domain_profile` (`samd`\|`cosmetic`) — the only place the pipeline branches by domain. Only **locked** IRs flow downstream |
| **StandardReference** | A Tier D standard as metadata only — number, edition, recognition/OJ number, dates, status, official URL. **Has no body text and no table that could hold it.** An IR may cite one; it resolves to a deep link |
| **WORM archive** | Write-once source archive, content-addressed by `sha256`. An unchanged re-fetch records a `fetch_observation` (proof the source was checked) but creates no version |

## Trust & evaluation

| Term | Definition |
| --- | --- |
| **needs verification** | The mandatory response when a citation cannot be produced. Never generate an unsourced answer |
| **evidence-verification agent** | The separate pass every generated result must survive before reaching a user |
| **confidence score** | Per-answer; below threshold routes to human review |
| **golden query set** | The evaluation corpus (200 items at PoC), scored **per domain** — SaMD and Cosmetic sets are separate |
| **the 6 gates** | Detection coverage ≥95% · detection latency ≤24h · citation accuracy ≥90% · hallucination rate ≤2% · research time savings ≥30% · pilot retention ≥60%. No-Go if 4+ fall short; measured per gated cell |

## Ambiguities to avoid

- **"CE"** — in RegOps this means **CE marking** (Conformité Européenne), the EU conformity mark. Write it in full; never use bare `CE` for a person or role.
- **"IR"** — always InfoRequirement. Not "Information Requirement".
- **"change_kind"** — the ClauseDiff kind. Not a release-version transition.
- **"document"** — when it means an *internal* SOP or technical file rather than a regulation, say "internal document" or "control document".

## Platform

| Term | Definition |
| --- | --- |
| **RAG / Vector DB** | Retrieval-Augmented Generation · pgvector (`nomic-embed-text`, 768-dim, HNSW cosine) |
| **PII / PHI** | Personally Identifiable Information · Protected Health Information — relevant once customer SOPs and technical documents are ingested for gap analysis |

> Terminology from the prior platform (SW Profile DB, git-agent, component/device release, clinical
> HITL gates, per-section signoff, Tele/FA/DDH) does **not** apply to RegOps and must not appear in
> RegOps documents or code — see [ADR-0001](../../../docs/design/ADR-0001-platform-foundation.md).
