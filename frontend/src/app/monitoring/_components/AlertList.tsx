import { CalendarClock, FileText, Lock, Send, UserCheck } from 'lucide-react';
import Link from 'next/link';

import { formatDateTime } from '@/lib/format';
import {
  ALERT_SEVERITY_LABEL,
  ALERT_SEVERITY_STYLE,
  ALERT_STATUS_LABEL,
  ALERT_STATUS_STYLE,
} from '@/types/constants';
import type { AlertSummary } from '@/types/monitoring';

/**
 * The change feed — one row per amendment, not per clause.
 *
 * **`clause_count` is the dedup made visible.** An amendment touching forty clauses is one alert
 * carrying forty references; forty rows would be the same information delivered as noise, and a
 * subscriber who stops reading the feed fails the coverage gate exactly as surely as a change
 * nobody detected.
 *
 * Every row shows the three facts that decide whether it needs someone today: how much changed,
 * whether a **locked** obligation rested on the text that moved, and whether anyone owns it. The
 * locked-IR badge is the top grading input and the only one carrying a human's prior assertion, so
 * it is on the row rather than behind a click.
 */
export function AlertList({
  alerts,
  owners,
}: {
  alerts: AlertSummary[];
  owners: Record<string, string>;
}) {
  return (
    <ul className="space-y-2">
      {alerts.map((alert) => (
        <li key={alert.id}>
          <Link
            href={`/monitoring/alerts/${alert.id}`}
            className="block rounded-lg border border-surface-border bg-surface-raised/40 px-4 py-3 transition-colors hover:border-slate-600"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] ${
                  ALERT_SEVERITY_STYLE[alert.severity] ?? ''
                }`}
              >
                {ALERT_SEVERITY_LABEL[alert.severity] ?? alert.severity}
              </span>

              {alert.cited_by_locked_ir ? (
                <span className="inline-flex items-center gap-1 rounded border border-red-800 bg-red-950/50 px-1.5 py-0.5 text-[10px] text-red-300">
                  <Lock size={10} /> 확정 요구사항 {alert.locked_ir_count}건 영향
                </span>
              ) : null}

              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] ${
                  ALERT_STATUS_STYLE[alert.status] ?? ''
                }`}
              >
                {ALERT_STATUS_LABEL[alert.status] ?? alert.status}
              </span>

              <span className="ml-auto font-mono text-[11px] text-slate-500">
                조문 {alert.clause_count}건
              </span>
            </div>

            <p className="mt-2 text-sm text-slate-200">{alert.title}</p>

            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-slate-600">
              <span className="inline-flex items-center gap-1">
                <FileText size={11} />
                {alert.document_title || alert.document_id.slice(0, 8)}
              </span>
              <span className="inline-flex items-center gap-1">
                <CalendarClock size={11} />
                {formatDateTime(alert.detected_at)}
              </span>
              <span className="inline-flex items-center gap-1">
                <Send size={11} />
                {alert.delivery.attempts === 0
                  ? '전달 대상 없음'
                  : `전달 ${alert.delivery.sent}/${alert.delivery.attempts}${
                      alert.delivery.failed > 0 ? ` · 실패 ${alert.delivery.failed}` : ''
                    }`}
              </span>
              <span
                className={`inline-flex items-center gap-1 ${
                  alert.owner_id ? '' : 'text-amber-500/80'
                }`}
              >
                <UserCheck size={11} />
                {alert.owner_id ? (owners[alert.owner_id] ?? '담당자 지정됨') : '담당자 미지정'}
              </span>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
