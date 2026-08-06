화장품 FDA 인허가를 자동화하는 **Regulation Domain**을 구축한다면, 가장 먼저 해야 할 일은 **Raw Regulation Library**를 구축하는 것입니다. 이 단계에서는 규정을 해석하거나 Requirement(IR)를 추출하지 않고, 원문을 최대한 그대로 수집·버전 관리하는 것이 목적입니다.

미국 화장품은 의료기기(SaMD)와 달리 대부분 **사전 승인(Premarket Approval)** 대상이 아니라, U.S. Food and Drug Administration의 **Federal Food, Drug, and Cosmetic Act(FD&C Act)** 및 **MoCRA(Modernization of Cosmetics Regulation Act of 2022)**를 기반으로 규제를 받습니다. 따라서 "FDA 승인"보다 "FDA 규정 준수(Compliance)"가 더 정확한 표현입니다.

---

# Regulation Library 구조

```
regulation-library/
└── FDA/
    └── Cosmetics/
        ├── Laws/
        ├── Regulations/
        ├── Guidance/
        ├── Compliance/
        ├── WarningLetters/
        ├── Import/
        ├── Labeling/
        ├── Ingredient/
        ├── Registration/
        ├── AdverseEvent/
        └── FAQ/
```

---

# 1. Laws (최우선)

가장 중요한 원본 자료입니다.

수집 대상

* Federal Food Drug and Cosmetic Act
* MoCRA
* Fair Packaging and Labeling Act
* Color Additives Amendments

원본 형태

* PDF
* HTML

메타데이터

```
country: US
agency: FDA
type: LAW
category: Cosmetics
version
effective_date
```

---

# 2. Code of Federal Regulations (CFR)

FDA가 실제 적용하는 규정입니다.

가장 중요한 Part

```
21 CFR Part 700
21 CFR Part 701
21 CFR Part 710
21 CFR Part 720
21 CFR Part 740
21 CFR Part 73
21 CFR Part 74
82
```

세부 내용

* Labeling
* Ingredient
* Color Additive
* Safety
* Packaging

---

# 3. FDA Guidance Documents

가장 많이 변경되는 문서입니다.

예시

* Cosmetic Labeling Guide
* Registration Guidance
* Facility Registration Guidance
* Responsible Person Guidance
* Adverse Event Reporting Guidance
* Safety Substantiation Guidance
* MoCRA Guidance

---

# 4. Compliance Program

FDA Inspection 기준

예시

```
Compliance Program Guidance Manual

Inspection Manual

Inspection Checklist
```

---

# 5. FDA Warning Letters

LLM 학습에 매우 중요합니다.

수집

```
Cosmetic Warning Letters

Import Alert

Enforcement Report
```

추출 항목

```
Violation
Reason
Citation
Action
```

---

# 6. Import Regulation

미국 수출용이라면 반드시 필요합니다.

예시

```
Import Alert

Import Guidance

CBP Documents
```

---

# 7. Registration

MoCRA 이후 새롭게 중요해진 영역입니다.

수집

```
Facility Registration

Product Listing

Responsible Person

Renewal

Amendment
```

---

# 8. Labeling

매우 중요합니다.

수집

```
Labeling Guide

Required Label

Claims

Warning Statement

INCI

Net Quantity

Principal Display Panel
```

---

# 9. Ingredient

```
Color Additive

Restricted Ingredient

Prohibited Ingredient

INCI

Safety Information
```

---

# 10. Adverse Event

MoCRA 핵심

```
Serious Adverse Event

Reporting

Record Keeping

Retention

Follow-up
```

---

# 11. FDA FAQ

의외로 Requirement가 많이 포함됩니다.

수집

```
Cosmetic FAQ

MoCRA FAQ

Registration FAQ

Label FAQ
```

---

# 12. Federal Register

최신 변경사항 관리용입니다.

```
Draft Rule

Final Rule

Notice

Public Comment
```

---

# Raw Document 메타데이터 예시

```json
{
  "document_id":"FDA-COS-GUIDE-0001",
  "country":"US",
  "authority":"FDA",
  "domain":"Cosmetics",
  "category":"Guidance",
  "title":"Cosmetic Labeling Guide",
  "document_type":"Guidance",
  "version":"2025",
  "status":"Effective",
  "effective_date":"2025-01-01",
  "language":"en",
  "format":"PDF",
  "source":"FDA",
  "url":"",
  "checksum":"",
  "import_date":"",
  "tags":[
      "Labeling",
      "Claims",
      "INCI"
  ]
}
```

---

# RegOps Import 우선순위

| Priority | Category           | 중요도   |
| -------- | ------------------ | ----- |
| P1       | Laws               | ★★★★★ |
| P1       | CFR                | ★★★★★ |
| P1       | Guidance           | ★★★★★ |
| P2       | Registration       | ★★★★☆ |
| P2       | Labeling           | ★★★★☆ |
| P2       | Ingredient         | ★★★★☆ |
| P2       | Adverse Event      | ★★★★☆ |
| P3       | Compliance Program | ★★★☆☆ |
| P3       | Warning Letter     | ★★★☆☆ |
| P3       | Import             | ★★★☆☆ |
| P4       | FAQ                | ★★☆☆☆ |
| P4       | Federal Register   | ★★★☆☆ |

### MedOps/CompliOps 관점의 추천

현재 구상 중인 **CompliOps(화장품 인허가 자동화)**에서는 단순히 PDF를 저장하는 것보다 다음과 같은 **Raw Regulation → Canonical Knowledge** 파이프라인을 권장합니다.

```
FDA Website
      │
      ▼
Raw Regulation Import
(PDF / HTML / XML)
      │
      ▼
Normalization
(텍스트, 표, 이미지 분리)
      │
      ▼
Document Metadata
(기관, 국가, 버전, 시행일, 문서 유형)
      │
      ▼
Section Parser
(Chapter → Section → Paragraph)
      │
      ▼
Canonical Regulation Document
      │
      ▼
IR Extract
      │
      ▼
Regulation Knowledge Graph
```

이 구조를 사용하면 이후 FDA뿐 아니라 MFDS, EU CPNP, EU Cosmetics Regulation (EC No 1223/2009), ASEAN Cosmetic Directive 등 다른 국가·지역 규정도 동일한 Canonical Schema로 확장할 수 있습니다.

아래와 같이 **FDA 화장품 인허가(Regulation Library) Raw Regulation 수집 링크 문서**를 만드는 것을 권장합니다. 이 문서는 Import Agent가 주기적으로 수집할 공식 소스를 정의하는 기준 문서로 사용할 수 있습니다.

# FDA Cosmetics Regulation Library

## Raw Regulation Source Links

**Version:** 1.0
**Authority:** U.S. Food and Drug Administration (FDA)
**Domain:** Cosmetics
**Purpose:** CompliOps Regulation Library Raw Document Collection

---

# 1. Laws

| Document                                          | URL                                                                                                                                                                                                                | Priority |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| FD&C Act                                          | [https://www.fda.gov/regulatory-information/laws-enforced-fda/federal-food-drug-and-cosmetic-act-fdc-act](https://www.fda.gov/regulatory-information/laws-enforced-fda/federal-food-drug-and-cosmetic-act-fdc-act) | P1       |
| Modernization of Cosmetics Regulation Act (MoCRA) | [https://www.fda.gov/cosmetics/modernization-cosmetics-regulation-act-2022-mocra](https://www.fda.gov/cosmetics/modernization-cosmetics-regulation-act-2022-mocra)                                                 | P1       |
| Fair Packaging and Labeling Act                   | [https://www.fda.gov/regulatory-information/laws-enforced-fda/fair-packaging-and-labeling-act-fpla](https://www.fda.gov/regulatory-information/laws-enforced-fda/fair-packaging-and-labeling-act-fpla)             | P2       |

---

# 2. Code of Federal Regulations (21 CFR)

| Regulation                                | URL                                                                                                                                            | Priority |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 21 CFR Part 700                           | [https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-700](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-700) | P1       |
| 21 CFR Part 701                           | [https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-701](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-701) | P1       |
| 21 CFR Part 710                           | [https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-710](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-710) | P1       |
| 21 CFR Part 740                           | [https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-740](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-G/part-740) | P1       |
| Color Additives (21 CFR Parts 73, 74, 82) | [https://www.ecfr.gov/current/title-21](https://www.ecfr.gov/current/title-21)                                                                 | P2       |

---

# 3. FDA Cosmetics Main Portal

| Resource                     | URL                                                                                                                      | Priority |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------- |
| Cosmetics Home               | [https://www.fda.gov/cosmetics](https://www.fda.gov/cosmetics)                                                           | P1       |
| Cosmetics Guidance           | [https://www.fda.gov/cosmetics/cosmetics-guidance-documents](https://www.fda.gov/cosmetics/cosmetics-guidance-documents) | P1       |
| Cosmetics Laws & Regulations | [https://www.fda.gov/cosmetics/cosmetics-laws-regulations](https://www.fda.gov/cosmetics/cosmetics-laws-regulations)     | P1       |

---

# 4. Guidance Documents

| Document           | URL                                                                                                                                                                | Priority |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| Guidance Documents | [https://www.fda.gov/cosmetics/cosmetics-guidance-documents](https://www.fda.gov/cosmetics/cosmetics-guidance-documents)                                           | P1       |
| Cosmetic Labeling  | [https://www.fda.gov/cosmetics/cosmetic-labeling-regulations](https://www.fda.gov/cosmetics/cosmetic-labeling-regulations)                                         | P1       |
| MoCRA Guidance     | [https://www.fda.gov/cosmetics/modernization-cosmetics-regulation-act-2022-mocra](https://www.fda.gov/cosmetics/modernization-cosmetics-regulation-act-2022-mocra) | P1       |

---

# 5. Registration (MoCRA)

| Document              | URL                                                                                                                                                                                        | Priority |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| Facility Registration | [https://www.fda.gov/cosmetics/registration-listing-cosmetic-product-facilities-and-products](https://www.fda.gov/cosmetics/registration-listing-cosmetic-product-facilities-and-products) | P1       |
| Product Listing       | [https://www.fda.gov/cosmetics/registration-listing-cosmetic-product-facilities-and-products](https://www.fda.gov/cosmetics/registration-listing-cosmetic-product-facilities-and-products) | P1       |
| Responsible Person    | [https://www.fda.gov/cosmetics](https://www.fda.gov/cosmetics)                                                                                                                             | P2       |

---

# 6. Labeling

| Resource          | URL                                                                                                                        | Priority |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------- | -------- |
| Cosmetic Labeling | [https://www.fda.gov/cosmetics/cosmetic-labeling-regulations](https://www.fda.gov/cosmetics/cosmetic-labeling-regulations) | P1       |
| Labeling Guide    | [https://www.fda.gov/cosmetics](https://www.fda.gov/cosmetics)                                                             | P2       |

---

# 7. Ingredient

| Resource               | URL                                                                                                                                                            | Priority |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| Color Additives        | [https://www.fda.gov/cosmetics/cosmetic-products/color-additives-and-cosmetics](https://www.fda.gov/cosmetics/cosmetic-products/color-additives-and-cosmetics) | P1       |
| Ingredient Information | [https://www.fda.gov/cosmetics](https://www.fda.gov/cosmetics)                                                                                                 | P2       |

---

# 8. Adverse Event Reporting

| Resource                | URL                                                                                                                                                                                              | Priority |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| Adverse Event Reporting | [https://www.fda.gov/cosmetics](https://www.fda.gov/cosmetics)                                                                                                                                   | P1       |
| MedWatch                | [https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program](https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program) | P2       |

---

# 9. Warning Letters

| Resource        | URL                                                                                                                                                                                                                                                                          | Priority |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| Warning Letters | [https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters) | P2       |

---

# 10. Import / Export

| Resource       | URL                                                                                                                                                          | Priority |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| Import Program | [https://www.fda.gov/industry/import-program-food-and-drug-administration-fda](https://www.fda.gov/industry/import-program-food-and-drug-administration-fda) | P2       |
| Import Alerts  | [https://www.accessdata.fda.gov/cms_ia/importalert_1.html](https://www.accessdata.fda.gov/cms_ia/importalert_1.html)                                         | P2       |

---

# 11. Federal Register

| Resource             | URL                                                                                                                                            | Priority |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FDA Federal Register | [https://www.federalregister.gov/agencies/food-and-drug-administration](https://www.federalregister.gov/agencies/food-and-drug-administration) | P2       |

---

# 12. FDA News

| Resource     | URL                                                                | Priority |
| ------------ | ------------------------------------------------------------------ | -------- |
| FDA Newsroom | [https://www.fda.gov/news-events](https://www.fda.gov/news-events) | P3       |

---

# Recommended Crawling Frequency

| Category         | Frequency |
| ---------------- | --------- |
| Laws             | Monthly   |
| CFR              | Weekly    |
| Guidance         | Daily     |
| MoCRA            | Daily     |
| Registration     | Daily     |
| Warning Letters  | Daily     |
| Federal Register | Daily     |
| FDA News         | Daily     |

---

# Supported Raw Formats

* HTML
* PDF
* XML
* RSS
* JSON (if available)

---

# Metadata to Store

* Document ID
* Source URL
* Title
* Authority
* Country
* Regulation Type
* Category
* Version
* Effective Date
* Last Updated
* Language
* File Format
* SHA-256 Checksum
* Imported Time
* Crawl Version
* Original Raw File
* Parsed Text
* OCR Text (if applicable)
* Parser Version

이 문서는 **CompliOps Regulation Import Agent**의 초기 수집 목록으로 바로 사용할 수 있습니다. 이후에는 **EU(EC 1223/2009), UK, ASEAN, 중국 NMPA, 일본 PMDA, 한국 MFDS**까지 동일한 형식으로 확장하여 국가별 Regulation Source Catalog를 구축하는 것을 권장합니다.

결론부터 말하면 **아니요. `open.law.go.kr`처럼 FDA Law/CFR를 직접 조회하는 Open API는 없습니다.**

FDA는 `openFDA API`를 제공하지만, 이것은 **규제 데이터(제품, 허가, 리콜, adverse event 등)**를 위한 API이며 **법령(21 CFR, FD&C Act) 자체를 제공하는 API는 아닙니다. ([U.S. Food and Drug Administration][1])

RegOps에서 **Regulation Import Agent**를 설계한다면 FDA는 다음과 같이 구성하는 것이 가장 적합합니다.

| 데이터              | 제공처                  | API 여부          | 권장           |
| ---------------- | -------------------- | --------------- | ------------ |
| 21 CFR           | eCFR                 | XML/JSON 제공(공식) | ⭐⭐⭐⭐⭐        |
| Federal Register | Federal Register API | REST API        | ⭐⭐⭐⭐⭐        |
| FDA Guidance     | FDA Website          | API 없음          | HTML/PDF 크롤링 |
| Guidance PDF     | FDA Website          | API 없음          | PDF 다운로드     |
| Warning Letter   | FDA Website          | API 없음          | HTML 크롤링     |
| openFDA          | openFDA              | REST API        | 제품/허가 데이터만   |

---

# 1. 법령(21 CFR)

FDA 규정은 실제로는 **Code of Federal Regulations(CFR)** 에 존재합니다.

SaMD라면 주로

```
21 CFR Part 11
21 CFR Part 803
21 CFR Part 806
21 CFR Part 807
21 CFR Part 812
21 CFR Part 820
```

등을 수집하게 됩니다. FDA도 의료기기 규정이 **Title 21 CFR Parts 800–1299**에 포함된다고 안내합니다. ([U.S. Food and Drug Administration][2])

---

# 2. 가장 좋은 방법 : eCFR API

미국 정부는 **eCFR API**를 제공합니다.

Import Agent

```
Import Agent
      ↓
eCFR API
      ↓
XML
      ↓
Parser
      ↓
Canonical Regulation
```

즉,

```
eCFR XML
        ↓
Section
Paragraph
Subparagraph
Appendix
```

까지 모두 가져올 수 있습니다.

---

# 3. Regulation 변경사항

MFDS RSS와 같은 역할은

**Federal Register API**

입니다.

여기에서

* Proposed Rule
* Final Rule
* Notice

를 API로 받을 수 있습니다.

Workflow

```
Federal Register API

↓

Today's Rule

↓

21 CFR 변경

↓

Import Agent

↓

Regulation Version
```

---

# 4. FDA Guidance

FDA의 Guidance는 API가 없습니다.

예를 들어

```
Guidance for Clinical Decision Support Software

AI/ML SaMD Guidance

Cybersecurity Guidance

Software Validation Guidance
```

모두 PDF입니다.

따라서

```
Crawler

↓

PDF Download

↓

PDF Parser

↓

LLM

↓

Canonical Regulation
```

형태가 일반적입니다.

---

# 5. openFDA API는 무엇인가?

openFDA는 Regulation API가 아닙니다.

예를 들어

```
Drug Label

Recall

510(k)

PMA

UDI

Device Classification

Registration

Listing
```

등의 데이터를 REST API로 제공합니다. 규정 원문이 아니라 규제 데이터와 허가 정보를 제공하는 플랫폼입니다. ([U.S. Food and Drug Administration][1])

---

# 6. RegOps Import Agent 권장 구조

```
FDA Import Agent
│
├── eCFR Connector
│      ├── XML Download
│      ├── Version Check
│      └── Diff
│
├── Federal Register Connector
│      ├── API
│      └── Rule Monitoring
│
├── FDA Guidance Connector
│      ├── HTML
│      ├── PDF
│      └── Metadata
│
├── openFDA Connector
│      ├── Device
│      ├── Drug
│      ├── Recall
│      └── UDI
│
└── Parser
       ├── XML Parser
       ├── HTML Parser
       ├── PDF Parser
       └── IR Extractor
```

### RegOps에서 권장하는 Raw Source 우선순위

| 우선순위  | Source               | 용도             |
| ----- | -------------------- | -------------- |
| ⭐⭐⭐⭐⭐ | eCFR API             | 21 CFR 법령 원문   |
| ⭐⭐⭐⭐⭐ | Federal Register API | 법령 변경 모니터링     |
| ⭐⭐⭐⭐  | FDA Guidance PDF     | Guidance 문서    |
| ⭐⭐⭐⭐  | FDA Guidance HTML    | Guidance 메타데이터 |
| ⭐⭐⭐   | openFDA API          | 허가·제품·리콜 데이터   |

이 구조는 이전에 설계한 **RegOps Regulation Domain**의 Import Agent 아키텍처와도 잘 맞습니다. `eCFR API`를 법령의 공식 원천(Source of Truth)으로 사용하고, `Federal Register API`를 변경 감지(Change Monitoring) 용도로, `FDA Guidance`를 해석 지식(Interpretation Knowledge) 생성용으로 사용하면 SaMD 규제 플랫폼에 적합한 규제 수집 파이프라인을 구축할 수 있습니다.

[1]: https://www.fda.gov/science-research/health-informatics-fda/openfda?utm_source=chatgpt.com "openFDA | FDA"
[2]: https://www.fda.gov/medical-devices/overview-device-regulation/code-federal-regulations-cfr?utm_source=chatgpt.com "Code of Federal Regulations (CFR) | FDA"

RegOps의 Import Agent에서 사용할 공식 eCFR URL은 다음과 같습니다.

### 1. eCFR 메인 사이트

* [eCFR (Electronic Code of Federal Regulations)](https://www.ecfr.gov?utm_source=chatgpt.com)

  * CFR 최신 버전을 검색하고 조회할 수 있는 공식 사이트입니다. ([National Archives][1])

### 2. eCFR API 문서 (권장)

* [eCFR API Documentation](https://www.ecfr.gov/developers/documentation/api/v1?utm_source=chatgpt.com)

  * JSON/XML API 사용법과 엔드포인트를 제공합니다. ([APIs.io][2])

### 3. 의료기기(SaMD) 관련 Title 21

* [Title 21 - Food and Drugs](https://www.ecfr.gov/current/title-21?utm_source=chatgpt.com)

  * FDA 관련 규정이 포함된 Title입니다. ([U.S. Food and Drug Administration][3])

### 4. 자주 사용하는 의료기기 규정

| 규정                                       | URL                                                                                                      |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 21 CFR Part 11 (Electronic Records)      | [Part 11](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11?utm_source=chatgpt.com)   |
| 21 CFR Part 803 (MDR)                    | [Part 803](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-803?utm_source=chatgpt.com) |
| 21 CFR Part 806                          | [Part 806](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-806?utm_source=chatgpt.com) |
| 21 CFR Part 807 (Registration & Listing) | [Part 807](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-807?utm_source=chatgpt.com) |
| 21 CFR Part 812 (IDE)                    | [Part 812](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-812?utm_source=chatgpt.com) |
| 21 CFR Part 820 (QMSR/QSR)               | [Part 820](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820?utm_source=chatgpt.com) |

### 5. Import Agent에서 가장 유용한 API

RegOps에서는 다음 API들을 주로 사용하게 됩니다.

* Agencies

  ```
  https://www.ecfr.gov/api/admin/v1/agencies.json
  ```

* Titles

  ```
  https://www.ecfr.gov/api/versioner/v1/titles.json
  ```

* Title 21 전체 구조

  ```
  https://www.ecfr.gov/api/versioner/v1/structure/current/title-21.json
  ```

* 특정 날짜 기준 Title 21

  ```
  https://www.ecfr.gov/api/versioner/v1/structure/2026-08-01/title-21.json
  ```

* 특정 Part(XML)

  ```
  https://www.ecfr.gov/api/versioner/v1/full/2026-08-01/title-21.xml?part=820
  ```

이러한 **Versioner API**를 사용하면 날짜별 스냅샷과 구조(JSON), 전체 본문(XML)를 가져올 수 있어, RegOps의 **Regulation Versioning**, **Diff Detection**, **Canonical Regulation 생성**에 매우 적합합니다. ([APIs.io][2])

[1]: https://www.archives.gov/federal-register/cfr/about-ecfr?utm_source=chatgpt.com "About the Electronic Code of Federal Regulations | National Archives"
[2]: https://apis.io/apis/ecfr/search/?utm_source=chatgpt.com "eCFR Search API — Documentation, OpenAPI | APIs.io APIs"
[3]: https://www.fda.gov/medical-devices/overview-device-regulation/code-federal-regulations-cfr?utm_source=chatgpt.com "Code of Federal Regulations (CFR) | FDA"

네, **가능합니다.** 다만 MFDS처럼 "RSS URL 하나"가 있는 구조는 아니고, **eCFR와 FederalRegister.gov에서 구독(Subscribe) 기능과 RSS를 제공합니다.**

RegOps에서는 다음 구성이 가장 좋습니다.

| 목적            | 권장 방식                      | 비고                        |
| ------------- | -------------------------- | ------------------------- |
| 법령 변경(21 CFR) | ⭐ eCFR Subscribe/RSS       | Part별 변경 추적 가능            |
| 신규 Rule       | ⭐ Federal Register RSS/API | Proposed Rule, Final Rule |
| FDA Guidance  | RSS 없음                     | 웹 크롤링                     |
| FDA News      | RSS 제공                     | 보조 정보                     |

### 1. eCFR 변경 RSS (추천)

예를 들어 **21 CFR Part 820** 페이지에 가면 **Subscribe** 기능이 있으며, 해당 CFR 조항의 변경 사항을 RSS 또는 이메일로 구독할 수 있습니다. Part, Subpart, Section 단위까지 변경 추적이 가능합니다. ([National Archives][1])

예시

```
21 CFR Part 820

↓

Subscribe

↓

RSS

↓

Import Agent
```

SaMD에서는 다음 Part들을 각각 구독하는 것을 권장합니다.

* Part 11
* Part 803
* Part 806
* Part 807
* Part 812
* Part 820

---

### 2. Federal Register RSS (가장 중요)

실제 규정이 개정되면 먼저 **Federal Register**에 게시됩니다.

RSS로 받을 수 있는 항목은 다음과 같습니다.

* Final Rule
* Proposed Rule
* Notice
* Guidance 관련 공고

또한 검색 조건 기반의 **Custom RSS Feed**도 생성할 수 있어, 예를 들어 "FDA" 또는 "21 CFR Part 820" 관련 문서만 구독하는 것도 가능합니다. ([GovInfo][2])

---

### 3. RegOps Import Agent 권장 설계

```text
Federal Register RSS
        │
        ▼
RSS Polling
        │
        ▼
Change Detector
        │
        ▼
Regulation Version
        │
        ▼
LLM Interpretation
```

그리고

```text
eCFR Subscribe
        │
        ▼
RSS Polling
        │
        ▼
Diff Generator
        │
        ▼
Canonical Regulation
```

---

## RegOps에서는 API와 RSS를 함께 사용하는 것을 추천합니다.

| Source           | API | RSS | 용도            |
| ---------------- | --- | --- | ------------- |
| eCFR             | ✅   | ✅   | 법령 원문 및 변경 감지 |
| Federal Register | ✅   | ✅   | 신규/개정 규정 모니터링 |
| FDA Guidance     | ❌   | ❌   | PDF/HTML 크롤링  |
| openFDA          | ✅   | ❌   | 허가·제품·리콜 데이터  |

**RegOps 관점에서는 `Federal Register API + eCFR API + RSS`를 함께 사용하는 것이 가장 안정적입니다.** RSS는 빠른 변경 감지(Trigger) 용도로 사용하고, 변경이 감지되면 API를 호출해 최신 XML/JSON을 가져와 Diff를 생성하는 방식이 효율적입니다.

[1]: https://www.archives.gov/federal-register/faqs?utm_source=chatgpt.com "Frequently Asked Questions for OFR | National Archives"
[2]: https://www.govinfo.gov/feeds?utm_source=chatgpt.com "RSS Feeds | GovInfo"

네. **510(k)는 RSS보다는 openFDA API를 사용하는 것이 표준적인 방법**입니다.

510(k)는 **법령(Law/Regulation)이 아니라 의료기기 사전시장 신고(Premarket Notification) 데이터**입니다.

---

## 1. 510(k) 데이터 소스

| 데이터                   | 권장 Source    | API | RSS |
| --------------------- | ------------ | --- | --- |
| 510(k) Clearance      | openFDA      | ✅   | ❌   |
| PMA                   | openFDA      | ✅   | ❌   |
| De Novo               | FDA Database | 일부  | ❌   |
| Device Classification | openFDA      | ✅   | ❌   |
| Recall                | openFDA      | ✅   | ❌   |

---

## 2. openFDA 510(k) API

기본 Endpoint

```text
https://api.fda.gov/device/510k.json
```

예시

최근 승인 10건

```text
https://api.fda.gov/device/510k.json?limit=10
```

특정 회사

```text
https://api.fda.gov/device/510k.json?search=applicant:"Philips"
```

특정 제품코드

```text
https://api.fda.gov/device/510k.json?search=product_code:QIH
```

특정 날짜

```text
decision_date:[20260101+TO+20261231]
```

---

## 3. 가져올 수 있는 주요 정보

```json
{
  "k_number": "K250123",
  "device_name": "...",
  "applicant": "...",
  "decision_date": "...",
  "decision_description": "...",
  "product_code": "...",
  "advisory_committee": "...",
  "review_panel": "...",
  "statement_or_summary": "...",
  "predicate_device": "...",
  "openfda": { ... }
}
```

RegOps에서는

```
510K Submission

↓

Product Profile

↓

Predicate Device

↓

Regulatory Intelligence
```

용도로 많이 사용됩니다.

---

## 4. RegOps에서의 활용

Regulation Domain과는 별도의 **Regulatory Intelligence** 데이터로 관리하는 것을 권장합니다.

```text
FDA Connector
│
├── eCFR
├── Federal Register
├── Guidance
├── 510(k)
├── PMA
├── Recall
├── UDI
└── Device Classification
```

---

## 5. SaMD에서 특히 유용한 활용

510(k) 데이터는 단순히 허가 목록이 아니라 다음과 같은 분석에도 활용할 수 있습니다.

* 경쟁 제품(Competitor) 분석
* Predicate Device 자동 추천
* 유사 제품 검색
* 제출 빈도 및 승인 추세 분석
* 제품 코드(Product Code)별 시장 동향
* Review Panel 및 Advisory Committee 분석
* 제출 문서(Statement/Summary) 기반 RAG 구축

따라서 **RegOps의 Regulation Domain**에는 `eCFR`, `Federal Register`, `FDA Guidance`를 두고, **Regulatory Intelligence Domain**(또는 Regulation Domain의 하위 서비스)에는 `510(k)`, `PMA`, `Recall`, `UDI`, `Device Classification` 등을 함께 수집하면 규제 준수와 시장 인텔리전스를 모두 지원하는 플랫폼을 구축할 수 있습니다.

RegOps 관점에서 보면 **FDA는 하나의 API가 아니라 여러 개의 공식 데이터 소스를 조합해야 하는 구조**입니다.

---

# 전체 Architecture

```text
                    FDA
                     │
     ┌───────────────┼────────────────┐
     │               │                │
 Regulation      Intelligence      Submission
     │               │                │
 eCFR          openFDA          Cosmetics Direct
 Federal Reg   510(k)           ESG
 Guidance       PMA
 RSS            Recall
```

---

# 1. SaMD FDA 전체 Flow

```text
Product Definition
        │
        ▼
Device Classification
        │
        ▼
Predicate Search
        │
        ▼
Applicable Regulation
        │
        ▼
Guidance Search
        │
        ▼
QMS(QMSR)
        │
        ▼
510(k)/De Novo/PMA
        │
        ▼
FDA Review
        │
        ▼
Clearance
        │
        ▼
Post Market
```

### 각 단계별 사용할 Source

| 단계                    | Source           | API | RSS |
| --------------------- | ---------------- | --- | --- |
| Regulation            | eCFR             | ✅   | ✅   |
| Rule Change           | Federal Register | ✅   | ✅   |
| Guidance              | FDA Guidance     | ❌   | ❌   |
| Device Classification | openFDA          | ✅   | ❌   |
| Predicate Search      | openFDA 510(k)   | ✅   | ❌   |
| PMA                   | openFDA          | ✅   | ❌   |
| Recall                | openFDA          | ✅   | ❌   |
| MDR                   | openFDA          | ✅   | ❌   |
| Registration          | openFDA          | ✅   | ❌   |
| UDI                   | openFDA          | ✅   | ❌   |

openFDA는 의료기기의 510(k), PMA, 분류(Classification), 등록(Listing), 리콜, 이상사례 등 다양한 데이터셋을 REST API로 제공합니다. ([Open FDA][1])

---

# 2. Cosmetic FDA(MoCRA) 전체 Flow

MoCRA 이후의 일반적인 절차는 다음과 같습니다.

```text
Ingredient Review
        │
        ▼
Label Review
        │
        ▼
Safety Substantiation
        │
        ▼
Facility Registration
        │
        ▼
Product Listing
        │
        ▼
US Agent
        │
        ▼
Marketing
        │
        ▼
Adverse Event Monitoring
```

### 사용할 Source

| 단계                    | Source                 | API    | RSS |
| --------------------- | ---------------------- | ------ | --- |
| Regulation            | eCFR                   | ✅      | ✅   |
| MoCRA                 | FD&C Act / Guidance    | PDF    | ❌   |
| Guidance              | FDA Guidance           | ❌      | ❌   |
| Facility Registration | Cosmetics Direct       | Portal | ❌   |
| Product Listing       | Cosmetics Direct       | Portal | ❌   |
| Adverse Event         | openFDA Cosmetic Event | ✅      | ❌   |

MoCRA에서는 **시설 등록(Facility Registration)** 및 **제품 등록(Product Listing)**을 `Cosmetics Direct` 전자 제출 포털을 통해 수행하며, 이는 승인 제도가 아니라 등록 제도입니다. ([U.S. Food and Drug Administration][2])

---

# 3. Regulation Source

| Source            | 내용                    | Import 방식      |
| ----------------- | --------------------- | -------------- |
| eCFR              | 21 CFR                | XML / JSON API |
| Federal Register  | Proposed / Final Rule | REST API       |
| FDA Guidance      | PDF                   | Crawling       |
| FDA Guidance HTML | HTML                  | Crawling       |

---

# 4. Intelligence Source

| Source         | 내용                     | API |
| -------------- | ---------------------- | --- |
| 510(k)         | Clearance              | ✅   |
| PMA            | Approval               | ✅   |
| Classification | Device Code            | ✅   |
| Registration   | Establishment          | ✅   |
| Recall         | Recall                 | ✅   |
| MDR            | Adverse Event          | ✅   |
| UDI            | Device Identifier      | ✅   |
| Cosmetic Event | Cosmetic Adverse Event | ✅   |

openFDA는 의료기기뿐 아니라 화장품 이상사례(Cosmetic Events) API도 제공합니다. ([Open FDA][1])

---

# 5. RSS / Monitoring

| Source           | RSS | API |
| ---------------- | --- | --- |
| eCFR             | ✅   | ✅   |
| Federal Register | ✅   | ✅   |
| FDA News         | ✅   | ❌   |
| FDA Guidance     | ❌   | ❌   |
| openFDA          | ❌   | ✅   |

---

# 6. RegOps Import Agent

```text
FDA Import Agent
│
├── Regulation
│      ├── eCFR API
│      ├── Federal Register API
│      ├── RSS Monitor
│      └── Guidance Crawler
│
├── Intelligence
│      ├── 510(k)
│      ├── PMA
│      ├── Classification
│      ├── Recall
│      ├── MDR
│      ├── Registration
│      ├── UDI
│      └── Cosmetic Event
│
├── Submission
│      ├── Cosmetics Direct
│      └── ESG(전자 제출)
│
└── Parser
       ├── XML
       ├── JSON
       ├── HTML
       ├── PDF
       └── IR Extractor
```

---

# 7. RegOps Canonical Knowledge Layer

```text
FDA
│
├── Regulation
│      ├── Law
│      ├── Rule
│      ├── Guidance
│      └── Interpretation
│
├── Product Intelligence
│      ├── Device Classification
│      ├── Predicate
│      ├── 510(k)
│      ├── PMA
│      ├── Recall
│      ├── MDR
│      └── UDI
│
├── Cosmetic
│      ├── Facility
│      ├── Product Listing
│      ├── Ingredient
│      ├── Label
│      └── Adverse Event
│
└── Monitoring
       ├── RSS
       ├── Change Detection
       └── Version Management
```

## 최종 권장 데이터 소스 매트릭스

| 구분                                      | Source           | API           | RSS | RegOps 활용도 |
| --------------------------------------- | ---------------- | ------------- | --- | ---------- |
| 법령(21 CFR)                              | eCFR             | ✅             | ✅   | ⭐⭐⭐⭐⭐      |
| 법령 변경                                   | Federal Register | ✅             | ✅   | ⭐⭐⭐⭐⭐      |
| FDA Guidance                            | PDF/HTML         | ❌             | ❌   | ⭐⭐⭐⭐⭐      |
| 510(k)                                  | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐⭐      |
| PMA                                     | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐       |
| Device Classification                   | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐⭐      |
| Registration & Listing (Medical Device) | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐       |
| UDI                                     | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐       |
| MDR / Adverse Events                    | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐       |
| Recall                                  | openFDA          | ✅             | ❌   | ⭐⭐⭐⭐       |
| Cosmetic Adverse Events                 | openFDA          | ✅             | ❌   | ⭐⭐⭐        |
| Cosmetic Facility Registration          | Cosmetics Direct | 포털(공개 API 없음) | ❌   | ⭐⭐⭐⭐       |
| Cosmetic Product Listing                | Cosmetics Direct | 포털(공개 API 없음) | ❌   | ⭐⭐⭐⭐       |

이 구성을 기반으로 하면 RegOps의 **FDA Import Agent**는 규제 원문(eCFR), 규정 변경(Federal Register), 규제 해석(Guidance), 의료기기 인텔리전스(openFDA), 화장품 등록(MoCRA/Comestics Direct)까지 모두 포괄하는 일관된 수집 파이프라인을 구축할 수 있습니다.

[1]: https://open.fda.gov/apis/cosmetic/?utm_source=chatgpt.com "openFDA"
[2]: https://www.fda.gov/cosmetics/registration-listing-cosmetic-product-facilities-and-products?utm_source=chatgpt.com "Registration & Listing of Cosmetic Product Facilities and Products | FDA"
