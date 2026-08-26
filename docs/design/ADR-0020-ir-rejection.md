# ADR-0020 — A review has two outcomes, and only one of them was representable

- **Status:** Accepted
- **Date:** 2026-08-26
- **Extends:** [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) decision 4 — *"the LLM
  proposes; a human locks; only locked IRs flow"*. It describes what happens when the reviewer
  agrees and is silent on the other half.
- **Confirms:** [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) decision 6 (examined and
  excluded must not read as unexamined), decision 5 (a locked IR is never mutated in place)
- **Forced by:** an operator mis-clicking 확정 on an IR with no way to undo it, and no way to say
  the IR should have been refused

---

## Context

`POST /irs/{id}/lock` existed. Nothing else did.

The review surface offered one button, and that was not a UI oversight — it was the only transition
the model had. `IRStatus` held `draft | locked | stale | superseded`. There was no way to write down
that an RA had looked at a draft and refused it, and no way to take back a lock.

The gap surfaced on real data. Extraction over 21 CFR Part 700 produced 21 draft IRs from 16
obligation-bearing clauses. Two of them cite paragraphs of **§ 700.3 Definitions** — the section
head was correctly excluded as `definition`, but the exclusion does not descend to its paragraphs,
so `700.3(g)` and `700.3(n)` were classified obligation-bearing and extracted. One of them produced
the statement *"be applicable to such terms when used in the regulations in this subchapter"*, which
is not an obligation and could not be one: a definition binds nobody.

An operator then locked `700.3(g)` by mistake, and there was no way back.

**Leaving a refusal as `draft` is not neutral.** It is the same claim as "nobody has looked at this
yet", so the item returns to the next reviewer's queue indefinitely, and the reviewer has no way to
know it has already been judged. It also makes the extraction agent's error rate unmeasurable —
there is no count of "proposed and refused" to put beside "proposed and approved".

That argument is not new here. [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) decision 6
makes it one level down, about clauses:

> Definitions, scope statements and headings produce no IR. If they are simply absent, "50 IRs from
> 200 clauses" is uninterpretable — it cannot be distinguished from 150 missed obligations.

The IR lifecycle had the defect that decision 6 exists to prevent, in the layer above it.

## Decision

### 1. `rejected` is a status, not an absence

`IRStatus` gains `REJECTED`. An RA who refuses a draft records it, and the record distinguishes
*reviewed and refused* from *not yet reviewed* — which is the whole point.

`IR_VISIBLE_STATUSES` is **unchanged** and stays `(LOCKED,)`. Nothing downstream reads the new
state: a rejected IR is inert exactly as a draft is. What changes is that it is inert *and*
accounted for.

The row is not deleted. Deleting it would lose the evidence that the agent proposed this, which is
the input to any claim about how often it is wrong.

### 2. The reason is an enum; the note is free text

`rejection_reason` is one of `not_an_obligation` · `misread_clause` · `not_atomic` ·
`wrong_citation` · `duplicate`, and `rejection_note` carries the particulars. Both are required.

This is the split [`ExclusionReason`](../../shared/regops_shared/constants.py) already makes, for
the same stated reason: *"a free-text reason would be unaggregatable, and the coverage claim depends
on being able to say how many clauses were excluded for each reason."* The count per reason is a
signal about the **extraction agent** rather than about any one IR — a jump in `not_an_obligation`
is a classification regression showing up at review time. The judgement about a single refusal is
not enum-shaped and should not be forced into one.

The five values are grounded in what the Part 700 run actually produced, not invented to fill a
taxonomy. If a sixth is needed, it is added when a refusal cannot honestly be described by these.

### 3. Unlocking returns to `draft`, never straight to `rejected`

`POST /irs/{id}/unlock` takes a `locked` IR back to `draft` and requires a note.

It does **not** go to `rejected`, and the distinction is the point: *"this approval was a mistake"*
and *"I have reviewed this and refuse it"* are different assertions, and collapsing them would put a
judgement in the record that nobody made. An IR that was mis-locked and should also be refused takes
two steps, and the trail then says both things happened.

Restricted to `ra` and `admin`, the same as locking. An RA correcting their own mis-click should not
need an administrator, and who did it is recorded either way.

### 4. The lock clears from the row and never from the audit trail

`unlock` sets `locked_by` and `locked_at` to null, because a draft that still names a signer is a
lie about its own state.

The `ir.locked` entry stays exactly where it is. `audit_log` is append-only and hash-chained
(`prev_hash` / `entry_hash`), so an entry cannot be edited or removed without breaking the chain —
which is the property the chain exists for. `unlock` appends `ir.unlocked` carrying the previous
signer and timestamp; `reject` appends `ir.rejected` carrying the reason and the agent provenance.

So "who approved this" and "who took that back" are both answerable, and **neither is answerable
from the row alone**. That is not a shortcoming of the row; it is the division of labour between a
mutable current state and an immutable history.

## Consequences

- **The review surface needs a second and third control.** One button was faithful to a model with
  one transition. Three transitions need three, and a reviewer who can only approve is a reviewer
  whose disagreement is unrecordable.
- **Rejection counts become a quality metric on extraction**, per `rule_version` / `prompt_version`
  / `llm_model`, which the payload carries. Nothing consumes it yet.
- **A rejected IR is not re-derived away.** ADR-0004 decision 5 re-derives on amendment and marks
  the old IR `superseded`; a `rejected` IR is out of the queue and stays out. Whether a re-extraction
  under a later `rule_version` should re-offer a previously rejected obligation is **not decided
  here** — it needs a rule about identity across runs that does not exist yet, and guessing now
  would be a decision made without the case in front of it.

  > **The case is arriving, 2026-08-26.** `_clear_previous_drafts` filters on `status == DRAFT`, so
  > a `rejected` IR survives a re-extraction — correct by accident rather than by decision, since
  > that function's docstring enumerates `locked`, `stale` and `superseded` and predates this ADR.
  > The consequence is visible on the next run: 21 CFR Part 700 holds the two rejections that forced
  > this ADR (`700.3(g)` and `700.3(n)`, both `not_an_obligation`), and re-extracting it will show
  > whether the same obligations come back as fresh drafts beside their own rejections. **Decide
  > after observing that**, which is what "without the case in front of it" was waiting for.
- **The `700.3` defect is untouched by this.** Being able to record a refusal is not the same as not
  producing the draft: the exclusion of a definitions section should descend to its paragraphs, and
  it does not. That fix moves what the **gated** MFDS cells extract — Korean 정의 조항 (제2조) have
  the same shape — so it carries a before-and-after over the phase 1.6 golden sets and is recorded
  in [phase2.0a](../plan/phase2.0a_fda.md) rather than made in passing.

## Alternatives rejected

- **A `rejected` boolean beside `status`.** Two columns that can disagree, and every downstream
  filter would have to remember to check both. The lifecycle is a state machine and belongs in the
  state column.
- **Delete the row.** Loses the evidence that the agent proposed it, which is exactly the number
  worth having, and re-extraction would silently propose it again with nothing to compare against.
- **Reuse `superseded`.** It means "a later IR replaced this one" and carries `supersedes_ir_id`.
  A refused draft has no successor, and overloading the value would make both counts unreadable.
- **Free-text rejection reason only.** Unaggregatable, for the reason `ExclusionReason` records.
- **Let `unlock` go straight to `rejected`.** Fewer clicks, and it writes a judgement the operator
  did not make. The mis-click that forced this ADR would have become "the RA refused this IR".
- **Edit or delete the `ir.locked` audit entry.** Breaks the hash chain, and the chain is the reason
  the lock is worth anything. The mistake happened; the record of it is not the problem.
