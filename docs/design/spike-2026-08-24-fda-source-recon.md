# Spike — FDA source reconnaissance

- **Date:** 2026-08-24
- **Purpose:** Answer the three questions [ADR-0018](ADR-0018-fda-source-model.md) rests on against
  **real sources**, before a second authority's connectors and parser profile are designed on top of
  assumptions. [phase2.0a](../plan/phase2.0a_fda.md) § W0 makes this blocking: *"every endpoint shape
  is unverified until a live call returns one."*
- **Method:** live HTTP against `ecfr.gov`, `federalregister.gov`, `api.govinfo.gov`,
  `uscode.house.gov` and `accessdata.fda.gov`. Anonymous except govinfo, which was probed with the
  public documented `DEMO_KEY`.
- **Scope:** the two Phase 2 FDA cells (`fda_samd`, `fda_cosmetic`).
- **Prior art it replaces:** four documents in `docs/reference/` describe this source landscape, and
  two of them are the same file (`fda-regops.md` and `samd-fda.md` differ by three lines). Every
  external citation in all four carries a `utm_source=chatgpt.com` tag — they are LLM-generated
  research, not measurement. They were **directionally right and wrong in the load-bearing detail**;
  see *Where the prior research was wrong*.

---

## Q1 — Does the eCFR serve point-in-time text, and at what granularity?

**Yes to both, and the date parameter is honoured.** This was the single most load-bearing probe: had
it failed, the Federal Register would have been the only possible version spine.

`GET /api/versioner/v1/full/{date}/title-21.xml?part=820` at three dates:

| Date | HTTP | Bytes | sha256 (first 8) |
|---|---|---:|---|
| 2026-08-01 | 200 | 21,523 | `4fdb61ec` |
| 2026-01-15 | 200 | 66,042 | `0def46a7` |
| 2025-06-01 | 200 | 66,042 | `0def46a7` |

The two pre-2026-02-02 dates are **byte-identical to each other** and the post date **differs** —
which is the correct semantics, not a coincidence: 21 CFR 820 became the Quality Management System
Regulation (QMSR) effective 2026-02-02, and the new part is a third of the size because it
incorporates ISO 13485:2016 by reference instead of restating it.

**This is the opposite of the `efYd` trap.** ADR-0016 decision 2 records an MFDS parameter that
appears to work and silently returns the wrong snapshot. The eCFR returns different bytes for
different version windows and identical bytes within one — so a point-in-time fetch can be trusted
without a corroborating check.

### Granularity

| Query | HTTP | Bytes |
|---|---|---:|
| `?part=820` | 200 | 21,523 |
| `?part=820&subpart=A` | 200 | 15,598 |
| `?section=820.35` (no ancestors) | 200 | 2,628 |
| `?chapter=I&part=820&section=820.35` | 200 | 2,628 |
| `?section=820.30` | **404** | 38 |
| `?part=820&subpart=C` | **404** | 38 |
| `?part=820&subpart=ZZ` | **404** | 38 |

**A section is addressable on its own, with no ancestor context required.** The two 404s that look
like a broken parameter are not: `820.30` and subpart `C` genuinely do not exist at that date — the
QMSR reserved them as the range nodes `820.20-820.30` and `C-O`. Both 404s carry
`{"error":"No matching content found."}`. An initial reading of the first 404 as "sections are not
addressable" was wrong, and re-probing with a section that exists is what caught it.

### What the XML carries

`DIV5 TYPE="PART"` → `DIV6 TYPE="SUBPART"` → `DIV8 TYPE="SECTION"`, with the number in `N`. Three
findings matter more than the hierarchy:

1. **The authority states its own citation.** Every node carries
   `hierarchy_metadata={"path":…,"citation":"21 CFR 820.1"}` — Part nodes read `21 CFR Part 820`,
   subparts `21 CFR Part 820 Subpart A`. The canonical citation does **not** have to be derived from
   the hierarchy; it can be read from the envelope. (`path` contains a literal `_SUBSTITUTE_DATE_`
   placeholder and is not usable as-is.)
2. **Paragraph designations are inline prose, not structure.** `(a)`, `(1)`, `(i)`, `(A)` appear
   inside `<P>` text — `<P>(a) <I>Applicability.</I> Current good manufacturing practice…`. This is
   the sharpest departure from MFDS, where the spike of 2026-07-29 found 조/항/호/목 arriving as
   separate fields with no segmentation to do. `cfr_structured` has to segment them out of prose.
3. **`<CITA TYPE="N">` carries per-section amendment history as Federal Register citations** —
   `[61 FR 52654, Oct. 7, 1996, as amended at 65 FR 17136, Mar. 31, 2000; … 85 FR 18442, Apr. 2, 2020]`.
   It is bracketed prose, not fields. The old part 820 carried 6 of them; the new one carries none,
   because a single part-level `<SOURCE>` covers it — `89 FR 7523, Feb. 2, 2024, unless otherwise noted`.

## Q2 — Does a Federal Register final rule state its effective date and its affected CFR sections as data?

**The date, yes. The sections, no — only the Part.**

`GET /api/v1/documents.json` filtered to `conditions[agencies][]=food-and-drug-administration` and
`conditions[type][]=RULE` reports **3,661** FDA final rules and returns `effective_on` as a
structured date field:

| Document | Citation | Published | `effective_on` | Lag | `cfr_references` |
|---|---|---|---|---:|---|
| 2026-16942 | 91 FR 53524 | 2026-08-19 | 2026-08-19 | **0 d** | part 573 |
| 2026-16727 | 91 FR 53184 | 2026-08-17 | 2026-09-16 | 30 d | part 864 |
| 2026-16420 | 91 FR 52011 | 2026-08-12 | **null** | — | part 117 |
| 2026-15963 | 91 FR 50708 | 2026-08-06 | 2026-08-06 | **0 d** | part 892 |
| 2026-15920 | 91 FR 50475 | 2026-08-05 | 2027-01-15 | 163 d | part 74 |

Three things follow, and all three are load-bearing:

1. **`effective_on` is envelope-grade** — the same category as MFDS `시행일자`, so ADR-0016 decision 3
   transfers unchanged. The `dates` field additionally carries the prose (*"This rule is effective
   February 2, 2026. The incorporation by reference of certain material…"*), which is exactly the
   `effective_date_phrase` input [ADR-0013](ADR-0013-unresolvable-effective-dates.md) asks for.
2. **It is nullable.** One of five returned `null`. ADR-0013 applies as written for those — null with
   the phrase retained, never a derived date.
3. **The lag is 0 to 163 days and sometimes null.** A same-day-effective rule means the ≤24h
   detection-latency gate has no publication-to-effect grace period to spend.

**`cfr_references` resolves to Part, never Section.** Filtering the other direction —
`conditions[cfr][title]=21&conditions[cfr][part]=820` — returns **30** documents and mixes `Rule`
with `Proposed Rule`, so a type filter is mandatory.

### The QMSR rule is FDA's 시행예정 case, and it is a two-year window

| Field | Value |
|---|---|
| `document_number` | `2024-01709` |
| `citation` | 89 FR 7496 |
| `publication_date` | 2024-02-02 |
| `effective_on` | **2026-02-02** — a 731-day pending window |
| `cfr_references` | parts **4 and 820** — one rule, two Parts |
| `regulation_id_numbers` | `0910-AH99` |
| `full_text_xml_url` | present |

A second document, `2024-23701` (89 FR 82945, published 2024-10-15), carries the **same**
`effective_on` of 2026-02-02 — so one effective date has two Federal Register documents behind it.

**The eCFR `<SOURCE>` for part 820 reads `89 FR 7523`; the Federal Register API calls the same rule
`89 FR 7496`.** 7523 is the page *inside* the rule at which part 820 begins. Joining the two surfaces
on citation equality would therefore fail on every section. The join is document number or page
range, not the citation string.

## Q3 — What is the detection denominator for the FDA cells?

**It exists and is computable — the coverage gate is measurable.** phase2.0a flags this as
unanswered, on the grounds that `regulation.discover_sources` enumerates MFDS 행정규칙 by 소관부처
code and FDA has no equivalent list. It has a better one.

`GET /api/versioner/v1/structure/current/title-21.json` (2.67 MB) enumerates the whole title:

| Node type | Count |
|---|---:|
| title | 1 |
| chapter | 3 |
| subchapter | 12 |
| part | 275 |
| subpart | 949 |
| **subject_group** | **102** |
| section | **8,408** |
| appendix | **5** |

Every Part named for the FDA cells in [import-source-map.md](../import-source-map.md) is present and
none is reserved:

| Part | Subparts | Direct sections | Title |
|---|---:|---:|---|
| 7 | 5 | 0 | Enforcement Policy |
| 11 | 3 | 0 | Electronic Records; Electronic Signatures |
| 700 | 2 | 0 | General (cosmetics) |
| 701 | 3 | 0 | Cosmetic Labeling |
| **710** | **0** | **9** | Voluntary Registration of Cosmetic Product Establishments |
| 740 | 2 | 0 | Cosmetic Product Warning Statements |
| 803 | 5 | 0 | Medical Device Reporting |
| 806 | 2 | 0 | Reports of Corrections and Removals |
| 807 | 5 | 0 | Establishment Registration and Device Listing |
| 820 | 3 | 0 | Quality Management System Regulation |
| 822 | 7 | 0 | Postmarket Surveillance |
| 860 | 4 | 0 | Medical Device Classification Procedures |
| 892 | 5 | 0 | Radiology Devices |

So the denominator is *sections of the parts in scope*, enumerable per cell from one call. It is a
**closed, authority-published list** — a stronger denominator than the MFDS cells have.

### And the change stream is structured too

`GET /api/versioner/v1/versions/title-21.json?part=820` returns **72 rows**, one per section-version,
with the schema:

`amendment_date` · `date` · `identifier` · `issue_date` · `name` · `part` · `removed` ·
`subpart` · `substantive` · `title` · `type`

- `identifier` is the section (`820.1`), `type` is `section`
- `amendment_date` and `issue_date` can differ (2016-12-30 amended, 2016-12-31 issued)
- **27 of 72 rows carry `removed: True`** — the authority itself flags removal, which is how the QMSR
  transition is recorded
- **`substantive` is a boolean on every row**

Incremental polling works: `?issue_date[gte]=2026-07-01` over the whole title returns 60 rows, all
`type=section`, all `substantive=True`, 4 `removed=True`, of which **2 touch parts in scope** —
`892.5060` amended 2026-08-06 and `892.5727` amended 2026-07-29. `meta` restates
`latest_amendment_date: 2026-08-19`.

**The two surfaces corroborate on a live amendment.** `892.5060` amended 2026-08-06 in the eCFR is
Federal Register document `2026-15963` (91 FR 50708), published 2026-08-06 against part 892. Neither
surface was needed to find the other; they agree.

## Where the prior research was wrong

The four `docs/reference/` documents got the shape right — eCFR is the text, the Federal Register is
the amendment surface, guidance has no API, and openFDA is not regulation text. What they got wrong
is what a design would have been built on:

| Claim in the research | Measured |
|---|---|
| eCFR gives "XML / JSON API", granularity unstated | Section-addressable, and **point-in-time is real and honoured** |
| Change detection needs the Federal Register (or RSS) | The eCFR **`versions` endpoint** gives per-section `amendment_date`, `removed` and `substantive` as structured data. Not mentioned anywhere in the research. |
| "eCFR Subscribe/RSS, Part별 변경 추적 가능" — presented as the recommended change-detection route | The one guessable feed path, `ecfr.gov/recent-changes.rss`, returns **302 with 0 bytes**. No per-Part feed URL was found. The `versions` endpoint makes the feed unnecessary. |
| Federal Register names the affected `21 CFR 변경` | `cfr_references` is **Part-level only** — no section |
| `federalregister.gov` for rules, unqualified | Returns `Proposed Rule` in the same result set; a `type` filter is mandatory |

`fda-url.md`'s concrete endpoint guesses (`/api/versioner/v1/structure/{date}/title-21.json`,
`/api/versioner/v1/full/{date}/title-21.xml?part=820`) both turned out to be correct.

## Failure signatures

Five were catalogued for MFDS, four of them HTTP-200. FDA's hosts are better behaved, and that itself
is a finding:

| Signature | Where | Handling |
|---|---|---|
| `404` + `{"error":"No matching content found."}` | eCFR, for any node that does not exist at that date | Honest. Not a drift signal on its own — a reserved or removed section legitimately 404s at one date and 200s at another. Disambiguate against the `versions` endpoint's `removed` flag. |
| `302` + 0 bytes | `ecfr.gov/recent-changes.rss` | A guessed path that does not exist. Do not follow the redirect and archive whatever it lands on. |
| Connection timeout, no HTTP status | `uscode.house.gov` — failed after 21 s | **Unreachable from this environment.** Recorded as measured, not as absent. Retry before concluding anything about the host. |
| `meta.import_in_progress: true` | eCFR `titles.json` | Was `false` throughout. A fetch during an import may serve a partial title; check the flag before trusting a diff. |
| **`503`, twice, then success** | `federalregister.gov/api/v1/documents.json` | **Found later, by the lag harness, not by these probes.** The curl probes above never tripped it; the first `PoliteFetcher` run hit `503` on attempts 0 and 1 and succeeded on the third. Transient, and absorbed by the existing backoff — but a connector that treated a single non-200 as failure would have recorded a failed observation on a source that is up. Whether `per_page=200` provokes it is untested. |

No silent-wrong-snapshot signature was found on any FDA host. **The 503 is the one signature these
probes missed and repetition found**, which is the argument for the connectors reusing
`PoliteFetcher` rather than a bare client.

## Incidental findings

- **`subject_group` is a real hierarchy level with no Korean equivalent** — 102 of them in title 21,
  sitting between subpart and section. Its `identifier` is an **opaque generated token**
  (`ECFRef316bd359c83c7`), which must never enter a `canonical_key`.
- **Appendix identifiers are prose strings with spaces** — all five in title 21 are of the form
  `Appendix B to Part 101`, one of them reserved. Nothing like `별표N`'s bare number, so a derived
  child key cannot be built by concatenating an index.
- **Range-named sections exist.** `820.20-820.30` is a single `DIV8 TYPE="SECTION"` whose `N` is a
  range, and subpart `C-O` is the same at subpart level. A key format assuming one number per node
  breaks on both.
- **The part hierarchy is not uniform.** Part 710 has 9 sections and no subparts; the other twelve
  parts in scope have subparts and no direct sections. A profile that assumes Part→Subpart→Section
  fails on 710.
- **Part 710 is still titled *Voluntary* Registration of Cosmetic Product Establishments.** MoCRA
  made facility registration mandatory, so the CFR part and the statute are out of step. Which one
  the `fda_cosmetic` cell treats as authoritative is a scope question, not a connector question.
- **govinfo is reachable and carries what is needed** — 42 collections including `USCODE`, `CFR`,
  `FR` and `STATUTE`. Probed with the public `DEMO_KEY`; a real key belongs in settings with a
  placeholder in the template ([ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 13).
- **`accessdata.fda.gov` Recognized Consensus Standards search returns 200 with 53 KB of HTML** — a
  server-rendered form, so Tier C in shape. Column labels only; no standard text is fetched at any
  point ([ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 7).
- **openFDA was not probed and does not need to be for this ADR.** It carries 510(k), PMA,
  classification, recalls, MAUDE and UDI — regulatory *data*, not regulation *text*. The
  undecomposed phase 2.0 named it and named neither eCFR nor govinfo, which is the catalog error
  phase2.0a W0 asked to settle.

## Actions taken

- [ADR-0018](ADR-0018-fda-source-model.md) written on this evidence, closing the three decisions
  [phase2.0a](../plan/phase2.0a_fda.md) required before the build.
- Confirmed endpoints and the Part inventory recorded in
  [import-source-map.md](../import-source-map.md) — the only source catalog.
- Raw probe responses were captured to a scratch directory, not committed. Every table above is
  reproducible from the URLs in *Sources*.

## Still open

- **Whether the eCFR `versions` endpoint lags the Federal Register, and by how much.** `titles.json`
  reported `latest_amended_on: 2026-08-19` against `up_to_date_as_of: 2026-08-20`, and the newest FDA
  final rule was published 2026-08-19 — so the lag is at most a day or two at this sample. One
  observation is not a measurement of a distribution, and the ≤24h gate depends on it.
  **A harness now measures it daily** — `scripts/fda_lag/`, accumulating into
  [fda-lag-observations.jsonl](fda-lag-observations.jsonl), with the first observation recorded
  2026-08-24. It reports `UNDETERMINED` and exits non-zero until ten distinct days are in.

  > **The naive number is misleading, and the first run proved it.** Observation date minus
  > `up_to_date_as_of` was **4 days** on 2026-08-24 — which reads as "the eCFR cannot carry a ≤24h
  > gate" but is actually a weekend. A compilation that does not advance because *nothing was
  > amended* and one that does not advance because it is *behind* produce the identical number.
  > The harness therefore reports a corroborated **blind spot**: days since the oldest rule that is
  > already in force yet absent from the compilation. On 2026-08-24 that was **0** — every rule in
  > force was present. Raw freshness is kept beside it as context, never as the verdict.
- **Whether a `removed: True` row plus a re-added identifier is distinguishable from a
  redesignation.** phase2.0a's open question. The flag is a much better starting point than expected,
  but renumbering-is-never-delete+add has not been demonstrated on CFR data.
- **The FD&C Act's version identity on govinfo.** Collections confirmed present; the granularity and
  whether `document_versions` can carry it were not probed.
- **How guidance documents are enumerated.** No API, and no crawl was attempted here. The Guidance
  block is a large part of the SaMD cell and its corpus size feeds the coverage denominator.
- **`uscode.house.gov` reachability**, and therefore whether it is a viable alternative to govinfo
  for the FD&C Act.

## Sources

- `https://www.ecfr.gov/api/versioner/v1/titles.json`
- `https://www.ecfr.gov/api/versioner/v1/structure/current/title-21.json`
- `https://www.ecfr.gov/api/versioner/v1/full/{date}/title-21.xml?part=820`
- `https://www.ecfr.gov/api/versioner/v1/full/{date}/title-21.xml?section=820.35`
- `https://www.ecfr.gov/api/versioner/v1/versions/title-21.json?part=820`
- `https://www.ecfr.gov/api/versioner/v1/versions/title-21.json?issue_date[gte]={date}`
- `https://www.federalregister.gov/api/v1/documents.json?conditions[agencies][]=food-and-drug-administration&conditions[type][]=RULE`
- `https://www.federalregister.gov/api/v1/documents.json?conditions[cfr][title]=21&conditions[cfr][part]=820`
- `https://www.federalregister.gov/api/v1/documents/2024-01709.json`
- `https://api.govinfo.gov/collections`
- `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/search.cfm`
- `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title21-chapter9&edition=prelim` — unreachable

---

# Part 2 — W0 completion (same day, after the ADR)

The three W0 rows left partial when [ADR-0018](ADR-0018-fda-source-model.md) was written, now closed.
**Two of the three turned up something the ADR did not account for.**

## Q4 — Does robots.txt permit what the connectors will fetch?

**Mostly, and there is one exception that lands on the ADR's version spine.**

| Host | Relevant rule | Effect |
|---|---|---|
| `ecfr.gov` | `Disallow: /api/renderer/v1/content/` and **`Disallow: /api/versioner/v1/full/`** | The **body-text endpoint is disallowed.** `versions/`, `structure/` and `titles.json` are not |
| `ecfr.gov` | `Disallow: /recent-changes` | Consistent with the 302 on the guessed RSS path |
| `federalregister.gov` | No `/api` rule, no `Crawl-delay` | Unrestricted |
| `accessdata.fda.gov` | No `cfStandards` rule, no `Crawl-delay`; **`Disallow: /scripts/cdrh/*excel*.cfm`** | The list page is permitted; **the Excel export is not** — read HTML |

**This is a genuine conflict and it is not ours to wave away.**
[ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 9 makes politeness part of the
contract, and [ADR-0018](ADR-0018-fda-source-model.md) decision 4 makes
`/api/versioner/v1/full/` the version spine — the one path robots.txt disallows.

The rule sits under `User-agent: *` with no API exemption, but the comment above it reads
*"Don't index developer tool links"*, which is an anti-**indexing** intent rather than an
anti-API one, and the endpoint is documented for developer use. Both readings are defensible.
**Recorded as ADR-0018 open question 6 rather than decided here** — it is a policy question about
someone else's server, and the honest options (fetch it as a documented API and say so; or route
citation text through `renderer` — also disallowed; or ask the eCFR) are not a spike's to pick.
Detection is unaffected either way: `versions/` is permitted.

## Q5 — Can `document_versions` carry the FD&C Act from govinfo?

**Yes, at section granularity — but the cadence is annual, and that is a problem for the gate.**

`GET /collections/USCODE/...` returns **1,552** packages named `USCODE-{year}-title{N}`; title 21 for
one year holds **901** granules:

| granuleId | granuleClass |
|---|---|
| `USCODE-2024-title21-toc` | `TOC` |
| `USCODE-2024-title21-chap1` | `TOPPARENT` |
| `USCODE-2024-title21-chap1-subchapI` | `NODE` |
| `USCODE-2024-title21-chap1-subchapI-sec1` | **`LEAF`** |

So the mapping is clean: **package → `DocumentVersion`** (`version_label` = the package id, which is
the authority's own key, satisfying [ADR-0016](ADR-0016-pending-effect-versions.md) decision 1), and
**`LEAF` granule → `Clause`**. `chap9` is the FD&C Act.

**The cadence is the finding.** The USC is republished **once a year**. The FD&C Act is the Primary
Law of *both* FDA cells, and an amendment to it would be invisible on this surface until the next
annual edition — against a **≤24h detection-latency gate**. The eCFR gives per-issue-date granularity
for the regulations; govinfo gives per-year for the statute they implement. Amendments arrive first
as Public Laws (govinfo's `PLAW` collection), which was **not probed**. Recorded as ADR-0018 open
question 7.

## Q6 — Do the Recognized Consensus Standards columns fit the existing connector?

**Configuration is enough for the fields that exist, and two fields do not exist on this surface.**

`results.cfm` is a **POST** form (`referencenumber`, `recognitionnumber`, `organization`, `category`,
`effectivedatefrom`/`to`, `productcode`, `regulationnumber`, `title`). Searching
`referencenumber=62304` returns rows under these labels:

| FDA label | `StandardRecord` field | Fits `DEFAULT_COLUMNS` as shipped? |
|---|---|---|
| Recognition Number | `recognition_number` | ✅ exact match on `"recognition number"` |
| Date of Entry | `effective_date` | ✅ exact match on `"date of entry"` |
| Standards Developing Organization | `issuing_body` | ❌ config — the default is `"organization"` |
| Standard Designation Number and Date | `number` | ❌ config |
| Standard Title | `title` | ❌ config — the default is `"title"` |
| Extent of Recognition | (feeds `status` by keyword scan) | — |
| Specialty Task Group Area | — | no counterpart; ignored |

`_match_column` matches the normalized label **exactly**, not by substring, so with the defaults the
`number` lookup misses and `row_to_record` returns `None` for **every** row. That is not a defect —
`sources.params["columns"]` exists for exactly this, and the connector's docstring predicted it. **The
seed row must carry a `columns` mapping; with one, no new code is needed.**

Two gaps config cannot close, and they are the deviation the plan asked to be told about:

- **`edition` has no column of its own.** FDA folds it into the designation
  (`62304 Edition 1.1 2015-06 CONSOLIDATED VERSION`). Pointing `edition` at the same column stores the
  whole blob twice; splitting it is code.
- **`withdrawal_date` is absent from the list view entirely.** `standard_references` has the column and
  this surface cannot fill it. The detail page behind *"click for recognition information"* may carry
  it; not probed.

Sample record, to show no body text is involved: `13-79` · Complete · IEC ·
`62304 Edition 1.1 2015-06` · *Medical device software — Software life cycle processes* ·
entered 01/14/2019.

## Q7 — Rate limits and politeness, per host

| Host | Limit | Evidence |
|---|---|---|
| `ecfr.gov` | **None published** — no `X-RateLimit-*`, no `Retry-After`, no `Crawl-delay` | ~30 probes over the session, none throttled |
| `federalregister.gov` | **None published** — same | |
| `api.govinfo.gov` | **`X-Ratelimit-Limit: 10`** on `DEMO_KEY` | Header returned on every call; remaining counted down 9 → 7 |
| `accessdata.fda.gov` | None published | |

**govinfo needs a real key**, and this is the only host that does. `DEMO_KEY` is 10 requests/hour —
enough to probe, not to ingest 901 granules. A key belongs in settings with a placeholder in the
template ([ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 13).

**"No published limit" is not "no limit."** Nothing was throttled here, which bounds the polite rate
from below and says nothing about the ceiling. `PoliteFetcher`'s existing backoff is reused
unchanged; no probe justified tuning it.
