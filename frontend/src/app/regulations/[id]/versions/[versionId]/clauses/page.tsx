import { ChevronLeft, ChevronRight, ClipboardList, FileCode, Scale } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { formatDate } from '@/lib/format';
import { serverGet, serverGetPage } from '@/lib/server-api';
import {
  CLAUSE_PAGE_SIZE,
  VERSION_STATUS_LABEL,
  VERSION_STATUS_STYLE,
} from '@/types/constants';
import type { ClauseListing, VersionDetail } from '@/types/regulation';

import { ClauseList } from './_components/ClauseList';

export const dynamic = 'force-dynamic';

/**
 * The parse output of one archived version — phase 1.1's clause store, read.
 *
 * The counterpart of the raw viewer next door: that page renders the bytes the authority sent,
 * this one renders what the parser made of them. Keeping both reachable is what makes a parse
 * defect visible, which is how the 별표 identity collision was found in the first place.
 *
 * The version's own status (시행중 / 시행예정 / 지난 버전) is fetched separately and shown here on
 * purpose: clause text read out of that context is exactly how not-yet-in-force provisions get
 * mistaken for current law.
 */
export default async function ClausesPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; versionId: string }>;
  searchParams: Promise<{ page?: string; clause_path?: string }>;
}) {
  const { id, versionId } = await params;
  const query = await searchParams;
  const page = Math.max(1, Number(query.page ?? '1') || 1);
  //: An answer citation links here by clause, not by page. The API resolves the path to whichever
  //: page holds it — the largest version in the corpus is five pages long, and a "deep link" that
  //: lands on page one is a link to the document rather than to the evidence.
  const focusPath = query.clause_path?.trim() || undefined;

  // Independent fetches — a failed status lookup must not blank the clauses, and vice versa.
  const listing = await serverGetPage<ClauseListing>(
    'regulation',
    `/document-versions/${versionId}/clauses`,
    { page, page_size: CLAUSE_PAGE_SIZE, clause_path: focusPath },
  );
  const version = await serverGet<VersionDetail>('regulation', `/document-versions/${versionId}`);

  if (!listing?.data) return <EmptyState title="버전을 찾을 수 없습니다" />;

  const { clauses, document, parseable } = listing.data;
  const total = listing.meta?.total ?? 0;
  const pageSize = listing.meta?.page_size ?? CLAUSE_PAGE_SIZE;
  //: The API may have moved us: `clause_path` overrides `page`, so the pagination footer has to
  //: follow `meta.page` rather than what the URL asked for, or "다음" would jump back.
  const current = listing.meta?.page ?? page;
  const first = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const last = Math.min(current * pageSize, total);
  const hasNext = last < total;
  //: Asked for a clause this version does not contain — a citation into a *different* version.
  //: Saying so beats scrolling to an anchor that is not on the page.
  const focusMissed = Boolean(focusPath) && !listing.data.focus_clause_path;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={`/regulations/${id}`}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        >
          <ChevronLeft size={13} /> {document?.title ?? '문서'}
        </Link>
        <h1 className="mt-2 text-lg font-semibold text-slate-100">
          {document?.title ?? '조문'}
          {listing.data.version.version_label ? (
            <span className="ml-2 font-mono text-sm text-slate-500">
              {listing.data.version.version_label}
            </span>
          ) : null}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="font-mono">{document?.canonical_key}</span>
          {version?.status ? (
            <span
              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                VERSION_STATUS_STYLE[version.status] ?? ''
              }`}
            >
              {VERSION_STATUS_LABEL[version.status] ?? version.status}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-4 rounded-lg border border-surface-border bg-surface-raised/40 p-4">
        <dl className="grid flex-1 grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
          <Field label="조문 수" value={total.toLocaleString()} mono />
          <Field label="언어" value={listing.data.version.language} mono />
          <Field
            label="effective_date"
            value={
              listing.data.version.effective_date
                ? formatDate(listing.data.version.effective_date)
                : (listing.data.version.effective_date_phrase ?? '미해석 (1.1)')
            }
            muted={!listing.data.version.effective_date}
            mono
          />
          <Field
            label="parser_version"
            value={listing.data.version.parser_version ?? '—'}
            muted={!listing.data.version.parser_version}
            mono
          />
        </dl>
        <div className="flex flex-wrap items-center gap-4">
          <Link
            href={`/regulations/${id}/versions/${versionId}`}
            className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
          >
            <FileCode size={13} /> 원문 보기
          </Link>
          <Link
            href={`/regulations/${id}/versions/${versionId}/irs`}
            className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
          >
            <Scale size={13} /> IR 보기
          </Link>
          <Link
            href={`/regulations/${id}/versions/${versionId}/submissions`}
            className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
          >
            <ClipboardList size={13} /> 제출 서류
          </Link>
        </div>
      </div>

      {focusMissed ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">
          이 버전에는 <span className="font-mono">{focusPath}</span> 조문이 없습니다. 인용은 다른
          버전을 가리키고 있을 수 있습니다 — 인용은 불변 버전에 고정되며 재지정되지 않습니다.
        </p>
      ) : null}

      {clauses.length === 0 ? (
        // "This document type has no clauses" and "this version was not parsed" are different
        // answers. An RSS board yields none by design and must not read as an ingestion gap.
        <EmptyState
          title={parseable ? '조문이 없습니다' : '이 문서 유형은 조문을 갖지 않습니다'}
          hint={
            parseable
              ? '파싱이 아직 실행되지 않았거나 드리프트로 중단되었을 수 있습니다.'
              : 'RSS 게시판은 변경 신호이지 규제 본문이 아닙니다 — 고시 본문은 별도 문서로 수집됩니다.'
          }
        />
      ) : (
        <ClauseList clauses={clauses} />
      )}

      {total > pageSize ? (
        <nav className="flex items-center justify-between border-t border-surface-border pt-4 text-xs text-slate-500">
          <span className="font-mono">
            {first.toLocaleString()}–{last.toLocaleString()} / {total.toLocaleString()}
          </span>
          <span className="flex gap-4">
            {current > 1 ? (
              <Link
                href={`/regulations/${id}/versions/${versionId}/clauses?page=${current - 1}`}
                className="inline-flex items-center gap-1 text-accent hover:underline"
              >
                <ChevronLeft size={13} /> 이전
              </Link>
            ) : null}
            {hasNext ? (
              <Link
                href={`/regulations/${id}/versions/${versionId}/clauses?page=${current + 1}`}
                className="inline-flex items-center gap-1 text-accent hover:underline"
              >
                다음 <ChevronRight size={13} />
              </Link>
            ) : null}
          </span>
        </nav>
      ) : null}
    </div>
  );
}
