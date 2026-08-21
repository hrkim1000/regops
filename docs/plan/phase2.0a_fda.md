# Phase 2.0a — FDA cells (SaMD + Cosmetic)

- **Roadmap:** Phase 2 (M5–12) · **Status:** ⬜ planned
- **Slice of:** [phase2.0](phase2.0_tier_c_scale.md) — scope completion, decomposed by cell group
- **Governed by:** [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decisions 3 · 5, [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md), [ADR-0004](../design/ADR-0004-ir-extraction-and-domain-branching.md) decisions 1 · 3, [ADR-0012](../design/ADR-0012-annex-version-identity.md), [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md), [ADR-0014](../design/ADR-0014-annex-row-granularity.md), [ADR-0016](../design/ADR-0016-pending-effect-versions.md)
- **Decides here:** three ADRs — FDA `canonical_key`, eCFR/Federal Register document identity, guidance as non-binding text
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

- [ ] **Phase 1 Go, or an amended dependency.** [phase2.0](phase2.0_tier_c_scale.md) says *Depends
      on: Phase 1 Go*, and [phase1.6](phase1.6_evaluation.md) currently reports four of six gates
      `미측정` with the recommendation `INCOMPLETE`. Starting anyway is defensible — the human and
      pilot halves are scheduling rather than engineering — but it has to be **written down as a
      change to the dependency**, with the reason. Starting quietly would be the third decision this
      project lost in silence, and the [plan README](README.md) decision table exists because of the
      first two.
- [ ] **The EU SaMD spike: run it, or drop it.** Non-gated, scheduled W3→W12, and carried from
      [phase1.0](phase1.0_ingestion.md) to [phase1.6](phase1.6_evaluation.md) without being done.
      Its whole purpose was to meet a second authority cheaply *before* one was gated. If FDA goes
      first, that purpose is spent and the spike should be dropped on the record — not carried a
      third time.
- [ ] **An FDA-side reviewer.** IR locking and golden-set sign-off need an `ra` who reads 21 CFR.
      The MFDS golden sets are still unsigned ([phase1.6](phase1.6_evaluation.md)); adding two cells
      to an unstaffed review queue makes both worse.

## Tasks

### W0 — Source reconnaissance (blocking, before any connector)

Same shape as [spike-2026-07-29](../design/spike-2026-07-29-mfds-source-recon.md), and for the same
reason: that spike downgraded the canonicalization estimate, found the three HTTP-200 failure
signatures, and killed a guessed URL that turned out to be a different document.

- [ ] **Which surface carries body text, and which carries only signals.** The one-line task in the
      undecomposed 2.0 named openFDA and Regulations.gov and named neither eCFR nor govinfo, while
      [import-source-map.md](../import-source-map.md) lists both. openFDA is MAUDE, recalls and
      registration data — **not regulation text**. Settle this against the catalog before anything is
      seeded, and correct the catalog if the catalog is what is wrong
- [ ] **eCFR** — confirm live: the point-in-time endpoint, the structure endpoint, the granularity at
      which a section can be fetched, and whether the response states an amendment date per section.
      Candidate host `ecfr.gov`; **every endpoint shape is unverified until a live call returns one**
- [ ] **Federal Register** — confirm live: query by agency and by affected CFR part, the
      effective-date field, and the publication-to-effect lag. Candidate host `federalregister.gov`
- [ ] **govinfo** — the FD&C Act (USC) surface, and whether it versions in a way `document_versions`
      can carry
- [ ] **accessdata** — the Recognized Consensus Standards table: **column labels only**. Feeds
      `sources.params["columns"]`, and no standard text is fetched at any point
      ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 7)
- [ ] **Credentials and rate limits** per host — API key, anonymous quota, `User-Agent` policy,
      `Retry-After` behaviour. A key lives in settings and the template carries a placeholder
      ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 13)
- [ ] **The HTTP-200 failure signatures for each host.** The MFDS lesson generalizes: a connector
      checking transport status alone records a healthy observation for a fetch that returned nothing
- [ ] **What is the denominator for detection coverage in these cells?** `regulation.discover_sources`
      enumerates MFDS 행정규칙 by 소관부처 code; FDA has no equivalent list, so the ≥95% gate has no
      denominator until this is defined. Answer it here, or the gate is unmeasurable later
- [ ] Findings land in `docs/design/spike-<date>-fda-source-recon.md`; confirmed facts move into
      [import-source-map.md](../import-source-map.md). **A source whose endpoint is unconfirmed is
      seeded with its schedule disabled** — the row exists, it just does not fire

### Decisions to close before the build (ADRs, not plan rows)

- [ ] **FDA `canonical_key`.** Closes [ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
      open question 3 for this authority. It must express a CFR citation, survive a section being
      redesignated, and give an appendix a derivable child key the way `…#별표N` does
- [ ] **eCFR and the Federal Register are two surfaces of one instrument — how is that modelled?**
      The structural difference from MFDS, and the hardest item in the slice. 국가법령정보 hands over
      the current full text *and* 시행일자 together. FDA splits them: the **eCFR** is a compiled
      current text (citation quality), while the amendment arrives as a **Federal Register final
      rule** that announces its own effective date and lands *before* the eCFR reflects it (detection
      latency). The ≤24h gate is therefore reachable only through the Federal Register, and citation
      accuracy only through the eCFR. The existing precedent is close — 현행 + 시행예정 are two
      connectors writing versions of the **same** Document
      ([ADR-0016](../design/ADR-0016-pending-effect-versions.md) decision 1). Decide whether that
      holds here, or whether a final rule is its own Document that a section's version cites
- [ ] **Guidance is citable text and is not extracted.** FDA guidance is explicitly nonbinding, and
      the Guidance block is a large part of the SaMD cell. The English modal inventory has no
      `should` ([rules.py](../../services/regulation/app/extraction/rules.py)), so extraction over
      guidance yields zero IRs — the correct result, which reads as a coverage hole unless the
      exclusion is **stated at `doc_type` level with a reason**. Decide it as a rule; do not let it
      emerge as a number nobody can explain

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
- [ ] `DocType` mapping decided and recorded: the enum's `LAW` / `DECREE` / `ENFORCEMENT_RULE` are the
      Korean statutory ladder ([constants.py](../../shared/regops_shared/constants.py)). Either map
      CFR onto existing values or add one — but the profile keys on the value, never on the cell
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

- **Risk 1 — the eCFR/Federal Register split is the real unknown.** Every other item here is work;
  this one is a modelling decision that version identity, the latency gate and the citation tuple all
  rest on. That is why its ADR is a prerequisite rather than an outcome.
- **Risk 2 — a second authority's parser profile is not a connector.** The undecomposed 2.0 priced six
  cells as six checkbox rows. `cfr_structured` is a phase-1.1-sized piece of work on its own, and
  pricing it as a connector is how the M8 checkpoint gets missed.
- **Risk 3 — review capacity, not code.** Two more cells means two more golden sets, IR locking in a
  legal system the current reviewer may not read, and a second `ra`. The MFDS sets are still unsigned.
- **Open question — does the Guidance block belong in `documents` at all,** or only as metadata with a
  deep link? Storing nonbinding text that is never extracted still buys citable retrieval, which is
  probably worth it — but it is a decision, and it changes the corpus size the coverage denominator is
  measured against.
- **Open question — CFR redesignation.** Sections get redesignated the way 조 get renumbered.
  Renumbering must never be delete+add; whether the existing diff stage recognises a CFR
  redesignation is unverified.

## Deviations & decisions

_None yet._
