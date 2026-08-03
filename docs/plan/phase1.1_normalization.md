# Phase 1.1 — Normalization

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W3–W6 · **Status:** ⬜ planned
- **Governed by:** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
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

**In:** parser profiles, clause segmentation, `DocumentVersion`, `ClauseDiff`, `ChangeEvent`
emission, renumbering resolution.

**Out:** IR extraction (1.2), embeddings (1.3), alert routing (1.4). Multilingual is *modelled* here
but not exercised — both gated cells are Korean-only.

## Tasks

### Clause schema — W3–4, do not defer

- [ ] `clauses(document_version_id, clause_path, path_segments, level, ordinal, heading, text)`
- [ ] **Domain-neutral** — no SaMD-only or Cosmetic-only column. 조/항/호 and Part/Subpart/§ are both ordered hierarchical paths
- [ ] `DocumentVersion` per `(document, version, language)` with a shared `version_group_id`
- [ ] Immutable once written; `parser_version` recorded

### Parser profiles

- [ ] Hierarchy mode — 조/항/호/목 from 본문조회
- [ ] **Table mode** — fixed-width box-drawing annexes (`┌ ├ │ ┬ ┼` at consistent offsets), one `Clause` per row with `path_segments = [별표N, row]`. Mechanical and deterministic; **no LLM in the parsing path**
- [ ] Both modes used by both domains — the split is prose vs table, not SaMD vs Cosmetic
- [ ] Canonicalization step per profile, taken over from [phase1.0](phase1.0_ingestion.md)'s per-connector minimum — it feeds `content_hash`, never the archived or cited bytes

### Annex storage — **decide by W4, owned here, consumed by 1.3**

- [ ] **Resolve [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 3: does `annex_rows` exist alongside `clauses`, and which service owns it?** [phase1.3](phase1.3_retrieval_qa.md) assumes a structured row store exists and accepts on exact-match ingredient lookup; nothing currently creates one. This decision is **this phase's**, not 1.3's — 1.3 inherits the answer and cannot build the index without it
- [ ] Feeds the same decision: 별표 1 of 화장품 안전기준 규정 is 340,074 chars / 7,367 lines, so one `Clause` per row is tens of thousands of rows per 고시 ([ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 2)
- [ ] Outcome goes in an **ADR**, not this file — it changes the storage model and 1.3 reads it

### 시행예정 (pending-effect) versions — **carried over from [phase1.0](phase1.0_ingestion.md), and it gates detection latency**

- [ ] **Ingest 시행예정 법령 via `target=eflaw`.** Polling 현행 only means an amendment is invisible from 공포 until 시행. Measured live 2026-08-03: **8 amendments across the 9 gated 법령 are already 공포'd and unseen**, the oldest promulgated 2025-12-30 — seven months before the check. Detection latency for those is 시행 − 공포, i.e. **2 months to 2.4 years**, so the ≤24h gate is not merely unmet but structurally unmeetable without this
- [ ] **A version is one `MST` (법령일련번호), not one 시행일자.** 화장품법 returns 6 pending rows but only **4 distinct MST**: one amending act (MST 282015, 공포 2025-12-30) carries three 시행일자 — 2026-12-31, 2028-01-01, 2029-01-01. Keying versions on 시행일자 would triplicate identical text
- [ ] **Those three dates are staged application, and they belong at clause level** — `조문시행일자`, which the spike already confirmed is present per clause. This is [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5's per-clause `effective_date` override, met in the wild rather than in theory
- [ ] **Version-level `effective_date` = the earliest 시행일자 for that MST**; clauses carry the rest
- [ ] **ADR needed before building.** The eflaw envelope states 시행일자 outright, so for these versions it is *fetch* metadata — the same category as 공포일자 → `published_at` — not the parse output [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5 describes. [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) is untouched: it governs 부칙 *text* extraction, where a date must never be guessed. Write the amendment before the code, not after
- [ ] **History (연혁) stays out of Phase 1.** `eflaw` also returns superseded versions — 20 rows for 화장품법 back to 2018. Backfilling them would give diff baselines we did not archive ourselves, which the citation contract does not accept ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 12). Phase 2 at the earliest
- [ ] Scope check: 9 documents → **17 versions** (현행 + 8 distinct pending MST) at the time of measurement, and that count moves with every new 공포

### Structure drift — the Phase 1 hook

- [ ] `structure_drift_alerts` raised against the **source** when the parse stage fails closed: zero clauses extracted, clause count beyond threshold, expected root missing. Creates **no** version and emits **no** change event ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 6, which says Phase 1 builds the hook even though Tier C is [phase2.0](phase2.0_tier_c_scale.md))
- [ ] Resolution restricted to `ra` — one of exactly two Phase 1 human-assertion actions in CLAUDE.md § Security, alongside locking an IR
- [ ] Threshold calibration is [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 5: clause-count delta is crude, and a large genuine amendment must not read as drift

### Diffing

- [ ] `clause_diffs(from_version_id, to_version_id, clause_path, change_kind, from_clause_id, to_clause_id, similarity)`
- [ ] `change_kind ∈ added | removed | modified | renumbered | moved`
- [ ] **Renumbering resolved explicitly, never reported as delete + add.** Primary signal is the authority's own: `조문변경여부`, `조문이동이전`, `조문이동이후` from law.go.kr. Content-similarity matching is the fallback for sources exposing nothing
- [ ] Low-confidence renumber matches queue for RA review
- [ ] Diffs computed **within one language** — KO for MFDS
- [ ] `ChangeEvent` emitted from `ClauseDiff`, fanned out to every claiming cell

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
- [ ] Fan-out reaches every claiming cell and no others — **verified against a synthetic multi-cell fixture, because the two gated cells share no real document.** In [import-source-map.md](../import-source-map.md) `mfds_cosmetic` (화장품법 family) and `mfds_samd` (의료기기법 family) have zero documents in common, and the FD&C Act — the natural M:N case — is FDA, first ingested in [phase2.0](phase2.0_tier_c_scale.md). Cell isolation is a CLAUDE.md non-negotiable test, so Phase 1 builds the fixture rather than deferring the test to Phase 2
- [ ] A single-cell document does **not** fan out to the other gated cell — the negative half of the same test
- [ ] Amending a cited clause flags the citation superseded and leaves its text resolvable

## Risks & open questions

- **Annex scale** ([ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 2) — 별표 1 of 화장품 안전기준 규정 alone is 340,074 chars / 7,367 lines. One `Clause` per row means tens of thousands of rows per 고시. **Owned here and due W4** (see *Annex storage* above); previously this file deferred it to 1.3 while 1.3 deferred it back here, leaving a critical-path decision with no owner.
- **Diff synchronously or async?** [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 4, and it is a structural choice in this phase: inline is simpler, splitting lets an improved profile re-diff historical versions without re-fetching. The ADR leans split; it costs a stage boundary. Decide with the clause schema, not after.
- **Multilingual is modelled, not built.** First real exercise is the EU spike. Do not let Korean-only assumptions leak into the schema.

## Deviations & decisions

_None yet._
