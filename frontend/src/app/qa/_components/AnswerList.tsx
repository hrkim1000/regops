import { AlertTriangle, CalendarClock, History } from 'lucide-react';
import Link from 'next/link';

import { formatDate, formatDateTime } from '@/lib/format';
import {
  ANSWER_STATUS_LABEL,
  ANSWER_STATUS_STYLE,
  NO_ANSWER_REASON_LABEL,
} from '@/types/constants';
import type { AnswerSummary } from '@/types/answer';

/**
 * The answer log, newest first.
 *
 * Every row carries the three facts that decide whether it can be relied on, and none of them is
 * behind a click: what it concluded (status), how sure the system was (confidence), and whether its
 * evidence has since moved (superseded). A list that showed only the status would let a superseded
 * answer read exactly like a current one.
 */
export function AnswerList({ answers }: { answers: AnswerSummary[] }) {
  return (
    <ul className="space-y-2">
      {answers.map((answer) => (
        <li key={answer.id}>
          <Link
            href={`/qa/${answer.id}`}
            className="block rounded-lg border border-surface-border bg-surface-raised/40 px-4 py-3 transition-colors hover:border-slate-600"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] ${
                  ANSWER_STATUS_STYLE[answer.status] ?? ''
                }`}
              >
                {ANSWER_STATUS_LABEL[answer.status] ?? answer.status}
              </span>

              {answer.superseded_at ? (
                <span className="inline-flex items-center gap-1 rounded border border-amber-700 bg-amber-950/50 px-1.5 py-0.5 text-[10px] text-amber-300">
                  <History size={10} /> 근거 개정됨 {answer.superseded_citation_count}/
                  {answer.citation_count}
                </span>
              ) : null}

              {answer.straddles_effective_date ? (
                <span className="inline-flex items-center gap-1 rounded border border-amber-700 bg-amber-950/50 px-1.5 py-0.5 text-[10px] text-amber-300">
                  <AlertTriangle size={10} /> 시행일 혼재
                </span>
              ) : null}

              <span className="ml-auto font-mono text-[11px] text-slate-500">
                신뢰도 {answer.confidence.toFixed(2)}
              </span>
            </div>

            <p className="mt-2 text-xs text-slate-500">
              {answer.no_answer_reason
                ? (NO_ANSWER_REASON_LABEL[answer.no_answer_reason] ?? answer.no_answer_reason)
                : `근거 조문 ${answer.citation_count}건`}
            </p>

            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-slate-600">
              <span className="inline-flex items-center gap-1">
                <CalendarClock size={11} />
                {answer.effective_date_scope ? formatDate(answer.effective_date_scope) : '시행일 —'}
              </span>
              <span>{formatDateTime(answer.created_at)}</span>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
