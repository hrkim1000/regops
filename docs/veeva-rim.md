Veeva Systems는 **제약(Pharma), 바이오(Biotech), 의료기기(Medical Device), 백신** 등 생명과학(Life Sciences) 산업을 위한 클라우드 소프트웨어를 제공하는 글로벌 기업입니다. 일반적인 ERP나 문서관리 시스템이 아니라 **규제(Regulatory), 품질(Quality), 임상(Clinical), 안전성(Safety), 영업(CRM)** 업무를 위한 업계 특화 플랫폼을 제공합니다. ([Veeva][1])

설계 중인 **Regulation Domain / Compliance Domain / RegOps Platform**과 가장 관련 있는 제품은 **Veeva Vault RIM**입니다.

## Veeva 제품군

Veeva는 크게 다음과 같은 제품군으로 구성됩니다.

| 영역         | 주요 제품           | 역할                                |
| ---------- | --------------- | --------------------------------- |
| Regulatory | Veeva Vault RIM | 인허가 정보 및 Submission 관리            |
| Quality    | Vault Quality   | eQMS, CAPA, Change Control, Audit |
| Clinical   | Vault Clinical  | eTMF, CTMS, Study Startup         |
| Safety     | Vault Safety    | 이상사례(PV) 관리                       |
| Commercial | Vault CRM       | 영업 및 Medical Affairs              |

---

## Veeva Vault RIM

Veeva Vault의 RIM(Regulatory Information Management)은 규제 업무를 하나의 플랫폼에서 관리하도록 설계되었습니다.

주요 기능은 다음과 같습니다.

* Registration 관리
* Submission Planning
* eCTD Publishing
* Health Authority 대응
* Regulatory Document Management
* Submission Archive
* IDMP 관리
* Regulatory Change Tracking

즉,

```
Regulation
    ↓
Requirement
    ↓
Submission Planning
    ↓
Document Authoring
    ↓
Review / Approval
    ↓
eCTD Publishing
    ↓
FDA/MFDS/EMA 제출
    ↓
Lifecycle Management
```

전체를 지원합니다. ([Veeva Systems][2])

---

## Vault RIM 내부 구성

대표적인 모듈은 다음과 같습니다.

```
Registrations
    제품 허가 정보

Submissions
    제출 문서 작성

Publishing
    eCTD 생성

Submission Archive
    제출본 보관

Health Authority Interactions
    질의응답 관리

Commitments
    후속 조치 관리
```

모든 모듈이 동일한 데이터 모델을 공유하기 때문에 중복 입력 없이 운영할 수 있습니다. ([Veeva Systems][2])

---

## RegOps와 비교

설계 중인 RegOps의 Regulation Domain과 비교하면 다음과 같습니다.

| RegOps             | Veeva              |
| ------------------ | ------------------ |
| Regulation Library | Regulation Content |
| Regulation Parser  | 없음(외부 시스템 활용)      |
| IR Extract         | 없음(문서 중심)          |
| Requirement Graph  | 일부 Metadata        |
| Rule Engine        | Business Rules     |
| Traceability       | Submission 중심      |
| AI Agent           | 최근 AI 기능 추가        |
| Compliance Engine  | Workflow 기반        |

가장 큰 차이점은 **RegOps는 규정을 분석하여 IR(Information Requirement)을 추출하고 이를 코드와 연결하는 AI 기반 구조**인 반면, Veeva는 **완성된 규제 업무 프로세스와 문서 관리**에 초점을 맞춘다는 점입니다.

---

## 최근 AI 기능

최근 Veeva는 AI 기능도 추가하고 있습니다.

* Health Authority Interaction Agent
* Regulatory Application Assistant
* AI 기반 질의응답
* 문서 검색
* Regulatory Narrative 생성

하지만 현재도 중심은 **LLM 기반 Requirement Extraction**보다는 **기존 RIM Workflow의 자동화**입니다. ([Veeva Systems][2])

---

## RegOps와의 차별점

RegOps는 Veeva와 비교해 다음과 같은 차별성을 가질 수 있습니다.

1. **Regulation PDF → IR 자동 추출**
2. **IR → Canonical Knowledge 자동 생성**
3. **GitHub 코드와 Requirement Traceability 자동 연결**
4. **LLM 기반 Compliance Gap 분석**
5. **Evidence 자동 수집**
6. **SaMD 문서 자동 생성**
7. **AI Agent 중심의 Compliance 운영**

이는 Veeva가 강점을 가진 **RIM 운영 플랫폼**보다 한 단계 앞단인 **"규정 이해 → 요구사항 추출 → 개발 산출물 연결"** 영역을 자동화하는 접근입니다.

## RegOps와 Veeva를 함께 사용하는 구조

오히려 두 플랫폼은 경쟁보다는 상호 보완적으로 사용할 수 있습니다.

```
MFDS/FDA Regulation
        │
        ▼
RegOps
  - Regulation Parser
  - IR Extract
  - Requirement Graph
  - Compliance Engine
  - Code Traceability
        │
        ▼
Generated Submission Documents
        │
        ▼
Veeva Vault RIM
  - Submission Management
  - Review
  - Approval
  - eCTD Publishing
  - Health Authority 대응
```

이 구조라면 **RegOps는 AI 기반 규제 해석·개발 컴플라이언스 플랫폼**, **Veeva는 글로벌 제출 및 허가 운영(RIM) 플랫폼**으로 역할을 명확히 분리할 수 있습니다.

[1]: https://ir.veeva.com/overview/?utm_source=chatgpt.com "Veeva Systems Inc. - Investor Relations"
[2]: https://www.veeva.com/products/veeva-rim/?utm_source=chatgpt.com "Veeva RIM | Veeva"

---

Veeva와 유사한 시스템은 크게 **RIM(Regulatory Information Management)**, **eQMS(Quality Management)**, **PLM(Product Lifecycle Management)**, **ALM(Application Lifecycle Management)**, **Clinical** 분야로 나눌 수 있습니다.

**RegOps(Engineering + AI + Regulation + Compliance + Quality + Clinical)**와 가장 직접적으로 비교할 수 있는 경쟁 제품은 다음과 같습니다.

| 제품                | Regulatory | Quality | Clinical | Engineering | AI | 주요 고객           |
| ----------------- | ---------- | ------- | -------- | ----------- | -- | --------------- |
| Veeva Systems     | ★★★★★      | ★★★★★   | ★★★★★    | △           | 일부 | Pharma, Biotech |
| MasterControl     | ★★★★☆      | ★★★★★   | ★★☆☆☆    | △           | 일부 | Medical Device  |
| Sparta Systems    | ★★★★☆      | ★★★★★   | ★☆☆☆☆    | ×           | 일부 | Pharma          |
| Dassault Systèmes | ★★★☆☆      | ★★★★☆   | ★★★★★    | ★★★☆☆       | 일부 | Pharma          |
| Ennov             | ★★★★★      | ★★★★★   | ★★★☆☆    | ×           | 일부 | Pharma          |
| AmpleLogic        | ★★★★☆      | ★★★★★   | ★☆☆☆☆    | ×           | 일부 | Pharma          |
| Arena Solutions   | ★★☆☆☆      | ★★★★☆   | ×        | ★★★★☆       | ×  | Medical Device  |
| Greenlight Guru   | ★★★☆☆      | ★★★★★   | ×        | △           | 일부 | Medical Device  |

### 1. Veeva Systems

* 사실상 글로벌 생명과학 SaaS의 표준
* Regulatory, Clinical, Quality를 하나의 플랫폼으로 통합
* Engineering 영역은 거의 포함하지 않음

**강점**

* Submission
* RIM
* eTMF
* eQMS
* CRM

---

### 2. MasterControl

의료기기 업체에서 많이 사용하는 eQMS 플랫폼입니다.

주요 기능

* Design Control
* DHF
* DMR
* CAPA
* Training
* Supplier Management
* Change Control

특히 **FDA 21 CFR Part 820** 및 **ISO 13485** 대응에 강점이 있습니다.

---

### 3. Sparta Systems (TrackWise Digital)

TrackWise Digital은 품질(QMS) 중심 플랫폼입니다.

주요 기능

* CAPA
* Audit
* Complaint
* Deviation
* Change Control
* Risk

대형 제약회사에서 많이 사용됩니다.

---

### 4. Dassault Systèmes (MEDIDATA)

임상시험(Clinical Trial) 분야에서 매우 강력합니다.

주요 제품

* Clinical Trial
* eConsent
* Randomization
* Data Capture
* Real World Data

Clinical 중심이라 RegOps의 Clinical Domain과 비교하기 좋습니다.

---

### 5. Ennov

유럽에서 많이 사용하는 RIM + eQMS 플랫폼입니다.

특징

* Regulatory
* Quality
* Document Management
* Training
* Validation

---

### 6. Greenlight Guru

SaMD 및 의료기기 스타트업에서 많이 사용하는 플랫폼입니다.

주요 기능

* DHF
* Design Control
* Risk
* CAPA
* Requirements Traceability

스타트업 친화적이라는 평가를 받습니다.

---

## Engineering 영역의 유사 제품

RegOps와 가장 차별화되는 영역입니다.

| 제품                                  | 특징                       |
| ----------------------------------- | ------------------------ |
| Jama Software                       | Requirement Traceability |
| IBM                                 | Requirement Management   |
| Polarion Software                   | ALM                      |
| Codebeamer                          | Medical Device ALM       |
| Siemens Digital Industries Software | PLM                      |

이들은 소스코드, 요구사항, 테스트, 위험관리 간의 추적성을 관리하는 데 강점이 있지만, **규정을 AI가 해석하거나 요구사항을 자동 추출하는 기능은 제한적**입니다.

## RegOps가 노릴 수 있는 시장

현재 시장을 보면 다음과 같이 나뉩니다.

```text
Engineering
    GitHub
    Jira
    DOORS
    Polarion

        ↓

Quality
    MasterControl
    TrackWise
    Greenlight Guru

        ↓

Regulatory
    Veeva RIM
    Ennov

        ↓

Clinical
    Medidata
```

각 제품은 특정 영역에 강하지만, **Engineering → Regulation → Compliance → Quality → Clinical**을 하나의 AI 기반 지식 모델과 자동화 흐름으로 연결하는 플랫폼은 드뭅니다.

### RegOps의 잠재적 차별점

RegOps는 기존 제품들과 달리 다음을 통합할 수 있습니다.

* **Canonical Knowledge Model** 기반으로 모든 도메인을 연결
* 규정(PDF, 가이드라인)에서 **IR(Information Requirement)** 자동 추출
* IR과 Git 코드, 테스트, 위험관리, 문서를 자동 연결하는 **Traceability**
* LLM/에이전트를 활용한 Compliance Gap 분석 및 증적(Evidence) 수집
* SaMD뿐 아니라 화장품 등 다른 규제 산업으로 확장 가능한 **Regulation Domain** 구조

이러한 방향이라면 RegOps는 단순한 RIM이나 eQMS가 아니라 **AI 기반 Regulatory Engineering Platform**이라는 새로운 포지셔닝을 노려볼 수 있습니다.
