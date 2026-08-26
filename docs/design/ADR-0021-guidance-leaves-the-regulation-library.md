# ADR-0021 — The regulation library holds binding text; guidance leaves it, and where it goes is not decided here

- **Status:** Accepted
- **Date:** 2026-08-26
- **Amends:** [ADR-0018](ADR-0018-fda-source-model.md) decision 9 — *"guidance is stored, citable,
  and never extracted"*. The storing half is reversed. The never-extracted half is kept and becomes
  structural rather than a rule someone has to remember.
- **Confirms:** [ADR-0002](ADR-0002-canonical-regulation-model.md) decision 6 (the Citation tuple),
  [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) decision 1 (the modal inventory is
  closed), [ADR-0006](ADR-0006-retrieval-and-citation-enforced-generation.md) (no answer without
  evidence)
- **Defers:** which channel guidance travels instead — three candidates are recorded below and
  **none is chosen**. See *Decision 3*.

---

## Context

[ADR-0018](ADR-0018-fda-source-model.md) decision 9 answered *"does the Guidance block belong in
`documents` at all"* with **yes**, on one sentence of reasoning:

> Storing nonbinding text that is never extracted still buys citation-enforced retrieval, which is
> most of what an RA asks guidance for.

That is a real benefit and it is not disputed here. What the decision did not have, on 2026-08-24,
was the cost — and two other things have since been measured that it could not have weighed.

**Nothing was ever ingested.** Across all eight cells: **0 documents** with `doc_type = guidance`,
**0 source rows** in the `guidance` block — not seeded, anywhere — and **0 clauses** carrying
`ExclusionReason.NON_BINDING`. The gated MFDS pair reached Phase 1 acceptance without a line of
guidance in the store. So this is not the removal of something working; it is declining to build
something that has never existed, which is the cheapest moment such a decision is ever available.

**The acquisition route turned out to be poor** ([phase2.0a](../plan/phase2.0a_fda.md)
*Deviations* 37). openFDA's own catalogue lists 9 namespaces and 24 endpoints and **none is
guidance**. The FDA guidance index is a Drupal DataTables view whose only working backend is
`POST /views/ajax`, returning rendered HTML inside an AJAX command envelope — one CMS's internal
response format, with no version to pin and no notice when it changes. The documents themselves are
HTML and PDF, and nothing in the pipeline extracts PDF. `robots.txt` permits the crawl and asks for
`Crawl-Delay: 30`, which the current fetcher would exceed by 30×.

That is a cost, and costs change. **The structural argument does not**, and it is the one that
decides this.

**A guidance citation is a weaker object than the contract assumes.** A `Citation` is
`(document_id, document_version_id, clause_path, effective_date)` pinned to an immutable version
(ADR-0002 decision 6). Guidance has no `effective_date` in the legal sense — it takes effect on
nobody. [ADR-0013](ADR-0013-unresolvable-effective-dates.md) makes that *representable* as a null
with the phrase retained, so nothing crashes; it stays weaker all the same.

**And the failure it invites is the worst one available in this domain.** Retrieval scopes on cell,
not on `doc_type` — `versions_in_scope` does not filter by it. So a fused answer can cite a
regulation and a guidance document side by side, in one list, under one contract that promises
clause-level evidence. A reader who acts on nonbinding text as though it bound them is the single
most damaging mistake regulatory work has, and the product would have handed it to them with a
citation attached. Decision 9 excluded guidance from *extraction* and from the *coverage
denominator*; it did not exclude it from the sentence a person reads.

## Decision

### 1. The regulation library holds binding instruments only

`documents` is for text that imposes obligations: statutes, decrees, enforcement rules, 고시,
CFR Parts, codified statutes, and their annexes. **Guidance does not enter it**, in any cell — this
is not an FDA rule. The `Guidance` block exists in the MFDS, EU and NMPA sections of
[import-source-map.md](../import-source-map.md) too, and the same reasoning applies to all of them.

This makes ADR-0018 decision 9's *"never extracted"* structural instead of procedural. Extraction no
longer needs a `doc_type` skip for nonbinding instruments, because no nonbinding instrument is in
the store to skip. A rule that cannot be forgotten beats one that must be remembered.

### 2. `DocType.GUIDANCE` and `ExclusionReason.NON_BINDING` stay in the enums, unused

Neither is dropped. Removing an enum value is a migration against a live type for no benefit, and
both are the correct name for their concept the day a channel decision brings nonbinding text back
into reach.

They are **unused, and that is now their documented state** rather than an omission somebody might
try to fix. `NON_BINDING` currently has 0 rows and would have had 0 rows under decision 9 as well,
since nothing was ingested.

### 3. Which channel guidance travels is **deferred**, and the candidates are recorded

An RA reads guidance. Removing it from the regulation library does not remove the need, and this
ADR deliberately does **not** answer where it goes — the answer depends on evidence nobody has yet,
and picking now would be the same mistake decision 9 made in the other direction.

Three candidates, with what each buys and what it costs:

| | Channel | Buys | Costs | Citation contract |
| --- | --- | --- | --- | --- |
| **1** | **A reference library** — its own store beside the regulation library, searchable, outside the citation contract | Full text search over what an RA actually reads | A second store, its own retrieval path, and a UI that must never let the two look alike | Outside it. Answers would have to mark guidance as non-evidence |
| **2** | **Link-only** — record title, issuer, revision date and a deep link; store no text | Cheapest by far; no acquisition problem, no PDF extractor, no crawl | The reader leaves the product to read the thing | Not a citation at all — a pointer |
| **3** | **A change signal only** — guidance revisions become monitoring events; nothing is stored as text | *"FDA revised the SaMD guidance"* is a large part of what an RA wants, and it is pillar 1's job rather than pillar 2's | Answers still cannot quote guidance | None needed. An alert is not an answer |

**What would settle it** — and none of it exists today:

- Whether pilot users ask *"what does the guidance say"* (channel 1) or *"has the guidance changed"*
  (channel 3). The phase 1.6 pilot is the instrument that would tell us and it has not run.
- Whether a guidance revision is detectable without storing the text. If a revision date is
  published, channel 3 costs almost nothing; if it is not, channel 3 collapses into channel 1.
- Whether the acquisition route improves. FDA's index is internal plumbing today; an actual API
  would make 1 and 2 cheap and would not change the argument in *Context* one bit.

Channels 2 and 3 compose — a link plus a revision alert is a coherent product on its own — and 1
subsumes both at the highest cost. **Nothing in this ADR forecloses any of them.**

## Consequences

- **Nothing to migrate, nothing to delete.** 0 documents, 0 source rows, 0 classifications. The
  decision is free today and would not have been once a corpus existed, which is the argument for
  making it now.
- **[ADR-0018](ADR-0018-fda-source-model.md) decision 10 stays correct and becomes uninteresting.**
  It defined the coverage denominator over obligation-bearing `doc_type`s so that storing guidance
  would not enlarge it. Nothing enlarges it now. The definition is still the right one and no longer
  load-bearing.
- **`should` still does not join the modal inventory.** ADR-0004 decision 1 closes it, and the
  reason decision 9 gave holds with more force: the inventory is shared by every cell including the
  gated MFDS pair, and it must not move to accommodate documents that are no longer stored.
- **[import-source-map.md](../import-source-map.md) keeps its `Guidance` blocks.** They are a true
  inventory of what exists per cell, and the source map is the single catalog — deleting real
  sources from it to reflect a routing decision would make it lie about the world. They are simply
  not sources for this library until *Decision 3* is answered.
- **The FDA acquisition problem stops being urgent.** phase2.0a *Deviations* 20 deferred the
  Guidance block because `fda.gov` was thought to be blocking us; *Deviations* 36 showed it is not,
  and *Deviations* 37 showed the route is unusable anyway. Under this ADR none of that is on the
  critical path.
- **Retrieval needs no `doc_type` filter.** The mixed-citation risk in *Context* disappears by
  construction rather than by a guard someone has to add and keep.

## Alternatives rejected

- **Keep guidance in `documents` and filter it out at retrieval.** The obvious smaller change, and
  it puts the safety property in a `WHERE` clause that one future query can forget. The store would
  hold text the contract cannot cite, waiting for someone to cite it.
- **Keep it and mark guidance citations as non-binding in the answer.** Better, and still a labelling
  promise rather than a structural one — it survives exactly as long as every prompt, renderer and
  export remembers to carry the flag.
- **Add `should` and extract guidance properly.** Changes extraction for all eight cells to
  accommodate nonbinding text, and would make guidance produce IRs — obligations that bind nobody,
  entering gap analysis as findings. This is the failure ADR-0004 decision 1 closes the inventory
  against.
- **Decide the channel now.** Tempting, and it would be decided without the pilot evidence that
  distinguishes *"what does it say"* from *"has it changed"* — the same shape of mistake as deciding
  storage without knowing acquisition cost. Recorded as deferred, with what would settle it.
- **Drop guidance from scope entirely.** Overshoots. RegOps.md lists guidance per cell and an RA
  reads it; the need is real and only its channel is open.
