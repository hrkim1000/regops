import Link from 'next/link';

import { ScopeBar } from '@/components/ScopeBar';
import { SignOutButton } from '@/components/SignOutButton';
import { readUserEmail, readUserRole } from '@/lib/auth';
import { readScope } from '@/lib/scope';
import { serverGet } from '@/lib/server-api';
import type { Cell } from '@/types/regulation';

/** The two pillars Phase 1 ships. `monitoring` joins them when 1.4 lands. */
const SECTIONS = [
  { key: 'regulations', href: '/regulations', label: '규제 원문' },
  { key: 'qa', href: '/qa', label: '질의응답' },
] as const;

export type Section = (typeof SECTIONS)[number]['key'];

/**
 * The chrome every signed-in page wears: identity, the cell ScopeBar, and the section nav.
 *
 * Shared rather than duplicated per section, because the **ScopeBar has to be the same control on
 * both**. Scope is an app-level axis (frontend-page skill: no per-page cell pickers), so a reader
 * who scopes to `mfds_cosmetic` in the regulation browser must land in the same cell when they
 * switch to Q&A — otherwise the one bound that prevents a cosmetic question being answered from
 * device regulation (ADR-0006 decision 9) would quietly reset on navigation.
 *
 * The cells fetch is independent of whatever the page below fetches — a failed page load must not
 * take the ScopeBar with it.
 */
export async function AppShell({
  active,
  children,
}: {
  active: Section;
  children: React.ReactNode;
}) {
  const cells = await serverGet<Cell[]>('regulation', '/cells');
  const role = await readUserRole();
  const email = await readUserEmail();
  const scope = await readScope();

  return (
    <div className="min-h-screen">
      <header className="border-b border-surface-border bg-surface-raised/60">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
          <Link href="/regulations" className="text-sm font-semibold text-slate-100">
            RegOps
          </Link>

          <nav className="flex items-center gap-1">
            {SECTIONS.map((section) => (
              <Link
                key={section.key}
                href={section.href}
                className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                  section.key === active
                    ? 'bg-accent-muted/40 text-slate-100'
                    : 'text-slate-500 hover:text-slate-200'
                }`}
              >
                {section.label}
              </Link>
            ))}
          </nav>

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
