# Phase 1.5 — Frontend

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W7–W12 · **Status:** 🟢 done (2026-08-14) — foundation + regulation browser built early (2026-08-05), clause view added once [phase1.1](phase1.1_normalization.md) landed (2026-08-06), **IR review + lock and the submission-document view built 2026-08-10**, **Q&A workbench built 2026-08-11** on [phase1.3](phase1.3_retrieval_qa.md), **monitoring dashboard built 2026-08-13** on [phase1.4](phase1.4_monitoring.md), **Playwright E2E built and green 2026-08-14** — 10 tests over both journeys against the live stack and the real model. The usability review is the one acceptance row left, and it is **미측정**: it needs pilot users, not code
- **Governed by:** [.claude/skills/frontend-page](../../.claude/skills/frontend-page/SKILL.md), [ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md)
- **Depends on:** [phase1.3](phase1.3_retrieval_qa.md), [phase1.4](phase1.4_monitoring.md)
- **Service:** `frontend`

---

## Goal

Two surfaces for 20–30 pilot users: a monitoring dashboard and a Q&A workbench. Along with 1.4, this
is one of the two branches that can absorb schedule slack — but the retention gate (≥ 60% weekly use
for 4 consecutive weeks) is a UX outcome, so "absorbs slack" is not "can be skipped."

## Scope

**In:** dashboard, Q&A workbench, IR review and lock UI, ScopeBar cell scoping, auth.

**Out:** gap analysis workbench (2.2), tenant admin (3.0), white-label theming (3.0).

## Tasks

### Foundation

- [x] Next.js App Router + React + TypeScript + Tailwind (dark theme)
- [x] `/api/<svc>/*` rewrites to the four services
- [x] **Middleware injects the JWT into `/api/<svc>/*`.** The token is httpOnly so client JS cannot attach it, and a rewrite alone forwards an anonymous request — which is why the raw-download link 404'd until this existed. Injecting server-side keeps both properties: the client never sees the token, the service still gets a bearer credential
- [x] `serverGet<Svc>()` / `serverGetPage()` / `serverGetRaw()` for Server Components — envelope unwrap, `null` on failure so one dead resource renders an `<EmptyState>` rather than blanking the page
- [x] Prefer Server Components; the only client components are ScopeBar and the login/sign-out forms
- [x] **`tsc --noEmit` wired into CI** — the phase 0 deferral, now that there is a frontend
- [x] **`frontend.depends_on` gates on `platform-core` health** — the other phase 0 deferral
- [x] **Playwright E2E** (2026-08-14) — `frontend/e2e/`, 10 tests over the two journeys, run against
      the compose stack with the real corpus and the real model. `npm run e2e`; see deviations 17–20
      and [frontend/e2e/README.md](../../frontend/e2e/README.md)

### Deliberately not built

Both were listed as tasks and neither is a gap. Recorded here rather than left as open boxes, so the
phase does not read as unfinished for the absence of things it decided against:

- **Client-island axios instances (`api<Svc>`) with 401 refresh.** Nothing needs one. Every read is
  a Server Component, and the five client islands that write (ScopeBar, AskBox, AssignBox, the
  login and sign-out forms) each make a single `fetch` and handle their own failure in place. A
  shared instance would be an abstraction with one caller per method.
- **Zustand · react-hook-form + zod · react-toastify.** The frontend-page skill names these as the
  libraries to reach for rather than alternatives — not as a checklist. No page has cross-component
  state, and no form has more than three fields. An unused dependency is not progress; it is a
  transitive advisory waiting to go red under a release gate (deviation 16).

### Scoping

- [x] **The scope axis is the cell** (`authority` × `domain`) — header ScopeBar cookies read server-side via `readScope()`. The same bar now carries all three pillars: a reader scoped to `mfds_cosmetic` in the browser lands in the same cell in Q&A *and* in the alert feed, because subscription matching is on cell and only on cell ([ADR-0009](../design/ADR-0009-service-boundaries-per-pillar.md) decision 5)
- [x] **No per-page cell pickers, no `?cell=` queries** — with **one deliberate exception**: the subscription form picks cells, because it does not *show* a cell, it manages a standing list of them, and making a reader switch scope four times to subscribe to four cells would serve the rule rather than the reader. Nothing on that page reads scoped data
- [x] Version selection within a page: `?version_id=` + `VersionPicker`, labelling language unambiguously
- [x] A citation renders identically regardless of the viewer's selected cell — resolve from its pinned `document_version_id`, never from a scope cookie

### Regulation browser (built 2026-08-05, ahead of sequence)

Built early because it is the only 1.5 surface whose backend already exists, and because a viewer is
how ingestion defects become visible. It immediately earned that: the document list showed 56 annexes
where the archive held 76, which is how the 별표 identity collision was found ([phase1.0](phase1.0_ingestion.md)
deviation 11), and 화장품법 시행규칙 labelled 법률 exposed `doc_type` never being read from the
envelope (deviation 12). Both were silent in the API and in every test.

- [x] Document list per cell, annexes excluded (`parent_only`) so a 고시 with four 별표 reads as one instrument, not five
- [x] **Grouped by the authority's own taxonomy** (2026-08-06) — 현행법령 · 현행 행정규칙 · 법령 별표·서식 · 행정규칙 별표·서식, the way 국가법령정보 files its holdings, with 가나다 ordering inside each group. A flat "본문 20건" says nothing about what kind of instrument those are; "법령 3 · 고시 17" reads the way the source does. The category is **derived, never stored** (`doc_category()`): it is `doc_type` plus, for an annex, the *parent's* `doc_type`, because 별표 of a 법령 and 별표 of a 고시 are different categories and the annex row carries `annex` for both
- [x] **Grouping is ordered in SQL, not in the client.** Sorting a page that has already been sliced would only group the rows that page happens to hold. Postgres orders Hangul by code point, which *is* 가나다순 for the Hangul Syllables block, so no collation is configured
- [x] Annex counts appear in the header even though annexes are not listed — a cell's real weight is in its 별표 (47 + 53 for `mfds_cosmetic`), and hiding the number would misreport the corpus. RSS boards get their own **변경 신호** group rather than being counted as instruments
- [x] **시행예정 is visible** (2026-08-06) — a `시행예정 N` badge on the list row, and 시행중 / 시행예정 / 지난 버전 per version on the detail page. Pending amendments are ingested as versions of the *same* Document (ADR-0016 decision 1), so 화장품법 with four 공포된-but-not-yet-in-force amendments looked exactly like one with none: a single row whose only hint was "버전 5". Live today: 화장품법 4, 의료기기법 2, 디지털의료제품법 1
- [x] **Status is derived, never stored** — `effective_date` against today (ADR-0016 decision 6). A status column would disagree with the date the morning a pending version comes into force, and nothing would run to flip it. It is computed over the **whole version set** because "which one is in force" is a property of the set (the latest whose date has arrived), not of a row: classifying rows one at a time would call every past date 시행중. The UTC/KST boundary is a known few-hour skew, harmless for a label and phase 1.4's problem for alert ordering — **closed there** (phase1.4 deviation 8): briefing timestamps render in `AUTHORITY_TIMEZONE`, and the briefing window is rolling rather than a calendar day so there is no boundary to get wrong for a subscriber holding cells across authorities
- [x] Document detail — annex children, versions, and **the three dates side by side** so a null `published_at` is visibly absent rather than silently replaced by our fetch clock
- [x] `effective_date` shows the retained 부칙 phrase, or "미해석 (1.1)" — never a guessed date ([ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md))
- [x] Both hashes exposed with what each means: `content_hash` (change detection) vs `raw_object_key` (what gets cited)
- [x] Raw viewer rendering the archived artefact **unmodified**, with a visible truncation marker and a full download — a silently truncated regulation is indistinguishable from a short one
- [x] **Clause view** (2026-08-06) — the parse output beside the archived bytes, one click apart.
      [phase1.1](phase1.1_normalization.md) unblocked it, but nothing exposed the clause store: the
      `regulation` API served cells · documents · versions · raw and no clauses, so this needed a
      read endpoint (`GET /document-versions/{id}/clauses`) before any page could exist
- [x] **Document order is `ordinal`, ordered in SQL** — the path is the *address*, not the sort key.
      Sorting by `clause_path` files 제10조 between 제1조 and 제2조
- [x] **`clause_path` is rendered for every clause**, including each annex table row. It is what a
      Citation pins, so a reader has to see the address they would cite and not just the text
- [x] **An annex table is drawn from the ordered header on its 표 clause, never from a row.** A
      row's `row_columns` is `jsonb` and Postgres sorts an object's keys, so rendering a row alone
      gives alphabetical columns — a limit table that looks right while stating the wrong limits.
      ADR-0014 decision 4 puts the order on the 표 for exactly this reason; the renderer depends on
      it, and a unit test pins it
- [x] **Zero clauses is not always a defect** — the response carries `parseable`, so an RSS board
      reads as "이 문서 유형은 조문을 갖지 않습니다" rather than as an ingestion gap
      ([phase1.1](phase1.1_normalization.md) deviation 11)
- [x] Version status (시행중 / 시행예정 / 지난 버전) shown on the clause page, fetched independently
      — clause text read without it is how not-yet-in-force provisions get mistaken for current law
- [x] Paginated at 500 clauses with a visible range and page links; the largest version holds 2,212

### Monitoring dashboard (built 2026-08-13, on [phase1.4](phase1.4_monitoring.md))

- [x] Change feed by cell, with `change_kind` and impact grade — **one row per amendment, not per change event**. 109 events over the gated corpus compose 7 alerts, and listing the events would bury 37 real edits under a thousand empty ones: the exact failure [ADR-0002](../design/ADR-0002-domain-model.md) decision 7 exists to prevent, reintroduced at the last step
- [x] Clause-level diff view — old vs new, renumbering shown as a move, not delete + add. Needed a new `regulation` read (deviation 6); `match_basis` and `needs_review` travel with each row so a move the authority *stated* never renders like one we inferred
- [x] Alert detail with owner assignment — `ra`+ only, written to the audit chain, reassignment included
- [x] Subscription management — subscribe, raise the severity floor, **중지 rather than delete** so the delivery history survives
- [x] The two Go/No-Go gates above the feed — detection coverage against the *emitted* event count from the other side of the seam, and latency from both clocks with `측정 불가` counted separately. Neither gate guards itself: a system that alerted on everything would score perfectly on coverage
- [x] Daily briefing strip — composed on read, rolling 24h, timestamps in the authority's own timezone

### Q&A workbench

- [x] Question → answer with citations rendered as deep links to clause text — the link carries `clause_path`, and the clause view resolves it to whichever page holds it (deviation 5)
- [x] **"Needs verification" is a first-class result state**, not an error toast — it is the product working correctly. It is a tab, a banner and a stored reason, and the two reasons that are *defect signals* (`fabricated_citation`, `unparseable`, `model_unavailable`) are styled apart from "근거 없음" so a model regression cannot read as an honest refusal
- [x] Confidence displayed; sub-threshold answers visibly marked as pending human review
- [x] **Every answer renders the version and effective date it relied on** — *"시행일 2026-04-02 기준"* ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 8) — and flags visibly when its clauses straddle an effective-date boundary. An answer that silently mixes in-force and not-yet-effective provisions looks identical to a correct one
- [x] Query history with the audit trail — the answer log with its filters, and per-answer provenance (`llm_provider` / `llm_model` / `prompt_version` / `retrieval_version`)
- [x] Superseded-citation banner on stored answers whose evidence has since been amended, plus the **근거 개정** queue it feeds

### IR review

- [x] Draft IR queue with source clause side by side — **linked, not side by side**; see deviation 3
- [x] **Lock action gated to `ra`+**, with the signer and timestamp shown
- [x] Draft IRs visibly distinct from locked — a draft must never look authoritative
- [x] Classification-coverage panel above the list — ADR-0004 decision 6 as a number, with the unclassified remainder always shown

### Cross-cutting

- [x] `readUserRole()` → `<Forbidden/>`; roles hide actions the backend would 403
- [x] Fetch independently — one failed fetch must not blank unrelated data
- [x] Empty states for: no scope selected · no data · in progress (with elapsed mm:ss)
- [x] **UI states that final judgment rests with the human** — a RegOps.md risk commitment, not a nicety. On the answer page the caveats are rendered *above* the answer text: a straddled effective date, a superseded citation and a sub-threshold confidence all produce an answer that looks identical to a correct one, so a banner below the prose is a banner read after the reader has already acted

## Acceptance criteria

- [x] `npm run typecheck && npm run lint` clean — both green on the host after `npm install` (2026-08-13); before that the toolchain existed only in the container image
- [x] Playwright E2E: change detection → alert, and question → retrieval → cited answer — green
      2026-08-14, 10 tests in 59s against the live stack
- [x] Playwright E2E covers the **"needs verification"** path and a superseded-citation
      re-verification — the refusal forced by a cell with no index rather than by a stub, the
      supersede by the real `assistant.supersede_answer_citations` task
- [x] A `viewer` sees no lock button and is 403'd if the call is forged — verified live 2026-08-10 through the `/api/regulation/*` rewrite (403 viewer · 200 ra · 409 re-lock)
- [x] Switching cells in the ScopeBar does not alter any rendered citation — every citation link is built from its own pinned `document_id` / `document_version_id`, and no page resolves one through the scope cookie
- [ ] **미측정** — Pilot users complete both core journeys unaided in usability review. This needs
      20–30 pilot users and a person watching them; nothing in the repository can produce it, and a
      row ticked on the strength of a passing E2E suite would be ticked for the wrong reason. A
      green suite says the journeys *work*; this row asks whether they work **unaided**, which is
      the retention gate's actual question. Carried the way [phase1.6](phase1.6_evaluation.md)
      carries its four unmeasured gates: named, with its reason, rather than defaulted

## Risks & open questions

- **Retention is a gate and it is a UX outcome.** ≥ 60% weekly use for 4 consecutive weeks cannot be recovered by backend quality if the workbench is awkward. Usability review before W11 freeze, not after.
- **Cookie names for ScopeBar are unsettled** — fixed when the frontend is scaffolded.
- **1 FTE product/frontend in Phase 1.** Two surfaces plus IR review is the tightest staffing ratio in the plan.

## Deviations & decisions

**1. The clause view needed a backend endpoint, not just a page.** The task read as frontend work
blocked on [phase1.1](phase1.1_normalization.md) producing clauses. 1.1 produced 25,729 of them and
the page was still impossible: `regulation`'s read API stopped at the version and the archived
bytes, so `GET /document-versions/{id}/clauses` was written as part of this slice. Read-only, like
the rest of that router — everything that *writes* the clause store is still the pipeline
(CLAUDE.md § The seam).

**2. A table's column order is load-bearing and lives in exactly one place.** `row_columns` on a
`table_row` is a `jsonb` object, and Postgres sorts its keys — 등급 comes back before 연번. The
ordered header on the parent 표 clause (ADR-0014 decision 4) is therefore the only record of what
order the authority published, and the renderer reads it from there. A row whose 표 fell on the
previous page is deliberately **not** drawn as a table: guessed column order in a limit table is
worse than no table, because it looks correct.

**3. The draft IR queue links to its clause rather than showing it side by side.** The task said
"side by side", and that is the right shape *once a reviewer is reading one IR at a time*. What was
built is a list where every citation is a link into the clause view, anchored on `clause_path`.

Two reasons, and the second is the load-bearing one. An IR can cite several clauses across several
versions, so "the source clause" is not always one thing to put in a panel. And a citation must
resolve through its **own** pinned `document_id` / `document_version_id`, never through the page it
is rendered on — a superseded citation points at an older version, and following it has to land on
the text that was actually cited, not on the current text at the same path. A side-by-side panel
fed from the route's `versionId` would quietly show the wrong evidence for exactly the citations
that matter most. Revisit as a per-IR detail view, where one IR bounds the panel honestly.

**4. Coverage is rendered above the IR list, not below it.** "1 IR from 4 clauses" is
uninterpretable without the classification ledger beside it (ADR-0004 decision 6) — it cannot be
told apart from 3 missed obligations. Putting the count first and the denominator later is how a
partial extraction reads as a complete one, so the panel leads and `unclassified` is shown **even
when it is zero**: a figure that only appears when it is bad teaches a reader to assume it is fine.

**5. The status filter defaults to `locked`, mirroring the API.** This page *is* the review queue,
so drafts have to be reachable — but a reader who lands here without choosing sees only what
actually flows downstream. An unrecognised `?status=` falls back to `locked` rather than to
"everything": a typo in a query string must not widen what is shown.

**6. A submission-document view was added, and it is deliberately not a checklist.** Korean
procedural clauses state 항 = the filing duty and 호 = each required document, and phase 1.1 already
parsed the 호 as child clauses — so the list is *read*, not extracted. Measured over the gated
corpus: **103 procedures, 370 document items, 99% with items already parsed.**

No LLM is involved and nothing is stored. The item text is the document name, so there is nothing to
generate and nothing to hallucinate; and the whole result is a pure function of clauses, so storing
it would create a second derived artefact to invalidate on re-parse — the bug
`parse._invalidate_derived` exists to fix for diffs (2,373 orphaned rows, observed).

The load-bearing constraint is that **conditions are never flattened**. Only **6 of 103 procedures
(6%) are unconditional**; the rest are qualified by case, defer to another instrument, or take their
enabling clause from a different law. So each item carries `conditional` plus its condition verbatim,
each requirement publishes machine-readable `Caveat` codes, and the UI renders the caveats *above*
the items with no tickboxes anywhere. A conditional list shown as a definitive one would manufacture
exactly the compliance error the gap-analysis pillar exists to find.

**What it does not answer:** which conditions bind a given company. Applicability is Compliance-owned
and tenant-scoped ([ADR-0007](../design/ADR-0007-context-map-and-applicability.md), phase 2.2), and
`regulation` has no product context — the same boundary [ADR-0017](../design/ADR-0017-extraction-determinism-and-conditional-obligations.md)
decision 2 draws for class-restricted IRs. The page says so in its own copy rather than only here.

Two measured limits, recorded rather than hidden:

- **Detection is a pattern, and the pattern is the precision.** A loose first attempt matched 341
  clauses, a strict one 92; the committed set yields 102–103 and its two negative patterns
  (`다음 각 호의 사항|어느 하나`, and exemptions like `제출하지 아니할 수 있다`) are what earn that.
  It has **not** been validated by an RA against a sample — that belongs with 1.6's markup.
- **Cross-instrument lists are incomplete.** 55 of 103 procedures take their enabling clause from
  another law (법 → 시행규칙). Joining them needs `clause_references`, which is phase 2.1
  ([ADR-0010](../design/ADR-0010-semantic-enrichment-and-graph-model.md) decision 7). Flagged as the
  `cross_instrument` caveat rather than silently under-reported.

**7. The app shell moved out of `regulations/layout.tsx` into a shared `AppShell`.** Not tidying —
the **ScopeBar has to be the same control on both sections**. Scope is an app-level axis (no
per-page cell pickers), so a reader who scopes to `mfds_cosmetic` in the regulation browser must
land in the same cell when they open Q&A. Two independent shells would have quietly reset the one
bound that stops a cosmetic question being answered from device regulation
([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 9). A route
group would have been the other idiom; extracting a component moved no files and left every URL
alone.

**8. Cross-cell is a checkbox in the ask box, worded as the risk it carries.** The alternative — a
cell picker on the page — would have made cross-cell retrieval an accident rather than the explicit
mode the ADR requires. The label says what it does (*"다른 셀도 검색 — 화장품 질문에 의료기기
규정으로 답할 수 있습니다"*) rather than naming the feature.

**9. A citation deep link needed a backend parameter.** `GET /document-versions/{id}/clauses`
paginates at 500 and the largest version holds 2,212 clauses, so linking by document would land the
reader on page 1 of 5 — a link to the instrument, not to the evidence. `?clause_path=` now resolves
to whichever page holds that clause, and the anchor already existed on every clause row. Rank is
**counted by ordinal**, not derived from it: ordinals are a reading order and are not dense, so
`ordinal // page_size` would send the reader past the end. A path that does not resolve returns page
1 *and says so* — that case is a citation into a different version, which is exactly what an
immutable citation looks like after an amendment.

**10. Found by running it: a model timeout left a question with no answer at all.** Generation and
verification calls were unguarded, so an `httpx.ReadTimeout` propagated out of the Celery task and
the query row sat there answerless — the asker watching a spinner until the poll ceiling, and the
monitored "needs verification" rate silently excluding every failure, which is the one direction
that makes it look healthy. Both calls are now caught and recorded as `model_unavailable`, a new
value in the closed `NoAnswerReason` inventory, and the verification side is the more important of
the two: an answer whose claims were never checked must not reach a reader as though they had been.
Fixed in `assistant`, covered by two cases in the 1.3 acceptance suite.

**11. The answer list returns a summary, not full answers.** Rendering citations and verdicts per
row meant two extra queries per answer — 400 round trips at `page_size=200` to draw a list nobody
reads in full. The list carries `citation_count` and `superseded_citation_count` from one grouped
query, and the detail endpoint enumerates. The counts are not decoration: on the 근거 개정 queue,
*"2 of 3 citations have moved"* is the whole reason a row is in the list.

**12. A pending question was invisible, and the ask box gave up silently.** The answer log lists
*answers*, so a question whose worker is still running appeared nowhere at all — and on a small local
model "still running" is minutes, not seconds. Reported from use as "계속 돌고 있음". The ask box now
says what happened when its 4-minute poll ceiling is reached instead of quietly refreshing, and
`/qa/queries/{id}` renders the pending question with an elapsed clock, redirecting to the answer once
it lands. That URL stays valid for the whole life of a question rather than only after it is
answered.

**13. Refusal copy is per reason, in three tones.** Reported from the UI: `model_unavailable`
rendered as *"모델이 잘못된 응답을 냈다는 뜻입니다"* — the model had not responded at all. One shared
"defect signal" sentence covered three genuinely different facts. `NO_ANSWER_REASON_TONE` now splits
them into `expected` (the product working — no evidence, or evidence that did not hold), `regression`
(a 조문 번호 from memory, or an unusable reply) and `infrastructure` (never reached), each with its
own sentence in `NO_ANSWER_REASON_HINT`. Rendering all three the same is how a broken model hides
inside an honest-looking refusal rate.

**14. The diff view needed a new `regulation` read** (2026-08-13). An alert names the clauses it
covers and carries a `clause_diff_id` per reference, but `monitoring` never reads clause text —
it composes alerts from `change_events` on its own side of the seam (CLAUDE.md § The seam), and
putting the old and new bodies on the alert would have made the alerting service a reader of the
clause store. So `GET /document-versions/{id}/diffs` was added to `regulation`, filtered by the
alert's clause paths, and the page joins the two on the reader's behalf. The seam stays intact
and the reader still gets the only thing they came for: *what does it say now?*

Two properties of that endpoint are deliberate. Clause text is **bounded and the truncation is
flagged** — a single 별표 clause in the corpus runs to 340 KB, and a shortened clause shown as if
whole is worse than no clause, because a reader draws a conclusion from text that was cut away.
And `match_basis` / `similarity` / `needs_review` travel with every row, so a move the authority
*stated* in 조문이동이전/이후 never renders identically to one inferred from text similarity.

**15. The subscription form is the one page that picks cells.** Everywhere else the ScopeBar decides
(frontend-page skill: no per-page cell pickers), and that rule is load-bearing — it is what keeps
a cosmetic question from being answered out of device regulation. But the subscription page does
not *show* a cell, it manages a standing list of them, and forcing a reader to switch scope four
times to subscribe to four cells would serve the rule rather than the reader. Nothing on that
page reads scoped data, so the property the rule protects is not in play.

**16. The lockfile is tracked, the image installs with `npm ci`, and two transitive deps are
overridden.** `package.json` had been tracked since the frontend was scaffolded and its lockfile
never was, so every machine and every CI run resolved a fresh dependency tree — under release gates
(`npm run typecheck && npm run lint`) that can go red on a transitive release nobody chose. The
Dockerfile compounded it by running `npm install` over a lockfile it had copied but did not have to
honour; it now runs `npm ci`, which installs exactly the pinned tree and fails if the two disagree.

The overrides are the part that will go stale, so they are written down here. `npm audit` reported
**3 high-severity findings, all inside `next@15.5.23`**: its exact pin of `postcss@8.4.31` (XSS via
unescaped `</style>`, and three sourceMappingURL path-traversal advisories) and its optional
`sharp@^0.34.3` (inherited libvips CVEs). `next@15.5.23` is the **latest 15.x** — the fixes are not
backported, which is why `npm audit fix --force` proposes `next@16.3.0`, a major upgrade.

Neither was exploitable here, and that is worth stating rather than implying: postcss runs at build
time over CSS we author ourselves, and the sharp CVEs need attacker-supplied images, while this app
renders **no `next/image` at all** and configures no `images.remotePatterns`. A major framework
upgrade to close two findings with no reachable path would have been the expensive way round. So
`overrides` pins `postcss` to the root's own `$postcss` (`^8.5.26` — one source of truth rather than
a second version literal to drift) and `sharp` to `^0.35.3`. **0 vulnerabilities**, `next` unmoved,
and a full `next build` green across every route, which is the only real test that overriding a
framework's own pinned CSS toolchain did no harm.

**Revisit when Next 16 is adopted**, or if Next backports: an override that outlives its reason
silently holds a dependency back.

**17. The E2E suite drives the live stack and the real model, and is deliberately not a CI gate.**
There is no `webServer` block and nothing is mocked: the app under test is
`docker compose --profile app up -d` — four services, pgvector, MinIO, two Celery workers and
host-native Ollama — reading the real 526-document corpus. A suite that could pass with every
service down would be worse than no suite, so `global-setup.ts` checks the world first and fails
with the command that fixes it rather than with a timeout.

The cost of that choice is determinism, and it is paid where it falls rather than hidden. **No
assertion depends on what the model says.** A live `gemma3:4b` phrases the same question differently
every run and may decline it, so the specs pin the invariant the product is built on — *no prose
without evidence, every citation pinned to an immutable version* — and leave whether the answer is
*right* to [phase1.6](phase1.6_evaluation.md), where it is scored against golden sets per domain
rather than off one ad-hoc question.

Three properties make that honest rather than lax:

- **The refusal path is deterministic without a stub.** `fda_samd` is one of the six cells with no
  connector, so it holds no clauses and no embeddings, and retrieval returns nothing on every run —
  `no_retrieval`, before the model is asked to generate anything. Deterministic *because of* how the
  product behaves.
- **An unreachable model fails the run.** `model_unavailable` is rejected explicitly, so a run with
  Ollama switched off goes red instead of scoring a green "it refused, as designed".
- **`retries: 0`.** A retried live-model run turns a flaky product into a green report.

It stays out of CI because a live answer takes minutes and a red build would as often mean *the
model was slow* as *the product broke* — a gate that cries wolf is a gate people learn to ignore. It
runs where the integration suites run: locally and against a stage stack, before a phase is called
done. CI keeps `typecheck` and `lint`, which are deterministic, and `next lint` now covers `e2e/`
too.

**18. One journey needed a seeded row, and only one.** Three of the four run on ingested data.
The fourth cannot: a superseded citation needs an answer that cites a clause a later amendment
moved, and **no answer in the corpus does** — the two answers pinned to a version that was amended
cite 제6장/제36조, while that amendment moved 제1장/제2조 and 제2장/제7조. The sweep therefore
correctly flags nothing, and the acceptance row would have been unprovable.

The alternatives were re-diffing a live version, or asking the model and hoping it cited the one
amended clause; both replace a deterministic check with a coin flip. So `scripts/e2e_fixture.py`
seeds **one answer**, pinned to a clause a real `clause_diff` really moved — and the sweep itself is
the real `assistant.supersede_answer_citations` task, sent by name on the real queue exactly as the
diff stage sends it. No model is involved on that path at all; superseding is deterministic SQL over
`clause_diffs`. The seeded rows carry a marker and are removed in `afterAll`, verified empty after
the run. What it asserts is ADR-0002 decision 4: same version, same path, same row, **plus** a flag
— the citation is flagged, never rewritten.

**19. The suite signs in as its own principal, because assignment is audited.** Owner assignment
writes to the hash chain, so a suite acting as `ra@example.com` would put automated rows under a
person's name and make the chain say something untrue about who did what. It uses
`e2e-ra@example.com` at role `ra`; the `viewer` half writes nothing and reuses the account phase 0's
acceptance suite already signs in as. **No password is in the repository** — both come from the
environment and the run stops before opening a browser if either is missing.

That also closed a hole this slice opened: `frontend/.dockerignore` was untracked (the root
`.gitignore` ignores `.dockerignore` wholesale), and `COPY frontend/ ./` would have carried
`e2e/.auth/*.json` — a signed-in user's JWT — into an image layer. The file is now tracked by
exception and excludes the suite from the image.

**20. Found by running it: the model fabricated a citation, and the pipeline threw the answer
away.** The first live run of *"화장품책임판매업자는 안전성 정보를 언제까지 보고해야 하나요?"* came
back `needs_verification / fabricated_citation` — `gemma3:4b` cited a 조문 number that retrieval had
never returned. That is the guardrail firing, not failing: nothing unsourced reached the reader, and
the refusal carried its reason. It is consistent with the corpus at large, where 11 of 32 answers
sit at `fabricated_citation`.

It did, however, falsify the spec's first draft, which required any refusal to be an "expected"-tone
one and so treated the guardrail working as a test failure. The assertion now separates the two
questions the tone map exists to separate: **the pipeline must reject a fabricated citation**
(asserted here, on every run), and **how often a model fabricates one** is model quality — measured
against the 1.6 golden sets per domain and per gated cell, which is the only place a rate means
anything. An E2E suite that failed on model quality would be a golden-set run with one question in
it.
