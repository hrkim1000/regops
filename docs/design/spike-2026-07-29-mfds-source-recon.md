# Spike — MFDS source reconnaissance

- **Date:** 2026-07-29
- **Purpose:** Answer three open questions from ADR-0003 and ADR-0004 against **real sources**, before
  more design is written on top of assumptions
- **Method:** live fetches of `law.go.kr`, `open.law.go.kr` API guides, `data.go.kr` dataset pages,
  and `mfds.go.kr` listings
- **Scope:** the two Phase 1 gated cells (`mfds_samd`, `mfds_cosmetic`) only

---

## Q1 — Do MFDS sources expose a machine-readable publication date?

**Yes, comprehensively.** ADR-0003 open question 2 is closed.

| API | Date fields returned |
|---|---|
| 법령 조항호목 조회 | `공포일자`, `시행일자`, **`조문시행일자`**, `조문시행일자문자열`, `별표시행일자문자열` |
| 행정규칙 목록 조회 (MFDS 고시) | `발령일자`, `발령번호`, `시행일자`, `제개정구분명`, `소관부처명` |
| MFDS 제개정고시등 listing | `제개정일` per row (server-rendered HTML) |
| MFDS RSS | exists — `https://www.mfds.go.kr/www/rss/list.do` |

The detection-latency gate is therefore measurable per event for both gated cells; it does not have
to fall back to the retrospective audit sample.

**Unplanned validation.** `조문시행일자` is a **per-clause enforcement date**, and
`별표시행일자문자열` gives annexes their own. ADR-0003 decision 5 introduced a clause-level
`effective_date` override as an accommodation for staged application — the authoritative source
already models it that way. The model matches the domain rather than merely tolerating it.

## Q2 — What does canonicalization actually require?

**Materially less than estimated.** ADR-0003 open question 1 was rated the single biggest schedule
risk in the ingestion workstream; for Phase 1 that assessment was wrong.

- `law.go.kr` HTML is **JS-rendered** — a plain fetch returns only the page title. The HTML is not
  scrapable, so the OPEN API is the only viable path. The API returns `조문번호` / `조문내용` /
  `항` / `호` / `목` as **separate structured fields**, so there is no page chrome to strip and
  **no canonicalization step at all** for the largest source.
- Canonicalization is needed only for MFDS listing pages, where the predicted problem is confirmed
  real: rows carry **`조회수`** (view count). Hashing the raw row would report a change on every
  poll. RSS may remove even this need.

Revised risk: low for Phase 1, unknown for Phase 2 (EU/FDA/NMPA page templates untested).

## Q3 — Can tabular annexes be represented as clauses?

**Not settled, and this is the live risk.** The 별표·서식 목록 조회 API returns metadata and file
links only:

```
별표일련번호 · 관련법령ID · 별표명 · 별표번호 · 별표종류 · 소관부처명 ·
공포일자 · 공포번호 · 제개정구분명 · 별표서식파일링크 · 별표서식PDF파일링크
```

**No field carries the table rows.** Annex content is delivered as **HWP or PDF attachments**. One
secondary source indicates the 본문조회 API exposes a `<별표단위>` tag carrying annex text, which
would soften this — **unverified, and the first thing to check with a real API key.**

Why it matters: the prohibited and restricted ingredient lists in 화장품 안전기준 등에 관한 규정 —
the substantive obligations of the Cosmetic cell — *are* 별표. So the falsifier named in ADR-0004
decision 3 is concrete, not hypothetical:

1. **HWP parsing is an unbudgeted workstream.** Korean proprietary format, thin library support.
   `import-agent.md` lists HWP among supported formats, so the prior platform met this too.
2. **Connectors need an attachment-fetch path** — annex files are separate downloads from the body,
   with their own effective dates.
3. **The clause model must represent table rows**, or annex obligations cannot be cited at clause
   granularity, which breaks the citation contract for the Cosmetic cell specifically.

## Incidental findings

**The authority already computes clause-level diffs.** `법령 변경이력 목록 조회`,
`일자별 조문 개정 이력 목록 조회`, and **`조문별 변경 이력 목록 조회`** all exist. This can simplify
or independently cross-check our own diff stage for every `law.go.kr` source — an external ground
truth for the detection-coverage gate, obtained for free.

**MFDS 고시 can be enumerated rather than curated.** The 행정규칙 list API filters by `소관부처`
(`org` parameter, codes supplied separately). Sources for the MFDS cells can therefore be
**discovered** via API rather than hand-listed. Strictly better for detection coverage — no 고시
missed because nobody added it to the source map — and it changes the registry model from a curated
list to a curated list *plus* a discovery sweep.

## Actions taken

- ADR-0003: OQ2 closed, OQ1 downgraded, attachment-fetch path and API-driven discovery added,
  변경이력 cross-check recorded
- ADR-0004: decision 3 and OQ1 updated with the concrete annex finding
- development-plan.md: HWP/attachment parsing added as a Phase 1 workstream item

## Still to verify with an API key

1. Does 본문조회 return annex text in `<별표단위>`, or only a file link?
2. Ministry code for 식품의약품안전처 in the `org` parameter
3. Whether 조문별 변경이력 granularity matches our ClauseDiff needs
4. RSS feed contents — which categories, and whether 고시 amendments appear there

## Sources

[국가법령정보 OPEN API 가이드](https://open.law.go.kr/LSO/openApi/guideList.do) ·
[조항호목 조회](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsNwJoListGuide) ·
[행정규칙 목록 조회](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide) ·
[별표·서식 목록 조회](http://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsBylListGuide) ·
[별표·서식(법령) 데이터셋](https://www.data.go.kr/data/3069189/openapi.do) ·
[MFDS 제개정고시등](https://www.mfds.go.kr/brd/m_207/list.do) ·
[MFDS RSS](https://www.mfds.go.kr/www/rss/list.do)
