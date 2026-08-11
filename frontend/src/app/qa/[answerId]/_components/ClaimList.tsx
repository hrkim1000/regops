import { ExternalLink, History } from 'lucide-react';
import Link from 'next/link';

import { formatDate } from '@/lib/format';
import {
  VERIFICATION_VERDICT_LABEL,
  VERIFICATION_VERDICT_STYLE,
  VERSION_STATUS_LABEL,
} from '@/types/constants';
import type { AnswerCitation, VerificationResult } from '@/types/answer';
import type { VersionDetail } from '@/types/regulation';

/**
 * The evidence, claim by claim — the part of the page that decides whether the answer above it can
 * be relied on.
 *
 * Three things are deliberate:
 *
 * - **A citation is a link to the clause, not to the document.** It carries `clause_path`, which the
 *   clause view resolves to whichever page holds it, and an anchor that scrolls to the line. A
 *   citation the reader cannot open in one click is a citation nobody checks — and an unopened
 *   citation is exactly what the mis-citation hallucination class survives on (ADR-0006 decision 5).
 * - **The version travels with it.** A Citation is pinned to an immutable version, so the link names
 *   that version rather than "current", and it renders identically whichever cell the reader has
 *   selected in the ScopeBar.
 * - **The verdict sits beside the claim it judged.** Verification is per claim; showing one verdict
 *   for the whole answer would hide which sentence is the unsupported one.
 */
export function ClaimList({
  citations,
  verification,
  versions,
}: {
  citations: AnswerCitation[];
  verification: VerificationResult[];
  versions: Record<string, VersionDetail | null>;
}) {
  const byClaim = new Map<number, AnswerCitation[]>();
  for (const citation of citations) {
    const bucket = byClaim.get(citation.claim_index) ?? [];
    bucket.push(citation);
    byClaim.set(citation.claim_index, bucket);
  }
  const verdicts = new Map(verification.map((result) => [result.claim_index, result]));
  //: A claim with a verdict but no citation should be impossible; if one appears it is a defect
  //: worth seeing rather than one worth hiding behind a filter.
  const indices = [...new Set([...byClaim.keys(), ...verdicts.keys()])].sort((a, b) => a - b);

  return (
    <ol className="space-y-3">
      {indices.map((index) => {
        const verdict = verdicts.get(index);
        return (
          <li
            key={index}
            className="rounded-lg border border-surface-border bg-surface-raised/40 p-4"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] text-slate-600">주장 {index + 1}</span>
              {verdict ? (
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${
                    VERIFICATION_VERDICT_STYLE[verdict.verdict] ?? ''
                  }`}
                  title="근거 검증은 질문을 보지 않고 인용 조문만 읽고 판정합니다"
                >
                  {VERIFICATION_VERDICT_LABEL[verdict.verdict] ?? verdict.verdict}
                </span>
              ) : null}
              {verdict?.reason ? (
                <span className="text-[11px] text-slate-500">{verdict.reason}</span>
              ) : null}
              {verdict ? (
                <span className="ml-auto font-mono text-[10px] text-slate-600">
                  {verdict.verifier_provider}/{verdict.verifier_model}
                </span>
              ) : null}
            </div>

            <ul className="mt-3 space-y-2">
              {(byClaim.get(index) ?? []).map((citation) => (
                <Citation
                  key={`${citation.document_version_id}:${citation.clause_path}`}
                  citation={citation}
                  version={versions[citation.document_version_id] ?? null}
                />
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}

function Citation({
  citation,
  version,
}: {
  citation: AnswerCitation;
  version: VersionDetail | null;
}) {
  const href =
    `/regulations/${citation.document_id}/versions/${citation.document_version_id}/clauses` +
    `?clause_path=${encodeURIComponent(citation.clause_path)}#${encodeURIComponent(citation.clause_path)}`;

  return (
    <li>
      <Link
        href={href}
        className="group flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-md border border-surface-border px-3 py-2 transition-colors hover:border-slate-600"
      >
        <span className="text-xs text-slate-300 group-hover:text-slate-100">
          {version?.document?.title ?? '문서'}
        </span>
        <span className="font-mono text-[11px] text-accent">{citation.clause_path}</span>
        {version?.version_label ? (
          <span className="font-mono text-[10px] text-slate-600">{version.version_label}</span>
        ) : null}
        {version?.status ? (
          <span className="text-[10px] text-slate-600">
            {VERSION_STATUS_LABEL[version.status] ?? version.status}
          </span>
        ) : null}
        <span className="font-mono text-[10px] text-slate-600">
          시행일 {citation.effective_date ? formatDate(citation.effective_date) : '—'}
        </span>
        {citation.superseded_at ? (
          <span
            className="inline-flex items-center gap-1 rounded border border-amber-700 bg-amber-950/50 px-1.5 py-0.5 text-[10px] text-amber-300"
            title="이 조문은 이후 개정되었습니다. 인용은 다시 가리키지 않고 그대로 남습니다"
          >
            <History size={10} /> 개정됨
          </span>
        ) : null}
        <ExternalLink
          size={11}
          className="ml-auto shrink-0 text-slate-600 group-hover:text-slate-400"
        />
      </Link>
    </li>
  );
}
