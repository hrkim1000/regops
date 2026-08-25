# Regulation Library Structure

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
화장품 FDA 인허가를 자동화하는 **Regulation Domain**을 구축한다면, 가장 먼저 해야 할 일은 **Raw Regulation Library**를 구축하는 것입니다. 이 단계에서는 규정을 해석하거나 Requirement(IR)를 추출하지 않고, 원문을 최대한 그대로 수집·버전 관리하는 것이 목적입니다.

미국 화장품은 의료기기(SaMD)와 달리 대부분 **사전 승인(Premarket Approval)** 대상이 아니라, U.S. Food and Drug Administration의 **Federal Food, Drug, and Cosmetic Act(FD&C Act)** 및 **MoCRA(Modernization of Cosmetics Regulation Act of 2022)**를 기반으로 규제를 받습니다. 따라서 "FDA 승인"보다 "FDA 규정 준수(Compliance)"가 더 정확한 표현입니다.

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

### RegOps 관점의 추천

**RegOps(화장품 인허가 자동화)**에서는 단순히 PDF를 저장하는 것보다 다음과 같은 **Raw Regulation → Canonical Knowledge** 파이프라인을 권장합니다.

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

이 구조를 사용하면 FDA Cosmetic 셀뿐 아니라 나머지 7개 셀(SaMD·Cosmetic × MFDS·FDA·EU·NMPA)도 동일한 Canonical Schema로 처리할 수 있습니다. 확장 대상은 그 8개 셀까지이며 — ASEAN Cosmetic Directive 등 범위 밖 규제는 추가하지 않는다 — [RegOps.md](RegOps.md) § Scope 참조.

> 이 문서는 **FDA Cosmetic 한 셀의 라이브러리 구조 예시**다. 수집 대상 문서의 확정 목록은 [`import-source-map.md`](import-source-map.md)에 있으며, 본 문서의 카테고리 목록과 충돌하면 source map이 우선한다.

