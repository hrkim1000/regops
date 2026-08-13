import { ArrowRight, ExternalLink } from 'lucide-react';
import Link from 'next/link';

import {
  CHANGE_KIND_LABEL,
  CHANGE_KIND_STYLE,
  MATCH_BASIS_LABEL,
  NON_SUBSTANTIVE_CHANGE_KINDS,
} from '@/types/constants';
import type { ClauseDiff } from '@/types/monitoring';

/**
 * What actually changed, clause by clause, old text beside new.
 *
 * **A renumber renders as a move, never as a delete beside an add** (ADR-0002 decision 7). MFDS 고시
 * renumber routinely, and the pair would be two false alerts about the same untouched provision —
 * so the row shows 제7조 → 제9조 with one body of text, and says which of the two signals paired
 * them. A move stated by the authority in 조문이동이전/이후 and one inferred from text similarity
 * carry very different confidence, and `needs_review` marks the ones nobody has checked; rendering
 * all three alike would present a guess as a fact.
 *
 * Non-substantive kinds are muted rather than hidden. An amendment made *only* of them raises no
 * alert at all, but a mixed one still has to show them — otherwise the clause count on the alert
 * would not add up, and a reader would be left wondering what the missing rows were.
 */
export function ClauseDiffList({
  diffs,
  documentId,
  versionId,
  fromVersionId,
}: {
  diffs: ClauseDiff[];
  documentId: string;
  versionId: string;
  fromVersionId: string | null;
}) {
  return (
    <ul className="space-y-3">
      {diffs.map((diff) => {
        const muted = (NON_SUBSTANTIVE_CHANGE_KINDS as readonly string[]).includes(
          diff.change_kind,
        );
        return (
          <li
            key={diff.id}
            className={`rounded-lg border border-surface-border bg-surface-raised/40 p-4 ${
              muted ? 'opacity-60' : ''
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] ${
                  CHANGE_KIND_STYLE[diff.change_kind] ?? ''
                }`}
              >
                {CHANGE_KIND_LABEL[diff.change_kind] ?? diff.change_kind}
              </span>

              <span className="inline-flex items-center gap-1.5 font-mono text-xs text-slate-300">
                {diff.from_clause_path ? (
                  <>
                    <span className="text-slate-500">{diff.from_clause_path}</span>
                    <ArrowRight size={11} className="text-slate-600" />
                  </>
                ) : null}
                {diff.clause_path}
              </span>

              {diff.match_basis ? (
                <span className="text-[11px] text-slate-600">
                  {MATCH_BASIS_LABEL[diff.match_basis] ?? diff.match_basis}
                  {diff.similarity !== null ? ` ${(diff.similarity * 100).toFixed(0)}%` : ''}
                </span>
              ) : null}

              {diff.needs_review ? (
                <span className="rounded border border-amber-700 bg-amber-950/50 px-1.5 py-0.5 text-[10px] text-amber-300">
                  확인 필요 — 유사도로 추정한 연결입니다
                </span>
              ) : null}

              <Link
                href={`/regulations/${documentId}/versions/${versionId}/clauses?clause_path=${encodeURIComponent(
                  diff.clause_path,
                )}`}
                className="ml-auto inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
              >
                조문 보기 <ExternalLink size={10} />
              </Link>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <Side
                label="개정 전"
                side={diff.from}
                documentId={documentId}
                versionId={fromVersionId}
                absent="이 개정에서 신설된 조문입니다"
              />
              <Side
                label="개정 후"
                side={diff.to}
                documentId={documentId}
                versionId={versionId}
                absent="이 개정에서 삭제된 조문입니다"
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Side({
  label,
  side,
  documentId,
  versionId,
  absent,
}: {
  label: string;
  side: ClauseDiff['from'];
  documentId: string;
  versionId: string | null;
  absent: string;
}) {
  return (
    <div className="rounded-md border border-surface-border bg-surface px-3 py-2">
      <p className="font-mono text-[10px] uppercase tracking-wide text-slate-600">{label}</p>
      {side === null ? (
        <p className="mt-1.5 text-[11px] text-slate-600">{absent}</p>
      ) : (
        <>
          {side.heading ? (
            <p className="mt-1.5 text-xs font-medium text-slate-300">{side.heading}</p>
          ) : null}
          <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-slate-400">
            {side.text || '(본문 없음)'}
          </p>
          {side.truncated ? (
            // Never let a shortened clause be read as the whole one — 별표 1 holds single clauses
            // of 340 KB, and a conclusion drawn from text that was cut away is the worst outcome.
            <p className="mt-1.5 text-[11px] text-amber-400/80">
              본문이 길어 일부만 표시했습니다 —{' '}
              {versionId ? (
                <Link
                  href={`/regulations/${documentId}/versions/${versionId}/clauses?clause_path=${encodeURIComponent(
                    side.clause_path,
                  )}`}
                  className="underline"
                >
                  전문 보기
                </Link>
              ) : (
                '조문 보기에서 전문을 확인하세요'
              )}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
