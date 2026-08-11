import { clsx } from 'clsx';
import { AlertTriangle, Link2 } from 'lucide-react';
import Link from 'next/link';

import { formatDate, formatDateTime } from '@/lib/format';
import {
  IR_STATUS_LABEL,
  IR_STATUS_STYLE,
  IR_TAXONOMY_LABEL,
} from '@/types/constants';
import type { IR, IRCitation } from '@/types/ir';

import { LockButton } from './LockButton';

/**
 * One atomic obligation per row: **one bearer + one modal + one required action** (ADR-0004
 * decision 1).
 *
 * The reading order is deliberate — *what does this require · on what authority · who said so* —
 * and the middle term is never optional. An IR without a citation cannot exist (decision 2), so an
 * empty citation list is rendered as a loud defect rather than an empty area: if one ever appears
 * here, the database's own guard has been bypassed and that is worth seeing.
 */
export function IRList({ irs, canLock }: { irs: IR[]; canLock: boolean }) {
  return (
    <ol className="space-y-3">
      {irs.map((ir) => (
        <IRCard key={ir.id} ir={ir} canLock={canLock} />
      ))}
    </ol>
  );
}

function IRCard({ ir, canLock }: { ir: IR; canLock: boolean }) {
  return (
    <li
      id={ir.id}
      className={clsx(
        'scroll-mt-24 rounded-lg border bg-surface-raised/40 p-4',
        // A draft is a proposal and a stale IR is work; both are marked at the edge so a reader
        // skimming the list never mistakes either for a settled obligation.
        ir.status === 'draft' && 'border-l-2 border-l-sky-700 border-surface-border',
        ir.status === 'stale' && 'border-l-2 border-l-amber-600 border-surface-border',
        ir.status !== 'draft' && ir.status !== 'stale' && 'border-surface-border',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200">
            {ir.statement}
          </p>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
            {ir.bearer ? (
              <span>
                <span className="text-slate-600">주체</span>{' '}
                <span className="text-slate-400">{ir.bearer}</span>
              </span>
            ) : null}
            {ir.modal ? (
              // The modal is shown verbatim from the closed inventory — it is what makes the
              // obligation an obligation, not decoration.
              <span className="rounded border border-surface-border px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                {ir.modal}
              </span>
            ) : null}
            {ir.taxonomy_code ? (
              <span className="rounded border border-surface-border px-1.5 py-0.5 text-[10px] text-slate-400">
                {IR_TAXONOMY_LABEL[ir.taxonomy_code] ?? ir.taxonomy_code}
              </span>
            ) : null}
            <span className="font-mono text-[10px] text-slate-600">{ir.domain_profile}</span>
          </div>
        </div>

        <div className="flex shrink-0 items-start gap-2">
          <span
            className={clsx(
              'rounded border px-1.5 py-0.5 text-[10px]',
              IR_STATUS_STYLE[ir.status] ?? '',
            )}
            title={
              ir.visible_downstream
                ? '확정됨 — 답변 생성·영향 등급·갭 분석에 사용됩니다'
                : '확정 전 — 답변 생성·영향 등급·갭 분석에서 보이지 않습니다'
            }
          >
            {IR_STATUS_LABEL[ir.status] ?? ir.status}
          </span>
          {canLock && ir.status === 'draft' ? <LockButton irId={ir.id} /> : null}
        </div>
      </div>

      {/* The class/category restriction lives here on one IR, not fanned out per class
          (ADR-0017 decision 2), so it is scope information a reader must not skip. */}
      {ir.condition_text ? (
        <p className="mt-2 rounded border border-surface-border bg-surface-raised/60 px-2.5 py-1.5 text-xs text-slate-400">
          <span className="text-[10px] uppercase tracking-wide text-slate-600">적용 조건</span>{' '}
          {ir.condition_text}
        </p>
      ) : null}

      <Citations citations={ir.citations} />

      {ir.status === 'stale' ? (
        <p className="mt-2 flex items-start gap-1.5 text-[11px] text-amber-300/90">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          인용 조문이 개정되었습니다 ({formatDateTime(ir.stale_since)}). 재추출이 새 IR을 만들고 이
          IR은 그대로 보존됩니다 — 제자리에서 수정되지 않습니다.
        </p>
      ) : null}

      <Provenance ir={ir} />
    </li>
  );
}

/**
 * The evidence. Every link resolves through the citation's **own** `document_id` /
 * `document_version_id`, never through the page's route params — a citation is pinned to an
 * immutable version, and a superseded one points at an older version whose text is the thing that
 * was actually cited. Following it has to land there.
 */
function Citations({ citations }: { citations: IRCitation[] }) {
  if (citations.length === 0) {
    return (
      <p className="mt-2 rounded border border-red-800 bg-red-950/40 px-2.5 py-1.5 text-[11px] text-red-300">
        인용이 없습니다 — 인용 없는 IR은 존재할 수 없습니다 (ADR-0004 결정 2). 데이터베이스 제약이
        우회된 상태이므로 결함으로 보고하세요.
      </p>
    );
  }

  return (
    <ul className="mt-2 flex flex-wrap gap-1.5">
      {citations.map((citation) => (
        <li key={`${citation.document_version_id}:${citation.clause_path}`}>
          <Link
            href={`/regulations/${citation.document_id}/versions/${citation.document_version_id}/clauses#${encodeURIComponent(citation.clause_path)}`}
            title={
              citation.superseded_at
                ? `이 인용이 가리키는 버전은 ${formatDateTime(citation.superseded_at)}에 개정되었습니다 — 링크는 인용 당시의 원문으로 갑니다`
                : '인용된 조문으로 이동'
            }
            className={clsx(
              'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] transition-colors',
              citation.superseded_at
                ? 'border-amber-800 bg-amber-950/30 text-amber-300 hover:border-amber-600'
                : 'border-surface-border text-slate-400 hover:border-slate-500 hover:text-slate-200',
            )}
          >
            <Link2 size={11} />
            {citation.clause_path}
            {citation.effective_date ? (
              <span className="text-slate-600">@{formatDate(citation.effective_date)}</span>
            ) : null}
            {citation.superseded_at ? <span className="not-italic">·개정됨</span> : null}
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * Who said so. Not diagnostics: an obligation asserted by a model and never reviewed is the artefact
 * an auditor asks about first (ADR-0004 decision 4), so what produced it travels with it.
 */
function Provenance({ ir }: { ir: IR }) {
  const { llm_provider, llm_model, rule_version, prompt_version } = ir.provenance;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-surface-border pt-2 font-mono text-[10px] text-slate-600">
      <span>
        {llm_provider ?? '?'}/{llm_model ?? '?'}
      </span>
      <span>rule {rule_version ?? '?'}</span>
      <span>prompt {prompt_version ?? '?'}</span>
      {ir.locked_at ? <span className="text-emerald-500/70">확정 {formatDateTime(ir.locked_at)}</span> : null}
      {ir.supersedes_ir_id ? (
        <a href={`#${ir.supersedes_ir_id}`} className="text-accent hover:underline">
          이전 IR 대체
        </a>
      ) : null}
    </div>
  );
}
