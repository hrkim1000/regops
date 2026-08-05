import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { readScope } from '@/lib/scope';
import { serverGet, serverGetPage } from '@/lib/server-api';
import { DOC_TYPE_LABEL } from '@/types/constants';
import type { Cell, DocumentSummary } from '@/types/regulation';

export const dynamic = 'force-dynamic';

/**
 * Documents in the active cell.
 *
 * Annexes are excluded (`parent_only`): under ADR-0012 a 고시 with four 별표 is five `documents`
 * rows, so a flat list would read as five instruments. They are reachable from the parent's detail
 * page, which is where their relationship is legible.
 */
export default async function RegulationsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const { q, page: pageParam } = await searchParams;
  const scope = await readScope();
  const page = Number(pageParam ?? '1') || 1;

  if (!scope) {
    return (
      <EmptyState
        title="셀을 선택하세요"
        hint="상단 ScopeBar에서 셀을 고르면 그 셀이 수집한 문서가 표시됩니다."
      />
    );
  }

  const cells = await serverGet<Cell[]>('regulation', '/cells');
  const cell = cells?.find((c) => c.slug === scope);

  const result = cell
    ? await serverGetPage<DocumentSummary[]>('regulation', '/documents', {
        cell_id: cell.id,
        parent_only: true,
        q,
        page,
        page_size: 50,
      })
    : null;

  if (!cell) {
    return <EmptyState title={`알 수 없는 셀: ${scope}`} hint="ScopeBar에서 다시 선택하세요." />;
  }
  if (!result?.data) {
    return <EmptyState title="문서를 불러오지 못했습니다" hint="regulation 서비스 상태를 확인하세요." />;
  }

  const documents = result.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="font-mono text-sm text-slate-300">{cell.slug}</h1>
        <p className="text-xs text-slate-500">
          본문 {cell.document_count}건 · 별표 {cell.annex_count}건
        </p>
      </div>

      <form className="flex gap-2" action="/regulations">
        <input
          name="q"
          defaultValue={q ?? ''}
          placeholder="제목 검색"
          className="w-64 rounded-md border border-surface-border bg-surface-raised px-3 py-1.5 text-sm outline-none focus:border-accent"
        />
        <button
          type="submit"
          className="rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-300 hover:border-slate-600"
        >
          검색
        </button>
      </form>

      {documents.length === 0 ? (
        <EmptyState
          title={q ? `"${q}"에 해당하는 문서가 없습니다` : '이 셀에는 아직 수집된 문서가 없습니다'}
          hint={q ? undefined : '커넥터가 아직 연결되지 않은 셀일 수 있습니다.'}
        />
      ) : (
        <ul className="divide-y divide-surface-border overflow-hidden rounded-lg border border-surface-border">
          {documents.map((document) => (
            <li key={document.id}>
              <Link
                href={`/regulations/${document.id}`}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 bg-surface-raised/40 px-4 py-3 hover:bg-surface-raised"
              >
                <span className="min-w-0 flex-1 truncate text-sm text-slate-100">
                  {document.title}
                </span>
                <span className="rounded border border-surface-border px-1.5 py-0.5 text-[10px] text-slate-400">
                  {DOC_TYPE_LABEL[document.doc_type] ?? document.doc_type}
                </span>
                <span className="font-mono text-[11px] text-slate-500">
                  별표 {document.annex_count} · 버전 {document.version_count}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-slate-600">
        {result.meta?.total ?? documents.length}건 중 {documents.length}건 표시
      </p>
    </div>
  );
}
