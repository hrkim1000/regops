---
name: glossary
description: Domain terminology and required abbreviations for RegOps — use when writing any document, comment, UI copy, or commit message that names domain concepts (IR, CE, SaMD, MFDS, Tele/FA/DDH, SW Profile DB, per-section signoff, clinical gates).
---

# Glossary & Terminology

Always use the abbreviation; give the full name in parentheses only when first explained.

## Required abbreviations

| Abbrev. | Full name |
| --- | --- |
| **Tele** | Teleroentgenogram (never "Teleradiography") |
| **FA** | Foot and Ankle |
| **DDH** | Developmental dysplasia of the hip |

## Platform terms

| Term | Definition |
| --- | --- |
| **SaMD** | Software as a Medical Device |
| **MFDS** | Ministry of Food and Drug Safety (Korea) — the MVP regulator |
| **IR / InfoRequirement** | One atomic regulatory obligation extracted from a regulation, with a mandatory citation. Mapped M:N to documents and to SW Profile DB fields. Only **locked** (confirmed) IRs flow downstream |
| **CE** | Clinical Expert — the `clinical_expert` role; sole signer of the 6 clinical HITL gates |
| **SW Profile DB** | Live record of a product's software facts, updated by the git-agent reconcile poll per repo |
| **per-section signoff** | Each generated document decomposes into one `document_sections` row per applicable IR (`draft → approved/flagged`). Any `flagged` section blocks document approval, which gates the submission package. Signers must be currently employed (403 otherwise) |
| **component release** | One repo's `software_versions` row (multi-repo, ADR-0006), detected from a GitLab Release object (frozen tag — ADR-0005) |
| **device release** | A `project_versions` row pinning one component release per repo (the BOM); the submission unit |
| **change_kind** | major/minor/patch from the release tag digit transition (`vX.Y.Z`); MAJOR fans out re-derivation + regeneration |
| **coverage rule** | A requirement is covered only by a **committed, executed, passing** test (⑥ re-collects); generated test proposals (⑰) never count by themselves |
| **6 clinical gates** | CE approvals: 1 requirements · 2 risks (ISO 14971) · 3 dataset freeze · 4 validation report · 5 CER · 6 major change |
| **MCP / RAG / Vector DB** | Model Context Protocol · Retrieval-Augmented Generation · pgvector (`nomic-embed-text`, 768-dim, HNSW cosine) |
| **PHI / PII** | Protected Health Information / Personally Identifiable Information — HIPAA-protected |
