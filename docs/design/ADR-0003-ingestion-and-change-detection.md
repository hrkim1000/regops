# ADR-0003 — Ingestion and change-detection contract

- **Status:** Proposed
- **Date:** 2026-07-29
- **Depends on:** [ADR-0001](ADR-0001-platform-foundation.md) (greenfield), [ADR-0002](ADR-0002-canonical-regulation-model.md) (canonical model)
- **Critical path:** development-plan.md § 6 — connector data contracts at W1-2, first connectors at W3-4

---

## Scope of this contract

**Built now: `mfds_samd` and `mfds_cosmetic` only** — the two Phase 1 gated cells.

References to EU, FDA and NMPA sources throughout this document are **commentary, not work items**.
They are recorded so the contract is designed wide enough to accept those cells later, but no EU,
FDA or NMPA connector, canonicalization profile or parser is in scope yet. ~~EU SaMD is a non-gated
Phase 1 spike (development-plan.md § 5) whose only deliverable is a findings memo;~~ FDA and NMPA
arrive in Phase 2.

**Schedule note, 2026-08-24:** the EU SaMD spike was deferred to **Phase 4** with both EU cells and
never run. This changes nothing in this ADR — EU was already commentary rather than a work item —
but the sentence above would otherwise read as a live Phase 1 deliverable. See
[plan/README](../plan/README.md) § decisions.

Where a decision below is driven by a non-MFDS example, treat the example as a design constraint to
honour, not a component to build.

## Context

Two of the six Phase 1 gates are owned entirely by this layer: **detection coverage ≥ 95%** and
**detection latency ≤ 24h**. Neither is a retrieval or generation problem — they are won or lost in
how sources are polled, hashed, and diffed. A third gate (citation accuracy) depends on this layer
producing correctly versioned clauses to cite.

The source registry is `docs/import-source-map.md` (CLAUDE.md § Architecture rules). This ADR
defines what a connector does with an entry in it.

## Pipeline

Five stages, each idempotent and independently resumable. A worker commits incrementally so a
retry skips completed rows (`.claude/skills/service-endpoint` § Celery).

```text
  fetch ──→ archive ──→ parse ──→ diff ──→ emit
    │          │           │        │        │
  bytes +   sha256      clauses  ClauseDiff  ChangeEvent
  headers   WORM blob      +     per path    per claiming cell
  (+ published_at        effective_date
   where exposed)      (from 부칙 / entry-into-force article)
    │
    └─ fetch_observation recorded on EVERY attempt, changed or not
```

Note `effective_date` is a **parse** output, not a fetch output — it lives in the document text, not
in HTTP metadata. See decision 5.

## Decisions

### 1. Connectors fetch; they do not parse

A connector's whole job is `Source → [FetchedArtifact{bytes, content_type, http_status, fetched_at,
source_url, publisher_timestamp?}]`. Parsing lives in the parser profile keyed by cell.

Splitting them keeps the count linear rather than multiplicative: fetching MFDS RSS and fetching
EUR-Lex are different problems; parsing 화장품법 and 의료기기법 is the *same* problem (ADR-0002
decision 3). Fusing them would push domain knowledge into the fetch layer and break the shared
pipeline.

### 2. Change detection is hash-first, and the hash is over a **canonicalized** body

Naive `sha256(response_bytes)` is useless for HTML: nav chrome, session tokens, "last viewed"
timestamps and rotating banners change on every request, so every poll looks like an amendment. That
single mistake would bury the detection-coverage gate in false positives on day one.

Each parser profile supplies a **canonicalization step** applied before hashing: select the content
region, drop volatile elements, normalize whitespace and encoding. `content_hash = sha256(canonical
bytes)`. The raw response is still archived unmodified — canonicalization is for change detection
only, never for what gets stored or cited.

- `content_hash` unchanged → record a `fetch_observation`, stop. No version, no parse, no diff.
- `content_hash` changed → new `DocumentVersion`, then parse → diff → emit.

### 3. Every fetch is recorded, including the ones that found nothing

`fetch_observation(source_id, fetched_at, http_status, content_hash, connector_version)` is written
on **every** attempt.

This is not logging. Detection coverage is measured by a quarterly retrospective audit
(development-plan.md § 5) that asks "did the system see amendment X?" — answerable only if
"we checked source S at time T and it was unchanged" is a stored fact. It also distinguishes *we
missed it* from *we never looked*, which are different failures with different fixes.

### 4. Poll interval is derived from the source's block, not hand-set per source

`import-source-map.md` orders blocks by ingestion priority (Primary Laws first, Official Sources
last). Interval is a function of that block plus tier, so adding a source inherits a sane cadence
instead of requiring a scheduling decision:

| Block | Interval | Rationale |
|---|---|---|
| Primary Laws, Annexes & amending acts | daily | Where legal change actually lands |
| Regulations, Registration | daily | |
| Guidance | weekly | Changes a few times a year |
| Safety (recalls, alerts, warning letters) | daily | Time-sensitive by nature |
| Standards (Tier D) | monthly | Metadata only — recognition lists move slowly |
| Official Sources (portals) | weekly | Navigation surfaces, not content |

Overrides are allowed but must be recorded on the source row with a reason.

### 5. Three dates, none substituting for another

A version carries three distinct timestamps. Collapsing any two of them corrupts a gate.

| Field | Source | Always present? | Used for |
|---|---|---|---|
| `retrieved_at` | our clock at fetch | yes | audit trail, latency **upper bound** |
| `published_at` | source metadata — MFDS 공고일, RSS `pubDate` *(later: Federal Register `publication_date`, EUR-Lex OJ date)* | **no** | the detection-latency gate |
| `effective_date` | **extracted at parse time** from the document text — 부칙 "…부터 시행한다" *(later: EU entry-into-force article, FDA effective-date line)* | usually | citations, applicability, alert prioritisation |

> **Amended by [ADR-0016](ADR-0016-pending-effect-versions.md) decision 3.** For `law.go.kr` the
> envelope states 시행일자 outright in `기본정보`, so `effective_date` is taken from there rather
> than re-derived from 부칙 prose — a derivation would be a worse estimate of a published fact. The
> parse stage is still the writer (one writer, and a bad date is fixed by re-parsing); 부칙 supplies
> `effective_date_phrase` and remains the fallback for sources that state no date.

**Do not set `published_at = retrieved_at` as a fallback.** Detection latency is
"authority publishes → owner alerted" (RegOps.md). Using our own fetch time makes latency ≈ our
processing time, so the ≤24h gate passes by construction and measures nothing. Where the source
exposes no publication timestamp, `published_at` stays **null** and latency for that source is
reported as **unmeasurable rather than zero** — an honest gap beats a flattering number.

**`effective_date` is not a substitute either.** Publication and application are routinely years
apart: MDR published 2017 / applied 2021; QMSR published 2024-02-02 / effective 2026-02-02; the EU
AI Act applies to embedded AI from 2028-08-02 with transparency duties from 2026-08-02. Latency
computed against effective date would be negative for anything not yet in force.

**Measuring the gate where `published_at` is null.** `retrieved_at` still bounds it — we detected no
later than that — and the quarterly retrospective audit (development-plan.md § 5) supplies ground
truth: RA looks up the real 공고일 for a sampled amendment and computes true latency. That keeps the
gate scoreable for sources without machine-readable publication dates, without inventing a number
per event.

**Staged application.** Many acts apply in stages by provision, so a single per-version
`effective_date` is insufficient — the EU AI Act example above has two dates in one instrument.
`effective_date` is therefore recorded per version **and** overridable per clause where the text
states a distinct application date. Alerting uses the clause-level date where present.

Daily polling puts the ceiling at 24h + processing. Sources on the critical gates that only expose
weekly cadence cannot meet the gate by polling alone and must be flagged at W1-2, so the gate is
scoped to what is achievable rather than discovered short at M4.

### 6. Structure drift is an operator alert, never a ChangeEvent

For Tier C especially, a site redesign changes everything at once. Emitting that as regulatory
change would generate thousands of false alerts and destroy trust in the monitoring pillar.

The parse stage fails closed on drift signals — zero clauses extracted, clause count changed beyond
a threshold, or the expected root selector missing. It raises a `structure_drift` alert against the
source, does **not** create a version, and does **not** emit change events. A human confirms whether
the regulation changed or the page did.

This is the mitigation the risk register already names ("source instability"); Phase 1 builds the
hook even though Tier C arrives in Phase 2.

### 7. Non-ingestible sources are unfetchable by construction

`sources.ingestible = false` for login-gated portals *(EU CPNP and EUDAMED — commentary, neither is
in Phase 1 scope)* and for Tier D. The
scheduler skips them and the connector API rejects them — a Tier D source has no code path that
could write body text, matching ADR-0002 decision 2.

Tier D freshness is tracked through the recognition/harmonized **list** (an ingestible Tier B page),
which yields `StandardReference` metadata. The standard itself is never fetched.

### 8. Emission fans out to every claiming cell

A `ClauseDiff` produces one `ChangeEvent` per cell claiming the document (ADR-0002 decision 1) — an
FD&C Act amendment reaches both `fda_samd` and `fda_cosmetic` subscribers. Routing from there to
product profiles is defined in [ADR-0007](ADR-0007-context-map-and-applicability.md) decision 8:
ChangeEvent → citing IRs → applicability entries → owning tenant.

Severity grading is deferred: Phase 1 emits ungraded events and measures whether they are *complete*
and *timely*. Grading quality is a Phase 2 concern once there is a corpus to calibrate against.

### 9. Politeness is part of the contract

Per-host concurrency cap, exponential backoff with jitter on 429/5xx, honour `Retry-After`,
identify with a contactable User-Agent, cache-validate with `ETag`/`If-Modified-Since` where offered
(a 304 is the cheapest possible `fetch_observation`).

Not optional courtesy: these are government hosts, and Phase 3 sells to customers who will ask how
we collect. Getting rate-limited off MFDS during the pilot would take out two gated cells at once.

### 10. Attachments are fetched as first-class artefacts, not skipped

*(Added after the [source reconnaissance](spike-2026-07-29-mfds-source-recon.md).)*

The substantive obligations of the Cosmetic cell — the prohibited and restricted ingredient lists in
화장품 안전기준 등에 관한 규정 — live in 별표, not in the body's prose clauses.

> **Revised after the live API test (2026-07-29).** The 별표·서식 *목록* API returns metadata and
> file links only, but **행정규칙 본문조회 returns `<별표단위>` with `<별표내용>` inline** — the annex
> text arrives in the same response as the body. **HWP/PDF extraction is therefore not on the Phase 1
> critical path**, which reverses this decision's original premise. The file links
> (`별표서식파일링크`, `별표서식PDF파일링크`) remain useful as an archival copy and a fallback where
> `별표내용` is empty, but they are not the ingestion route.

A connector therefore returns a body artefact **plus zero or more attachment artefacts**, each
archived, hashed and versioned independently. An annex that changes while its parent body does not
must still produce a `ChangeEvent` — hashing only the body would silently miss every ingredient-list
amendment, which for `mfds_cosmetic` is most of what matters.

> **Amended by [ADR-0012](ADR-0012-annex-version-identity.md).** "Versioned independently" and the
> `attachments(document_version_id, …)` sketch below contradict each other: a child row of a version
> cannot out-version its parent. An annex is a child `Document` with its own `document_versions`;
> `attachments` keeps the narrower job of recording the authority's own file links.

HWP is a Korean proprietary format with thin library support; treat extraction as a workstream, not
a library call.

### 11. MFDS sources are discovered by API, not only curated by hand

The 행정규칙 목록 API filters by `소관부처` (`org`), so every MFDS 고시 can be **enumerated** rather
than hand-listed.

`import-source-map.md` stays the curated registry of what we *intend* to cover, but for MFDS a
scheduled discovery sweep reconciles it against the authority's own list and raises an alert on
anything present upstream and absent locally. A hand-maintained list silently caps detection
coverage at whatever someone remembered to add — the discovery sweep converts that from an unknown
into a measurable delta.

> **First live sweep, 2026-08-03.** `org=1471000` (식품의약품안전처) returns **511 행정규칙**, of
> which **72** name 화장품 / 의료기기 / 디지털의료제품 and **6** are covered. The delta this decision
> was written to expose is therefore real and large; see
> [phase1.0](../plan/phase1.0_ingestion.md) § Risks.
>
> Two properties the sweep needs to stay usable:
>
> - **A relevance filter is mandatory, not a refinement.** Most of the 511 are 식품 and
>   건강기능식품, which belong to no RegOps cell. Reporting all of them would be ~500 false
>   positives and the sweep would be muted within a week. The filter is deliberately
>   over-inclusive — a 고시 missed because the filter was clever is a coverage hole, one wrongly
>   listed costs a glance — and the unfiltered total is recorded next to the filtered one so the
>   narrowing is visible rather than silent.
> - **Titles are compared normalized.** The catalog and the authority differ on 중점 (`·` vs `ㆍ`)
>   and spacing without naming a different instrument; comparing raw would manufacture gaps.
> - **"Over-inclusive" needs a standing check, because a regulation can govern a domain without
>   naming it.** *(Added 2026-08-06.)* Title matching cannot see those by construction, so the
>   claim above is untestable from inside the filter. `scripts/admrul_triage.py` tests it from
>   outside: it re-buckets the 511 and reports the ones a *wider* net catches that the production
>   keywords miss. Its first run found two genuine misses — 의약품등의 타르색소 지정과 기준 및
>   시험방법 (a cosmetic colorant standard) and 인체적용제품의 위해성평가에 관한 규정 (the statutory
>   category covers 화장품 **and** 의료기기) — both now in `DISCOVERY_KEYWORDS`, taking the in-scope
>   count from 72 to **74**. Each candidate term is measured against the live list before being
>   added; `이물`, `부작용`, `원료` and `의약외품` were rejected on that evidence.
> - **Over-inclusive still needs a way to say no, and it has to be a *negative* list.** The keywords
>   are substrings, so 체외진단의료기기 matches 의료기기 however the positive list is written — no
>   edit to it can put IVD out of scope. `DISCOVERY_EXCLUSIONS` does, and exclusion beats inclusion
>   in `cells_for()`. 11 고시 are excluded by decision (2026-08-06), taking in-scope 74 → **63**;
>   the rationale lives in `import-source-map.md`, since scope is a catalog question. Excluded rows
>   stay **visible** in the coverage report under their own bucket: *seen and rejected* and *never
>   seen* are different states, and a filter that silently drops the first is how a scope decision
>   becomes folklore.

### 12. Use the authority's own change history as an independent check

`법령 변경이력 목록`, `일자별 조문 개정 이력` and **`조문별 변경 이력`** APIs exist. Where a source
offers them, reconcile our computed `ClauseDiff` against the authority's record.

This is free ground truth for the detection-coverage gate and turns the quarterly retrospective
audit from a manual sample into a continuous cross-check for `law.go.kr` sources. It does **not**
replace our own diff: their granularity and timing are outside our control, and the citation
contract requires diffs against versions we archived ourselves.

### 13. Source credentials live in settings, and never reach a stored URL

Some sources authenticate. 국가법령정보 OPEN API takes an `OC` key — **self-designated by the
account holder**, confirmed under 마이페이지 → API인증키관리 — passed as a **query-string
parameter**.

- The key lives in environment settings (`LAW_GO_KR_OC`), never in `import-source-map.md`, never in
  a `sources` row, never in an ADR or fixture. `.env.example` carries the name with an empty value.
- `sources.url` stores the **URL template** with a credential placeholder. The resolved URL is built
  at request time and is never persisted.
- `fetch_observations` records `source_id`, status and hash — **not the resolved request URL**. Any
  connector logging must redact credential parameters before emitting.

The audit trail is append-only and outlives any key rotation; a credential written into it cannot be
cleaned up, and Phase 3 exports it to customers. Because the key is user-chosen rather than issued,
it is also likelier to be low-entropy and reused — one leak is enough.

Applies to any authenticated source, not just this one; treat it as the default connector contract.

> **The credential also arrives inbound.** *(Added 2026-08-03, from the first live sweep.)*
> 국가법령정보's **목록** endpoints echo the `OC` parameter back inside the response body:
> `행정규칙상세링크` on every row is a fully-formed URL containing the key. So the outbound rules
> above are necessary but not sufficient — a response we never logged and never built a URL from
> can still carry the credential.
>
> Two structural consequences, both implemented:
>
> - **The WORM archive refuses any payload containing a configured source credential.** Not
>   redaction: the archive stores the raw response *unmodified*, so there is no variant that keeps
>   the evidence intact and the key out. The check sits inside `archive_bytes` rather than at its
>   call sites, so no future caller can omit it.
> - **The discovery sweep's row model has no link field.** `source_discovery_runs.details` is
>   persisted JSON; the safe design is one where the credential-bearing value is never carried far
>   enough to be written, mirroring `fetch_observations` having no request-URL column.
>
> The 본문조회 endpoints do **not** echo it — verified against all 13 archived documents. Only the
> 목록/검색 responses do, which is why the sweep consumes them in memory and archives nothing.

## Schema additions to ADR-0002

```sql
fetch_observations(id, source_id, fetched_at, http_status, content_hash,
                   connector_version, published_at, notes)
source_schedules(source_id, interval, next_due_at, override_reason)
structure_drift_alerts(id, source_id, detected_at, signal, expected, actual, resolved_at)
attachments(id, document_version_id, kind, title, ordinal, file_format,
            source_url, content_hash, raw_object_key)   -- file links only; see ADR-0012
source_discovery_runs(id, authority, ran_at, upstream_count, matched, unmatched)  -- dec 11
```

`document_versions` gains `content_hash`, `retrieved_at`, `published_at` (nullable),
`effective_date` (nullable, parse-derived), `fetch_observation_id`.

`clauses` gains `effective_date` (nullable) — set only where the text states an application date
distinct from the version's, for staged-application instruments.

## Open questions

1. ~~**Canonicalization per profile is where the effort actually goes**~~ — **downgraded** by the
   [source reconnaissance](spike-2026-07-29-mfds-source-recon.md). `law.go.kr` HTML is JS-rendered
   and unscrapable, so the OPEN API is the only path — and it returns 조문/항/호/목 as separate
   structured fields, meaning **no canonicalization at all** for the largest Phase 1 source.
   It is needed only for MFDS listing pages, where `조회수` (view count) is confirmed as the volatile
   element, and RSS may remove even that. Low risk for Phase 1; **unknown for Phase 2**, where
   EU/FDA/NMPA templates are untested.
2. ~~**Publication timestamps on MFDS sources**~~ — **closed** by the
   [source reconnaissance](spike-2026-07-29-mfds-source-recon.md). The 법령 API returns `공포일자`,
   `시행일자` and **`조문시행일자`**; the 행정규칙 API returns `발령일자`, `발령번호`, `시행일자`.
   Per-event latency is measurable for both gated cells. ~~`조문시행일자` and `별표시행일자문자열`
   also confirm decision 5's clause-level `effective_date` override matches how the authority itself
   models staged application.~~ *(EU and NMPA equivalents: still deferred.)*

   > **That last sentence is withdrawn** ([ADR-0016](ADR-0016-pending-effect-versions.md)).
   > `조문시행일자` is present per clause but **constant within a document** — measured across all
   > nine gated 법령, it always equals the document's own 시행일자, so it restates the snapshot date
   > rather than overriding it. The authority models staged application through separate consolidated
   > snapshots of one MST plus 부칙 prose whose dates are conditional on the *addressee*. Decision 5's
   > clause-level override stays in the schema on its own merits — the EU AI Act case is real — but
   > not on this evidence.
3. ~~**Effective-date extraction reliability**~~ — **closed** by
   [ADR-0013](ADR-0013-unresolvable-effective-dates.md): `effective_date` stays NULL when the text
   states a condition rather than a calendar date, and the raw 부칙 phrase is retained in
   `effective_date_phrase`. A computed date is never written into the column that forms part of the
   Citation tuple, because there it would be indistinguishable from an authoritative one.
4. ~~**Diff synchronously or async?**~~ — **closed** by
   [ADR-0015](ADR-0015-diff-stage-boundary.md): split, as this question leaned. `parse` and `diff`
   are separate tasks chained by name, so a corrected profile is applied by re-enqueueing over the
   WORM archive without re-fetching, and a diff-stage defect can no longer prevent clauses from
   being committed at all. Emission stays inside `diff`.
5. **Drift thresholds** — clause-count delta is a crude signal. Needs calibration against real
   amendment sizes; a large genuine amendment must not read as drift.

   > **Set to 0.5 in phase 1.1, reasoned rather than measured.** The threshold is deliberately
   > loose because the errors are asymmetric: a rejected parse creates no version and emits no
   > change event, so a *missed amendment* is invisible to the detection-coverage gate, while a
   > *missed drift* is caught by the zero-clause signal and by the next poll.
   >
   > **First real measurement, 2026-08-06.** 시행예정 ingestion produced the amendment pairs this
   > question needed. Seven consecutive-version pairs across three 법령:
   >
   > | | clause delta |
   > |---|---|
   > | 화장품법 20901 → 21525 | **+9.4%** (351 → 384) |
   > | 화장품법 21525 → 21709 | +1.6% |
   > | 화장품법 21709 → 21302 | −1.5% |
   > | 화장품법 21302 → 21604 | +1.3% |
   > | 의료기기법 21525 → 21775 | +0.8% |
   > | 의료기기법 21263 → 21525 · 디지털의료제품법 20139 → 21525 | 0.0% |
   >
   > So the largest genuine amendment moves the count **9.4%**, and 0.5 sits 5.3× above it. The
   > signal has never fired: 533 versions parsed, zero `clause_count_delta` alerts.
   >
   > **Still open, and now for a sharper reason than "no data".** The sample cannot support
   > tightening:
   >
   > - **It covers 3 documents.** 527 of 530 have exactly one version — every 고시 and every 별표
   >   included — so the threshold is untested against 99% of the corpus, and annex clause counts
   >   behave nothing like 조문 counts.
   > - **No 전부개정 or 폐지제정 in the sample.** Those are precisely the amendments that can double
   >   or halve a document, and they are what a tightened threshold would start rejecting.
   > - **No drift event has occurred**, so the other side of the trade is still unobserved.
   >
   > Tightening on n=7 with the large-amendment case absent would be overfitting to a quiet quarter.
   > What the measurement *does* justify is a question for the next revision: **should the threshold
   > be asymmetric?** A parser break collapses a count; a 전부개정 grows it. A strict floor on
   > shrinkage with a loose ceiling on growth would fit both failure shapes better than one ratio —
   > decide it in phase 1.6 against the evaluation corpus, not here.

## What this unblocks

W1-2 connector data contracts and W3-4 first connectors. Next: IR extraction and domain branching
(where the ADR-0002 architecture bet gets tested), then retrieval and citation-enforced generation.
