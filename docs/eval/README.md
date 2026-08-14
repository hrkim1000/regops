# Evaluation corpus

The data the [phase 1.6](../plan/phase1.6_evaluation.md) harness measures against. The harness
itself is [`scripts/evaluation/`](../../scripts/evaluation/); this directory is what it reads and
writes.

**The purpose of the PoC is measurement, not a demo.** No-Go is called at four shortfalls in any one
cell, so everything here is arranged around one question: *could a reasonable person disagree with
this number and be shown to be wrong?*

## Layout

```text
golden/
  <cell>.curated.json      hand-authored items — conceptual · effective_date · unanswerable
  <cell>.json              the full set: curated + generated. THE file a run scores against
ground_truth/
  <cell>.atomicity_sample.json          the blind clause denominator, drawn by recorded seed
  <cell>.ir_markup.template.json        one rater fills this; ir_agreement.py compares two
  <cell>.submission_sample.template.json  the denominator for submission-detection precision
  amendment_ledger.template.json        the authority's own amendment list — the coverage gate
  pilot_cohort.template.json            fixed before the pilot starts
  research_time_baseline.template.json  captured before the pilot starts
worksheets/                the blind assessment sheets, and the RA's filled versions
runs/                      run artifacts, resumable and gitignored
go-no-go.<date>.md         a dated report snapshot — never "the" report until W16
reviewer-packet.md         what the second reviewer does, in the order it has to be done
pilot-runbook.md           the four weeks, and the two things that cannot be repaired afterwards
```

Two of the files above are procedures rather than data, and they exist because the templates each
explain themselves while nothing said what order to fill them in:

- **[reviewer-packet.md](reviewer-packet.md)** — for the RA who did not build this system. Five
  tasks: sign the golden sets, mark the IR ground truth, mark the submission sample, assess answers
  blind, write the amendment ledger. The ordering is load-bearing: the two markup tasks must finish
  **before** the reviewer sees extractor output, and blindness is not recoverable once lost.
- **[pilot-runbook.md](pilot-runbook.md)** — freeze, fix the cohort, capture the baseline, onboard,
  four uncompressible weeks, measure. Its first section is the two constraints that cannot be
  repaired after the fact: the baseline is captured **before** access, and the cohort is fixed
  **before** week 1.

A `.template.json` is not read by anything. Fill it, drop the `.template`, and the harness picks it
up — so a half-finished template can never be mistaken for evidence.

## Three rules, and what each of them stops

### 1. Seeding proposes. Only an RA signs.

`<cell>.json` carries `ra_signed_off: false` until a person who is not the system's author has read
every item. `validate` reports the set as **not citable as gate evidence** until then, and `score`
exits non-zero. A golden set the system's own authors wrote and scored themselves is not evidence,
however good the questions are.

Three axes are generated from the clause store, because for those a template produces a *faithful*
instance rather than a plausible-looking one:

| Axis | Generated? | Why |
|---|---|---|
| `identifier` | yes | "「화장품법」 제5조는 무엇을 규정하고 있습니까?" *is* an identifier lookup |
| `mis_citation` | yes | A trap is only a trap if the clause provably does not exist, or provably says something else. Both are database facts — generating these is *more* reliable than writing them, because a hand-written trap can accidentally name a real clause |
| `cross_domain` | yes | A real obligation from the neighbouring cell, asked here. The neighbouring clause store is exactly where those live |
| `conceptual` | **no** | A paraphrase reusing the statute's own vocabulary is an identifier lookup wearing a sentence |
| `effective_date` | **no** | Requires knowing which two versions differ and what turns on the difference |
| `unanswerable` | **no** | Requires knowing what the corpus does *not* contain, which no query over the corpus can tell you |

After sign-off, `<cell>.json` is the source of truth and the generator is never run over it again —
`seed` refuses a signed set unless forced.

### 2. Ground-truth markup is blind, and blindness is now the only protection left.

The markup was planned to run in parallel with [phase 1.2](../plan/phase1.2_ir_extraction.md). It
did not: 1.2 closed with no markup authored, so it will be written while a working extractor exists.
Two things follow.

**Mark up from the clause text alone.** Never from `/irs`, never from `/coverage`. Marking up after
seeing extractor results inflates recall and produces a number that cannot be defended.

**The denominator is fixed before anyone starts.** `atomicity_sample.json` is drawn from `clauses`
by a recorded seed and never looks at `irs`, so a clause cannot be quietly dropped later for having
turned out to be hard. `0` and *absent* are different answers: write `0` for a clause you judged to
bear no obligation, because "I judged this to yield nothing" and "I did not look at it" are the
distinction [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 6 exists
to keep.

The same rule governs the submission-detection sheet, which is deliberately **not** pre-filled with
what the detector found — pre-filling would anchor the RA on the answer being measured.

### 3. A number nobody could have measured is never reported as if somebody had.

Three of the six gates are human judgements. The harness computes their mechanical halves and stops:

| Gate | What the harness can measure | What it cannot |
|---|---|---|
| Citation accuracy | whether a cited clause is one the set expected — a **lower bound** | whether the clause *supports* the claim. That is a reading |
| Hallucination rate | whether a cited clause resolves at the version named, and whether a forbidden path was cited | whether the answer contradicts the source text |
| Research time savings | nothing | all of it, without a pre-pilot baseline |
| Detection coverage | what the system *saw* | what the authority actually published |

For the first two, `worksheet` emits a blind CSV: the claim and the cited clause text, and
deliberately **not** the expected answer, the expected clause paths, the confidence or the
verification verdicts. An assessor who can see those is checking agreement, not assessing support.
Rows are shuffled by a recorded seed, because run order groups items by axis and the thirty-first
identifier lookup is not read the way the first was.

Everything else is returned as `미측정` — neither a pass nor a failure. A report with any unmeasured
gate recommends `INCOMPLETE` rather than guessing, because four shortfalls call No-Go and a coerced
default would be making the decision rather than informing it.

## Running it

Inside the stack — the harness mints its own token from the JWT secret already in the environment
rather than holding a password, and `docs/eval` is mounted at `/eval`:

```bash
E="docker compose exec -T -w /scripts regulation python -m evaluation.cli"

$E seed                       # propose both sets from the clause store
$E validate                   # composition + every expected clause path resolved against the corpus
$E sample                     # draw the blind markup denominators
$E run --per-axis 3           # a bounded pass that spreads across axes; resumable
$E score --out /eval/runs/score.md
$E worksheet                  # emit the blind assessment CSV
$E worksheet --read /eval/worksheets/mfds_samd.assessment.csv
$E polls --days 30            # scheduled polls versus polls that ran
$E determinism --version-id <uuid> --domain samd
$E gates --out /eval/go-no-go.md
```

A full run is ~320 model-bound questions at 80–190 seconds each. It is resumable by design: the run
artifact, not the process, is the run.

## Known limits of this corpus, recorded rather than hidden

- **162 items per cell, not 200.** All six axes clear the per-axis floor, which is the option the
  phase file offers in place of sizing up ("either size up or state per-axis coverage explicitly").
  The per-axis table in `validate` is that statement.
- **100 of 162 items per cell are template-generated.** Review those first.
- **Extraction precision and recall are upper bounds.** The markup format records how many
  obligations a clause yields, not which ones, so an extractor finding the right *number* of the
  wrong obligations scores perfectly. The harness names them `clause_level_precision` /
  `clause_level_recall` for that reason.
- **Atomicity agreement becomes inter-rater with the second reviewer** (2026-08-14). It was
  test–retest while one RA held every role ([phase1.2](../plan/phase1.2_ir_extraction.md)
  deviation 3), and that mode cannot detect a rater's consistent private misreading — the same wrong
  reading returns both times and scores as perfect agreement. `ir_agreement.py` switches on its own:
  it reports `inter-rater` whenever the two files carry different `rater` names. Nothing needs
  configuring; what it needs is two people marking the same fixed sample **without conferring**, per
  [reviewer-packet.md](reviewer-packet.md) § 2.
