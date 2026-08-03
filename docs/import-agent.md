# Import Agent

**How sources are fetched, archived, and versioned.** The catalog of *what* to fetch is
[import-source-map.md](import-source-map.md) and is never duplicated here — a catalog in two places
means one of them is stale and nothing says which.

- **Governed by:** [ADR-0002](design/ADR-0002-canonical-regulation-model.md) (canonical model),
  [ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) (ingestion contract),
  [ADR-0008](design/ADR-0008-service-composition.md) (composition),
  [ADR-0012](design/ADR-0012-annex-version-identity.md) (annex identity),
  [ADR-0013](design/ADR-0013-unresolvable-effective-dates.md) (effective dates)
- **Built in:** [phase1.0](plan/phase1.0_ingestion.md) (fetch → archive → version),
  [phase1.1](plan/phase1.1_normalization.md) (parse → diff → emit)
- **Verified against the live 국가법령정보 API** on 2026-08-03; findings marked *(live)* below

> **"Import Agent" is a pipeline, not an agent.** It invokes no LLM, writes no row carrying model
> provenance, and needs no separate verification gate — it fails all three of
> [ADR-0008](design/ADR-0008-service-composition.md) decision 2's tests. The name is **grandfathered
> as a proper noun and confers no agent obligations** (ADR-0008 decision 3). Determinism is the
> point: a regulation's text must arrive byte-identical to what the authority published, and nothing
> in this path is permitted to paraphrase it.

---

## Scope

Eight cells — `{authority}_{domain}`, `authority ∈ mfds|fda|eu|nmpa`, `domain ∈ samd|cosmetic`.
Phase 1 builds **`mfds_samd` and `mfds_cosmetic`** only; FDA, EU and NMPA appear below solely as
design constraints the contract must remain wide enough to accept.

The generic structure exists for maintainability, **not as grounds for widening scope**.
Pharmaceuticals, biologics, food, health functional food and every other regulator are out of scope
([RegOps.md](RegOps.md) § Scope).

## Pipeline

Five stages, each idempotent and independently resumable, committing incrementally so a retry skips
completed rows.

```text
  fetch ──→ archive ──→ parse ──→ diff ──→ emit
    │          │           │        │        │
  bytes +   sha256      clauses  ClauseDiff  ChangeEvent
  headers   WORM blob      +     per path    per claiming cell
  (+ published_at    effective_date
   where exposed)   (부칙 / entry-into-force)
    │
    └─ fetch_observation recorded on EVERY attempt, changed or not
  └────── phase 1.0 ──────┘└──────────── phase 1.1 ────────────┘
```

Per-cell variation is isolated into exactly two places — **Connectors** and **Parser Profiles**.
Everything else is shared across all eight cells.

## Connectors

A connector's whole job is `Source → [FetchedArtifact]`. **Connectors fetch; they do not parse**
([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 1). Fetching MFDS RSS and
fetching EUR-Lex are different problems; parsing 화장품법 and 의료기기법 is the *same* problem, so
fusing the two would multiply the work instead of adding to it.

Where the line falls:

| Connector | Parser Profile (phase 1.1) |
|---|---|
| talk to the host, honour cache validators, back off | clause segmentation into 조/항/호/목 |
| identify which artefacts a response carries (body, each 별표) | `effective_date` from 부칙 |
| read dates the API envelope hands over | anything requiring the regulation to be *read* |
| produce the canonicalized bytes change detection hashes | |

`effective_date` is therefore absent from a connector's output even where the envelope states
시행일자 outright: it is a parse output
([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 5) and rides in artefact
metadata until phase 1.1 writes it.

### Politeness is part of the contract

Per-host minimum interval, exponential backoff with jitter on 429/5xx, `Retry-After` honoured,
a contactable `User-Agent`, and `ETag`/`If-Modified-Since` wherever offered — a 304 is the cheapest
possible `fetch_observation`.

Not optional courtesy: these are government hosts, and being rate-limited off MFDS during the pilot
would take out both gated cells at once. Phase 3 also sells to customers who will ask how we collect.

### Credentials — in both directions

The 국가법령정보 key is **self-designated by the account holder** and passed as a query-string
parameter, so it is likelier to be low-entropy and reused than an issued token. One leak is enough.

**Outbound** ([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 13):

- The key lives in settings (`LAW_GO_KR_OC`) — never in this document, the source map, a `sources`
  row, an ADR, or a fixture.
- `sources.url_template` stores a template with a `{OC}` placeholder. The resolved URL is built at
  request time and **is never persisted**.
- `fetch_observations` has **no column** a request URL could occupy. Any logging redacts credential
  parameters first.

**Inbound** *(live, and the reason "never log the URL" is insufficient)*: 국가법령정보's **목록**
endpoints echo the key straight back inside the response body — `행정규칙상세링크` on every row is a
fully-formed URL containing it. Consequences, both structural:

- The WORM archive **refuses** any payload containing a configured source credential. Refusal, not
  redaction: the archive stores the raw response unmodified, so no variant keeps both the evidence
  intact and the key out. The check lives inside the archive helper, not at its call sites.
- The discovery sweep's row model has **no link field at all**, mirroring `fetch_observations`.

The 본문조회 endpoints do **not** echo it — verified across every archived document. Only 목록/검색
does, which is why sweep responses are consumed in memory and archived never.

### Non-ingestible sources are unfetchable by construction

`sources.ingestible = false` for Tier D and for login-gated portals (EU CPNP, EUDAMED — commentary,
neither in Phase 1 scope). The scheduler skips them **and** every connector refuses them at its
entry point. A Tier D source has no code path that could write body text.

## 국가법령정보 OPEN API

`law.go.kr` HTML is JS-rendered and returns only the page title to a plain fetch, so the OPEN API is
the only viable path. It returns 조문/항/호/목 as **separate structured fields**, which is why the
clause hierarchy is *given* rather than inferred.

### Two endpoints, and they are not interchangeable

| Purpose | Endpoint |
|---|---|
| 본문조회 — the document text | `GET /DRF/lawService.do` |
| 목록/검색 — enumeration | `GET /DRF/lawSearch.do` |

Calling `lawSearch.do` with an `ID` returns a *list*, not 본문. Getting this wrong fails silently.

### Targets

| Target | Grant | Used | Note |
|---|---|---|---|
| `law` | ✅ | ✅ | 법령 본문. 9 documents across the two gated cells |
| `admrul` | ✅ | ✅ | 행정규칙 (고시) 본문, including `<별표단위>` |
| `eflaw` | ✅ | ⬜ **phase 1.1** | 시행일법령 — 시행예정 versions. See *Known gaps* |
| `licbyl` | ✅ | ✅ *(metadata only)* | 별표·서식 목록 — file links, kept as fallback |
| `expc` / `prec` | ❌ | ❌ | 법령해석 / 판례. Not granted, **not needed** — not regulation text and absent from the source map |

Common parameters: `OC` (required), `target` (required), `type=XML`, `display` (≤100), `page`,
plus `ID`/`MST`/`LM` for 본문조회 and `query`/`org` for 목록.

### Every failure signature is HTTP 200 *(live)*

A connector checking only transport status records a healthy observation for a fetch that retrieved
nothing. Each is detected explicitly:

| Response | Meaning | Handling |
|---|---|---|
| `사용자 정보 검증에 실패…IP주소 및 도메인주소를 등록` | egress IP no longer matches registration | `auth_failure` drift alert |
| HTML `미신청된 목록/본문에 대한 접근입니다` | API scope not granted | `auth_failure` drift alert |
| `resultCode 00 success` with `totalCnt 0` | malformed query — indistinguishable from "does not exist" | `zero_records` drift alert |
| non-200 / timeout | authority outage | retry with backoff |

**IP enforcement is confirmed real.** The account is registered by IP alone, so any change of egress
network reopens this.

### Source discovery

`lawSearch.do?target=admrul&org=…` enumerates every 고시 by 소관부처, so the curated catalog can be
reconciled against the authority's own list rather than trusted
([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 11).

**소관부처 code for 식품의약품안전처 is `1471000`** *(live)* — a public identifier, held in
`regops_shared.constants.MFDS_ORG_CODE`, deliberately **not** in an env file where it would be
unreviewable.

Two properties keep the sweep usable rather than noisy:

- **The relevance filter is mandatory.** Most of the 511 MFDS 고시 are 식품 and 건강기능식품, which
  belong to no cell. It is deliberately over-inclusive — a 고시 missed because the filter was clever
  is a coverage hole; one wrongly listed costs a glance — and the unfiltered total is recorded
  alongside the filtered one so the narrowing is visible.
- **Titles compare normalized.** The catalog writes `·` where the authority writes `ㆍ`, and spacing
  differs; comparing raw would manufacture gaps that are not there.

Output is a `source_discovery_runs` row: a **triage list for a human**, never an ingestion trigger.

## Change detection

`content_hash = sha256(canonicalized body)` — and **never** `sha256(response bytes)`. Nav chrome,
session tokens, rotating banners and view counts change on every request, so hashing raw bytes makes
every poll look like an amendment and buries the detection-coverage gate in false positives on day
one ([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 2).

Two hashes, and conflating them is the mistake:

| | Value | Role |
|---|---|---|
| `raw_object_key` | `sha256(raw response bytes)` | WORM key — **this is what gets cited** |
| `content_hash` | `sha256(canonicalized body)` | what change detection keys on |

- unchanged → record a `fetch_observation`, stop. **No version, no parse, no diff.**
- changed → new `DocumentVersion`, then parse → diff → emit.

Canonicalization effort varies sharply by source. The structured 본문조회 responses need only a
stable serialization — there is no page chrome to strip. MFDS listing rows carry **`조회수`**
(view count), the confirmed volatile element; dropping it is the entire job there, and the test
proving it is the one protecting the coverage gate.

## Parser Profiles

> **The split is prose vs. table — a content type present in both domains — not SaMD vs. Cosmetic.**

Profiles are *addressed* per cell, but they must not **fork** the pipeline. The same two modes serve
both domains:

| Mode | Input | Output |
|---|---|---|
| hierarchy | 조/항/호/목 from 본문조회 | one `Clause` per node, `path_segments` ordered |
| table | fixed-width box-drawing annexes (`┌ ├ │ ┬ ┼` at consistent offsets) | one row per line, `path_segments = [별표N, row]` |

Both are mechanical and deterministic. **No LLM anywhere in the parsing path.**

**Falsification criterion** ([ADR-0002](design/ADR-0002-canonical-regulation-model.md) decision 3):
if the cross-domain check requires a Cosmetic-only column on `Clause`, or a second parser stage
before Section Extraction, the shared-pipeline assumption has failed and Phase 2 must be re-planned.
**Escalate rather than adding the column.**

*(live)* The falsifier did not trigger. Box-drawing annexes appear on the SaMD side (의료기기
기준규격) and 별표 3 of the *cosmetic* 고시 is 0% table — so the content types cross the domain
boundary in both directions.

## Where the domain branch happens

**Import → Normalization → Section Parsing is shared by all eight cells. The first domain-specific
step is IR extraction — and there is no branch before it.**

```text
Source Import
      │
      ▼
Regulation Library       ─┐
      │                   │  shared across all 8 cells:
      ▼                   │  no domain-specific column, no domain-forked
Document Normalization    │  parser, no pre-IR stage
      │                   │
      ▼                   │
Section Extraction       ─┘
      │
      ├────────► SaMD IR Extract
      │
      └────────► Cosmetic IR Extract
```

Domain divergence lives in `IR.domain_profile` (`samd` | `cosmetic`) and the extraction rules keyed
by it ([ADR-0002](design/ADR-0002-canonical-regulation-model.md) decision 3,
[ADR-0004](design/ADR-0004-ir-extraction-and-domain-branching.md) decision 3).

This is the architecture bet Phase 2's six-cell build rests on, which is why the two gated cells hold
the *regulator* constant and vary the *domain*: MFDS SaMD and MFDS Cosmetic differ in exactly the
dimension the claim is about. Moving the branch earlier is not a refinement — it invalidates the
Phase 2 estimate.

## Annexes (별표)

The substantive obligations of the Cosmetic cell — the prohibited and restricted ingredient lists —
live in 별표, not in the body's prose clauses.

**행정규칙 본문조회 returns `<별표단위>` containing `<별표내용>` inline** *(live)*, and so does
법령 본문조회 — 의료기기법 시행규칙 returns 93 of them. Annex text arrives with the body, so
**HWP/PDF extraction is not on the Phase 1 path at all**.

**An annex is a child `Document`, not a row on a version**
([ADR-0012](design/ADR-0012-annex-version-identity.md)):

- `doc_type = 'annex'`, `parent_document_id` → the body, `canonical_key = {parent}#별표{n}`
- its own `document_versions`, `effective_date`, and diff lineage

A row keyed on `document_version_id` could not version independently of its parent, which is exactly
what amending 별표 2 alone requires. `attachments` keeps the narrower job of recording the
authority's file links (`별표서식파일링크`) as an archival copy and as the fallback for an empty
`별표내용`.

*(live)* 별표번호 arrives **zero-padded** (`0001`). It is normalized to `1`, because every human
citation and every cross-reference in the text says 별표 1.

## Dates — three, none substituting for another

| Field | Source | Always present? | Used for |
|---|---|---|---|
| `retrieved_at` | our clock at fetch | yes | audit trail, latency **upper bound** |
| `published_at` | 공포일자 / 발령일자 / RSS `pubDate` | **no** | the detection-latency gate |
| `effective_date` | parse-derived from 부칙 | usually | citations, applicability, alert priority |

**Never default `published_at` to `retrieved_at`.** Latency is "authority publishes → owner
alerted"; using our own fetch clock makes the ≤24h gate pass by construction and measure nothing.
Where a source exposes no publication timestamp it stays **null** and latency is reported
**unmeasurable rather than zero**.

**Never guess `effective_date`.** Where the text states a condition rather than a calendar date
("공포 후 6개월"), the column stays NULL and the raw 부칙 phrase is retained in
`effective_date_phrase` ([ADR-0013](design/ADR-0013-unresolvable-effective-dates.md)). A computed
date there would be indistinguishable from an authoritative one to every downstream reader, and
`effective_date` is part of the Citation tuple.

**Staged application** is real, not hypothetical: one amending act routinely carries several
시행일자. `effective_date` is recorded per version **and** overridable per clause — which matches how
the authority itself models it (`조문시행일자`, `별표시행일자문자열`).

## Poll cadence

Derived from the source's block plus tier, **never hand-set per source**
([ADR-0003](design/ADR-0003-ingestion-and-change-detection.md) decision 4), so adding a source
inherits a sane cadence instead of requiring a scheduling decision.

| Block | Interval | Rationale |
|---|---|---|
| Primary Laws, Regulations, Registration, Ingredient | daily | where legal change actually lands |
| Standards | daily | binding 고시 unless the tier floor applies |
| Safety | daily | time-sensitive by nature |
| Guidance, Official Sources | weekly | changes a few times a year; portals are navigation |

A **tier floor** then applies: Tier C no faster than daily, **Tier D monthly** — recognition lists
move slowly, and monthly is a property of the tier, not of the block. In the MFDS cells the
`Standards` block holds Tier A 고시 (화장품 안전기준 등에 관한 규정 among them), so a monthly
cadence there would miss the ≤24h gate by a factor of thirty on the cell's most important content.

Overrides are allowed but `interval_override_seconds` and `interval_override_reason` are set
together, enforced by a CHECK constraint: an override without a recorded reason is an accident, not
a decision.

## Structure drift is an operator alert, never a ChangeEvent

A site redesign changes everything at once. Emitting that as regulatory change would generate
thousands of false alerts and destroy trust in the monitoring pillar.

The parse stage fails closed on drift signals — zero records, record count beyond threshold, missing
root, an authority error behind HTTP 200, an empty `별표내용`. It raises a `structure_drift_alert`
against the source, creates **no** version and emits **no** change event. Resolution is restricted to
`ra`: it is one of exactly two Phase 1 actions where a human assertion enters the audit trail.

## Tier D — metadata only

ISO/IEC standards and pharmacopoeias prohibit source-text storage and AI training. This is enforced
by there being **nowhere to put the text**, not by policy
([ADR-0002](design/ADR-0002-canonical-regulation-model.md) decision 2):

1. `standard_references` has no `text` column and no varchar over 512 characters
2. every connector refuses a Tier D source at its entry point
3. the recognition-list connector returns records and **no artefacts** — nothing on this path can
   reach the archive
4. seeded Tier D rows carry no connector and no URL

Freshness is tracked through the recognition/harmonized **list**, an ingestible Tier B page. The
standard itself is never fetched. This holds even where a regulation makes the standard legally
binding — QMSR incorporates ISO 13485:2016 by reference: cite the requirement, link the standard,
store neither. A CI string scan is the backstop, not the mechanism.

## Formats

**In use:** XML (본문조회, RSS), HTML (listing and recognition tables).

**Not used, and not planned for Phase 1:** PDF, HWP, DOCX, XLS, ZIP. The reconnaissance reversed the
original premise here — annex text arrives inline, so the attachment pipeline records *links*, not
extracted content. Binary archival is opt-in per source and off by default: fetching every government
attachment on every poll is a politeness cost with no Phase 1 payoff.

**OCR is not performed.** It appeared in earlier drafts of this spec; nothing in the Phase 1 path
needs it, and running OCR over a Tier D document would produce exactly the stored standard text the
architecture forbids.

## Metadata actually recorded

Mapped to real columns rather than aspiration. Absences are as load-bearing as presences.

| Concept | Where it lives |
|---|---|
| document identity | `documents.canonical_key` — 법령ID / 행정규칙ID from the **response**, so querying by 법령명 does not weaken it |
| cell claim | `document_cells` — **M:N**; a statute claimed by two cells is ingested once |
| version identity | `document_versions(document_id, language, content_hash)` unique |
| raw bytes | `raw_object_key` — content-addressed, write-once, never mutated |
| language | `document_versions.language` + shared `version_group_id` across variants |
| dates | `retrieved_at`, `published_at`, `effective_date`, `effective_date_phrase` |
| every fetch attempt | `fetch_observations` — written on **every** attempt, changed or not |
| parser provenance | `document_versions.parser_version`, `fetch_observations.connector_version` |
| Tier D | `standard_references` — recognition record only |
| drift | `structure_drift_alerts` |
| catalog delta | `source_discovery_runs` |

**Deliberately absent:** a request-URL column anywhere (credentials), a body-text column on
`standard_references` (Tier D), and `authority`/`domain` as scalars on `documents` — the last would
force duplicate ingestion of any statute two cells share, which is what `document_cells` exists to
prevent.

## Known gaps

- **시행예정 (`eflaw`) is not yet ingested — phase 1.1.** Polling 현행 only means an amendment is
  invisible from 공포 until 시행. *(live)* 8 amendments across the 9 gated 법령 are already 공포'd and
  unseen, the oldest promulgated seven months prior; latency for those is 시행 − 공포, between
  2 months and 2.4 years. **Until this ships, detection latency for the 법령 sources is not
  measurable** and must be reported as such rather than given a number.
  A version is one **MST** (법령일련번호), not one 시행일자 — several 시행일자 on one MST are staged
  application belonging at clause level.
- **Catalog coverage is 6 of 72 in-scope MFDS 고시** *(live)*. The sweep measures it; closing it is
  an RA triage decision against `import-source-map.md`, not a code change.
- **Three MFDS surfaces are seeded disabled** — RSS, the 제개정고시등 listing, the recognition list.
  Connectors are built and tested against recorded fixtures; the endpoints are unconfirmed, and
  firing guessed URLs at a government host to find out is the wrong way to learn.
- **History (연혁) is out of Phase 1.** `eflaw` also returns superseded versions, but those are
  baselines we did not archive ourselves, which the citation contract does not accept.
- **Tier C scraping is phase 2.0.** The drift hook is built now regardless.
