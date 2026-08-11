import { AlertTriangle, ChevronLeft, History } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { formatDate } from '@/lib/format';
import { serverGet } from '@/lib/server-api';
import {
  ANSWER_CONFIDENCE_THRESHOLD,
  ANSWER_STATUS_LABEL,
  ANSWER_STATUS_STYLE,
  NO_ANSWER_REASON_HINT,
  NO_ANSWER_REASON_LABEL,
  NO_ANSWER_REASON_TONE,
} from '@/types/constants';
import type { Answer } from '@/types/answer';
import type { VersionDetail } from '@/types/regulation';

import { ClaimList } from './_components/ClaimList';

export const dynamic = 'force-dynamic';

/**
 * One answer, with everything needed to decide whether to trust it.
 *
 * The ordering on this page is the argument: **the caveats come before the answer text.** An answer
 * whose clauses straddle an effective-date boundary, or whose evidence has since been amended, looks
 * identical to a correct one — so those banners sit above the prose rather than under it, where a
 * reader who has already acted on the answer would find them.
 *
 * A refusal renders as a *result*, not as an error. "확인 필요" is the promise in RegOps.md being
 * kept: no unsourced answer is ever emitted, and the reason it was refused is a value from a closed
 * inventory rather than an apology.
 */
export default async function AnswerPage({ params }: { params: Promise<{ answerId: string }> }) {
  const { answerId } = await params;
  const answer = await serverGet<Answer>('assistant', `/answers/${answerId}`);
  if (!answer) return <EmptyState title="답변을 찾을 수 없습니다" />;

  // One fetch per distinct cited version, for its title and status. Independent of the answer read:
  // a version lookup that fails must leave the citation rendered with its path rather than blanking
  // the evidence list.
  const versionIds = [...new Set(answer.citations.map((c) => c.document_version_id))];
  const versions: Record<string, VersionDetail | null> = {};
  for (const versionId of versionIds) {
    versions[versionId] = await serverGet<VersionDetail>(
      'regulation',
      `/document-versions/${versionId}`,
    );
  }

  const belowThreshold = answer.confidence < ANSWER_CONFIDENCE_THRESHOLD;
  //: Three tones, not two. "The model misbehaved" and "the model was never reached" are different
  //: facts, and rendering the second as the first tells the reader something untrue.
  const tone = answer.no_answer_reason
    ? (NO_ANSWER_REASON_TONE[answer.no_answer_reason] ?? 'expected')
    : 'expected';

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
          {answer.question ?? '질문'}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              ANSWER_STATUS_STYLE[answer.status] ?? ''
            }`}
          >
            {ANSWER_STATUS_LABEL[answer.status] ?? answer.status}
          </span>
          <span className="font-mono text-[11px] text-slate-500">
            신뢰도 {answer.confidence.toFixed(2)}
            <span className="text-slate-600"> / 임계값 {ANSWER_CONFIDENCE_THRESHOLD}</span>
          </span>
        </div>
      </div>

      {answer.superseded_at ? (
        <Banner tone="amber" icon={<History size={14} />}>
          이 답변이 인용한 조문이 이후 <strong>개정</strong>되었습니다 (
          {formatDate(answer.superseded_at)}). 답변과 인용은 수정되지 않고 그대로 남습니다 — 당시
          근거의 기록이기 때문입니다. 현재 기준이 필요하면 다시 질문하세요.
        </Banner>
      ) : null}

      {answer.straddles_effective_date ? (
        <Banner tone="amber" icon={<AlertTriangle size={14} />}>
          근거 조문의 <strong>시행일이 일치하지 않습니다</strong>. 시행 중인 조문과 개정되었으나 아직
          시행되지 않은 조문이 함께 검색되었습니다 — 둘을 섞어 읽으면 안 됩니다. 아래 각 인용의
          시행일을 확인하세요.
        </Banner>
      ) : null}

      {answer.status === 'needs_review' ? (
        <Banner tone="amber" icon={<AlertTriangle size={14} />}>
          신뢰도가 임계값 아래여서 <strong>사람 검토로 보낸 답변</strong>입니다. 최종 답변으로
          쓰지 마세요 — 근거는 아래에 그대로 있으니 직접 확인하고 판단하십시오.
        </Banner>
      ) : null}

      {answer.status === 'needs_verification' ? (
        <Banner tone={tone === 'expected' ? 'sky' : 'red'} icon={<AlertTriangle size={14} />}>
          <strong>확인 필요</strong> —{' '}
          {answer.no_answer_reason
            ? (NO_ANSWER_REASON_LABEL[answer.no_answer_reason] ?? answer.no_answer_reason)
            : '근거를 확인하지 못했습니다'}
          .{' '}
          {answer.no_answer_reason
            ? (NO_ANSWER_REASON_HINT[answer.no_answer_reason] ?? '')
            : '근거를 댈 수 없을 때 답변을 지어내지 않는 것이 이 제품의 약속입니다.'}
        </Banner>
      ) : null}

      {answer.text ? (
        <section className="rounded-lg border border-surface-border bg-surface-raised/40 p-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
            {answer.text}
          </p>
        </section>
      ) : null}

      <div className="rounded-lg border border-surface-border bg-surface-raised/40 p-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
          <Field
            label="기준 시행일"
            value={answer.effective_date_scope ? formatDate(answer.effective_date_scope) : '—'}
            muted={!answer.effective_date_scope}
            mono
          />
          <Field label="근거 조문" value={String(answer.citations.length)} mono />
          <Field label="대상 버전" value={String(answer.document_version_scope.length)} mono />
          <Field
            label="검토 필요"
            value={belowThreshold ? '예' : '아니오'}
            muted={!belowThreshold}
          />
        </dl>
      </div>

      <section className="space-y-3">
        <h2 className="text-xs font-medium text-slate-400">근거와 검증</h2>
        {answer.citations.length === 0 && answer.verification.length === 0 ? (
          <EmptyState
            title="근거 조문이 없습니다"
            hint="근거를 댈 수 없어 답변하지 않은 경우입니다 — 이것이 정상 동작입니다."
          />
        ) : (
          <ClaimList
            citations={answer.citations}
            verification={answer.verification}
            versions={versions}
          />
        )}
      </section>

      <section className="rounded-lg border border-surface-border bg-surface-raised/40 p-4">
        <h2 className="text-xs font-medium text-slate-400">생성 이력</h2>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
          <Field label="llm_provider" value={answer.provenance.llm_provider} mono />
          <Field label="llm_model" value={answer.provenance.llm_model} mono />
          <Field label="prompt_version" value={answer.provenance.prompt_version} mono />
          <Field label="retrieval_version" value={answer.provenance.retrieval_version} mono />
        </dl>
      </section>
    </div>
  );
}

function Banner({
  tone,
  icon,
  children,
}: {
  tone: 'amber' | 'sky' | 'red';
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const styles = {
    amber: 'border-amber-700 bg-amber-950/40 text-amber-200',
    sky: 'border-sky-800 bg-sky-950/40 text-sky-200',
    red: 'border-red-800 bg-red-950/40 text-red-200',
  } as const;

  return (
    <p className={`flex gap-2 rounded-lg border px-4 py-3 text-xs leading-relaxed ${styles[tone]}`}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span>{children}</span>
    </p>
  );
}
