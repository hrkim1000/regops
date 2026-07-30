# Phase 1.5 — Frontend

- **Roadmap:** Phase 1 (M0–4) · **Weeks:** W7–W12 · **Status:** ⬜ planned
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

- [ ] Next.js App Router + React + TypeScript + Tailwind (dark theme)
- [ ] Established libraries only: Zustand · Axios (JWT interceptor) · react-hook-form + zod · lucide-react · react-toastify · clsx + tailwind-merge · Playwright
- [ ] `/api/<svc>/*` rewrites to the four services
- [ ] `serverGet<Svc>()` for Server Components; `api<Svc>` axios instances for client islands — envelope unwrap and 401 refresh built in
- [ ] Prefer Server Components; client components only where interactivity requires it

### Scoping

- [ ] **The scope axis is the cell** (`authority` × `domain`) — header ScopeBar cookies read server-side via `readScope()`
- [ ] **No per-page cell pickers, no `?cell=` queries**
- [ ] Version selection within a page: `?version_id=` + `VersionPicker`, labelling language unambiguously
- [ ] A citation renders identically regardless of the viewer's selected cell — resolve from its pinned `document_version_id`, never from a scope cookie

### Monitoring dashboard (alpha W7–8)

- [ ] Change feed by cell, with `change_kind` and impact grade
- [ ] Clause-level diff view — old vs new, renumbering shown as a move, not delete + add
- [ ] Alert detail with owner assignment
- [ ] Subscription management

### Q&A workbench

- [ ] Question → answer with citations rendered as deep links to clause text
- [ ] **"Needs verification" is a first-class result state**, not an error toast — it is the product working correctly
- [ ] Confidence displayed; sub-threshold answers visibly marked as pending human review
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
