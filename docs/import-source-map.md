# Import Source Map

Per-cell inventory of primary laws, regulations, guidance, and official source URLs for the fixed RegOps scope — **2 product domains (SaMD, Cosmetic) × 4 regulatory regions (MFDS, FDA, EU, NMPA) = 8 cells**. See [RegOps.md](RegOps.md) § Scope for the boundary and what is excluded.

This file is the source of truth the Import Agent connectors and parser profiles are built against; the scope tables in the planning docs are summaries of it.

**Ingestion priority is the subsection order within each cell.** `Primary Laws` is always first and is the top tier — the binding statute a cell cannot be ingested without. Subsequent blocks (Regulations, Standards, Guidance, Registration, Ingredient, Safety) descend in priority and vary by cell. `Official Sources` is always last and lists the portals every block above is fetched from.

**`Standards` blocks are metadata-only — Tier D.** ISO/IEC standards and pharmacopoeias (ISO 13485, ISO 14971, IEC 62304, IEC 62366, ISO 27001, …) prohibit source-text storage and AI training. Connectors ingest only the *recognition record* — standard number, edition, recognition/listing number, effective and withdrawal dates, harmonized status — and deep-link to the official copy. Never the standard's body text, even when a regulation makes it legally binding (e.g. QMSR incorporates ISO 13485:2016 by reference, effective 2026-02-02: cite the requirement, link the standard, store neither). See [RegOps.md](RegOps.md) § Data Strategy.

---

# Region 1. Korea (MFDS)

> **Coverage against the authority's own list:**
> [mfds-admrul-coverage.md](mfds-admrul-coverage.md) — generated, not hand-maintained. The 행정규칙
> entries below are what we *intend* to cover; that report is the gap between them and the 511 고시
> MFDS actually publishes under `org=1471000`. Regenerate it with
> `scripts/admrul_triage.py`; a row triaged **add** becomes an entry here.

### Out of scope by decision — MFDS 행정규칙

15 고시 match the discovery keywords and are ruled out. Enforced by `DISCOVERY_EXCLUSIONS`, which
has to be a **negative** list: the keywords are substrings, so 체외진단의료기기 contains 의료기기 and
no edit to the positive side could remove it. Excluded rows keep their own bucket in
[mfds-admrul-coverage.md](mfds-admrul-coverage.md) — *seen and rejected* and *never seen* are
different states, and only the first can be revisited.

| Excluded | Count | Why |
|---|---:|---|
| 체외진단의료기기 | 8 | 체외진단의료기기법 is a **separate statute** and is deliberately absent from Primary Laws. Monitoring its 고시 without the act they implement would be incoherent — revisit only together with adding the statute |
| 범부처 … 연구개발사업 운영관리규정 | 2 | How an R&D grant scheme is administered |
| …감시원 운영 규정 (device **and** cosmetic) | 2 | Citizen-inspector programme administration |
| 의료기기위원회 규정 | 1 | Advisory-committee constitution |
| 맞춤형화장품조제관리사 자격시험 운영에 관한 규정 | 1 | Qualification-exam administration |
| 화장품 법령·제도 등 교육실시기관 지정 및 교육에 관한 규정 | 1 | Training-provider designation |

The last four rows are one category: **how a programme is run, not what a product must do.** None
states an obligation a manufacturer could be found non-compliant against, so each would be noise in
an IR extraction whose unit is one bearer + one modal + one required action (ADR-0004 decision 1).

> **우수화장품 제조 및 품질관리기준 (CGMP) is back *in* scope (2026-08-06).** It was ruled out on
> 2026-08-03 when the cosmetic `GMP` block was dropped from this catalog; that is reversed. It is
> listed under Cosmetics → Regulations, **not** under a restored `GMP` block, so it polls daily like
> the device GMP 고시 rather than weekly — ADR-0003 decision 4 puts `GMP` on a 7-day interval, which
> would under-poll a 고시 carrying substantive manufacturing duties.

## Domain : Cosmetics

### Primary Laws

* 화장품법
* 화장품법 시행령
* 화장품법 시행규칙

### Regulations

*Added from the discovery sweep, 2026-08-06 — the triage backlog decided in. Seeded as
`admrul_<행정규칙ID>` sources; see [mfds-admrul-coverage.md](mfds-admrul-coverage.md) for what
remains outside.*

* 기능성화장품 기준 및 시험방법
* 맞춤형화장품판매업자의 준수사항에 관한 규정
* 수입화장품 품질검사 면제에 관한 규정
* 영유아 또는 어린이 사용 화장품 안전성 자료의 작성·보관에 관한 규정
* 우수화장품 제조 및 품질관리기준
* 의약품등의 타르색소 지정과 기준 및 시험방법
* 인체적용제품의 위해성평가에 관한 규정
* 화장품 가격표시제 실시요령
* 화장품 바코드 표시 및 관리요령
* 화장품 사용할 때의 주의사항 및 알레르기 유발성분 표시에 관한 규정
* 화장품 안전성 정보관리 규정
* 화장품 원료 사용금지 해제·변경 및 사용기준 지정·변경 심사에 관한 규정
* 화장품의 색소 종류 및 기준
* 화장품의 생산ㆍ수입실적 및 원료목록 보고에 관한 규정

### Standards

* 화장품 안전기준 등에 관한 규정
* 기능성화장품 심사 규정
* 표시·광고 규정

### Registration

* 제조업
* 책임판매업
* 기능성화장품 심사

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
* 디지털의료제품법
* 디지털의료제품법 시행령
* 디지털의료제품법 시행규칙

### Regulations

* 의료기기 허가·신고·심사 규정
* 의료기기 소프트웨어 허가심사 가이드라인

*Added from the discovery sweep, 2026-08-06 — the triage backlog decided in. Seeded as
`admrul_<행정규칙ID>` sources; see [mfds-admrul-coverage.md](mfds-admrul-coverage.md) for what
remains outside.*

* (식품의약품안전처) 의료기기 허가·신의료기술평가 등 통합운영에 관한 규정
* 디지털의료기기 임상시험등 계획 승인 및 실시·관리에 관한 규정
* 디지털의료기기 전자적 침해행위 보안 지침
* 디지털의료기기 제조 및 품질관리 기준
* 디지털의료제품 분류 및 등급 지정 등에 관한 규정
* 디지털의료제품 허가·인증·신고·심사 및 평가 등에 관한 규정
* 디지털의료제품법에 따른 기관 지정 등에 관한 규정
* 생산·수입 중단 보고대상 의료기기 및 보고 방법
* 의료기기 기술문서심사기관 지정 및 운영 등에 관한 규정
* 의료기기 부작용 등 안전성 정보 관리에 관한 규정
* 의료기기 생산 및 수출·수입·수리실적 보고에 관한 규정
* 의료기기 수입요건확인 면제 등에 관한 규정
* 의료기기 시판 후 조사에 관한 규정
* 의료기기 위탁 인증·신고의 대상 및 범위 등에 관한 지침
* 의료기기 이물 보고대상 및 절차 등에 관한 규정
* 의료기기 임상시험 기본문서 관리에 관한 규정
* 의료기기 임상시험계획 승인에 관한 규정
* 의료기기 임상시험기관 지정에 관한 규정
* 의료기기 재평가에 관한 규정
* 의료기기 제조 및 품질관리 관련 기관 지정 등에 관한 규정
* 의료기기 제조허가등 갱신에 관한 규정
* 의료기기 통합정보 관리 등에 관한 규정
* 의료기기 표시·기재 등에 관한 규정
* 의료기기 표준코드의 표시 및 관리요령
* 의료기기 품목 및 품목별 등급에 관한 규정
* 의료기기 회수·폐기 등에 관한 규정
* 의료기기소프트웨어제조기업 인증제도 운영에 관한 규정
* 의료기기의 생물학적 안전에 관한 공통기준규격
* 의료기기의 안정성시험 기준
* 의료기기의 전기·기계적 안전에 관한 공통기준규격
* 의료기기의 전자파안전에 관한 공통기준규격
* 인체적용제품의 위해성평가에 관한 규정
* 인터넷 홈페이지 형태 첨부문서 제공 가능 의료기기의 지정에 관한 규정
* 장기추적조사대상 의료기기 지정 및 실사용 정보 제출에 관한 규정
* 추적관리대상 의료기기 기록과 자료 제출에 관한 규정
* 추적관리대상 의료기기 지정에 관한 규정
* 혁신의료기기 기술 및 관리기준 표준화에 관한 규정
* 혁신의료기기 지정 절차 및 방법 등에 관한 규정
* 혁신의료기기 허가 등에 관한 특례 규정
* 희소·긴급도입 필요 의료기기 공급 등에 관한 규정

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
