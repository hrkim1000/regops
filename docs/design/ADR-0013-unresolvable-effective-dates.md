# ADR-0013 — An unresolvable effective date is null plus the raw phrase

- **Status:** Accepted
- **Date:** 2026-08-03
- **Closes:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md) open question 3
- **Due:** W3–4 ([plan/README](../plan/README.md) § Decisions due) — `effective_date` is a component
  of the Citation tuple, so it is fixed by the clause schema and cannot be deferred past it

---

## Context

`effective_date` is parse-derived, extracted from 부칙 (ADR-0003 decision 5). The phrasing varies —
"…부터 시행한다", "…적용한다", "…이후 최초로 …하는 분부터" — and a meaningful share of it names a
condition rather than a date: **"공포 후 6개월"** cannot be resolved to a calendar date at parse
time, because the 공포일자 of the *amending* instrument may not be the one in hand, and
event-triggered application dates have no date at all until the event occurs.

The choice was between storing null and retaining the phrase, or computing a best-effort date and
flagging its confidence. It matters because `effective_date` is not an ordinary column: it is the
fourth element of `Citation = (document_id, document_version_id, clause_path, effective_date)`
(ADR-0002 decision 4), which is what the product is sold on.

## Decision

**`effective_date` stays NULL when the text does not state a resolvable calendar date, and the raw
phrase is retained verbatim in `effective_date_phrase`.**

- Both `document_versions` and (from phase 1.1) `clauses` carry the pair.
- A computed date is **never** written into `effective_date`. Once there, it is indistinguishable
  from an authoritative one to every downstream reader — retrieval, citation rendering, the
  superseded-citation queue, and any Phase 2 applicability rule. A confidence flag only helps
  readers that remember to check it, and the citation contract has no room for a reader that
  forgets.
- `effective_date_phrase` is populated **whenever the phrase was non-trivial**, not only when
  resolution failed. That makes "we resolved this" and "we had nothing to resolve" distinguishable
  after the fact, which is what makes the extraction rate measurable in phase 1.6 rather than
  inferred.
- Alerting treats a null `effective_date` as "not yet in force, date unknown" and orders such
  changes by `published_at`. That is a visible degradation, which is the point: an honest gap beats
  a flattering number, the same reasoning ADR-0003 decision 5 applies to `published_at`.

## Consequences

**Good.** No citation ever carries a guessed date. The Citation tuple stays fully trustworthy
without a per-reader confidence check, and the phrase is preserved so a human — or a later,
better resolver — can revisit it without re-fetching the archive.

**Cost.** Alert prioritisation loses date ordering for the affected clauses and falls back to
publication order. Sorting a change list by effective date will show nulls in a bucket rather than
interleaved. Both surface in phase 1.4 and 1.5 as a UI state to design, not as a defect.

**Reversible.** Adding a resolved-date column later is additive and re-derivable from the retained
phrase — the phrase is the input a resolver needs. The reverse would not be: a guessed date written
into `effective_date` and then cited cannot be distinguished from an authoritative one after the
fact, and citations are never rewritten (ADR-0002 decision 4). The asymmetry is why this is the
safe default even if a resolver later proves accurate.

## Alternatives rejected

- **Computed date with a confidence flag.** More useful for alert prioritisation, and the reason it
  was tempting. Rejected because it puts a low-confidence value in the Citation tuple; the failure
  mode is silent and only detectable by audit.
- **Both columns — clean `effective_date` plus a separate `resolved_effective_date`.** Preserves the
  citation contract and keeps alerting ordered. Rejected *for now* on cost, not on principle: it
  needs a documented rule about which reader uses which column, and Phase 1 has no resolver to
  populate it. If phase 1.6 shows the null bucket is large enough to hurt alerting, this is the
  extension to make, and the retained phrase is exactly what it would be built on.
