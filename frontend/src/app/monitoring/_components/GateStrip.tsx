import { DETECTION_COVERAGE_TARGET, DETECTION_LATENCY_TARGET_HOURS } from '@/types/constants';
import type { CellMetrics } from '@/types/monitoring';

/**
 * The two Go/No-Go gates this pillar carries, in front of the people the alerts are for.
 *
 * **Neither gate guards itself, which is why both numbers are shown with their denominators.**
 * A system that alerted on everything would score perfectly on coverage, and one that never
 * resolved a publication date could report a latency of zero. So coverage is drawn against the
 * *emitted* event count from the other side of the seam, and latency separates the measurable
 * cases from the ones the authority published no date for.
 *
 * `subscribers` sits beside coverage on purpose: a cell at 0% with nobody subscribed means *nobody
 * asked*, and reading it as a routing failure is the misdiagnosis this column exists to prevent.
 */
export function GateStrip({ metrics }: { metrics: CellMetrics }) {
  const coverage = metrics.coverage;
  const latency = metrics.latency_hours;
  const published = latency.from_published;
  const retrieved = latency.from_retrieved;

  return (
    <section className="space-y-3 rounded-lg border border-surface-border bg-surface-raised/40 p-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <h2 className="text-xs font-medium text-slate-400">탐지 지표</h2>
        <span className="text-[11px] text-slate-600">
          Go/No-Go 게이트 두 개 — 탐지 커버리지 ≥ {(DETECTION_COVERAGE_TARGET * 100).toFixed(0)}% ·
          탐지 지연 ≤ {DETECTION_LATENCY_TARGET_HOURS}시간 (공포 → 알림)
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-md border border-surface-border px-3 py-2">
          <p className="font-mono text-[11px] text-slate-500">탐지 커버리지</p>
          <p className="mt-1 text-sm text-slate-200">
            <span
              className={`font-mono ${
                coverage === null
                  ? 'text-slate-500'
                  : coverage >= DETECTION_COVERAGE_TARGET
                    ? 'text-emerald-300'
                    : 'text-amber-300'
              }`}
            >
              {coverage === null ? '—' : `${(coverage * 100).toFixed(1)}%`}
            </span>
          </p>
          <p className="mt-1 font-mono text-[11px] text-slate-600">
            알림 도달 {metrics.change_events_alerted.toLocaleString()} / 감지{' '}
            {metrics.change_events_emitted.toLocaleString()} · 구독자 {metrics.subscribers}
          </p>
          {metrics.subscribers === 0 ? (
            <p className="mt-1 text-[11px] text-slate-600">
              구독자가 없어 알림이 만들어지지 않습니다 — 라우팅 실패가 아닙니다
            </p>
          ) : null}
        </div>

        <div className="rounded-md border border-surface-border px-3 py-2">
          <p className="font-mono text-[11px] text-slate-500">탐지 지연 (공포 기준)</p>
          <p className="mt-1 text-sm text-slate-200">
            <span className="font-mono">
              {published.max === null ? '—' : `최대 ${published.max.toFixed(1)}h`}
            </span>
          </p>
          <p className="mt-1 font-mono text-[11px] text-slate-600">
            {published.count === 0
              ? '측정 가능한 알림 없음'
              : `${DETECTION_LATENCY_TARGET_HOURS}시간 내 ${published.within_target}/${published.count}`}
          </p>
          {latency.unmeasurable > 0 ? (
            // Not zero, and not hidden: a source that publishes no date makes its own latency
            // unmeasurable, and a gate report has to say so (ADR-0003 decision 5).
            <p className="mt-1 text-[11px] text-slate-600">
              공포일자 미제공 {latency.unmeasurable}건 — 측정 불가 (0시간이 아닙니다)
            </p>
          ) : null}
        </div>

        <div className="rounded-md border border-surface-border px-3 py-2">
          <p className="font-mono text-[11px] text-slate-500">탐지 지연 (수집 기준)</p>
          <p className="mt-1 text-sm text-slate-200">
            <span className="font-mono">
              {retrieved.max === null ? '—' : `최대 ${retrieved.max.toFixed(1)}h`}
            </span>
          </p>
          <p className="mt-1 font-mono text-[11px] text-slate-600">
            우리 시계 기준 상한 · 알림 {metrics.alerts.toLocaleString()}건
          </p>
        </div>
      </div>
    </section>
  );
}
