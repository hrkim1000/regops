import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { readScope } from '@/lib/scope';
import { serverGet, serverGetPage } from '@/lib/server-api';
import {
  ALERT_PAGE_SIZE,
  ALERT_SEVERITY_LABEL,
  ALERT_SEVERITY_ORDER,
  ALERT_SEVERITY_STYLE,
} from '@/types/constants';
import type {
  AlertMetrics,
  AlertSeverity,
  AlertSummary,
  Briefing,
  UserSummary,
} from '@/types/monitoring';
import type { Cell } from '@/types/regulation';

import { AlertList } from './_components/AlertList';
import { BriefingStrip } from './_components/BriefingStrip';
import { GateStrip } from './_components/GateStrip';

export const dynamic = 'force-dynamic';

/** `unassigned` is a filter, not a severity — an alert of any grade can be nobody's. */
type Tab = AlertSeverity | 'all' | 'unassigned';

const TABS: readonly Tab[] = ['all', ...ALERT_SEVERITY_ORDER, 'unassigned'] as const;

const TAB_LABEL: Record<Tab, string> = {
  all: '전체',
  high: ALERT_SEVERITY_LABEL.high,
  medium: ALERT_SEVERITY_LABEL.medium,
  low: ALERT_SEVERITY_LABEL.low,
  unassigned: '담당자 미지정',
};

/**
 * The change feed — phase 1.4's alerts, read in the cell the ScopeBar selects.
 *
 * Three shapes here carry the ADR rather than the layout:
 *
 * - **The cell comes from the ScopeBar, never from this page.** Subscription matching is on cell
 *   and only on cell (ADR-0009 decision 5), because until the Product context exists an IR applies
 *   to a cell (ADR-0007). A per-page picker would imply the routing is finer than it is.
 * - **One amendment is one row.** The list is alerts, not change events: 109 events over the gated
 *   corpus compose 7 alerts, and rendering the events would bury 37 real edits under a thousand
 *   empty ones — the exact failure ADR-0002 decision 7 exists to prevent, reintroduced at the last
 *   step.
 * - **The gates sit above the list, not on an admin page.** Neither is self-guarding: a system that
 *   alerted on everything would score perfectly on coverage. The numbers that guard them belong in
 *   front of the people acting on the alerts.
 */
export default async function MonitoringPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; page?: string; unassigned?: string }>;
}) {
  const query = await searchParams;
  const page = Math.max(1, Number(query.page ?? '1') || 1);
  const tab = normalizeTab(query.unassigned === 'true' ? 'unassigned' : query.tab);
  const scope = await readScope();

  if (!scope) {
    return (
      <EmptyState
        title="셀을 선택하세요"
        hint="상단 ScopeBar에서 셀을 고르면 그 셀에서 감지된 개정만 표시됩니다. 알림 라우팅은 셀 단위입니다 — 제품별 영향 판단은 Phase 2입니다."
      />
    );
  }

  const cells = await serverGet<Cell[]>('regulation', '/cells');
  const cell = cells?.find((candidate) => candidate.slug === scope);
  if (!cell) {
    return <EmptyState title={`알 수 없는 셀: ${scope}`} hint="ScopeBar에서 다시 선택하세요." />;
  }

  // Independent fetches — a failed briefing read must not blank the feed, and vice versa
  // (frontend-page skill: no `Promise.all` for unrelated resources).
  const briefing = await serverGet<Briefing>('monitoring', '/briefing');
  const metrics = await serverGet<AlertMetrics>('monitoring', '/metrics/alerts');
  const listing = await serverGetPage<AlertSummary[]>('monitoring', '/alerts', {
    cell_id: cell.id,
    severity: tab === 'all' || tab === 'unassigned' ? undefined : [tab],
    unassigned: tab === 'unassigned' ? true : undefined,
    page,
    page_size: ALERT_PAGE_SIZE,
  });

  const alerts = listing?.data ?? [];
  const total = listing?.meta?.total ?? 0;
  const pageSize = listing?.meta?.page_size ?? ALERT_PAGE_SIZE;
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const cellMetrics = metrics?.cells.find((row) => row.cell === cell.slug);

  // Owner ids render as people, not UUIDs. A failed read leaves the ids — the fallback copy says
  // "담당자 지정됨" rather than showing a raw UUID nobody can act on.
  const users = await serverGet<UserSummary[]>('platform-core', '/users', { page_size: 200 });
  const owners = Object.fromEntries((users ?? []).map((user) => [user.id, user.email]));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">변경 모니터링</h1>
          <p className="mt-1 text-xs text-slate-500">
            개정 하나가 알림 하나입니다 — 40개 조문이 바뀌어도 알림은 하나이고 그 안에 조문 40건이
            들어 있습니다. 조번호만 바뀐 개정은 알림을 만들지 않습니다.
          </p>
        </div>
        <Link
          href="/monitoring/subscriptions"
          className="rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-slate-500"
        >
          구독 설정
        </Link>
      </div>

      {briefing ? <BriefingStrip briefing={briefing} /> : null}
      {cellMetrics ? <GateStrip metrics={cellMetrics} /> : null}

      <nav className="flex flex-wrap gap-1.5 border-b border-surface-border pb-3">
        {TABS.map((candidate) => {
          const active = candidate === tab;
          const style =
            candidate === 'all' || candidate === 'unassigned'
              ? 'border-accent text-slate-100'
              : (ALERT_SEVERITY_STYLE[candidate] ?? 'border-accent text-slate-100');
          return (
            <Link
              key={candidate}
              href={`/monitoring?tab=${candidate}`}
              className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                active
                  ? style
                  : 'border-surface-border text-slate-400 hover:border-slate-600 hover:text-slate-200'
              }`}
            >
              {TAB_LABEL[candidate]}
            </Link>
          );
        })}
      </nav>

      {listing === null ? (
        <EmptyState
          title="알림 목록을 불러오지 못했습니다"
          hint="monitoring 서비스 상태를 확인하세요."
        />
      ) : alerts.length === 0 ? (
        <EmptyState title={emptyTitle(tab)} hint={emptyHint(tab, cellMetrics?.subscribers ?? 0)} />
      ) : (
        <AlertList alerts={alerts} owners={owners} />
      )}

      {total > pageSize ? (
        <nav className="flex items-center justify-between border-t border-surface-border pt-4 text-xs text-slate-500">
          <span className="font-mono">
            {first.toLocaleString()}–{last.toLocaleString()} / {total.toLocaleString()}
          </span>
          <span className="flex gap-4">
            {page > 1 ? (
              <Link
                href={`/monitoring?tab=${tab}&page=${page - 1}`}
                className="text-accent hover:underline"
              >
                이전
              </Link>
            ) : null}
            {last < total ? (
              <Link
                href={`/monitoring?tab=${tab}&page=${page + 1}`}
                className="text-accent hover:underline"
              >
                다음
              </Link>
            ) : null}
          </span>
        </nav>
      ) : null}
    </div>
  );
}

/** An unrecognised tab falls back to `all` rather than to an empty filter nobody chose. */
function normalizeTab(value: string | undefined): Tab {
  return (TABS as readonly string[]).includes(value ?? '') ? (value as Tab) : 'all';
}

/** "Nothing here" has several meanings, and most of them are good news. */
function emptyTitle(tab: Tab): string {
  switch (tab) {
    case 'unassigned':
      return '담당자가 지정되지 않은 알림이 없습니다';
    case 'high':
      return '높음 등급 알림이 없습니다';
    default:
      return '이 셀에서 감지된 개정이 없습니다';
  }
}

/**
 * An empty feed and an unsubscribed cell look identical, and only one of them is a problem. The
 * subscriber count is what tells them apart, so it decides the hint.
 */
function emptyHint(tab: Tab, subscribers: number): string | undefined {
  if (tab === 'unassigned') {
    return '모든 알림에 담당자가 지정되어 있습니다.';
  }
  if (subscribers === 0) {
    return '이 셀을 구독한 사람이 없어 알림이 만들어지지 않습니다. 구독 설정에서 이 셀을 구독하세요 — 감지 자체는 계속 이루어지고 있습니다.';
  }
  return '수집 주기마다 개정을 확인하고 있습니다. 조번호만 바뀐 개정은 실질 개정이 아니므로 알림을 만들지 않습니다.';
}
