# Phase 1.0 — Ingestion

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W1–W4 · **Status:** ⬜ planned
- **Governed by:** [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md), [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decisions 1 · 6, [import-agent.md](../import-agent.md)
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

- [ ] `sources` seeded from [import-source-map.md](../import-source-map.md) for both gated cells — read the catalog, never copy it into code comments
- [ ] `url_template` holds a credential **placeholder**, never a resolved URL ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 13)
- [ ] `tier` and `ingestible` flags carried through; Tier D rows carry no fetch path at all
- [ ] `source_schedules` driving the beat, per-source cadence

### Connectors

- [ ] 국가법령정보 OPEN API — obtain the key (W3, blocking); 법령 본문조회 for 화장품법 and 의료기기법
- [ ] MFDS RSS — notices, legislative notices, amendments
- [ ] 행정규칙 본문조회 for 고시, including `<별표단위>` / `<별표내용>`
- [ ] Polite fetch: contactable `User-Agent`, `ETag` / `If-Modified-Since` where offered, backoff
- [ ] **Attachment pipeline — HWP and PDF for 별표.** The 별표·서식 API returns file links only, and the prohibited/restricted ingredient lists carrying most `mfds_cosmetic` obligations arrive this way. HWP has thin library support — size it as a workstream, not a library call
- [ ] Annexes hashed and versioned **independently of the parent body** — they carry their own effective dates, and sharing the parent's hash silently misses every ingredient-list amendment

### WORM archive

- [ ] Content-addressed `raw_object_key = sha256(bytes)` in MinIO; write-once, never mutated
- [ ] Unchanged re-fetch records a `fetch_observation` and creates **no** new version
- [ ] Changed hash creates a `DocumentVersion` and enqueues parse → diff → change event
- [ ] `document_cells` M:N — a document is ingested once and claimed by one or more cells

### Dates & scheduling

- [ ] Three separate dates: `retrieved_at`, `published_at`, `effective_date` — none substituting for another ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5)
- [ ] Celery beat on the `regulation` queue; incremental commit so a retry skips completed rows

### Reconnaissance follow-ups (W3, from the [MFDS spike](../design/spike-2026-07-29-mfds-source-recon.md))

- [ ] Confirm 본문조회 returns annex text via `<별표단위>` — **resolved 2026-07-29, re-verify with the live key**
- [ ] Obtain the 소관부처 code for 식품의약품안전처
- [ ] Confirm 조문별 변경이력 granularity matches `ClauseDiff`
- [ ] **Source discovery sweep** — the 행정규칙 API enumerates 고시 by 소관부처. Reconcile the curated source map against the authority's own list; a hand-maintained list caps detection coverage at whatever someone remembered to add

### EU SaMD spike (non-gated, W3 → W12)

- [ ] EUR-Lex fetch for MDR (EU) 2017/745 at reduced depth
- [ ] Record multilingual and Tier C effort for the Phase 2 estimate — findings memo lands in phase 1.6

## Acceptance criteria

- [ ] Both gated cells fetch on schedule with zero manual steps
- [ ] An unchanged re-fetch produces a `fetch_observation` and **no** new `DocumentVersion` — verified by integration test
- [ ] A changed source produces exactly one new version and enqueues downstream work
- [ ] Annexes version independently: amending 별표 2 alone creates a version for the annex and not the body
- [ ] No credential appears in `sources`, logs, or fixtures
- [ ] No Tier D bytes reach the archive — CI scan green

## Risks & open questions

- **API key on the critical path (W3).** The 국가법령정보 key gates the first real fetch. Request it in W1, not W3.
- **HWP extraction** is the most likely schedule surprise in this phase. If library support proves unworkable, escalate — the ingredient lists are where most `mfds_cosmetic` obligations live.
- **ADR-0002 open question 3** — `canonical_key` derivation. Phase 1 needs only the MFDS answer (법령ID / 고시번호); EU ELI, FDA CFR citation and NMPA are deferred.

## Deviations & decisions

_None yet._
