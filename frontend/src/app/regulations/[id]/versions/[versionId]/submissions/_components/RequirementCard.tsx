import { clsx } from 'clsx';
import { AlertTriangle, CornerDownRight, FileSignature, Link2, Send } from 'lucide-react';
import Link from 'next/link';

import { CAVEAT_LABEL } from '@/types/constants';
import type { RequiredDocument, SubmissionRequirement } from '@/types/submission';

/**
 * One procedure and what it requires filed.
 *
 * The design constraint that shapes everything here: **this must not look like a checklist.**
 * 94% of these procedures carry a caveat, and a conditional list rendered with tickboxes would
 * manufacture the exact compliance error the product exists to find. So:
 *
 * - there are no checkboxes, and the items are an ordered list of *provisions*, not tasks
 * - the caveat banner sits **above** the items, not under them
 * - a conditional item is marked at its left edge and states its condition inline — it cannot be
 *   read without also reading that it is conditional
 * - every item links to its own clause, because the item *is* a clause
 */
export function RequirementCard({
  requirement,
  documentId,
  versionId,
}: {
  requirement: SubmissionRequirement;
  documentId: string;
  versionId: string;
}) {
  return (
    <li className="rounded-lg border border-surface-border bg-surface-raised/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-slate-100">
            {requirement.heading ?? '제출 절차'}
          </h3>
          <ClauseLink
            documentId={documentId}
            versionId={versionId}
            clausePath={requirement.clause_path}
            className="mt-0.5"
          />
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 text-[11px]">
          {requirement.form_reference ? (
            <span
              className="inline-flex items-center gap-1 rounded border border-surface-border px-1.5 py-0.5 text-slate-300"
              title="조문이 쓴 그대로입니다 — 문서로 해소하지 않았습니다 (교차참조는 phase 2.1)"
            >
              <FileSignature size={11} /> {requirement.form_reference}
            </span>
          ) : null}
          {requirement.recipient ? (
            <span className="inline-flex items-center gap-1 rounded border border-surface-border px-1.5 py-0.5 text-slate-300">
              <Send size={11} /> {requirement.recipient}
            </span>
          ) : null}
        </div>
      </div>

      <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-400">
        {requirement.text}
      </p>

      <Caveats requirement={requirement} />

      {requirement.documents.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          이 조문의 항목이 자식 조문으로 파싱되지 않았습니다 — 위 본문에서 직접 확인하세요.
        </p>
      ) : (
        <ol className="mt-3 space-y-2">
          {requirement.documents.map((document) => (
            <DocumentRow
              key={document.clause_id}
              document={document}
              documentId={documentId}
              versionId={versionId}
            />
          ))}
        </ol>
      )}
    </li>
  );
}

/**
 * Above the items, deliberately. A caveat rendered below a list is read after the reader has
 * already decided what the list says.
 */
function Caveats({ requirement }: { requirement: SubmissionRequirement }) {
  if (requirement.is_definitive) {
    return (
      <p className="mt-3 rounded border border-emerald-900/60 bg-emerald-950/20 px-2.5 py-1.5 text-[11px] text-emerald-300/90">
        조건·위임·교차참조가 확인되지 않았습니다 — 이 조문이 진술하는 목록은 그대로입니다.
      </p>
    );
  }
  return (
    <ul className="mt-3 space-y-1 rounded border border-amber-800/60 bg-amber-950/20 p-2.5">
      {requirement.caveats.map((caveat) => (
        <li key={caveat.code} className="flex items-start gap-1.5 text-[11px] text-amber-300/90">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          {CAVEAT_LABEL[caveat.code] ?? caveat.meaning}
        </li>
      ))}
    </ul>
  );
}

function DocumentRow({
  document,
  documentId,
  versionId,
}: {
  document: RequiredDocument;
  documentId: string;
  versionId: string;
}) {
  return (
    <li
      className={clsx(
        'rounded border-l-2 bg-surface-raised/40 py-1.5 pl-3 pr-2',
        // A conditional item is marked where the eye enters the row, so it cannot be read as a
        // flat requirement and then qualified afterwards.
        document.conditional ? 'border-l-amber-600' : 'border-l-surface-border',
      )}
    >
      <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-200">
        {document.text}
      </p>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        <ClauseLink
          documentId={documentId}
          versionId={versionId}
          clausePath={document.clause_path}
        />
        {document.conditional ? (
          <span className="text-[11px] text-amber-300/90">
            조건부{document.condition_text ? ` — ${document.condition_text}` : ''}
          </span>
        ) : null}
        {document.delegates ? (
          <span className="text-[11px] text-amber-300/90">하위법령 위임 — 내용은 다른 곳에</span>
        ) : null}
        {document.has_sub_items ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
            <CornerDownRight size={11} />
            하위 항목 {document.sub_item_paths.length || '있음'}
          </span>
        ) : null}
      </div>
    </li>
  );
}

/**
 * The address a reader would cite, linked to the clause itself.
 *
 * Anchored on `clause_path`, which is what the clause view uses as its element id — so following
 * this lands on the provision rather than on the top of a 500-clause page.
 */
function ClauseLink({
  documentId,
  versionId,
  clausePath,
  className,
}: {
  documentId: string;
  versionId: string;
  clausePath: string;
  className?: string;
}) {
  return (
    <Link
      href={`/regulations/${documentId}/versions/${versionId}/clauses#${encodeURIComponent(clausePath)}`}
      className={clsx(
        'inline-flex items-center gap-1 font-mono text-[11px] text-slate-500 hover:text-accent hover:underline',
        className,
      )}
    >
      <Link2 size={11} />
      {clausePath}
    </Link>
  );
}
