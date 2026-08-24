# Phase 1.1 — Normalization

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W3–W6 · **Status:** 🟢 done (2026-08-06) — 9/9 acceptance
  criteria, both falsifiers run against real ingestion and **not triggered**. Re-verified after the
  MFDS 행정규칙 backlog was seeded: **526 documents · 25,729 clauses · 4,839 annex table rows**
- **Governed by:** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md),
  [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) (drift · diff · dates),
  [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) (domain branching),
  [ADR-0012](../design/ADR-0012-annex-version-identity.md) (annex identity),
  [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) (effective dates)
- **Decided here:** [ADR-0014](../design/ADR-0014-annex-row-granularity.md) (annex rows are
  Clauses), [ADR-0015](../design/ADR-0015-diff-stage-boundary.md) (diff is its own stage),
  [ADR-0016](../design/ADR-0016-pending-effect-versions.md) (시행예정 versions)
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

- [x] `clauses(document_version_id, clause_path, path_segments, level, ordinal, heading, text)`
- [x] **plus `effective_date` and `effective_date_phrase`** — not optional and not deferrable to a
      later migration. [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5
      makes the version-level date *overridable per clause*, and
      [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) pairs every date column with
      its raw-phrase fallback. Adding them after the archive is parsed is the expensive change
      ADR-0002 warns about. *The 시행예정 premise for this turned out to be false — see deviation 4.*
- [x] **Domain-neutral** — no SaMD-only or Cosmetic-only column. 조/항/호 and Part/Subpart/§ are both
      ordered hierarchical paths. Guarded by a unit test that fails if a domain-named column appears
- [x] Immutable once written; populate `parser_version` (the column already exists)

### Parser profiles

- [x] Hierarchy mode — 조/항/호/목 from 본문조회 (`parsing/law.py`)
- [x] **Text mode for 고시 — unplanned, and mandatory.** 행정규칙 본문조회 returns **no clause
      structure at all**: 화장품 안전기준 규정 comes back as 11 flat `조문내용` blobs, one of which
      holds 제6조 with every 항 and 호 inside 9,062 characters. The tree has to be segmented out of
      text (`parsing/admrul.py`). This is a **source-shape** branch, not a domain one — both gated
      cells have 법령 *and* 고시 sources — so it does not trip the falsifier. See deviation 1
- [x] **Table mode** — fixed-width box-drawing annexes, one `Clause` per row. Mechanical and
      deterministic; **no LLM in the parsing path** (`parsing/tables.py`, `parsing/layout.py`)
- [x] **Decided: an annex clause path repeats 별표N** —
      [ADR-0014](../design/ADR-0014-annex-row-granularity.md) decision 3, so an annex citation reads
      correctly when rendered apart from its document. A `표N` segment was added to ADR-0006's
      two-segment sketch: 62 tables sit across only 24 별표, so `[별표N, row]` cannot survive a table
      being inserted ahead of another, and there is nowhere to hang the per-table column map
- [x] Both modes used by both domains — the split is prose vs table, not SaMD vs Cosmetic
- [x] Canonicalization step per profile, taken over from [phase1.0](phase1.0_ingestion.md)'s
      per-connector minimum — it feeds `content_hash`, never the archived or cited bytes

### Annex row granularity — decided W4, owned here, consumed by 1.3

- [x] **Resolved in [ADR-0014](../design/ADR-0014-annex-row-granularity.md): `annex_rows` is not
      created.** An annex table row is a `Clause` addressed by `clause_path` like any other, so
      `ir_citations` needs no branch and there is no second store to keep in sync.
      [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 3
      and [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) open question 2 are
      both closed by it
- [x] **Re-measured from the WORM archive, 2026-08-06.** Agrees with the 2026-08-05 count to within
      ~2%; the residual is where a table boundary falls when two tables abut.

      | | 별표 | 서식 | 별지 | total |
      |---|---:|---:|---:|---:|
      | annex documents | 81 | 173 | 24 | **278** |
      | documents with ≥1 table | 24 | 104 | 4 | 132 |
      | tables | 62 | 114 | 4 | 180 |
      | **data rows** (excluding headers) | **1,937** | 41 | 21 | **1,999** |
      | non-blank physical lines | 20,265 | 10,179 | 1,527 | 31,971 |

      Two facts beyond the row count changed the design: **only 24 of the 81 별표 contain a table at
      all** (the rest are prose), and a table-bearing annex usually holds **several** tables.
- [x] **Row columns are typed per table in `jsonb`** (ADR-0014 decision 4). The 표 clause carries the
      ordered header; each 행 carries `{label: value}`. Verified against the query ADR-0006 names:
      `갈라민트리에치오다이드` resolves to `별표1/표1/행1` by exact match on 원료명
- [x] Outcome recorded in an **ADR**, not here

### 시행예정 (pending-effect) versions

- [x] **Ingest 시행예정 법령 via `target=eflaw`** — `PendingLawConnector`, one source per 법령, nine
      seeded and enabled
- [x] **A version is one `MST` (법령일련번호), not one 시행일자.** Confirmed live 2026-08-06: MST
      282015 returns three list rows and exactly one 본문
- [x] **Version-level `effective_date` = the MST's 시행일자**, taken from the envelope
- [x] **Verified in production, not only in a test.** The nine sources ran on cadence on 2026-08-06
      and ingested 7 pending versions. 화장품법 now holds 5 versions, and **MST 282015 — the one with
      three 시행일자 — produced exactly one** (공포번호 21302, `effective_date` 2026-12-31, the
      earliest of its three). A query for the in-force text still returns 현행 (공포번호 20901,
      2026-04-02). 시행령/시행규칙 correctly returned `unchanged` with zero artefacts — they have no
      pending amendments
- [ ] ~~Those three dates are staged application, and they belong at clause level — `조문시행일자`~~
      — **false, and measured.** `조문시행일자` is **constant within a document** across all nine
      gated 법령; it restates the snapshot date rather than overriding it. The staged dates live in
      부칙 prose and are conditional on the *addressee's annual revenue*, so no clause-level date is
      correct. They are retained verbatim in `effective_date_phrase`
      ([ADR-0016](../design/ADR-0016-pending-effect-versions.md)). See deviation 4
- [x] **ADR written before the code** —
      [ADR-0016](../design/ADR-0016-pending-effect-versions.md)
- [x] **History (연혁) stays out of Phase 1.** The connector filters on `현행연혁코드 = 시행예정`
- [x] Scope check: 9 documents, each with a 현행 and a 시행예정 source. The pending MST count moves
      with every new 공포, so it is measured per fetch rather than pinned here

### Structure drift — the parse-stage half

- [x] Raise on **zero clauses extracted** (`ZERO_CLAUSES`) and on **clause count beyond threshold**
      (`CLAUSE_COUNT_DELTA`). Creates **no** version and emits **no** change event
- [x] **`EMPTY_ANNEX_BODY` is now raised**, where 1.0 defined it and never did. An annex whose
      `별표내용` is empty fails closed; `attachments` holds the authority's own HWP/PDF links as the
      documented fallback for a human to follow. **Decided: alerted, not auto-fetched** — HWP
      extraction is a workstream, not a library call, and it is off the Phase 1 critical path
- [x] Threshold calibrated at **0.5** and the reasoning recorded on the constant
      (`CLAUSE_COUNT_DRIFT_RATIO`): the largest genuine amendment in the corpus is a 6.8% move, and
      rejecting a real amendment is the worse error because it is invisible to the coverage gate.
      [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 5 stays open
      pending more amendments to calibrate against

### Diffing

- [x] `clause_diffs(from_version_id, to_version_id, clause_path, change_kind, from_clause_id, to_clause_id, similarity)`
      plus `from_clause_path`, `match_basis`, and the RA-review fields
- [x] `change_kind ∈ added | removed | modified | renumbered | moved`, each carrying information:
      `moved` is **same clause number, different parent**, never a shift in reading order. See
      deviation 8 — the first implementation emitted 1,209 events for an amendment with 37 real edits
- [x] **A re-parse invalidates the diffs derived from it**, in both directions, and re-enqueues the
      diff for the version and its successor. See deviation 9
- [x] **Renumbering resolved explicitly, never reported as delete + add.** Primary signal is
      `조문이동이전`/`조문이동이후`; content similarity is the fallback for sources exposing nothing
- [x] Low-confidence renumber matches queue for RA review (`needs_review`, between
      `RENUMBER_MATCH_RATIO` and `RENUMBER_CONFIDENT_RATIO`)
- [x] Diffs computed **within one language** — KO for MFDS
- [x] `ChangeEvent` emitted from `ClauseDiff`, fanned out to every claiming cell
- [x] `조문변경여부` is stored per clause (`authority_changed`) so the authority's own change history
      can be reconciled against our computed diff. **The reconciliation itself is deferred to 1.6**,
      where the detection-coverage gate is scored — storing the signal is what 1.1 owed
- [x] **Decided: diff is its own stage** — [ADR-0015](../design/ADR-0015-diff-stage-boundary.md),
      closing [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 4

### Citation support

- [x] Superseded-citation detection: a diff touching a cited clause path marks the citation
      `superseded` and records which diff did it. **The citation is never rewritten**

## Falsifiers — run against real ingestion, 2026-08-06

Both were run over the **whole archived corpus** — 526 documents and 25,729 clauses after the MFDS
행정규칙 backlog was seeded on 2026-08-06 — rather than against a fixture, and both are also encoded
as tests so they keep running.

- [x] **Annex representation (W3–4). NOT TRIGGERED.** A 화장품 안전기준 규정 limit-table row is a
      `Clause`:

      ```text
      clause_path   : 별표2/표1/행1
      path_segments : ["별표2", "표1", "행1"]
      row_columns   : {"원료명": "글루타랄(펜탄-1,5-디알)", "사용한도": "0.1%",
                       "CAS No.": "111-30-8", "비고": "에어로졸(스프레이에 한함) 제품에는 사용금지"}
      ```

      4,839 table rows in the store, and exact-match lookup on 원료명 resolves
      `갈라민트리에치오다이드` → `별표1/표1/행1`. No second addressing scheme was invented.

- [x] **Cross-domain (W5–6). NOT TRIGGERED.** Both cells use the **same three profiles**, selected
      by document shape and never by domain:

      | cell | law / decree / rule | notice | annex |
      |---|---|---|---|
      | `mfds_cosmetic` | `law_structured` | `admrul_text` | `annex` |
      | `mfds_samd` | `law_structured` | `admrul_text` | `annex` |

      No domain-specific column on `clauses`, no second stage between Section Extraction and IR
      extraction, no domain-forked parser. The one branch that exists is 법령 vs 고시 vs 별표 —
      a *source shape* both domains have.

> The live API test on 2026-07-29 did **not** trigger the falsifier either, but it tested a spike
> rather than real ingestion. This run is against the archive the pipeline actually produced.

### What "escalate" means, concretely

Written down before the falsifiers run, because the failure mode is not refusing to escalate — it
is **not noticing that you already decided not to**. Adding one column is a five-minute change that
feels like progress; it is also the exact action ADR-0002 decision 3 forbids, and nothing in a diff
review makes it look different from ordinary schema work.

**A falsifier has fired if any of these is true.** These are the triggers, not judgement calls:

1. A column is proposed on `clauses` that only one domain populates.
2. A parser stage is proposed that runs for one domain and not the other.
3. A second stage is proposed between Section Extraction and IR extraction.
4. An annex table row cannot be addressed by `clause_path` without inventing a second scheme.

**When one fires, in this order:**

1. **Stop the change.** Do not commit the column, the stage, or the workaround — not even behind a
   flag or a TODO. A merged workaround is a decision taken silently.
2. **Write the evidence down**: the document and clause that cannot be represented, what was tried,
   and why the shared model fails on it. One paragraph is enough; it becomes the ADR's Context.
3. **Say it out loud to the human who owns the plan**, naming the ADR at risk (0002 decision 3 or
   0004 decision 3) and the consequence: *Phase 2's six-cell build rests on this, so a Phase 2
   re-plan is on the table.* Not "we hit a snag."
4. **The decision is an ADR**, not a plan-file note — it changes the canonical model.
5. **1.2 and 1.3 do not start against the affected model** until that ADR exists. They inherit the
   clause schema; building on a model known to be wrong converts one bad week into three.

**What does *not* count as escalation:** a comment, a TODO, a `# domain-specific for now`, a
column that is nullable "so it does not really branch", or raising it and proceeding while waiting
for an answer. The point of a falsifier is that it stops something.

## Acceptance criteria

All nine are covered by `tests/integration/test_phase1_1_acceptance.py`, one test per criterion.

- [x] 화장품법 and 의료기기법 both parse to clauses through one pipeline, no domain branch
- [x] A renumbered-but-unchanged clause reports `renumbered`, never delete + add — integration test
- [x] An annex limit-table row round-trips as a `Clause` and is addressable by `clause_path`
- [x] A parse yielding zero clauses raises drift, creates no version, and emits no change event
- [x] **A 시행예정 version is ingested with a future `effective_date` and does not displace 현행** — a
      query for the current text still returns the in-force version
- [x] **One MST carrying three 시행일자 produces exactly one version**, with the earliest date at
      version level — **and the remainder in `effective_date_phrase`, not on clauses** (ADR-0016
      corrects the second half of this criterion; see deviation 4)
- [x] Fan-out reaches every claiming cell and no others — verified against a **synthetic multi-cell
      fixture**, because the two gated cells share no *regulation* in common: `mfds_cosmetic`
      (화장품법 family) and `mfds_samd` (의료기기법 family) have zero documents in common, and the
      FD&C Act — the natural M:N case — is FDA, first ingested in
      [phase2.0](phase2.0_tier_c_scale.md). Cell isolation is a CLAUDE.md non-negotiable test, so
      Phase 1 builds the fixture rather than deferring the test. *(The MFDS RSS boards are now a real
      shared case — one Document claimed by both cells — so the synthetic fixture is a deterministic
      complement to it, not a substitute for something that does not exist.)*
- [x] A single-cell document does **not** fan out to the other gated cell — the negative half
- [x] Amending a cited clause flags the citation superseded and leaves its text resolvable

## Risks & open questions

- ~~**The MFDS RSS feed is registered twice and would ingest twice.**~~ — **closed by the W3
  reconnaissance (2026-08-05).** The feed is per-board (`brdId`), and MFDS boards are
  regulator-wide, so `data0008` 제개정고시등 genuinely belongs to both gated cells. Feed identity now
  comes from the authority's `brdId` rather than our source slug, so the two subscriptions resolve
  to **one Document claimed by two cells** — verified live on three boards.

- ~~**Annex row granularity**~~ — **closed by
  [ADR-0014](../design/ADR-0014-annex-row-granularity.md)**: rows live in `clauses`, columns in
  `jsonb`, no `annex_rows` table.
- ~~**Diff synchronously or async?**~~ — **closed by
  [ADR-0015](../design/ADR-0015-diff-stage-boundary.md)**: its own task, dispatched by name.
- **Multilingual is modelled, not built.** ~~First real exercise is the EU spike.~~ **The first real
  exercise is now NMPA in 2.0c** — the EU group moved to Phase 4 on 2026-08-24 and took the spike
  with it. This matters more than a pointer change: EU would have met a second language on Tier A/B
  sources with stable ELI keys, while NMPA meets it alongside full-weight Tier C scraping and a
  curated `canonical_key`. Do not let Korean-only assumptions leak into the schema — there is now no
  cheap rehearsal before that.
- ~~**Detection latency stays unmeasurable for the 법령 sources until 시행예정 ships.**~~ — **the
  connector ships in this phase.** Latency becomes measurable once the sources have run on cadence;
  1.6 scores it. Report it as unmeasured rather than zero until then.
- **Clause-path disambiguation runs at 4.95%, and the rate is rising with corpus diversity** —
  1,274 of 25,729 clauses carry a `~N` suffix because a free-form annex outline restarts its
  numbering under a section it never marked. It was 0.95% (95 of 10,036) over the six curated 고시;
  seeding the other 53 multiplied it fivefold, which says the discovered-ladder segmenter meets
  outline shapes it cannot nest rather than that the corpus got messier. Paths stay unique and
  deterministic so nothing is lost or mis-cited, but a `~3` in a citation reads badly and one in
  twenty is no longer a rounding error. **Measure per document shape in 1.6** before deciding
  whether to extend the ladder or accept it.
- **Drift-threshold calibration** ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md)
  open question 5) stays open. 0.5 is reasoned, not measured against a real drift event, because the
  corpus has not produced one yet.

## Deviations & decisions

<!-- Architecture changes go in an ADR, linked here. -->

**1. A third parser profile was needed: 고시 bodies carry no clause structure.** The plan assumed one
hierarchy mode reading 조/항/호/목 "from 본문조회". True for 법령; **false for 행정규칙**, which
returns flat `조문내용` text blobs — 11 of them for 화장품 안전기준 규정, one holding 9,062 characters
of 제6조. A text segmenter was built alongside the structured one. *This does not trip the falsifier*:
the branch is 법령 vs 고시, a source shape both gated cells have, and both profiles produce the same
clause tree with no domain-conditional code.

**2. Two outline ladders, not one.** 고시 bodies use the fixed legal outline (편·장·절·관 → 조 → 항 →
호 → 목). Annexes invent their own — 유통화장품 안전관리 시험방법 runs `Ⅰ.` → `1.` → `가)` → `①` →
`-`, putting a 항 marker *below* a 목-like one — so annex prose discovers its ladder from the order
in which marker styles first appear. Forcing the legal precedence on annexes collapsed one annex into
137 clauses sharing four paths.

**3. `irs` and `ir_citations` were created here rather than in 1.2.** *"Amending a cited clause flags
the citation superseded"* is a 1.1 acceptance criterion, and an untestable criterion is not a
criterion. 1.1 writes only `superseded_at` / `superseded_by_diff_id`; `extraction_runs` and
`clause_classifications` remain 1.2's, along with everything that fills these two tables.

**4. `조문시행일자` is not a clause-level override, and the acceptance criterion was wrong.** Both
this file and [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) open question 2 stated
that the several 시행일자 of one MST are staged application carried per clause in `조문시행일자`.
Measured across all nine gated 법령: the field is **constant within a document** and always equals
the document's own 시행일자. The authority models staged application by publishing separate
consolidated snapshots of one MST — which it then declines to serve individually (`efYd` is ignored)
— plus 부칙 prose whose dates are conditional on the addressee's annual revenue. The remainder
therefore goes in `effective_date_phrase`, not on clauses.
[ADR-0016](../design/ADR-0016-pending-effect-versions.md) records this and partly withdraws ADR-0003
open question 2. The clause-level column stays, on ADR-0003 decision 5's own merits.

**5. `effective_date` is taken from the envelope, not derived from 부칙.** ADR-0003 decision 5
classifies it as a parse output extracted from 부칙 text. `기본정보/시행일자` states it outright for
both 법령 and 행정규칙, and re-deriving it from prose would be a worse estimate of a published fact.
The parse stage still writes it — one writer, and a bad date is fixed by re-parsing — but the value
comes from the envelope. Amended in [ADR-0016](../design/ADR-0016-pending-effect-versions.md)
decision 3.

**6. A drift-failed parse deletes the version.** The criterion says "creates no version", but 1.0
creates the version at archive time and hands off to parse by task name, so by the time drift is
detected the row exists. Deleting it keeps the stronger invariant — **a `DocumentVersion` that exists
has clauses and is citable** — instead of leaving a half-version that would make retrieval answer
"current text" with nothing. The archived blob is untouched (it is write-once) and the
`fetch_observation` remains, so the evidence of what was fetched survives. Alerts are deduped per
(source, signal, document) because a permanently broken envelope would otherwise raise one per poll.

**7. `target=eflaw` has no 본문조회 endpoint.** It answers **HTTP 500 with an XHTML error page** — a
failure signature beyond the three HTTP-200 ones 1.0 handles. Pending bodies are fetched through
`target=law&MST=…`, and the connector refuses any non-XML body rather than archiving an error page
as regulation text. `efYd` is silently ignored by the API and is never sent: a parameter that
appears to work while returning the wrong snapshot is worse than one that errors.


**8. `moved` was emitting an index shift, and it buried the real changes.** `ordinal` is a single
document-wide reading sequence, so inserting one article shifts every clause below it. Reported as
`moved`, one 화장품법 amendment with **37 real edits produced 1,209 change events**. In a numbered
hierarchy the *path is the position* — 제8조 always follows 제7조 — so a shifted index says nothing
a reader could act on. `moved` is now **same clause number, different parent** (제8조 relocated from
제2장 to 제3장), a clause whose own number changed is `renumbered`, and same-path-same-content emits
nothing. Corpus-wide: **2,373 diffs → 109**, all real (81 modified, 16 removed, 12 added). Recorded
in [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 7.

**9. A re-parse was orphaning the diffs derived from it.** `clause_diffs` references clauses
`ON DELETE SET NULL`, so replacing a version's clauses left diffs with null endpoints — describing a
parse that no longer existed, with live `ChangeEvent` rows still attached. One corpus re-parse
orphaned 2,373 of them. `parse` now deletes the diffs touching that version in both directions and
re-enqueues the diff for it and its successor, so the chain heals. ADR-0015 makes re-parsing routine;
a routine operation must not degrade the change history.

**10. An annex now takes its own `effective_date` where the authority states one.** `별표시행일자
문자열` — the field ADR-0012's whole rationale rests on — was being ignored, and every annex
inherited its parent 고시's date. It is easy to miss: it sits in `기본정보`, not in the `별표단위` it
describes, shaped as `20260701:별표9,별표10,서식12의2`. 21 of 278 annexes are named in one, and in
every case the stated date equals the parent's — **so no value changed.** It is read anyway because
an inherited date that happens to be right is not a stated one, and this value is the fourth element
of the Citation tuple. Recorded as an amendment to
[ADR-0012](../design/ADR-0012-annex-version-identity.md).

**11. An RSS feed must survive the parse stage, and nearly did not.** MFDS boards are **change
signals**: `data0008` 제개정고시등 announces 고시 amendments with a title and a `pubDate` and carries
no 고시 text, which arrives separately through 행정규칙 본문조회. So a feed has no clauses — correct,
and not a gap. But the parse stage answers an unknown `doc_type` with `ParseError(MISSING_ROOT)`, and
deviation 6 has `_fail_closed` answer *that* by **deleting the version**. Every board publication
would therefore have destroyed the archived record of what the board said at time T — the one thing
that makes the feed usable as a latency signal — and raised a drift alert for it. Latent rather than
observed only because the four feed versions predate the parse stage. `is_parseable()` now gates
both ends: ingest does not enqueue a parse for a feed, and the parse stage skips one if something
enqueues it anyway. `parse_document` stays strict, so a *regulation* type added without a profile is
still caught loudly. The smell that found it: every re-parse script I wrote had to say
`where doc_type != 'feed'` — a guard living in each caller instead of in the code.
