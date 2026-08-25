# ADR-0018 — FDA sources: the eCFR is the text and the version spine, the Federal Register is the effective date

- **Status:** Accepted
- **Date:** 2026-08-24
- **Closes:** [ADR-0002](ADR-0002-canonical-regulation-model.md) open question 3 for
  `authority = fda` — the question already anticipated "CFR citation for FDA" and deferred it
- **Extends:** [ADR-0016](ADR-0016-pending-effect-versions.md) decisions 1 and 3 — the authority's
  own key is the version key, and `effective_date` comes from the envelope where the authority states
  it. Both transfer; decision 6 transfers **vacuously**, and that is a finding rather than a
  formality
- **Confirms:** [ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 12 (the authority's
  own change history), [ADR-0013](ADR-0013-unresolvable-effective-dates.md),
  [ADR-0014](ADR-0014-annex-row-granularity.md)
- **Forced by:** [phase2.0a](../plan/phase2.0a_fda.md) — *"Decisions to close before the build"*,
  three of them, all here
- **Evidence:** [spike-2026-08-24](spike-2026-08-24-fda-source-recon.md). Every claim below is
  measured; nothing rests on the `docs/reference/` research, which was wrong on the two facts that
  matter most

---

## Context

MFDS hands over the current full text *and* `시행일자` in one envelope. FDA splits them, and
[phase2.0a](../plan/phase2.0a_fda.md) named that split its Risk 1 on the assumption that citation
quality would live in the eCFR while detection latency lived only in the Federal Register — reachable
by RSS. **Measurement says the split is real and the mitigation was wrong.** The eCFR is not merely a
compiled text surface; it publishes its own structured change history.

| What was assumed | What the probes returned |
|---|---|
| eCFR point-in-time "where the API offers it" | Real, honoured, and section-addressable. Two dates inside one version window are byte-identical; across the QMSR boundary they differ (66,042 → 21,523 bytes) |
| Change detection needs the Federal Register or a per-Part RSS feed | `versions/title-21.json` returns **per-section** rows carrying `amendment_date`, `issue_date`, `removed` and `substantive`. The guessable RSS path returns 302 with 0 bytes |
| Federal Register names the amended `21 CFR` provisions | `cfr_references` is **Part-level only**; `effective_on` is a structured, **nullable** date |
| — | **The eCFR refuses future dates.** `2026-09-30` → 404 *"past the title's most recent issue date of 2026-08-20"* |

Two structural facts drive everything below.

**First, the authority states its own citation.** Every eCFR node carries
`hierarchy_metadata={"path":…,"citation":"21 CFR 820.1"}`. ADR-0016 decision 3 established the
principle — take what the authority states, do not re-derive it — and here it applies to identity, not
just to dates.

**Second, there is no pending text.** MFDS `target=eflaw` serves the 시행예정 본문 two months to 2.4
years early, which is what makes the ≤24h gate meetable there. The eCFR serves nothing past
`up_to_date_as_of`, while the Federal Register currently carries **5 future-effective FDA rules, one
effective 2033-03-07**. So FDA announces amendments years ahead and withholds the text until they
bite. The detection gate is therefore met on the *announcement*, and the corpus follows later.

## Decision

### Part A — identity

#### 1. A `Document` is a CFR **Part**; a `Section` is a `Clause`

The Part is the unit the Federal Register names (`cfr_references` carries `part`, never a section),
the unit that carries `<AUTH>` and `<SOURCE>`, and the unit a single call returns. Sections are the
obligation-bearing provisions — the structural role 조 plays — so they are clauses.

Making a Section a Document was rejected: title 21 has **8,408** of them, one Federal Register rule
routinely amends a whole Part, and every such rule would fan out to dozens of Documents whose
versions then have to be kept consistent with each other for no gain.

`path_segments` is `[subpart, section, paragraph…]` and `clause_path` renders the way a US regulatory
professional writes a citation — **`21 CFR 820.35(a)(1)`**, never a transliteration of 조/항/호/목.

#### 2. `canonical_key` is the citation the authority already publishes, normalized

Following the existing `{authority}:{block}:{id}` convention
([law_go_kr.py](../../services/regulation/app/connectors/law_go_kr.py#L248), `mfds:law:002015`):

| Instrument | `canonical_key` | `doc_type` |
|---|---|---|
| A CFR Part | `fda:cfr:21-820` | `REGULATION` (new — decision 3) |
| A CFR appendix | `fda:cfr:21-101#appendix-B` | `ANNEX` |
| The FD&C Act | `fda:usc:21-9` | `LAW` |
| A guidance document | `fda:guidance:{fda-document-number}` | `GUIDANCE` |

It survives redesignation because a section being renumbered does not change the Part's key, and it
gives an appendix a **derivable child key** exactly as `…#별표N` does — the parent key plus the
appendix letter.

Three edge cases from the spike, all decided against normalizing:

- **Appendix identifiers are prose with spaces** (`Appendix B to Part 101`). The key takes the letter
  only; the full string stays in `title`.
- **Range-named nodes exist** — `820.20-820.30` is one section and `C-O` one subpart. The authority's
  `N` is kept **verbatim** as the path segment. Splitting a range into its endpoints would invent
  provisions that do not exist.
- **`subject_group` never enters a key or a path.** There are 102 in title 21 and their identifiers
  are opaque generated tokens (`ECFRef316bd359c83c7`). A subject group becomes a `Clause` excluded as
  `HEADING`, the same treatment 편/장/절/관 get.

#### 3. `DocType` gains `REGULATION`; the profile still keys on the value, never on the cell

`LAW` / `DECREE` / `ENFORCEMENT_RULE` name positions in the Korean statutory ladder
([constants.py](../../shared/regops_shared/constants.py#L108)). A CFR Part is a codified agency rule
issued directly under a statute, with no 시행령 tier between them, so mapping it to
`ENFORCEMENT_RULE` would assert a hierarchy that does not exist. `REGULATION = "regulation"` is added
as a domain-neutral value; the FD&C Act takes `LAW`.

This is a `constants.py` change **authorised here and made in the build slice**, not in the commit
carrying this ADR.

### Part B — the two surfaces

#### 4. The eCFR owns Document identity *and* the version spine. A Federal Register rule is not a `Document`

One `DocumentVersion` per **distinct `issue_date` at which any section of the Part changed**, fetched
as the point-in-time snapshot at that date. The set of such dates is not guessed — it is
`{issue_date}` from `versions/title-21.json?part=NNN`, which is the authority's own record.

This is ADR-0016 decision 1 with a different key: there, a version was one MST because the authority
keyed its snapshots that way; here the authority keys them by date. In both cases the version key is
the authority's, so it cannot drift from theirs.

A Federal Register rule is **provenance on the version**, not a Document of its own. It has no
independent text we cite from: its body announces a change to the CFR, and the CFR is what an RA
cites. Modelling it as a Document that a version cites was rejected — it would double every
amendment, and `cfr_references` is too coarse (Part-level) to link it to the clauses that moved.

**The join between the surfaces is date-and-Part, and it is best-effort.** The eCFR `<SOURCE>` for
part 820 reads `89 FR 7523` while the Federal Register calls the same rule `89 FR 7496` — 7523 is the
page *inside* it where part 820 begins. Joining on the citation string fails on every section. Where
the join succeeds it enriches the version; where it fails the version is still complete, and nothing
is invented to fill the gap.

#### 5. `effective_date` is the Federal Register's `effective_on`, falling back to the eCFR's `amendment_date`

ADR-0016 decision 3 unchanged in principle: the envelope where the authority states it.

- **`effective_on`** is envelope-grade — a structured date field, the legally stated one. Preferred
  wherever the version joins to a rule.
- **`amendment_date`** from the `versions` endpoint is the fallback. Also authority-stated, but it is
  when the compilation absorbed the change, not when the rule bit: the QMSR is `effective_on`
  2026-02-02 and `amendment_date` 2026-02-04. Two days, and the difference is real.
- **`effective_date_phrase`** is the Federal Register `dates` prose, verbatim
  (*"This rule is effective February 2, 2026. The incorporation by reference…"*).
- **`effective_on` is nullable** — one of five sampled rules returned null.
  [ADR-0013](ADR-0013-unresolvable-effective-dates.md) applies as written: null with the phrase
  retained, never a derived date entering the Citation tuple.

The 부칙 parser ([parsing/dates.py](../../services/regulation/app/parsing/dates.py)) is neither reused
nor extended. Both dates arrive as fields; there is no prose to parse for the value.

#### 6. Detection polls the eCFR `versions` endpoint. The Federal Register is the pending-effect surface, not the fallback

`GET versions/title-21.json?issue_date[gte]={last_seen}`, filtered to the Parts in scope. It returned
60 section rows over seven weeks, of which 2 touched Parts in scope — a change stream small enough to
poll often and structured enough to route without parsing.

This makes [ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 12 — *use the authority's
own change history as an independent check* — the **primary** signal for this authority rather than a
cross-check. Hash-first detection (decision 2) still runs; it is what catches a change the endpoint
failed to report.

`substantive` is **recorded and not acted on** in `regulation`. Whether a non-substantive amendment
deserves an alert is a grading judgement, and grading belongs to `monitoring` on the other side of the
seam — the same reason the diff stage dispatches `monitoring.route_change_events` even when every diff
was a renumber.

The Federal Register is polled for a different purpose: **it is the only surface that shows an
amendment before it exists.** A future-effective rule produces no `DocumentVersion`, because there is
no text to version — the eCFR 404s on any date past `up_to_date_as_of`.

#### 7. A pending FDA amendment is a signal without a version, and this is a stated gap

ADR-0016 decision 6 says the in-force version is `max(effective_date) where effective_date <= today`,
with no status flag. That rule holds here **vacuously**: no FDA version ever has a future
`effective_date`, because the text is unavailable until it is in force.

So the FDA cells cannot answer *"what will 21 CFR 820 say on 2027-01-15"* the way the MFDS cells can.
What they can answer is *"a rule effective 2027-01-15 was published, here it is, and it amends Part
74"*. Recording that as a change signal against the Part, with the rule's own document number and
`effective_on`, is the honest floor.

**Do not synthesise a pending version** by applying the rule's body to the current text. That is
generating regulation text, it would enter the clause store indistinguishable from fetched text, and
it is the failure mode the whole citation contract exists to prevent.

#### 8. Redesignation relies on the similarity fallback, because FDA states removal but not movement

The `versions` endpoint carries `removed: True` — 27 of 72 rows for part 820, which is how the QMSR
transition is recorded. That is a genuine signal and better than expected.

It is not a *move* signal. MFDS supplies `조문변경여부` / `조문이동이전` / `조문이동이후`, so a
renumber is **stated** — which is why
[ADR-0002](ADR-0002-canonical-regulation-model.md) decision 7 is titled *"via an explicit mapping,
not heuristics"*. FDA supplies nothing equivalent.

So CFR redesignation runs on the other half of that same decision — **content similarity plus
explicit mapping rows, with RA review where confidence is low**, which decision 7 already prescribes
for "sources that expose nothing". This is not a departure from it: similarity alone was never the
decision, and it is not the decision here either. `change_kind ∈ {added, removed, modified,
renumbered, moved}` is unchanged, and `moved` keeps its phase-1.1 meaning — same identifier, different
parent — which a CFR section moving between subparts fits exactly.

Renumbering must still never be delete+add. **It must be tested on real CFR data before either cell
is gated**, because this is the first time the mapping path carries a gated cell without a stated
move signal underneath it. The `removed` flag helps: it distinguishes "the authority deleted this"
from "our differ lost it", which MFDS never had to.

### Part C — guidance

#### 9. Guidance is stored, citable, and never extracted — excluded at `doc_type` level with a reason

FDA guidance is explicitly nonbinding. The English modal inventory is `shall` · `must` ·
`is required to` · `may not` ([constants.py](../../shared/regops_shared/constants.py#L500)) and has
no `should`, so extraction over guidance yields zero IRs. That is the **correct** result and it reads
as a coverage hole unless it is stated as a rule.

- **Guidance enters `documents`** with `doc_type = GUIDANCE`. Storing nonbinding text that is never
  extracted still buys citation-enforced retrieval, which is most of what an RA asks guidance for.
  The cost is accepted explicitly: it enlarges the corpus the coverage denominator is measured
  against, so the denominator is defined over **obligation-bearing `doc_type`s only** (decision 10).
- **Extraction skips it by `doc_type`**, not by cell and not by authority, and writes one excluded row
  per clause carrying a new `ExclusionReason.NON_BINDING`. None of the existing eleven values means
  "the instrument itself binds nobody" — `PERMISSIVE` is about a modal inside a binding instrument.
  Examined-and-excluded, never unexamined.
- **`should` is not added to `MODAL_INVENTORY`.** The inventory is closed by
  [ADR-0004](ADR-0004-ir-extraction-and-domain-branching.md) decision 1 and an IR whose modal falls
  outside its language's tuple is rejected. Adding `should` would change extraction for every cell,
  including the gated MFDS pair, to accommodate documents this decision excludes anyway.

#### 10. The detection-coverage denominator is the sections of the in-scope Parts, from the structure endpoint

phase2.0a records the ≥95% coverage gate as unmeasurable for FDA on the grounds that
`regulation.discover_sources` enumerates MFDS 행정규칙 by 소관부처 code and FDA has no equivalent.
It has a better one: `structure/current/title-21.json` enumerates all 275 Parts and 8,408 Sections,
and every Part named in [import-source-map.md](../import-source-map.md) is present and unreserved.

The denominator is **sections of the in-scope Parts of `doc_type` `REGULATION` or `LAW`**, computed
per cell from that call. Guidance is outside it, per decision 9. It is a closed, authority-published
list, which is a stronger denominator than the MFDS cells have.

## Consequences

**Good.** Version identity is the authority's own date, so it cannot drift. Detection is
section-granular, structured, and independent of the text fetch — a change is *reported* rather than
inferred from a hash. The coverage gate has a real denominator, and the removal flag makes the QMSR
transition legible without heuristics. The two surfaces corroborated on a live amendment
(`892.5060` amended 2026-08-06 = 91 FR 50708 of the same day), so the join is not theoretical.

**Cost — pending amendments are announced but not readable.** The clause store cannot show future
text, and one rule on the books today is effective 2033-03-07. Detection meets the gate on the
announcement; the corpus catches up years later. MFDS is strictly better served here, and no amount of
engineering on our side changes it.

**Cost — `cfr_structured` is more parser than the MFDS profiles.** Paragraph designations `(a)(1)(i)(A)`
arrive as **inline prose** inside `<P>`, where MFDS delivers 조/항/호/목 as separate fields with
nothing to segment. Plus a non-uniform hierarchy — Part 710 has sections and no subparts while the
other twelve in scope have subparts and no direct sections — and a `subject_group` level with no
Korean equivalent. phase2.0a Risk 2 priced this as phase-1.1-sized work; that pricing stands.

**Cost — the eCFR↔Federal Register join is best-effort.** The page-number mismatch (`89 FR 7523` vs
`89 FR 7496`) means some versions will carry `amendment_date` as their `effective_date` rather than
the legally stated `effective_on`, and the two can differ by days. Where that happens the version is
correct but less precise, and it is visible as an absent rule link rather than as a wrong date.

**Cost — redesignation is now carried by the similarity fallback.** ADR-0002 decision 7's primary,
stated path does not exist for this authority. The fallback was written for exactly this and has never
been the load-bearing path in a gated cell.

**One phase2.0a item is answered better than it was asked.** Its W0 asks *"what is the denominator for
detection coverage in these cells?"* and warns the gate is unmeasurable until someone answers.
Decision 10 answers it from the structure endpoint, so the gate is measurable from W0 rather than
being defined into existence.

## Alternatives rejected

- **eCFR only, with no Federal Register connector.** Loses `effective_on` — the legally stated
  effective date — leaving `amendment_date`, which is when the compilation absorbed the change.
  Two days wrong on the QMSR, and it would make pending amendments completely invisible: no surface
  would show the 2033-03-07 rule at all.
- **Federal Register only.** There is no compiled current text, so a citation would resolve to an
  amendment fragment rather than to the operative provision, and `cfr_references` is Part-level so
  clause-level citation would be impossible. This is the ADR-0016 failure mode restated: polling only
  the announcement surface.
- **A Federal Register rule as its own `Document` that a version cites.** phase2.0a offered this as
  the alternative to the ADR-0016 shape. Rejected: it doubles every amendment into two Documents,
  the FR body is not what an RA cites, and `cfr_references` cannot tie it to the clauses that changed.
- **A Section as the `Document`.** Matches the eCFR's own section-addressability and the granularity
  of `versions`. Rejected at 8,408 Documents per title, where one rule amending a Part becomes dozens
  of Document versions that must stay mutually consistent.
- **One version per section-amendment rather than per Part snapshot.** Follows `versions` exactly, and
  produces a Part whose sections are at different versions — there would be no single version of
  21 CFR 820 to cite or to diff against.
- **RSS as the detection surface**, as all four `docs/reference/` documents recommend. The one
  guessable path returns 302 with 0 bytes, no per-Part feed URL was found, and the `versions` endpoint
  is strictly better: structured, section-level, and carrying `removed` and `substantive`.
- **openFDA as a regulation source.** It carries 510(k), PMA, classification, recalls, MAUDE and UDI —
  regulatory data, no regulation text. The undecomposed phase 2.0 named it and named neither eCFR nor
  govinfo; that is the catalog error, now corrected.
- **Synthesising a pending version from a rule's body.** Would restore parity with MFDS eflaw and
  requires generating regulation text that then sits in the clause store indistinguishable from
  fetched text. Refused on the citation contract.
- **Adding `should` to the modal inventory so guidance yields IRs.** Breaks a closed inventory across
  all eight cells to extract obligations from instruments that state none.

## Open questions

1. **How far does the eCFR `versions` endpoint lag the Federal Register?** **Being measured** —
   `scripts/fda_lag/` runs daily into
   [fda-lag-observations.jsonl](fda-lag-observations.jsonl); it renders `UNDETERMINED` and exits
   non-zero until ten distinct days are in, so the number cannot be quoted early. Decision 6 rests
   on the answer.

   The metric is **not** the naive one. Observation date minus `up_to_date_as_of` was 4 days on the
   first run, which reads as a failed gate but was a weekend — a compilation that has not advanced
   because nothing was amended is indistinguishable, by that number, from one that is behind. The
   harness reports the **blind spot**: days since the oldest rule already in force yet absent from
   the compilation. First observation: **0**, with raw freshness recorded beside it as context.

   Day granularity is the endpoint's own — `up_to_date_as_of` is a date, not a timestamp — so this
   can bound the lag at ≤1 day and can never *prove* ≤24h. That bound is what decision 6 needs.
2. **Is a `removed` row followed by a re-added identifier distinguishable from a redesignation?**
   Decision 8 routes this to the similarity fallback; whether the fallback actually separates the two
   on CFR data is untested.
3. **The FD&C Act's version identity on govinfo.** `USCODE` is confirmed present; the granularity, and
   whether `document_versions` can carry it, were not probed. Decision 2 assigns it a key on the
   assumption that it can.
4. **How is the guidance corpus enumerated?** There is no API and no crawl was attempted. Decision 9
   settles how guidance is *treated*; it does not settle how it is *found*.
5. **Part 710 is still titled *Voluntary* Registration of Cosmetic Product Establishments** while
   MoCRA made facility registration mandatory. Which the `fda_cosmetic` cell treats as authoritative
   is a scope question for [import-source-map.md](../import-source-map.md), not a connector question.

6. **`ecfr.gov/robots.txt` disallows `/api/versioner/v1/full/` — the endpoint decision 4 makes the
   version spine.** Found after this ADR was accepted
   ([spike Part 2](spike-2026-08-24-fda-source-recon.md) Q4). The rule sits under `User-agent: *`
   with no API exemption; the comment above it says *"Don't index developer tool links"*, which reads
   as anti-indexing rather than anti-API, and the endpoint is documented for developers. Both
   readings are defensible and [ADR-0003](ADR-0003-ingestion-and-change-detection.md) decision 9
   makes politeness part of the contract, so this needs a decision before the eCFR connector fetches
   body text. **Detection is unaffected** — `versions/` is not disallowed — so decision 6 stands
   whichever way this goes. The `renderer` alternative is disallowed too.

7. **The FD&C Act versions annually, against a ≤24h gate.** govinfo publishes the USC as
   `USCODE-{year}-title21` — one edition a year, section-granular
   ([spike Part 2](spike-2026-08-24-fda-source-recon.md) Q5). Decision 2 gives the act a
   `canonical_key` and decision 1 makes it a Document claimed by both cells, but neither anticipated
   that its *only* probed surface refreshes yearly. An FD&C Act amendment would be invisible until
   the next edition. Public Laws (govinfo `PLAW`) are the likely announcement surface and were not
   probed. Until this is settled the statute cannot carry the detection gate the regulations can.
