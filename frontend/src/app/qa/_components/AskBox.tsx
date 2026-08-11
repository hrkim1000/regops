'use client';

import { Search } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

/** How often to re-read the question while the worker is answering, in ms. */
const POLL_MS = 3_000;
/** Stop polling after this. An answer that outlives it is not lost — it is in the list below. */
const POLL_CEILING_MS = 4 * 60_000;

/**
 * Ask a question in the active cell.
 *
 * `POST /queries` returns `202` with the question's id, because answering is model-bound: one
 * generation plus one verification per claim. The question row is written synchronously, so there
 * is always something to poll — and a question that was asked stays on the record even if the
 * answer never arrives.
 *
 * **The cell is not selectable here.** It comes from the header ScopeBar, like every other scope in
 * this app (frontend-page skill), and a per-page picker would make cross-cell retrieval an accident
 * rather than the explicit mode ADR-0006 decision 9 requires it to be. The cross-cell checkbox is
 * the explicit form, and it is worded as the risk it carries.
 *
 * The elapsed clock starts **after mount** — a timer initialised during render disagrees with the
 * server's HTML and trips a hydration mismatch.
 */
export function AskBox({ cellId, cellSlug }: { cellId: string; cellSlug: string }) {
  const router = useRouter();
  const [text, setText] = useState('');
  const [crossCell, setCrossCell] = useState(false);
  const [queryId, setQueryId] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    if (queryId === null || startedAt === null) return;

    const tick = setInterval(() => setElapsed(Date.now() - startedAt), 1_000);
    const poll = setInterval(async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const response = await fetch(`/api/assistant/queries/${queryId}`);
        if (!response.ok) return;
        const body = (await response.json()) as { data?: { answer?: { id: string } | null } };
        const answerId = body.data?.answer?.id;
        if (answerId) {
          setQueryId(null);
          setStartedAt(null);
          router.push(`/qa/${answerId}`);
        }
      } catch {
        // A transient failure is not an answer. Keep polling; the ceiling ends it.
      } finally {
        inFlight.current = false;
      }
    }, POLL_MS);
    const stop = setTimeout(() => {
      // Not a silent give-up. The question is recorded and the worker is still on it, so say so and
      // leave a link — a spinner that simply stops looks like the question was lost.
      setPending(queryId);
      setQueryId(null);
      setStartedAt(null);
      router.refresh();
    }, POLL_CEILING_MS);

    return () => {
      clearInterval(tick);
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [queryId, startedAt, router]);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const question = text.trim();
    if (question.length < 2 || queryId !== null) return;

    setError(null);
    setPending(null);
    try {
      const response = await fetch('/api/assistant/queries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: question, cell_id: cellId, cross_cell: crossCell }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(body?.message ?? `질문 접수 실패 (HTTP ${response.status})`);
        return;
      }
      const body = (await response.json()) as { data?: { id?: string } };
      if (!body.data?.id) {
        setError('질문 ID를 받지 못했습니다');
        return;
      }
      setQueryId(body.data.id);
      setStartedAt(Date.now());
      setElapsed(0);
    } catch {
      setError('서비스에 연결하지 못했습니다');
    }
  }

  const running = queryId !== null;

  return (
    <form
      onSubmit={ask}
      className="space-y-3 rounded-lg border border-surface-border bg-surface-raised/40 p-4"
    >
      <label htmlFor="qa-question" className="block text-xs text-slate-500">
        <span className="font-mono text-slate-400">{cellSlug}</span> 범위에서 질문합니다
      </label>
      <textarea
        id="qa-question"
        value={text}
        onChange={(event) => setText(event.target.value)}
        disabled={running}
        rows={3}
        placeholder="예: 화장품책임판매업자는 안전성 정보를 언제까지 보고해야 하나요?"
        className="w-full resize-y rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none disabled:opacity-50"
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="inline-flex items-center gap-2 text-[11px] text-slate-500">
          <input
            type="checkbox"
            checked={crossCell}
            onChange={(event) => setCrossCell(event.target.checked)}
            disabled={running}
            className="accent-accent"
          />
          다른 셀도 검색 — 화장품 질문에 의료기기 규정으로 답할 수 있습니다
        </label>

        <span className="inline-flex items-center gap-3">
          {running ? (
            <span className="font-mono text-[11px] text-slate-500">
              {formatElapsed(elapsed)} 경과 · 검색 → 생성 → 검증
            </span>
          ) : null}
          <button
            type="submit"
            disabled={running || text.trim().length < 2}
            className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
          >
            <Search size={12} /> {running ? '답변 생성 중…' : '질문하기'}
          </button>
        </span>
      </div>

      {error ? <p className="text-[11px] text-red-400">{error}</p> : null}

      {pending ? (
        <p className="rounded-md border border-amber-700 bg-amber-950/40 px-3 py-2 text-[11px] leading-relaxed text-amber-200">
          아직 생성 중입니다. 질문은 기록되었고 워커는 계속 작업 중이니, 잠시 후{' '}
          <Link href={`/qa/queries/${pending}`} className="underline">
            이 질문
          </Link>
          을 다시 열어 보거나 아래 목록을 새로고침하세요. 이 정도로 오래 걸린다면 모델이 이 프롬프트에
          비해 느린 것입니다.
        </p>
      ) : null}
    </form>
  );
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
