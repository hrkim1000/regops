# Phase 1.6 — Evaluation & pilot

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W2–W16 (golden set starts W2; the rest is W7–W16) · **Status:** 🟡 harness built and the machine-measurable half measured (2026-08-13); **the human and pilot halves are now prepared to the start line (2026-08-14)** — a second reviewer is available and has a packet, and the pilot has a runbook — but neither has run, so the four gates that need a person or a pilot are still **미측정** and the report still recommends `INCOMPLETE` rather than guessing
- **Governed by:** [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 7, [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md), [development-plan.md](../development-plan.md) § 5
- **Depends on:** all of 1.0–1.5
- **Owner:** Regulatory domain (RA/QA), with AI/ML for the harness

---

## Goal

Produce the numbers. **The purpose of the PoC is measurement, not a demo** — No-Go is called if four
or more of the six gates fall short. This phase exists to make that judgement defensible rather than
arguable.

Sequencing is the whole game here: two exercises are only valid if they happen **before** the thing
they measure.

## Scope

**In:** golden query sets, IR ground-truth markup, evaluation harness, pilot operation, the M4
Go/No-Go report.

**Out:** fixing what the measurements reveal — that is the Phase 2 backlog.

## Tasks

### Golden query set (W2 → W8)

- [x] Items built per domain — **SaMD and Cosmetic scored separately.** A shared score hides one domain failing behind the other passing. **162 per cell, not 200** — see deviation 3
- [x] Composition covers **all four axes [ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) open question 4 names** — identifier lookups, paraphrased conceptual queries, **effective-date-straddling cases**, and **deliberate mis-citation traps**. The inventory is closed in `EvaluationAxis` and the floor is enforced per axis, so a passing score cannot rest on identifier lookups
- [x] Cross-domain questions — asked in the wrong cell, where the correct behaviour is to decline rather than answer from the neighbouring cell ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 9). 30 per cell, drawn from the *neighbouring* cell's real obligations, and `validate` rejects one authored with `cross_cell=true` because that defeats the item
- [x] Known-unanswerable questions — 20 per cell, including Tier D material (ISO 13485, IEC 62304, IEC 62366, 약전), where refusing is correct **and** doubles as a Tier D check
- [x] **Per-axis coverage stated explicitly** rather than sizing up — the option the task itself offers. `validate` prints the per-axis table and fails below `GOLDEN_SET_MIN_ITEMS_PER_AXIS`
- [ ] **Authored by RA.** Both sets carry `ra_signed_off: false`, `validate` reports them as *not citable as gate evidence*, and `score` exits non-zero. Seeding proposes; only an RA makes them count — see deviation 2

### IR ground-truth markup (W7–8) — sequencing is load-bearing

- [x] **The denominator is drawn and fixed** — `evaluation.cli sample` draws 40 조-level clauses each from 화장품법 @ 2026-04-02 and 의료기기법 @ 2026-07-01 by a *recorded* seed, and writes a markup template pre-populated with those paths and nulls. Selection reads `clauses` and never `irs`, so a clause cannot be quietly dropped later for having turned out to be hard
- [ ] RA hand-marks obligations in that sample
- [x] **Blind to extractor output — enforced as far as tooling can.** The sample is drawn without reference to extraction, the template says in its own text to mark from the clause text alone, and the submission sheet is deliberately **not** pre-filled with what the detector found. The rest is a person's discipline, and the harness says so rather than pretending to check it
- [x] ~~Runs in parallel with [phase1.2](phase1.2_ir_extraction.md) work~~ — **the parallelism did not happen.** 1.2 closed 2026-08-07 with no markup authored, so the markup will be written while a working extractor exists. Blindness is therefore the *only* protection left, not a belt-and-braces one. Recorded in [docs/eval/README.md](../eval/README.md) where the marker will read it
- [ ] Without it, extraction **recall** is unmeasurable and the gap-analysis pillar has no evidence base. `extraction_against_markup` is written and tested; it has no markup to run against

### Harness (W9–10)

- [x] Automated regression over both golden sets; per-domain, per-cell, **and per-axis** reporting. Resumable — the run artifact, not the process, is the run
- [x] **Submission-requirement detection precision/recall** against an RA-marked sample. The pattern yields 102–103 procedures where looser and stricter variants gave 341 and 92; nobody has confirmed which is right, and the feature ships with that stated ([phase1.5](phase1.5_frontend.md) deviation 6). `score_detection` keeps false positives (a 기준 list read as a document list) apart from false negatives — the first is visible to a user and the second is not. The markup sheet is drawn (55 candidate clauses for Cosmetic, 97 for SaMD) and **unmarked**
- [x] Extraction precision, recall, and citation correctness against the ground truth — named `clause_level_precision` / `clause_level_recall` because the markup format records how *many* obligations a clause yields, not which ones, so they are upper bounds. Atomicity agreement still runs through `scripts/ir_agreement.py` and still has **no markup to run against**; until a second RA is funded it reports **test–retest, not inter-rater** ([phase1.2](phase1.2_ir_extraction.md) deviation 3), and that caveat is printed with the number
- [x] Citation accuracy and hallucination rate measured here — **not inferred from unit coverage**. The harness computes the mechanical half of each and returns the gate itself as 미측정 until a blind worksheet comes back; see deviation 1
- [x] **"Needs verification" rate reported per domain beside them** ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 7), as a `Guard` in the report rather than as a gate. Answer rate and refusal rate lead the Overall block of every scored run, above the two gates they keep honest
- [x] Model, **rule** and prompt versions pinned and recorded with every run — and the model is read back off the `answers` rows rather than off a constant, because what the report needs is what actually answered
- [x] **Extraction-determinism regression** ([ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 1) — `determinism` compares two *completed runs* by `extraction_run_id` (not by version: re-extracting leaves both runs' rows, and a version-level count would report perfect stability by addition), refuses to compare across regimes, and **reports the drift rate** rather than asserting zero
- [x] **Score detection coverage against *scheduled* polls, not observed ones.** A day the poller did not run leaves no row in `fetch_observations` at all, so coverage computed over observations divides by the polls that happened rather than the polls that were due — and downtime silently *improves* the number. Observed for real on 2026-08-04 ([phase1.0](phase1.0_ingestion.md) risks): 28 observations on 08-03, 16 on 08-05, none on 08-04 while the stack was down. Derive expected polls from `source_schedules.interval_seconds` over the measurement window and report the shortfall as an explicit **uptime caveat** beside the gate. A gate that improves when the system is off is not measuring the system

### Pilot (W11–16)

*Instrumented and **operationalised**, not run. Every measurement below exists and is tested, and
[docs/eval/pilot-runbook.md](../eval/pilot-runbook.md) (2026-08-14) turns them into a start date;
no users have been onboarded — see deviation 12.*

- [ ] Freeze build at W11–12; onboard 20–30 users in one business unit; capture baseline —
      **procedure written, not executed.** The runbook leads with the two constraints that cannot be
      repaired afterwards: the baseline is captured *before* access, and the cohort is fixed *before*
      week 1
- [ ] **Four consecutive weeks of real usage — the retention gate cannot be compressed**
- [x] **Retention is computed from `queries.asked_by`, not from logins** — voluntary use means a question asked, and a session opened is not use. `score_retention` intersects across *every* week in the window rather than counting active weeks, so a user active in weeks 1, 2 and 4 does not clear a four-consecutive-week bar
- [x] **The cohort must be fixed before the four weeks start** — `pilot_cohort.template.json`. A cohort assembled afterwards from whoever kept using it scores 100% every time, and dropping a non-returner is the single easiest way to manufacture a passing number
- [ ] Blind accuracy assessment by RA staff against both golden sets — **the packet is written**
      ([docs/eval/reviewer-packet.md](../eval/reviewer-packet.md)) and a second reviewer is available
      (deviation 11), so this is now scheduling rather than an open question of who
- [x] **The blind worksheet is built** — one row per (answer, citation) with the claim and the cited clause text, and deliberately *without* the expected answer, the expected paths, the confidence or the verification verdicts. Rows are shuffled by a **recorded** seed, because run order groups items by axis and the thirty-first identifier lookup is not read the way the first was. A blank `supports` cell raises rather than defaulting either way
- [ ] Research-time-savings measurement against the existing manual process for matched query types
- [x] **The baseline template states both halves of the gate** — captured *before* access, and *for the same query type*. It also states that the measurement is the analyst's time to a usable answer, which includes reading the citations, not the harness's `elapsed_seconds`

### EU spike close-out (W12)

- [ ] **EUR-Lex fetch for MDR (EU) 2017/745 at reduced depth** — transferred from [phase1.0](phase1.0_ingestion.md). Non-gated and scheduled W3→W12, so it never fit inside 1.0's W1–W4 window; the findings memo lands here regardless. **Explicitly carried, not dropped** (2026-08-13): it counts toward no exit criterion and needs a connector plus a parser profile, which is build work in a slice that is otherwise about measurement
- [ ] Findings memo: multilingual normalization and Tier C effort estimate for Phase 2
- [ ] Does not count toward exit criteria

### Go/No-Go report (W16)

- [x] Per-cell measurement against all six gates, with each gate carrying its threshold, its method, and the evidence it was computed from
- [x] **An unmeasured gate is neither a pass nor a failure.** It renders as `미측정` with the reason, and any unmeasured gate makes the recommendation `INCOMPLETE` rather than `GO` or `NO-GO` — four shortfalls call No-Go, so a coerced default would be making the decision rather than informing it
- [x] **No-Go is counted per cell**, and the two gates that are not cell-scoped (retention, research-time savings) count against *every* cell rather than none — matching shortfalls by slug alone would mean a failed retention gate could never call No-Go
- [x] Deviations log consolidated from every phase file — read from the files rather than restated, so it cannot go stale
- [ ] Phase 2 backlog and re-plan recommendation — written at W16 against the numbers, not now

## The six gates — measured per gated cell

| Gate | Threshold | Method |
|---|---|---|
| Detection coverage | ≥ 95% | Share of actual amendments captured, verified by after-the-fact manual comparison. **Score against *scheduled* polls, not observed ones** — see below |
| Detection latency | ≤ 24h | Authority publication → owner alert |
| Citation accuracy | ≥ 90% | Share of cited clauses that actually support the answer, blind RA assessment |
| Hallucination rate | ≤ 2% | Outputs citing non-existent clauses or contradicting source text |
| Research time savings | ≥ 30% | Versus the manual process for the same query type |
| Pilot retention | ≥ 60% | Voluntary use ≥ 1×/week for 4 consecutive weeks |

**A cell that misses is not offset by the other passing.** No-Go if four or more fall short.

Two failure modes the six gates do **not** catch, both reported alongside them rather than gated:
the **"needs verification" rate** (refuse everything → citation accuracy and hallucination rate both
pass) and **alert precision** (alert on everything → detection coverage and latency both pass, see
[phase1.4](phase1.4_monitoring.md)). Neither is a gate in Phase 1; both belong in the Go/No-Go
report, because a gate set that can be satisfied by a degenerate system is evidence of nothing.

## What was built

| Unit | Kind | Module |
| --- | --- | --- |
| Golden-set schema, axis-coverage and sign-off validation | pure function | `scripts/evaluation/goldenset.py` |
| Set seeding from the clause store | pipeline | `scripts/evaluation/seed.py` |
| Cross-boundary reads (all four services' tables, read-only raw SQL) | pipeline | `scripts/evaluation/corpus.py` |
| Service reads and the minted-token client | pipeline | `scripts/evaluation/client.py` |
| **All scoring arithmetic** | pure function | `scripts/evaluation/score.py` |
| Scored run — resumable, regime-pinned | pipeline | `scripts/evaluation/run.py` |
| Blind assessment worksheet | pipeline | `scripts/evaluation/worksheet.py` |
| Gate measurement (coverage · latency · submissions · retention · extraction) | pipeline | `scripts/evaluation/measure.py` |
| The six gates as data, and the Go/No-Go report | pure function | `scripts/evaluation/report.py` |

**Nothing here is an agent.** The harness never calls `get_llm_client()`; it asks `assistant` a
question over HTTP and scores what comes back. A module that scored a model's output by asking a
model would need its own gate, which is the regress this whole slice exists to avoid.

`score.py` and `report.py` carry 45 unit cases (`scripts/evaluation/tests/`), written against the
failure modes the design prevents rather than against the implementation: a harness error must not
read as a refusal, a refusal must not read as an answer, an unmeasured gate must not read as a zero,
and three weeks of use must not read as four.

The corpus and its authoring rules are [docs/eval/README.md](../eval/README.md).

## Acceptance criteria

- [ ] Both golden sets complete and RA-signed before W9 — **complete (162 items per cell, six axes, every expected clause path resolved against the live corpus); not signed.** `validate` reports them as *not citable as gate evidence* and `score` exits non-zero until an RA signs
- [x] Ground-truth markup demonstrably blind — *as far as tooling can carry it*: the denominator is drawn by recorded seed from `clauses` alone, and the assessment worksheet withholds the expected answer, the expected paths, the confidence and the verification verdicts. The markup itself is not yet authored
- [x] Harness reproduces a scored run from pinned model + prompt versions — the regime travels on the run artifact, with `llm_model` read off the `answers` rows rather than off a constant
- [ ] All six gates measured per cell with stated method, not estimated — **two are measurable today and four are not.** The report renders the four as `미측정` with the reason and recommends `INCOMPLETE`; see deviation 1
- [ ] Go/No-Go report delivered at W16 with evidence attached — the generator is built and runs; the report it produces today is a scaffold with four holes in it, which is the honest state at W-not-16

## Risks & open questions

- **Risk 7 — key-person dependency (development-plan.md § 9). Partly mitigated 2026-08-14: a second
  reviewer is available.** The risk as written was one RA holding every role — golden-set designer,
  ground-truth marker, blind assessor, IR locker and final signoff — which made both "blind"
  exercises non-blind in practice, and it was **accepted rather than mitigated** at 1 FTE. The
  mitigation the entry itself asked for (*"budget a second RA reviewer, even part-time, to separate
  authorship from assessment"*) is now available, and
  [docs/eval/reviewer-packet.md](../eval/reviewer-packet.md) is what it is handed. Two consequences:
  the blind assessment is genuinely blind, and atomicity agreement becomes **inter-rater** rather
  than test–retest (deviation 11). What remains is that the *authoring* was still done by the
  system's own authors — the second reviewer reviews and signs, which is the separation that
  matters, but it is not the same as an independently authored set.
- **Retention needs 4 uncompressible weeks.** Any slip upstream eats the measurement window, not the build. Protect W13–16.
- **Research-time-savings needs a baseline** captured before the pilot starts, or the 30% is unfalsifiable.
- **Retrieval has no relevance floor, and there is now a measurement to tune one against.** Asked
  on 2026-08-11 in the running stack: *"화장품 안전성 검토 문서 제출 시기"* — a cosmetic question —
  with the ScopeBar on `mfds_samd`. Cell scoping worked; no cosmetic clause was used. But hybrid
  retrieval never returns zero rows, so it returned **eight hits scoring 0.018–0.030**, all of them
  blank 서식/별지/별표, and generation was handed application-form boilerplate and asked to answer.
  The model duly quoted a form (*"…제조(수입) 허가를 신청합니다"*) and cited `'전부 위탁의 경우)'`,
  which the mechanical citation check rejected.

  **The final state was correct** — 확인 필요 — and the design intends verification to catch this.
  The cost is that a question the system could refuse in 5 seconds takes 112. Two candidate fixes,
  neither to be chosen by eye: a floor on the vector arm's cosine plus "no lexical exact match at
  all", or excluding `form` passages from the vector arm (**1,018 of 7,640 passages are forms**, and
  a form passage is a title — short enough to score well against a short query). Decide with the
  golden set, scored per query shape, because a threshold set from two queries would start refusing
  real answers.
  **The instrument for deciding it now exists**: `score --out` reports per axis, so a candidate
  floor can be judged on what it does to `unanswerable` and `cross_domain` (where refusing is
  correct) *against* what it does to `conceptual` and `identifier` (where refusing is a failure).
  That is the trade-off, and it was previously being argued without a way to see it.
- **`no_retrieval` currently means "zero rows", which never happens.** The reason exists in the
  closed inventory and the metrics report it, but under hybrid retrieval nothing can produce it.
  Whatever floor the item above lands on is what will make that number mean something.
- **The local model, not the product, is currently the binding constraint on four gates.** At the
  pinned regime `gemma3:4b` misses its own 180-second ceiling on most questions, so citation
  accuracy, hallucination rate and research-time savings are all measured through a timeout. Any
  scored run at this regime measures the hardware. Run the Anthropic provider behind the same seam
  as a comparison before W9 — and record it as a *different regime*, not as an improvement to this
  one.

  **Staying at the pinned regime was reaffirmed on 2026-08-14**, which keeps every number already
  measured comparable and is the reason this entry is a risk rather than a task. Two consequences
  follow and are recorded where they will be read: **retention is a UX outcome**, so a participant
  who waits three minutes for 확인 필요 learns not to return and the gate faithfully records that as
  a fact about the hardware ([pilot-runbook.md](../eval/pilot-runbook.md) § the caveat this pilot
  carries); and the comparison run this entry recommends **cannot currently be executed at all**,
  because the Anthropic arm of the seam 400s on `temperature` (deviation 13).
- **A mis-citation trap was answered from neighbouring clauses on the first bounded run**
  (deviation 7). Both citations resolved, so neither the mechanical citation check nor the
  verification agent caught it. One observation is not a rate; the full mis-citation axis is 30
  items per cell and that is what will say whether this is a pattern.

## Deviations & decisions

**1. Four of the six gates are returned unmeasured, and that is the deliverable — not a shortfall
in it.** The temptation in a measurement slice is to produce six numbers, because six numbers look
like a finished phase. Three of these gates are human judgements and one needs a pilot that has not
run:

| Gate | Measurable today | Why not |
| --- | --- | --- |
| Detection latency | **yes** | both clocks are stored; unmeasurable alerts counted apart |
| Hallucination rate — mechanical half | **yes** | a cited clause either resolves at its version or it does not |
| Detection coverage | no | the denominator is what the *authority* published. The system's own count scores 100% by construction |
| Citation accuracy | no | whether a clause *supports* a claim is a reading |
| Hallucination rate — contradiction half | no | same |
| Research time savings | no | needs a baseline captured before the pilot starts |
| Pilot retention | no | needs 20–30 users and four uncompressible weeks |

So the report renders each as `미측정` **with its reason**, and any unmeasured gate makes the
recommendation `INCOMPLETE` rather than `GO` or `NO-GO`. A defaulted gate would not be a rounding
error: four shortfalls call No-Go, so coercing an unmeasured gate in either direction moves the
decision rather than the number. What the harness computes instead is each gate's mechanical half,
named for what it is — `citation_expected_match` is a **lower bound** on citation accuracy, not a
proxy for it.

**2. The golden sets are seeded and unsigned, and the harness enforces the difference.** Both cells
have 162 items across all six axes, every expected clause path resolved against the live corpus. All
of them were proposed by the system's own authors, which is not evidence however good the questions
are. `ra_signed_off` is therefore a field, it defaults false, `validate` prints *not citable as gate
evidence*, `score` exits non-zero, and `seed` refuses to regenerate a signed set. Seeding proposes;
only an RA makes it count.

Three axes are generated from the clause store and three are hand-authored, split on whether a
template produces a *faithful* instance or a plausible-looking one. Generating `mis_citation` is
**more** reliable than writing it by hand — a trap is only a trap if the clause provably does not
exist, and that is a database fact, where a hand-written trap can accidentally name a real clause.
Generating `conceptual` is not, because a paraphrase that reuses the statute's vocabulary is an
identifier lookup wearing a sentence.

**3. 162 items per cell, not 200.** The task offers the alternative itself — "either size up or
state per-axis coverage explicitly" — and this takes it: `GOLDEN_SET_MIN_ITEMS_PER_AXIS` is enforced
per axis per domain, and `validate` prints the per-axis table every time. A 200-item set that was
70% identifier lookups would have satisfied the count and measured the easy half; 162 with a floor
on all six axes cannot.

**4. Found by running it — `POST /queries` dispatched the answering task *before* committing the
question row.** A race the worker wins often enough to matter: it picked the task up, found no row,
logged `answer.unknown_query` and returned **success**, leaving a question that would never be
answered, with no retry and no signal — the asker watching a spinner to the 4-minute poll ceiling
([phase1.5](phase1.5_frontend.md) deviation 12 built that ceiling for a *slow* answer, not a lost
one). The first harness run hit it repeatedly and burned 600 seconds per affected item.

Committing first is strictly better rather than merely different. A crash between the commit and
the dispatch leaves a committed question with no worker, which is **visible** — `/qa/queries/{id}`
already renders a pending question with an elapsed clock — and re-dispatchable, because the row is
there to dispatch for. An orphaned task is neither. Two unit cases in `assistant` pin the ordering.

The other four dispatch sites were checked and are not affected: they enqueue work for rows
committed long before (a `document_version` that already exists), so a worker arriving early reads
the row it expects.

**5. Found by running it — `regulation-worker` and `regulation-beat` were in a restart loop, and
the beat is the scheduler.** Their images predated `pgvector` being added to `shared` (phase 1.3),
and `regops_shared.models.__init__` imports `answer.py` unconditionally, so both crashed on import
while the `regulation` API next to them answered normally. Compose names an image after the service
unless told otherwise, so `docker compose up -d --build regulation` had rebuilt one of the three.

**No source was being polled at all.** That is the exact failure the coverage task above is written
against, arriving on its own: the first measurement of it read **77.0% poll completion — 493 of 640
scheduled polls over 30 days, 147 missed across 85 sources**. Measured over *observed* polls the
same window would have read 100%, because a poll that never ran leaves no row to divide by. All
three regulation services now pin one `image:`, as do the monitoring and assistant pairs, so the
three tags are the same image id and a worker cannot silently diverge from its API again.

**6. The harness runs inside the stack, and mints its own token.** It needs the database, the four
services, and a bearer credential. Running it on a host would mean a `.env` holding a copy of
`JWT_SECRET` and a database URL per machine; asking `platform-core` to log in would mean a password
in a script to obtain a credential the process can already produce. Instead `docs/eval` is mounted
at `/eval` on the `regulation` container — the one that already carries `/scripts` — and the token
is minted for a *real* `users` row looked up by email, so `queries.asked_by` references a principal
that exists and the audit trail names a person. The mount is scoped to the evaluation corpus rather
than all of `docs/`: it is writable, and a harness has no business editing an ADR.

**7. Measured while proving the harness: the local model is the binding constraint, and the
mis-citation trap fired.** A bounded pass of 23 items (2 per axis per cell) at the pinned regime —
`ollama` / `gemma3:4b`, `LLM_TIMEOUT_SECONDS=180`:

| | `mfds_cosmetic` | `mfds_samd` |
|---|---|---|
| Answer rate / refusal rate | 18.2% / 81.8% | 16.7% / 83.3% |
| Citations resolving | 100% | 100% |
| Citation accuracy (lower bound, **not** the gate) | 40% (2/5) | 80% (8/10) |
| Hallucination, mechanical half | 0% (0/2) | **50% (1/2)** |
| Outcome accuracy — mis_citation · unanswerable | 100% · 100% | 50% · 100% |
| Outcome accuracy — conceptual · effective_date | 0% · 0% | 0% · 0% |

Three readings, and only the third is a product finding.

**The refusal rate is an artefact, not a result.** Most refusals are `model_unavailable` at 186–194
seconds — the 180-second ceiling missed by seconds. Conceptual and effective-date score 0% almost
entirely because nothing came back in time. Deliberately **not** retuned: raising the timeout
changes the regime, and this file's own rule is that a threshold chosen by eye from a handful of
observations is a guess with a decimal point. Comparing the Anthropic provider behind the same seam
is the obvious next run, and it is a *comparison*, not a fix.

**The refusal rate also makes the two citation gates meaningless here**, exactly as the design says
it would: a system refusing 80%+ of questions scores well on citation accuracy for the trivial
reason that it barely cites anything. This is the degenerate case the answer/refusal pair is
reported above the gates to expose, and it is exposing it on the very first run.

**The one real product finding: `samd-mis-002` answered a mis-citation trap and cited two forbidden
paths** — a 50% mechanical hallucination rate on the SaMD side, from two answers. The question named
a 조 that was never enacted, and the system answered from neighbouring clauses instead of declining.
Both citations *resolve* — they are real clauses — so the mechanical citation check could never have
caught this, and the verification agent did not either. This is precisely why the axis exists and
why the traps are generated from the clause store rather than written by hand.

**8. The blind worksheet shuffles by a *recorded* seed.** Run order groups items by axis, and an
assessor who has just worked through thirty identifier lookups reads the thirty-first differently.
An unrecorded shuffle would have been equally effective and impossible to audit — there would be no
way to show afterwards that the order was not chosen. The seed goes in the sidecar with the run id
and the list of fields deliberately withheld.

**9. The EU spike close-out is carried, not done.** EUR-Lex for MDR (EU) 2017/745 needs a connector
and a parser profile — build work, in a slice that is otherwise about measurement — and it counts
toward no exit criterion. Recorded here as outstanding rather than quietly dropped, which is the
failure mode this table exists to prevent.

**10. The harness nearly reported a 100% hallucination rate it had invented.** The first full run
died at its last step — one database session held open across 40 minutes of model-bound waiting,
closed by the server underneath it — *after* every answer had been collected. The incremental
artifact survived, which is the design working. Scoring it then reported **citations resolving 0%,
hallucination 100%**, because `resolves` was *absent* on every citation and the reader defaulted a
missing key to `False`.

Absent and `false` are different facts: the first means nobody looked the citation up, the second
means the clause does not exist at the version named. `observations_from` now **raises** on an
unchecked citation rather than defaulting it, `score` resolves them first, and the run holds no
session across the model-bound part at all. The true numbers for that run were 100% resolving and
0% mechanical hallucination — the harness had been about to report the exact kind of unfounded
number it exists to prevent, in a file whose own docstring says a bug there produces a passing gate
nobody investigates. It produced a *failing* one instead, which is the only reason it was noticed.

**11. A second reviewer is available, which upgrades one measurement and makes one word true.**
Recorded 2026-08-14. Two things follow, and only the first needed anything built:

**Atomicity agreement becomes inter-rater.** [phase1.2](phase1.2_ir_extraction.md) deviation 3
degraded the criterion to same-rater test–retest at ≥ 2 weeks' separation, because inter-rater is not
runnable with one rater. Test–retest detects an unstable rule and an unstable reader, but **not a
reader's consistent private misreading** — the same wrong reading returns both times and scores as
perfect agreement, which is why the script prints that caveat with the number. `ir_agreement.py`
needed no change: it already reports `inter-rater` whenever the two markup files carry different
`rater` names. What it needed was a procedure, and that is
[docs/eval/reviewer-packet.md](../eval/reviewer-packet.md) § 2 — the same fixed sample, marked
independently, **without conferring**, because two people who conferred are one rater with extra
steps.

**"Blind" stops being aspirational.** The blind worksheet already withheld the expected answer, the
expected paths, the confidence and the verdicts, but an assessor who *wrote the questions* is
checking their own work whatever the sheet withholds. That is the half of risk 7 the second reviewer
actually closes. The half it does not close is authorship: the sets were still proposed by the
system's own authors, and the reviewer signs rather than writes. Recorded here so the Go/No-Go report
claims the separation it has and not the one it doesn't.

**12. The pilot is prepared to the start line and deliberately not started.** Recorded 2026-08-14 as
a decision, not a slip: no cohort has been fielded, so **pilot retention and research-time savings
stay 미측정** and the recommendation stays `INCOMPLETE`.

What was missing was never instrumentation — `score_retention` intersects across every week rather
than counting active ones, the cohort and baseline templates each state their own trap, and both are
unit-tested. What was missing was the *order*: the templates explain themselves individually while
nothing said which one has to be filled first.
[docs/eval/pilot-runbook.md](../eval/pilot-runbook.md) is that, and it leads with the two constraints
that cannot be repaired after the fact rather than burying them in a checklist:

- **The baseline is captured before anyone gets access.** Once an analyst has used the workbench,
  their "manual" time is contaminated — they now know where the answer is — and the 30% becomes
  unfalsifiable.
- **The cohort is fixed before week 1.** A cohort assembled afterwards out of whoever kept using it
  scores 100% every time, and dropping one non-returner is invisible in the result.

A third constraint is expensive rather than fatal and is stated as such: the four weeks cannot be
compressed, so any upstream slip eats the measurement window rather than the build.

**13. The Claude arm of the LLM seam does not run, and is recorded rather than fixed.**
`shared/regops_shared/llm/__init__.py:108` sends `temperature` on every Anthropic request, and both
`EXTRACTION_TEMPERATURE` and `GENERATION_TEMPERATURE` are pinned to `0.0` by
[ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md) decision 1. On
`claude-opus-4-7` — the id in `.env.dev` — and on every current Opus- and Sonnet-tier model,
`temperature` is **rejected with a 400**. So `LLM_PROVIDER=claude` fails on its first generation
call, and the pluggable seam [ADR-0005](../design/ADR-0005-service-architecture.md) decision 7
promises is untested on one of its two sides.

Not fixed, on a recorded decision (2026-08-14): the pinned regime stays `ollama` / `gemma3:4b`, so
the defect blocks nothing that is currently measured, and changing the seam while a phase is being
closed would put an unexercised code path into the build the pilot is meant to freeze. **It becomes
blocking the moment anyone acts on this file's own standing recommendation to compare the Anthropic
provider as a second regime** — which is exactly when it would otherwise be discovered, mid-run, as a
400 per item. The fix is small and known: drop `temperature` for models that reject it, and update
the pinned model id.

**14. Scoring counts three buckets, not two.** A bounded run leaves most of the set unasked, and
the first version counted every unasked item as a harness error — a 12-item sample of a 162-item
set reported *150 harness errors* and divided its accuracy by the whole set. **Scored**, **harness
error** (asked, no answer came back) and **not attempted** (never asked) are now separate, and none
may be folded into another: an error read as a refusal moves the refusal rate the healthy-looking
way, and an unasked item read as scored puts it in a denominator it was never part of.
