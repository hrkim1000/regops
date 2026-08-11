import { clsx } from 'clsx';

import { EXCLUSION_REASON_DEFECT, EXCLUSION_REASON_LABEL } from '@/types/constants';
import type { DomainCoverage } from '@/types/ir';

/**
 * *Was every clause examined?* — ADR-0004 decision 6, rendered as a number rather than an assumption.
 *
 * Two things this panel exists to make impossible to miss:
 *
 * - **`unclassified` is shown even when it is zero.** "2 IRs from 29 clauses" cannot be told apart
 *   from 27 missed obligations unless the remainder is on record as examined-and-empty. A coverage
 *   figure that only appears when it is bad teaches a reader to assume it is fine.
 * - **The exclusion reasons are broken out.** A single "27 excluded" count is opaque; the split is
 *   what makes the claim auditable, and it is where a regression shows first — `unparseable` is a
 *   *defect signal*, not a verdict, so it is styled apart from the ten legitimate reasons.
 */
export function CoveragePanel({ coverage }: { coverage: DomainCoverage }) {
  const { clauses, classified, unclassified, obligation_bearing, excluded, complete } = coverage;
  const pct = clauses === 0 ? 0 : Math.round((classified / clauses) * 100);

  return (
    <section className="rounded-lg border border-surface-border bg-surface-raised/40 p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-xs uppercase tracking-wide text-slate-500">분류 커버리지</h2>
        <span className="font-mono text-[11px] text-slate-500">{coverage.domain}</span>
        <span
          className={clsx(
            'rounded border px-1.5 py-0.5 text-[10px]',
            complete
              ? 'border-emerald-800 bg-emerald-950/50 text-emerald-300'
              : 'border-red-800 bg-red-950/40 text-red-300',
          )}
        >
          {complete ? '전 조문 검토됨' : `미분류 ${unclassified.toLocaleString()}건`}
        </span>
      </div>

      <p className="mt-2 text-[11px] text-slate-600">
        모든 조문은 <em className="not-italic text-slate-400">의무 보유</em> 또는{' '}
        <em className="not-italic text-slate-400">사유가 붙은 제외</em> 중 하나입니다. 건너뛴 조문이
        없다는 것이 커버리지 주장의 근거입니다 — 미분류가 0이 아니면 그것이 곧 결함입니다.
      </p>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-border">
        <div
          className={clsx('h-full', complete ? 'bg-emerald-600' : 'bg-red-600')}
          style={{ width: `${pct}%` }}
        />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <Stat label="조문" value={clauses} />
        <Stat label="의무 보유" value={obligation_bearing} />
        <Stat label="제외" value={excluded} />
        <Stat label="미분류" value={unclassified} alarm={unclassified > 0} />
      </dl>

      {excluded > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-1.5 border-t border-surface-border pt-3">
          {Object.entries(coverage.exclusion_reasons)
            .sort(([, a], [, b]) => b - a)
            .map(([reason, count]) => {
              const defect = reason === EXCLUSION_REASON_DEFECT;
              return (
                <li
                  key={reason}
                  title={
                    defect
                      ? '에이전트가 사용 가능한 응답을 내지 못했습니다 — 판정이 아니라 결함 신호입니다'
                      : undefined
                  }
                  className={clsx(
                    'rounded border px-1.5 py-0.5 text-[11px]',
                    defect
                      ? 'border-red-800 bg-red-950/40 text-red-300'
                      : 'border-surface-border text-slate-400',
                  )}
                >
                  {EXCLUSION_REASON_LABEL[reason] ?? reason}
                  <span className="ml-1.5 font-mono text-[10px] text-slate-500">{count}</span>
                </li>
              );
            })}
        </ul>
      ) : null}
    </section>
  );
}

function Stat({ label, value, alarm }: { label: string; value: number; alarm?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd
        className={clsx(
          'mt-0.5 font-mono text-sm',
          alarm ? 'text-red-300' : 'text-slate-200',
        )}
      >
        {value.toLocaleString()}
      </dd>
    </div>
  );
}
