'use client';

import { Lock } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

/**
 * The human gate: **the LLM proposes, a person locks** (ADR-0004 decision 4).
 *
 * A client island because it writes, and one of only two restricted actions in Phase 1 — this is
 * where a human assertion enters the audit trail, so the copy says what is being asserted rather
 * than naming a state change. "확정" is not a status toggle; it is a reviewer saying *this
 * obligation is correctly extracted from that clause*.
 *
 * Hiding the button for a `viewer` is cosmetic and known to be: the endpoint re-checks the role and
 * 403s regardless, and this component never sees a token to spend.
 */
export function LockButton({ irId }: { irId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function lock() {
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`/api/regulation/irs/${irId}/lock`, { method: 'POST' });
      if (!response.ok) {
        // Show the service's own reason. The interesting failures here are 409s that state
        // something true — the IR went stale, or somebody else locked it first — and replacing
        // those with a generic message would hide a real change from the reviewer.
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(body?.message ?? `확정 실패 (HTTP ${response.status})`);
        return;
      }
      router.refresh();
    } catch {
      setError('서비스에 연결하지 못했습니다');
    } finally {
      setPending(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={lock}
        disabled={pending}
        className="inline-flex items-center gap-1.5 rounded-md border border-emerald-800 bg-emerald-950/40 px-2.5 py-1 text-xs text-emerald-300 transition-colors hover:border-emerald-600 disabled:opacity-50"
      >
        <Lock size={12} /> {pending ? '확정 중…' : '확정'}
      </button>
      {error ? <span className="text-right text-[11px] text-red-400">{error}</span> : null}
    </span>
  );
}
