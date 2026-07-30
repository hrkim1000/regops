# Memo — agent list sketch (superseded)

> **Superseded 2026-07-30 by [ADR-0008](../design/ADR-0008-service-composition.md). Not authoritative.**
>
> Kept for provenance only. ADR-0008 decision 6 maps every entry below to its kind (agent ·
> pipeline · shared), owning service, and phase. Do not copy from this list:
>
> - Most entries are **pipelines, not agents** — only IR extraction, generation, and evidence
>   verification meet the three tests in ADR-0008 decision 2.
> - **Import Agent is one pipeline, not four.** Splitting it into Crawler / Parser / Normalizer
>   contradicts [import-agent.md](../import-agent.md); per-cell variation belongs in Connectors and
>   Parser Profiles, which this list omits.
> - **Audit Agent is not an agent** — as defined here (agent run history and decisions) it is
>   `extraction_runs` / `enrichment_runs` plus per-row provenance, distinct from the platform
>   `audit_log` ([ADR-0005](../design/ADR-0005-service-architecture.md) decision 4). Neither is a service.
> - **Interpretation Agent is absorbed** into IR extraction — as defined here it produces exactly
>   ADR-0004's IR fields. The graph vocabulary the name also carried became
>   [ADR-0010](../design/ADR-0010-semantic-enrichment-and-graph-model.md) `semantic enrichment`.
>   The name itself is retired: interpretation is a legal act.
> - **Evidence Agent here is evidence *collection*** (Phase 2 gap analysis), not the
>   evidence-verification pass every answer must survive — which is missing from the list and is a
>   trust invariant ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 6).
> - **Citation is a property of generation**, not a downstream agent — a separate citation step
>   inverts citation-enforced generation into generate-then-justify.

```text
Import Agent

Crawler Agent

Parser Agent

Normalizer Agent

Requirement Agent

Interpretation Agent

Embedding Agent

Version Agent

Diff Agent

Impact Agent

Compliance Agent

Mapping Agent

Evidence Agent

Report Agent

RAG Agent

Q&A Agent

Alert Agent

Audit Agent

```

## agent 정리

```
| Agent                            | 기능(한 줄 정의)                                           |
| -------------------------------- | ---------------------------------------------------- |
| **Import Agent**                 | 규제기관의 원본 규정(PDF, HTML, API 등)을 수집한다.                 |
| **Parser Agent**                 | 원본 문서를 구조화하여 Section, Table, Figure, Metadata를 추출한다. |
| **Requirement Extraction Agent** | 규정에서 요구사항(Requirements)을 식별하고 추출한다.                  |
| **Interpretation Agent**         | 요구사항의 의미를 해석하여 의무, 대상, 범위, 증적 등을 구조화한다.              |
| **Ontology Mapping Agent**       | 규정 용어를 Canonical 용어와 Ontology에 매핑한다.                 |
| **Cross-reference Agent**        | 관련 규정, 표준, 조항 간의 관계를 연결한다.                           |
| **Embedding Agent**              | 검색과 RAG를 위해 임베딩(Vector)을 생성·갱신한다.                    |
| **Version Agent**                | 규정의 버전과 개정 이력을 관리한다.                                 |
| **Diff Agent**                   | 버전 간 변경 사항을 비교하고 변경된 요구사항을 식별한다.                     |
| **Impact Analysis Agent**        | 규정 변경이 제품, 문서, 컴플라이언스에 미치는 영향을 분석한다.                 |
| **Retrieval Agent**              | 질문과 관련된 규정 및 요구사항을 검색한다.                             |
| **Reasoning Agent**              | 검색 결과를 기반으로 질의에 대한 논리적 답변을 생성한다.                     |
| **Citation Agent**               | 답변의 근거가 되는 규정과 조항을 정확하게 인용한다.                        |
| **Requirement Mapping Agent**    | 요구사항을 제품, 프로세스, QMS, Control과 매핑한다.                  |
| **Gap Analysis Agent**           | 요구사항 대비 부족하거나 미충족된 항목을 분석한다.                         |
| **Evidence Agent**               | 요구사항을 만족하는 증적(Document, Record)을 식별·연결한다.            |
| **Report Agent**                 | 분석 결과를 규제 보고서나 컴플라이언스 문서로 생성한다.                      |
| **Alert Agent**                  | 규정 변경이나 영향 분석 결과를 사용자에게 알림으로 전달한다.                   |
| **Audit Agent**                  | Agent 실행 이력과 의사결정 과정을 감사 가능하도록 기록한다.                 |

```
