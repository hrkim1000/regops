# Import Source Map

Per-cell inventory of primary laws, regulations, guidance, and official source URLs for the fixed RegOps scope — **2 product domains (SaMD, Cosmetic) × 4 regulatory regions (MFDS, FDA, EU, NMPA) = 8 cells**. See [RegOps.md](RegOps.md) § Scope for the boundary and what is excluded.

This file is the source of truth the Import Agent connectors and parser profiles are built against; the scope tables in the planning docs are summaries of it.

**Ingestion priority is the subsection order within each cell.** `Primary Laws` is always first and is the top tier — the binding statute a cell cannot be ingested without. Subsequent blocks (Regulations, Standards, Guidance, Registration, Ingredient, GMP, Safety) descend in priority and vary by cell. `Official Sources` is always last and lists the portals every block above is fetched from.

**`Standards` blocks are metadata-only — Tier D.** ISO/IEC standards and pharmacopoeias (ISO 13485, ISO 14971, IEC 62304, IEC 62366, ISO 27001, …) prohibit source-text storage and AI training. Connectors ingest only the *recognition record* — standard number, edition, recognition/listing number, effective and withdrawal dates, harmonized status — and deep-link to the official copy. Never the standard's body text, even when a regulation makes it legally binding (e.g. QMSR incorporates ISO 13485:2016 by reference, effective 2026-02-02: cite the requirement, link the standard, store neither). See [RegOps.md](RegOps.md) § Data Strategy.

---

# Region 1. Korea (MFDS)

## Domain : Cosmetics

### Primary Laws

* 화장품법
* 화장품법 시행령
* 화장품법 시행규칙

### Standards

* 화장품 안전기준 등에 관한 규정
* 기능성화장품 심사 규정
* 표시·광고 규정

### Registration

* 제조업
* 책임판매업
* 기능성화장품 심사

### GMP

* CGMP

### Ingredient

* 사용금지 원료
* 사용제한 원료
* 원료 기준

### Safety

* 위해사례
* 회수
* 안전성 정보

### Official Sources

* [https://www.mfds.go.kr](https://www.mfds.go.kr)
* [https://nedrug.mfds.go.kr](https://nedrug.mfds.go.kr)
* [https://www.law.go.kr](https://www.law.go.kr)

---

## Domain : SaMD

### Primary Laws

* 의료기기법
* 의료기기법 시행령
* 의료기기법 시행규칙

### Regulations

* 디지털의료제품법
* 의료기기 허가·신고·심사 규정
* 의료기기 소프트웨어 허가심사 가이드라인

### Standards

* GMP
* IEC 62304 관련 가이드 — *메타데이터만 (Tier D)*: 표준 번호·판·정합 여부만, 원문 미수집
* AI 의료기기 가이드라인

### Safety

* 이상사례
* 회수
* 안전성 정보

### Official Sources

* [https://www.mfds.go.kr](https://www.mfds.go.kr)
* [https://emedi.mfds.go.kr](https://emedi.mfds.go.kr)
* [https://www.law.go.kr](https://www.law.go.kr)

---

# Region 2. United States (FDA)

## Domain : Cosmetics

### Primary Laws

* FD&C Act
* MoCRA
* Fair Packaging and Labeling Act

### Regulations

* 21 CFR Part 700
* 21 CFR Part 701
* 21 CFR Part 710
* 21 CFR Part 740

### Guidance

* Cosmetic Labeling
* Facility Registration
* Product Listing
* Responsible Person
* Safety Substantiation

### Safety

* Warning Letters
* Import Alerts
* Adverse Event

### Official Sources

* [https://www.fda.gov/cosmetics](https://www.fda.gov/cosmetics)
* [https://www.ecfr.gov](https://www.ecfr.gov)
* [https://www.federalregister.gov](https://www.federalregister.gov)

---

## Domain : SaMD

### Primary Laws

* FD&C Act

### Regulations

* 21 CFR Part 892 Subpart C (892.2050 / 2060 / 2070 / 2080 / 2090) — the SaMD classification regulations; 892.2090 newly created 2025-06-13
* 21 CFR Part 860 (classification procedures, De Novo)
* 21 CFR Part 820 (QMSR) — effective 2026-02-02
* 21 CFR Part 11
* 21 CFR Part 803
* 21 CFR Part 806
* 21 CFR Part 807
* 21 CFR Part 822 (postmarket surveillance)
* 21 CFR Part 7 (recalls / enforcement policy)

### Guidance

* Software as a Medical Device
* AI/ML Guidance
* Cybersecurity Guidance
* Premarket Submission Guidance

### Standards

* Recognized Consensus Standards — *metadata only (Tier D)*: recognition number, edition, listing/withdrawal date from the FDA Recognized Consensus Standards DB. Covers IEC 62304, ISO 14971, IEC 62366-1, IEC 81001-5-1, ANSI/AAMI SW96, AAMI CR515; no standard text
* ISO 13485:2016 — incorporated by reference into 21 CFR 820 (QMSR), effective 2026-02-02. Cite and link only

### Registration

* Establishment Registration & Listing (21 CFR Part 807 Subpart B)
* FURLS
* U.S. Agent
* Initial Importer

### Safety

* MAUDE adverse event reports
* Recalls
* Warning Letters
* Import Alerts
* 522 Postmarket Surveillance Studies

### Official Sources

* [https://www.fda.gov/medical-devices](https://www.fda.gov/medical-devices)
* [https://www.accessdata.fda.gov](https://www.accessdata.fda.gov)
* [https://www.ecfr.gov](https://www.ecfr.gov)
* [https://www.federalregister.gov](https://www.federalregister.gov)
* [https://open.fda.gov](https://open.fda.gov)
* [https://www.govinfo.gov](https://www.govinfo.gov)

---

# Region 3. European Union (EC)

## Domain : Cosmetics

### Primary Laws

* Regulation (EC) No.1223/2009
* Annexes II–VI (prohibited / restricted / colorants / preservatives / UV filters) and their amending Commission Regulations — the primary change-detection target

### Regulations

* Commission Implementing Decision 2013/674/EU (Annex I — Cosmetic Product Safety Report)
* Commission Regulation (EU) No 655/2013 (claims common criteria)
* CosIng
* CPNP — login-gated notification system, reference only; not an ingestion source

### Guidance

* SCCS Opinions
* Guidance Documents

### Safety

* Safety Gate (RAPEX)

### Official Sources

* [https://single-market-economy.ec.europa.eu/sectors/cosmetics_en](https://single-market-economy.ec.europa.eu/sectors/cosmetics_en) — DG GROW hosts cosmetics; the old `health.ec.europa.eu/cosmetics/*` paths 404
* [https://eur-lex.europa.eu](https://eur-lex.europa.eu)
* [https://ec.europa.eu/growth/tools-databases/cosing](https://ec.europa.eu/growth/tools-databases/cosing)
* [https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs_en](https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs_en) — SCCS only (DG SANTE)

---

## Domain : SaMD

### Primary Laws

* MDR (EU 2017/745)
* IVDR (EU 2017/746)

### Regulations

* MDCG Guidance

### Standards

* Harmonized Standards — *metadata only (Tier D)*: OJ citation, standard number, edition, harmonized status; no standard text
* Common Specifications — full text ingestible (EU-authored, published in the OJ)

### Registration

* EUDAMED

### Official Sources

* [https://health.ec.europa.eu](https://health.ec.europa.eu)
* [https://eur-lex.europa.eu](https://eur-lex.europa.eu)

---

# Region 4. China (NMPA)

## Domain : Cosmetics

### Primary Laws

* Cosmetic Supervision and Administration Regulation (CSAR)

### Regulations

* Cosmetic Registration
* Filing
* Technical Standards

### Ingredient

* IECIC

### Safety

* Recall
* Adverse Event

### Official Sources

* [https://www.nmpa.gov.cn](https://www.nmpa.gov.cn)
* [https://zwfw.nmpa.gov.cn](https://zwfw.nmpa.gov.cn)

---

## Domain : SaMD

### Primary Laws

* Regulations for the Supervision and Administration of Medical Devices

### Regulations

* Medical Device Registration
* Software Registration Guidance
* AI Medical Device Guidance

### Standards

* YY Standards

### Safety

* Recall
* Adverse Event

### Official Sources

* [https://www.nmpa.gov.cn](https://www.nmpa.gov.cn)

---
