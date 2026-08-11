import { ChevronLeft, ListTree } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { formatDate } from '@/lib/format';
import { serverGet } from '@/lib/server-api';
import { VERSION_STATUS_LABEL, VERSION_STATUS_STYLE } from '@/types/constants';
import type { VersionDetail } from '@/types/regulation';
import type { SubmissionListing } from '@/types/submission';

import { RequirementCard } from './_components/RequirementCard';

export const dynamic = 'force-dynamic';

/**
 * *What has to be filed* for the procedures this version states.
 *
 * Derived from the clause store on every read — nothing is stored, nothing is generated, no LLM is
 * involved. Each required document **is** a clause, so every line on this page carries the address
 * a reader would cite.
 *
 * The page is deliberately not a checklist. Measured over the gated corpus, only 6% of these
 * procedures are unconditional; the rest are qualified by case, defer to another instrument, or
 * take their enabling clause from a different law. Presenting them as tickboxes would turn a
 * conditional obligation into a definitive one — the precise error the gap-analysis pillar exists
 * to find — so the caveats lead and the items read as provisions.
 */
export default async function SubmissionsPage({
  params,
}: {
  params: Promise<{ id: string; versionId: string }>;
}) {
  const { id, versionId } = await params;

  // Independent fetches — a failed status lookup must not blank the requirements.
  const listing = await serverGet<SubmissionListing>(
    'regulation',
    `/document-versions/${versionId}/submission-requirements`,
  );
  const version = await serverGet<VersionDetail>('regulation', `/document-versions/${versionId}`);

  if (!listing) return <EmptyState title="버전을 찾을 수 없습니다" />;

  const { requirements, document } = listing;
  const totalDocuments = requirements.reduce((sum, item) => sum + item.documents.length, 0);
  const definitive = requirements.filter((item) => item.is_definitive).length;

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
          제출 서류
          {listing.version.version_label ? (
            <span className="ml-2 font-mono text-sm text-slate-500">
              {listing.version.version_label}
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
          <span className="font-mono text-slate-600">
            {listing.version.effective_date
              ? formatDate(listing.version.effective_date)
              : (listing.version.effective_date_phrase ?? '시행일 미확정')}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href={`/regulations/${id}/versions/${versionId}/clauses`}
          className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
        >
          <ListTree size={13} /> 조문 보기
        </Link>
        {requirements.length > 0 ? (
          <p className="font-mono text-[11px] text-slate-500">
            절차 {requirements.length} · 서류 항목 {totalDocuments} · 무조건부 {definitive}
          </p>
        ) : null}
      </div>

      {/* Stated once, at the top, before any list is read. The per-requirement caveats say which
          specific reservation applies; this says the reservation is the norm. */}
      {requirements.length > 0 ? (
        <p className="rounded-lg border border-surface-border bg-surface-raised/40 p-3 text-[11px] leading-relaxed text-slate-400">
          이 목록은 <strong className="font-semibold text-slate-300">규정이 무엇을 요구하는지</strong>
          와 그 <strong className="font-semibold text-slate-300">명시된 조건</strong>을 그대로 옮긴
          것입니다. <strong className="font-semibold text-slate-300">어느 조건이 귀사에 적용되는지는
          판단하지 않습니다</strong> — 적용성은 제품 컨텍스트가 필요하고 Compliance(phase 2.2)가
          소유합니다. 각 항목은 자기 조문을 인용하므로 원문에서 직접 확인하세요.
        </p>
      ) : null}

      {requirements.length === 0 ? (
        <EmptyState
          title="이 버전은 제출 서류를 명시하지 않습니다"
          hint="대부분의 규정이 그렇습니다 — 제출 절차는 주로 시행규칙에 있습니다. 누락이 의심되면 조문 보기에서 “다음 각 호”를 확인하세요."
        />
      ) : (
        <ol className="space-y-4">
          {requirements.map((requirement) => (
            <RequirementCard
              key={requirement.clause_id}
              requirement={requirement}
              documentId={id}
              versionId={versionId}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
