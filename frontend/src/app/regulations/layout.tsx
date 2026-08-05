import Link from 'next/link';
import { redirect } from 'next/navigation';

import { ScopeBar } from '@/components/ScopeBar';
import { SignOutButton } from '@/components/SignOutButton';
import { readUserEmail, readUserRole } from '@/lib/auth';
import { readScope } from '@/lib/scope';
import { accessToken, serverGet } from '@/lib/server-api';
import type { Cell } from '@/types/regulation';

/**
 * Shell for every regulation page: auth gate, the cell ScopeBar, and nothing else.
 *
 * The cells fetch is independent of whatever the page below fetches — a failed page load must not
 * take the ScopeBar with it (frontend-page skill: no `Promise.all` for unrelated resources).
 */
export default async function RegulationsLayout({ children }: { children: React.ReactNode }) {
  if (!(await accessToken())) redirect('/login');

  const [cells, role, email, scope] = [
    await serverGet<Cell[]>('regulation', '/cells'),
    await readUserRole(),
    await readUserEmail(),
    await readScope(),
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-surface-border bg-surface-raised/60">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
          <Link href="/regulations" className="text-sm font-semibold text-slate-100">
            RegOps
          </Link>
          <span className="text-[11px] text-slate-600">규제 원문</span>

          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            {email ? <span>{email}</span> : null}
            {role ? (
              <span className="rounded border border-surface-border px-1.5 py-0.5 font-mono text-[10px]">
                {role}
              </span>
            ) : null}
            <SignOutButton />
          </div>

          <div className="w-full">
            {cells ? (
              <ScopeBar cells={cells} active={scope} />
            ) : (
              <p className="text-xs text-red-400">셀 목록을 불러오지 못했습니다</p>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
