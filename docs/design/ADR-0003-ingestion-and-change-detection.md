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
FDA or NMPA connector, canonicalization profile or parser is in scope yet. EU SaMD is a non-gated
Phase 1 spike (development-plan.md § 5) whose only deliverable is a findings memo; FDA and NMPA
arrive in Phase 2.

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
FD&C Act amendment reaches both `fda_samd` and `fda_cosmetic` subscribers. Routing to product
profiles sits above this and is out of scope here.

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

The 별표·서식 API returns **metadata and file links only** — annex content arrives as **HWP or PDF
attachments**, with their own `별표시행일자`. The substantive obligations of the Cosmetic cell (the
prohibited and restricted ingredient lists in 화장품 안전기준 등에 관한 규정) live in exactly these
annexes.

A connector therefore returns a body artefact **plus zero or more attachment artefacts**, each
archived, hashed and versioned independently. An annex that changes while its parent body does not
must still produce a `ChangeEvent` — hashing only the body would silently miss every ingredient-list
amendment, which for `mfds_cosmetic` is most of what matters.

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

## Schema additions to ADR-0002

```sql
fetch_observations(id, source_id, fetched_at, http_status, content_hash,
                   connector_version, published_at, notes)
source_schedules(source_id, interval, next_due_at, override_reason)
structure_drift_alerts(id, source_id, detected_at, signal, expected, actual, resolved_at)
attachments(id, document_version_id, kind, title, ordinal, file_format,
            source_url, content_hash, raw_object_key, effective_date)   -- 별표·서식 (dec 10)
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
   Per-event latency is measurable for both gated cells. `조문시행일자` and `별표시행일자문자열` also
   confirm decision 5's clause-level `effective_date` override matches how the authority itself
   models staged application. *(EU and NMPA equivalents: still deferred.)*
3. **Effective-date extraction reliability** — 부칙 phrasing varies ("시행한다", "적용한다",
   "…이후 최초로 …하는 분부터"), and conditional or event-triggered application dates ("공포 후 6개월")
   cannot be resolved to a calendar date at parse time. Decide whether such cases store null with the
   raw phrase retained, or a computed date with a confidence flag. Null-plus-phrase is safer for
   citations; a computed date is more useful for alert prioritisation.
4. **Diff synchronously or async?** Parsing then diffing inline is simpler; splitting them lets a
   re-parse with an improved profile re-diff historical versions without re-fetching. Leaning split,
   but it costs a stage boundary.
5. **Drift thresholds** — clause-count delta is a crude signal. Needs calibration against real
   amendment sizes; a large genuine amendment must not read as drift.

## What this unblocks

W1-2 connector data contracts and W3-4 first connectors. Next: IR extraction and domain branching
(where the ADR-0002 architecture bet gets tested), then retrieval and citation-enforced generation.
