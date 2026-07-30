# Phase 2.0 — Tier C & scope completion

- **Roadmap:** Phase 2 (M5–12) · **Status:** ⬜ planned
- **Governed by:** [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md), [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 5
- **Depends on:** Phase 1 Go
- **Service:** `regulation`

---

## Goal

Complete the scope matrix — the remaining six cells — and introduce the scraping tier Phase 1
deliberately avoided. This is the phase where detection coverage and citation quality are most
likely to degrade, because it adds two hard capabilities and two new source languages at once.

## Scope

**In:** FDA, EU and NMPA connectors across both domains; Tier C scraping with resilience; Chinese
and EU-language normalization.

**Out:** the knowledge graph (2.1) and gap analysis (2.2), which run in parallel but are tracked
separately.

## Tasks

### Remaining six cells

- [ ] `fda_samd`, `fda_cosmetic` — openFDA, Federal Register API, Regulations.gov (Tier A)
- [ ] `eu_samd`, `eu_cosmetic` — EUR-Lex, EC cosmetics portal, CosIng, EU Safety Gate (Tier B)
- [ ] `nmpa_samd`, `nmpa_cosmetic` — NMPA notices, CSAR documents, IECIC (Tier C)
- [ ] Per-cell parser profiles; **no domain-specific column on `Clause`** — the ADR-0002 bet must still hold at eight cells
- [ ] `document_cells` M:N exercised for real: the FD&C Act ingested once, claimed by both FDA cells

### Tier C scraping

- [ ] Scraper framework with per-source selectors and versioned extraction rules
- [ ] **Structure-change detection** — `structure_drift_alerts` raised on layout change, adjudicated by an `ra`
- [ ] Connector health monitoring and alerting in production
- [ ] Manual fallback playbook per Tier C source
- [ ] **No connector on a login-gated portal** — EU CPNP, EUDAMED and equivalents are reference-only

### Multilingual

- [ ] Chinese (NMPA) and EU-language normalization, **source text retained alongside**
- [ ] Diffs computed in the authoritative language per cell: EN for EU, KO for MFDS, ZH for NMPA, EN for FDA
- [ ] Other languages retained for citation display, not change detection
- [ ] `version_group_id` joining language variants of the same act

### `canonical_key` completion

- [ ] EU — ELI URI; FDA — CFR citation; NMPA — curated key, no stable identifier exists ([ADR-0002](../design/ADR-0002-canonical-regulation-model.md) open question 3)

## Mid-phase checkpoint (M8) — hard gate

Phase 2 carries the two hardest new capabilities across eight months. Do **not** run it without an
interim gate:

- [ ] 4 of 8 cells live and independently passing the Phase 1 trust gates
- [ ] Graph schema frozen (see [phase2.1](phase2.1_semantic_graph.md))
- [ ] Tier C connector health monitoring in production

Miss any of these and **re-plan the back half** rather than continuing to M12.

## Acceptance criteria — per cell, all eight

- [ ] Detection coverage ≥ 95%
- [ ] Detection latency ≤ 24h
- [ ] Citation accuracy ≥ 90%
- [ ] Hallucination rate ≤ 2%

The Phase 1 thresholds do not retire at M4. Scaling 2 → 8 cells while adding scraping and two
languages is exactly when they degrade, so every cell clears them independently before Phase 2
closes.

- [ ] A Tier C layout change raises a drift alert rather than silently returning empty
- [ ] No Tier D body text anywhere across all eight cells — CI scan green at scale

## Risks & open questions

- **Risk 1 — source instability.** Tier C is fragile by construction; the mitigation is drift detection plus manual fallback, not more careful selectors.
- **Multilingual diffing.** Computing diffs in a non-authoritative language produces phantom changes. The per-cell authoritative language must be configuration, not convention.
- **NMPA has no stable document identifier**, so `canonical_key` is curated — a manual surface that will drift.

## Deviations & decisions

_None yet._
