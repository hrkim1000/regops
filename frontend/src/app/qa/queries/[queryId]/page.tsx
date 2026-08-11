import { ChevronLeft } from 'lucide-react';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { EmptyState } from '@/components/EmptyState';
import { formatDateTime } from '@/lib/format';
import { serverGet } from '@/lib/server-api';
import type { QueryDetail } from '@/types/answer';

import { AwaitAnswer } from './_components/AwaitAnswer';

export const dynamic = 'force-dynamic';

/**
 * A question that has been asked but not yet answered.
 *
 * This page exists because **a pending question is otherwise invisible.** The answer log lists
 * answers, so a question whose worker is still running appears nowhere at all — and on a small local
 * model "still running" can mean minutes. Losing sight of a question you asked is the same failure
 * as losing the question.
 *
 * Once the answer lands this redirects to it, so the URL the ask box hands out stays valid for the
 * whole life of the question rather than only until it is answered.
 */
export default async function QueryPage({ params }: { params: Promise<{ queryId: string }> }) {
  const { queryId } = await params;
  const query = await serverGet<QueryDetail>('assistant', `/queries/${queryId}`);
  if (!query) return <EmptyState title="질문을 찾을 수 없습니다" />;
  if (query.answer) redirect(`/qa/${query.answer.id}`);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/qa"
          className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        >
          <ChevronLeft size={13} /> 질의응답
        </Link>
        <h1 className="mt-2 text-base font-semibold leading-relaxed text-slate-100">
          {query.text}
        </h1>
        <p className="mt-2 font-mono text-[11px] text-slate-600">
          {formatDateTime(query.asked_at)}
          {query.cross_cell ? ' · 교차 셀 검색' : ''}
        </p>
      </div>

      <EmptyState
        title="답변을 생성하는 중입니다"
        hint="검색은 끝났고 모델이 답변과 근거 검증을 만들고 있습니다. 질문은 이미 기록되어 있으니 이 페이지를 닫아도 결과는 남습니다."
      />

      <AwaitAnswer queryId={queryId} />
    </div>
  );
}
