# ADR-0014 — Annex table rows are Clauses; there is no `annex_rows` table

- **Status:** Accepted
- **Date:** 2026-08-06
- **Closes:** [ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md) open question 3,
  [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) open question 2
- **Extends:** [ADR-0012](ADR-0012-annex-version-identity.md), which settled the *container* (a 별표
  is a child `Document`) but not the granularity inside it
- **Due:** W4 ([plan/README](../plan/README.md) § Decisions due) —
  [phase1.3](../plan/phase1.3_retrieval_qa.md) builds the retrieval index on the answer at W5–6

---

## Context

[ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md) decision 2 sketched a separate
`annex_rows` store, and its open question 3 leaned that way **conditionally**: *"Acceptable
denormalisation for lookup speed, or a single store with a structured overlay? Leaning the former;
revisit if the row count makes sync a burden."*

The condition rests on a number nobody had measured. The estimate in circulation — "tens of
thousands of rows per 고시" — came from counting *physical lines* in the fixed-width tables, and a
logical row wraps across several of them.

**Measured against the live archive, 2026-08-06** (278 annex documents across the two gated cells,
re-measured from the WORM archive rather than from the API):

| | 별표 | 서식 | 별지 | total |
|---|---:|---:|---:|---:|
| annex documents | 81 | 173 | 24 | **278** |
| documents containing ≥1 table | 24 | 104 | 4 | 132 |
| tables | 62 | 114 | 4 | 180 |
| **data rows** (excluding header rows) | **1,937** | 41 | 21 | **1,999** |
| non-blank physical lines | 20,265 | 10,179 | 1,527 | 31,971 |

This agrees with the count recorded in [phase1.1](../plan/phase1.1_normalization.md) on 2026-08-05
(1,967 rows, 1,904 in 별표) to within ~2%; the residual is where a table boundary falls when two
tables abut. Either number settles the question the same way.

Three facts drive everything below:

1. **1,999 rows is not a burden.** It is one ordinary table with an index. The condition ADR-0006
   attached to its preference is simply not met, so the preference does not apply.
2. **Most annexes are forms, and most 별표 are prose.** 197 of 278 annexes are 서식/별지 — blank
   application templates carrying 62 rows between them and no obligation text. And of the 81 별표,
   only **24** contain a table at all; the other 57 are prose. A parser that treats every annex as
   tabular data would manufacture thousands of meaningless clauses out of form layouts.
3. **A table-bearing annex usually holds several tables** — 62 tables across 24 별표. 별표 2 of
   화장품 안전기준 등에 관한 규정 has one table per 성분 class (보존제, 자외선 차단제, …). Any row
   address that assumes one table per annex is wrong on the majority of the cases that matter.

## Decision

### 1. Annex table rows are `clauses`. `annex_rows` is not created.

A row is a `Clause` like any other: same table, same `clause_path`, same diff lineage, same
`ir_citations` target. `ir_citations` needs no branch for annexes, and there is no second store to
keep in sync with the first.

This **removes** `annex_rows` from ADR-0006's schema additions. Nothing else in ADR-0006 changes.

### 2. Decisions 1 and 2 of ADR-0006 are untouched: annex rows are still not embedded

Where rows are *stored* and how they are *retrieved* are different questions, and they were being
conflated. Rows remain excluded from the embedding index and served by exact and prefix match on
their identifier columns; what gets embedded is the annex's title and header. That reasoning — that
thousands of near-identical vectors are noise — is unaffected by the storage decision.

### 3. A row's path is `[별표N, 표M, 행K]`, and it repeats 별표N

```text
clause_path   : 별표2/표1/행3
path_segments : ["별표2", "표1", "행3"]
document      : mfds:admrul:37098#별표2
```

Three choices are folded together here:

- **별표N is repeated** even though the annex's `canonical_key` already carries it. An annex citation
  is then self-describing when the path is rendered apart from its document, which is how citations
  are read in an answer. The cost is one redundant segment.
- **A 표 segment exists**, refining ADR-0006's two-segment `[별표N, row]` sketch. With 62 tables over
  24 annexes, a path without it cannot survive a table being inserted ahead of another, and there is
  nowhere to hang the per-table column map. Uniform three segments beat a shape that changes with
  the annex.
- **Rows are ordinal-addressed** (`행3`), not keyed on their first column value. 원료명 repeats, can
  be empty in a continuation row, and is sometimes hundreds of characters. Insertion therefore
  renumbers subsequent rows — which is exactly the case the diff stage's content-similarity
  renumber fallback exists for, since annex rows carry no `조문이동이전`/`조문이동이후` signal.

### 4. Row columns are typed per table, in `jsonb`, against a header captured on the 표 clause

Every table has a different column set: 별표 2 has five (원료명 · 사용한도 · 비고 · CAS No. ·
화학물질명), 별표 1 has three. A fixed schema is impossible, so:

- The **표 clause** (`[별표N, 표M]`) carries `row_columns` = the ordered header labels for that table.
- Each **행 clause** carries `row_columns` = `{header_label: cell_text}` for its own row.
- `text` on a 행 clause is the row rendered as `label: value` pairs, so a row is readable — and
  citable — without a client that understands the column map.

`jsonb` rather than columns is what makes exact-match lookup work at all: *"갈라민트리에치오다이드는
사용할 수 있나?"* is an equality test against one named column of one table, and the column is not
the same one in the next table.

### 5. The parser branches on `별표구분`, never on domain

`별표` → table mode where a box-drawing table is present, prose mode otherwise.
`서식` / `별지` → **one clause for the whole form.** A blank application template has no rows worth
addressing, and its box-drawing is layout, not data.

`별표구분` is the authority's own field, already recorded in `canonical_key` and `annex_no`
(ADR-0012). This is a *content-shape* branch — the same branch prose-vs-table already is — and it is
keyed on a source field, not on `samd` vs `cosmetic`. The falsifier is not tripped.

## Consequences

**Good.** One clause store, one citation contract, one diff lineage. The falsifier in
[phase1.1](../plan/phase1.1_normalization.md) — *"an annex limit-table row round-trips as a `Clause`
and is addressable by `clause_path`"* — is testable directly instead of being routed around by a
second store that would have made it vacuous.

**Cost.** `clauses` holds a mix of prose clauses and table rows, so a query meaning "prose only" must
filter on `kind`. Row ordinals shift when a row is inserted, which loads the renumber-detection
fallback rather than avoiding it. And `row_columns` is schemaless, so a malformed column map is a
data defect rather than a migration error — the parser validates cell count against the header and
raises drift on mismatch instead of writing a ragged row.

**Reversible?** Partly. Extracting rows into a separate store later is mechanical, because the rows
and their column maps are already structured. Going the other way — merging a populated `annex_rows`
back into `clauses` after citations point into it — would rewrite citations, which ADR-0002
decision 4 forbids. The asymmetry is the reason to start here even if the row count later grows.

## Alternatives rejected

- **`annex_rows` alongside `clauses`, per ADR-0006's sketch.** Its own stated condition is unmet at
  1,999 rows. It also duplicates every row in two shapes, and forces `ir_citations` to branch on
  whether a citation target is a clause or a row.
- **One clause per annex, with the table left as opaque text.** Cheapest, and it fails the phase 1.1
  falsifier by construction: 별표 1 사용할 수 없는 원료 would be a single 340 KB clause, so
  "이 원료를 쓸 수 있나" could never resolve to a citable unit.
- **Fixed columns (substance · cas_no · limit · condition · product_type), as ADR-0006 sketched.**
  Fits 별표 2 of one 고시 and nothing else. 별표 1 has three columns with different meanings, and the
  SaMD 기준규격 tables share no columns with either.
