import { ChevronLeft, ChevronRight, ListTree } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { hasAtLeast, readUserRole } from '@/lib/auth';
import { formatDate } from '@/lib/format';
import { serverGet, serverGetPage } from '@/lib/server-api';
import {
  IR_PAGE_SIZE,
  IR_STATUS_LABEL,
  IR_STATUS_ORDER,
  IR_STATUS_STYLE,
  VERSION_STATUS_LABEL,
  VERSION_STATUS_STYLE,
} from '@/types/constants';
import type { CoverageReport, IR, IRStatus } from '@/types/ir';
import type { VersionDetail } from '@/types/regulation';

import { CoveragePanel } from './_components/CoveragePanel';
import { ExtractButton } from './_components/ExtractButton';
import { IRList } from './_components/IRList';

export const dynamic = 'force-dynamic';

/**
 * The obligations extracted from one version — phase 1.2's IR store, read and reviewed.
 *
 * Three shapes here carry the ADR rather than the layout:
 *
 * - **`locked` is the default filter**, mirroring the API. Drafts are reachable in one click because
 *   this *is* the review queue and hiding them would make locking impossible — but a reader who
 *   lands here without choosing sees only what actually flows downstream (ADR-0004 decision 4).
 *   Anything else would present unreviewed model output as obligations.
 * - **Coverage sits above the list, not below it.** "2 IRs from 29 clauses" is uninterpretable
 *   without the classification ledger beside it; putting the count first and the denominator later
 *   is how a partial extraction reads as a complete one (decision 6).
 * - **Every status is fetched for its count**, independently. Without them the tabs are blind and
 *   "3 drafts awaiting review" — the most actionable fact on the page — is invisible until someone
 *   clicks through looking for it.
 */
export default async function IRsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; versionId: string }>;
  searchParams: Promise<{ status?: string; page?: string }>;
}) {
  const { id, versionId } = await params;
  const query = await searchParams;
  const page = Math.max(1, Number(query.page ?? '1') || 1);
  const status = normalizeStatus(query.status);

  const role = await readUserRole();
  const canWrite = hasAtLeast(role, 'ra');

  // Independent fetches throughout — a failed coverage read must not blank the IR list, and one
  // failed count must not blank the tabs (frontend-page skill: no `Promise.all` for unrelated
  // resources).
  const version = await serverGet<VersionDetail>('regulation', `/document-versions/${versionId}`);
  const coverage = await serverGet<CoverageReport>(
    'regulation',
    `/document-versions/${versionId}/coverage`,
  );
  const listing = await serverGetPage<IR[]>('regulation', `/document-versions/${versionId}/irs`, {
    status: [status],
    page,
    page_size: IR_PAGE_SIZE,
  });

  // The tab counts are the one place `Promise.all` is right here: they are the *same* resource under
  // four filters, and `serverGetPage` returns null rather than throwing — so this cannot reject and
  // one dead probe still renders as a `?` beside its tab instead of taking the other three with it.
  // `page_size=1` because this reads `meta.total`, not the rows.
  // Whether an extraction is in flight is the server's answer, read once here and handed to both
  // consumers. Two components asking the same question independently is how they end up disagreeing
  // on screen — the button saying "추출 중" beside a panel calling the same run's remainder a defect.
  const latestRun = coverage?.latest_run ?? null;
  // `live`, not `status`: a run whose worker died still says `running`, and the server is the only
  // side that can tell — it holds the checkpoint heartbeat. Reading `status` here is what would put
  // "추출 중" on screen for a run that stopped hours ago.
  const running = latestRun?.live === true;

  const probes = await Promise.all(
    IR_STATUS_ORDER.map((candidate) =>
      serverGetPage<IR[]>('regulation', `/document-versions/${versionId}/irs`, {
        status: [candidate],
        page_size: 1,
      }),
    ),
  );
  const counts: Partial<Record<IRStatus, number>> = {};
  IR_STATUS_ORDER.forEach((candidate, index) => {
    const total = probes[index]?.meta?.total;
    if (total !== undefined && total !== null) counts[candidate] = total;
  });

  if (!version) return <EmptyState title="버전을 찾을 수 없습니다" />;

  const irs = listing?.data ?? [];
  const total = listing?.meta?.total ?? 0;
  const pageSize = listing?.meta?.page_size ?? IR_PAGE_SIZE;
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const extracted = Object.values(counts).some((count) => count > 0);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={`/regulations/${id}`}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        >
          <ChevronLeft size={13} /> {version.document?.title ?? '문서'}
        </Link>
        <h1 className="mt-2 text-lg font-semibold text-slate-100">
          IR — 추출된 의무
          {version.version_label ? (
            <span className="ml-2 font-mono text-sm text-slate-500">{version.version_label}</span>
          ) : null}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="font-mono">{version.document?.canonical_key}</span>
          {version.status ? (
            <span
              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                VERSION_STATUS_STYLE[version.status] ?? ''
              }`}
            >
              {VERSION_STATUS_LABEL[version.status] ?? version.status}
            </span>
          ) : null}
          <span className="font-mono text-slate-600">
            {version.effective_date
              ? formatDate(version.effective_date)
              : (version.effective_date_phrase ?? '시행일 미확정')}
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
        {canWrite ? <ExtractButton versionId={versionId} run={latestRun} /> : null}
      </div>

      {coverage === null ? (
        <EmptyState
          title="커버리지를 불러오지 못했습니다"
          hint="IR 목록은 아래에 그대로 표시됩니다 — 분류 원장만 읽지 못한 상태입니다."
        />
      ) : coverage.domains.length === 0 ? (
        // Zero domains means zero classified clauses, which is the same picture at two opposite
        // moments: before anyone ran it, and in the first seconds of a run that has not committed a
        // clause yet. The run tells them apart, so it decides which sentence this is.
        <EmptyState
          title={running ? '추출을 시작했습니다' : '아직 추출이 실행되지 않았습니다'}
          hint={
            running
              ? '조문마다 LLM을 호출하므로 시간이 걸립니다. 워커가 조문 단위로 커밋하므로 결과는 진행되는 대로 나타납니다.'
              : canWrite
                ? '조문마다 LLM을 호출하므로 수집 시 자동 실행되지 않습니다. 위의 “IR 추출 실행”을 누르세요.'
                : '조문마다 LLM을 호출하므로 수집 시 자동 실행되지 않습니다. ra 권한을 가진 사용자가 실행할 수 있습니다.'
          }
        />
      ) : (
        <div className="space-y-3">
          {coverage.domains.map((domain) => (
            <CoveragePanel key={domain.domain} coverage={domain} running={running} />
          ))}
        </div>
      )}

      <nav className="flex flex-wrap gap-1.5 border-b border-surface-border pb-3">
        {IR_STATUS_ORDER.map((candidate) => {
          const active = candidate === status;
          const count = counts[candidate];
          return (
            <Link
              key={candidate}
              href={`/regulations/${id}/versions/${versionId}/irs?status=${candidate}`}
              className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                active
                  ? (IR_STATUS_STYLE[candidate] ?? 'border-accent text-slate-100')
                  : 'border-surface-border text-slate-400 hover:border-slate-600 hover:text-slate-200'
              }`}
            >
              {IR_STATUS_LABEL[candidate]}
              <span className="ml-1.5 font-mono text-[10px] text-slate-500">
                {count === undefined ? '?' : count}
              </span>
            </Link>
          );
        })}
      </nav>

      {listing === null ? (
        <EmptyState
          title="IR 목록을 불러오지 못했습니다"
          hint="regulation 서비스 상태를 확인하세요."
        />
      ) : irs.length === 0 ? (
        <EmptyState
          title={emptyTitle(status, extracted)}
          hint={emptyHint(status, extracted)}
        />
      ) : (
        <IRList irs={irs} canLock={canWrite} />
      )}

      {total > pageSize ? (
        <nav className="flex items-center justify-between border-t border-surface-border pt-4 text-xs text-slate-500">
          <span className="font-mono">
            {first.toLocaleString()}–{last.toLocaleString()} / {total.toLocaleString()}
          </span>
          <span className="flex gap-4">
            {page > 1 ? (
              <Link
                href={`/regulations/${id}/versions/${versionId}/irs?status=${status}&page=${page - 1}`}
                className="inline-flex items-center gap-1 text-accent hover:underline"
              >
                <ChevronLeft size={13} /> 이전
              </Link>
            ) : null}
            {last < total ? (
              <Link
                href={`/regulations/${id}/versions/${versionId}/irs?status=${status}&page=${page + 1}`}
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

/**
 * The default is `locked` and an unrecognised value falls back to it rather than to "everything".
 * A typo in the query string must not widen what is shown — the safe answer is the one the API
 * defaults to.
 */
function normalizeStatus(value: string | undefined): IRStatus {
  return (IR_STATUS_ORDER as readonly string[]).includes(value ?? '')
    ? (value as IRStatus)
    : 'locked';
}

/**
 * "Nothing here" has several meanings and they are not interchangeable. Nothing extracted yet,
 * nothing locked yet, and nothing stale are three different states — and the last one is good news.
 */
function emptyTitle(status: IRStatus, extracted: boolean): string {
  if (!extracted) return '아직 추출된 IR이 없습니다';
  switch (status) {
    case 'locked':
      return '확정된 IR이 없습니다';
    case 'draft':
      return '검토 대기 중인 초안이 없습니다';
    case 'rejected':
      return '반려된 IR이 없습니다';
    case 'stale':
      return '재도출이 필요한 IR이 없습니다';
    case 'superseded':
      return '대체된 IR이 없습니다';
  }
}

function emptyHint(status: IRStatus, extracted: boolean): string | undefined {
  if (!extracted) return '이 버전에 대해 추출을 실행하면 초안 IR이 생성됩니다.';
  switch (status) {
    case 'locked':
      return '추출은 초안만 만듭니다. ra가 확정해야 답변 생성·영향 등급·갭 분석에 사용됩니다.';
    case 'stale':
      return '인용 조문이 개정되면 해당 IR이 여기에 나타납니다.';
    case 'rejected':
      return 'ra가 반려한 초안이 여기에 남습니다. 사유별 건수는 추출 품질의 신호입니다.';
    default:
      return undefined;
  }
}
