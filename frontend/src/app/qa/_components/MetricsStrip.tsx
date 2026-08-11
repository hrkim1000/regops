import {
  NO_ANSWER_REASON_HINT,
  NO_ANSWER_REASON_LABEL,
  NO_ANSWER_REASON_TONE,
} from '@/types/constants';
import type { AnswerMetrics, NoAnswerReason } from '@/types/answer';

/**
 * A refusal the product is supposed to produce reads plainly; a model regression and an
 * unreachable model both draw the eye, because neither is "근거가 없다" and both need someone to
 * look. Rendering them all the same is how a broken model hides inside an honest-looking rate.
 */
const TONE_STYLE: Record<string, string> = {
  expected: 'text-slate-500',
  regression: 'text-amber-300',
  infrastructure: 'text-red-300',
};

/**
 * The "확인 필요" rate, per domain, beside the counts it comes from — ADR-0006 decision 7.
 *
 * **This is a two-sided signal and the UI has to show both sides.** Near 0% means the confidence
 * threshold is too permissive and the hallucination gate is about to be missed; too high means the
 * product is unusable however honest it is. A single number rendered as "3 unanswered" reads as a
 * defect count, which is exactly the misreading that would drive someone to loosen the threshold.
 *
 * It sits here rather than on an admin page because a system that refuses everything passes both
 * Go/No-Go gates cleanly — so the gates are not self-guarding, and the rate that guards them should
 * be in front of the people asking the questions.
 */
export function MetricsStrip({ metrics }: { metrics: AnswerMetrics }) {
  if (metrics.overall.total === 0) return null;

  const reasons = Object.entries(metrics.reasons) as [NoAnswerReason, number][];

  return (
    <section className="space-y-3 rounded-lg border border-surface-border bg-surface-raised/40 p-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <h2 className="text-xs font-medium text-slate-400">답변 결과 비율</h2>
        <span className="text-[11px] text-slate-600">
          0%에 가까우면 임계값이 느슨하다는 뜻이고, 너무 높으면 제품이 쓸 수 없다는 뜻입니다 — 어느
          쪽으로든 급변하면 회귀로 봅니다
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <RateCard label="전체" block={metrics.overall} />
        {metrics.domains.map((domain) => (
          <RateCard key={domain.domain} label={domain.domain} block={domain} />
        ))}
      </div>

      {reasons.length > 0 ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-surface-border pt-3">
          {reasons.map(([reason, count]) => {
            const tone = NO_ANSWER_REASON_TONE[reason] ?? 'expected';
            return (
              <span
                key={reason}
                className={`text-[11px] ${TONE_STYLE[tone]}`}
                title={NO_ANSWER_REASON_HINT[reason]}
              >
                {NO_ANSWER_REASON_LABEL[reason] ?? reason}
                <span className="ml-1 font-mono">{count}</span>
              </span>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function RateCard({
  label,
  block,
}: {
  label: string;
  block: AnswerMetrics['overall'];
}) {
  return (
    <div className="rounded-md border border-surface-border px-3 py-2">
      <p className="font-mono text-[11px] text-slate-500">{label}</p>
      <p className="mt-1 text-sm text-slate-200">
        확인 필요{' '}
        <span className="font-mono">
          {block.needs_verification_rate === null
            ? '—'
            : `${(block.needs_verification_rate * 100).toFixed(1)}%`}
        </span>
      </p>
      <p className="mt-1 font-mono text-[11px] text-slate-600">
        답변 {block.answered} · 검토 {block.needs_review} · 확인 {block.needs_verification} / 전체{' '}
        {block.total}
      </p>
    </div>
  );
}
