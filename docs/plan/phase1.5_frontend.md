# Phase 1.5 — Frontend

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W7–W12 · **Status:** 🟡 foundation + regulation browser built early (2026-08-05); dashboard · Q&A · IR review still blocked on 1.3/1.4
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
- [ ] Client-island axios instances (`api<Svc>`) with 401 refresh — nothing needs one yet; every current read is a Server Component
- [ ] Zustand · react-hook-form + zod · react-toastify — deliberately **not** introduced until a page needs them. The skill says use these rather than alternatives, not that an unused dependency is progress
- [ ] Playwright E2E

### Scoping

- [ ] **The scope axis is the cell** (`authority` × `domain`) — header ScopeBar cookies read server-side via `readScope()`
- [ ] **No per-page cell pickers, no `?cell=` queries**
- [ ] Version selection within a page: `?version_id=` + `VersionPicker`, labelling language unambiguously
- [ ] A citation renders identically regardless of the viewer's selected cell — resolve from its pinned `document_version_id`, never from a scope cookie

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
- [x] **Status is derived, never stored** — `effective_date` against today (ADR-0016 decision 6). A status column would disagree with the date the morning a pending version comes into force, and nothing would run to flip it. It is computed over the **whole version set** because "which one is in force" is a property of the set (the latest whose date has arrived), not of a row: classifying rows one at a time would call every past date 시행중. The UTC/KST boundary is a known few-hour skew, harmless for a label and phase 1.4's problem for alert ordering
- [x] Document detail — annex children, versions, and **the three dates side by side** so a null `published_at` is visibly absent rather than silently replaced by our fetch clock
- [x] `effective_date` shows the retained 부칙 phrase, or "미해석 (1.1)" — never a guessed date ([ADR-0013](../design/ADR-0013-unresolvable-effective-dates.md))
- [x] Both hashes exposed with what each means: `content_hash` (change detection) vs `raw_object_key` (what gets cited)
- [x] Raw viewer rendering the archived artefact **unmodified**, with a visible truncation marker and a full download — a silently truncated regulation is indistinguishable from a short one
- [ ] Clause view — blocked on [phase1.1](phase1.1_normalization.md); there are no clauses yet

### Monitoring dashboard (alpha W7–8)

- [ ] Change feed by cell, with `change_kind` and impact grade
- [ ] Clause-level diff view — old vs new, renumbering shown as a move, not delete + add
- [ ] Alert detail with owner assignment
- [ ] Subscription management

### Q&A workbench

- [ ] Question → answer with citations rendered as deep links to clause text
- [ ] **"Needs verification" is a first-class result state**, not an error toast — it is the product working correctly
- [ ] Confidence displayed; sub-threshold answers visibly marked as pending human review
- [ ] **Every answer renders the version and effective date it relied on** — *"시행일 2026-04-02 기준"* ([ADR-0006](../design/ADR-0006-retrieval-and-citation-enforced-generation.md) decision 8) — and flags visibly when its clauses straddle an effective-date boundary. An answer that silently mixes in-force and not-yet-effective provisions looks identical to a correct one
- [ ] Query history with the audit trail
- [ ] Superseded-citation banner on stored answers whose evidence has since been amended

### IR review

- [ ] Draft IR queue with source clause side by side
- [ ] **Lock action gated to `ra`+**, with the signer and timestamp shown
- [ ] Draft IRs visibly distinct from locked — a draft must never look authoritative

### Cross-cutting

- [ ] `readUserRole()` → `<Forbidden/>`; roles hide actions the backend would 403
- [ ] Fetch independently — one failed fetch must not blank unrelated data
- [ ] Empty states for: no scope selected · no data · in progress (with elapsed mm:ss)
- [ ] **UI states that final judgment rests with the human** — a RegOps.md risk commitment, not a nicety

## Acceptance criteria

- [ ] `npm run typecheck && npm run lint` clean
- [ ] Playwright E2E: change detection → alert, and question → retrieval → cited answer
- [ ] Playwright E2E covers the **"needs verification"** path and a superseded-citation re-verification
- [ ] A `viewer` sees no lock button and is 403'd if the call is forged
- [ ] Switching cells in the ScopeBar does not alter any rendered citation
- [ ] Pilot users complete both core journeys unaided in usability review

## Risks & open questions

- **Retention is a gate and it is a UX outcome.** ≥ 60% weekly use for 4 consecutive weeks cannot be recovered by backend quality if the workbench is awkward. Usability review before W11 freeze, not after.
- **Cookie names for ScopeBar are unsettled** — fixed when the frontend is scaffolded.
- **1 FTE product/frontend in Phase 1.** Two surfaces plus IR review is the tightest staffing ratio in the plan.

## Deviations & decisions

_None yet._
