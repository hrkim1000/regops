---
name: frontend-page
description: Use when adding or changing a frontend page or component — Next.js App Router patterns, server vs client data access, ScopeBar cookie scoping, established libraries, naming, and the pre-commit gates.
---

# Frontend Pages

Stack: **Next.js (App Router) + React + TypeScript 5 + Tailwind (dark theme)**.
Use the established libraries — do not introduce alternatives:
Zustand (`src/store/`, hooks `useXxxStore`) · Axios (JWT interceptor) ·
react-hook-form + zod · lucide-react/react-icons · react-toastify · clsx + tailwind-merge ·
Playwright (E2E).

## Data access

- **Server Components fetch via `serverGet<Svc>()`** (`lib/server-api.ts`) — reads the
  httpOnly `access_token` cookie, unwraps the envelope, returns `null` on failure (render an
  `<EmptyState>` fallback).
- **Client islands use `api<Svc>` axios instances** (`lib/api.ts`) — envelope unwrap + 401
  refresh built in. Typed helpers live in `lib/<domain>.ts`; types in `types/<domain>.ts`
  mirroring the backend schema.
- Async work: `202` + poll with `router.refresh()` on an interval while active
  (see `SuiteAutoRefresh` / `GeneratingTimer` patterns); set timers only after mount to avoid
  hydration mismatch.

## Scoping

- The active project/product/regulation comes from the **header ScopeBar cookies**
  (`ctx_project_id` / `ctx_product_id` / `ctx_regulation_id`) — read server-side with
  `readScope()`. **No per-page project pickers, no `?project_id=` queries.**
- Version selection inside a page: `?version_id=` + `VersionPicker`, labeling options
  `repo · version` (a multi-repo product has several identical `v1.0.0`s).
- Resolve derived entities from their **permanent binding** (e.g. a project's regulation via
  the project), not from a scope cookie.

## Page skeleton

1. `readUserRole()` → `<Forbidden/>` unless the role is allowed (mirror the backend RBAC).
2. Fetch independently — one failed fetch must not blank unrelated data
   (no `Promise.all` for unrelated resources).
3. Empty states for: no scope selected · no data · in-progress (with progress + elapsed
   mm:ss where work is long).
4. Roles gate actions client-side too (hide buttons the backend would 403).

## Naming & gates

- Components `PascalCase.tsx` (page-private ones under `_components/`); routes `kebab-case`;
  vars `camelCase`; constants `UPPER_SNAKE_CASE` in `types/constants.ts` (with `__other__`
  sentinels for select+Other patterns).
- Before commit: `npm run typecheck` && `npm run lint` from `frontend/` — both clean.
- Prefer Server Components; a client component only when interactivity requires it.
