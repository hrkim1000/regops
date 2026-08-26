import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { readScope } from '@/lib/scope';
import { serverGet, serverGetPage } from '@/lib/server-api';
import {
  ANNEX_CATEGORIES,
  DOC_CATEGORY_LABEL,
  DOC_TYPE_LABEL,
  VERSION_STATUS_STYLE,
} from '@/types/constants';
import type { Cell, DocCategory, DocumentSummary } from '@/types/regulation';

export const dynamic = 'force-dynamic';

/**
 * Documents in the active cell, grouped by where each sits on the legal ladder.
 *
 * "법률·법령 3건, 하위 규정 17건" says what kind of instrument they are, where a flat "20 본문" does
 * not. The grouping began as 국가법령정보's own filing (현행법령 · 현행 행정규칙 · …) and now names
 * the distinction instead, because it is the one every authority in scope makes — the same headers
 * have to hold a 고시 and a C.F.R. Part without either looking like an exception.
 *
 * Annexes are excluded from the *list* (`parent_only`): under ADR-0012 a 고시 with four 별표 is five
 * `documents` rows, so listing them flat would read as five instruments. They are still **counted**
 * in the header, because a cell's real weight is in its 별표, and reachable from the parent's detail
 * page, which is where the relationship is legible.
 *
 * The server sorts by (category, title), so this only has to emit a header when the category
 * changes. Sorting here instead would group whatever 50 rows the page happens to hold.
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
        page_size: 200,
      })
    : null;

  if (!cell) {
    return <EmptyState title={`알 수 없는 셀: ${scope}`} hint="ScopeBar에서 다시 선택하세요." />;
  }
  if (!result?.data) {
    return (
      <EmptyState title="문서를 불러오지 못했습니다" hint="regulation 서비스 상태를 확인하세요." />
    );
  }

  const documents = result.data;

  // Preserve the server's ordering — never re-sort. Grouping is a fold over an already-ordered
  // list, so the run of rows under each header is exactly what the database returned.
  const groups: { category: DocCategory; rows: DocumentSummary[] }[] = [];
  for (const document of documents) {
    const last = groups.at(-1);
    if (last?.category === document.category) last.rows.push(document);
    else groups.push({ category: document.category, rows: [document] });
  }

  const counted = (Object.entries(cell.categories) as [DocCategory, number][]).filter(
    ([, n]) => n > 0,
  );

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <h1 className="font-mono text-sm text-slate-300">{cell.slug}</h1>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          {counted.map(([category, n]) => (
            <span key={category} className="text-slate-400">
              {DOC_CATEGORY_LABEL[category] ?? category}{' '}
              <span className="font-mono text-slate-200">{n}</span>건
            </span>
          ))}
        </div>
        <p className="text-[11px] text-slate-600">
          별표·서식은 각 본문의 상세 페이지에서 볼 수 있습니다.
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
        <div className="space-y-6">
          {groups.map(({ category, rows }) => (
            <section key={category} className="space-y-2">
              <h2 className="flex items-baseline gap-2 text-xs font-medium text-slate-300">
                {DOC_CATEGORY_LABEL[category] ?? category}
                <span className="font-mono text-[11px] text-slate-500">{rows.length}건</span>
              </h2>
              <ul className="divide-y divide-surface-border overflow-hidden rounded-lg border border-surface-border">
                {rows.map((document) => (
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
                      {/* 공포는 됐지만 아직 시행 전인 개정. Without this a 법령 carrying four
                          pending amendments looks exactly like one carrying none. */}
                      {document.pending_version_count > 0 && (
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10px] ${VERSION_STATUS_STYLE.pending}`}
                          title="공포되었으나 아직 시행 전인 버전이 있습니다"
                        >
                          시행예정 {document.pending_version_count}
                        </span>
                      )}
                      <span className="font-mono text-[11px] text-slate-500">
                        별표 {document.annex_count} · 버전 {document.version_count}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <p className="text-xs text-slate-600">
        본문 {result.meta?.total ?? documents.length}건 · 별표·서식{' '}
        {ANNEX_CATEGORIES.reduce((sum, key) => sum + (cell.categories[key] ?? 0), 0)}건
      </p>
    </div>
  );
}
