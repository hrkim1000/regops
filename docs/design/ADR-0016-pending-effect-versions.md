# ADR-0016 — 시행예정 versions: MST is the version, and staged dates are not clause-level

- **Status:** Accepted
- **Date:** 2026-08-06
- **Amends:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 5 (where
  `effective_date` comes from) and **withdraws part of its open question 2**
- **Confirms:** [ADR-0013](ADR-0013-unresolvable-effective-dates.md), decisively and from the wild
- **Forced by:** [phase1.1](../plan/phase1.1_normalization.md) § 시행예정 — *"Write the amendment
  before the code, not after"*

---

## Context

Polling 현행 only means an amendment is invisible between 공포 and 시행 — for the gated 법령 that is
2 months to 2.4 years, so the ≤24h detection-latency gate is not merely unmet but structurally
unmeetable. `target=eflaw` exposes the pending versions.

The plan recorded three claims from the 2026-08-03 measurement. **Probed live again on 2026-08-06,
one holds, one is confirmed and strengthened, and one is wrong.**

### What the API actually does

| Probe | Result |
|---|---|
| `lawSearch.do?target=eflaw&query=화장품법` | 200, `<LawSearch>` with `<law>` rows carrying `현행연혁코드 ∈ {시행예정, 현행, 연혁}`, `법령일련번호` (MST), `법령ID`, `공포일자`, `시행일자` |
| `lawService.do?target=eflaw&MST=282015` | **HTTP 500 with an XHTML error page.** There is no 본문조회 under `target=eflaw` |
| `lawService.do?target=law&MST=282015` | 200 — the pending 본문. `시행일자 20261231`, 79 조문 |
| `…&MST=282015&efYd=20280101` | **byte-identical to the call without `efYd`.** The parameter is ignored |
| `…&target=law&ID=002015&efYd=20290101` | returns the **현행** text (시행일자 20260402), not the requested snapshot |

So: **the list enumerates `(MST, 시행일자)` pairs, but 본문 is addressable by MST alone**, and the
one document an MST yields is the earliest of its 시행일자. There is no way to ask the API for the
2028-01-01 state of 화장품법.

### The claim that is wrong

phase1.1 and ADR-0003 open question 2 both assert that the several 시행일자 of one MST are staged
application *"and they belong at clause level — `조문시행일자`, which the spike already confirmed is
present per clause."*

`조문시행일자` **is** present per clause. It is also **constant within a document.** Measured across
every 법령 in the archive:

| Document | 시행일자 | 조문 | distinct 조문시행일자 |
|---|---|---:|---:|
| 화장품법 · 시행령 · 시행규칙 | 20260402 / 20260310 / 20260402 | 74 / 19 / 55 | **1 / 1 / 1** |
| 의료기기법 · 시행령 · 시행규칙 | 20260701 | 111 / 30 / 97 | **1 / 1 / 1** |
| 디지털의료제품법 · 시행령 · 시행규칙 | 20250124 / 20250124 / 20260124 | 72 / 11 / 62 | **1 / 1 / 1** |
| 화장품법 @ MST 282015 (시행예정) | 20261231 | 79 | **1** |

Nine documents, nine out of nine uniform, and the value always equals the document's own 시행일자.
`조문시행일자` is the **snapshot date restated per clause**, not a per-provision override. The
authority models staged application by publishing separate consolidated snapshots of one MST — which
it then declines to serve individually.

### Where the staged dates really live, and why they are not dates

The 부칙 of MST 282015 (제21302호, 2025.12.30):

> 이 법은 공포 후 1년이 경과한 날부터 시행한다. 다만, … 제4조의2의 개정규정 … 은 해당 호에서 정한
> 날부터 시행하고, 제4조의3제1항제2호의 개정규정 … 은 2029년 1월 1일부터 시행한다.
> 1. 연 생산액ㆍ수입액이 10억원 이상인 업소 …: 가. … 2028년 1월 1일 / 나. … 2030년 1월 1일 /
>    다. … 2031년 1월 1일
> 2. 연 생산액ㆍ수입액이 10억원 미만인 업소: 2031년 1월 1일

Two things follow, and both are load-bearing:

1. **The 부칙 names five dates; the eflaw list returns three.** 2030-01-01 and 2031-01-01 appear
   nowhere in the list. Treating the list as the record of staged application would silently lose
   two of them.
2. **The staged dates are conditioned on the addressee, not on the clause.** The same 제4조의2
   개정규정 takes effect in 2028, 2030 or 2031 depending on the reader's annual revenue and product
   history. There is no single `clauses.effective_date` that is correct — a per-clause date column
   cannot represent this obligation no matter how it is populated.

## Decision

### 1. A version is one MST. `시행일자` is never a version key.

One `DocumentVersion` per `법령일련번호`, attached to the **same** `Document` as 현행 (both are
법령ID 002015). MST 282015's three list rows produce **one** version; keying on 시행일자 would
triplicate identical text and emit two phantom amendments through the diff stage.

### 2. 본문 is fetched by `target=law&MST=`, never `target=eflaw`

`eflaw` is a **list-only** target for us. `lawService.do?target=eflaw` returns HTTP 500 with an
XHTML body — a **fifth HTTP-200-adjacent failure signature**, and the first that is not 200. The
connector treats a non-XML body as a drift signal rather than archiving an error page.

`efYd` is ignored and must not be sent: a parameter that appears to work and silently returns the
wrong snapshot is worse than one that errors.

### 3. `effective_date` comes from the envelope where the authority states it *(amends ADR-0003 dec 5)*

ADR-0003 decision 5 classifies `effective_date` as "extracted at parse time from the document text —
부칙 '…부터 시행한다'". For `law.go.kr` that is a derivation of something the envelope already
states outright in `기본정보/시행일자`.

- **`effective_date` = the envelope's `시행일자`** where the source states one. This is the same
  category as `공포일자 → published_at`: authority-stated metadata, not an inference.
- **`부칙` supplies `effective_date_phrase`, and is the fallback** for sources that state no date.
- The value is still **written by the parse stage**, re-read from the WORM archive. One writer, and
  a bad date is fixed by re-parsing rather than re-fetching.

Parsing 부칙 prose to re-derive a number the authority already published would be a worse estimate of
the same fact, and ADR-0013's whole point is that a derived date must never enter the Citation tuple.

### 4. Version-level `effective_date_phrase` is the newest 부칙단위's 시행일 text, verbatim

`부칙단위` is a full history — 17 of them on 화장품법, back to 2011. The applicable one is the
**last**, matching the version's 공포일자/공포번호.

This phrase, not the eflaw list, is the record of staged application. It is authoritative text, it
carries all five dates rather than three, and it preserves the conditions that make them meaningful.
Per [ADR-0013](ADR-0013-unresolvable-effective-dates.md) it is exactly the input a later resolver
would need, and it is retained whenever the phrase is non-trivial — not only when resolution failed.

### 5. Clause-level `effective_date` is written only when `조문시행일자` differs from the version's

The column exists (ADR-0003 decision 5 requires it, and phase1.1 forbids deferring it to a later
migration). It stays **null** for every clause in the gated corpus today, because the check is
`조문시행일자 != version.effective_date` and that is never true.

Keeping the check rather than dropping the column is deliberate: the override is real in EU
instruments (the AI Act's two dates), the column is part of the clause schema that ADR-0002 warns is
the most expensive thing to change later, and a null column costs nothing. What is *not* done is
inventing a clause-level date by attributing 부칙 text to clause paths — that requires resolving
"제4조의3제1항제2호의 개정규정" to a `clause_path`, which is cross-reference resolution
([ADR-0010](ADR-0010-semantic-enrichment-and-graph-model.md) decision 7, Phase 2), and it would still
be wrong because the date depends on the addressee.

### 6. A pending version does not displace 현행, and no status column says so

The in-force version of a document is `max(effective_date) where effective_date <= today`. A future
`effective_date` is what makes a version pending; there is no `is_current` flag to drift out of sync
with the date it duplicates. Where no version is yet in force the query returns none rather than
guessing.

### 7. 연혁 stays out of Phase 1

`eflaw` also returns superseded versions (`현행연혁코드 = 연혁`) — 20 rows for 화장품법 back to 2018.
Backfilling them would supply diff baselines we did not archive ourselves, which the citation
contract does not accept (ADR-0003 decision 12). The connector filters on
`현행연혁코드 = 시행예정` and on our own `법령ID`; the query is a name search and returns unrelated
statutes.

## Consequences

**Good.** Detection latency for the 법령 sources becomes measurable for the first time — an
amendment is seen at 공포 rather than at 시행. Version identity is the authority's own key, so it
cannot drift from theirs.

**Cost, and it is a real gap.** The staged application of MST 282015 is stored as *text*, not as
data. Nothing in Phase 1 can answer "which obligations bite on 2028-01-01 for a company over
₩1bn". That question needs the addressee dimension, which is the Product/Compliance context of
[ADR-0007](ADR-0007-context-map-and-applicability.md) — Phase 2. Recording it as a retained phrase is
the honest floor, not a solution.

**One phase-1.1 acceptance criterion is corrected by this ADR.** It reads *"One MST carrying three
시행일자 produces exactly one version, with the earliest date at version level and the remainder on
clauses."* The first half stands and is tested. **The remainder does not go on clauses** — the
evidence above shows it cannot — it goes in `effective_date_phrase`. The plan file records the
deviation.

**ADR-0003 open question 2 is partly withdrawn.** Its closing note claims `조문시행일자` "confirms
decision 5's clause-level `effective_date` override matches how the authority itself models staged
application." Measurement says otherwise: the field is constant per document, and the authority
models staged application through separate snapshots plus 부칙 prose. The clause-level override
remains in the schema on its own merits (decision 5 above), not on this evidence.

## Alternatives rejected

- **One version per `(MST, 시행일자)`.** What the eflaw list's shape suggests, and it triplicates
  identical bytes — the 본문 is the same document for all three rows, so two of every three versions
  would be phantom amendments the diff stage then emits as change events.
- **Parse 부칙 to compute clause-level dates.** Rejected on ADR-0013's reasoning plus new evidence: a
  computed date in the Citation tuple is indistinguishable from an authoritative one, and here the
  correct value is not a date at all but a function of the addressee.
- **A `pending_effective_dates` array on `document_versions`, populated from the eflaw list.**
  Tempting for alert ordering. Rejected because the list is demonstrably incomplete — it omits two
  of MST 282015's five dates — so the column would look authoritative while being wrong, which is
  the exact failure mode ADR-0013 exists to prevent.
- **An `is_pending` / `is_current` status column.** Duplicates `effective_date` and can disagree with
  it. The date already answers the question, and it keeps answering it correctly as time passes
  without a job to flip flags.
