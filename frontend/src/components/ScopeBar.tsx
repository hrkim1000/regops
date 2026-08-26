'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useTransition } from 'react';

import { SCOPE_AWARE_PATHS, SCOPE_COOKIE, SECTION_ROOTS } from '@/types/constants';
import type { Cell } from '@/types/regulation';

/**
 * The one place a cell is chosen. Scope is an app-level axis, not a page-level filter, so there are
 * **no per-page cell pickers and no `?cell=` queries** (frontend-page skill) — every page reads the
 * same cookie server-side via `readScope()`.
 *
 * Client component because it writes a cookie and refreshes; everything it scopes stays a Server
 * Component.
 */
export function ScopeBar({ cells, active }: { cells: Cell[]; active: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();

  const destination = scopeDestination(pathname);

  function select(slug: string) {
    if (slug === active) return;
    // Not httpOnly: this is a display preference the server reads back, never a credential.
    document.cookie = `${SCOPE_COOKIE}=${slug}; path=/; max-age=31536000; samesite=lax`;
    startTransition(() => {
      // A page pinned to one entity cannot show another cell, so refreshing it in place is the
      // click doing nothing. Going to the section root is what "switch to that cell" can only mean
      // here, and it leaves the pinned page's own rule intact: while you are on it, it still
      // resolves its entity by id and ignores scope entirely.
      if (destination) router.push(destination);
      else router.refresh();
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {cells.map((cell) => {
        const total = cell.document_count;
        const empty = total === 0;
        const isActive = cell.slug === active;
        return (
          <button
            key={cell.id}
            type="button"
            onClick={() => select(cell.slug)}
            disabled={pending}
            // An empty cell is still shown and still selectable. Hiding it would imply the
            // scope is 2 cells; it is 8, and 6 of them simply have no connector yet.
            title={scopeTitle({ empty, total, isActive, destination })}
            className={[
              'rounded-md border px-2.5 py-1 font-mono text-xs transition-colors',
              isActive
                ? 'border-accent bg-accent-muted/40 text-slate-100'
                : 'border-surface-border text-slate-400 hover:border-slate-600 hover:text-slate-200',
              empty && !isActive ? 'opacity-40' : '',
            ].join(' ')}
          >
            {cell.slug}
            <span className="ml-1.5 text-[10px] text-slate-500">{total}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Where a cell change should land, or `null` to re-render where we are.
 *
 * `null` for a route that reads the cookie itself. Otherwise the section root, because the page is
 * pinned to an entity resolved by id — a document, an alert, an answer — and no cell selection
 * changes what it shows.
 */
export function scopeDestination(pathname: string | null): string | null {
  if (!pathname) return null;
  if ((SCOPE_AWARE_PATHS as readonly string[]).includes(pathname)) return null;
  return (SECTION_ROOTS as readonly string[]).find((root) => pathname.startsWith(`${root}/`)) ?? null;
}

function scopeTitle({
  empty,
  total,
  isActive,
  destination,
}: {
  empty: boolean;
  total: number;
  isActive: boolean;
  destination: string | null;
}): string {
  if (isActive) return empty ? '아직 수집된 문서가 없습니다' : `${total}건 — 현재 선택된 셀`;
  const count = empty ? '아직 수집된 문서가 없습니다' : `${total}건`;
  // Say where the click goes. The complaint that produced this was that the button looked live and
  // did nothing; a button that navigates should say so before it does.
  return destination ? `${count} · 목록으로 이동합니다` : count;
}
