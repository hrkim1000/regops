'use client';

import { Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

/** How often to re-read the page while an extraction is believed to be running, in ms. */
const POLL_MS = 4_000;
/** Stop polling after this long. A run that outlives it is not lost — reload to see where it got to. */
const POLL_CEILING_MS = 5 * 60_000;

/**
 * Trigger an extraction run. Returns `202` and a `task_id`; the worker commits incrementally.
 *
 * **Deliberately a button and not something that happens on ingest.** Extraction calls an LLM per
 * obligation-bearing clause, so auto-running it on every poll would spend a full extraction to
 * discover nothing changed (phase1.2 deviation 1). Someone asks for it, and this is where they ask.
 *
 * There is no run-status stream to subscribe to, so progress is inferred by re-reading the page.
 * The elapsed clock starts **after mount** — a timer initialised during render disagrees with the
 * server's HTML and trips a hydration mismatch.
 */
export function ExtractButton({ versionId }: { versionId: string }) {
  const router = useRouter();
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (startedAt === null) return;

    const tick = setInterval(() => setElapsed(Date.now() - startedAt), 1_000);
    const poll = setInterval(() => router.refresh(), POLL_MS);
    const stop = setTimeout(() => setStartedAt(null), POLL_CEILING_MS);
    return () => {
      clearInterval(tick);
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [startedAt, router]);

  async function trigger() {
    setError(null);
    try {
      const response = await fetch(`/api/regulation/document-versions/${versionId}/extract`, {
        method: 'POST',
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(body?.message ?? `추출 요청 실패 (HTTP ${response.status})`);
        return;
      }
      setStartedAt(Date.now());
      setElapsed(0);
    } catch {
      setError('서비스에 연결하지 못했습니다');
    }
  }

  const running = startedAt !== null;

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={trigger}
        disabled={running}
        title="조문마다 LLM을 호출합니다 — 수집 시 자동 실행되지 않는 이유입니다"
        className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
      >
        <Sparkles size={12} /> {running ? '추출 중…' : 'IR 추출 실행'}
      </button>
      {running ? (
        <span className="font-mono text-[11px] text-slate-500">
          {formatElapsed(elapsed)} 경과 · 자동 새로고침 중
        </span>
      ) : null}
      {error ? <span className="text-right text-[11px] text-red-400">{error}</span> : null}
    </span>
  );
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
