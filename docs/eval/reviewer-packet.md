# Reviewer packet — the five things only a person can do

For the **second reviewer**: the RA who did not build this system and did not write the golden sets.
That distinction is the entire point of this packet. Four of the six Go/No-Go gates are blocked on
judgements a program cannot make, and a judgement made by the system's own author is not evidence,
however careful it is.

You do not need to understand the harness. You need to read regulation text and answer questions
about it. Everything here is a file you fill in and hand back.

> **If you are also the person who authored the golden sets or the extractor**, stop and read
> [phase1.6 § Risks](../plan/phase1.6_evaluation.md#risks--open-questions) first. Risk 7 is the
> overlap of authorship and assessment, and it is *accepted, not mitigated* when one person holds
> both roles. Everything below still runs; it just measures less than it appears to.

---

## The order, and why it is not arbitrary

```text
  1. Golden-set sign-off ─────────────┐
                                      ├──> 4. Blind assessment   (needs a scored run of a signed set)
  2. IR ground-truth markup ──┐       │
  3. Submission markup ───────┴───────┘   ← both must be finished BEFORE you see extractor output

  5. Amendment ledger ── independent of all of the above
```

**Tasks 2 and 3 come before task 4, and before you open anything in the app that shows extracted
requirements.** The markup is only worth something if it was written blind, and blindness is not
recoverable: once you have seen what the extractor found, you cannot un-see it, and no later care
repairs the number. Task 4 shows you cited clause text — corpus text, not extractor output — but
doing the markup first removes the question entirely.

Tasks 1 and 5 can happen at any time. Task 5 needs a browser and the authority's own website, not
this system.

---

## 1. Sign the golden sets

**What it unblocks:** everything. Until both sets are signed, `validate` prints *not citable as gate
evidence* and `score` exits non-zero, so no scored run can be quoted against a gate.

**The files:** `golden/mfds_cosmetic.json` and `golden/mfds_samd.json` — 162 items each, across six
axes. Roughly 100 of the 162 per cell are template-generated; **review those first**, because a
generated item is the one that can be fluent and wrong.

**Read every item and ask three questions:**

| Question | What a "no" means |
| --- | --- |
| Is this a question a real reader would ask? | The item measures the generator's phrasing, not the product |
| Is `expected_outcome` right? | An item expecting `answered` where the corpus genuinely cannot answer scores a correct refusal as a failure — and vice versa |
| Do `expected_clause_paths` actually say what the item claims? | The commonest generated defect: a real clause path that does not support the expected answer |

For `mis_citation` items, the trap is the point: the named 조 must **not** exist, or must provably
say something else. `forbidden_clause_paths` is what the system is not allowed to cite. Check both.

For `cross_domain` items, the correct behaviour is to **decline** — the question is a real obligation
from the neighbouring cell, asked in this one. An item authored with `cross_cell: true` defeats
itself, and `validate` rejects it.

**Recording it.** Edit the file's header, not the items:

```json
"ra_signed_off": true,
"signed_off_by": "your name",
"signed_off_at": "2026-08-14"
```

Fix the items you found wrong before signing — editing an item is expected, and the whole point of
the review. Signing means *these 162 questions are ones I would defend*, not *I read them*.

> After sign-off, `seed` refuses to regenerate the set unless forced. That is deliberate: a signed
> set is the source of truth, and a regenerator that overwrote a reviewed file would erase the only
> evidence the review happened.

---

## 2. Mark the IR ground truth — blind

**What it unblocks:** extraction **recall**. Without it, nobody can say what share of the real
obligations the extractor found — only what share of what it found was right, which is the easy half.

**The files:** `ground_truth/<cell>.ir_markup.template.json`, pre-populated with 40 조-level clause
paths per cell drawn by a recorded seed from `clauses` alone. The denominator is fixed before you
start, so a clause cannot be quietly dropped later for having turned out to be hard.

**The task:** for each clause path, read the clause text and write **how many atomic regulatory
obligations it yields** under the rule in
[ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decision 1.

Three rules, each of which stops a specific way the number goes wrong:

1. **Mark from the clause text alone.** Never from `/irs`, never from the coverage panel. Marking up
   after seeing extractor results inflates recall and produces a figure that cannot be defended to
   anyone who asks how it was made.
2. **Write `0`, never blank.** *"I judged this clause to bear no obligation"* and *"I did not look at
   this clause"* are different answers, and the distinction is the whole reason the denominator is
   drawn in advance. An omitted path is an error, not a zero.
3. **Do not discuss the hard ones with the other rater until both files are handed back.** See below.

**Rename to `<cell>.ir_markup.json`** when done — a `.template.json` is read by nothing, so a
half-finished file can never be mistaken for evidence.

### The part that is new with two reviewers

With one RA, agreement could only be measured as **test–retest**: the same person, twice, two weeks
apart. That detects an unstable rule and an unstable reader, but it cannot detect a *consistent
private misreading* — the same wrong reading returns both times and scores as perfect agreement.

With two reviewers it becomes **inter-rater**, which is the measurement ADR-0004 decision 1 was
actually written to support: two people, one rule, and a disagreement means the rule is ambiguous.

`scripts/ir_agreement.py` switches modes on its own — it reports `inter-rater` whenever the two files
carry different `rater` names, and `test-retest` otherwise, with the caveat printed in its own output
so a report cannot cite the number without it. Nothing needs configuring. What it needs from you:

- **Both raters mark the same fixed sample**, independently, each writing their own file with their
  own name in `rater` and the date in `marked_at`.
- **Neither reads the other's file first.** Two people who conferred are one rater with extra steps.

```bash
docker compose exec -T regulation python /scripts/ir_agreement.py \
    --sample /eval/ground_truth/mfds_cosmetic.atomicity_sample.json \
    /eval/ground_truth/mfds_cosmetic.ir_markup.rater_a.json \
    /eval/ground_truth/mfds_cosmetic.ir_markup.rater_b.json
```

---

## 3. Mark the submission-detection sample — blind, same rules

**What it unblocks:** whether the 제출 서류 view is precise. The detector currently yields 102–103
procedures over the gated corpus; a looser pattern gave 341 and a stricter one 92, and **nobody has
confirmed which is right**. The feature ships saying so.

**The files:** `ground_truth/<cell>.submission_sample.template.json` — 55 candidate clauses for
Cosmetic, 97 for SaMD. It is deliberately **not** pre-filled with what the detector found, because a
pre-filled sheet anchors you on the answer being measured.

For each clause, judge from the text alone: does this clause state a **filing duty with a list of
required documents** (항 = the duty, 호 = each document), or does it state something else that looks
like one — a 기준 list, a list of matters to be recorded, a definition?

That distinction is the whole measurement. A 기준 list read as a document list is a **false
positive**, which a user sees and can be misled by; a missed procedure is a **false negative**, which
a user never sees. The harness keeps the two apart for that reason.

---

## 4. Assess answers blind

**What it unblocks:** **citation accuracy** (≥ 90%) and the contradiction half of **hallucination
rate** (≤ 2%). Both are readings. The harness measures their mechanical halves — whether a cited
clause *resolves* at the version named — and stops there, because whether a clause *supports* a claim
is not a database question.

**Prerequisite:** a scored run over a **signed** set (task 1). Someone runs:

```bash
E="docker compose exec -T -w /scripts regulation python -m evaluation.cli"
$E run --per-axis 3          # resumable; the run artifact is the run
$E worksheet                 # → docs/eval/worksheets/<cell>.assessment.csv
```

**What you get:** one row per (answer, citation), carrying the claim and the cited clause text — and
deliberately **not** the expected answer, the expected clause paths, the confidence score, or the
verification verdicts. An assessor who can see those is checking agreement with the system, not
assessing support.

Rows are shuffled by a **recorded** seed. Run order groups items by axis, and the thirty-first
identifier lookup is not read the way the first one was; the seed is recorded so it can be shown
afterwards that the order was not chosen.

**Per row, two judgements:**

| Column | The question | Note |
| --- | --- | --- |
| `supports` | Does this clause actually support this claim? | A blank raises rather than defaulting either way — an unassessed row must never read as a pass |
| `contradicts` | Does the answer contradict the source text? | This is the half of hallucination rate no mechanical check can reach |

Hand it back and someone runs `$E worksheet --read <your file>`.

> **A refusal is not a failure.** If the system returned 확인 필요, that is the product keeping its
> promise — no unsourced answer is ever emitted. Assess the citations that exist; do not mark a
> refusal down for being one.

---

## 5. Write the amendment ledger

**What it unblocks:** **detection coverage** (≥ 95%) — the gate that cannot be measured from inside
the system at all. RegOps can report how many amendments it saw; it cannot report how many it
missed. *"We detected everything we detected"* is 100% by construction.

**The file:** `ground_truth/amendment_ledger.template.json`.

**The task:** go to the authority's own publication listing — 국가법령정보센터, the MFDS 공고 게시판 —
for the measurement window, and write down **every amendment it published for the cell**, whether or
not RegOps has it. That listing is the denominator; this system is not.

Two things the harness cannot check for you:

- **Titles must match the label the harness compares against**: `<document title> @ <effective
  date>`, or `<document title> @ 미해석` where the effective date could not be resolved. A near-miss
  in spelling reads as a detection failure — check titles against the regulation browser before
  handing it back.
- **Record the window you actually surveyed.** A ledger covering a different window than the
  `gates --days` run is not a denominator; it is two measurements pretending to be one.

---

## What happens to your work

Someone runs `$E gates --out /eval/go-no-go.md`, and each artifact you hand back turns one 미측정
into a number with a method behind it. Until then that gate renders as **미측정 with its reason**, and
any unmeasured gate makes the recommendation `INCOMPLETE` rather than `GO` or `NO-GO` — because four
shortfalls call No-Go, so a defaulted gate would be *making* the decision rather than informing it.

Nothing you hand back is scored against you. If an item is wrong, say so and fix it; if a clause is
genuinely ambiguous, that is a finding about the rule, not about you — and with two raters it is
exactly the finding the agreement measurement exists to surface.
