import { ChevronLeft, ClipboardList, FileText, ListTree, Scale } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { formatBytes, formatDate, formatDateTime, shortHash } from '@/lib/format';
import { serverGet } from '@/lib/server-api';
import {
  DOC_TYPE_LABEL,
  VERSION_STATUS_LABEL,
  VERSION_STATUS_STYLE,
} from '@/types/constants';
import type { DocumentDetail } from '@/types/regulation';

export const dynamic = 'force-dynamic';

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const document = await serverGet<DocumentDetail>('regulation', `/documents/${id}`);

  if (!document) {
    return <EmptyState title="문서를 찾을 수 없습니다" />;
  }

  return (
    <div className="space-y-8">
      <div>
        <Link
          href={document.parent ? `/regulations/${document.parent.id}` : '/regulations'}
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        >
          <ChevronLeft size={13} />
          {document.parent ? document.parent.title : '목록'}
        </Link>

        <h1 className="mt-2 text-xl font-semibold text-slate-100">{document.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
          <span className="font-mono">{document.canonical_key}</span>
          <span className="rounded border border-surface-border px-1.5 py-0.5 text-[10px]">
            {DOC_TYPE_LABEL[document.doc_type] ?? document.doc_type}
          </span>
          {document.cells.map((cell) => (
            <span key={cell} className="font-mono text-[10px] text-accent">
              {cell}
            </span>
          ))}
        </div>
      </div>

      {/* Annexes are child documents with their own versions and their own effective dates
          (ADR-0012) — listed as siblings-of-record, not as attachments. */}
      {document.annexes.length > 0 ? (
        <section>
          <h2 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            별표 · 서식 {document.annexes.length}건
          </h2>
          <ul className="grid gap-1.5 sm:grid-cols-2">
            {document.annexes.map((annex) => (
              <li key={annex.id}>
                <Link
                  href={`/regulations/${annex.id}`}
                  className="flex items-center gap-2 rounded-md border border-surface-border bg-surface-raised/40 px-3 py-2 hover:bg-surface-raised"
                >
                  <span className="shrink-0 font-mono text-[11px] text-accent">
                    {annex.canonical_key.split('#')[1]}
                  </span>
                  <span className="truncate text-xs text-slate-300">{annex.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h2 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
          버전 {document.versions.length}건
        </h2>
        {document.versions.length === 0 ? (
          <EmptyState title="아직 수집된 버전이 없습니다" />
        ) : (
          <ul className="space-y-2">
            {document.versions.map((version) => (
              <li
                key={version.id}
                className="rounded-lg border border-surface-border bg-surface-raised/40 p-4"
              >
                {version.status && (
                  <div className="mb-3">
                    {/* Derived from effective_date against today, never stored — a flag would
                        disagree with the date the morning a pending version comes into force. */}
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[10px] ${
                        VERSION_STATUS_STYLE[version.status] ?? ''
                      }`}
                    >
                      {VERSION_STATUS_LABEL[version.status] ?? version.status}
                    </span>
                  </div>
                )}
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 lg:grid-cols-6">
                  <Field label="version" value={version.version_label ?? '—'} mono />
                  <Field label="언어" value={version.language} mono />
                  {/* The three dates travel together so a null is visibly a null, never a
                      silent substitution of our fetch clock for the authority's date. */}
                  <Field label="retrieved_at" value={formatDateTime(version.retrieved_at)} mono />
                  <Field
                    label="published_at"
                    value={version.published_at ? formatDate(version.published_at) : '없음'}
                    muted={!version.published_at}
                    mono
                    title={version.published_at ? undefined : '이 소스는 공표일자를 제공하지 않습니다'}
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
                    title={
                      version.effective_date
                        ? undefined
                        : '부칙에서 달력 날짜로 확정되지 않음 — 원문 문구를 그대로 보존 (ADR-0013)'
                    }
                  />
                  <Field label="크기" value={formatBytes(version.raw_bytes)} mono />
                  <Field
                    label="content_hash"
                    value={shortHash(version.content_hash)}
                    title={version.content_hash}
                    mono
                  />
                  <Field
                    label="raw_object_key"
                    value={shortHash(version.raw_object_key.split('/').pop() ?? '')}
                    title={version.raw_object_key}
                    mono
                  />
                </dl>

                <div className="mt-3 flex flex-wrap items-center gap-4">
                  {/* The three readings of one version, one click apart: what the parser made of
                      it, what the authority actually sent, and what was extracted from it. A parse
                      defect is only visible when the first two sit beside each other, and an
                      extraction is only reviewable when it sits beside the clause it cites. */}
                  <Link
                    href={`/regulations/${document.id}/versions/${version.id}/clauses`}
                    className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
                  >
                    <ListTree size={13} /> 조문 보기
                  </Link>
                  <Link
                    href={`/regulations/${document.id}/versions/${version.id}`}
                    className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
                  >
                    <FileText size={13} /> 원문 보기
                  </Link>
                  <Link
                    href={`/regulations/${document.id}/versions/${version.id}/irs`}
                    className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
                  >
                    <Scale size={13} /> IR 보기
                  </Link>
                  <Link
                    href={`/regulations/${document.id}/versions/${version.id}/submissions`}
                    className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline"
                  >
                    <ClipboardList size={13} /> 제출 서류
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
