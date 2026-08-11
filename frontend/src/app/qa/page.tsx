import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { readScope } from '@/lib/scope';
import { serverGet, serverGetPage } from '@/lib/server-api';
import {
  ANSWER_PAGE_SIZE,
  ANSWER_STATUS_LABEL,
  ANSWER_STATUS_ORDER,
  ANSWER_STATUS_STYLE,
} from '@/types/constants';
import type { AnswerMetrics, AnswerStatus, AnswerSummary } from '@/types/answer';
import type { Cell } from '@/types/regulation';

import { AnswerList } from './_components/AnswerList';
import { AskBox } from './_components/AskBox';
import { MetricsStrip } from './_components/MetricsStrip';

export const dynamic = 'force-dynamic';

/** `superseded` is a filter, not a status — an answer of any status can have moved evidence. */
type Tab = AnswerStatus | 'all' | 'superseded';

const TABS: readonly Tab[] = ['all', ...ANSWER_STATUS_ORDER, 'superseded'] as const;

const TAB_LABEL: Record<Tab, string> = {
  all: '전체',
  answered: ANSWER_STATUS_LABEL.answered,
  needs_review: ANSWER_STATUS_LABEL.needs_review,
  needs_verification: ANSWER_STATUS_LABEL.needs_verification,
  superseded: '근거 개정',
};

/**
 * The Q&A workbench — phase 1.3's answer log, asked and read.
 *
 * Three shapes here carry the ADR rather than the layout:
 *
 * - **The cell comes from the ScopeBar, never from this page.** Retrieval is cell-scoped
 *   (ADR-0006 decision 9) because a cosmetic question answered from device regulation is a
 *   confident wrong answer — the worst failure this product can produce. Cross-cell is a checkbox
 *   in the ask box, worded as the risk it is.
 * - **The "확인 필요" rate sits above the list, not in an admin corner.** A system that refuses
 *   everything passes both Go/No-Go gates cleanly, so the gates do not guard themselves; the rate
 *   that does belongs in front of the people asking (decision 7).
 * - **근거 개정 is a tab, not a maintenance job.** *"An answer you relied on rests on a clause that
 *   has since been amended"* is the alert the citation model exists to make possible; burying it in
 *   a cron job would waste the one thing it buys.
 */
export default async function QaPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; page?: string }>;
}) {
  const query = await searchParams;
  const page = Math.max(1, Number(query.page ?? '1') || 1);
  const tab = normalizeTab(query.tab);
  const scope = await readScope();

  if (!scope) {
    return (
      <EmptyState
        title="셀을 선택하세요"
        hint="상단 ScopeBar에서 셀을 고르면 그 셀의 규제 원문을 근거로 답변합니다. 셀 없이 답하면 화장품 질문에 의료기기 규정으로 답할 수 있습니다."
      />
    );
  }

  const cells = await serverGet<Cell[]>('regulation', '/cells');
  const cell = cells?.find((candidate) => candidate.slug === scope);
  if (!cell) {
    return <EmptyState title={`알 수 없는 셀: ${scope}`} hint="ScopeBar에서 다시 선택하세요." />;
  }

  // Independent fetches — a failed metrics read must not blank the answer list, and vice versa
  // (frontend-page skill: no `Promise.all` for unrelated resources).
  const metrics = await serverGet<AnswerMetrics>('assistant', '/metrics/answers');
  const listing = await serverGetPage<AnswerSummary[]>('assistant', '/answers', {
    cell_id: cell.id,
    status: tab === 'all' || tab === 'superseded' ? undefined : [tab],
    superseded: tab === 'superseded' ? true : undefined,
    page,
    page_size: ANSWER_PAGE_SIZE,
  });

  const answers = listing?.data ?? [];
  const total = listing?.meta?.total ?? 0;
  const pageSize = listing?.meta?.page_size ?? ANSWER_PAGE_SIZE;
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">질의응답</h1>
        <p className="mt-1 text-xs text-slate-500">
          답변에는 근거 조문과 그 조문이 속한 버전·시행일이 함께 붙습니다. 근거를 댈 수 없으면
          답변하지 않고 “확인 필요”로 돌려줍니다 — 그것이 실패가 아니라 이 제품의 약속입니다.
        </p>
      </div>

      <AskBox cellId={cell.id} cellSlug={cell.slug} />

      {metrics ? <MetricsStrip metrics={metrics} /> : null}

      <nav className="flex flex-wrap gap-1.5 border-b border-surface-border pb-3">
        {TABS.map((candidate) => {
          const active = candidate === tab;
          const style =
            candidate === 'all' || candidate === 'superseded'
              ? 'border-accent text-slate-100'
              : (ANSWER_STATUS_STYLE[candidate] ?? 'border-accent text-slate-100');
          return (
            <Link
              key={candidate}
              href={`/qa?tab=${candidate}`}
              className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                active
                  ? style
                  : 'border-surface-border text-slate-400 hover:border-slate-600 hover:text-slate-200'
              }`}
            >
              {TAB_LABEL[candidate]}
            </Link>
          );
        })}
      </nav>

      {listing === null ? (
        <EmptyState
          title="답변 목록을 불러오지 못했습니다"
          hint="assistant 서비스 상태를 확인하세요."
        />
      ) : answers.length === 0 ? (
        <EmptyState title={emptyTitle(tab)} hint={emptyHint(tab)} />
      ) : (
        <AnswerList answers={answers} />
      )}

      {total > pageSize ? (
        <nav className="flex items-center justify-between border-t border-surface-border pt-4 text-xs text-slate-500">
          <span className="font-mono">
            {first.toLocaleString()}–{last.toLocaleString()} / {total.toLocaleString()}
          </span>
          <span className="flex gap-4">
            {page > 1 ? (
              <Link href={`/qa?tab=${tab}&page=${page - 1}`} className="text-accent hover:underline">
                이전
              </Link>
            ) : null}
            {last < total ? (
              <Link href={`/qa?tab=${tab}&page=${page + 1}`} className="text-accent hover:underline">
                다음
              </Link>
            ) : null}
          </span>
        </nav>
      ) : null}
    </div>
  );
}

/** An unrecognised tab falls back to `all` rather than to an empty filter nobody chose. */
function normalizeTab(value: string | undefined): Tab {
  return (TABS as readonly string[]).includes(value ?? '') ? (value as Tab) : 'all';
}

/** "Nothing here" has several meanings, and one of them is good news. */
function emptyTitle(tab: Tab): string {
  switch (tab) {
    case 'superseded':
      return '근거가 개정된 답변이 없습니다';
    case 'needs_verification':
      return '확인 필요로 돌아간 답변이 없습니다';
    case 'needs_review':
      return '검토 대기 중인 답변이 없습니다';
    case 'answered':
      return '확정된 답변이 없습니다';
    default:
      return '아직 질문이 없습니다';
  }
}

function emptyHint(tab: Tab): string | undefined {
  switch (tab) {
    case 'superseded':
      return '인용한 조문이 개정되면 해당 답변이 여기에 모입니다. 답변은 수정되지 않고 그대로 남습니다 — 다시 질문하면 새 답변이 만들어집니다.';
    case 'needs_verification':
      return '근거를 댈 수 없거나 검증을 통과하지 못한 답변이 여기 모입니다. 0%에 가깝다면 임계값이 느슨하다는 신호입니다.';
    case 'answered':
      return '근거가 확인되고 신뢰도 임계값을 넘은 답변만 여기 표시됩니다.';
    default:
      return '위에 질문을 입력하면 이 셀의 규제 원문에서 근거를 찾아 답변합니다.';
  }
}
