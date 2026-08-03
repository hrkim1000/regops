# ADR-0012 — Annexes are child Documents, not attachments on a version

- **Status:** Accepted
- **Date:** 2026-08-03
- **Amends:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 10 and its schema
  sketch; extends [ADR-0002](ADR-0002-canonical-regulation-model.md) decision 1
- **Forced by:** [phase1.0](../plan/phase1.0_ingestion.md) acceptance criterion — "amending 별표 2
  alone creates a version for the annex and not the body"

---

## Context

ADR-0003 decision 10 requires that a connector return "a body artefact **plus zero or more
attachment artefacts**, each archived, hashed and versioned independently," and its schema sketch
records that as:

```sql
attachments(id, document_version_id, kind, title, ordinal, file_format,
            source_url, content_hash, raw_object_key, effective_date)
```

Writing the migration surfaced a contradiction between the sentence and the table. A row keyed on
`document_version_id` is a **child of a version**. It cannot version independently of that version:
creating a new annex row requires a new parent `document_version` to hang it from, which is exactly
the outcome the acceptance criterion forbids. Nothing about the shape is fixable by adding columns —
`attachments.effective_date` gives the annex its own date but still not its own version identity or
its own diff lineage.

This is not hypothetical for the gated cells. 별표 1 and 별표 2 of 화장품 안전기준 등에 관한 규정 are
where the substantive `mfds_cosmetic` obligations live (spike 2026-07-29: 340 K and 219 K characters
of fixed-width table), and the authority publishes `별표시행일자문자열` — an annex-specific
enforcement date — precisely because annexes move on their own schedule.

## Decision

**An annex is a `Document` in its own right, with `parent_document_id` pointing at the body.**

- `documents.doc_type = 'annex'`, `documents.annex_no` carries 별표번호, and
  `canonical_key = f"{parent_key}#별표{annex_no}"` so it is addressable without a second identifier
  scheme.
- It gets its own `document_versions` rows: its own `content_hash`, its own `raw_object_key`, its
  own `effective_date`, and — from phase 1.1 — its own clauses and its own `ClauseDiff` lineage.
- A `CHECK` constraint makes the two directions agree: `doc_type = 'annex'` if and only if
  `parent_document_id IS NOT NULL`. An annex cannot be orphaned and a body cannot claim a parent.

**`attachments` survives, with a narrower job**: the authority's own file links
(`별표서식파일링크`, `별표서식PDF파일링크`) recorded per version as an archival copy and as the
fallback for the case where `별표내용` comes back empty. It is no longer the ingestion route, which
matches ADR-0003 decision 10 as revised after the live API test — annex text arrives inline in
행정규칙 본문조회, so HWP/PDF extraction is off the Phase 1 critical path. `raw_object_key` on an
attachment stays null unless the source opts into archiving the binary; fetching every government
attachment on every poll is a politeness cost with no Phase 1 payoff.

## Consequences

**Good.** Annex versioning, diffing, citation and change-event fan-out are the *same* machinery as
the body's — no parallel code path, and a citation into 별표 2 is structurally identical to one into
제8조. It also means the ADR-0002 decision 1 M:N claim applies to annexes for free: an annex claimed
by both `mfds_samd` and `mfds_cosmetic` is ingested once.

**Cost.** `documents` is now a shallow tree rather than a flat list, so any query that means "the
body only" must filter on `doc_type` or `parent_document_id IS NULL`. Document counts per cell will
read higher than the number of instruments — a 고시 with four annexes is five `documents` rows. Both
are worth it against re-parsing the archive later.

**Not decided here.** Whether annex table *rows* become `Clause` rows or a separate row store is
[ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md) open question 3, still open and
due W4. This ADR settles the container, not the granularity inside it.

## Alternatives rejected

- **Keep `attachments` as the ingestion route and add a version counter to it.** Reimplements
  version identity, WORM keying, and diff lineage as a second, weaker copy of `document_versions`.
- **Give annexes their own top-level `Document` with no parent link.** Loses the ability to answer
  "what changed in this 고시" as one question, and makes the fan-out to claiming cells manual.
