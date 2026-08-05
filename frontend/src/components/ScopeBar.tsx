'use client';

import { useRouter } from 'next/navigation';
import { useTransition } from 'react';

import type { Cell } from '@/types/regulation';
import { SCOPE_COOKIE } from '@/types/constants';

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
  const [pending, startTransition] = useTransition();

  function select(slug: string) {
    // Not httpOnly: this is a display preference the server reads back, never a credential.
    document.cookie = `${SCOPE_COOKIE}=${slug}; path=/; max-age=31536000; samesite=lax`;
    startTransition(() => router.refresh());
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
            title={empty ? '아직 수집된 문서가 없습니다' : `${total}건`}
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
