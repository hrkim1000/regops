# Phase 1.1 — Normalization

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W3–W6 · **Status:** ⬜ planned
- **Governed by:** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md),
  [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) (drift · diff · dates),
  [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) (domain branching),
  [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 3,
  [ADR-0012](../design/ADR-0012-annex-version-identity.md) (annex identity),
  [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) (effective dates)
- **Depends on:** [phase1.0](phase1.0_ingestion.md)
- **Service:** `regulation` (L2)

---

## Goal

Turn archived bytes into an addressable, diffable clause store. **This is the critical path** —
ADR-0002 calls the clause model the most expensive thing in RegOps to change later, because altering
it after ingestion means re-parsing the archive and invalidating every stored citation.

This phase also carries both architecture falsifiers. They are not milestones to pass; they are
tests designed to fail loudly if the shared-pipeline bet is wrong.

## Scope

**In:** parser profiles, clause segmentation, `ClauseDiff`, `ChangeEvent` emission, renumbering
resolution, and — carried over from 1.0 — 시행예정 ingestion.

**Out:** IR extraction (1.2), embeddings (1.3), alert routing (1.4). Multilingual is *modelled* here
but not exercised — both gated cells are Korean-only.

**Already delivered by [phase1.0](phase1.0_ingestion.md)**, so do not rebuild: `document_versions`
per `(document, language, content_hash)` with `version_group_id` and a `parser_version` column;
the `structure_drift_alerts` table with its `ra`-restricted resolve endpoint and audit entry; the
per-connector canonicalizers this phase takes over.

## Tasks

### Clause schema — W3–4, do not defer

- [ ] `clauses(document_version_id, clause_path, path_segments, level, ordinal, heading, text)`
- [ ] **plus `effective_date` and `effective_date_phrase`** — not optional and not deferrable to a
      later migration. [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5
      makes the version-level date *overridable per clause*, the 시행예정 work below **requires**
      clause-level `조문시행일자`, and
      [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) pairs every date column with
      its raw-phrase fallback. Adding them after the archive is parsed is the expensive change
      ADR-0002 warns about
- [ ] **Domain-neutral** — no SaMD-only or Cosmetic-only column. 조/항/호 and Part/Subpart/§ are both ordered hierarchical paths
- [ ] Immutable once written; populate `parser_version` (the column already exists)

### Parser profiles

- [ ] Hierarchy mode — 조/항/호/목 from 본문조회
- [ ] **Table mode** — fixed-width box-drawing annexes (`┌ ├ │ ┬ ┼` at consistent offsets), one `Clause` per row. Mechanical and deterministic; **no LLM in the parsing path**
- [ ] **Decide whether an annex clause path repeats 별표N.** Under
      [ADR-0012](../design/ADR-0012-annex-version-identity.md) the annex is its own `Document`, so
      its identity already carries 별표N (`canonical_key = …#별표2`, `annex_no`). Repeating it in
      `path_segments` makes annex citations self-describing; omitting it keeps the path relative to
      its document exactly like a body clause. Either is defensible, neither is reversible once
      citations exist — pick deliberately and record it
- [ ] Both modes used by both domains — the split is prose vs table, not SaMD vs Cosmetic
- [ ] Canonicalization step per profile, taken over from [phase1.0](phase1.0_ingestion.md)'s per-connector minimum — it feeds `content_hash`, never the archived or cited bytes

### Annex row granularity — **decide by W4, owned here, consumed by 1.3**

- [ ] **Resolve [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open
      question 3: does `annex_rows` exist alongside `clauses`, and which service owns it?**
      [ADR-0012](../design/ADR-0012-annex-version-identity.md) settled only the *container* — a 별표
      is a child `Document` with its own versions — so what is still open is the **granularity
      inside it**. [phase1.3](phase1.3_retrieval_qa.md) assumes a structured row store exists and
      accepts on exact-match ingredient lookup; nothing currently creates one. 1.3 inherits the
      answer and cannot build the index without it
- [ ] Feeds the same decision: 별표 1 of 화장품 안전기준 규정 is 340,074 chars / 7,367 lines and
      별표 2 is 218,995 / 4,235, so one `Clause` per row is **~12,000 rows for that 고시 alone** —
      and phase 1.0 already ingested **116 annexes** across the two cells
      ([ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 2)
- [ ] Outcome goes in an **ADR**, not this file — it changes the storage model and 1.3 reads it

### 시행예정 (pending-effect) versions — **carried over from [phase1.0](phase1.0_ingestion.md), and it gates detection latency**

> L1 ingestion work in an L2 phase, deliberately: a pending version is only *useful* once it can be
> diffed and carries an `effective_date`, and both land here. Deferred from 1.0 by decision on
> 2026-08-03.

- [ ] **Ingest 시행예정 법령 via `target=eflaw`.** Polling 현행 only means an amendment is invisible from 공포 until 시행. Measured live 2026-08-03: **8 amendments across the 9 gated 법령 are already 공포'd and unseen**, the oldest promulgated 2025-12-30 — seven months before the check. Detection latency for those is 시행 − 공포, i.e. **2 months to 2.4 years**, so the ≤24h gate is not merely unmet but structurally unmeetable without this
- [ ] **A version is one `MST` (법령일련번호), not one 시행일자.** 화장품법 returns 6 pending rows but only **4 distinct MST**: one amending act (MST 282015, 공포 2025-12-30) carries three 시행일자 — 2026-12-31, 2028-01-01, 2029-01-01. Keying versions on 시행일자 would triplicate identical text
- [ ] **Those three dates are staged application, and they belong at clause level** — `조문시행일자`, which the spike already confirmed is present per clause. This is [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5's per-clause `effective_date` override, met in the wild rather than in theory
- [ ] **Version-level `effective_date` = the earliest 시행일자 for that MST**; clauses carry the rest
- [ ] **ADR needed before building.** The eflaw envelope states 시행일자 outright, so for these versions it is *fetch* metadata — the same category as 공포일자 → `published_at` — not the parse output [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5 describes. [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) is untouched: it governs 부칙 *text* extraction, where a date must never be guessed. Write the amendment before the code, not after
- [ ] **History (연혁) stays out of Phase 1.** `eflaw` also returns superseded versions — 20 rows for 화장품법 back to 2018. Backfilling them would give diff baselines we did not archive ourselves, which the citation contract does not accept ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 12). Phase 2 at the earliest
- [ ] Scope check: 9 documents → **17 versions** (현행 + 8 distinct pending MST) at the time of measurement, and that count moves with every new 공포

### Structure drift — the parse-stage half

[phase1.0](phase1.0_ingestion.md) built the table, the `ra`-restricted resolve endpoint, and the
fetch-stage signals (`auth_failure`, `zero_records`, `missing_root`). This phase adds the parse-stage
ones.

- [ ] Raise on **zero clauses extracted** and on **clause count beyond threshold**. Creates **no** version and emits **no** change event ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 6, which says Phase 1 builds the hook even though Tier C is [phase2.0](phase2.0_tier_c_scale.md))
- [ ] **Raise `EMPTY_ANNEX_BODY`, which is currently defined but never raised.** 1.0 logs and skips an annex whose `별표내용` is empty; `attachments` holds the authority's own file links as the documented fallback. Decide here whether the fallback is *implemented* (fetch the HWP/PDF) or the case is simply *alerted* — an annex silently absent is the worst outcome for the cell whose obligations live in them. Spike still-open question 4
- [ ] Threshold calibration is [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 5: clause-count delta is crude, and a large genuine amendment must not read as drift

### Diffing

- [ ] `clause_diffs(from_version_id, to_version_id, clause_path, change_kind, from_clause_id, to_clause_id, similarity)`
- [ ] `change_kind ∈ added | removed | modified | renumbered | moved`
- [ ] **Renumbering resolved explicitly, never reported as delete + add.** Primary signal is the authority's own: `조문변경여부`, `조문이동이전`, `조문이동이후` from law.go.kr. Content-similarity matching is the fallback for sources exposing nothing
- [ ] Low-confidence renumber matches queue for RA review
- [ ] Diffs computed **within one language** — KO for MFDS
- [ ] `ChangeEvent` emitted from `ClauseDiff`, fanned out to every claiming cell
- [ ] **Confirm 조문별 변경이력 granularity matches `ClauseDiff`** — transferred from [phase1.0](phase1.0_ingestion.md), which could not act on the answer. The authority computes clause-level change history itself; where it does, reconcile our computed diff against it as free ground truth for the detection-coverage gate ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 12)
- [ ] **Decide: diff inline, or as its own stage?** [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 4, due W3–4 alongside the clause schema because it is a stage boundary in this pipeline. Inline is simpler; splitting lets an improved profile re-diff historical versions without re-fetching. The ADR leans split

### Citation support

- [ ] Superseded-citation detection: when a diff touches a cited clause path, mark citations `superseded` and queue re-verification. **Never rewrite a citation**

## Falsifiers — escalate, do not work around

- [ ] **Annex representation (W3–4).** Can a 화장품 안전기준 규정 limit-table row be expressed as a `Clause` with `path_segments`? Must be answered *before* the W5–6 check, not during it. Failing this falsifies [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 3
- [ ] **Cross-domain (W5–6).** Does Cosmetic parse without forking Normalization or Section Parsing? A Cosmetic-only column on `Clause`, a second pre-IR stage, or a domain-forked parser all falsify [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 3 — and Phase 2's six-cell build rests on it

> The live API test on 2026-07-29 did **not** trigger the falsifier: the same box-drawing annexes
> appear on the SaMD side, and 별표 3 of the cosmetic 고시 is pure prose. Re-run against real
> ingestion rather than treating the spike as settled.

## Acceptance criteria

- [ ] 화장품법 and 의료기기법 both parse to clauses through one pipeline, no domain branch
- [ ] A renumbered-but-unchanged clause reports `renumbered`, never delete + add — integration test
- [ ] An annex limit-table row round-trips as a `Clause` and is addressable by `clause_path`
- [ ] A parse yielding zero clauses raises drift, creates no version, and emits no change event
- [ ] **A 시행예정 version is ingested with a future `effective_date` and does not displace 현행** — a query for the current text still returns the in-force version
- [ ] **One MST carrying three 시행일자 produces exactly one version**, with the earliest date at version level and the remainder on clauses
- [ ] Fan-out reaches every claiming cell and no others — verified against a **synthetic multi-cell fixture**, because the two gated cells share no *regulation* in common: `mfds_cosmetic` (화장품법 family) and `mfds_samd` (의료기기법 family) have zero documents in common, and the FD&C Act — the natural M:N case — is FDA, first ingested in [phase2.0](phase2.0_tier_c_scale.md). Cell isolation is a CLAUDE.md non-negotiable test, so Phase 1 builds the fixture rather than deferring the test. *(The MFDS RSS boards are now a real shared case — one Document claimed by both cells — so the synthetic fixture is a deterministic complement to it, not a substitute for something that does not exist.)*
- [ ] A single-cell document does **not** fan out to the other gated cell — the negative half of the same test
- [ ] Amending a cited clause flags the citation superseded and leaves its text resolvable

## Risks & open questions

- ~~**The MFDS RSS feed is registered twice and would ingest twice.**~~ — **closed by the W3
  reconnaissance (2026-08-05).** The feed is per-board (`brdId`), and MFDS boards are
  regulator-wide, so `data0008` 제개정고시등 genuinely belongs to both gated cells. Feed identity now
  comes from the authority's `brdId` rather than our source slug, so the two subscriptions resolve
  to **one Document claimed by two cells** — verified live on three boards. The duplicate this risk
  predicted cannot occur, and Phase 1 now has a real M:N case rather than only a synthetic one.

- **Annex row granularity** ([ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 2) — ~12,000 rows for 화장품 안전기준 alone, against 116 annexes already ingested. **Owned here and due W4** (see *Annex row granularity* above); previously this file deferred it to 1.3 while 1.3 deferred it back here, leaving a critical-path decision with no owner.
- **Diff synchronously or async?** [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 4 — now carried as a task above rather than only as a risk, because it is due in the same W3–4 window as the clause schema.
- **Multilingual is modelled, not built.** First real exercise is the EU spike. Do not let Korean-only assumptions leak into the schema.
- **Detection latency stays unmeasurable for the 법령 sources until 시행예정 ships.** Report it as unmeasurable rather than quoting a number the pipeline cannot produce.

## Deviations & decisions

<!-- Architecture changes go in an ADR, linked here. -->

*None yet — this file was revised on 2026-08-03 against what phase 1.0 actually delivered, but no
1.1 work has started.*
