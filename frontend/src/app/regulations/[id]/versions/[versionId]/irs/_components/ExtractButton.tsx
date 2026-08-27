'use client';

import { Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState, useTransition } from 'react';

import type { ExtractionRunSummary } from '@/types/ir';

/** How often to re-read the page while a run is in flight, in ms. */
const POLL_MS = 5_000;

/**
 * Trigger an extraction run. Returns `202` and a `task_id`; the worker commits incrementally.
 *
 * **Deliberately a button and not something that happens on ingest.** Extraction calls an LLM per
 * obligation-bearing clause, so auto-running it on every poll would spend a full extraction to
 * discover nothing changed (phase1.2 deviation 1). Someone asks for it, and this is where they ask.
 *
 * **Whether a run is in flight is the server's answer, not this component's.** It used to be client
 * state — *"did I click within the last five minutes"* — with a `POLL_CEILING_MS` that gave up after
 * five. A 23-minute extraction therefore re-enabled its own button at minute five, stopped
 * refreshing, and left the page showing a mid-run snapshot as though it were the result. Reloading
 * lost the state entirely, and a second tab never had it. Now `run` comes from `/coverage` and
 * survives all three.
 *
 * It reads `run.live` rather than `run.status`. A worker that dies without closing its run leaves
 * the row saying `running` forever, and only the server can tell the difference — it holds the
 * checkpoint heartbeat.
 *
 * The elapsed clock still starts **after mount** — a timer initialised during render disagrees with
 * the server's HTML and trips a hydration mismatch.
 */
export function ExtractButton({
  versionId,
  run,
}: {
  versionId: string;
  run: ExtractionRunSummary | null;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [refreshing, startRefresh] = useTransition();
  // Read inside the interval without re-arming it — `refreshing` in the effect deps would tear the
  // timer down and rebuild it on every poll, which is its own way of losing the cadence.
  const refreshingRef = useRef(false);
  refreshingRef.current = refreshing;

  const running = run?.live === true;
  const startedAt = run?.started_at ?? null;

  useEffect(() => {
    if (!running || !startedAt) {
      setElapsed(null);
      return;
    }
    const since = new Date(startedAt).getTime();
    setElapsed(Date.now() - since);
    const tick = setInterval(() => setElapsed(Date.now() - since), 1_000);
    // No ceiling. The poll stops when the server says the run stopped, which is the only thing that
    // actually knows — a timeout here is a guess that was wrong for every run over five minutes.
    //
    // It does skip a tick while the previous refresh is still in flight. One `router.refresh()`
    // costs the server nine upstream reads, and firing unconditionally every five seconds is what
    // stacked them: renders grew 33s → 73s → 129s until undici's 10s connect timeout began failing
    // and the page rendered a live version as "버전을 찾을 수 없습니다".
    const poll = setInterval(() => {
      if (refreshingRef.current) return;
      startRefresh(() => router.refresh());
    }, POLL_MS);
    return () => {
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [running, startedAt, router]);

  async function trigger() {
    setError(null);
    setRequesting(true);
    try {
      const response = await fetch(`/api/regulation/document-versions/${versionId}/extract`, {
        method: 'POST',
      });
      if (!response.ok) {
        // A 409 here is the server refusing a second concurrent run, and its message says how far
        // the live one has got. Showing it verbatim is more useful than "요청 실패".
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(body?.message ?? `추출 요청 실패 (HTTP ${response.status})`);
        return;
      }
      router.refresh();
    } catch {
      setError('서비스에 연결하지 못했습니다');
    } finally {
      setRequesting(false);
    }
  }

  const busy = running || requesting;

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={trigger}
        disabled={busy}
        title="조문마다 LLM을 호출합니다 — 수집 시 자동 실행되지 않는 이유입니다"
        className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
      >
        <Sparkles size={12} /> {running ? '추출 중…' : requesting ? '요청 중…' : 'IR 추출 실행'}
      </button>
      {running ? (
        <span className="font-mono text-[11px] text-slate-500">
          {elapsed === null ? '' : `${formatElapsed(elapsed)} 경과 · `}
          {run.clauses_seen.toLocaleString()}개 조문 검토 · 자동 새로고침 중
        </span>
      ) : null}
      {error ? <span className="max-w-xs text-right text-[11px] text-red-400">{error}</span> : null}
    </span>
  );
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
