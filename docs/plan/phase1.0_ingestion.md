# Phase 1.0 — Ingestion

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W1–W4 · **Status:** 🟢 **done (2026-08-05)** — 8/8 acceptance criteria, W3 reconnaissance complete. Three items transferred, named in *Deviations*
- **Governed by:** [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md), [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decisions 1 · 6, [import-agent.md](../import-agent.md)
- **Decided here:** [ADR-0012](../design/ADR-0012-annex-version-identity.md) (annex version identity), [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) (unresolvable effective dates)
- **Depends on:** [phase0](phase0_foundation.md)
- **Service:** `regulation` (L1)

---

## Goal

Fetch the two gated cells reliably and prove the fetch is auditable: a source was checked at time T,
and either nothing changed or a new immutable version exists. Everything downstream reads from the
archive, never from the network.

Gated cells are **MFDS SaMD + MFDS Cosmetic** — same regulator, both domains. Both are Tier A
(국가법령정보 OPEN API, MFDS RSS), so ingestion is deliberately off the critical path for a
trust-metric PoC.

## Scope

**In:** Tier A/B connectors for the two gated cells, WORM archive, change-detection scheduler,
source registry seeded from the catalog.

**Out:** Tier C scraping (phase 2.0). Parsing and clause segmentation (phase 1.1) — this phase stops
at "bytes are archived and a version row exists."

## Tasks

### Source registry

- [x] `sources` seeded from [import-source-map.md](../import-source-map.md) for both gated cells — read the catalog, never copy it into code comments
- [x] `url_template` holds a credential **placeholder**, never a resolved URL ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 13)
- [x] `tier` and `ingestible` flags carried through; Tier D rows carry no fetch path at all
- [x] `source_schedules` driving the beat. **Interval is derived from the source's block + tier, never hand-set per source** ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 4); an override is allowed but must be recorded on the source row with a reason — one override exists, on the recognition list (deviation 3)

### Tier D — `StandardReference`, metadata only

- [x] `standard_references(number, edition, issuing_body, recognition_number, effective_date, withdrawal_date, status, official_url)` — **no `DocumentVersion`, no body text, and no column body text could occupy** ([ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 2). No `text` column and no varchar over 512; `tests/unit/test_tier_d.py` fails if one is added
- [x] Recognition-list connector — Tier D freshness is tracked through the recognition/harmonized **list**, which is an ingestible Tier B page ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 7). The standard itself is never fetched
- [x] Seed from the `Standards` block of `mfds_samd` (IEC 62304 관련 가이드, GMP) — the source map already marks it metadata-only
- [x] **Recognition list — there is no MFDS one.** W3 recon: the guessed URL (`m_211`) is 고시전문, and neither 의료기기 기준규격 nor the GMP 고시 names a single IEC/ISO identifier. Korea has no FDA-style Recognized Consensus Standards database; the connector was built against an FDA-shaped assumption and stays for Phase 2. The Tier D row keeps what it always had — metadata, no fetch path

### Connectors

- [x] **국가법령정보 OPEN API key** — in hand, and the first live fetch succeeded 2026-08-03
- [x] 국가법령정보 OPEN API — 법령 본문조회 for 화장품법 and 의료기기법 (plus 시행령 · 시행규칙 · 디지털의료제품법)
- [x] 행정규칙 본문조회 for 고시, including `<별표단위>` / `<별표내용>`
- [x] Polite fetch: contactable `User-Agent`, `ETag` / `If-Modified-Since`, exponential backoff with jitter, `Retry-After`, per-host minimum interval
- [x] The three HTTP-200 failure signatures detected explicitly — unregistered egress IP, ungranted scope, and `success` with `totalCnt 0`
- [x] **MFDS RSS — confirmed and enabled.** `https://www.mfds.go.kr/www/rss/brd.do?brdId={brdId}`; 35 boards mapped by fetching each and reading the channel title it declares. Four seeded: `data0008` 제개정고시등, `data0003` 법·시행령·시행규칙, `data0009` 입법/행정예고, `plc0168` 의료기기 행정처분. Closes spike still-open question 3
- [x] **제개정고시등 — superseded by RSS, not scraped.** The same board is published as `data0008` with a `pubDate` per item and no `조회수` to strip, so the HTML scrape buys nothing. The listing connector and its `조회수` canonicalization stay built and tested — phase 2.0's Tier C work needs exactly that shape
- [x] **Attachment pipeline** — `attachments` records 별표서식파일링크 / 별표서식PDF파일링크 per version as archival copy and fallback. **HWP/PDF extraction is not needed for ingestion**: `<별표내용>` arrives inline, confirmed live on 116 annexes across both cells ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 10 as revised). Binary archival is opt-in per source and off by default
- [x] Annexes hashed and versioned **independently of the parent body** — as child `Document`s ([ADR-0012](../design/ADR-0012-annex-version-identity.md)), not as rows on a version

### WORM archive

- [x] Content-addressed `raw_object_key = sha256(raw bytes)` in MinIO; write-once, never mutated. The raw response is archived **unmodified** — this is what gets cited
- [x] **`content_hash = sha256(canonicalized body)` is a second, separate hash, and it is the one change detection keys on**
- [x] Canonicalization step per connector — NFC, line endings, whitespace; volatile fields dropped. Per [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 1 the 법령/행정규칙 OPEN API needs a stable serialization but no chrome-stripping; the MFDS listing drops `조회수`
- [x] Unchanged `content_hash` records a `fetch_observation` and creates **no** new version — verified live over 13 sources
- [x] Changed `content_hash` creates a `DocumentVersion` and enqueues parse (phase 1.1 stub); diff → change event is 1.1
- [x] `document_cells` M:N — a document is ingested once and claimed by one or more cells

### Dates & scheduling

- [x] Three separate dates: `retrieved_at`, `published_at`, `effective_date` — none substituting for another ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5). `published_at` comes from 공포일자 / 발령일자 and is populated on all 13 live sources
- [x] **[ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 3 decided → [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md).** Null plus the retained raw 부칙 phrase; never a guessed date in the Citation tuple
- [x] Celery beat on the `regulation` queue; incremental commit so a retry skips completed rows

### Test environment (carried over from [phase0](phase0_foundation.md))

- [x] Separate test database — `regops_test`, created by `infra/postgres/init/02-test-db.sh`, migrated to head, selected by `REGOPS_DB_NAME`
- [x] `.env.test` created (by a human — the `guard_env` hook blocks the agent from writing any `.env.*`, correctly). Verified end to end: `STAGE=test REGOPS_DB_NAME=regops_test docker compose run --rm regulation python -m pytest tests/unit tests/integration -q` → 118 passed against `regops_test` from a clean container
- [ ] **Blank `LAW_GO_KR_OC` in `.env.test`.** It currently carries the live key. No test path calls out — every suite uses `StubFetcher` — so this is a latent risk rather than an active one, but a blank key is what makes "a test run cannot reach a government host" true by construction instead of by convention

### Reconnaissance follow-ups (W3, from the [MFDS spike](../design/spike-2026-07-29-mfds-source-recon.md))

- [x] Confirm 본문조회 returns annex text via `<별표단위>` — **re-verified with the live key 2026-08-03.** 116 annexes across 13 documents, including 화장품 안전기준's 별표 1 (사용할 수 없는 원료) and 별표 2 (사용상의 제한이 필요한 원료)
- [x] **소관부처 code for 식품의약품안전처 = `1471000`** — verified live: 511 행정규칙 returned, all with `소관부처명 = 식품의약품안전처`. Lives in `regops_shared.constants.MFDS_ORG_CODE`, **not** in `.env`: it is a public identifier, and a gitignored file is where a reviewable constant goes to become invisible
- [ ] Confirm 조문별 변경이력 granularity matches `ClauseDiff` — **transferred to [phase1.1](phase1.1_normalization.md)**, which owns `ClauseDiff` and is the only place the answer can be acted on
- [x] **Source discovery sweep** — `regulation.discover_sources`, weekly on the beat, writing `source_discovery_runs`. Relevance-filtered per cell and title-normalized so 중점/spacing differences do not read as gaps. Ran live; result in Risks below

### ~~EU SaMD spike (non-gated, W3 → W12)~~ — moved to Phase 4, 2026-08-24

**Never run, and no longer carried.** The whole EU group (`eu_samd` + `eu_cosmetic`) moved beyond
Phase 3 ([plan README](README.md) § decisions). The spike's purpose was to meet a second authority
cheaply *before* one was gated; the FDA reconnaissance
([spike-2026-08-24](../design/spike-2026-08-24-fda-source-recon.md)) spent that purpose instead.

- ⛔ ~~EUR-Lex fetch for MDR (EU) 2017/745 at reduced depth~~ — Phase 4
- ⛔ ~~Record multilingual and Tier C effort for the Phase 2 estimate~~ — the estimate it fed is gone
  with the slice; multilingual now arrives with NMPA in 2.0c

## Acceptance criteria

- [x] Both gated cells fetch on schedule with zero manual steps — 13 sources, beat-driven, verified live
- [x] An unchanged re-fetch produces a `fetch_observation` and **no** new `DocumentVersion` — verified by integration test **and live**: a second round over all 13 sources recorded 13 `unchanged` observations and left the version count at 214
- [x] A changed source produces exactly one new version and enqueues downstream work
- [x] Annexes version independently: amending 별표 2 alone creates a version for the annex and not the body — integration test `test_amending_one_annex_versions_only_that_annex`
- [x] No credential appears in `sources`, logs, or fixtures — `fetch_observations` has no column a request URL could occupy, and `redact_url` covers every credential parameter
- [x] Re-fetching an MFDS listing page whose only delta is `조회수` produces **no** new version — `test_view_count_delta_is_not_a_change`, with `test_a_real_edit_still_registers` as its counterpart
- [x] No Tier D bytes reach the archive — CI scan green (179 files)
- [x] A Tier D source has no code path that can write body text: the connector API rejects it, the recognition-list connector returns metadata with `artifacts=()`, and `standard_references` has no column to hold it — structural, not just the CI scan

## Risks & open questions

- ~~**API key on the critical path**~~ — **closed.** Key in hand; first live fetch 2026-08-03 returned 200 on all 13 enabled sources. The account is authorised by **egress IP**, so this reopens on any change of network — that failure returns HTTP 200 with an error body, which the connector detects and files as an `auth_failure` drift alert rather than a healthy observation.
- ~~**HWP extraction is the most likely schedule surprise**~~ — **closed.** `<별표내용>` arrives inline on both 법령 and 행정규칙 responses; no HWP or PDF parsing is on the Phase 1 path. The file links are recorded as a fallback for the case where `별표내용` comes back empty, which has not yet been observed.
- ~~**Three MFDS surfaces are seeded disabled**~~ — **closed by the W3 reconnaissance (2026-08-05).** RSS is confirmed and enabled on four boards; the 제개정고시등 listing is superseded by one of them; the recognition list does not exist for MFDS. Every fetchable source is now enabled — the only disabled rows are the three reference-only portals, which have no connector at all.
- 🔴 **We only see 현행, so an amendment is invisible from 공포 until 시행.** Measured live 2026-08-03 across the 9 gated 법령: **8 amendments are already 공포'd and unseen**, the oldest promulgated 2025-12-30 — seven months earlier. Detection latency for those is 시행 − 공포, between **2 months and 2.4 years**, which makes the ≤24h gate structurally unmeetable rather than merely unmet. Fetching is 1.0's job and nothing downstream can recover latency that ingestion never had.

  **Deferred to [phase1.1](phase1.1_normalization.md) by decision (2026-08-03)**, where diff and `effective_date` land anyway and the work is done once. The tasks and the measured numbers are recorded there, including the two findings that shape the design: a version is one **MST**, not one 시행일자 (화장품법 has 6 pending rows but 4 distinct MST), and an act with several 시행일자 is staged application belonging at clause level via `조문시행일자`. **Until it ships, detection latency for the 법령 sources is not measurable** — say so in the M4 report rather than quoting a number the pipeline cannot produce.

- 🟢 **CLOSED 2026-08-06 — the catalog now covers 59 of 59 in-scope MFDS 고시.** 53 added, 15 ruled out by decision, 0 candidates outstanding; see [mfds-admrul-coverage.md](../mfds-admrul-coverage.md). The original finding, kept because it is the evidence the gate was measured against:

  🔴 **The catalog covers 6 of 72 in-scope MFDS 고시.** First live discovery sweep, 2026-08-03: 511 행정규칙 upstream, **72** naming 화장품 / 의료기기 / 디지털의료제품, **6 matched, 66 unmatched.** This is not a defect in the sweep — it is the number [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 11 was written to expose, and it is the first honest read on the ≥95% detection-coverage gate. Notable absences include 기능성화장품 기준 및 시험방법 and the entire 디지털의료제품법 family (7 고시, most amended within the last year). 우수화장품 제조 및 품질관리기준 (CGMP) also appears in the unmatched list but is ~~**out of scope by decision** — the cosmetic `GMP` block was removed from the catalog on 2026-08-03~~ — **reversed 2026-08-06: CGMP is in scope and is now ingested**, under Cosmetics → Regulations so it polls daily rather than on the `GMP` block's 7-day interval. Worth noting *how* the reversal nearly did not happen: the 2026-08-03 decision lived only in this paragraph, so nothing enforced it and CGMP kept surfacing as a candidate. A decision recorded in prose is a decision the pipeline cannot keep — scope decisions now live in `DISCOVERY_EXCLUSIONS` with the catalog carrying the rationale.

  Re-measured after the W3 reconnaissance: **still 6 of 72.** The new RSS boards are change *signals*, not 행정규칙, so they improve detection *latency* rather than coverage — closing this gap is RA triage of the catalog, and nothing technical will move the number.

  The unmatched rows are an **over-inclusive triage list, not a work queue**: some are genuinely out of scope even inside the filter (범부처 연구개발사업 운영관리규정, 소비자의료기기감시원 운영 규정). **Next action is RA triage** — decide which belong in `import-source-map.md`, then re-seed. That is a catalog decision, not a code change, which is exactly where it belongs.

  **Now 6 of 63, and the worklist is generated (2026-08-06).** [mfds-admrul-coverage.md](../mfds-admrul-coverage.md), from `scripts/admrul_triage.py`, replaces reading the sweep's JSON by hand — and it reports two buckets the sweep cannot.

  *Filter misses:* its first run found two real ones, now in `DISCOVERY_KEYWORDS` — 의약품등의 타르색소 지정과 기준 및 시험방법 and 인체적용제품의 위해성평가에 관한 규정. Neither names 화장품 or 의료기기, because **a regulation can govern a domain without naming it**; that is the limit of title matching and why the check is standing rather than one-off. 72 → 74.

  *Scope decisions:* 11 고시 ruled out — 체외진단의료기기 (8, a separate statute absent from Primary Laws), the 범부처 R&D-programme rules (2), 소비자의료기기감시원 운영 규정 (1). 74 → **63**. This is the first movement on the two items this risk already named as "out of scope even inside the filter". They keep their own bucket in the report rather than disappearing, so the decision stays revisitable. The remaining 57 are still RA triage.
- 🔴 **A day the poller did not run leaves no trace, and detection coverage cannot tell that from a
  quiet day.** Observed 2026-08-05: `fetch_observations` has 28 rows on 08-03 and 16 on 08-05, and
  **nothing at all on 08-04** — the stack was down. `advance()` moves `next_due_at` forward from
  *now* rather than from the missed due time, which is deliberate (a source that was down for a day
  must not fire a day of catch-up polls at a host that has just proven fragile) and is not the
  problem.

  The problem is that [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 3
  writes an observation on every *attempt*, so it separates "we missed it" from "we never looked" —
  but there is a third state it does not capture: **we never looked and nothing records that we
  should have.** Coverage computed over observations therefore divides by the polls that happened,
  not the polls that were due, and downtime silently improves the number. That is the wrong
  direction for a gate that is meant to be falsifiable.

  Partially detectable live — `next_due_at` versus now shows a source overdue by N intervals at any
  instant — but **not reconstructable after the fact**, because the beat advances the schedule on
  recovery and the skipped intervals leave nothing behind. Measurement belongs in
  [phase1.6](phase1.6_evaluation.md), not here; the fix is to score coverage against *scheduled*
  polls rather than observed ones.

- 🟡 **The archive only ever grows, and nothing defines what happens to an unreferenced object.**
  Observed 2026-08-05: 2 of 17 objects in the dev bucket are referenced by no `document_versions`
  row, left by a truncate-and-re-ingest during this build. That is the WORM contract working, not a
  defect — deleting a row must not delete the evidence. But it also means a Tier D document archived
  by mistake **cannot be removed**, and the four structural Tier D guards make that unlikely rather
  than impossible. Harmless at 2 objects and a few MB; it needs a decision before the archive holds
  anything a rightsholder or customer can compel action on. Recorded as
  [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) open question 5; not Phase 1 work.
  Reconcile with:
  `select count(*) from document_versions` versus the bucket listing — the two are not expected to
  match, and the gap is the thing to watch rather than to zero out.

- **ADR-0002 open question 3** — `canonical_key` derivation. Answered for MFDS by construction: identity comes from the 법령ID / 행정규칙ID the response returns, so querying by 법령명 does not weaken it. EU ELI, FDA CFR citation and NMPA remain deferred.

## Deviations & decisions

<!-- Architecture changes go in an ADR, linked here. -->

**1. Annexes are child Documents, not attachment rows → [ADR-0012](../design/ADR-0012-annex-version-identity.md).**
[ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 10 requires annexes to be
"versioned independently" but sketches them as `attachments(document_version_id, …)`. Writing the
migration surfaced the contradiction: a child row of a version cannot out-version its parent, so the
acceptance criterion "amending 별표 2 alone creates a version for the annex and not the body" was
unsatisfiable as sketched. Annexes are now child `Document`s with their own versions; `attachments`
keeps the narrower job of recording the authority's file links.

**2. Unresolvable effective dates → [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md).**
Null plus the retained raw 부칙 phrase, closing [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md)
open question 3 on its W3–4 deadline. A computed date would sit in the Citation tuple
indistinguishably from an authoritative one.

**3. The `Standards` block polls daily, not monthly.**
[ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 4's table gives Standards a
monthly cadence, but that row is annotated *(Tier D)* and its rationale is "metadata only —
recognition lists move slowly". Monthly is therefore a property of the **tier**, and it moved to a
per-tier floor. It matters because in the MFDS cells the catalog's `Standards` block holds Tier A
binding 고시 — 화장품 안전기준 등에 관한 규정 among them, where most of the cosmetic cell's
obligations live in its 별표. Seeding revealed those inheriting a 30-day interval, which would have
missed the ≤24h detection-latency gate by a factor of thirty on the cell's most important content.
The recognition list is the one row that genuinely wants monthly and is Tier B, so it carries the
phase's single `interval_override_seconds` with a recorded reason.

**4. Celery workers use a sync SQLAlchemy session.**
`regops_shared.db` was async-only. A prefork worker has no long-lived event loop, and an asyncpg
connection cached across `asyncio.run()` calls is bound to a loop that has already closed. Added
`get_sync_engine` / `sync_session`; the API layer stays async. psycopg2 was already a dependency for
Alembic, so this costs no new package.

**5. Artefacts from one response share their archived object.**
403 KB of 의료기기법 시행규칙 arrives as one response carrying a body and 93 annexes. Archiving a
re-serialized subtree per annex would have violated "the raw response is archived **unmodified**",
so all artefacts from a call share one content-addressed `raw_object_key` and differ only in
`content_hash`. Citing an annex therefore resolves to the response it actually arrived in.

**6. `별표번호` is zero-padded by the API; the canonical key is not.**
Found on the first live fetch: every 별표번호 came back four-digit padded (`0001`). Left as
delivered, `canonical_key` would read `…#별표0001` while every human citation and every
cross-reference inside the text says 별표 1 — a mismatch that would have surfaced as a broken
citation in phase 1.3 rather than as a bug now. Pure-digit values are stripped; compound numbering
such as `1의2` is preserved verbatim.

**7. 법령 responses carry `<별표단위>` too.**
The spike observed inline annexes on 행정규칙 only. The live fetch found them on 법령 as well —
의료기기법 시행규칙 returned 93. Annex handling is not a 고시 special case, and the annex count for
the two gated cells is 116, not the handful the spike implied.

**8. The credential comes back *inbound*, and the archive now refuses it.**
[ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 13 is written entirely
about credentials going out — resolved URLs, logs, stored rows. The first live sweep found the other
direction: 국가법령정보's **목록** endpoints echo the `OC` parameter back inside the response body
(`행정규칙상세링크` is a fully-formed URL containing it). A response we never logged and never built
a URL from can therefore still carry the key.

Checked immediately: **the 13 already-archived documents are clean** — 본문조회 does not echo it,
only 목록/검색 does. Closed structurally rather than by convention: `archive_bytes` now refuses any
payload containing a configured source credential (inside the helper, not at its call sites, so no
future caller can omit it), and `UpstreamRule` has no link field at all — the same move as
`fetch_observations` having no request-URL column, and for the same reason, since
`source_discovery_runs.details` is persisted JSON.

**9. The 소관부처 code is a constant, not an env value.**
`MFDS_ORG_CODE = "1471000"` lives in `regops_shared/constants.py`. It is a public identifier, not a
credential: putting it in a gitignored `.env` would make it unreviewable, unversioned, and something
every environment and CI run has to rediscover — while blurring the boundary that makes
"what belongs in env" answerable at all. Non-secret connector arguments have a home already
(`sources.params`), and the seed writes it there from the constant.

**10. The 법령 set is 9, and 디지털의료제품법 moved to Primary Laws.**
The seed covered 7. 디지털의료제품법 has its own 시행령 (법령ID 014826) and 시행규칙 (014846), neither
of which the catalog listed, and the act itself sat under `Regulations` while the two structurally
identical acts — 의료기기법 and 화장품법 — sat under `Primary Laws` with their subordinate
instruments. All three 법령ID verified live 2026-08-03. Catalog corrected and the seed follows it;
`law_go_kr_law` sources are now 9.

**11. 별표번호 alone does not identify an annex — 105 units were silently merged.**
Found on 2026-08-05 while building the phase 1.5 viewer, which is the point of building one: the
list showed 디지털의료제품법 시행규칙 with 56 annexes where the archived response holds 76. The
authority reuses 별표번호 across **별표구분** (별표 vs 서식 share a number space) and across
**별표가지번호** (42, 42의2, 42의3). `canonical_key = {parent}#별표{번호}` therefore collided, and
`_upsert_document` returns the existing row on a key match — so the second annex's text was written
as a new **version** of the first.

Corpus-wide before the fix: **105 of 261 annex units had no document of their own**, and 66 annex
documents held 105 versions that were not revisions but other annexes' content. Phase 1.1's diff
stage would have emitted every one as a change event, on the cell whose obligations live in annexes.

Identity is now `(별표구분, 별표번호, 별표가지번호)` — exactly what the authority's own `별표키`
encodes — and the connector **fails closed** on any remaining duplicate rather than merging.
`connector_version` bumped to 1.1.0 so observations are attributable. Re-ingested: 278 annexes, zero
annex documents with multiple versions. Regression fixture and suite added; the original fixtures
missed it because their 별표번호 were unique, which is the lesson.
[ADR-0012](../design/ADR-0012-annex-version-identity.md) amended — the decision stands, its key
recipe was under-specified.

**12. `doc_type` is read from the envelope, not fixed per connector.**
The same viewer showed 화장품법 시행규칙 labelled 법률. `법종구분` states 총리령 outright in the
법령 envelope, and `DocType.DECREE` / `ENFORCEMENT_RULE` were defined but unreachable — the exact
smell of an enum value nothing produces. Now mapped: 3 laws, 3 decrees, 3 enforcement rules, 6
notices.

**13. The W3 reconnaissance, and what it changed.**
Three surfaces were seeded disabled because their endpoints were guesses. Firing guessed URLs at a
government host to discover their shape is the wrong way to learn, so they waited for a deliberate
reconnaissance rather than a live experiment.

- **RSS is `/www/rss/brd.do?brdId={brdId}`.** The directory page's link text cannot be used to map
  boards — every anchor carries the *same* generic title attribute — so all 35 feeds were fetched
  and each one's declared channel title read instead. That is the map.
- **제개정고시등 is one of those boards** (`data0008`), so the HTML scrape is unnecessary: RSS gives
  a `pubDate` per item and has no `조회수` to strip. The listing connector and its canonicalization
  stay, because phase 2.0's Tier C work needs exactly that shape.
- **There is no MFDS recognition list.** The guessed URL is 고시전문, and neither 의료기기 기준규격
  nor the GMP 고시 contains a single IEC/ISO identifier. Korea does not publish an FDA-style
  Recognized Consensus Standards database; that connector was built against an FDA-shaped
  assumption and waits for Phase 2.
- **4 of 35 feeds emit malformed XML** (`ntc0056`, `ntc0063`, `plc0138`, `plc0139`). None are ones
  we subscribe to, but it is why the connector must fail closed on a parse error rather than treat
  an unparseable body as an empty one.

**14. The M:N case is real, and it works.**
[phase1.1](phase1.1_normalization.md) recorded a risk that the two gated cells share no document, so
fan-out could only be tested against a synthetic fixture — and that the seed would *duplicate* the
RSS feed rather than share it. The reconnaissance settled both. MFDS boards are regulator-wide, so
`data0008` genuinely belongs to both cells, and keying feed identity on the authority's `brdId`
rather than our source slug makes it **one Document claimed by two cells**. Verified live: three
boards, two cells each, one version each — the cosmetic fetch creates it, the SaMD fetch finds the
same `content_hash`, records `unchanged`, and claims it. ADR-0002 decision 1 exercised against real
data instead of a fixture.

**15. The seeder never retired anything.**
Re-seeding is upsert-only, so a source dropped from the catalog kept its schedule and kept polling —
two stale RSS rows survived the catalog rewrite and were only noticed because their slugs appeared
in a query. The seeder now **disables** rows absent from the catalog and records why on the source.
Disable rather than delete: `documents.source_id` records which source discovered a document, and
deleting would either fail on the foreign key or destroy that provenance.

**16. `.env.test` could not have worked, and the reason generalises.**
The `guard_env` hook blocks the agent from writing any `.env.*`, so the file was created by hand —
and wiring it up exposed a defect in the phase-0 compose file that had been latent all along:
**`environment:` wins over `env_file:` in Compose.** `x-service-base` pinned `DATABASE_URL`,
`REDIS_URL` and `MINIO_ENDPOINT` under `environment:`, so a `DATABASE_URL` in `.env.test` was
silently ignored — `STAGE=test` resolved to the *dev* database. A test environment that quietly
shares the database it was created to avoid is worse than none, because the isolation is believed.

Fixed by separating the two concerns instead of fighting the precedence. Keys naming something
defined in `docker-compose.yml` itself stay pinned there; the database name gets one explicit knob,
`REGOPS_DB_NAME`. Everything else — `JWT_SECRET`, `LLM_*`, `LAW_GO_KR_OC` — still comes from the
stage file, which is what `.env.test` is actually for.

The same split-brain then surfaced on MinIO: the *server* password came from host interpolation
while the *client* password came from the stage file, so the first archive write failed with
`SignatureDoesNotMatch`. Both now read the same interpolated variable, and the compose file says why.

**17. Service images install `[dev]` extras.**
The documented way to run a service suite is inside the stack, but the images installed `/shared`
without dev extras — so `docker compose run --rm regulation python -m pytest` failed on a clean
image and only worked after someone pip-installed pytest by hand into a running container. That is
exactly how a suite becomes green on one machine. These are local dev images; the extras belong in
them.
