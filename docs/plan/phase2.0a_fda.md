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

**Out, added 2026-08-25: everything that lives on `fda.gov`** — the Recognized Consensus Standards
list (Tier D freshness) and the whole Guidance block. Not deferred on cost or priority: FDA's CDN
classifies our identified client as abuse, so both are unreachable and asking to be let back in is
a request with someone else's answer on the end of it (*Deviations* 20).

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

- [x] eCFR connector — section-granular fetch, point-in-time where the API offers it.
      **Unblocked 2026-08-24**: [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 11 settles
      the robots.txt question — documented API only, and **never** eCFR or Federal Register HTML
      → [`ecfr_part`](../../services/regulation/app/connectors/ecfr.py). Polls `versions/` for
      identity, then fetches the body **at the issue_date that endpoint stated** rather than at
      "today", so archived bytes are reproducible. 15 unit tests, one of which asserts the no-HTML
      rule against the recorded call list. Verified live end to end: 21,490 B → 61 clauses
- [x] Federal Register connector — final rules by agency and affected CFR part, carrying the stated
      effective date in `meta` (it is a parse output, not a fetch output —
      [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 5)
      → [`federal_register`](../../services/regulation/app/connectors/federal_register.py), one
      `FEED` per Part (`fda:fr:21-820` against `fda:cfr:21-820`, so the decision 5 join is structural
      rather than a search). 24 unit tests; 13 seed rows live. **But `meta` reaches nothing** — see
      *Deviations* 10. The rules themselves are archived and reproducible from WORM
- [x] govinfo connector for the FD&C Act, **ingested once** and claimed by both cells
      → unblocked **and** built 2026-08-25 →
      [`govinfo_uscode`](../../services/regulation/app/connectors/govinfo.py), with 10 unit tests.
      Verified live end to end: one 5.37 MB fetch of the chapter granule → `fda:usc:21-9`, version
      `USCODE-2024-title21`, **12,179 clauses**, claimed by `fda_samd` *and* `fda_cosmetic`. The key
      travels in `X-Api-Key`, never in a URL, and a test asserts that against the recorded call list.
      [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 12 settles the cadence — **annual
      text** from `USCODE-{year}-title21`, one version per package. A mid-year amendment is not in
      the text until the next edition and **no version is synthesised to pretend otherwise**. `PLAW`
      is the announcement surface and is *not* built here, so the statute does not meet the ≤24h
      gate; decision 12 states that rather than blending a yearly source into a cell-level daily
      figure. The seed row carries a **weekly** interval override saying exactly that
- [ ] Recognized Consensus Standards through the **existing** `recognition_list` connector — the
      header→field mapping is already `sources.params["columns"]` configuration, so this should be a
      seed row and no new code. If it needs code, record that in *Deviations*: the connector was built
      against an FDA-shaped assumption ([phase1.0](phase1.0_ingestion.md) recon) and this is the first
      time that assumption is tested
      → **deferred out of this slice 2026-08-25 — the work is done, the access is not.** The
      connector, the column mapping and six seed rows all exist and are verified correct against the
      live page; the rows ship **disabled** and the source returns when FDA answers (*Deviations* 20).
      What was learned building it:
      **it needed code, and the code turned out to be "read HTML properly" (2026-08-25).** The
      three gaps were real — no `<th>`, chrome rows parsing as data, continuation rows misaligned —
      but each has a **standard attribute** behind it: `scope="col"` marks the header, `rowspan`
      says the continuation carries the row above, `colspan` spanning the width marks a banner.
      Honouring all three is authority-neutral and is a no-op for MFDS, which uses `<th>` and none
      of them. Six seed rows written, records verified correct against the live page — and **all six
      seeded disabled**, because FDA's CDN refuses our agent. See *Deviations* 16 and 17
- [x] Safety surfaces — Warning Letters, Import Alerts, recalls, MAUDE — as change signals. A feed
      yields no clauses and that is not a gap
      ([parsing/__init__.py](../../services/regulation/app/parsing/__init__.py))
      → **probed 2026-08-26, and three of the four are reachable.** Nothing built; this is the
      reconnaissance the row needed before anyone priced it. `api.fda.gov` — a **different host**
      from the two that refuse us — answers 200 on `device/recall.json`, `device/event.json`
      (MAUDE), `device/enforcement.json` and `device/classification.json`. **Warning Letters** on
      `www.fda.gov` answers 200 and is **server-rendered** (11 table rows in the HTML), so it is
      enumerable without a browser. **Import Alerts** is the one that stays out —
      `accessdata.fda.gov` redirects to Akamai's `abuse-detection-apology.html`. See *Deviations* 36
      → **moved out of this slice 2026-08-26, all four of them, to
      [phase2.3](phase2.3_product_registries.md).** Not deferred and not blocked — **re-homed**: a
      recall, an adverse-event report, a warning letter and an import alert are product- and
      firm-level fact, and this slice is the regulation corpus. Splitting the row would have left
      two plans claiming the same work, and would have split it by *publisher* rather than by what
      the thing is. See *Deviations* 39
- [x] Every new connector registered by key; a seed row cannot name one that does not exist
      → `ecfr_part` in `CONNECTOR_KEYS`, asserted by test. **13 seed rows landed 2026-08-24** — the
      Parts the source map names for both cells, all confirmed present and unreserved against the
      structure endpoint. Tier A, daily. Not seeded: the FD&C Act (needs
      [ADR-0018](../design/ADR-0018-fda-source-model.md) open question 7 settled) and the Federal
      Register (no connector yet)
- [x] Polite fetch, backoff and `redact_url` reused unchanged. **No credential in `sources`, logs or
      fixtures**
      → `PoliteFetcher` unchanged; the eCFR needs **no credential at all**, so there is nothing to
      redact on this source. govinfo is the one FDA host that will need a key
- [ ] ISO 13485:2016 stays a `StandardReference` even though 21 CFR 820 (QMSR) incorporates it by
      reference — cite the requirement, link the standard, store neither

### Parser profile — `cfr_structured`

- [x] A **fourth** profile beside `law_structured`, `admrul_text` and `annex`. CFR nests
      Part → Subpart → Section → `(a)(1)(i)(A)`, which no existing profile segments
      → `cfr_structured` ([cfr.py](../../services/regulation/app/parsing/cfr.py)), registered on
      `DocType.REGULATION`. 18 unit tests
- [x] `path_segments` for that hierarchy, and a `clause_path` that renders the way a US regulatory
      professional writes a citation — `21 CFR 820.30(a)`, not a transliteration of 조/항/호/목
      → stores `Subpart B/820.35/(a)/(1)`. **The rendered citation is composed, not stored**: MFDS
      stores `제7장/제43조/제1항` while a lawyer writes 화장품법 제43조제1항, and `21 CFR ` comes from
      the Document's `canonical_key` the same way. ADR-0018 decision 1 gave the rendered form as its
      example; this is the stored form of that address
- [x] `DocType` mapping decided and recorded: the enum's `LAW` / `DECREE` / `ENFORCEMENT_RULE` are the
      Korean statutory ladder ([constants.py](../../shared/regops_shared/constants.py)). Either map
      CFR onto existing values or add one — but the profile keys on the value, never on the cell
      → **added `DocType.REGULATION`**, migration
      [0007](../../shared/alembic/versions/0007_fda_source_model.py) (2026-08-24). `ENFORCEMENT_RULE`
      was rejected: it names a rung of the Korean ladder and a CFR Part has no 시행령 tier above it.
      The same migration adds `ExclusionReason.NON_BINDING` for the guidance rule (decision 9)
- [x] CFR appendices and tables follow [ADR-0014](../design/ADR-0014-annex-row-granularity.md)
      unchanged — a table row is a `Clause` with its columns in `row_columns`, not embedded, served by
      exact match. **`annex_rows` still does not exist**
      → **done 2026-08-26, and the row asked for more than title 21 contains.** Measured across all
      13 in-scope Parts: **no appendix at all**, and the tables are **HTML-shaped**
      (`TABLE`/`THEAD`/`TBODY`/`TR`/`TD`), not GPO `GPOTABLE`/`BOXHD`/`ROW`/`ENT` — three tables,
      17 rows, in 701.30, 820.10 and 822.19. They were being **silently dropped**: `_section` read
      only `<P>` children. Now a `TABLE` clause carrying the header plus one `TABLE_ROW` per row,
      hung off the paragraph the table follows. `assistant` needed no change — the
      not-embedded rule is keyed on `ClauseKind`, so the CFR rows inherit it; verified over Part 820
      (5 rows, 0 passage roots, no cell text in any passage). See *Deviations* 29
- [x] `effective_date` from the Federal Register's stated date;
      [ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md) applies as written — unresolvable
      stays null with the raw phrase retained. The 부칙 parser
      ([parsing/dates.py](../../services/regulation/app/parsing/dates.py)) is neither reused nor extended
- [x] **Falsifier.** If profile selection acquires a branch on authority or cell — anywhere —
      [ADR-0002](../design/ADR-0002-canonical-regulation-model.md) decision 3 has failed. Escalate; do
      not work around it. This is the check the slice exists to run
      → **not triggered.** `profile_for(doc_type)` takes one argument and the registry is keyed on
      `DocType`; a test asserts the signature so a later branch cannot be added quietly. Re-check when
      the connector and the extraction rules land — the profile was only the first place it could fire

### Parser profile — `usc_text`

Not planned when this slice was written: the FD&C Act was expected to reuse a profile. It could not.

- [x] A **fifth** profile, registered on `DocType.CODIFIED_STATUTE`
      → [usc.py](../../services/regulation/app/parsing/usc.py). Reading the Act through
      `law_structured` fails at the envelope — a govinfo granule is HTML that is not well-formed XML
      — and `DocType.LAW` names 법률, a rung of the Korean ladder. See *Deviations* 22
- [x] The paragraph ladder shared with `cfr_structured`, **parameterized rather than copied**
      → [ladder.py](../../services/regulation/app/parsing/ladder.py). The two conventions differ on
      both axes: the CFR nests `(a)(1)(i)(A)` and continues `z → aa → ab`; the USC nests
      `(a)(1)(A)(i)(I)(aa)(AA)` and continues `z → aa → bb`. Both differences were **measured**
      against 21 U.S.C. chapter 9, not taken from a drafting manual — spike Q11
- [x] Editorial notes excluded, and excluded **by position rather than by class name** — the chapter
      carries more apparatus than law (4,149 `note-body` against 2,061 `statutory-body`), and the
      one style used on both sides (`Q04`, 1,259 blocks) cannot be told apart any other way
- [x] `path_segments` `[subchapter, part, section, paragraph…]`, so `21 U.S.C. 351(a)(1)` stores as
      `Subchapter V/Part A/351/(a)/(1)` — the same shape `cfr_structured` uses, rendered at citation
      time. 20 unit tests
- [x] The 23 ambiguous clause paths (0.19% of 12,179) that remain. Each is logged and suffixed
      deterministically by `_disambiguate`; whether any is our mis-nesting rather than the source's
      own repeat is **not yet established** — see *Deviations* 24
      → **established 2026-08-26, and it was both.** **16 were ours** — a roman `(i)` nested three
      levels down is a perfect successor to subsection `(h)`, so the ladder read it as the section's
      ninth subsection and the real `(i)` then collided with it. **7 are the source's**, and the
      Office of the Law Revision Counsel says so in its own footnotes: *"So in original. Two
      subsecs. (z) have been enacted."* Fixed the 16 by using the depth the authority states
      (`subsection-head`) instead of inferring it; the 7 keep their `~2` suffix, which is what
      `_disambiguate` is for. 23 → 7, clause count unchanged at 12,179. See *Deviations* 30

### Extraction — the English rule set

- [x] `rule_set_for(domain, "en")` is **already implemented** — `shall` · `must` · `is required to` ·
      `may not`, with permissive `may` behind a negative lookahead, and `document_versions.language`
      already selects it. Verify it end to end rather than rebuilding it
      → **verified, not rebuilt.** Run over **2,039 real CFR clauses** (2026-08-25): 357
      obligation-bearing, every inventory modal firing — `must` 229, `shall` 116, `is required to`
      16, `may not` 13 — plus 194 permissive, 41 heading, 8 scope, 7 definition. Nothing needed
      writing; the advice to verify rather than rebuild was right
- [x] English counterparts for the triage heuristics that are Korean-only: delegation (`_DELEGATION`
      matches 대통령령/총리령 only), transitional segments (`부칙` — CFR has no direct equivalent, and
      "no equivalent" is an acceptable answer that must be recorded), and the `제N조(제목)` title regex.
      Definition and scope headings already carry English forms
      → **"no equivalent" for both, measured and recorded in
      [rules.py](../../services/regulation/app/extraction/rules.py).** Delegation: zero matches for
      every FDA form searched, and structurally so — 법령 delegates down to 시행령/시행규칙 while a
      CFR Part *is* the subordinate instrument. The 46 hits that look like it are **cross-references**
      ("in accordance with part 807"), and admitting them would exclude 39 clauses that do state
      obligations. Transitional: zero — effective dates live in the Federal Register rule, which
      ADR-0019 models as an announcement, not codified text. The `제N조(제목)` regex needs no English
      twin: the eCFR supplies `heading` separately. **One real defect found and fixed** — see
      *Deviations* 11
- [x] **A missing rule set must raise, never fall back.** `rule_set_for` already refuses an unknown
      language for exactly this reason: extracting an English document under a Korean inventory finds
      nothing and reports full coverage. Keep a test on that behaviour
      → test kept, and a second one added that demonstrates *why*: the same English sentence yields
      `("shall",)` under the English set and `()` under the Korean one — a silent zero, not an error
- [x] Review `TAXONOMY_CODES` for FDA fit. The SaMD codes (`design_control`, `risk`, `vnv`,
      `postmarket`) read as though drawn from 21 CFR 820 in the first place; registration, listing and
      MDR reporting need a home, or a recorded decision that `postmarket` is it
      → **the hunch was right and the gap was larger than it reads.** Part 820 supplies **21 of 341**
      obligation-bearing SaMD clauses, so the four codes described 6% of them. Added `registration`
      (807, 63), `classification` (892 + 860, 102) and `records` (11, 18); `postmarket` absorbs MDR,
      surveillance, corrections/removals and recalls (137) **by decision, recorded**. `IR_RULE_VERSION`
      → 1.3.0. See *Deviations* 13
- [x] Guidance excluded by the rule decided above — with an `ExclusionReason`, so it appears as
      examined-and-excluded rather than unexamined
      → **deferred with the Guidance block (2026-08-25).** The rule is decided
      ([ADR-0018](../design/ADR-0018-fda-source-model.md) decision 9) and `ExclusionReason.NON_BINDING`
      exists in the schema; there is simply no guidance document to apply it to while `fda.gov`
      refuses us. **Nothing in the coverage number moves**: decision 10 already defines the
      denominator over obligation-bearing `doc_type`s, so guidance was never in it
      → **closed as no-longer-applicable 2026-08-26 by
      [ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md).** Guidance does not
      enter `documents` at all, in any cell, so there is nothing to mark examined-and-excluded. The
      rule this row implements is now structural rather than procedural: extraction needs no
      `doc_type` skip because no nonbinding instrument is in the store.
      `ExclusionReason.NON_BINDING` stays in the enum, unused and documented as such. *(Also: the
      premise this row was deferred on was wrong — `fda.gov` was not refusing us, *Deviations* 36.)*
- [x] `IR_RULE_VERSION` bumped if the inventory or taxonomy moves. IRs extracted under two rule
      versions are not comparable, and a golden-set score is meaningful only per rule version
      → **1.2.0 → 1.3.0** with the taxonomy. The modal inventory did not move, so *whether* a clause
      bears an obligation is unchanged. The evaluation harness **records** the version rather than
      asserting it, so nothing broke — but the 2026-08-13 Go/No-Go report is stamped 1.2.0 and is
      now a valid record *of that version only*

### Retrieval — an English corpus

- [x] **CFR identifier boost.** `21 CFR 892.2050` and `§ 820.30(a)(1)` are now recognised
      → and the bug was worse than "not recognised": the extractor emitted `§ 892.2050` **with the
      sign**, a form nothing stores. Measured 2026-08-25 against the live corpus — `21 CFR
      892.2050` extracted *nothing*, `§ 820.30(a)(1)` extracted one identifier returning *zero*
      rows, while the bare `820.35` returned five. A unit test had locked the broken form in.
      Now: `21 CFR`, `21 U.S.C.` and bare `§` all normalise to the stored segment; `21 CFR Part 820`
      deliberately yields nothing, because a Part is the *Document*; and a compound address becomes
      a **path tail** matched against the end of `clause_path` together with its descendants —
      `820.35(a)` returns `(a)` and `(a)(1)`…`(a)(7)` and **not** `(b)`, where the loose-segment
      form would have put `(a)` into an array overlap matching every `(a)` in scope
- [x] **Per-language full-text configuration.** Now a property of the version's language
      → `fts_config_for()` plus migration `0010`, a second GIN index stemmed for English beside the
      `simple` one from 0005. The cost of not doing it, measured over the FDA corpus on 2026-08-25:
      `requirement` matched **258** clauses under `simple` and **2,009** under `english` (+679%),
      `label` 185 against 696, `manufacturer` 495 against 1,066. A hybrid retrieval whose lexical
      arm loses three quarters of its recall is a vector-only retrieval with extra steps.
      **The `ko` no-op is structural, not tested for**: the 0005 index and its `simple` query are
      untouched, so a Korean-only scope runs exactly the SQL it ran before and there is nothing for
      a before-and-after to detect. The lexical arm groups the versions in scope by language and
      runs once per group, because cross-cell mode can put both languages in one query and either
      single choice would read half the corpus with the wrong stemmer
- [ ] Embedding model unchanged — `nomic-embed-text`, 768-dim, fixed regardless of generation
      provider. If the English corpus argues for a different model, that is a separate decision with a
      full re-index behind it
      → **the model is unchanged and the index was never built (2026-08-26).** `clause_embeddings`
      holds 7,640 rows and **0 of them are FDA**, so retrieval in an FDA cell is lexical-only — the
      hybrid has one arm. Not a defect: embedding is explicit by design and nobody has run
      `assistant.embed_index` over these versions. Open, and it gates any claim about English
      retrieval quality. See *Deviations* 35
- [x] Passage assembly reviewed against CFR section length; `MAX_PASSAGE_CHARS` was tuned on
      별표-heavy Korean text
      → **reviewed, measured, and left alone.** The worry does not bite: English clauses sit more
      comfortably under the 1,200-character cap than Korean ones do. Raw clauses — `en` median 153,
      p95 612, max 5,827, **0.6%** over the cap; `ko` median 60, p95 312, max 272,172, **2.0%** over.
      Assembled passages — `en` mean 482, p95 1,152; `ko` mean 696, p95 1,196; **neither corpus
      produced a single passage over the cap**. Recorded because "no change" is only a finding if
      the numbers behind it are written down

### Cross-cell — the M:N exercise

- [x] FD&C Act ingested **once**, claimed by `fda_samd` and `fda_cosmetic` through `document_cells`
      → verified live 2026-08-25, and it **found a defect in the shared-document path** the MFDS
      cells had never exposed: the claim is written only where an artefact is applied, so a cell
      that lost the claim to a race could never regain it while the source answered 304. See
      *Deviations* 23
- [x] Cell isolation extended to the shared document: a change event fans out to **every** claiming
      cell and no others — one of the five non-negotiable test cases
      → [3 acceptance tests](../../services/regulation/tests/integration/test_phase2_0a_acceptance.py).
      Phase 1.1 already proved the *mechanism*, but against a fixture that hands both
      claims to one version — the gated MFDS pair share no regulation, so it had no real M:N case.
      These drive the claim through the **real path**: two sources in two cells, one
      `canonical_key`, one Document, one version, then an amendment producing exactly one event per
      (diff, claiming cell) and none for the other six cells. That path is where *Deviations* 23's
      defect lived, which is why it is the one under test
- [x] Alert routing verified for a subscriber in one FDA cell when the shared act changes
      → the phase 1.4 fan-out test is now **parameterized over both authorities**. Routing matches
      on `cell_id` with no authority-conditional branch, so an FDA copy of the MFDS test would be
      the same code path with different ids; parameterizing says exactly that, and the FDA case is
      the one where the shared document is real rather than synthetic
- [x] Refusal verified in the other direction — **but not as this row states it.** The criterion
      asked that an `fda_cosmetic` question not be answered from `fda_samd` clauses *of the same
      act*, and there is no such thing: the Act is one Document claimed by both cells, so its
      clauses belong to both, and refusing it would deny the cosmetic cell the statute governing it.
      The coherent test is a document the other cell claims **alone** — 21 CFR Part 892 is
      `fda_samd` only — and both halves are asserted together, because either alone is satisfiable
      by a scope that is wrong in the other direction. See *Deviations* 25

### Evaluation

- [ ] Golden sets for both cells, six axes, same composition rules as the MFDS pair
      → **the three generated axes are seeded (2026-08-26); the three hand-authored ones are not.**
      100 items per cell — identifier 40, mis_citation 30, cross_domain 30 — and `validate` reports
      `structurally valid: False` for exactly the right reason: `conceptual`, `effective_date` and
      `unanswerable` are 0, and a template cannot write them — the
      [seed](../../scripts/evaluation/seed.py) docstring says which and why. Those need a person,
      as they did for the MFDS pair. See *Deviations* 32
- [x] **The neighbour-cell pairing is a decision, not a default.** The harness hardcodes
      `GATED = {"mfds_samd": "mfds_cosmetic", …}`
      ([scripts/evaluation/cli.py](../../scripts/evaluation/cli.py)), where the neighbour supplies the
      "asked in the wrong cell" axis. For an FDA cell the cross-**domain** neighbour (`fda_cosmetic`)
      and the cross-**authority** neighbour (`mfds_samd`) are different failure modes, and answering a
      US question out of Korean law is the one that would actually hurt a customer. Pick deliberately
      and record why
      → **decided 2026-08-26: both, and the axis budget splits between them.** They fail
      differently, so choosing one leaves the other unmeasured. The reason travels in
      [cells.json](../eval/cells.json)'s own `note`, beside the value rather than only here
- [x] The gated-cell map moves out of the harness source into configuration — four cells is where a
      hardcoded dict stops being cheaper than the config
      → [docs/eval/cells.json](../eval/cells.json) + [cells.py](../../scripts/evaluation/cells.py).
      **No fallback map in the source**, deliberately: a default would be the hardcoded dict one
      import away, and it is what would run the day the file was mis-mounted. **The gated pair does
      not move** — both MFDS sets rebuild byte-identical, 162 items each. See *Deviations* 31
- [ ] RA sign-off on both sets before any score is reported as a gate measurement

## Acceptance criteria

Per cell, both cells, independently — the Phase 1 thresholds do not retire at M4:

- [ ] Detection coverage ≥ 95%, against a denominator defined in W0 rather than assumed
- [ ] Detection latency ≤ 24h
- [ ] Citation accuracy ≥ 90%
- [ ] Hallucination rate ≤ 2%

And the structural criteria the slice is really about:

- [x] **No authority- or domain-conditional branch in profile selection, parsing, or the clause
      schema** — grep-able, and asserted by a test
      → **met, and re-checked after every profile landed (2026-08-26).** Selection is `_BY_DOC_TYPE`
      keyed on `DocType` alone across all five profiles, and
      `test_profile_selection_has_no_authority_or_cell_input` asserts
      `signature(profile_for) == ["doc_type"]` so a later argument cannot be added quietly. Grepped:
      **no conditional on authority or cell anywhere in `app/parsing/`** — every match for those
      words is docstring prose. `Clause` carries no domain or authority column
      (`authority_changed` is *whether the authority stated a move*, not which authority).
      The two places it could have fired and did not are recorded: `usc_text` needed a fifth profile
      and got one on `doc_type` (*Deviations* 22), and `cfr_structured` shares its paragraph ladder
      with it by parameterization rather than a branch
- [x] The FD&C Act exists as **one** `Document` with two `document_cells` rows, and its change
      events reach both cells and no third
      → **met, live and in test (2026-08-26).** In the store: `fda:usc:21-9` is **1 document with 2
      claiming cells**, `fda_samd` and `fda_cosmetic`. Both halves are covered by
      the 2.0a acceptance suite —
      `test_two_cells_two_sources_one_document` for the shape,
      `test_an_amendment_to_the_shared_act_fans_out_to_both_fda_cells_and_no_others` for fan-out.
      The claim path is what actually broke here and is regression-tested too (*Deviations* 23)
- [x] An English document is extracted under an English rule set, and a missing rule set **raises**
      rather than silently extracting nothing
      → **met (2026-08-26).** `extract` selects `rule_set_for(domain, version.language)`, so the
      language comes off the version rather than a caller's guess. Exercised for real: Part 700 is
      an `en` version whose run produced 21 IRs on English modals, and the inventory was verified
      over 2,039 CFR clauses (*Deviations* 13). The refusal is unit-tested: `rule_set_for(SAMD,
      "fr")` raises `ValueError("No modal inventory")` rather than returning an empty set, which
      would have extracted nothing and reported full coverage
- [x] No Tier D body text — CI scan green. **Amended 2026-08-25**: this read "…with the Recognized
      Consensus Standards list **live**", and that cannot be met while `accessdata.fda.gov` refuses
      us. The scan still runs and is still green; what it no longer proves is that the rule holds
      with a live Tier D source attached. That proof moves with the source (*Deviations* 20), and
      saying so is the point — a criterion quietly reworded to be passable is worse than one that
      names what it stopped covering
      → **checked as amended, not as originally written (2026-08-26).** `tier_d_scan.py` is green
      over 433 files and runs in CI. What that proves is the rule holds across everything ingested;
      what it still does not prove is that it holds with a live Tier D source attached, and that
      half moves with the access request
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
  → **tested 2026-08-26** — seven integration tests against the real parse and diff stages, in
  [test_risk_1a.py](../../services/regulation/tests/integration/test_risk_1a.py).
  The pending half held as written: a future-effective rule lands as an announcement linked to its
  Part, creates no `DocumentVersion`, moves no in-force text, and no FDA version carries a future
  `effective_date`. The redesignation half did **not** — writing the tests turned up a mitigation
  that had never been connected, and a second one that does not reach this authority. See
  *Deviations* 27 and 28.
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
  → **crawl attempted 2026-08-26, and the answer is "not on anything worth building on".** Three
  layers, and each closes a different door (*Deviations* 37). There **is no API**: openFDA's own
  endpoint catalogue lists 9 namespaces and 24 endpoints, and **none is guidance**. The index is
  reachable but only through undocumented Drupal plumbing that returns rendered HTML inside a JSON
  envelope. And the documents are HTML/PDF, which we have no extractor for. Still open — what is
  closed is the assumption that a documented route exists and nobody had looked.
- **Open question (new, 2026-08-26) — is a question in the "wrong" language answerable, and should
  it be?** Nothing branches on the question's language: the API takes no language and retrieval
  picks its stemmer from the *version's* language, so both are accepted and neither is handled.
  Measured live, the two directions fail differently and **both fail silently** (*Deviations* 35).
  Deciding this is not a retrieval tuning question — it is whether an FDA cell asked in Korean
  should say so, or return nothing and let the citation contract call it "needs verification".

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

9. **`recognition_list` needs code for FDA, and the seed row is blocked behind it (2026-08-24).**
   This row predicted "a seed row and no new code" and asked to be corrected if wrong. It is wrong,
   and the correction is worth more than the prediction was: the connector has **never been seeded
   anywhere** — no source row in `seed.py` names it — so this is its first real use, not its first
   FDA use. The MFDS Tier D row points its note at `mfds_samd.standards.recognition_list`, a source
   that does not exist.

   Measured by running `extract_table_rows` + `row_to_record` against the live page rather than by
   reading the HTML:

   - **No `<th>` in the document at all.** The header is a plain `<tr>` of `<td>`s, so extraction
     falls back to positional keys (`col0`…`col6`) and `_match_column` — which looks up header
     labels — matches nothing. `row_to_record` returns `None` for every row. **`sources.params["columns"]`
     cannot fix this**: it maps labels to fields, and there are no labels.
   - **Chrome rows parse as data.** The results-per-page control and the *New Search / Export to
     Excel* bar are `<tr>`s in the same table.
   - **Continuation rows do not align with the header.** One query returns two recognized standards;
     the second arrives with **3 cells instead of 7**, its leading columns omitted. Read positionally
     it would file `ANSI AAMI IEC` as *Date of Entry*.

   What the fix is *not*: an FDA branch in the connector. Header-row detection without `<th>`, chrome
   rejection and continuation carry-forward are all properties of *this table shape*, so they belong
   behind configuration or a shape-keyed rule, the same way parser profiles key on the shape of an
   instrument and never on who published it ([ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
   decision 3). If the fix acquires an `if authority == "fda"`, that is the same falsifier this slice
   exists to run.

   Two things this does **not** block: `edition` and `withdrawal_date` remain unfillable from this
   surface regardless (*Deviations* 5), and the GET/POST question is settled — `results.cfm` accepts
   GET with a query string and returns bytes identical to the POST, so `PoliteFetcher.get()` is
   enough and no new fetch path is needed.

10. **`FetchedArtifact.meta` is computed and then dropped — there is nowhere to put it
    (2026-08-24).** `document_versions` has no column for it: `version_label`, `language`,
    `content_hash`, `raw_object_key`, `published_at`, `effective_date`, `effective_date_phrase`,
    `parser_version` and nothing else. On the MFDS path that is fine, because `meta` is *consumed*
    at parse time to set `effective_date` and is not meant to survive.

    The Federal Register connector breaks that assumption. Its `meta` carries `pending_count`,
    `earliest_pending`, `latest_pending` and `truncated_of_total` — and a feed has **many** rules
    with **many** dates, so there is no single version-level date to fold them into. Today those
    values are computed on every fetch and reach nothing queryable.

    **Nothing is lost, and nothing is usable either.** The raw payload is in the WORM archive and
    round-trips: 32 rules recovered for Part 892, whose two newest are the same two amendments the
    eCFR `versions` endpoint reported. So the evidence is reproducible by reading the archive, and
    not by querying the database.

    This blocks the half of ADR-0018 decision 7 that matters — *knowing* which amendments are
    announced and not yet in force — and the decision 5 join, which needs per-rule `effective_on`
    beside the CFR version. Both want the same thing: somewhere structured for the rules to live.
    That is a schema decision, not a connector one, so it is recorded here rather than improvised.

    → **Resolved 2026-08-25 by [ADR-0019](../design/ADR-0019-announced-amendments.md)**, migration
    `0008`. `amendment_announcements` + `announcement_documents`, upserted on `(authority, ref)`.
    Both questions are SQL now: `fda:cfr:21-820`'s eCFR issue reads **2026-02-04** against the
    Federal Register's `effective_on` of **2026-02-02** for the two QMSR rules — the exact two-day
    difference decision 5 predicted, visible rather than argued. 150 announcements and 187 links
    across the 13 in-scope Parts; **no pending amendment in any of them**, which is now a measured
    answer instead of an absence of one. The generic `FetchedArtifact.meta` gap is **not** closed:
    this gave the Federal Register's records a home, it did not make `meta` durable.

11. **`_matches` compared substrings, so `scope` matched `endoscope` (2026-08-25).** Found while
    verifying the English triage, not by a failing test — nothing in the current corpus trips it,
    and that is exactly what makes it the dangerous kind. A clause wrongly excluded as *scope*
    never reaches the agent while coverage still counts it examined, so the obligation disappears
    and the number that would reveal it stays green.

    Fixed by matching on word boundaries **where the script has them**: an ASCII needle uses ``,
    a Korean needle keeps the substring path. `` is defined against ASCII word characters and
    matches nothing useful in Hangul, so applying it across the board would have stopped 정의 and
    목적 matching at all — the fix had to be script-aware rather than uniform.

    **Proven a no-op for the gated cells**, which is the condition this slice attaches to any
    shared-code change: triage re-run over all **33,472** MFDS clauses before and after gives
    byte-identical counts across all ten verdicts, and the FDA counts are unchanged too.

13. **The SaMD taxonomy grew from four codes to seven, and `IR_RULE_VERSION` moved with it
    (2026-08-25).** The plan asked for a review and offered two acceptable outcomes — add codes, or
    record that `postmarket` covers it. The measurement chose: 21 CFR 820 supplies **21 of 341**
    obligation-bearing SaMD clauses, so `design_control`/`risk`/`vnv` described **6%** of them and
    described nothing outside Part 820.

    Added `registration` (Part 807, 63 obligations), `classification` (892 and 860, 102) and
    `records` (Part 11, 18). `postmarket` absorbs MDR, surveillance, corrections/removals and
    recalls (137) — one idea, duties attaching after market entry. It does **not** absorb the other
    four: those are pre-market and market-entry duties, and filing them under `postmarket` would
    make the label false, which is worse than no label because a wrong one reads as information.

    **The cost is not hidden.** `Domain.SAMD` is shared with `mfds_samd`, so the wider taxonomy is
    available to Korean extraction too, and `IR_RULE_VERSION` is now 1.3.0 while every stored IR —
    the gated MFDS ones included — is stamped 1.2.0. phase1.6's golden-set scores stay valid *for
    1.2.0* and are not comparable with anything extracted from here on. Restoring comparability
    means re-extracting 25,729 clauses through the agent; that is a decision for whoever next needs
    the two sides compared, not a side effect to slip in here.

    **Cosmetic was not reviewed, and that is a gap rather than a verdict.** Only Part 700 is
    ingested — 701, 740 and 710 failed to fetch — so there is no FDA evidence to assess the cosmetic
    taxonomy against.

14. **A "defect" investigated and deliberately not fixed (2026-08-25).** Sampling the cosmetic
    corpus showed obligation-bearing clauses that are children of a *Definitions* section —
    `700.3(g)` and `700.3(n)`. The section is excluded as `DEFINITION`; its paragraphs are not,
    because a paragraph carries no `heading` of its own and triage judges each clause on its own
    text. That looked like a leak worth plugging by propagating the parent's role.

    **Measuring it stopped the fix.** 31 clauses sit under a `DEFINITION` or `SCOPE` parent and
    still reach the agent — 14 English, 17 Korean — and reading them shows the current behaviour is
    right. `21 CFR 820.1(a)` sits under a section titled **Scope** and is where the QMSR's central
    duty lives: *"…must establish and maintain a quality management system…"*. Propagating the
    parent would have discarded it.

    What remains is narrower and different in kind: `700.3(n)` reads *"…shall be applicable to such
    terms…"* — `shall` as a declarative rather than a duty, with no bearer. That is a modal-semantics
    case, and it is **the agent's to judge, not triage's**. Triage is deliberately over-inclusive
    for the same reason [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 11
    makes the discovery filter over-inclusive: something missed because the filter was clever is a
    coverage hole, and a clause the agent sees and rejects is on the record either way.

    Recorded because the fix was nearly made, and it would have removed a real obligation to tidy
    away a borderline one.

15. **Re-collecting the three failed Parts exposed the `/full/` endpoint's shape (2026-08-25).**
    701 and 740 came back on a spaced retry; 710 failed a second time on the same URL. The obvious
    reading — an old point-in-time date is expensive — was **wrong**: probing directly, `part=820`
    at a *recent* date was also returning 503 after 40 s, having succeeded an hour earlier.

    The endpoints separate cleanly. `titles.json` and `versions/` answered in **0.6 s** throughout,
    while `/full/` alternated between 503 (upstream "No server is available", after 25–40 s) and
    200. No `Retry-After`, no rate-limit header. So this is a heavy endpoint shedding load, not a
    block aimed at us — and 710 succeeded on a later attempt with no change but timing.

    **The architecture already accounts for it.** ADR-0018 decision 6 makes `versions/` the
    detection surface and `/full/` the thing fetched only when something changed; that split was
    argued from structure and turns out to match the operational reality — the cheap surface is the
    reliable one. Fail-closed behaved correctly throughout: four attempts, an observation recorded,
    a drift alert, and **no version written** from a 503.

16. **The `recognition_list` fix was HTML, not FDA (2026-08-25).** *Deviations* 9 scoped this as
    connector work and was right that configuration alone could not do it. It was wrong about the
    shape of the work. Reading the markup rather than the rendered text, each of the three gaps has
    a standard attribute behind it:

    - the header row is `<td>` throughout but **every cell carries `scope="col"`**, the attribute
      that makes a cell a column header;
    - the continuation row is a **`rowspan="2"`** on the four shared cells, so the row above is
      carried down rather than the short row being re-aligned by guesswork;
    - the *New Search / Export to Excel* bar is a **`colspan="7"`** banner, so skipping it needs no
      list of chrome phrases for someone to maintain.

    So the change is "parse an HTML table correctly", which is exactly the shape-keyed answer the
    constraint demanded — no `if authority == "fda"` anywhere. **Provably a no-op for MFDS**: those
    pages use `<th>` and contain no `rowspan`, `colspan` or `scope` at all, the three fixtures parse
    to identical rows, and the feed tests pass unchanged.

    One further fix the config forced: `_match_column` compared labels raw, and the FDA header
    renders `Date of<br>Entry`, arriving with a double space. Requiring `sources.params["columns"]`
    to reproduce the page's line breaks would break a column the day someone moved one, so labels
    are folded to single spaces at match time. Verified against the live page: two records, both
    recognition number `13-79`, differing in organization and designation — which is what the
    `rowspan` meant.

    Still unfillable, unchanged from *Deviations* 5: `edition` (folded into the designation string)
    and `withdrawal_date` (absent from the list view).

17. **FDA's CDN classifies our agent as abuse, so the six rows are seeded disabled (2026-08-25).**
    `accessdata.fda.gov` sits behind Akamai, which answers our identified client with a 302 to
    `/apology_objects/abuse-detection-apology.html` — a page that is itself 404, which is why the
    connector saw a bare `HTTP 404`. The parser and the column mapping are verified correct against
    the live page; only the fetch is refused.

    **A User-Agent that slips through was not looked for, and must not be.** That is evasion, and
    it is the behaviour [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 11 forbids on
    the other FDA hosts for exactly this reason. There is an irony worth recording: the string that
    trips it is our polite one, `RegOps-ImportAgent/0.1 (+https://github.com/…)` — the crawler
    self-identification convention is itself a bot signal.

    The rows exist and do not fire, which is this file's own rule for an endpoint we cannot reach.
    **Consequence to state plainly:** Tier D freshness for the FDA cell —
    [ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md) decision 7's "track the
    recognition list, never the standard" — has no working path today.

    The request is drafted and **not yet sent**: [docs/fda-request/](../fda-request/README.md),
    with the measurement behind every claim in it. The block turned out to be **FDA-wide** rather
    than one host — `www.fda.gov` redirects too, which is why the request names the general contact
    form: the page that would identify a CDRH technical contact cannot be read from here.

18. **The seeder could disable a schedule the catalog stopped, and could not (2026-08-25).**
    Found while disabling the six: `seed_sources` deliberately left `enabled` alone on update, so
    that re-seeding could not revive a source an operator had stopped. Sound, and asymmetric in the
    wrong direction — a row the catalog says must not fire kept firing, and the seed-level flag was
    inert.

    Now **the catalog may stop a schedule and may never start one.** Disabling is the safe
    direction and propagates; enabling is the one that would override a deliberate stop, and still
    does not.

20. **Tier D freshness and the whole Guidance block leave this slice (2026-08-25).** Decided after
    a question worth recording, because the reasoning behind it was wrong in a way that would have
    left the plan saying something false: *"if the FDA submission feature moves to the next tier,
    the access request is not needed"*.

    **It is not a submission question.** There is no submission work in this slice — the 제출 서류
    view is phase1.5, built from the MFDS clause tree, and FDA premarket submissions are not in
    scope here at all. What the block actually closes is two other things:

    - **`accessdata.fda.gov`** — the Recognized Consensus Standards list, which is how Tier D
      freshness is tracked ([ADR-0003](../design/ADR-0003-ingestion-and-change-detection.md)
      decision 7: watch the list, never the standard).
    - **`www.fda.gov`** — and this is the larger half. The entire Guidance block for `fda_samd`
      lives there: SaMD, AI/ML, Cybersecurity and Premarket Submission guidance. The block is
      FDA-wide, not one host.

    So deferring a submission feature would have changed nothing, and recording it that way would
    have left a false reason attached to a real decision.

    **What is actually deferred, and what it costs.** Both sources leave 2.0a's scope and return
    when FDA answers [the request](../fda-request/README.md). The costs, stated rather than
    absorbed:

    - The Tier D acceptance row could no longer be met as written and is **amended in place with
      its old text quoted**, not silently reworded to something passable.
    - The Guidance block is a large part of the SaMD cell and is simply absent. **The coverage
      number does not move** — [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 10 defines
      the denominator over obligation-bearing `doc_type`s, and guidance was never in it — so this
      shows up as a smaller corpus rather than as a gap, which is exactly why it needs saying here.
    - `ExclusionReason.NON_BINDING` and ADR-0018 decision 9 stay decided and unexercised.

    **What is not affected.** The four per-cell trust gates measure regulation text, which comes
    from the eCFR and the Federal Register — both working, neither on `fda.gov`. Nothing in the
    detection, citation or hallucination path depends on the blocked host.

    **The request is still worth sending** and is no longer blocking: it is drafted, unsent, and
    the six seed rows sit disabled behind it.

    > **Annotation, 2026-08-26 — half of this is wrong, and the decision still stands.** The
    > sentence *"The block is FDA-wide, not one host"* does not survive a probe. `www.fda.gov`
    > answers **200** with 48–77 KB of real content, including the guidance search page and the
    > Warning Letters index. Only **`accessdata.fda.gov`** refuses us, and it refuses specifically:
    > `AkamaiGHost` redirects to `/apology_objects/abuse-detection-apology.html`.
    >
    > What this changes and what it does not. The **Tier D freshness** deferral is unaffected — the
    > Recognized Consensus Standards list is on the blocked host. The **Guidance** deferral survives
    > for a *different reason than the one recorded here*: the corpus is reachable and the search
    > page is **JS-driven**, so there are no document links in the HTML to enumerate. That is the
    > open question *"how is the guidance corpus enumerated?"*, which was already open and is now
    > the only thing in the way.
    >
    > Recorded as an annotation rather than an edit: the decision was right, the reason given for
    > half of it was not, and a plan that quietly corrects its own reasoning teaches nobody.

21. **The `docs/reference/` FDA research was read as spike input, by explicit request (2026-08-24).**
   `CLAUDE.md` marks that directory do-not-consult, so this is a one-off exception and not a
   precedent. It earned its keep as a source-landscape sketch and failed as evidence — every citation
   in it carries a `utm_source=chatgpt.com` tag, and it missed the `versions` endpoint entirely while
   recommending an RSS feed that returns 302 with 0 bytes. Two of its four files
   (`fda-regops.md`, `samd-fda.md`) are the same document. **Nothing in ADR-0018 rests on it**; the
   spike's *Where the prior research was wrong* table is the audit.

22. **The FD&C Act needed a fifth parser profile and a new `doc_type` (2026-08-25).** The slice
    assumed the statute would reuse `law_structured`, because both are statutes. It cannot: a
    govinfo USCODE granule is HTML that fails `defusedxml` on its first character reference, while
    `law_structured` reads 조/항/호/목 as XML *elements*. They are different **envelopes**, which is
    what `doc_type` selects on ([ADR-0002](../design/ADR-0002-canonical-regulation-model.md)
    decision 3).

    So `DocType.CODIFIED_STATUTE` (migration `0009`) and `usc_text`, on exactly the precedent
    `DocType.REGULATION` set three days earlier: `LAW` names 법률, a rung of the Korean statutory
    ladder, and reusing it would assert a shape that is not there. The name says *codification*
    rather than *statute* on purpose — what is ingested is the Office of the Law Revision Counsel's
    annual compilation, not the enacted act, and `PLAW` (the enactment surface) is not built.

    **The falsifier did not fire.** Profile selection is still `_BY_DOC_TYPE` and still has no
    branch on authority or cell. `usc_text` and `cfr_structured` *share* their paragraph ladder
    through [ladder.py](../../services/regulation/app/parsing/ladder.py), which is reuse of a shape
    helper, not selection.

    The registry did grow one seam: a profile now declares `ACCEPTS_RAW`, because hoisting "parse
    the bytes as XML" into the registry had made XML-ness a property of every profile instead of the
    four that happen to want it. All five state their input form explicitly.

23. **A cell's claim on a shared document depended on HTTP cache state, and it should not have
    (2026-08-25).** Found by the M:N exercise, latent since phase 1.0 and invisible until now.

    `_claim_for_cell` runs inside `_apply_artifact`, which a 304 never reaches. Both FDA cells
    fetched the FD&C Act in the same second; one committed the document and its claim, the other
    lost its claim to the race and thereafter answered 304. The USC is republished **annually**
    against a weekly poll, so `fda_samd` would have shown no claim on its own governing statute for
    a year — and that cell's coverage denominator would have been wrong the whole time, silently.

    Fixed with `_reclaim_from_history` on the 304 path. **The link is the content hash, not the
    version this source wrote**: on a shared document only the race winner writes a version, so
    "versions created by my observations" is empty for exactly the cell that lost the claim. What
    the loser does have is an observation recording the hash of the bytes it saw. Reproduced, fixed
    and verified live, and locked in by an integration test that replays the incident.

    The MFDS cells never exposed this because their shared sources are RSS boards whose content
    changes constantly, so a lost claim was re-won on the next changed fetch. An annually
    republished statute has no next changed fetch.

24. **Compound designators changed the CFR too, and the residual is recorded rather than rounded
    off (2026-08-25).** `(3)(A) Except as provided…` opens two levels, not one. Teaching the shared
    ladder that fixed the USC — and re-parsed 21 CFR Part 740 to **41 clauses against the 39
    stored**, because two compound heads now open the level they always stated. That is a
    correction, not a regression, but it means stored CFR clause counts move on the next parse and
    the four Parts that could not be re-checked (503 under burst) are unmeasured.

    23 ambiguous clause paths remain in the Act, 0.19% of 12,179. `_disambiguate` logs each and
    suffixes it deterministically, which is what that mechanism is for — but it was built for *the
    source's* ambiguous numbering, and whether these 23 are that or our own mis-nesting has not been
    established. Recorded as an open row rather than described as clean.

25. **One cross-cell criterion did not survive contact with the M:N case (2026-08-25).** The row
    *"an `fda_cosmetic` question must not be answered from `fda_samd` clauses of the same act"* was
    written before the Act was ingested, and it rests on a misreading of what sharing a document
    means. `document_cells` is M:N over **documents**, not over clauses: one Document, two claims,
    and every clause reachable from both. There is no `fda_samd` subset of the FD&C Act to refuse,
    and a scope that refused it would deny the cosmetic cell the statute it is governed by — MoCRA
    sits inside that same Act.

    Rewritten to the case that is real: a document claimed by the *other cell alone* — 21 CFR Part
    892, Radiology Devices — must not be reachable from a cosmetic question. Asserted together with
    its positive half, because a scope returning nothing passes the negative test and a scope
    returning everything passes the positive one; only the pair pins it. Measured at
    `versions_in_scope`, which is where ADR-0006 decision 9's bound is actually enforced, so no
    model is involved.

26. **The Korean compound identifier over-matches, and is deliberately left alone (2026-08-25).**
    Found while fixing the English side. `제8조제1항` extracts two *loose* identifiers, and
    `path_segments &&` is an overlap, so it matches 제1항 of **every** article in scope rather than
    the 제1항 of 제8조. The English fix — a path tail matched against the end of `clause_path` — is
    the same mechanism the Korean side would need.

    Not applied here, because it would change what retrieval returns for the two **gated** cells,
    and that is a change with a before-and-after over the MFDS golden sets behind it rather than a
    change to make in passing while building an English corpus. Recorded so the next person finds a
    measurement instead of rediscovering it: the fix is `extract_identifier_paths` extended to the
    Korean patterns, and the proof is the phase 1.6 golden sets re-scored either side of it.

27. **ADR-0018 decision 8's mitigation was computed and then dropped (2026-08-26).** The decision
    accepts a cost and names the thing that limits it in the same breath: *"the `removed` flag
    helps: it distinguishes 'the authority deleted this' from 'our differ lost it', which MFDS never
    had to."* It did not help, because nothing read it. `ecfr.py` wrote `removed_sections` into
    `FetchedArtifact.meta`, meta reaches nothing durable (*Deviations* 10), and the only consumer
    `grep` could find was one assertion in a connector test.

    That matters at the numbers involved. `RENUMBER_MATCH_RATIO` is **0.60** and CFR prose is
    boilerplate — *"Each manufacturer shall maintain records of … including the name of the device,
    the date …"* opens both a complaint-records section and a servicing one. A section the authority
    **deleted** need only resemble some survivor by 60% to be absorbed as a renumber, and a deletion
    reported as a renumber is an alert the subscriber never receives. Measured on the fixture: 0.69.

    **The fix raises the bar; it does not close the door**, and that distinction is the design.
    FDA writes a redesignation as *"§ 820.25 removed"* plus *"§ 820.35 added"*, so the sections
    carrying a stated removal are exactly the ones most likely to be renumbers — vetoing them would
    manufacture the delete+add that ADR-0002 decision 7 exists to prevent. So a stated-removed
    clause must clear `RENUMBER_CONFIDENT_RATIO` (0.90) instead of 0.60, and whatever it pairs to
    is flagged `needs_review` however high the score, because we contradict the authority about what
    happened to a provision. Below that bar it stays unpaired and is a `REMOVED` — which is what the
    authority said. Byte-identical text is exempt: that arm infers nothing.

    Migration `0011` — `document_versions.authority_removed_paths` (`jsonb`), and
    `clause_diffs.match_basis` widened 16 → 32 for the new basis value `similarity_contested`. A
    **named column rather than a generic `meta` blob**, on the ADR-0019 precedent: the generic
    connector-meta gap stays open and stays recorded rather than being widened into a place to put
    anything. Null and empty are kept apart on the way in — null is *"this source has no removal
    signal"*, empty is *"it reported and removed nothing"* — so silence can never read as a report.

    **Nothing on the MFDS path moves.** law.go.kr states 조문이동이전 / 조문이동이후, so a Korean
    renumber is resolved by `_authority_renumbers` and never reaches this fallback; a source that
    states no removal keeps the 0.60 floor it always had, and a test pins that half too. No new ADR:
    decision 8 already decided this behaviour, and this is its implementation.

    Found on the way: `amendment_announcements` and `announcement_documents` are listed under
    `regulation` in CLAUDE.md § Table ownership but were never re-exported from `app/models.py`.
    Added, rather than importing around the boundary.

28. **The CFR embeds its section number in the clause text, and the existing remedy is Korean-only
    (2026-08-26).** Found by a test that asserted the wrong thing and was right to fail. A pure
    redesignation with an unchanged body does **not** hit the free exact-hash arm, because a section
    clause's text opens `§ 820.35 Records.` — so the hash moves with the number.

    This is the 조문내용 phenomenon exactly, and phase 1.1 already solved it: `_same_but_for_its_number`
    strips the leading article number before comparing. But it strips it with `^제\d+조(?:의\d+)?`,
    and it is called from `_authority_renumbers` — a Korean regex on a path this authority never
    reaches. So FDA has no equivalent at all.

    **Consequence, stated rather than absorbed:** every CFR redesignation lands on the similarity
    arm, and over a stated removal every one is `needs_review`. Correct, and not free — the QMSR
    issue flagged 27 removed sections in Part 820 alone, so one Part rewrite could put 27 items in a
    review queue that has no FDA-side `ra` behind it (*Prerequisites*).

    **Not fixed in passing, deliberately.** The fix is to key the strip on the clause's own
    `path_segments[-1]` rather than on a numbering convention, which is authority-neutral and would
    serve both — but `_same_but_for_its_number` is on the **gated** MFDS pair's path, and changing
    what those cells diff needs a before-and-after over the phase 1.6 golden sets, not an edit made
    while writing a test for something else. That is the same refusal as *Deviations* 26, for the
    same reason. Recorded so the next person finds a measurement instead of rediscovering it.

29. **The CFR carries no appendices and no GPO tables, and its tables were being dropped
    (2026-08-26).** The row above assumed the MFDS shape would recur. Measured over all 13 in-scope
    Parts before writing anything:

    - **Zero appendices.** `cfr_structured` already treats `APPENDIX` as a container level, and
      nothing in title 21's in-scope Parts exercises it. That half of the row is satisfied by having
      nothing to do, which is worth recording so nobody looks for the missing work later.
    - **Zero `GPOTABLE`.** The eCFR serves HTML tables — `TABLE` / `THEAD` / `TBODY` / `TR` / `TD` /
      `TH` — while carrying `class="gpo_table"`, which is the trap: the class name says GPO and the
      markup is not. Three tables, 17 rows, in 701.30, 820.10 and 822.19.
    - **They reached the store as nothing.** `_section` collected `[child for child in node if
      child.tag == "P"]`, and a table sits inside a `<DIV class="gpotbl_div">` wrapper. So the
      obligation in 21 CFR 820.10's exemption table — five device types exempt from a QMS
      requirement — was not in the clause store at all, and no citation could resolve to it.

    **ADR-0014 is unchanged and now shared rather than described as shared.** `_table` moved out of
    `annex.py` into `tables.py` as `table_clauses`, parameterized on the segment labels — `표1`/`행3`
    for a 별표, `Table 1`/`Row 3` for a CFR section. The structure is one implementation; only the
    naming belongs to the instrument, which is the same split
    [ladder.py](../../services/regulation/app/parsing/ladder.py) already makes and the same reuse
    *Deviations* 22 recorded. The MFDS tests pass unchanged.

    **A table hangs off the paragraph it follows, and the authority checks our work.** 21 CFR 820.10
    puts its table between `(c)(2)` and `(d)` *and* captions it *"Table 1 to Paragraph (c)(2)"* — so
    position and caption agree, which is what licenses trusting position for the two tables that
    carry no caption. `segment_paragraphs` now returns the clause index each paragraph produced,
    because the mapping is not the identity: a compound run like `(3)(A)` emits two clauses from one
    paragraph.

    **Why extraction rather than flattening, stated because it is not obvious.** 21 CFR 822.19's
    first column *opens with paragraph designators* — `(a) Should result in…`, `(b) …`. Appended to
    the paragraph run those parse as designators, open two phantom levels under the section, and
    every later paragraph nests under them — including the section's real `(a)`. A test pins it.

    **Found and not fixed:** parsing 21 CFR Part 701 logs three `parse.duplicate_clause_path`
    warnings (`701.3/(a)`, `(b)`, `(c)`, occurrence 2). **Pre-existing** — reproduced on the parser
    as it stood before this change — so it is a separate defect in how that section restarts its
    designators, not a regression here. Recorded rather than folded in silently.

30. **The 23 ambiguous clause paths were two different things, and one of them was ours
    (2026-08-26).** *Deviations* 24 left this open rather than describing it as clean. Answering it
    needed the source, not the parser.

    **16 of 23 were our mis-nesting, and the cause is a genuine ambiguity.** The USC nests
    `(a)(1)(A)(i)(I)`, so `(i)` is both the **ninth subsection** and the **first roman numeral**.
    `depth_for` walks the open levels from the inside out looking for a successor — and after a
    subsection `(h)`, a roman `(i)` three levels down *is* a perfect successor to it. So the ladder
    closed three levels and filed the provision at subsection depth, where the section's real `(i)`
    later landed on the same path. Nine subsections were misplaced this way, in 335a, 343, 348,
    350a–1, 353, 355–1, 360, 360j, 360bbb–4, 379j, 379aa and 379aa–1.

    **7 are the source's own repeat, and the authority states it outright.** 21 U.S.C. 355 carries
    two subsections `(z)` and 353b carries two `(d)`, each flagged by an OLRC footnote reading *"So
    in original. Two subsecs. (z) have been enacted."* — the ` 6` marker in the clause text is
    that footnote reference. Their `~2` suffix is correct and stays: this is exactly the case
    `_disambiguate` was written for, and dropping the second would lose an obligation while the
    clause count still looked plausible.

    **The fix is the shape ADR-0002 decision 7 already argues for.**
    [usc.py](../../services/regulation/app/parsing/usc.py) treated *every* class as
    presentational — *"the suffix is matched and then ignored"*. True of `-Nem`, and it
    stays true: a compound run like `(h)(1)(A)` is indented at its **outermost** new
    level, so the indent does not state what the paragraph opens. It was never true of
    `subsection-head` / `paragraph-head` / `subparagraph-head` / `clause-head`, which are the OLRC
    **naming the level** — 1,444 blocks carry one. Those now supply the depth outright and the
    ladder is told; inference runs where nothing is stated, which is the same primary/fallback split
    as a stated 조문이동 beating a similarity guess.

    With the real subsections stated, the inference can safely prefer the deep reading for what is
    left: a token that is a successor at a shallower level **and** a well-formed first child of the
    innermost one now takes the child, because the shallow reading is the destructive one and a
    genuine subsection no longer relies on it.

    **Measured, not asserted.** `subsection-head` blocks placed at subsection depth: **904 → 912 of
    913**. Duplicate paths **23 → 7**. Clause count **12,179, unchanged** — 306 paths (2.5%) moved,
    nothing was lost or invented. **No citation broke: `ir_citations` pinned to this version is 0**,
    because the Act has not been extracted yet, so the re-addressing is free exactly now and would
    not have been later.

    **The gated cells cannot be reached by this.** `ladder.py` is imported only by `cfr.py` and
    `usc.py`; MFDS parses through `outline.py`. That is why this was fixable in passing and
    *Deviations* 26 and 28 were not — those sit on the gated pair's own path.

    One `subsection-head` is still misplaced (`350k/(a)/(1)`, filed a level deep) and is left as
    measured rather than rounded off.

31. **The gated-cell map was one dict doing two jobs, and the second only became visible at four
    cells (2026-08-26).** `GATED = {"mfds_samd": "mfds_cosmetic", …}` named *which cells the harness
    measures* **and** *which cell supplies each one's wrong-cell items*. With two cells each was the
    other's only option, so the two questions could not be told apart. They separate now.

    **`gated` is not "measurable".** The FDA cells are configured and **not gated**: Phase 1 Go is
    still required before any Phase 2 cell is declared gated (*Deviations* 4). So the `--cells`
    **choices** are all four and the **default stays the gated pair** — widening the default would
    have quietly changed what every documented command in CLAUDE.md measures. A Phase 2 cell is
    opted into by name until it is gated, at which point the default follows the file on its own.

    **The neighbour decision: both, budget split evenly.** The two are different failure modes and
    the row asked for a deliberate choice rather than a default:

    - **Cross-domain** (`fda_samd` ← `fda_cosmetic`): same authority, same language, and the two FDA
      cells already share Parts 7 and 11. Declining therefore requires respecting the **cell scope**
      rather than noticing a change of subject — the sharper test of the boundary itself.
    - **Cross-authority** (`fda_samd` ← `mfds_samd`): same subject, so retrieval finds topically
      similar in-scope clauses and can answer a Korean question out of US law — a confident wrong
      answer carrying the wrong jurisdiction's numbers — the one that would reach a customer.

    Picking either alone leaves the other unmeasured, so `neighbours` is a list and
    `generate_cross_domain` divides the axis target between them rather than doubling or halving it.
    A neighbour with no usable article is skipped rather than consuming its share.

    **The gated pair does not move, and it is measured rather than argued:** both MFDS sets rebuild
    **byte-identical** — 162 items, same ids, axes and questions — because a single neighbour takes
    the whole budget exactly as the scalar did. Same discipline as *Deviations* 26 and 28, and here
    it was cheap to honour rather than a reason to defer.

    **No fallback map in `cells.py`.** A default there would be the hardcoded dict again, one import
    away, and it would be what ran the day the file was mis-mounted — silently measuring a different
    set of cells than the operator believed. A missing file is an error naming where it looked.

    Validation refuses the one mistake that would not fail on its own: **a cell listing itself as a
    neighbour**. Those items expect `needs verification`, but answering them is correct in their own
    cell, so every one would score as a failure and the axis would report the opposite of what it
    measures. A missing golden set is now a sentence rather than a `FileNotFoundError`.

32. **The seeder was written against one corpus and had inherited its shape without saying so
    (2026-08-26).** Pointed at an FDA cell it did not fail — it produced **nothing**, because
    `corpus.articles` matched a 조-only pattern and no CFR path is a 조. Four things were Korean,
    and only one of them was the templates.

    The seam is **the version's `language`**, not the cell — the same one `rule_set_for(domain,
    language)` and the per-language full-text configuration already use. Keying on authority would
    have put a branch on who *wrote* the instrument, which is what the falsifier watches for. Two
    English cells share [phrasing.py](../../scripts/evaluation/phrasing.py); a third needs no
    change, and an unknown language **raises rather than falling back**, on `rule_set_for`'s
    precedent.

    What is per-language and not merely translated:

    - **The citable unit.** A CFR and a USC section are both path segments *beginning with a
      digit* — `820.35`, `351`, `350a–1`. Containers begin with a letter, paragraphs with `(`.
    - **A vacated provision.** 삭제 · `[Reserved]` · `Repealed.` · `Omitted` · `Transferred`,
      measured against the live corpus rather than guessed.
    - **A provably absent identifier.** `제{highest+11}조` counts upward; a CFR section must keep
      its Part, because `56` is not a section and `831.45` is a *different Part that exists* — which
      would turn a trap about a non-existent provision into a question about a real one.
    - **The heading.** A CFR heading repeats its own number (`§ 820.35 Control of records.`), so the
      identifier is stripped for display or the question says it twice.

    **Two defects surfaced that are not about language, and one is in a gated set.**

    - **The harness scoped more narrowly than the product.** `in_force_versions` took only versions
      whose effective date had arrived, while `assistant`'s `versions_in_scope` falls back to the
      nearest pending version and then to the most recently retrieved. Invisible while every MFDS
      version carried a 부칙 date; **9 of 13 CFR Parts and the FD&C Act state none**, because the
      Federal Register's `effective_on` still does not reach `document_versions` (*Deviations* 10).
      `fda_cosmetic` seeded **zero** identifier items against four Parts. The harness now uses
      `assistant`'s ladder — measuring a corpus the product does not answer from is a defect in
      the measurement, not a conservative choice.
    - **The cross-cell axis drew from documents the asking cell also claims.** `document_cells` is
      M:N over *documents*, so an item from the FD&C Act marked "declining is correct" scores a
      **correct** answer as a failure — *Deviations* 25, now enforced in the generator rather than
      left as a criterion. It was reaching 3 of `fda_samd`'s 30 cross items.

    **In the stored, gated `mfds_samd` set, 2 of 30 cross-cell items have this defect today**: they
    are drawn from 「인체적용제품의 위해성평가에 관한 규정」, which that cell also claims.
    The set is **not regenerated here** — it is a phase 1.6 gate input and the stored JSON is the
    source of truth, so correcting it is a change with a re-score behind it — *Deviations* 26 and
    28, again.
    Recorded with its size so the next person finds a measurement: up to 6.7 points of that cell's
    cross-domain axis is currently scored against itself.

    The seeder now also drifts from both stored MFDS sets for a second, benign reason — the wider
    in-force ladder makes more documents visible, which changes which ones feed each axis. Neither
    difference is applied.

33. **A review had two outcomes and only one was representable —
    [ADR-0020](../design/ADR-0020-ir-rejection.md), 2026-08-26.** Found by an operator mis-clicking
    확정 on an IR and having no way back, which turned out not to be a missing button.

    `POST /irs/{id}/lock` existed and nothing else did. `IRStatus` held `draft | locked | stale |
    superseded`, so there was **nowhere to record that an RA had refused a draft** and no way to
    undo a lock. ADR-0004 decision 4 describes the reviewer agreeing and is silent on the other
    half; the silence was load-bearing.

    A refusal left as `draft` is the same claim as *"nobody has looked at this"*, so it returns to
    the next reviewer's queue forever and the extraction agent's error rate has no denominator.
    That is ADR-0004 decision **6**'s own argument — examined-and-excluded must not read as
    unexamined — one level up, about the IR rather than the clause.

    Added: `IRStatus.REJECTED`, a `RejectionReason` enum with a required free-text note (the split
    `ExclusionReason` already makes — the count per reason is a signal about the *agent*, the
    particulars of one refusal are a human judgement), `POST /irs/{id}/reject`, and
    `POST /irs/{id}/unlock`. Migration `0012`. **`IR_VISIBLE_STATUSES` is unchanged at `(LOCKED,)`**
    — a rejected IR is inert exactly as a draft is, and the difference is that it is inert *and*
    accounted for. The review surface gained the two controls the model had been missing.

    **Unlock returns to `draft`, never straight to `rejected`.** *"This approval was a mistake"* and
    *"I have reviewed this and refuse it"* are different assertions; collapsing them would write a
    judgement nobody made — which is exactly what happened here.

    **The lock cleared from the row and not from the audit trail.** `audit_log` is append-only and
    hash-chained, so the `ir.locked` entry stays and `ir.unlocked` is appended beside it. The
    mis-clicked IR now reads `ir.locked` → `ir.unlocked` → `ir.rejected` across seq 84–86, and
    `verify_chain` passes over all 86 entries. Who approved it and who took that back are both
    answerable, and neither from the row alone.

    **What this does not fix, and the ADR says so.** Being able to record a refusal is not the same
    as not producing the draft: `§ 700.3 Definitions` is correctly excluded as `definition`, but the
    exclusion **does not descend to its paragraphs**, so `700.3(g)` and `700.3(n)` were classified
    obligation-bearing and extracted — 2 of Part 700's 16 obligation-bearing clauses and 2 of its 21
    drafts. Both are now `rejected` as `not_an_obligation`. The fix moves what the **gated** MFDS
    cells extract, because Korean 정의 조항 (제2조) have the same shape, so it carries a
    before-and-after over the phase 1.6 golden sets — *Deviations* 26, 28 and 32 again.

34. **The definitions exclusion now descends — and fixing it first uncovered why it was dangerous
    (2026-08-26).** Deferred three times (*Deviations* 26, 28, 32, 33) because it moves what the
    **gated** cells extract. Measured before shipping, and the measurement rewrote the change.

    **First attempt, and the number that stopped it.** Inheriting the role from the provision above
    moved 306 of `mfds_samd`'s 22,776 clauses, of which **17 left `obligation_bearing`** — and
    reading all 17 showed most were real duties: *"승인을 취소하여야 하고"*, *"승인을 얻어야
    한다"*, *"하여서는 아니 되며"*. The inheritance was not wrong; it was **amplifying a defect
    underneath it**.

    **The defect: the Korean role test was a substring match, and it was live.** `_matches` guarded
    the ASCII needles with `` — `scope` inside `endoscope` — and said so. Hangul has no ``, so
    the Korean needles fell through to plain containment:

    | heading | needle | matched as |
    | --- | --- | --- |
    | 지**정의** 취소 등 | 정의 | definition |
    | 적합성인**정의** 취소 등 | 정의 | definition |
    | 사용**목적** | 목적 | scope |
    | 전시 **목적** 의료기기의 진열 승인 등 | 목적 | scope |

    Every one is an obligation-bearing article that **never reached the agent while coverage counted
    it as examined** — the failure `_matches` was written to prevent, arriving through the door it
    left open. Two are excluded that way in the store today.

    Replaced with an **anchored** test: a heading must *be* the role. All four genuine forms in the
    corpus still match (정의 · 용어의 정의 · 목적 · 적용범위), a trailing 등 is allowed, and a CFR
    heading's own section number is stripped so `§ 700.3 Definitions.` still reads. Verified against
    all 15 real headings containing a needle, including a table header row `번호 | … | 정의`.

    **Combined effect on the gated pair, which is what the deferral was about:**

    | | obligation-bearing gained | lost |
    | --- | ---: | ---: |
    | `mfds_samd` | **+6** | **−2** |
    | `mfds_cosmetic` | **0** | **0** |

    Net **+4 on one cell and nothing on the other**, and the direction is *recovering* obligations
    the substring bug had been swallowing. The first attempt's 17 losses became 2 once the false
    parents were gone. **No locked IR is affected** — there is one in the store and its clause
    (`제4조 규제의 재검토`) stays obligation-bearing.

    Inheritance carries only `definition` and `scope`: both describe what the *provision* is, and a
    paragraph of a definitions article is still a definition. `permissive`, `delegation` and the
    rest describe the clause itself, and inheriting them would bury a duty a sub-clause carries
    on its own. Structure still wins — an empty stub inside a definitions article is `empty`.

    **The stored classifications are now behind the rules.** Re-extraction is per-version, LLM-bound
    and explicit by design (CLAUDE.md § Celery), so nothing re-runs automatically; the delta above
    is computed deterministically from the rules, which is why it could be measured without one.

35. **Both languages are accepted; only one of them retrieves. Recorded, not fixed (2026-08-26).**
    Raised as a question — *can a question be asked in English or Korean?* — and worth measuring
    rather than reasoning about, because the honest answer is "the interface takes both" and that is
    not the same as "both work".

    **Nothing branches on the question's language.** `POST /api/v1/queries` has no language
    parameter, and `_lexical_by_language` keys the stemmer on the **version's** language, not the
    asker's. So the question language selects nothing, anywhere.

    Measured live against the running stack:

    | question | corpus in scope | hits | what came back |
    | --- | --- | ---: | --- |
    | English | FDA (English) | 5 | on target — `820.35(a) Records of complaints`, `803.18(d)(1)` |
    | **Korean** | **FDA (English)** | **0** | lexical 0, vector 0 — nothing at all |
    | Korean | MFDS (Korean) | 5 | same-language path, unchanged |
    | English | MFDS (Korean) | 5 | 별지 서식 and a table of contents — worse than nothing |

    Two causes, and the second is the one worth recording:

    - **The lexical arm cannot cross languages by construction.** Korean tokens do not match English
      text. That is not a bug and no amount of tuning changes it.
    - **The FDA corpus has no embeddings.** `clause_embeddings` holds 7,640 rows, **0 of them FDA**,
      so an FDA cell has no vector arm at all — the hybrid is running on one leg. A Korean question
      there loses the only arm it could not use anyway, which is why it returns exactly zero.

    Embedding is deliberately not chained off parse (CLAUDE.md § Celery), so this is unrun work
    rather than a failure. It does mean **no claim about English retrieval quality is currently
    supported by anything**, including the FDA golden sets seeded in *Deviations* 32.

    **The asymmetry is the part that should not survive to a user.** Korean→FDA returns nothing, and
    the citation contract turns that into *"needs verification"* — which is correct and honest.
    English→MFDS returns *plausible-looking wrong evidence*, because `nomic-embed-text` emits enough
    cross-lingual signal to rank something (37 vector hits) and not enough to rank the right thing.
    An empty answer is a good failure; a confident one built on a 별지 form is the failure the
    evidence-verification pass exists to catch, and it should not be reaching that pass by design.

    Neither is in any row of this plan. Left as an open question above rather than fixed here,
    because "run the embeddings" and "decide what a language mismatch should do" are different
    decisions and only the first is mechanical.

36. **Three of the four safety surfaces are reachable, and the FDA block is one host rather than
    FDA-wide (2026-08-26).** A probe, not a build. The row had been carried since W0 with nobody
    having asked whether the surfaces answer at all.

    | surface | host | result |
    | --- | --- | --- |
    | Recalls | `api.fda.gov/device/recall.json` | **200** |
    | MAUDE | `api.fda.gov/device/event.json` | **200** |
    | Enforcement | `api.fda.gov/device/enforcement.json` | **200** |
    | Classification | `api.fda.gov/device/classification.json` | **200** |
    | Warning Letters | `www.fda.gov` | **200**, server-rendered, 11 table rows |
    | Import Alerts | `accessdata.fda.gov` | **refused** — Akamai `abuse-detection-apology.html` |
    | Guidance index | `www.fda.gov` | **200**, but JS-driven: no links in the HTML |

    Probed with our own identified `User-Agent` and a delay between requests — the same client the
    blocked host objects to, which is what makes the comparison mean anything.

    **openFDA is a *signal* source here and still not a regulation source.**
    [ADR-0018](../design/ADR-0018-fda-source-model.md) rejects it as the latter because it carries
    regulatory data and no regulation text. That rejection is untouched: a recall is a change signal
    about a product, and this row was always about signals — *"a feed yields no clauses and that is
    not a gap"*.

    **The correction matters more than the probe.** *Deviations* 20 recorded the block as
    *"FDA-wide, not one host"*, and built two deferrals on it. One of those reasons was wrong:
    `www.fda.gov` was never refusing us. The Guidance deferral survives on the enumeration problem
    instead, which was already an open question. Annotated at *Deviations* 20 rather than edited.

    Nothing is built and no seed row is added. What the row needs next is a decision about **what a
    safety signal is for** — an alert with no clause to cite is a different object from an amendment
    (ADR-0006's citation contract has nothing to bind it to), and that is worth settling before a
    connector exists rather than after.

37. **Guidance has no API, and the route that exists is not one to build on (2026-08-26).** The open
    question said *"no API, and no crawl was attempted"*. The crawl was attempted. Three layers, and
    the first is decisive.

    **There is no API.** openFDA's own catalogue (`api.fda.gov/download.json`, 590 KB) lists every
    endpoint it has — 9 namespaces, 24 endpoints, `device` holding `510k · classification ·
    covid19serology · enforcement · event · pma · recall · registrationlisting · udi`. **None is
    guidance**, and none is Warning Letters either. openFDA carries regulatory *data* about
    products, which is exactly what [ADR-0018](../design/ADR-0018-fda-source-model.md) rejected it
    for as a regulation source; it does not become a text source by being reachable.

    **The index is reachable and is internal plumbing.** The search page is a Drupal DataTables view
    and its settings name the backend outright — `view_name: fda_guidance_documents`,
    `view_base_path: datatables-json/search-for-guidance.json`. That path answers **200 with zero
    bytes** whatever parameters it is given. What answers is `POST /views/ajax`, and it returns a
    Drupal AJAX command envelope with **rendered HTML inside it** rather than data.
    So a connector would be parsing one CMS's internal response format, which changes without
    notice and without a version to pin. ADR-0018 decision 11 chose *documented API only, never
    HTML* for the other two hosts on the publisher's own instruction; there is no such instruction
    here, and no such API either.

    **The documents are HTML/PDF.** `/media/{n}/download`. Nothing in the pipeline extracts PDF, and
    decision 9 wants guidance stored as citable text — so the index is the smaller half of the
    problem even if it were clean.

    **One constraint found that outlives this question.** `www.fda.gov/robots.txt` does **not**
    disallow the guidance paths — it asks for **`Crawl-Delay: 30`**. Our
    `HOST_MIN_INTERVAL_SECONDS` is **1.0**, so any crawl of this host under the current fetcher
    would run 30× faster than the publisher asks. A per-host interval override is a prerequisite for
    touching `fda.gov` at all, and that is not abstract: the sibling host has already put us behind
    Akamai's abuse detection (*Deviations* 36).

    Nothing built. The question stays open; what is now closed is the possibility that a documented
    route was sitting there unlooked-at.

38. **Guidance leaves the regulation library —
    [ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md), 2026-08-26.**
    [ADR-0018](../design/ADR-0018-fda-source-model.md) decision 9 answered *"does the Guidance block
    belong in `documents` at all"* with yes. The storing half is reversed; the never-extracted half
    is kept and becomes structural.

    **Free to decide, because nothing was ever built.** Across all eight cells: **0** documents with
    `doc_type = guidance`, **0** source rows in the `guidance` block — not seeded anywhere — and
    **0** clauses carrying `ExclusionReason.NON_BINDING`. The gated MFDS pair reached Phase 1
    acceptance without a line of guidance in the store. This is declining to build, not removing
    something that works, and that is the cheapest such decision ever is.

    **The acquisition cost is not the argument, though it is what prompted the question.**
    *Deviations* 37 found no API, an index reachable only through Drupal internals, HTML/PDF
    documents and a 30× crawl-delay gap. Costs change. What does not: a guidance `Citation` carries
    no legal `effective_date`, and `versions_in_scope` **does not filter on `doc_type`** — so a
    fused answer could cite binding and nonbinding text in one list under one contract that promises
    clause-level evidence. A reader acting on nonbinding text as though it bound them is the worst
    mistake this domain offers, and the product would have handed it over with a citation attached.

    **Where guidance goes instead is deliberately not decided.** Three channels are recorded — a
    reference library outside the citation contract, link-only, or a change signal with no stored
    text — with what each buys, what it costs, and what evidence would settle it. The pilot is the
    instrument that distinguishes *"what does the guidance say"* from *"has the guidance changed"*,
    and it has not run. Picking now would repeat decision 9's mistake in the other direction.

    **This is not an FDA rule.** The `Guidance` block exists in the MFDS, EU and NMPA sections of
    the source map too, and the same reasoning covers them. The blocks stay in
    [import-source-map.md](../import-source-map.md): they are a true inventory of what exists, and
    deleting real sources to reflect a routing decision would make the single catalog lie.

39. **The safety surfaces are re-homed, not deferred (2026-08-26).** The row had carried Warning
    Letters, Import Alerts, recalls and MAUDE since W0, on the unexamined assumption that a change
    signal about a product belongs beside the regulations it concerns.

    It does not, and the reasoning is
    [ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md)'s one surface on:
    **this slice is the regulation corpus.** A recall is a fact about a product, an adverse-event
    report about an incident, a warning letter about a firm, an import alert about a shipment. None
    is regulation text and none has a clause to cite.

    All four go to [phase2.3](phase2.3_product_registries.md) together. **Splitting was the tempting
    wrong answer**: recalls and MAUDE are on openFDA and the other two are not, so a split would
    have divided the row by *publisher* — leaving 2.0a holding two surfaces for no reason but where
    FDA happens to serve them, and leaving two plans claiming the same work.

    Nothing is lost by the move and something is gained: 2.3 already has to answer *is a registry
    row citable at all*, which is the same question these four raise and which this slice had
    nowhere to put. What the probe found travels with them — three of four reachable,
    `Crawl-Delay: 30` on `www.fda.gov`, Import Alerts behind the same Akamai block as the
    Recognized Consensus Standards list (*Deviations* 36, 37).

40. **`기타` was not a label problem, and every FDA cell was reading as empty (2026-08-26).** The
    browser groups documents by `DocCategory`, and both FDA `doc_type`s — `regulation` and
    `codified_statute` — fell through `doc_category()` to `OTHER`. The visible symptom was 15
    documents filed under 기타; the one that mattered was not visible at all.

    `list_cells` computes `document_count` as `STATUTE + ADMIN_RULE`, so **the ScopeBar showed
    `fda_samd 0` and `fda_cosmetic 0`** while the store held 10 and 5 instruments. The cell badge
    said no connector reaches those cells yet, which is precisely the claim the badge exists to
    make truthfully, and it was false for a fortnight.

    Three options were weighed: map the two types onto the existing rungs (A); do that and rename
    the rungs so neither authority's vocabulary is privileged (B); or give each authority its own
    buckets (C). **B was chosen.** A alone leaves a C.F.R. Part filed under **현행 행정규칙** —
    correct placement under a heading that names a Korean instrument class, so the reader has to
    know it is a translation. C preserves each authority's real vocabulary and multiplies the
    buckets by authority, which is the grouping the browser exists to avoid.

    So the categories are now the **distinction** rather than one authority's name for it:
    `법률·법령` (법률·시행령·시행규칙 · U.S.C.) and `하위 규정` (고시 · C.F.R. Part). The rungs did
    not move, only the claim about whose vocabulary names them. `doc_type` labels stay
    authority-specific — a C.F.R. Part is shown as **C.F.R. Part**, never as 시행규칙 — because a
    `doc_type` names the instrument as its issuer issues it. The ladder is shared; the instruments
    are not.

    **`other` now means 분류 미정 and never "not Korean."** A bucket that quietly means *foreign*
    grows with every cell added, and it is the shape this defect had.

    This amends [phase1.5](phase1.5_frontend.md)'s *"grouped by the authority's own taxonomy"*
    (2026-08-06). That was right for a one-authority corpus and would have been wrong to generalise
    in advance — the FDA corpus is what made the second reading available.

    Two things kept it from recurring rather than one. `_CATEGORY_SQL` in `documents.py` mirrors
    `doc_category()` for `ORDER BY` and **restated the membership as inline literals**; it now
    imports `STATUTE_DOC_TYPES` / `ADMIN_RULE_DOC_TYPES`, so a new `doc_type` cannot be added to one
    and forgotten in the other. And `test_every_doc_type_maps_to_a_category` passed throughout —
    `OTHER` is a member of `DOC_CATEGORY_ORDER`, so a fall-through satisfied it. The new
    `test_no_storable_doc_type_lands_in_other` is the assertion that fails, with `guidance` its one
    exemption by decision ([ADR-0021](../design/ADR-0021-guidance-leaves-the-regulation-library.md)
    keeps it out of `documents` entirely) rather than by omission.
