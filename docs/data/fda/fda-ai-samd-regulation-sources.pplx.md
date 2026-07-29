# FDA AI/ML 기반 의료기기 소프트웨어(SaMD) 규제 원문 자료 수집본

## 개요 및 사용 방법

본 문서는 한국 AI/ML 기반 의료 소프트웨어 개발사가 미국 FDA 인허가(510(k), De Novo, PMA 등)를 준비할 때 참조할 수 있도록, FDA·eCFR·Federal Register·govinfo·IMDRF 등 1차 규제 원문을 직접 확인(fetch)하여 정리한 자료 모음이다. 조사 기준일은 2026년 7월 29일(KST)이며, 모든 링크는 원문 조사 과정에서 실제로 확인된 URL만 사용하였고 창작된 URL은 없다. 확인되지 않은 사항은 본문에 **'미확인'**으로 명시하였다(11절 참조). 각 섹션은 (1) 본문 설명, (2) 실무 체크리스트, (3) 9절의 마스터 링크 목록과 상호 참조되도록 구성되어 있다. 규정·가이던스명은 최초 언급 시 영문 정식 원제를 병기한다.

---

## 1. 인허가 경로 비교

미국에서 의료기기(SaMD/AI-ML 포함)를 시판하기 위한 주요 경로는 다음과 같다([FDA Premarket Notification 510(k)](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k); [FDA De Novo Classification Request](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/de-novo-classification-request); [FDA Premarket Approval (PMA)](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-approval-pma)).

| 경로 (Pathway) | 근거 법조항 (FD&C Act) | CFR | MDUFA 심사목표 | 필요 데이터 | 적용 상황 |
|---|---|---|---|---|---|
| 510(k) Exempt | 해당 분류규정 `.9`절 한도 내 자체 면제 | 21 CFR 862–892 각 품목분류 규정 및 `.9`조 | 해당 없음(제출 불필요) | 일반관리(General Controls)만 | Class I 대부분, 일부 Class II([FDA 510(k) 개요](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k)) |
| Traditional 510(k) | §513(i)(1)(A), §510(k) | 21 CFR 807 Subpart E | 90 FDA days(SE/NSE 결정, 95% 목표); Total Time to Decision FY2023 128일→FY2025-27 112일 | Substantial Equivalence 입증자료(성능·벤치 테스트, 필요시 임상자료) | Predicate 존재하는 Class I/II([FDA 510(k) Submission Process](https://www.fda.gov/medical-devices/premarket-notification-510k/510k-submission-process); [MDUFA Performance Goals FY2023–2027](https://www.fda.gov/media/157074/download)) |
| Special 510(k) | §510(k) | 21 CFR 807 Subpart E | 30일 목표 | 설계관리(21 CFR 820.30) 기반 변경 검증·확인자료 | 자사 기존 기기의 설계 변경([The 510(k) Program 가이던스 FDA-2011-D-0652](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/510k-program-evaluating-substantial-equivalence-premarket-notifications-510k)) |
| Abbreviated 510(k) | §510(k) | 21 CFR 807 Subpart E | 90 FDA days(Traditional과 동일) | 가이던스/특수통제/인정 컨센서스 표준 준거성 요약 | Class I/II |
| De Novo | §513(f)(2) (21 U.S.C. 360c(f)(2)) | 21 CFR 860 Subpart F | 150 review days(FY2023 70%, 이후 상향 가능) | 일반·특별통제로 안전성·유효성 입증 가능함을 보이는 임상·비임상 자료 | 신규 기기(predicate 없음), Class I/II 분류 요청([eCFR Part 860](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-860)) |
| PMA | §515 | 21 CFR 814 | Advisory Committee 불필요 시 180 FDA days(90% 목표), 필요 시 320 FDA days | 임상시험 자료 포함 최고 수준 과학적 근거 | Class III([eCFR Part 814](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-814); [govinfo MDUFA 성과보고서](https://www.govinfo.gov/content/pkg/CMR-HE20_4000-00195426/pdf/CMR-HE20_4000-00195426.pdf)) |
| HDE | §520(m) | 21 CFR 814 Subpart H(추정, 본문 명시 확인 불가 — 미확인) | 명확한 MDUFA 목표 미확인 | 유효성 입증 면제, 안전성 및 확률적 이익 입증 자료 | HUD(미국 내 연간 8,000명 이하 발생 질환)([FDA Humanitarian Device Exemption](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/humanitarian-device-exemption)) |
| Breakthrough Devices Program | §515B (21 U.S.C. 360e-3) | 해당 없음(지정 프로그램) | 지정 요청 60일 내 결정(추가정보 요청 시 30일) | 필수 임상데이터 완비 불요, "합리적 기대" 수준 예비자료 | PMA/510(k)/De Novo 대상 전체(자발적 지정)([FDA Breakthrough Devices Program](https://www.fda.gov/medical-devices/how-study-and-market-your-device/breakthrough-devices-program); [가이던스 PDF](https://www.fda.gov/media/162413/download)) |
| Safer Technologies Program (STeP) | 명시적 개별 법조항 미확인 | 해당 없음 | 개별 가이던스 참조(구체적 일수 목표 미확인) | Breakthrough과 유사하나 "덜 심각한 질환/상태" 대상 | PMA/510(k)/De Novo 대상 전체([FDA STeP](https://www.fda.gov/medical-devices/how-study-and-market-your-device/safer-technologies-program-step-medical-devices)) |

**주요 세부사항**
- eSTAR 전자제출은 2023년 10월 1일부터 일부 예외를 제외한 모든 510(k)에 의무화되었다([FDA 510(k) 개요](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k)).
- De Novo는 (1) 510(k) NSE 판정 후 신청, (2) predicate 부재 판단 시 직접 신청의 2가지 경로가 있으며, 승인되면 이후 510(k)의 predicate로 활용 가능하다([FDA De Novo](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/de-novo-classification-request)).
- HDE는 FD&C Act §514, §515의 유효성(effectiveness) 요건을 면제받으며, 소아 질환 등 특정 조건 충족 시 영리판매가 가능하다(§520(m)(6)(A)(i)). 2025년 1월 13일 HDE Modular Review 프로세스 관련 가이던스가 소규모 업데이트되었다([FDA HDE](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/humanitarian-device-exemption)).
- Breakthrough Devices Program은 21st Century Cures Act §3051 신설, FDA Reauthorization Act of 2017 §901, SUPPORT Act §3001로 개정되었으며 최신 최종 가이던스는 2023년 9월 15일 발행되었다(Docket FDA-2017-D-5966)([가이던스 PDF](https://www.fda.gov/media/162413/download)).
- STeP는 2018년 4월 Medical Device Safety Action Plan에서 제안되어 2021년 1월 6일 최종 가이던스가 발행되었고, 2021년 3월 8일부터 Entrance Request 접수가 시작되었다([FDA STeP 웨비나 자료](https://www.fda.gov/media/145541/download)).
- 2026년 7월 현재 510(k)/De Novo/PMA/HDE/Breakthrough/STeP 외의 완전히 새로운 법정 시판전 경로가 추가되었다는 증거는 없다. 대신 PCCP(§515C) 도입, TAP(Total Product Life Cycle Advisory Program) 확대(2026년 7월 1일부로 전체 OHT Breakthrough/STeP 기기로 등록 확대, FY2026 최대 225개·FY2027 최대 325개 목표) 등 틀 내 정책 변화가 있었다([FDA TAP](https://www.fda.gov/medical-devices/how-study-and-market-your-device/total-product-life-cycle-advisory-program-tap); [TAP Pilot Enrollment & Expansion](https://www.fda.gov/medical-devices/total-product-life-cycle-advisory-program-tap/tap-pilot-enrollment-expansion)).
- 현재 유효 체제는 MDUFA V(FY2023–FY2027)이며, MDUFA VI(FY2028~) 재승인 협상이 진행 중(2025년 12월 11일 FDA-Industry 회의)이나 신규 프로그램 도입 여부는 미확인이다([FDA-Industry MDUFA VI Reauthorization Meeting](https://www.fda.gov/media/190452/download)).

**실무 체크리스트**
- [ ] 자사 기기가 predicate 보유 여부(510(k)) 또는 신규 유형(De Novo) 또는 고위험(PMA)인지 우선 판별
- [ ] MDUFA 심사기간을 사업 일정에 반영하고 eSTAR 전자제출 의무 여부 확인
- [ ] Breakthrough/STeP 지정 요건 충족 여부를 조기에 검토(무료 신청, 60일 내 결정)
- [ ] HDE는 자사 적응증이 아닌 한 일반적으로 해당 없음에 유의

---

## 2. 기기 분류 및 Predicate 조사

### 2-1. 분류 절차 개요 (21 CFR Part 860)

21 CFR Part 860(Medical Device Classification Procedures)은 다음 8개 Subpart로 구성된다([eCFR Part 860](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-860)):

| Subpart | 제목 |
|---|---|
| A | General Provisions |
| B | Procedures for Classification of Devices |
| C | Administrative Procedures for Reclassification |
| D | Special Controls |
| E | Procedures for Exemptions From Premarket Notification Requirements |
| F | De Novo Classification Process |
| G | Procedures for Certain Actions Under Section 513(f)(2) |
| H | Procedures for Requests for Information and Evaluations of Class III Devices Under Section 513(f)(1) |

대부분의 기기는 21 CFR Parts 862–892에서 매칭되는 설명을 찾아 분류되며, FDA는 약 1,700개 이상의 고유 기기유형을 16개 의료전문분야 패널로 조직화한다([FDA Device Classification Panels](https://www.fda.gov/medical-devices/classify-your-medical-device/device-classification-panels)). 위험등급은 3단계: **Class I**(일반통제, 저위험, 약 780개 유형), **Class II**(일반+특수통제, 중위험, 약 800개 유형), **Class III**(일반통제+PMA, 고위험, 약 120개 유형)이다([FDA Device Classification Overview](https://www.fda.gov/files/drugs/published/Device-Classification-Overview.pdf)).

영상진단 소프트웨어 등 SaMD는 대부분 **Radiology 패널(21 CFR Part 892)**에 해당한다.

### 2-2. 조사용 데이터베이스

| 데이터베이스 | 용도 | URL |
|---|---|---|
| Product Classification Database | 기기명·제품코드·등급·심사부서·제출유형 조회(매주 갱신) | [accessdata.fda.gov](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm) |
| openFDA Product Classification | 다운로드용 원자료(매월 갱신, 1976년~현재) | [open.fda.gov](https://open.fda.gov/data/product-classification/) |
| 510(k) 승인(Clearance) 검색 | Predicate 탐색 | [accessdata.fda.gov cfPMN](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm) |
| PMA 승인(Approval) 검색 | Predicate/PMA 이력 조회 | `www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMA/pma.cfm`([FDA 발표자료](https://www.fda.gov/media/131272/download)) |
| De Novo 데이터베이스 | De Novo 이력 조회 | `www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/denovo.cfm`([FDA 발표자료](https://www.fda.gov/media/131272/download)) |

### 2-3. 513(g) Request for Information

제품코드를 찾지 못하거나 분류가 불명확한 경우 **FD&C Act §513(g)** 신청을 활용할 수 있다([FDA 513(g) 가이던스, FDA-2010-D-0153, 최근 개정 2024-08-23](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/fda-and-industry-procedures-section-513g-requests-information-under-federal-food-drug-and-cosmetic)). 공식 신청 외에 Device Determination Team(`DeviceDetermination@fda.hhs.gov`)에 이메일로 문의하는 비공식 경로도 있다([FDA 513(g) 자료](https://www.fda.gov/media/133229/download)). 공식 신청은 60일 심사 주기이며, FY2026 수수료는 표준 $7,820 / 소기업 $3,910이다([MDUFA Fees](https://www.fda.gov/industry/fda-user-fee-programs/medical-device-user-fee-amendments-mdufa-fees)).

### 2-4. SaMD/영상분석 소프트웨어 관련 규정 및 제품코드 (21 CFR 892 Subpart C)

| CFR 조항 | 기기명(영문) | 등급 | 대표 Product Code | 비고 |
|---|---|---|---|---|
| 21 CFR 892.2050 | Medical image management and processing system | Class II | QIH, LLZ, NFJ, OEB, OMJ, NWE 등 | 의료영상 라우팅·처리·디스플레이·저장·검색·관리 기기. 최근 개정 2024-05-29([eCFR 892.2050](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-C/section-892.2050)) |
| 21 CFR 892.2060 | Radiological computer-assisted diagnostic software for lesions suspicious of cancer | Class II(특수통제) | POK | 암 의심 병변 특성 규정 보조 소프트웨어. 특수통제: 알고리즘 상세기술, 사전지정 성능평가 프로토콜, reader-performance 테스트 등. 최종개정 85 FR 3542(2020-01-22)([govinfo PDF](https://www.govinfo.gov/content/pkg/CFR-2022-title21-vol8/pdf/CFR-2022-title21-vol8-sec892-2060.pdf)) |
| 21 CFR 892.2070 | Medical image analyzer (CADe 포함) | Class II | MYN | 이상소견 식별·표시·강조 처방기기. 세부 특수통제 전체 원문은 부분 미확인([govinfo PDF](https://www.govinfo.gov/content/pkg/CFR-2022-title21-vol8/pdf/CFR-2022-title21-vol8-sec892-2060.pdf)) |
| 21 CFR 892.2080 | Radiological computer-aided triage and notification software | Class II(510(k) 면제, `.9`한도 내) | QAS(Triage/Notification), QFM(Prioritization) | 두개내출혈·대혈관폐색 등 시간민감성 소견 식별·통지 소프트웨어. 최근 개정 2024-04-01([eCFR 892.2080](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-C/section-892.2080)) |
| 21 CFR 892.2090 | Radiological computer-assisted detection and diagnosis software | Class II(특수통제) | QDQ(암 의심 병변), QBS(골절) | 2025년 6월 13일 최종규칙으로 신설(Federal Register 2025-10789), 분류 적용일 2018-05-24로 소급, 최근 개정 2024-08-06([eCFR 892.2090](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-C/section-892.2090); [Federal Register 최종규칙](https://www.federalregister.gov/documents/2025/06/13/2025-10789/medical-devices-radiology-devices-classification-of-the-radiological-computer-assisted-detection-and)) |

CFR-제품코드 매핑은 accessdata.fda.gov Product Classification Database 직접조회 결과를 기준으로 하였다([QAS 조회결과](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?start_search=1&productcode=QAS)). 일부 3차 자료(법무법인·컨설팅)는 QDQ를 892.2060 계열로 표기하는 등 혼선이 있으므로 1차 DB 조회를 권장한다.

**2024–2025 재분류 동향**: 유방촬영술 유방암, 초음파 유방병변, 방사선촬영 폐결절·치아우식 탐지용 Medical Image Analyzer(MYN, CADe) 제품 8건이 Class III에서 Class II(특수통제)로 재분류되었다(2차 출처, 참고용)([AuntMinnie 보도](https://www.auntminnie.com/imaging-informatics/artificial-intelligence/article/15750598/radiology-drives-july-fda-aienabled-medical-device-update)).

**실무 체크리스트**
- [ ] Product Classification Database에서 유사 기기의 제품코드·등급·심사부서를 먼저 확인
- [ ] 510(k) Clearance/De Novo/PMA 데이터베이스에서 후보 predicate 3~5건 이상 비교 검토
- [ ] 제품코드가 불명확하면 513(g) 공식 신청 또는 비공식 Device Determination 문의를 조기에 진행
- [ ] 영상분석 AI 소프트웨어는 892.2050/2060/2070/2080/2090 중 기능(관리·진단보조·트리아지·탐지)에 따라 해당 조항 정밀 확인

---

## 3. AI/ML SaMD 특화 가이던스

### 3-1. Predetermined Change Control Plan (PCCP)

- **법적 근거**: FD&C Act **§515C** (21 U.S.C. § 360e–4) — 2022년 12월 29일 제정된 Food and Drug Omnibus Reform Act(FDORA) Section 3308이 신설. PMA(§515) 또는 510(k)(§510) 대상 기기에 대해 FDA가 PCCP를 명시적으로 승인/허가할 수 있는 법적 권한을 부여하며, 소프트웨어/AI에 한정되지 않고 모든 기기유형에 적용된다([Federal Register, 2024-03-15 최종규칙](https://www.govinfo.gov/content/pkg/FR-2024-03-15/pdf/2024-05473.pdf); [FDA CDRH 웨비나 대본](https://www.fda.gov/media/187905/download)).
- **AI 특화 최종 가이던스**: *Marketing Submission Recommendations for a Predetermined Change Control Plan for Artificial Intelligence-Enabled Device Software Functions* — 최초 발행 2024년 12월 4일, **2025년 8월 18일 재발행(현재 유효본)**, Docket FDA-2022-D-2628([PDF](https://www.fda.gov/media/166704/download); [Federal Register 공지](https://www.federalregister.gov/documents/2024/12/04/2024-28361/marketing-submission-recommendations-for-a-predetermined-change-control-plan-for-artificial)). 적용대상: 510(k)(Traditional/Abbreviated), PMA 서플리먼트, De Novo. 연혁: 2023년 4월 초안 → 2024년 12월 최종본 → 2025년 8월 재발행.
- **범용(비AI 한정) 초안 가이던스**: *Predetermined Change Control Plans for Medical Devices* — 2024년 8월 21일 초안 발행(FDA-2024-D-2338), 2026년 7월 현재도 **초안(draft) 상태**([FDA 초안 페이지](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/predetermined-change-control-plans-medical-devices)).
- **국제 공동 문서**: FDA·Health Canada·MHRA 공동 *Predetermined Change Control Plans for Machine Learning-Enabled Medical Devices: Guiding Principles* — 5대 원칙: ① Focused and Bounded, ② Risk-based, ③ Evidence-Based, ④ Transparent, ⑤ Total Product Lifecycle Perspective. 2023년 10월 발행, 최신 페이지 업데이트 2025년 8월 18일([FDA PCCP Guiding Principles](https://www.fda.gov/medical-devices/software-medical-device-samd/predetermined-change-control-plans-machine-learning-enabled-medical-devices-guiding-principles)).

### 3-2. Good Machine Learning Practice (GMLP) — 10대 가이딩 원칙

FDA·Health Canada·MHRA 공동 발행(2021년 10월), 구속력 없는 가이딩 원칙([FDA GMLP](https://www.fda.gov/medical-devices/software-medical-device-samd/good-machine-learning-practice-medical-device-development-guiding-principles); [PDF](https://www.fda.gov/media/153486/download)):
1. 제품 총수명주기(TPLC) 전반 다학제적 전문성 활용
2. 우수 소프트웨어공학·보안 관행 구현
3. 임상시험 참가자·데이터셋의 대상 인구 대표성 확보
4. 훈련·테스트 데이터셋 독립성 유지
5. 최선의 방법에 기반한 참조 데이터셋 선정
6. 가용 데이터에 맞춘 모델 설계 및 의도된 사용 목적 반영
7. 인간-AI 팀 성능에 초점
8. 임상적으로 유의미한 조건에서 기기 성능 입증(테스트)
9. 사용자에게 명확하고 필수적인 정보 제공
10. 배포된 모델의 성능 모니터링 및 재훈련 리스크 관리

### 3-3. 투명성(Transparency) 가이딩 원칙

*Transparency for Machine Learning-Enabled Medical Devices: Guiding Principles* — FDA·Health Canada·MHRA 공동, 2024년 6월 13일 발행([FDA 원문](https://www.fda.gov/medical-devices/software-medical-device-samd/transparency-machine-learning-enabled-medical-devices-guiding-principles); [CDRH 보도자료](https://www.fda.gov/medical-devices/medical-devices-news-and-events/cdrh-issues-guiding-principles-transparency-machine-learning-enabled-medical-devices)). GMLP 원칙 7·9를 바탕으로 누가·왜·무엇을·어디에·언제·어떻게의 6가지 관점에서 투명성 확보 방안을 제시한다.

### 3-4. Clinical Decision Support (CDS) Software 및 §520(o)

- **최신 최종 가이던스**: *Clinical Decision Support Software* — Docket FDA-2017-D-6569. 연혁: 2017년 12월 초안 → 2019년 9월 개정초안 → 2022년 9월 28일 최초 최종본 → **2026년 1월 6일 개정 최종본** → **2026년 1월 29일 재발행(현재 유효본, 2026-01-06판을 대체)**([PDF](https://www.fda.gov/media/109618/download)). 2026년 개정으로 단일한 임상적으로 적절한 권고안만 제시해도 조건 충족 시 집행재량(enforcement discretion) 적용이 가능하도록 완화되었으나, 소비자 대상 AI 서비스는 여전히 규제 대상이다(2차 분석: [Covington & Burling](https://www.cov.com/news-and-insights/insights/2026/01/5-key-takeaways-from-fdas-revised-clinical-decision-support-cds-software-guidance)).
- **법적 근거(Non-Device CDS 제외 기준)**: FD&C Act **§520(o)(1)(E)** — 2016년 12월 13일 21st Century Cures Act Section 3060(a)가 신설(21 U.S.C. §360j(o)). 비의료기기 CDS로 인정되는 4대 요건(모두 충족 시): ① 의료영상·IVD 신호·신호획득시스템 패턴을 분석하지 않을 것, ② 환자/의료정보 표시·분석·출력 목적일 것, ③ 질병 예방·진단·치료 권고를 HCP에게 지원하는 목적일 것, ④ HCP가 권고 근거를 독립 검토 가능하여 해당 권고에 주로 의존하지 않도록 할 것([FDA CDS FAQ](https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs); [CDS 최종 가이던스](https://www.fda.gov/media/109618/download)).
- 21st Century Cures Act(2016-12-13) Section 3060은 5개 범주 소프트웨어 기능을 의료기기 정의에서 제외한다([FDLI 분석](https://www.fdli.org/2017/04/21st-century-cures-act-provides-clarity-fdas-regulation-software/); [Federal Register 2017-12-08](https://www.govinfo.gov/content/pkg/FR-2017-12-08/pdf/2017-26469.pdf)).

### 3-5. IMDRF 국제 프레임워크

| 문서 | 코드 | 발행일 | 핵심 내용 | URL |
|---|---|---|---|---|
| Software as a Medical Device: Possible Framework for Risk Categorization | IMDRF/SaMD WG/N12FINAL:2014 | 2014-09-18 | 정보 중요도(Inform→Drive→Diagnose/Treat)×심각도(Non-serious→Serious→Critical) 교차 4단계(Category I~IV) 위험분류 | [imdrf.org](https://www.imdrf.org/documents/software-medical-device-possible-framework-risk-categorization-and-corresponding-considerations) |
| Characterization Considerations for Medical Device Software and Software-Specific Risk (N12 보완문서) | IMDRF/SaMD WG/N81 FINAL:2025 | 2025-01-29 | N12를 대체하지 않고 보완 | [imdrf.org](https://www.imdrf.org/documents/characterization-considerations-medical-device-software-and-software-specific-risk) |
| SaMD: Clinical Evaluation | IMDRF/SaMD WG/N41FINAL:2017 | 2017-09-21 | 출력값-대상 임상상태 간 유효한 임상적 연관성 확립을 위한 임상평가 국제조화 원칙 | [PDF](https://www.imdrf.org/sites/default/files/docs/imdrf/final/technical/imdrf-tech-170921-samd-n41-clinical-evaluation_1.pdf) |

IMDRF 문서는 국제 규제기관 조화 문서로 FDA 규정 자체는 아니며, FDA가 이를 별도 가이던스로 공식 채택했는지는 **미확인**이다.

### 3-6. AI-Enabled Device Software Functions Lifecycle Management (초안)

*Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations* — Docket FDA-2024-D-4488, **2025년 1월 7일 발행, 2026년 7월 현재도 초안(draft) 상태**([PDF](https://www.fda.gov/media/184856/download); [검색 페이지](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/artificial-intelligence-enabled-device-software-functions-lifecycle-management-and-marketing)). 코멘트는 21 CFR 10.115(g)(5)에 따라 상시 접수 가능.

### 3-7. AI-Enabled Medical Device List 및 최근 정책 동향

- FDA는 시판 승인된 AI 탑재 기기를 식별하는 **AI-Enabled Medical Device List**를 운영하며, "포괄적 목록이 아님"을 명시한다. FDA 페이지 확인일 2026년 6월 16일, 2026년 3월 30일자 결정 건(K254207 등)까지 반영([FDA AI-Enabled Medical Devices](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices)). 3차 분석 기관(MedTech Dive, IntuitionLabs)은 1,400~1,524건 누적을 보도하나 FDA 1차 출처는 총계를 공표하지 않아 **미확인**이다.
- FDA Digital Health Advisory Committee(DHAC): 창립 회의 2024년 11월 20~21일, 2025년 회의는 2025년 11월 6일 "생성형 AI 기반 디지털 정신건강 의료기기" 주제로 개최(Docket FDA-2025-N-2338)([회의 공고](https://www.fda.gov/advisory-committees/advisory-committee-calendar/november-6-2025-digital-health-advisory-committee-meeting-announcement-11062025); [요약](https://www.fda.gov/media/189618/download)). 2026년 신규 회의 일정은 **미확인**.
- FDA는 향후 파운데이션 모델/LLM 기반 기능을 별도 식별·태깅하는 방법을 모색 중이다([FDA AI-Enabled Medical Devices](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices)).

**실무 체크리스트**
- [ ] AI/ML 기기 반복학습·업데이트 계획이 있다면 PCCP 포함 제출을 초기 설계 단계부터 검토
- [ ] GMLP 10대 원칙을 개발 문서화(데이터거버넌스, 모델설계, 성능모니터링)에 반영
- [ ] 투명성 가이딩 원칙에 따라 라벨링·사용자설명서에 6하원칙 기반 정보 포함
- [ ] CDS 성격 기능이 있다면 §520(o)(1)(E) 4대 요건 충족 여부로 비의료기기 해당성 사전 검토
- [ ] IMDRF N12 위험분류(Category I~IV)를 자사 SaMD 리스크 매핑에 활용

---

## 4. 소프트웨어 문서화 및 사이버보안

### 4-1. 소프트웨어 문서화

| 가이던스(영문) | 상태 | 발행일 | Docket | 핵심 내용 | URL |
|---|---|---|---|---|---|
| Content of Premarket Submissions for Device Software Functions | Final | 2023-06-14 | FDA-2021-D-0775 | 위험도에 따라 **Basic/Enhanced Documentation** 결정. Enhanced는 소프트웨어 고장·결함이 사망/중대부상의 개연적 위험을 초래하는 위해상황(사이버보안 취약성 포함) 시 요구. 2005년판 대체 | [PDF](https://www.fda.gov/media/153781/download) |
| Off-The-Shelf (OTS) Software Use in Medical Devices | Final | 2023-08-11(원발행 1999-09-09, 2019년판 대체) | FDA-2019-D-3598 | OTS 소프트웨어(OS, 프린터/디스플레이 라이브러리 등) 사용 시 시판전 신고서 문서 요건. 라벨링에 검증된 최소 하드웨어 플랫폼 명시 및 경고문 권고 | [PDF](https://www.fda.gov/media/71794/download) |

### 4-2. 사이버보안

| 버전 | 제목 | 발행일 | 상태 |
|---|---|---|---|
| 최신 | Cybersecurity in Medical Devices: **Quality Management System** Considerations and Content of Premarket Submissions | **2026-02-03** | Final(Level 2, QMSR 정합) |
| 이전 | Cybersecurity in Medical Devices: **Quality System** Considerations... | 2025-06-27 | Final(Level 1, Section VII 신설·524B 반영) |
| 이전 | 동일 제목 | 2023-09-27 | Final(2014년판 대체) |
| 초안 이력 | 동일 제목 | 2024-03 | Level 1 Draft로 재발행 |

- **문서번호**: GUI00001825. **URL(최신판)**: [https://www.fda.gov/media/119933/download](https://www.fda.gov/media/119933/download); 안내페이지: [FDA Cybersecinformation](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity).
- **핵심 내용(2026-02-03판)**: Section VII "Cyber Devices"에 FD&C Act §524B 관련 문서화 권고 포함. Security Objectives: Authenticity(무결성 포함), Authorization, Availability, Confidentiality, Secure/timely updatability. **SBOM 요구**(Section V.A.4): cyber device는 SBOM 필수, 기계판독 가능 형식·NTIA baseline attributes 준수·지원종료일 포함 권고. Section VI.A는 SBOM이 라벨링 포함 또는 사용자에게 지속 제공되어야 함을 규정. Section VII.C.3은 §524B(b)(3)에 따라 상용·오픈소스·기성품 소프트웨어 구성요소 포함 SBOM 제공 의무를 규정.
- **FD&C Act §524B(Ensuring Cybersecurity of Devices)**: 2023년 3월 29일부터 cyber device의 시판전 신고서에 적용. §524B(a)는 510(k)/PMA/PDP/De Novo/HDE 신고 시 cyber device 정의 해당 시 §524B(b) 요건 충족정보 제출 의무를 규정. §524B(c) cyber device 정의: (1) 검증·설치·승인된 소프트웨어 포함, (2) 인터넷 연결 가능, (3) 사이버보안 위협에 취약할 수 있는 기술적 특성 보유. 법조문 자체의 ecfr.gov 직접 링크는 **미확인**(가이던스 원문 인용으로 확인)([사이버보안 가이던스 2026-02-03판](https://www.fda.gov/media/119933/download)).
- **Postmarket Management of Cybersecurity in Medical Devices**(2016-12-27, Final): 시판후 사이버보안 관리 가이던스. 직접 PDF URL은 **미확인**(안내페이지에서 존재만 확인)([안내페이지](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity)).

**실무 체크리스트**
- [ ] 자사 기기의 위험도를 평가해 Basic/Enhanced Documentation Level 결정
- [ ] OTS 소프트웨어 구성요소 목록·검증 하드웨어 플랫폼을 문서화
- [ ] cyber device 해당 여부(인터넷 연결·소프트웨어 포함·사이버보안 취약성) 판단 후 SBOM 준비(NTIA baseline attributes 준수)
- [ ] 2026-02-03 최신 사이버보안 가이던스의 QMSR 정합 요건을 품질시스템에 반영

---

## 5. 품질시스템(QMSR) 및 임상/데이터 요건

### 5-1. QMSR (Quality Management System Regulation)

- **정식 제목**: *Medical Devices; Quality System Regulation Amendments* — Federal Register Citation **89 FR 7496**, 발행일 **2024년 2월 2일**, Docket FDA-2021-N-0507 / RIN 0910-AH99([Federal Register 원문](https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments)).
- **시행일**: **2026년 2월 2일**(현재 시행 중). fda.gov는 QSIT(Quality System Inspection Technique) 대신 신규 Compliance Program **7382.850**(Inspection of Medical Device Manufacturers)을 적용 중이며, 기존 7382.845/7383.001은 더 이상 사용하지 않는다([FDA QMSR 안내 페이지](https://www.fda.gov/medical-devices/postmarket-requirements-devices/quality-management-system-regulation-qmsr)).
- **21 CFR Part 820 개정 요지**: 명칭을 "Quality System (QS) Regulation"에서 "Quality Management System Regulation (QMSR)"로 변경. **ISO 13485:2016(E)**(Third Edition, 2016-03-01) 및 **ISO 9000:2015 Clause 3**를 **참조로 편입(Incorporation by Reference, IBR)**. 조문 구성 간소화: §820.1(Scope), §820.3(Definitions), §820.7(IBR), §820.10(QMS 요건), §820.35(기록관리), §820.45(라벨링·포장관리) 중심. 2024년 10월 15일 정정고시(89 FR, 2024-23701)로 §820.3 "batch or lot" 정의 누락을 정정(2차 출처 justia.com으로 확인, 1차 federalregister.gov/govinfo.gov 직접 fetch는 **미실시**).
- **ISO 13485 통합 방식**: 원칙적으로 수정 없이 수용하되, FDA 고유 규제체계와 불일치 방지를 위해 일부 조항을 대체·추가(전면 동일채택 아님).
- **검사 변화**: 리스크 기반 전체 시스템 평가로 전환, "correction"을 "corrective action"과 별도 용어로 추가(ISO 13485 정합).

### 5-2. 임상시험/데이터 관련 CFR

| 조문 | 정식 제목 | eCFR published_date | URL |
|---|---|---|---|
| 21 CFR Part 812 | Investigational Device Exemptions | 2026-02-02(QMSR 반영) | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-812) |
| 21 CFR Part 50 | Protection of Human Subjects | 2024-01-22 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-50) |
| 21 CFR Part 56 | Institutional Review Boards | 2026-07-27 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-56) |

### 5-3. Real-World Evidence (RWE) 가이던스

*Use of Real-World Evidence to Support Regulatory Decision-Making for Medical Devices* — Docket FDA-2023-D-4395, **최종 2025년 12월 18일 발행**(2017-08-31 최초판 대체, 2023-12-19 초안 경유)([PDF](https://www.fda.gov/media/190201/download)). 2025년 개정 핵심: 개별 환자수준 식별 데이터 제출을 항상 요구하지 않고 익명화·집계 데이터 접근 모델도 정당화 시 인정. 적용대상: IDE, PMA, 510(k), HDE, De Novo, CLIA Waiver. 신규 권고사항은 2026년 2월 17일부터 반영 예상(60일 전환기간)([2017년 원판 Federal Register](https://www.federalregister.gov/documents/2017/08/31/2017-18469/use-of-real-world-evidence-to-support-regulatory-decision-making-for-medical-devices-guidance-for)).

IMDRF SaMD Clinical Evaluation(N41, 2017-09-21)도 임상성능평가 참고자료로 활용되나, FDA의 공식 채택 여부는 **미확인**이다([IMDRF PDF](https://www.imdrf.org/sites/default/files/docs/imdrf/final/technical/imdrf-tech-170921-samd-n41-clinical-evaluation_1.pdf)).

**실무 체크리스트**
- [ ] 2026-02-02 QMSR 시행에 맞춰 품질시스템을 ISO 13485:2016 기준으로 전환·정합화
- [ ] 신규 Compliance Program 7382.850 기준의 사찰 대비 리스크 기반 QMS 평가 체계 구축
- [ ] IDE 임상시험 계획 시 21 CFR Part 812/50/56 요건 동시 검토
- [ ] AI 모델 검증에 RWE 활용 시 2025-12-18 개정 가이던스의 데이터 접근모델 완화 요건 확인

---

## 6. 라벨링·UDI·시판후 의무

### 6-1. 라벨링 및 UDI

| 조문 | 정식 제목 | eCFR published_date | URL |
|---|---|---|---|
| 21 CFR Part 801 | Labeling | 2026-02-02 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-801) |
| 21 CFR Part 830 | Unique Device Identification | 2023-07-14 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-830) |

- **UDI 최종규칙**: *Unique Device Identification System* — Federal Register 최종규칙 발행일 2013년 9월 24일([FDA UDI 리소스 페이지](https://www.fda.gov/medical-devices/unique-device-identification-system-udi-system/udi-rule-guidances-training-and-other-resources)).
- **관련 최종 가이던스**: *UDI: Direct Marking of Devices*(Final, 2017-11-17); *UDI: Convenience Kits*(2019-04-26, final/draft 구분 페이지상 불명확); *UDI: Policy Regarding Compliance Dates for Class I and Unclassified Devices...*(Final, 2022-07-22).
- **소프트웨어 라벨링**: 독립적인 "소프트웨어 전용 라벨링 가이던스"는 **미확인**. 대신 OTS Software 가이던스(4-1)에 검증된 최소 하드웨어 플랫폼 명시 권고가 있고, 사이버보안 가이던스(4-2) Section VI.A에 SBOM의 라벨링 포함/지속 제공 의무가 규정되어 있다([OTS PDF](https://www.fda.gov/media/71794/download); [Cybersecurity PDF](https://www.fda.gov/media/119933/download)).

### 6-2. 시판후 의무

| 조문 | 정식 제목 | 한국어 | eCFR published_date | URL |
|---|---|---|---|---|
| 21 CFR Part 803 | Medical Device Reporting | 의료기기 이상사례 보고(MDR) | 2026-02-02 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-803) |
| 21 CFR Part 806 | Reports of Corrections and Removals | 시정·회수 보고 | 2019-01-04 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-806) |
| 21 CFR Part 822 | Postmarket Surveillance | 시판후 감시(FD&C Act §522 시행규정 — 대응관계는 통상적으로 알려진 정보) | 2020-02-04 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-822) |
| 21 CFR Part 7 | Enforcement Policy(리콜 등) | 집행정책 | 2023-07-14 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-7) |
| 21 CFR Part 11 | Electronic Records; Electronic Signatures | 전자기록·전자서명 | 2023-02-03 | [ecfr.gov](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11) |

- QMSR 신규 검사 매뉴얼(CP 7382.850)은 21 CFR 803, 806, 821(Tracking), 801, 830을 ISO 13485 미포함 영역으로 별도 검토한다고 명시된다([emergobyul.com 분석](https://www.emergobyul.com/news/qmsr-what-us-fdas-new-inspection-manual-really-means-device-manufacturers)).
- Part 11(전자기록·전자서명)은 QMSR/QSR 하의 전자 품질기록 관리(eQMS)에 통상 적용되는 것으로 업계에서 이해되나, SaMD 소프트웨어 자체에 대한 구체적 scope 해당성(§11.1 상세)은 **미확인**이다.

**실무 체크리스트**
- [ ] UDI 부착·GUDID 등록 일정을 자사 기기 등급별 컴플라이언스 기한에 맞춰 계획
- [ ] SBOM을 라벨링 또는 사용자 제공 문서에 반영(사이버보안 가이던스 Section VI.A)
- [ ] MDR(Part 803)·시정회수(Part 806) 보고 프로세스를 시판후 QMS에 내재화
- [ ] eQMS 등 전자기록 시스템의 Part 11 정합성 별도 법률 검토 권장

---

## 7. 제출 실무: eSTAR, 수수료(FY2026), 등록·리스팅, U.S. Agent, Q-Sub, RTA

### 7-1. 전자제출(eSTAR/CDRH Portal)

- **eSTAR**: 510(k)(Traditional/Abbreviated/Special) 및 De Novo(CDRH/CBER 대상)는 면제 대상이 아니면 eSTAR 전자제출이 **의무**(결합제품, 510(k)/CLIA Waiver 이중신청 포함). PMA는 현재 **자발적(voluntary)**([eSTAR Program](https://www.fda.gov/medical-devices/how-study-and-market-your-device/estar-program)).
  - 510(k) 의무화 시행일: **2023년 10월 1일**([가이던스](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/electronic-submission-template-medical-device-510k-submissions), Docket FDA-2021-D-0872).
  - De Novo 의무화 시행일: **2025년 10월 1일**([CDRH Portal 페이지](https://www.fda.gov/medical-devices/industry-medical-devices/send-and-track-medical-device-premarket-submissions-online-cdrh-portal)).
  - 현재 템플릿: nIVD/IVD eSTAR v6.2(2026년 8월 3일 폐지 예정) → **v7.0**(최신 권장); PreSTAR v2.2(폐지 예정) → **v3.0**(최신). OMB 관리번호: nIVD/IVD eSTAR 0910-0120/0910-0844/0910-0231, PreSTAR 0910-0756/0910-0078/0910-0511.
  - 2026년 5월 29일 발행 Human Factors Content Guidance가 eSTAR에 반영되어 2026년 8월 1일부터 발효.
- **CDRH Portal(Customer Collaboration Portal)**: 510(k)/De Novo는 반드시 CDRH Portal로 제출(파일 크기 제한: 단일 4GB, PDF 1GB 초과 시 우편). CBER 대상은 별도 ESG 제출. 2024년 11월 1일부터 Small Business Request도 전자제출 의무([CDRH Portal](https://www.fda.gov/medical-devices/industry-medical-devices/send-and-track-medical-device-premarket-submissions-online-cdrh-portal)).
- **eSubmitter**: CDRH 프리마켓 제출용은 CDRH Portal로 대체되었으며, ISO 13485/방사선 보고서/eMDR(3500A) 등 특정 용도에 한정 사용([FDA eSubmitter](https://www.fda.gov/industry/fda-esubmitter)).

### 7-2. 수수료 (FY2026: 2025-10-01 ~ 2026-09-30)

| 신청 유형 | 표준 수수료 | 소기업 수수료 |
|---|---:|---:|
| 510(k) | $26,067 | $6,517 |
| 513(g) | $7,820 | $3,910 |
| PMA/PDP/PMR/BLA | $579,272 | $144,818 |
| De Novo Classification Request | $173,782 | $43,446 |
| Panel-track Supplement | $463,418 | $115,855 |
| 180-Day Supplement | $86,891 | $21,723 |
| Real-Time Supplement | $40,549 | $10,137 |
| 30-Day Notice | $9,268 | $4,634 |
| Class III 연간보고 수수료 | $20,275 | $5,069 |
| 연간 시설등록 수수료 | $11,423 | 해당 없음(소기업 감면 대상 아님) |

출처: [MDUFA Fees](https://www.fda.gov/industry/fda-user-fee-programs/medical-device-user-fee-amendments-mdufa-fees). FDA 인증 제3자 심사기관 경유 510(k)는 수수료 없음. MDUFA V는 2022-10-01~2027-09-30 적용, MDUFA VI는 2028년 재승인 예정.

**Small Business Determination(SBD)**: 매출 $100백만 이하 시 표준 수수료의 약 25%로 감면(가이던스 Docket FDA-2018-D-1873, 2025-07-30 최종판). $30백만 이하는 최초 PMA/PDP/PMR/BLA 수수료 전액 면제(1회). **한국 기업은 Form 3602N Section III(국가 세무당국 인증) 첨부한 "MDUFA Foreign SBR" 제출 필요**하며, 한국처럼 세무당국이 인증서를 발급하지 않으면 재무제표 등 대체자료로 사안별 심사받는다. FY2026 SBR 신청 마감: **2026년 8월 1일 오후 4시(ET)**; SBD는 매 회계연도 재신청 필요; 신청 자체는 무료([SBD Program](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/reduced-or-waived-medical-device-user-fees-small-business-determination-sbd-program); [가이던스](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/medical-device-user-fee-small-business-qualification-and-determination)).

### 7-3. 등록·리스팅 및 U.S. Agent

**법적 근거**: [21 CFR Part 807 Subpart B](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-807/subpart-B) — §807.20(General)~§807.47(Duration)까지 구성. §807.37(외국시설 요건), §807.39(최초수입자 요건) 조항 번호·제목은 확인되나 전체 조문 원문은 **미확인**.

- **FURLS**(FDA Unified Registration and Listing System): 등록·리스팅 전자 제출 시스템([Device Registration and Listing](https://www.fda.gov/medical-devices/how-study-and-market-your-device/device-registration-and-listing)). "DRLM"이 FURLS 내 공식 하위시스템명으로 독자 사용되는지는 **미확인**.
- **연간 등록 수수료**: FY2026 **$11,423**(초기 등록도 면제 대상 아님).
- **U.S. Agent**(21 CFR 807.37 근거): 미국에 수입되는 기기를 제조하는 모든 해외 시설은 지정 필수. FURLS로 전자 제출. 시설당 1인만 지정(Official Correspondent 겸임 가능). 요건: 미국 내 거주/사업장, PO Box 불가, 정규 근무시간 응답 가능. 확인 절차: 자동 이메일 인증 후 10영업일 내 미응답/거부 시 재지정 필요. **책임 범위**: FDA-해외시설 간 communication 보조, 문의 응답, 사찰 일정 조율 보조. **책임 아님**: MDR(803), 510(k) 제출(807 Subpart E)([U.S. Agents](https://www.fda.gov/medical-devices/device-registration-and-listing/us-agents)).
- **Initial Importer**(21 CFR 807.3(g)): 해외제조사 기기를 최종사용자에게 유통 촉진하는 자로 포장·라벨 미변경자. 의무: 시설등록, MDR(803), 시정·회수(806), 해당 시 기기추적(821)([Importing Medical Devices](https://www.fda.gov/medical-devices/importing-and-exporting-medical-devices/importing-medical-devices-and-radiation-emitting-electronic-products-us)).

### 7-4. Q-Submission Program

*Requests for Feedback and Meetings for Medical Device Submissions: The Q-Submission Program* — **2025년 5월 29일 발행**(초안 2024-03-15, 2023-06-02판 및 1998년 PMA Day-100 가이던스 대체), Docket FDA-2018-D-1774([PDF](https://www.fda.gov/media/114034/download)). 유형: Pre-Submission(Pre-Sub), Submission Issue Request, Informational Meeting, Study Risk Determination, PMA Day 100 Meeting, Accessory Classification Request 등.

### 7-5. Refuse to Accept (RTA) / Acceptance Review

| 가이던스 | 발행일 | Docket | 핵심 | URL |
|---|---|---|---|---|
| Refuse to Accept Policy for 510(k)s | 2022-04-21(원발행 1994-05-20, 2019년판 대체) | FDA-2012-D-0523 | 510(k) 실질적 심사를 위한 최소 수리기준, 유형별 Acceptance Checklist | [PDF](https://www.fda.gov/media/83888/download); [Checklists](https://www.fda.gov/medical-devices/premarket-notification-510k/acceptance-checklists-510ks) |
| Acceptance Review for De Novo Classification Requests | 미확인(정확 발행일) | FDA-2017-D-6069 | MDUFA IV 커밋먼트에 따른 De Novo 수리심사 체크리스트. 관련 최종규칙 2021-10-05(21 CFR 860 Subpart D 신설) | [PDF](https://www.fda.gov/media/152657/download) |

**실무 체크리스트**
- [ ] 최신 eSTAR/PreSTAR v7.0/v3.0 템플릿 사용, v6.2/v2.2는 2026년 8월 3일 폐지 대비
- [ ] FY2026 수수료 예산 반영 및 SBD 자격 여부 검토(한국기업은 Foreign SBR 절차 숙지)
- [ ] 미국 내 U.S. Agent 사전 지정 및 FURLS 등록·연간 갱신 일정 관리
- [ ] Pre-Sub(Q-Sub)을 통해 신청 전 FDA 피드백을 받아 RTA 리스크 최소화
- [ ] Acceptance Checklist 기준으로 제출 전 자체 점검(Traditional/Abbreviated/Special 유형별 상이)

---

## 8. 인정 컨센서스 표준 (Recognized Consensus Standards)

**FDA Recognized Consensus Standards Database**: [accessdata.fda.gov](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/search.cfm)(2025-12-22 갱신 확인). 관련 가이던스: *Appropriate Use of Voluntary Consensus Standards in Premarket Submissions for Medical Devices*(2018년 9월). Federal Register 게재 페이지: [Standards](https://www.fda.gov/medical-devices/standards-and-conformity-assessment-program/federal-register-documents); 관할부서: [Division of Standards and Conformity Assessment](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/division-standards-and-conformity-assessment).

| 표준번호 | 명칭 | 적용 영역 | FDA 인정번호 |
|---|---|---|---|
| IEC 62304 (Edition 1.1, 2015-06 Consolidated) / ANSI AAMI IEC 62304:2006/A1:2016 | 의료기기 소프트웨어 – 소프트웨어 생애주기 프로세스 | Software/Informatics | **13-79**(전면 인정, 등재 2019-01-14)([DB 검색결과](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?start_search=1&productcode=&category=&type=&title=&organization=2&referencenumber=&regulationnumber=&effectivedatefrom=&effectivedateto=&pagenum=50&sortcolumn=pad)) |
| IEC 62366-1 (Edition 1.1, 2020-06) / ANSI AAMI IEC 62366-1:2015+AMD1:2020 | 사용적합성공학 적용 | General I(QS/RM) | **5-129**(전면 인정, 등재 2020-07-06)([DB 상세](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=41235)) |
| ISO 14971 (제3판, 2019-12) / ANSI AAMI ISO 14971:2019 | 의료기기 위험관리 | General I(QS/RM) | **5-125**(전면 인정, 등재 2019-12-23; 구판 2007년 제2판은 2022-12-25까지 병행 인정 후 만료)([DB 상세](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=41349)) |
| ANSI/AAMI SW96:2023 | 의료기기 보안 표준 – 기기제조자를 위한 보안 위험관리 | Software/Informatics | **13-131**(FR Recognition List 061, 등재 2023-10-09; 일부 2차자료는 "44689"로 오기 — 이는 DB 내부 identification_no)([DB 상세](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=44689)) |
| IEC 81001-5-1 (Edition 1.0, 2021-12) | 헬스소프트웨어·헬스IT 시스템 안전·유효성·보안 – 제품생애주기 보안활동 | Software/Informatics | **13-122**(FR Recognition List 059, 등재 2022-12-19)([DB 상세](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=43889)) |
| ISO/IEC 27001 | 정보보안관리시스템(ISMS) | — | **미확인**(DB 내 정식 등재 직접 확인 못함; 사이버보안 가이던스는 IEC 81001-5-1, SW96을 인용하나 27001 인정 여부는 미확인) |
| ANSI/AAMI/ISO 13485:2016 | 품질관리시스템 요구사항 | — | DB상 개별 인정번호는 **미확인**. 단 QMSR 최종규칙이 ISO 13485:2016(E)/ISO 9000:2015(E) Clause 3를 참조로 편입(Incorporate by Reference)([QMSR 최종규칙](https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments); [FDA QMSR 설명자료](https://www.fda.gov/media/190872/download)) |
| AAMI CR515:2025 | 머신러닝 기반 의료기기 특유 사이버보안 고려사항 | Software/Informatics | **13-153**(등재 2025-12-22)([DB 검색결과](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?start_search=1&productcode=&category=&title=medical+device&supportingdocsyn=off&ascapilotyn=off&organization=&regulationnumber=&recognitionnumber=&effectivedatefrom=&effectivedateto=&pagenum=100&sortcolumn=rt)) |
| ISO/IEC/IEEE 29119-1 | 소프트웨어 테스팅 | — | 2026년 2월 FDA 신규 인정 3개 표준 중 하나로 보도(2차 출처, 1차 DB 직접 확인 미완료)([RAPS 기사](https://www.raps.org/resource/fda-recognizes-three-new-international-medical-dev.html)) |

### QMSR-ISO 13485 관계 요약

FDA는 2024년 2월 2일 최종규칙(Federal Register Doc. **2024-01709**)으로 21 CFR 820을 QMSR로 개편, ISO 13485:2016(E) 전문과 ISO 9000:2015(E) Clause 3를 참조로 편입하여 **"인정 표준" 여부와 별개로 규정 자체가 ISO 13485를 사실상 법적 요건화**하였다. 시행일은 2026년 2월 2일이다([Federal Register 최종규칙](https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments); [FDA QMSR 설명 슬라이드](https://www.fda.gov/media/190872/download)).

### ASCA (Accreditation Scheme for Conformity Assessment)

자발적 적합성평가 인정제도([FDA ASCA](https://www.fda.gov/medical-devices/division-standards-and-conformity-assessment/accreditation-scheme-conformity-assessment-asca), 2026-01-28 최종 업데이트). 현재 적용 범위는 **생체적합성**과 **기본안전성·필수성능**(IEC 60601/61010/61326 계열) 시리즈에 한정되며, IEC 62304 등 SaMD/소프트웨어 표준에 대한 언급은 확인되지 않아 순수 SaMD의 ASCA 직접 해당성은 낮다. 다만 하드웨어 결합기기는 해당 하드웨어 요소에 ASCA가 적용될 수 있다. 2025년 9월 18일 일부 인증기관 인증 철회, 2025년 7월 28일 IEC 61326-2-6 Edition 4 추가 인정.

**실무 체크리스트**
- [ ] IEC 62304, ISO 14971, IEC 62366-1을 소프트웨어 개발·위험관리·사용성 문서의 기본 표준으로 채택
- [ ] cyber device는 ANSI/AAMI SW96:2023, IEC 81001-5-1, AAMI CR515:2025(ML 특화) 적용 여부 검토
- [ ] QMSR 대응 시 ISO 13485:2016 인증/정합을 최우선 과제로 설정(FDA 인정표준 등재와 별개로 법적 요건)
- [ ] 순수 소프트웨어 기기는 ASCA 적용 대상이 아님을 인지하고 별도 적합성평가 경로 확인

---

## 9. 전체 원문 링크 마스터 목록

### 9-1. 인허가 경로 및 기기분류 (1·2절 관련)

| 문서명(영문 원제) | 유형 | 발행·개정일 | URL |
|---|---|---|---|
| Premarket Notification 510(k) | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k) |
| 21 CFR Part 807 Subpart E | eCFR | 미확인 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-807/subpart-E) |
| The 510(k) Program: Evaluating Substantial Equivalence in Premarket Notifications (FDA-2011-D-0652) | Final Guidance | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/510k-program-evaluating-substantial-equivalence-premarket-notifications-510k) |
| MDUFA Performance Goals and Procedures, FY2023–2027 | FDA 공식자료 | 미확인 | [링크](https://www.fda.gov/media/157074/download) |
| 510(k) Submission Process | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/premarket-notification-510k/510k-submission-process) |
| FDA and Industry Actions on 510(k) Submissions: Effect on FDA Review Clock and Goals | FDA 자료 | 미확인 | [링크](https://www.fda.gov/media/73507/download) |
| De Novo Classification Request | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/de-novo-classification-request) |
| Premarket Approval (PMA) | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-approval-pma) |
| 21 CFR Part 814 | eCFR | 개정 2024-04-26 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-814) |
| MDUFA 성과 보고서 (govinfo) | 정부 보고서 | 미확인 | [링크](https://www.govinfo.gov/content/pkg/CMR-HE20_4000-00195426/pdf/CMR-HE20_4000-00195426.pdf) |
| Humanitarian Device Exemption | FDA 안내페이지 | 업데이트 2025-01-13 | [링크](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/humanitarian-device-exemption) |
| Breakthrough Devices Program | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/how-study-and-market-your-device/breakthrough-devices-program) |
| Breakthrough Devices Program Guidance (FDA-2017-D-5966) | Final Guidance | 2023-09-15 | [링크](https://www.fda.gov/media/162413/download) |
| Safer Technologies Program (STeP) for Medical Devices | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/how-study-and-market-your-device/safer-technologies-program-step-medical-devices) |
| STeP 웨비나 자료(개요 PDF) | FDA 발표자료 | 미확인 | [링크](https://www.fda.gov/media/145541/download) |
| 21 CFR Part 860 | eCFR | 미확인 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-860) |
| Device Classification Panels | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/classify-your-medical-device/device-classification-panels) |
| Device Classification Overview (PPT/PDF) | FDA 자료 | 미확인 | [링크](https://www.fda.gov/files/drugs/published/Device-Classification-Overview.pdf) |
| Product Classification Database | FDA DB | 매주 갱신 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm) |
| openFDA Product Classification | 오픈데이터 | 매월 갱신 | [링크](https://open.fda.gov/data/product-classification/) |
| 510(k) Premarket Notification 검색(cfPMN) | FDA DB | 미확인 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm) |
| 513(g) 관련 FDA 발표자료(PPT) | FDA 자료 | 미확인 | [링크](https://www.fda.gov/media/131272/download) |
| Procedures for Section 513(g) Requests for Information (FDA-2010-D-0153) | Guidance | 개정 2024-08-23 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/fda-and-industry-procedures-section-513g-requests-information-under-federal-food-drug-and-cosmetic) |
| 513(g) 자료 PDF | FDA 자료 | 미확인 | [링크](https://www.fda.gov/media/133229/download) |
| 21 CFR 892.2050 | eCFR | 개정 2024-05-29 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-C/section-892.2050) |
| 21 CFR 892.2060/892.2070 (2022 Edition) | govinfo PDF | 2022 edition | [링크](https://www.govinfo.gov/content/pkg/CFR-2022-title21-vol8/pdf/CFR-2022-title21-vol8-sec892-2060.pdf) |
| 21 CFR 892.2080 | eCFR | 개정 2024-04-01 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-C/section-892.2080) |
| 21 CFR 892.2090 | eCFR | 개정 2024-08-06 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-C/section-892.2090) |
| Medical Devices; Radiology Devices; Classification of the Radiological Computer-Assisted Detection and Diagnosis Software (Final Rule, 2025-10789) | Federal Register | 2025-06-13 | [링크](https://www.federalregister.gov/documents/2025/06/13/2025-10789/medical-devices-radiology-devices-classification-of-the-radiological-computer-assisted-detection-and) |
| 892.2090 최종규칙 원문(govinfo PDF) | govinfo | 2025-06-13 | [링크](https://www.govinfo.gov/content/pkg/FR-2025-06-13/pdf/2025-10789.pdf) |
| QAS 제품코드 분류조회 | FDA DB | 미확인 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?start_search=1&productcode=QAS) |
| AuntMinnie 보도(재분류 사례, 2차 출처) | 뉴스 | 2025-07-18 | [링크](https://www.auntminnie.com/imaging-informatics/artificial-intelligence/article/15750598/radiology-drives-july-fda-aienabled-medical-device-update) |
| Total Product Life Cycle Advisory Program (TAP) | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/how-study-and-market-your-device/total-product-life-cycle-advisory-program-tap) |
| TAP Pilot Enrollment & Expansion | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/total-product-life-cycle-advisory-program-tap/tap-pilot-enrollment-expansion) |
| FDA-Industry MDUFA VI Reauthorization Meeting 자료 | FDA 자료 | 2025-12-11 회의 | [링크](https://www.fda.gov/media/190452/download) |

### 9-2. AI/ML SaMD 특화 가이던스 (3절 관련)

| 문서명(영문 원제) | 유형 | 발행·개정일 | URL |
|---|---|---|---|
| AI-Enabled Medical Devices (AI-Enabled Medical Device List) | FDA 안내페이지 | 확인일 2026-06-16 | [링크](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices) |
| Marketing Submission Recommendations for a Predetermined Change Control Plan for AI-Enabled Device Software Functions (PCCP, FDA-2022-D-2628) | Final Guidance | 원발행 2024-12-04, 재발행 2025-08-18 | [링크](https://www.fda.gov/media/166704/download) |
| PCCP 가이던스 Federal Register 공지(2024-28361) | Federal Register | 2024-12-04 | [링크](https://www.federalregister.gov/documents/2024/12/04/2024-28361/marketing-submission-recommendations-for-a-predetermined-change-control-plan-for-artificial) |
| Predetermined Change Control Plans for Medical Devices (범용, FDA-2024-D-2338) | Draft Guidance | 2024-08-21 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/predetermined-change-control-plans-medical-devices) |
| Predetermined Change Control Plans for Machine Learning-Enabled Medical Devices: Guiding Principles | Guiding Principles | 2023-10, 업데이트 2025-08-18 | [링크](https://www.fda.gov/medical-devices/software-medical-device-samd/predetermined-change-control-plans-machine-learning-enabled-medical-devices-guiding-principles) |
| Section 515C 관련 Federal Register(2024-05473) | Federal Register 최종규칙 | 2024-03-15 | [링크](https://www.govinfo.gov/content/pkg/FR-2024-03-15/pdf/2024-05473.pdf) |
| FDA CDRH 웨비나 대본(PCCP/515C) | FDA 자료 | 미확인 | [링크](https://www.fda.gov/media/187905/download) |
| Good Machine Learning Practice (GMLP) for Medical Device Development: Guiding Principles | Guiding Principles | 2021-10 | [링크](https://www.fda.gov/medical-devices/software-medical-device-samd/good-machine-learning-practice-medical-device-development-guiding-principles) |
| GMLP 원문 PDF | Guiding Principles | 2021-10 | [링크](https://www.fda.gov/media/153486/download) |
| Transparency for Machine Learning-Enabled Medical Devices: Guiding Principles | Guiding Principles | 2024-06-13 | [링크](https://www.fda.gov/medical-devices/software-medical-device-samd/transparency-machine-learning-enabled-medical-devices-guiding-principles) |
| CDRH 보도자료(투명성 가이딩 원칙) | 보도자료 | 2024-06-13 | [링크](https://www.fda.gov/medical-devices/medical-devices-news-and-events/cdrh-issues-guiding-principles-transparency-machine-learning-enabled-medical-devices) |
| Clinical Decision Support Software (FDA-2017-D-6569) | Final Guidance | 재발행 2026-01-29(2026-01-06 대체) | [링크](https://www.fda.gov/media/109618/download) |
| Clinical Decision Support Software 검색 페이지 | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software) |
| Clinical Decision Support Software – FAQs | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs) |
| Covington & Burling 분석(2026 CDS 개정, 2차 출처) | 법무법인 분석 | 2026-01 | [링크](https://www.cov.com/news-and-insights/insights/2026/01/5-key-takeaways-from-fdas-revised-clinical-decision-support-cds-software-guidance) |
| FDLI 분석(21st Century Cures Act, 2차 출처) | 법률정보 | 2017-04 | [링크](https://www.fdli.org/2017/04/21st-century-cures-act-provides-clarity-fdas-regulation-software/) |
| Federal Register 2017-12-08 (2017-26469) | Federal Register | 2017-12-08 | [링크](https://www.govinfo.gov/content/pkg/FR-2017-12-08/pdf/2017-26469.pdf) |
| IMDRF SaMD: Possible Framework for Risk Categorization (N12FINAL:2014) | IMDRF Final Document | 2014-09-18 | [링크](https://www.imdrf.org/documents/software-medical-device-possible-framework-risk-categorization-and-corresponding-considerations) |
| IMDRF N12 PDF 원문 | IMDRF Final Document | 2014-09-18 | [링크](https://www.imdrf.org/sites/default/files/docs/imdrf/final/technical/imdrf-tech-140918-samd-framework-risk-categorization-141013.pdf) |
| Characterization Considerations for Medical Device Software and Software-Specific Risk (N81 FINAL:2025) | IMDRF Final Document | 2025-01-29 | [링크](https://www.imdrf.org/documents/characterization-considerations-medical-device-software-and-software-specific-risk) |
| SaMD: Clinical Evaluation (N41FINAL:2017) | IMDRF Final Document | 2017-09-21 | [링크](https://www.imdrf.org/sites/default/files/docs/imdrf/final/technical/imdrf-tech-170921-samd-n41-clinical-evaluation_1.pdf) |
| Artificial Intelligence and Software as a Medical Device (정책 연혁 페이지) | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-software-medical-device) |
| AI-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations (FDA-2024-D-4488) | Draft Guidance | 2025-01-07 | [링크](https://www.fda.gov/media/184856/download) |
| 동 초안 검색 페이지 | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/artificial-intelligence-enabled-device-software-functions-lifecycle-management-and-marketing) |
| FDA Digital Health Advisory Committee | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/digital-health-center-excellence/fda-digital-health-advisory-committee) |
| DHAC 2025-11-06 회의 공고(FDA-2025-N-2338) | 회의 공고 | 2025-11-06 | [링크](https://www.fda.gov/advisory-committees/advisory-committee-calendar/november-6-2025-digital-health-advisory-committee-meeting-announcement-11062025) |
| DHAC 회의 요약자료 | FDA 자료 | 2025-11-06 | [링크](https://www.fda.gov/media/189618/download) |
| MedTech Dive 분석(AI 기기 수, 2차 출처) | 뉴스 | 2026-05-11 | [링크](https://www.medtechdive.com/news/ai-medtech-track-new-devices-fda/748397/) |
| IntuitionLabs 분석(AI 기기 수, 2차 출처) | 분석리포트 | 2026-07-19 | [링크](https://intuitionlabs.ai/articles/fda-approved-ai-medical-devices-list) |

### 9-3. 소프트웨어 문서화·사이버보안·QMSR·임상데이터·라벨링·시판후 (4·5·6절 관련)

| 문서명(영문 원제) | 유형 | 발행·개정일 | URL |
|---|---|---|---|
| Content of Premarket Submissions for Device Software Functions (FDA-2021-D-0775) | Final Guidance | 2023-06-14 | [링크](https://www.fda.gov/media/153781/download) |
| 동 안내 페이지 | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/content-premarket-submissions-device-software-functions) |
| Off-The-Shelf Software Use in Medical Devices (FDA-2019-D-3598) | Final Guidance | 2023-08-11 | [링크](https://www.fda.gov/media/71794/download) |
| 동 안내 페이지 | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/shelf-software-use-medical-devices) |
| Cybersecurity in Medical Devices: Quality Management System Considerations and Content of Premarket Submissions | Final Guidance | 2026-02-03(최신) | [링크](https://www.fda.gov/media/119933/download) |
| Cybersecurity 안내 페이지 | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity) |
| Postmarket Management of Cybersecurity in Medical Devices | Final Guidance | 2016-12-27 | 직접 PDF **미확인**(안내페이지에서 존재 확인) — [안내페이지](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity) |
| Medical Devices; Quality System Regulation Amendments (QMSR, 89 FR 7496 / 2024-01709) | Federal Register 최종규칙 | 발행 2024-02-02, 시행 2026-02-02 | [링크](https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments) |
| FDA QMSR 안내 페이지 | FDA 안내페이지 | Update 2026-02-02 | [링크](https://www.fda.gov/medical-devices/postmarket-requirements-devices/quality-management-system-regulation-qmsr) |
| QMSR 정정고시(2024-23701, 2차 출처 justia.com) | 2차 법률정보 | 2024-10-15 | [링크](https://regulations.justia.com/regulations/fedreg/2024/10/15/2024-23701.html) |
| FDA QMSR 설명자료(슬라이드 PDF) | FDA 자료 | 미확인 | [링크](https://www.fda.gov/media/190872/download) |
| 21 CFR Part 812 | eCFR | published 2026-02-02 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-812) |
| 21 CFR Part 50 | eCFR | published 2024-01-22 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-50) |
| 21 CFR Part 56 | eCFR | published 2026-07-27 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-56) |
| Use of Real-World Evidence to Support Regulatory Decision-Making for Medical Devices (FDA-2023-D-4395) | Final Guidance | 2025-12-18 | [링크](https://www.fda.gov/media/190201/download) |
| 동 안내 페이지 | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/use-real-world-evidence-support-regulatory-decision-making-medical-devices) |
| RWE 2017년 원판 Federal Register 공고 | Federal Register | 2017-08-31 | [링크](https://www.federalregister.gov/documents/2017/08/31/2017-18469/use-of-real-world-evidence-to-support-regulatory-decision-making-for-medical-devices-guidance-for) |
| 21 CFR Part 801 | eCFR | published 2026-02-02 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-801) |
| 21 CFR Part 830 | eCFR | published 2023-07-14 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-830) |
| UDI Rule, Guidances, Training and Other Resources | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/unique-device-identification-system-udi-system/udi-rule-guidances-training-and-other-resources) |
| 21 CFR Part 803 | eCFR | published 2026-02-02 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-803) |
| 21 CFR Part 806 | eCFR | published 2019-01-04 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-806) |
| 21 CFR Part 822 | eCFR | published 2020-02-04 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-822) |
| 21 CFR Part 7 | eCFR | published 2023-07-14 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-7) |
| 21 CFR Part 11 | eCFR | published 2023-02-03 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11) |
| emergobyul.com QMSR 검사매뉴얼 분석(2차 출처) | 업계 분석 | 미확인 | [링크](https://www.emergobyul.com/news/qmsr-what-us-fdas-new-inspection-manual-really-means-device-manufacturers) |

### 9-4. 제출 실무·수수료·표준 (7·8절 관련)

| 문서명(영문 원제) | 유형 | 발행·개정일 | URL |
|---|---|---|---|
| eSTAR Program | FDA 안내페이지 | 업데이트 2026-06-01 | [링크](https://www.fda.gov/medical-devices/how-study-and-market-your-device/estar-program) |
| Electronic Submission Template for Medical Device 510(k) Submissions (FDA-2021-D-0872) | Final Guidance | 2023-10-02(원발행 2022-09-22) | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/electronic-submission-template-medical-device-510k-submissions) |
| 동 PDF | Final Guidance | 상동 | [링크](https://www.fda.gov/media/152429/download) |
| Send and Track Medical Device Premarket Submissions Online: CDRH Portal | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/industry-medical-devices/send-and-track-medical-device-premarket-submissions-online-cdrh-portal) |
| FDA eSubmitter | FDA 안내페이지 | 업데이트 2025-08-07 | [링크](https://www.fda.gov/industry/fda-esubmitter) |
| Nicotine Insider(CTP eSubmitter 폐지, 참고, 2차 출처) | 뉴스 | 2026-07-20 | [링크](https://nicotineinsider.com/2026/07/20/u-s-fda-expands-pmta-submission-portal/) |
| Medical Device User Fee Amendments (MDUFA): Fees | FDA 공식페이지 | FY2026 | [링크](https://www.fda.gov/industry/fda-user-fee-programs/medical-device-user-fee-amendments-mdufa-fees) |
| Reduced or Waived Medical Device User Fees: SBD Program | FDA 안내페이지 | 업데이트 2026-07-13 | [링크](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/reduced-or-waived-medical-device-user-fees-small-business-determination-sbd-program) |
| Medical Device User Fee Small Business Qualification and Determination (FDA-2018-D-1873) | Final Guidance | 2025-07-30 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/medical-device-user-fee-small-business-qualification-and-determination) |
| 21 CFR Part 807 Subpart B | eCFR | 미확인 | [링크](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-807/subpart-B) |
| Device Registration and Listing | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/how-study-and-market-your-device/device-registration-and-listing) |
| U.S. Agents | FDA 안내페이지 | 업데이트 2023-08-15 | [링크](https://www.fda.gov/medical-devices/device-registration-and-listing/us-agents) |
| Importing Medical Devices and Radiation-Emitting Electronic Products to the US | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/importing-and-exporting-medical-devices/importing-medical-devices-and-radiation-emitting-electronic-products-us) |
| The Q-Submission Program (FDA-2018-D-1774) | Final Guidance | 2025-05-29 | [링크](https://www.fda.gov/media/114034/download) |
| Refuse to Accept Policy for 510(k)s (FDA-2012-D-0523) | Final Guidance | 2022-04-21 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/refuse-accept-policy-510ks) |
| 동 PDF | Final Guidance | 상동 | [링크](https://www.fda.gov/media/83888/download) |
| Acceptance Checklists for 510(k)s | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/premarket-notification-510k/acceptance-checklists-510ks) |
| Acceptance Review for De Novo Classification Requests (FDA-2017-D-6069) | Guidance | 미확인 | [링크](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/acceptance-review-de-novo-classification-requests) |
| 동 PDF | Guidance | 미확인 | [링크](https://www.fda.gov/media/152657/download) |
| FDA Recognized Consensus Standards Database | FDA DB | 갱신 2025-12-22 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/search.cfm) |
| Division of Standards and Conformity Assessment | FDA 안내페이지 | 미확인 | [링크](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/division-standards-and-conformity-assessment) |
| Accreditation Scheme for Conformity Assessment (ASCA) | FDA 안내페이지 | 업데이트 2026-01-28 | [링크](https://www.fda.gov/medical-devices/division-standards-and-conformity-assessment/accreditation-scheme-conformity-assessment-asca) |
| IEC 62304 DB 검색결과 | FDA DB | 미확인 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?start_search=1&productcode=&category=&type=&title=&organization=2&referencenumber=&regulationnumber=&effectivedatefrom=&effectivedateto=&pagenum=50&sortcolumn=pad) |
| IEC 62366-1 DB 상세 | FDA DB | 등재 2020-07-06 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=41235) |
| ISO 14971 DB 상세 | FDA DB | 등재 2019-12-23 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=41349) |
| ANSI/AAMI SW96:2023 DB 상세 | FDA DB | 등재 2023-10-09 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=44689) |
| IEC 81001-5-1 DB 상세 | FDA DB | 등재 2022-12-19 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfstandards/detail.cfm?standard__identification_no=43889) |
| AAMI CR515:2025 DB 검색결과 | FDA DB | 등재 2025-12-22 | [링크](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?start_search=1&productcode=&category=&title=medical+device&supportingdocsyn=off&ascapilotyn=off&organization=&regulationnumber=&recognitionnumber=&effectivedatefrom=&effectivedateto=&pagenum=100&sortcolumn=rt) |
| RAPS 기사(신규 인정 표준, 2차 출처) | 뉴스 | 미확인 | [링크](https://www.raps.org/resource/fda-recognizes-three-new-international-medical-dev.html) |

**실무 체크리스트**
- [ ] 위 4개 하위 표를 카테고리별 즐겨찾기로 저장해 신청 단계별 참조 문서로 활용
- [ ] PDF 직접링크(`/media/`)는 FDA 사이트 개편 시 변경될 수 있으므로 주기적으로 유효성 재확인
- [ ] 2차 출처(뉴스·법무법인 분석)로 표시된 항목은 반드시 1차 원문으로 교차검증 후 규제전략에 반영

---

## 10. 최신 상태 및 변경 이력 타임라인 (2024~2026)

| 날짜 | 변경 사항 | 근거 |
|---|---|---|
| 2024-02-02 | QMSR 최종규칙 발행(Federal Register 89 FR 7496, Doc. 2024-01709) | [Federal Register](https://www.federalregister.gov/documents/2024/02/02/2024-01709/medical-devices-quality-system-regulation-amendments) |
| 2024-03-15 | FD&C Act §515C(PCCP) 관련 Federal Register 최종규칙(21 CFR 807.81(b), 814.39(b) 개정) | [govinfo](https://www.govinfo.gov/content/pkg/FR-2024-03-15/pdf/2024-05473.pdf) |
| 2024-06-13 | MLMD 투명성 가이딩 원칙 발행 | [FDA](https://www.fda.gov/medical-devices/software-medical-device-samd/transparency-machine-learning-enabled-medical-devices-guiding-principles) |
| 2024-08-21 | 범용 PCCP 초안 가이던스 발행(FDA-2024-D-2338, 현재도 초안) | [FDA](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/predetermined-change-control-plans-medical-devices) |
| 2024-10-15 | QMSR 정정고시(89 FR, 2024-23701) | [justia.com(2차)](https://regulations.justia.com/regulations/fedreg/2024/10/15/2024-23701.html) |
| 2024-11-01 | Small Business Request(SBD) 전자제출 의무화(CDRH Portal) | [SBD Program](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/reduced-or-waived-medical-device-user-fees-small-business-determination-sbd-program) |
| 2024-12-04 | PCCP(AI-DSF) 마케팅제출권고 최초 최종 가이던스 발행 | [FDA PDF](https://www.fda.gov/media/166704/download) |
| 2025-01-07 | AI-Enabled Device Software Functions Lifecycle Management 초안 가이던스 발행(현재도 초안) | [FDA PDF](https://www.fda.gov/media/184856/download) |
| 2025-01-13 | HDE Modular Review 반영 가이던스 소규모 업데이트 | [FDA](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/humanitarian-device-exemption) |
| 2025-05-29 | Q-Submission Program 최종 가이던스 개정 발행 | [FDA PDF](https://www.fda.gov/media/114034/download) |
| 2025-06-13 | 21 CFR 892.2090 신설(Radiological CAD/Dx software, Class II) | [Federal Register](https://www.federalregister.gov/documents/2025/06/13/2025-10789/medical-devices-radiology-devices-classification-of-the-radiological-computer-assisted-detection-and) |
| 2025-06-27 | 사이버보안 가이던스 Level 1 개정판 발행(524B, Section VII 신설) | [FDA](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity) |
| 2025-07-30 | Small Business Qualification and Determination 가이던스 최종판(2018년판 대체) | [FDA](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/medical-device-user-fee-small-business-qualification-and-determination) |
| 2025-08-18 | **PCCP(AI-DSF) 최종 가이던스 재발행** | [FDA PDF](https://www.fda.gov/media/166704/download) |
| 2025-09-18 | 일부 ASCA 인증기관 인증 철회 | [FDA ASCA](https://www.fda.gov/medical-devices/division-standards-and-conformity-assessment/accreditation-scheme-conformity-assessment-asca) |
| 2025-10-01 | De Novo 신청 eSTAR 전자제출 의무화 | [CDRH Portal](https://www.fda.gov/medical-devices/industry-medical-devices/send-and-track-medical-device-premarket-submissions-online-cdrh-portal) |
| 2025-11-06 | DHAC 회의(생성형 AI 정신건강 기기) 개최 | [FDA 회의공고](https://www.fda.gov/advisory-committees/advisory-committee-calendar/november-6-2025-digital-health-advisory-committee-meeting-announcement-11062025) |
| 2025-12-18 | RWE 가이던스 최종 개정판 발행(개별환자 데이터 요구 완화) | [FDA PDF](https://www.fda.gov/media/190201/download) |
| 2025-12-22 | AAMI CR515:2025(ML 특화 사이버보안 표준) FDA 인정 등재 | [FDA DB](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?start_search=1&productcode=&category=&title=medical+device&supportingdocsyn=off&ascapilotyn=off&organization=&regulationnumber=&recognitionnumber=&effectivedatefrom=&effectivedateto=&pagenum=100&sortcolumn=rt) |
| **2026-01-06** | CDS 가이던스 개정 최종본 발행(2022년판 대체) | [FDA PDF](https://www.fda.gov/media/109618/download) |
| **2026-01-29** | CDS 가이던스 재발행판(현재 유효본, 01-06판 대체) | [FDA PDF](https://www.fda.gov/media/109618/download) |
| 2026-02-02 | **QMSR 시행(effective)** — 21 CFR 820 전면 개편, ISO 13485:2016 IBR 적용 개시 | [FDA QMSR](https://www.fda.gov/medical-devices/postmarket-requirements-devices/quality-management-system-regulation-qmsr) |
| **2026-02-03** | 사이버보안 가이던스 최신판 발행(QMSR 정합 Level 2 업데이트) | [FDA PDF](https://www.fda.gov/media/119933/download) |
| 2026-02-17(예상) | RWE 가이던스 신규 권고사항 반영 신고 개시(60일 전환기간 종료) | [FDA PDF](https://www.fda.gov/media/190201/download) |
| 2026-05-29 | Human Factors Content Guidance 발행(eSTAR 반영, 2026-08-01 발효 예정) | [eSTAR Program](https://www.fda.gov/medical-devices/how-study-and-market-your-device/estar-program) |
| 2026-07-01 | TAP 전체 OHT Breakthrough/STeP 기기로 등록 확대 | [FDA TAP](https://www.fda.gov/medical-devices/how-study-and-market-your-device/total-product-life-cycle-advisory-program-tap) |
| 2026-08-01(예상) | FY2026 Small Business Request 신청 마감 | [SBD Program](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/reduced-or-waived-medical-device-user-fees-small-business-determination-sbd-program) |
| 2026-08-03(예정) | eSTAR/PreSTAR 구버전(v6.2/v2.2) 폐지 예정 | [eSTAR Program](https://www.fda.gov/medical-devices/how-study-and-market-your-device/estar-program) |

**실무 체크리스트**
- [ ] 2026년 2월 QMSR·사이버보안 가이던스 동시 정합 완료 여부 자체 점검
- [ ] 2026년 1월 CDS 가이던스 개정 내용을 CDS 성격 AI 기능에 즉시 반영
- [ ] 2025년 8월 PCCP 재발행판 기준으로 AI 변경관리계획 문서 최신화
- [ ] eSTAR v7.0/PreSTAR v3.0으로 조기 전환(2026년 8월 구버전 폐지 대비)

---

## 11. 확인 불가 / 후속 검증 필요 항목

| 구분 | 항목 | 상태 |
|---|---|---|
| 인허가 경로 | HDE의 구체적 CFR Subpart(21 CFR 814 Subpart H) 명시적 본문 확인 | 미확인(추정치로만 표시) |
| 인허가 경로 | HDE의 MDUFA 심사기간(일수) 목표 | 미확인 |
| 인허가 경로 | STeP의 개별 법조항(§515B 이외 별도 조항 여부) | 미확인 |
| 기기분류 | 21 CFR 892.2070의 전체 특수통제 조항 원문(세부 항목) | 부분 미확인 |
| 기기분류 | 21 CFR 807 Subpart E, 21 CFR 860의 "가장 최근 개정일" 명시적 날짜 | 미확인(eCFR 페이지 날짜 필드 공란) |
| 기기분류 | 513(g) 신청의 2026년 현재 정확한 사용자수수료 금액(2016 회계연도 수수료만 확인) | 미확인 |
| 인허가 경로 | MDUFA VI(FY2028~) 관련 신규 경로/프로그램 도입 여부 | 미확인(협상 진행만 확인) |
| AI/SaMD | AI-Enabled Device Software Functions Lifecycle Management 가이던스의 최종본 발행 여부 및 시기 | 미확인(2026-07-29 기준 초안 유지) |
| AI/SaMD | AI-Enabled Medical Device List의 FDA 공식 발표 총 건수 및 정확한 최종 갱신일 | 미확인(3차 분석기관 수치만 확인) |
| AI/SaMD | Digital Health Advisory Committee의 2026년 예정 회의 일정/의제 | 미확인 |
| AI/SaMD | FDA가 IMDRF SaMD Clinical Evaluation(N41:2017)을 공식 가이던스로 정식 채택했는지 여부 | 미확인 |
| 사이버보안 | FD&C Act §524B 조문 자체의 ecfr.gov 직접 링크(가이던스 인용으로만 확인) | 미확인 |
| 사이버보안 | Postmarket Management of Cybersecurity in Medical Devices(2016)의 직접 PDF 다운로드 URL | 미확인 |
| QMSR | QMSR 정정고시(2024-23701)의 federalregister.gov/govinfo.gov 1차 URL 직접 확인 | 미확인(2차 출처 justia.com만 확인) |
| 라벨링 | 소프트웨어 전용 독립 라벨링 가이던스 문서의 존재 여부(제목 특정) | 미확인 |
| 전자기록 | 21 CFR Part 11의 SaMD 소프트웨어 자체에 대한 구체적 scope 해당성(§11.1 상세 미확보) | 미확인 |
| 시판후 | 21 CFR Part 812, 801, 803, 850 등 eCFR 페이지의 조항별 세부 최종 개정일 | 미확인(페이지 메타데이터만 확인) |
| 제출실무 | Electronic Submission Template for Medical Device De Novo Requests 가이던스의 정확한 발행일자·Docket 번호 | 미확인 |
| 제출실무 | 21 CFR 807.37(외국시설), 807.39(최초수입자) 조문 전체 원문 텍스트 | 미확인(조항 제목만 확인) |
| 제출실무 | "DRLM"이 FURLS 내 공식 하위시스템명으로 독자 사용되는지 여부 | 미확인 |
| 인정표준 | ISO/IEC 27001의 FDA Recognized Consensus Standards DB 내 개별 등재 여부 | 미확인 |
| 인정표준 | ANSI/AAMI/ISO 13485:2016의 FDA DB상 개별 Recognition Number(QMSR을 통한 참조편입은 확인됨) | 미확인 |
| 인정표준 | ISO/IEC/IEEE 29119-1의 FDA DB 직접 등재 확인 | 미확인(RAPS 2차 보도만 확인) |
| 인정표준 | Q-Submission/Acceptance Review for De Novo 가이던스의 OMB 관리번호 만료일 갱신 여부(0910-0844, 페이지 기재 2025-01-31) | 미확인 |

**실무 체크리스트**
- [ ] 위 미확인 항목 중 자사 제품에 직결되는 사항(예: 892.2070 특수통제 세부, §524B 조문 원문)은 FDA Q-Sub 또는 규제 컨설턴트를 통해 별도 확인
- [ ] 2차 출처(뉴스·법무법인·컨설팅 분석) 기반 수치는 신청 서류 작성 시 인용하지 말고 1차 출처 재확인 후 사용
- [ ] 본 문서는 2026년 7월 29일 기준이므로, 실제 신청 착수 시점에 fda.gov·eCFR 최신본 재확인 필수
