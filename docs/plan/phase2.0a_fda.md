# Phase 2.0a — FDA cells (SaMD + Cosmetic)

- **Roadmap:** Phase 2 (M5–12) · **Status:** ⬜ planned
- **Slice of:** [phase2.0](phase2.0_tier_c_scale.md) — scope completion, decomposed by cell group
- **Governed by:** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decisions 3 · 5, [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md), [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decisions 1 · 3, [ADR-0012](../design/ADR-0012-annex-version-identity.md), [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md), [ADR-0014](../design/ADR-0014-annex-row-granularity.md), [ADR-0016](../design/ADR-0016-pending-effect-versions.md)
- **Decides here:** ✅ **[ADR-0018](../design/ADR-0018-fda-source-model.md)** (2026-08-24) — one ADR,
  not three: FDA `canonical_key`, eCFR/Federal Register document identity and guidance as non-binding
  text are one decision each about the same source model. Evidence in
  [spike-2026-08-24](../design/spike-2026-08-24-fda-source-recon.md). See *Deviations & decisions* 1
- **Depends on:** Phase 1 Go — see *Prerequisites*, which gate **starting** and are not tasks
- **Service:** `regulation`, plus two changes in `assistant`

---

## Goal

Bring **both** FDA cells to the four per-cell trust gates. The regulations are the deliverable; the
thing actually under test is narrower and older than they are:

> **One pipeline, profiles as data.** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
> decision 3 says a `Clause` carries no domain column and a profile is keyed on the *shape* of the
> instrument, never on who wrote it. Phase 1.1 tested that across two domains of one legal system
> and it did not trigger. This slice is the first time it meets a **second legal system**, whose
> hierarchy, amendment mechanism, effective-date convention and language all differ.

Everything below exists either to serve that test or to keep it honest.

## Scope

**In:** both `fda_samd` and `fda_cosmetic` — connectors, the CFR parser profile, English-language
extraction, English retrieval, the first real `document_cells` M:N exercise, and golden sets for
both cells.

**Out:** Tier C scraping and multilingual normalization — they stay in
[phase2.0](phase2.0_tier_c_scale.md) because the FDA cells need neither. Every FDA source in
[import-source-map.md](../import-source-map.md) is Tier A/B and English. That is exactly why this
group goes first: it isolates *second authority* from *scraping* and *second language*, which the
undecomposed 2.0 fused into one eight-month block with no observation point before M8.

**Both cells, not `fda_samd` alone.** They share the FD&C Act, eCFR, the Federal Register, Warning
Letters and Import Alerts; splitting them pays the connector and profile cost twice and defers the
M:N case ([ADR-0002](../design/ADR-0002-canonical-regulation-model.md) — the FD&C Act is a Primary
Law in **both** FDA cells) that is the only reason `document_cells` exists.

## Prerequisites

These gate the start. None is work in this slice; each is a decision someone has to record.

- [x] **Phase 1 Go, or an amended dependency.** [phase2.0](phase2.0_tier_c_scale.md) says *Depends
      on: Phase 1 Go*, and [phase1.6](phase1.6_evaluation.md) currently reports four of six gates
      `미측정` with the recommendation `INCOMPLETE`. Starting anyway is defensible — the human and
      pilot halves are scheduling rather than engineering — but it has to be **written down as a
      change to the dependency**, with the reason. Starting quietly would be the third decision this
      project lost in silence, and the [plan README](README.md) decision table exists because of the
      first two.
      → **taken 2026-08-24: the dependency is amended, not waived.** 2.0a may start on the
      machine-measurable half; **Phase 1 Go is still required before an FDA cell is declared
      gated.** The [phase2.0](phase2.0_tier_c_scale.md) header carries the amended text and the
      reason. See *Deviations* 4.
- [x] **The EU SaMD spike: run it, or drop it.** Non-gated, scheduled W3→W12, and carried from
      [phase1.0](phase1.0_ingestion.md) to [phase1.6](phase1.6_evaluation.md) without being done.
      Its whole purpose was to meet a second authority cheaply *before* one was gated. If FDA goes
      first, that purpose is spent and the spike should be dropped on the record — not carried a
      third time.
      → **taken 2026-08-24: neither — the whole EU group moved to Phase 4.** `eu_samd` and
      `eu_cosmetic` leave [2.0b](phase2.0_tier_c_scale.md) for a new roadmap stage after M24, and the
      spike goes with them, never run. **Scope is still 8 cells**; only the timing changed. Nothing
      in 2.0a depends on it — this prerequisite existed so the spike would not be carried a fourth
      time, and it no longer can be.
- [ ] **An FDA-side reviewer.** IR locking and golden-set sign-off need an `ra` who reads 21 CFR.
      The MFDS golden sets are still unsigned ([phase1.6](phase1.6_evaluation.md)); adding two cells
      to an unstaffed review queue makes both worse.

## Tasks

### W0 — Source reconnaissance (blocking, before any connector)

Same shape as [spike-2026-07-29](../design/spike-2026-07-29-mfds-source-recon.md), and for the same
reason: that spike downgraded the canonicalization estimate, found the three HTTP-200 failure
signatures, and killed a guessed URL that turned out to be a different document.

**W0 is complete — 2026-08-24.** [spike-2026-08-24](../design/spike-2026-08-24-fda-source-recon.md),
Parts 1 and 2. Every row was answered by a live call; the connectors are no longer blocked on recon.
Two answers landed *after* [ADR-0018](../design/ADR-0018-fda-source-model.md) was accepted and became
its open questions 6 and 7 — see *Deviations* 7.

- [x] **Which surface carries body text, and which carries only signals.** The one-line task in the
      undecomposed 2.0 named openFDA and Regulations.gov and named neither eCFR nor govinfo, while
      [import-source-map.md](../import-source-map.md) lists both. openFDA is MAUDE, recalls and
      registration data — **not regulation text**. Settle this against the catalog before anything is
      seeded, and correct the catalog if the catalog is what is wrong
      → **eCFR carries the text; openFDA carries no regulation text at all.** Recorded in
      [ADR-0018](../design/ADR-0018-fda-source-model.md) *Alternatives rejected*
- [x] **eCFR** — confirm live: the point-in-time endpoint, the structure endpoint, the granularity at
      which a section can be fetched, and whether the response states an amendment date per section.
      Candidate host `ecfr.gov`; **every endpoint shape is unverified until a live call returns one**
      → all four confirmed. Point-in-time is honoured, a section is addressable with no ancestor
      context, and `versions/title-21.json` states `amendment_date` **per section** plus `removed`
      and `substantive`. **Future dates 404** — `up_to_date_as_of` is a hard ceiling
- [x] **Federal Register** — confirm live: query by agency and by affected CFR part, the
      effective-date field, and the publication-to-effect lag. Candidate host `federalregister.gov`
      → both queries confirmed. `effective_on` is structured and **nullable**; `cfr_references` is
      **Part-level only**. Lag sampled at 0 · 30 · null · 0 · 163 days, and 5 rules are on the books
      with a future effective date, one of them 2033-03-07
- [x] **govinfo** — the FD&C Act (USC) surface, and whether it versions in a way `document_versions`
      can carry
      → **yes, section-granular — but annually.** Packages are `USCODE-{year}-title21` (1,552 in all,
      901 granules in one title-21 year); a `LEAF` granule is a section. So package → `DocumentVersion`
      and `LEAF` → `Clause`. **The cadence is the problem**: the FD&C Act is the Primary Law of both
      cells and its only probed surface refreshes once a year, against a ≤24h gate — now
      [ADR-0018](../design/ADR-0018-fda-source-model.md) open question 7. `PLAW` not probed.
      `uscode.house.gov` timed out and is unverified as an alternative
- [x] **accessdata** — the Recognized Consensus Standards table: **column labels only**. Feeds
      `sources.params["columns"]`, and no standard text is fetched at any point
      ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 7)
      → **captured.** `results.cfm` is a POST form. Labels: Recognition Number · Date of Entry ·
      Standards Developing Organization · Standard Designation Number and Date · Standard Title ·
      Extent of Recognition · Specialty Task Group Area. `_match_column` matches **exactly**, so the
      shipped defaults miss `number` and drop every row — the seed row must carry a `columns` mapping,
      and with one **no new code is needed**. Two fields this surface cannot fill at all: `edition`
      (folded into the designation string) and `withdrawal_date` (absent). See *Deviations* 6
- [x] **Credentials and rate limits** per host — API key, anonymous quota, `User-Agent` policy,
      `Retry-After` behaviour. A key lives in settings and the template carries a placeholder
      ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 13)
      → **govinfo is the only host that needs a key.** `api.data.gov` returns
      `X-Ratelimit-Limit: 10` on `DEMO_KEY` — enough to probe, not to ingest 901 granules. eCFR,
      Federal Register and accessdata publish no limit and throttled nothing across ~30 probes, which
      bounds the polite rate from below and says nothing about the ceiling; `PoliteFetcher` is reused
      unchanged. **robots.txt was read for all three** and turned up a conflict with
      [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 4 — see *Deviations* 7
- [x] **The HTTP-200 failure signatures for each host.** The MFDS lesson generalizes: a connector
      checking transport status alone records a healthy observation for a fetch that returned nothing
      → **none found, and that is the finding.** FDA hosts fail honestly: two distinct self-describing
      404 bodies, a 302 on a guessed RSS path, and a connection timeout. Plus one flag to respect —
      `meta.import_in_progress` on `titles.json`
- [x] **What is the denominator for detection coverage in these cells?** `regulation.discover_sources`
      enumerates MFDS 행정규칙 by 소관부처 code; FDA has no equivalent list, so the ≥95% gate has no
      denominator until this is defined. Answer it here, or the gate is unmeasurable later
      → **it has a better one.** `structure/current/title-21.json` enumerates 275 Parts and 8,408
      Sections, and all 13 Parts named in the source map are present and unreserved.
      [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 10 defines the denominator
- [x] Findings land in `docs/design/spike-<date>-fda-source-recon.md`; confirmed facts move into
      [import-source-map.md](../import-source-map.md). **A source whose endpoint is unconfirmed is
      seeded with its schedule disabled** — the row exists, it just does not fire

### Decisions to close before the build (ADRs, not plan rows)

**All three closed by [ADR-0018](../design/ADR-0018-fda-source-model.md), 2026-08-24.**

- [x] **FDA `canonical_key`.** Closes [ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
      open question 3 for this authority. It must express a CFR citation, survive a section being
      redesignated, and give an appendix a derivable child key the way `…#별표N` does
      → decisions 1–3. A `Document` is a CFR **Part** and a Section is a `Clause`;
      `fda:cfr:21-820`, appendix child `…#appendix-B`, FD&C Act `fda:usc:21-9`. `DocType` gains
      `REGULATION`. The authority publishes the citation itself, so it is read, not derived
- [x] **eCFR and the Federal Register are two surfaces of one instrument — how is that modelled?**
      The structural difference from MFDS, and the hardest item in the slice. 국가법령정보 hands over
      the current full text *and* 시행일자 together. FDA splits them: the **eCFR** is a compiled
      current text (citation quality), while the amendment arrives as a **Federal Register final
      rule** that announces its own effective date and lands *before* the eCFR reflects it (detection
      latency). The ≤24h gate is therefore reachable only through the Federal Register, and citation
      accuracy only through the eCFR. The existing precedent is close — 현행 + 시행예정 are two
      connectors writing versions of the **same** Document
      ([ADR-0016](../design/ADR-0016-pending-effect-versions.md) decision 1). Decide whether that
      holds here, or whether a final rule is its own Document that a section's version cites
      → decisions 4–8. **The ADR-0016 shape holds, with a different version key.** The eCFR owns
      identity and the version spine — one version per distinct `issue_date` at which a section of the
      Part changed — and a final rule is **provenance on the version, not a Document**. The premise
      that the latency gate is *only* reachable through the Federal Register turned out to be wrong:
      the eCFR publishes its own section-level change history, so detection polls the eCFR and the
      Federal Register supplies `effective_on` and pending-effect awareness. **The real gap is the
      other way round** — there is no pending *text*, because the eCFR 404s past `up_to_date_as_of`
- [x] **Guidance is citable text and is not extracted.** FDA guidance is explicitly nonbinding, and
      the Guidance block is a large part of the SaMD cell. The English modal inventory has no
      `should` ([rules.py](../../services/regulation/app/extraction/rules.py)), so extraction over
      guidance yields zero IRs — the correct result, which reads as a coverage hole unless the
      exclusion is **stated at `doc_type` level with a reason**. Decide it as a rule; do not let it
      emerge as a number nobody can explain
      → decisions 9–10. Guidance **is** stored (`doc_type = GUIDANCE`) and citable, extraction skips
      it by `doc_type`, and every clause gets an excluded row carrying a new
      `ExclusionReason.NON_BINDING`. `should` stays out of `MODAL_INVENTORY`. The coverage denominator
      is defined over obligation-bearing `doc_type`s only, so guidance cannot read as a hole

### Connectors

- [ ] eCFR connector — section-granular fetch, point-in-time where the API offers it
- [ ] Federal Register connector — final rules by agency and affected CFR part, carrying the stated
      effective date in `meta` (it is a parse output, not a fetch output —
      [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5)
- [ ] govinfo connector for the FD&C Act, **ingested once** and claimed by both cells
- [ ] Recognized Consensus Standards through the **existing** `recognition_list` connector — the
      header→field mapping is already `sources.params["columns"]` configuration, so this should be a
      seed row and no new code. If it needs code, record that in *Deviations*: the connector was built
      against an FDA-shaped assumption ([phase1.0](phase1.0_ingestion.md) recon) and this is the first
      time that assumption is tested
- [ ] Safety surfaces — Warning Letters, Import Alerts, recalls, MAUDE — as change signals. A feed
      yields no clauses and that is not a gap
      ([parsing/__init__.py](../../services/regulation/app/parsing/__init__.py))
- [ ] Every new connector registered by key; a seed row cannot name one that does not exist
- [ ] Polite fetch, backoff and `redact_url` reused unchanged. **No credential in `sources`, logs or
      fixtures**
- [ ] ISO 13485:2016 stays a `StandardReference` even though 21 CFR 820 (QMSR) incorporates it by
      reference — cite the requirement, link the standard, store neither

### Parser profile — `cfr_structured`

- [ ] A **fourth** profile beside `law_structured`, `admrul_text` and `annex`. CFR nests
      Part → Subpart → Section → `(a)(1)(i)(A)`, which no existing profile segments
- [ ] `path_segments` for that hierarchy, and a `clause_path` that renders the way a US regulatory
      professional writes a citation — `21 CFR 820.30(a)`, not a transliteration of 조/항/호/목
- [x] `DocType` mapping decided and recorded: the enum's `LAW` / `DECREE` / `ENFORCEMENT_RULE` are the
      Korean statutory ladder ([constants.py](../../shared/regops_shared/constants.py)). Either map
      CFR onto existing values or add one — but the profile keys on the value, never on the cell
      → **added `DocType.REGULATION`**, migration
      [0007](../../shared/alembic/versions/0007_fda_source_model.py) (2026-08-24). `ENFORCEMENT_RULE`
      was rejected: it names a rung of the Korean ladder and a CFR Part has no 시행령 tier above it.
      The same migration adds `ExclusionReason.NON_BINDING` for the guidance rule (decision 9)
- [ ] CFR appendices and tables follow [ADR-0014](../design/ADR-0014-annex-row-granularity.md)
      unchanged — a table row is a `Clause` with its columns in `row_columns`, not embedded, served by
      exact match. **`annex_rows` still does not exist**
- [ ] `effective_date` from the Federal Register's stated date;
      [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) applies as written — unresolvable
      stays null with the raw phrase retained. The 부칙 parser
      ([parsing/dates.py](../../services/regulation/app/parsing/dates.py)) is neither reused nor extended
- [ ] **Falsifier.** If profile selection acquires a branch on authority or cell — anywhere —
      [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 3 has failed. Escalate; do
      not work around it. This is the check the slice exists to run

### Extraction — the English rule set

- [ ] `rule_set_for(domain, "en")` is **already implemented** — `shall` · `must` · `is required to` ·
      `may not`, with permissive `may` behind a negative lookahead, and `document_versions.language`
      already selects it. Verify it end to end rather than rebuilding it
- [ ] English counterparts for the triage heuristics that are Korean-only: delegation (`_DELEGATION`
      matches 대통령령/총리령 only), transitional segments (`부칙` — CFR has no direct equivalent, and
      "no equivalent" is an acceptable answer that must be recorded), and the `제N조(제목)` title regex.
      Definition and scope headings already carry English forms
- [ ] **A missing rule set must raise, never fall back.** `rule_set_for` already refuses an unknown
      language for exactly this reason: extracting an English document under a Korean inventory finds
      nothing and reports full coverage. Keep a test on that behaviour
- [ ] Review `TAXONOMY_CODES` for FDA fit. The SaMD codes (`design_control`, `risk`, `vnv`,
      `postmarket`) read as though drawn from 21 CFR 820 in the first place; registration, listing and
      MDR reporting need a home, or a recorded decision that `postmarket` is it
- [ ] Guidance excluded by the rule decided above — with an `ExclusionReason`, so it appears as
      examined-and-excluded rather than unexamined
- [ ] `IR_RULE_VERSION` bumped if the inventory or taxonomy moves. IRs extracted under two rule
      versions are not comparable, and a golden-set score is meaningful only per rule version

### Retrieval — an English corpus

- [ ] **CFR identifier boost.** [retrieval.py](../../services/assistant/app/retrieval.py) boosts
      `제N조` and `별표N` only; `21 CFR 892.2050` and `§ 820.30(a)(1)` are not recognised. Identifier
      lookup is one of the six golden-set axes, so this is a gate input, not a nicety
- [ ] **Per-language full-text configuration.** `FTS_CONFIG` is the global constant `simple`
      ([constants.py](../../shared/regops_shared/constants.py)) — correct for Korean, which has no
      Postgres stemmer, and wrong for English, where it indexes `requirement` and `requirements` as
      unrelated tokens. Make it a property of the version's language. **This can change what the
      lexical arm returns for the MFDS cells**, so it must be a no-op for `ko`, proven by re-running
      the MFDS golden sets before and after
- [ ] Embedding model unchanged — `nomic-embed-text`, 768-dim, fixed regardless of generation
      provider. If the English corpus argues for a different model, that is a separate decision with a
      full re-index behind it
- [ ] Passage assembly reviewed against CFR section length; `MAX_PASSAGE_CHARS` was tuned on
      별표-heavy Korean text

### Cross-cell — the M:N exercise

- [ ] FD&C Act ingested **once**, claimed by `fda_samd` and `fda_cosmetic` through `document_cells`
- [ ] Cell isolation extended to the shared document: a change event fans out to **every** claiming
      cell and no others — one of the five non-negotiable test cases
- [ ] Alert routing verified for a subscriber in one FDA cell when the shared act changes
- [ ] Refusal verified in the other direction: an `fda_cosmetic` question must not be answered from
      `fda_samd` clauses of the same act

### Evaluation

- [ ] Golden sets for both cells, six axes, same composition rules as the MFDS pair
- [ ] **The neighbour-cell pairing is a decision, not a default.** The harness hardcodes
      `GATED = {"mfds_samd": "mfds_cosmetic", …}`
      ([scripts/evaluation/cli.py](../../scripts/evaluation/cli.py)), where the neighbour supplies the
      "asked in the wrong cell" axis. For an FDA cell the cross-**domain** neighbour (`fda_cosmetic`)
      and the cross-**authority** neighbour (`mfds_samd`) are different failure modes, and answering a
      US question out of Korean law is the one that would actually hurt a customer. Pick deliberately
      and record why
- [ ] The gated-cell map moves out of the harness source into configuration — four cells is where a
      hardcoded dict stops being cheaper than the config
- [ ] RA sign-off on both sets before any score is reported as a gate measurement

## Acceptance criteria

Per cell, both cells, independently — the Phase 1 thresholds do not retire at M4:

- [ ] Detection coverage ≥ 95%, against a denominator defined in W0 rather than assumed
- [ ] Detection latency ≤ 24h
- [ ] Citation accuracy ≥ 90%
- [ ] Hallucination rate ≤ 2%

And the structural criteria the slice is really about:

- [ ] **No authority- or domain-conditional branch in profile selection, parsing, or the clause
      schema** — grep-able, and asserted by a test
- [ ] The FD&C Act exists as **one** `Document` with two `document_cells` rows, and its change events
      reach both cells and no third
- [ ] An English document is extracted under an English rule set, and a missing rule set **raises**
      rather than silently extracting nothing
- [ ] No Tier D body text — CI scan green with the Recognized Consensus Standards list live
- [ ] The MFDS golden sets score no worse after the full-text change than before it

## Risks & open questions

- ~~**Risk 1 — the eCFR/Federal Register split is the real unknown.**~~ **Retired 2026-08-24** by
  [ADR-0018](../design/ADR-0018-fda-source-model.md) decisions 4–8, on measured evidence. The split is
  real but it is not the risk it was priced as: the eCFR publishes its own section-level change
  history, so version identity, the latency gate and the citation tuple all rest on **one** surface
  rather than on a reconciliation between two. **What replaces it is smaller and sharper** — the
  eCFR↔Federal Register join is page-based and best-effort (`89 FR 7523` vs `89 FR 7496` for the same
  rule), so some versions will carry the compilation's `amendment_date` instead of the legally stated
  `effective_on`, and the two can differ by days.
- **Risk 1a (new) — there is no pending text, and redesignation lost its stated signal.** Two costs
  the ADR accepts and neither was on this list before. FDA announces amendments years ahead — one rule
  on the books is effective 2033-03-07 — and the eCFR 404s on any future date, so the clause store
  cannot show future text at all. And FDA states *removal* but not *movement*, so CFR redesignation
  falls to ADR-0002 decision 7's content-similarity fallback, which has never been the load-bearing
  path in a gated cell. Both need tests before either cell is gated.
- **Risk 2 — a second authority's parser profile is not a connector.** The undecomposed 2.0 priced six
  cells as six checkbox rows. `cfr_structured` is a phase-1.1-sized piece of work on its own, and
  pricing it as a connector is how the M8 checkpoint gets missed.
  **Confirmed 2026-08-24, and it is worse than assumed.** CFR paragraph designations `(a)(1)(i)(A)`
  arrive as **inline prose** inside `<P>`, where MFDS delivers 조/항/호/목 as separate fields with
  nothing to segment. The hierarchy is also non-uniform (Part 710 has sections and no subparts; the
  other twelve in scope have subparts and no direct sections), and there is a `subject_group` level
  with no Korean equivalent — 102 of them in title 21.
- **Risk 3 — review capacity, not code.** Two more cells means two more golden sets, IR locking in a
  legal system the current reviewer may not read, and a second `ra`. The MFDS sets are still unsigned.
- ~~**Open question — does the Guidance block belong in `documents` at all**~~ — **answered yes**,
  [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 9. The denominator problem it raised is
  solved by defining coverage over obligation-bearing `doc_type`s only (decision 10), so storing
  guidance no longer enlarges the number the gate is measured against.
- **Open question — CFR redesignation.** Sections get redesignated the way 조 get renumbered.
  Renumbering must never be delete+add; whether the existing diff stage recognises a CFR
  redesignation is unverified. **Sharpened 2026-08-24:** the eCFR `versions` endpoint does carry
  `removed` (27 of 72 rows for part 820), but no move field — so this is now Risk 1a, not an
  open question about whether a signal exists.
- **Open question (new) — how far does the eCFR lag the Federal Register?** One observation puts it at
  a day or two. The ≤24h gate depends on the distribution, not one sample; measure over a fortnight
  before fixing the poll interval ([ADR-0018](../design/ADR-0018-fda-source-model.md) open question 1).
- **Open question (new) — how is the guidance corpus enumerated?** No API, and no crawl was attempted.
  Decision 9 settles how guidance is *treated*, not how it is *found*.

## Deviations & decisions

1. **Three planned ADRs became one — [ADR-0018](../design/ADR-0018-fda-source-model.md), 2026-08-24.**
   The header line of this file committed to three: FDA `canonical_key`, eCFR/Federal Register
   document identity, and guidance as non-binding text. They turned out to be one decision each about
   the same source model, and the first two are not separable — `canonical_key` cannot be settled
   without first deciding whether a `Document` is a Part, a Section or a Federal Register rule. Split
   across three files, decisions 1–3 would have had to forward-reference decision 4 to be readable.
   Recorded here because the plan said three and the repo now has one.

2. **The W0 recon ran before the Prerequisites were closed, and it did not need them.**
   *Prerequisites* gate starting the build; probing public read-only endpoints and recording decisions
   is neither. *(Two of those three closed later the same day — Phase 1 Go by amendment, the EU
   spike by moving the whole EU group to Phase 4. Only the FDA-side `ra` still gates the
   connectors.)* Nothing in this change touches code.

3. **Two of the ADR's inputs contradict this file as written, and the file is what was wrong.**
   Both are corrected above rather than silently: the ≤24h gate is **not** "reachable only through the
   Federal Register" (the eCFR publishes section-level `amendment_date`), and the coverage denominator
   is **not** undefined (the structure endpoint enumerates it). Left uncorrected, the first would have
   built a connector against the wrong primary surface and the second would have deferred a
   measurable gate.

4. **Phase 2's dependency on Phase 1 Go is amended, not waived (2026-08-24).** Recorded because
   *Prerequisites* required it in writing rather than by whatever got built first.

   **What it licenses:** starting 2.0a — W0 recon, ADRs, connectors, `cfr_structured`, extraction,
   retrieval — on the machine-measurable half of Phase 1's gates. The four `미측정` gates need a
   person or a pilot, not engineering; the reviewer packet and pilot runbook exist and a reviewer is
   available ([1.6](phase1.6_evaluation.md)), so what remains is scheduling. None of 2.0a's build
   work becomes more correct by waiting on it.

   **What it does not license, and this is the load-bearing half:** declaring an FDA cell **gated**.
   The four per-cell trust gates in *Acceptance criteria* are untouched, and **Phase 1 Go must still
   be called before any Phase 2 cell is gated** — otherwise "amend the dependency" would quietly
   become "retire the gates", which is the failure mode the 1.6 harness refuses when it reports
   `미측정` instead of defaulting. That boundary was not stated in the instruction; it is the
   conservative reading, and it is written here so it can be corrected rather than assumed.

5. **The Recognized Consensus Standards row needs configuration, and two fields it cannot supply
   (2026-08-24).** The plan predicted "a seed row and no new code" and asked to be told if that was
   wrong. It is **half right**. `_match_column` matches a normalized header **exactly**, and the FDA
   labels are longer than the shipped defaults (`Standard Title` vs `title`, `Standards Developing
   Organization` vs `organization`), so with `DEFAULT_COLUMNS` the `number` lookup misses and
   `row_to_record` drops **every** row. That is what `sources.params["columns"]` is for, so the seed
   row carries a mapping and **no code changes** — the connector's FDA-shaped assumption
   ([phase1.0](phase1.0_ingestion.md) recon) holds on its first real test.

   What does **not** hold: `edition` has no column of its own (FDA folds it into
   `62304 Edition 1.1 2015-06 CONSOLIDATED VERSION`) and `withdrawal_date` is absent from the list
   view entirely. `standard_references` has both columns and this surface fills neither. Splitting the
   designation string is code; the withdrawal date needs the per-standard detail page, which was not
   probed. Neither blocks the seed row — they bound what it can populate.

6. **robots.txt disallows the endpoint ADR-0018 made the version spine (2026-08-24).**
   `ecfr.gov/robots.txt` carries `Disallow: /api/versioner/v1/full/` — the point-in-time body-text
   call — under `User-agent: *`. [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md)
   decision 9 makes politeness part of the contract, so this cannot be shrugged off, and it was found
   *after* the ADR was accepted. The comment above the rule reads *"Don't index developer tool
   links"*, which is an anti-indexing intent rather than an anti-API one, and the endpoint is
   documented for developers — but the rule states no exemption. **Not decided here**: it is
   [ADR-0018](../design/ADR-0018-fda-source-model.md) open question 6, and it must close before the
   eCFR connector fetches body text. Detection is unaffected — `versions/` is permitted — so the
   ≤24h gate does not depend on the answer. `accessdata` separately disallows its Excel export, so
   the standards list is read as HTML.

7. **The FD&C Act refreshes annually, and the gate does not care (2026-08-24).** govinfo publishes
   the USC as `USCODE-{year}-title21`, section-granular but one edition a year. The act is the
   Primary Law of *both* FDA cells. Nothing in ADR-0018 anticipated that its only probed surface
   moves yearly against a ≤24h detection gate; Public Laws (`PLAW`) are the likely announcement
   surface and were not probed. [ADR-0018](../design/ADR-0018-fda-source-model.md) open question 7.

8. **The `docs/reference/` FDA research was read as spike input, by explicit request (2026-08-24).**
   `CLAUDE.md` marks that directory do-not-consult, so this is a one-off exception and not a
   precedent. It earned its keep as a source-landscape sketch and failed as evidence — every citation
   in it carries a `utm_source=chatgpt.com` tag, and it missed the `versions` endpoint entirely while
   recommending an RSS feed that returns 302 with 0 bytes. Two of its four files
   (`fda-regops.md`, `samd-fda.md`) are the same document. **Nothing in ADR-0018 rests on it**; the
   spike's *Where the prior research was wrong* table is the audit.
