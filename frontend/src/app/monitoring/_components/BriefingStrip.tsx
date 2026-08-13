import { Inbox } from 'lucide-react';
import Link from 'next/link';

import { ALERT_SEVERITY_LABEL, ALERT_SEVERITY_ORDER, ALERT_SEVERITY_STYLE } from '@/types/constants';
import type { Briefing } from '@/types/monitoring';

/**
 * The daily briefing — *"here is what moved in your cells since yesterday"*.
 *
 * Composed on read rather than stored, so it reflects the subscriptions the reader holds *now*
 * rather than the ones a batch job saw at 06:00. The window is a rolling 24 hours: a subscriber may
 * hold cells across authorities in different timezones, so a calendar day would need a boundary
 * that is wrong for at least one of them (phase1.4 deviation 8).
 *
 * `unassigned` leads the counts on purpose. An alert nobody owns is an alert nobody actions, and
 * "who was told to deal with this" is the first question asked after a missed amendment.
 */
export function BriefingStrip({ briefing }: { briefing: Briefing }) {
  const total = briefing.entries.length;

  if (briefing.cells.length === 0) {
    return (
      <section className="rounded-lg border border-dashed border-surface-border bg-surface-raised/40 px-4 py-3">
        <p className="text-xs text-slate-400">구독 중인 셀이 없습니다</p>
        <p className="mt-1 text-[11px] text-slate-600">
          <Link href="/monitoring/subscriptions" className="text-accent hover:underline">
            구독 설정
          </Link>
          에서 셀을 구독하면 그 셀의 개정이 여기에 모입니다. 구독은 셀 단위입니다 — 제품 단위 라우팅은
          Phase 2입니다.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-surface-border bg-surface-raised/40 px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <h2 className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400">
          <Inbox size={12} /> 최근 24시간 브리핑
        </h2>

        <span className="font-mono text-[11px] text-slate-600">
          {briefing.cells.join(' · ')}
        </span>

        {total === 0 ? (
          <span className="text-[11px] text-slate-500">이 기간에 새 개정이 없습니다</span>
        ) : (
          <span className="flex flex-wrap items-center gap-1.5">
            {ALERT_SEVERITY_ORDER.map((severity) => {
              const count = briefing.severity_counts[severity] ?? 0;
              if (count === 0) return null;
              return (
                <span
                  key={severity}
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${ALERT_SEVERITY_STYLE[severity]}`}
                >
                  {ALERT_SEVERITY_LABEL[severity]} {count}
                </span>
              );
            })}
            <span className="ml-1 font-mono text-[11px] text-slate-500">총 {total}건</span>
          </span>
        )}

        {briefing.unassigned > 0 ? (
          <Link
            href="/monitoring?unassigned=true"
            className="ml-auto rounded border border-amber-700 bg-amber-950/50 px-1.5 py-0.5 text-[10px] text-amber-300 hover:border-amber-500"
          >
            담당자 미지정 {briefing.unassigned}건
          </Link>
        ) : null}
      </div>
    </section>
  );
}
