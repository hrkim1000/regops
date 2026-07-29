결론부터 말하면 **같은 Import Agent를 사용하는 것이 가장 좋은 설계**입니다. 다만 Import Agent는 **도메인 독립적(Generic)** 으로 만들고, SaMD와 Cosmetic의 차이는 **Connector와 Parser Profile**로 분리하는 것이 확장성과 유지보수 측면에서 유리합니다.

RegOps 아키텍처에서는 다음과 같이 구성하는 것을 권장합니다.

```text
                    Regulation Import Service
                           │
                 Generic Import Agent
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   Source Connector   Change Detector   Scheduler
        │
        ▼
 ┌─────────────────────────────────────────────┐
 │                Source Profile               │
 ├─────────────────────────────────────────────┤
 │ MFDS SaMD          MFDS Cosmetic           │
 │ FDA  SaMD          FDA  Cosmetic           │
 │ EU   SaMD          EU   Cosmetic           │
 │ NMPA SaMD          NMPA Cosmetic           │
 └─────────────────────────────────────────────┘
        (8 cells — 2 domains × 4 regions, 전체)
        │
        ▼
         Parser
        │
        ├── PDF
        ├── HTML
        ├── XML
        ├── DOCX
        ├── HWP
        └── ZIP
        │
        ▼
 Normalized Document
        │
        ▼
 Regulation Library
```

### Import Agent가 담당하는 공통 기능

SaMD와 Cosmetic 모두 동일하게 수행할 수 있는 기능입니다.

* 웹사이트 크롤링
* RSS 감시
* PDF 다운로드
* HTML 수집
* ZIP 압축 해제
* 버전 비교
* SHA256 생성
* 변경 감지
* 메타데이터 생성
* OCR 수행
* 원문 저장(MinIO 등)
* 재시도 및 오류 처리
* 감사 로그 생성

즉, **Import 로직은 규제 분야와 무관하게 재사용**됩니다.

---

### 달라지는 부분은 Source Profile

예를 들어 다음과 같이 설정만 바뀝니다.

| Field          | SaMD             | Cosmetic             |
| -------------- | ---------------- | -------------------- |
| Domain         | `samd`           | `cosmetic`           |
| Authority      | `mfds`           | `mfds`               |
| Parser Profile | `mfds_samd`      | `mfds_cosmetic`      |
| IR Profile     | SaMD Requirement | Cosmetic Requirement |
| Schedule       | Daily            | Daily                |

`domain`은 `samd` | `cosmetic` 두 값만 갖는다. "Medical Device", "Device", "MDR" 등은 사용하지 않는다 — 셀 식별자는 `{authority}_{domain}` 하나로 통일한다.

예시:

```yaml
source:
  authority: mfds
  domain: cosmetic
  profile: mfds_cosmetic
```

```yaml
source:
  authority: fda
  domain: samd
  profile: fda_samd
```

---

### Parser Profile도 분리

예를 들어 같은 MFDS라도 문서 구조가 다를 수 있습니다.

```text
Parser
 ├── mfds_samd.py       ├── mfds_cosmetic.py
 ├── fda_samd.py        ├── fda_cosmetic.py
 ├── eu_samd.py         ├── eu_cosmetic.py
 └── nmpa_samd.py       └── nmpa_cosmetic.py
```

8개 셀에 1:1로 대응하는 8개 프로파일 — 누락된 셀이 있으면 그 셀은 수집되지 않는다.

공통 PDF Parser는 하나이고,

* Heading Rule
* Table Rule
* Notice Rule
* Metadata Rule

만 프로파일마다 다르게 적용합니다.

---

### Regulation Library도 하나

Regulation Library를 SaMD와 Cosmetic으로 분리하지 말고 하나의 Canonical 모델로 관리하는 것이 좋습니다.

```text
RegulationDocument
 ├── authority
 ├── jurisdiction
 ├── regulation_type
 ├── domain
 ├── product_category
 ├── document_type
 ├── source
 └── version
```

예를 들면:

| Authority | Domain     | Cell ID          |
| --------- | ---------- | ---------------- |
| `mfds`    | `samd`     | `mfds_samd`      |
| `fda`     | `samd`     | `fda_samd`       |
| `eu`      | `samd`     | `eu_samd`        |
| `nmpa`    | `samd`     | `nmpa_samd`      |
| `mfds`    | `cosmetic` | `mfds_cosmetic`  |
| `fda`     | `cosmetic` | `fda_cosmetic`   |
| `eu`      | `cosmetic` | `eu_cosmetic`    |
| `nmpa`    | `cosmetic` | `nmpa_cosmetic`  |

---

### 추천 아키텍처

사용자의 프로젝트는 **SaMD와 Cosmetic을 모두 지원하는 규제 플랫폼**을 목표로 하고 있으므로, **Import Agent는 Regulation Domain의 공통 서비스**로 두는 것이 적합합니다.

이후 단계는 도메인별로 분기합니다.

```text
Source Import
      │
      ▼
Regulation Library
      │
      ▼
Document Normalization
      │
      ▼
Section Extraction
      │
      ├────────► SaMD IR Extract
      │
      └────────► Cosmetic IR Extract
```

즉, **Import → Normalization → Section Parsing**까지는 100% 공통으로 사용하고, **IR 추출과 규정 해석(Interpretation), Compliance Rule 생성**부터 SaMD와 Cosmetic 전용 파이프라인으로 분기하는 것이 가장 확장성과 재사용성이 높은 구조입니다.

> 도메인 분기 구조가 일반적(generic)인 것은 유지보수를 위한 설계일 뿐, 범위 확장의 근거가 아니다. RegOps의 범위는 SaMD·Cosmetic × MFDS·FDA·EU·NMPA **8개 셀로 고정**되어 있으며, 의약품·바이오·식품·건강기능식품 및 그 외 규제기관은 범위 밖이다. 확장은 범위 결정을 다시 하기 전까지 하지 않는다 — [RegOps.md](RegOps.md) § Scope.

아래는 **RegOps Regulation Import Agent Specification v1.1** 형태의 통합 문서입니다. 이 문서는 **SaMD + Cosmetics**, **한국(MFDS)·미국(FDA)·EU·중국(NMPA)** 8개 셀을 지원하는 Import Agent의 사양을 정의합니다.

# RegOps Regulation Import Agent

## Global Raw Regulation Source Catalog

**Version:** 1.1

**Purpose**

본 문서는 RegOps Regulation Domain의 Import Agent **사양**을 정의한다. 수집 대상 문서 목록 자체는 [`import-source-map.md`](import-source-map.md)에 있으며, 본 문서는 그것을 어떻게 수집·정규화·파싱하는지를 규정한다.

지원 분야

* SaMD (Software as a Medical Device)
* Cosmetics

지원 지역

* Korea (MFDS)
* United States (FDA)
* European Union (EC)
* China (NMPA)

Import Agent는 아래 Source를 주기적으로 수집하여 Raw Regulation Library를 구축하며, 이후 Normalization → Section Parsing → IR Extraction 파이프라인으로 전달한다.

---

# Canonical Source Structure

```
Region
    └── Authority
            └── Domain
                    ├── Laws
                    ├── Regulations
                    ├── Guidance
                    ├── Standards
                    ├── Registration
                    ├── Labeling
                    ├── Ingredient
                    ├── GMP
                    ├── Safety
                    ├── Recall
                    ├── Notice
                    └── FAQ
```

---

# Source Registry

수집 대상 Source의 **단일 원본은 [`import-source-map.md`](import-source-map.md)** 이다. 8개 셀(SaMD·Cosmetic × MFDS·FDA·EU·NMPA)의 법령·규정·가이던스·표준·등록·안전 항목과 공식 소스 URL이 셀 단위로 정리되어 있으며, Connector와 Parser Profile은 그 파일을 기준으로 구현한다.

본 문서에는 Source 목록을 중복 기재하지 않는다. 카탈로그가 두 곳에 존재하면 한쪽이 반드시 뒤처지고, 어느 쪽이 유효한지 판단할 방법이 없다.

`import-source-map.md`에서 반드시 함께 읽어야 할 규칙:

* **Ingestion priority = 셀 내부 subsection 순서.** `Primary Laws`가 최상위 tier, `Official Sources`가 마지막.
* **`Standards` 블록은 Tier D — 메타데이터만.** ISO/IEC 표준·약전은 원문 저장 및 AI 학습이 금지된다. 표준 번호·판·인정번호·발효일·정합 상태만 수집하고 정품 링크로 연결한다. QMSR이 ISO 13485:2016을 참조편입하여 법적 요건이 된 경우에도 동일하다 — 요건은 인용하되 원문은 저장하지 않는다.
* **수집 대상이 아닌 포털**은 셀 안에 명시되어 있다(EU CPNP, EU EUDAMED 등 로그인 기반 신고 시스템). 규제 원문이 아니므로 Connector를 붙이지 않는다.

---

# Common Raw Formats

Import Agent는 다음 형식을 모두 지원한다.

* HTML
* PDF
* XML
* RSS
* JSON
* DOC/DOCX
* HWP
* XLS/XLSX
* ZIP

---

# Common Metadata

모든 Raw Document는 다음 Metadata를 생성한다.

* Document ID
* Region
* Authority
* Domain
* Regulation Category
* Document Type
* Regulation Number
* Title
* Version
* Status
* Effective Date
* Revision Date
* Language
* Source URL
* File Format
* SHA-256 Checksum
* Imported Time
* Crawl Version
* Original Raw File
* Parsed Text
* OCR Text
* Parser Version

---

# Recommended Crawling Frequency

| Category      | Frequency |
| ------------- | --------- |
| Laws          | Weekly    |
| Regulations   | Daily     |
| Guidance      | Daily     |
| Standards     | Weekly    |
| Registration  | Daily     |
| Safety Alerts | Daily     |
| Recall        | Daily     |
| Notices       | Daily     |
| FAQ           | Weekly    |

---

# Import Agent Pipeline

```
Scheduler
      │
      ▼
Source Registry
      │
      ▼
Crawler / Downloader
      │
      ▼
Raw File Storage
      │
      ▼
Metadata Generator
      │
      ▼
Checksum & Version Detection
      │
      ▼
Normalizer
      │
      ▼
Section Parser
      │
      ▼
Canonical Regulation Library
      │
      ▼
IR Extraction
      │
      ├── SaMD Pipeline
      └── Cosmetics Pipeline
```

이 문서는 **RegOps Regulation Domain**의 **Import Agent 표준 명세**이며, 대상은 8개 셀(SaMD·Cosmetic × MFDS·FDA·EU·NMPA)로 고정된다. 그 외 규제기관은 범위 밖이며, 범위 결정을 다시 하기 전까지 추가하지 않는다 — [RegOps.md](RegOps.md) § Scope.
