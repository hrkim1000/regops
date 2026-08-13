import { ChevronLeft, Lock } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { hasAtLeast, readUserRole } from '@/lib/auth';
import { formatDateTime } from '@/lib/format';
import { serverGet } from '@/lib/server-api';
import {
  ALERT_SEVERITY_HINT,
  ALERT_SEVERITY_LABEL,
  ALERT_SEVERITY_STYLE,
  ALERT_STATUS_LABEL,
  ALERT_STATUS_STYLE,
  DETECTION_LATENCY_TARGET_HOURS,
  DIFF_PAGE_SIZE,
} from '@/types/constants';
import type { AlertDetail, DiffListing, UserSummary } from '@/types/monitoring';

import { AssignBox } from './_components/AssignBox';
import { ClauseDiffList } from './_components/ClauseDiffList';
import { DeliveryList } from './_components/DeliveryList';

export const dynamic = 'force-dynamic';

/**
 * One amendment, in full: what changed, who was told, and who owns it.
 *
 * The clause diffs are fetched from `regulation` rather than carried on the alert. `monitoring`
 * composes alerts from `change_events` and never reads clause text (CLAUDE.md § The seam) — so the
 * alert names the clauses and this page resolves them on the reader's behalf, which keeps the seam
 * intact while still answering the only question that matters: *what does it say now?*
 *
 * The latency line states the gate against the clock the authority publishes on, and says
 * "측정 불가" where it publishes none. Reporting that as zero would turn a missing date into a
 * perfect score (ADR-0003 decision 5).
 */
export default async function AlertDetailPage({
  params,
}: {
  params: Promise<{ alertId: string }>;
}) {
  const { alertId } = await params;

  const alert = await serverGet<AlertDetail>('monitoring', `/alerts/${alertId}`);
  if (!alert) {
    return (
      <EmptyState
        title="알림을 찾을 수 없습니다"
        hint="삭제되었거나 monitoring 서비스에 연결하지 못했습니다."
      />
    );
  }

  // Independent fetches — a failed diff read must still leave the alert, its deliveries and the
  // assignment control usable.
  const diffs = await serverGet<DiffListing>(
    'regulation',
    `/document-versions/${alert.document_version_id}/diffs`,
    {
      clause_path: alert.clause_references.map((reference) => reference.clause_path),
      page_size: DIFF_PAGE_SIZE,
    },
  );
  const users = await serverGet<UserSummary[]>('platform-core', '/users', { page_size: 200 });
  const role = await readUserRole();

  const owner = users?.find((user) => user.id === alert.owner_id);
  const latency = latencyHours(alert.published_at, alert.created_at);

  return (
    <div className="space-y-6">
      <Link
        href="/monitoring"
        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
      >
        <ChevronLeft size={12} /> 변경 모니터링
      </Link>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              ALERT_SEVERITY_STYLE[alert.severity] ?? ''
            }`}
            title={ALERT_SEVERITY_HINT[alert.severity]}
          >
            {ALERT_SEVERITY_LABEL[alert.severity] ?? alert.severity}
          </span>
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              ALERT_STATUS_STYLE[alert.status] ?? ''
            }`}
          >
            {ALERT_STATUS_LABEL[alert.status] ?? alert.status}
          </span>
          <span className="font-mono text-[11px] text-slate-500">{alert.cell}</span>
          {alert.cited_by_locked_ir ? (
            <span className="inline-flex items-center gap-1 rounded border border-red-800 bg-red-950/50 px-1.5 py-0.5 text-[10px] text-red-300">
              <Lock size={10} /> 확정 요구사항 {alert.locked_ir_count}건의 근거가 변경됨
            </span>
          ) : null}
        </div>

        <h1 className="text-lg font-semibold text-slate-100">{alert.title}</h1>

        {/* The server composes this, including the cell-scope limitation. Rendered verbatim: the
            sentence saying this alert is cell-level and not product-level is the honest part. */}
        <p className="whitespace-pre-wrap rounded-lg border border-surface-border bg-surface-raised/40 p-4 text-xs leading-relaxed text-slate-400">
          {alert.summary}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-4 rounded-lg border border-surface-border bg-surface-raised/40 p-4 lg:grid-cols-4">
        <Field label="문서" value={alert.document_title || '—'} />
        <Field label="변경 조문" value={`${alert.clause_count}건`} mono />
        <Field
          label="공포"
          value={alert.published_at ? formatDateTime(alert.published_at) : '미제공'}
          mono
          muted={!alert.published_at}
          title={
            alert.published_at
              ? undefined
              : '이 출처는 공포일자를 제공하지 않습니다 — 지연을 0시간으로 볼 수 없습니다'
          }
        />
        <Field
          label={`공포 → 알림 (목표 ${DETECTION_LATENCY_TARGET_HOURS}h)`}
          value={latency === null ? '측정 불가' : `${latency.toFixed(1)}h`}
          mono
          muted={latency === null}
        />
        <Field label="감지 (현지 시각)" value={alert.detected_at_local} mono />
        <Field label="수집" value={formatDateTime(alert.retrieved_at)} mono />
        <Field
          label="담당자"
          value={owner?.email ?? (alert.owner_id ? '지정됨' : '미지정')}
          muted={!alert.owner_id}
        />
        <Field
          label="지정 시각"
          value={alert.assigned_at ? formatDateTime(alert.assigned_at) : '—'}
          mono
          muted={!alert.assigned_at}
        />
      </dl>

      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-sm font-medium text-slate-300">담당자</h2>
          <p className="text-[11px] text-slate-600">
            지정 내역은 감사 로그에 남습니다 — 재지정도 포함해 모든 이관이 기록됩니다
          </p>
        </div>
        {hasAtLeast(role, 'ra') ? (
          <AssignBox alertId={alert.id} users={users ?? []} currentOwnerId={alert.owner_id} />
        ) : (
          <p className="text-[11px] text-slate-600">
            담당자 지정은 `ra` 이상만 할 수 있습니다. 권한은 서버에서 다시 확인됩니다.
          </p>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-sm font-medium text-slate-300">변경 내용</h2>
          {diffs?.from_version ? (
            <p className="font-mono text-[11px] text-slate-600">
              {diffs.from_version.version_label ?? '이전 버전'} →{' '}
              {diffs.version.version_label ?? '현재 버전'}
            </p>
          ) : null}
        </div>

        {diffs === null ? (
          <EmptyState
            title="조문 변경 내용을 불러오지 못했습니다"
            hint="regulation 서비스 상태를 확인하세요. 알림 자체는 위에 그대로 있습니다."
          />
        ) : diffs.diffs.length === 0 ? (
          <EmptyState
            title="표시할 조문 변경이 없습니다"
            hint="알림이 참조하는 조문을 이 버전에서 찾지 못했습니다 — 재파싱으로 diff가 다시 만들어지는 중일 수 있습니다."
          />
        ) : (
          <ClauseDiffList
            diffs={diffs.diffs}
            documentId={alert.document_id}
            versionId={alert.document_version_id}
            fromVersionId={alert.from_version_id}
          />
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-slate-300">전달 내역</h2>
        <DeliveryList deliveries={alert.deliveries} />
      </section>
    </div>
  );
}

/**
 * Publication → alert, in hours. `null` where the authority published no date — the gate is
 * unmeasurable for that source, which is a different statement from "delivered instantly".
 */
function latencyHours(publishedAt: string | null, createdAt: string): number | null {
  if (!publishedAt) return null;
  const delta = new Date(createdAt).getTime() - new Date(publishedAt).getTime();
  return Number.isFinite(delta) ? delta / 3_600_000 : null;
}
