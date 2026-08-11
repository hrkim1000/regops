'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

/** How often to re-check, in ms. Slower than the ask box: this page is opened, not watched. */
const POLL_MS = 5_000;

/**
 * Re-check until the answer lands, then let the server component redirect to it.
 *
 * No ceiling here, unlike the ask box. That one has to release the form so another question can be
 * asked; this page has nothing else to do, and a question that takes ten minutes on a small local
 * model is slow rather than lost.
 *
 * The elapsed clock starts **after mount** — a timer initialised during render disagrees with the
 * server's HTML and trips a hydration mismatch.
 */
export function AwaitAnswer({ queryId }: { queryId: string }) {
  const router = useRouter();
  const [elapsed, setElapsed] = useState(0);
  const inFlight = useRef(false);

  useEffect(() => {
    const startedAt = Date.now();
    const tick = setInterval(() => setElapsed(Date.now() - startedAt), 1_000);
    const poll = setInterval(async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const response = await fetch(`/api/assistant/queries/${queryId}`);
        if (!response.ok) return;
        const body = (await response.json()) as { data?: { answer?: { id: string } | null } };
        if (body.data?.answer?.id) router.refresh();
      } catch {
        // A transient failure is not an answer. Keep checking.
      } finally {
        inFlight.current = false;
      }
    }, POLL_MS);

    return () => {
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [queryId, router]);

  return (
    <p className="text-center font-mono text-[11px] text-slate-600">
      {formatElapsed(elapsed)} 경과 · 자동 확인 중
    </p>
  );
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
