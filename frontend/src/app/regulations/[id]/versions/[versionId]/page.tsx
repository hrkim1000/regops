import { ChevronLeft, ClipboardList, Download, ListTree, Scale } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { formatBytes, formatDate, formatDateTime } from '@/lib/format';
import { serverGet, serverGetRaw } from '@/lib/server-api';
import { RAW_PREVIEW_CHARS } from '@/types/constants';
import type { VersionDetail } from '@/types/regulation';

export const dynamic = 'force-dynamic';

/**
 * The archived artefact, exactly as the authority returned it.
 *
 * This renders the WORM object — not a re-serialization, not a reformatted view. That is the whole
 * point of the archive: what is cited is what was received. Large artefacts are truncated for
 * display with a **visible** marker and a download link; a silently truncated regulation would be
 * indistinguishable from a short one.
 */
export default async function RawVersionPage({
  params,
}: {
  params: Promise<{ id: string; versionId: string }>;
}) {
  const { id, versionId } = await params;

  // Independent fetches: if the archive read fails, the metadata still renders and says so.
  const version = await serverGet<VersionDetail>('regulation', `/document-versions/${versionId}`);
  const raw = await serverGetRaw(versionId);

  if (!version) return <EmptyState title="버전을 찾을 수 없습니다" />;

  const truncated = raw !== null && raw.text.length > RAW_PREVIEW_CHARS;
  const shown = truncated ? raw.text.slice(0, RAW_PREVIEW_CHARS) : (raw?.text ?? '');

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
          {version.document?.title ?? '원문'}
          {version.version_label ? (
            <span className="ml-2 font-mono text-sm text-slate-500">{version.version_label}</span>
          ) : null}
        </h1>
        <p className="mt-1 font-mono text-xs text-slate-500">
          {version.document?.canonical_key}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-lg border border-surface-border bg-surface-raised/40 p-4 sm:grid-cols-4">
        <Field label="retrieved_at" value={formatDateTime(version.retrieved_at)} mono />
        <Field
          label="published_at"
          value={version.published_at ? formatDate(version.published_at) : '없음'}
          muted={!version.published_at}
          mono
        />
        <Field
          label="effective_date"
          value={
            version.effective_date
              ? formatDate(version.effective_date)
              : (version.effective_date_phrase ?? '미해석 (1.1)')
          }
          muted={!version.effective_date}
          mono
        />
        <Field label="크기" value={formatBytes(version.raw_bytes)} mono />
        <Field
          label="content_hash"
          value={version.content_hash}
          title="정규화 본문의 sha256 — 변경 감지가 보는 값"
          mono
        />
        <Field
          label="raw_object_key"
          value={version.raw_object_key}
          title="원본 응답 바이트의 sha256 — 인용의 근거"
          mono
        />
      </dl>

      {version.attachments.length > 0 ? (
        <section>
          <h2 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            authority 파일 링크
          </h2>
          <p className="mb-2 text-[11px] text-slate-600">
            보존용 사본이자 <code>별표내용</code>이 비었을 때의 대체 경로입니다 — 수집 경로가
            아닙니다.
          </p>
          <ul className="space-y-1">
            {version.attachments.map((attachment, index) => (
              <li key={index} className="font-mono text-[11px] text-slate-400">
                {attachment.file_format ?? '?'} · {attachment.source_url ?? '—'}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h2 className="text-xs uppercase tracking-wide text-slate-500">원문</h2>
          <Link
            href={`/regulations/${id}/versions/${versionId}/clauses`}
            className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
          >
            <ListTree size={13} /> 조문 보기
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
          <a
            href={`/api/regulation/document-versions/${versionId}/raw?download=1`}
            className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
          >
            <Download size={13} /> 전체 내려받기
          </a>
          {truncated ? (
            <span className="rounded border border-amber-800/60 bg-amber-950/30 px-2 py-0.5 text-[11px] text-amber-300">
              표시용으로 앞부분 {RAW_PREVIEW_CHARS.toLocaleString()}자만 잘랐습니다 — 전체는
              내려받으세요
            </span>
          ) : null}
        </div>

        {raw === null ? (
          <EmptyState
            title="아카이브에서 원문을 읽지 못했습니다"
            hint="MinIO 상태를 확인하세요. 메타데이터는 위에 그대로 표시됩니다."
          />
        ) : (
          <pre className="max-h-[70vh] overflow-auto rounded-lg border border-surface-border bg-surface-raised/40 p-4 font-mono text-[11px] leading-relaxed text-slate-300">
            {shown}
          </pre>
        )}
      </section>
    </div>
  );
}
