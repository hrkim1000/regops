# ADR-0015 — Diff is its own stage, dispatched by task name

- **Status:** Accepted
- **Date:** 2026-08-06
- **Closes:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md) open question 4
- **Due:** W3–4 ([plan/README](../plan/README.md) § Decisions due) — it is a stage boundary in the
  [phase1.1](../plan/phase1.1_normalization.md) pipeline, so it is fixed by the clause schema and
  cannot be deferred past it

---

## Context

[ADR-0003](ADR-0003-ingestion-and-change-detection.md) draws the pipeline as five stages —
`fetch → archive → parse → diff → emit` — and then asks in open question 4 whether `parse` and `diff`
are actually one unit of work: *"Parsing then diffing inline is simpler; splitting them lets a
re-parse with an improved profile re-diff historical versions without re-fetching. Leaning split, but
it costs a stage boundary."*

Inline is genuinely simpler. The parse stage already holds the new clauses in memory, and diffing
there avoids a task hop, a second transaction, and a second place where a crash can land.

## Decision

**`parse` and `diff` are separate Celery tasks on the `regulation` queue, chained by task name.**

```text
regulation.parse_document_version(version_id)     writes clauses, commits
        └─ send_task("regulation.diff_document_version", [version_id])
regulation.diff_document_version(version_id)      writes clause_diffs + change_events
```

Three properties follow, and the third is the one that decided it:

1. **Re-parsing is re-runnable in isolation.** `parse` is idempotent per `document_version_id`: it
   deletes the clauses it previously wrote for that version and writes them again. A corrected parser
   profile is applied by re-enqueueing `parse` over the affected versions, reading from the WORM
   archive — no re-fetch, and no politeness cost against a government host for a bug that is ours.
2. **Diff can be re-run without re-parsing**, which is what makes renumber-detection tuning
   affordable. Renumbering resolution is the part of this phase most likely to need calibration
   against real amendments, and coupling it to parse would mean re-deriving every clause to change a
   similarity threshold.
3. **A parse failure cannot suppress a clause store.** With the stages fused, a diff bug raises
   inside the same transaction as the clause write, so a version that parsed perfectly well ends up
   with no clauses. Split, `parse` commits first and the diff retries against committed rows.

**Emission stays inside `diff`.** ADR-0003 draws `emit` as a fifth stage, but a `ChangeEvent` is
derived from a `ClauseDiff` by a pure fan-out over the claiming cells — there is no independent
input, nothing to recompute separately, and no reason to make an empty diff pay for a task hop. The
two are one transaction: a diff that is committed without its events would under-report detection
coverage, and that is the gate this layer is measured on.

**The boundary is a task name, not an import.** `parse` never imports the diff module, matching the
cross-service rule in CLAUDE.md § Celery Queue Architecture even though both stages live in
`regulation` — the same discipline that already governs `ingest → parse`.

## Consequences

**Good.** Each stage is independently resumable and independently re-runnable, which is what
ADR-0003's "idempotent and independently resumable" already asked of every stage. Reprocessing the
archive with a better profile becomes an operational routine rather than a re-ingestion.

**A re-parse must invalidate the diffs derived from it.** Property 1 above makes re-parsing routine,
and routine operations must not corrupt the change history. `clause_diffs` references clauses
`ON DELETE SET NULL`, so replacing a version's clauses leaves its diffs with null endpoints —
describing a parse that no longer exists, with live `ChangeEvent` rows still hanging off them.
Observed for real during phase 1.1: one corpus re-parse orphaned **2,373** of them.

So `parse` deletes the diffs touching that version in **both** directions — into it, and the
successor's comparison *out of* it, which points at the clauses just deleted — and re-enqueues the
diff for the version and for its successor. `change_events` cascade with the diff, which is right:
an event whose evidence has been re-derived must be re-derived too, not left pointing at nothing.

**Cost.** One task hop per new version, and a window — bounded by queue latency — in which clauses
exist and their diffs do not. A reader querying `change_events` during that window sees a version
that has not been diffed yet. This is visible rather than silent: the diff task records its run
against the version, so "parsed but not diffed" is a queryable state and not an indistinguishable
absence.

Detection *latency* is unaffected. The gate measures 공포 → alert, and both stages run in the same
worker pool within seconds of the fetch.

## Alternatives rejected

- **Diff inline inside `parse`.** Simpler, and rejected on consequence 3 above: a diff-stage defect
  would prevent clauses from being committed at all. It also makes profile improvement expensive
  exactly where it is most likely to be needed.
- **A third `emit` task, as ADR-0003's diagram literally shows.** No independent input and no
  independent failure mode; splitting it would let a diff commit without its change events, which
  loses detection coverage in the one place it is measured.
