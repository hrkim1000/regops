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
 * **The one thing the server cannot answer is "did my request get queued".** `POST .../extract`
 * returns `202` the moment the message is on the queue, and the run row is written later by the
 * worker that picks it up. Between those two moments there is no live run, so `/coverage` reports
 * none, the server's own 409 guard — which asks for a *live run* — accepts a second request, and
 * this button re-enabled itself. That is not hypothetical: on 2026-09-08 the queue was hours deep
 * behind a batch, one version was triggered at 13:16 and again at 13:17, and both were enqueued.
 * A second run is destructive, not idempotent — it calls `_clear_previous_drafts`.
 *
 * So acceptance is held here, as `queued`, until a *new* run row appears. It is keyed on the run
 * id observed at request time rather than on a clock, because comparing a browser's `Date.now()`
 * with a server timestamp is a skew bug waiting to happen. A reload clears it, and that is the
 * deliberate escape hatch: a queued task has no server representation to recover from, so a
 * request that never starts must not disable the button forever.
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
  const [pending, setPending] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);
  // The run the page was showing when the request went out. A different one means the worker has
  // picked our task up, which is the only honest signal that the queued window is over.
  const runIdAtRequest = useRef<string | null>(null);
  const [refreshing, startRefresh] = useTransition();
  // Read inside the interval without re-arming it — `refreshing` in the effect deps would tear the
  // timer down and rebuild it on every poll, which is its own way of losing the cadence.
  const refreshingRef = useRef(false);
  refreshingRef.current = refreshing;

  const running = run?.live === true;
  const startedAt = run?.started_at ?? null;
  const runId = run?.id ?? null;
  // Enqueued, not yet started. Holds the button between the `202` and the worker's first write.
  const queued = pending && runId === runIdAtRequest.current;

  const busy = running || requesting || queued;

  useEffect(() => {
    if (pending && runId !== runIdAtRequest.current) setPending(false);
  }, [pending, runId]);

  useEffect(() => {
    // Poll while queued as well as while running: without it the page never learns that the task
    // it enqueued has started, so the queued hold would only ever end by reload.
    if (!running && !queued) {
      setElapsed(null);
      return;
    }
    const since = startedAt === null ? null : new Date(startedAt).getTime();
    setElapsed(running && since !== null ? Date.now() - since : null);
    const tick = setInterval(
      () => setElapsed(running && since !== null ? Date.now() - since : null),
      1_000,
    );
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
  }, [running, queued, startedAt, router]);

  async function trigger() {
    // Guard the handler itself, not only the `disabled` attribute. `disabled` is a render away,
    // and two clicks inside one frame both reach this function before React has re-rendered either.
    if (busy) return;
    setError(null);
    setRequesting(true);
    // Pinned before the request, not after: the response can arrive after a poll has already
    // replaced `run`, and comparing against the newer row would clear the hold immediately.
    runIdAtRequest.current = runId;
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
      // Accepted and queued. Hold the button here until a new run row proves a worker took it.
      setPending(true);
      router.refresh();
    } catch {
      setError('서비스에 연결하지 못했습니다');
    } finally {
      setRequesting(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={trigger}
        disabled={busy}
        title="조문마다 LLM을 호출합니다 — 수집 시 자동 실행되지 않는 이유입니다"
        className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
      >
        <Sparkles size={12} />{' '}
        {running ? '추출 중…' : requesting ? '요청 중…' : queued ? '대기 중…' : 'IR 추출 실행'}
      </button>
      {running ? (
        <span className="font-mono text-[11px] text-slate-500">
          {elapsed === null ? '' : `${formatElapsed(elapsed)} 경과 · `}
          {run.clauses_seen.toLocaleString()}개 조문 검토 · 자동 새로고침 중
        </span>
      ) : queued ? (
        // Says *queued*, not *running*, because they are different facts and only one of them
        // means a worker is spending model budget. A depth-hours queue can sit here a long time.
        <span className="font-mono text-[11px] text-slate-500">
          큐에 등록됨 · 워커가 가져가면 시작됩니다 · 다른 화면으로 이동해도 계속됩니다
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
