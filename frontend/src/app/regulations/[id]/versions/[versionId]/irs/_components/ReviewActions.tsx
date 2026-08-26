'use client';

import { Lock, RotateCcw, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { IR_REJECTION_REASON_LABEL, IR_REJECTION_REASONS } from '@/types/constants';
import type { IRRejectionReason, IRStatus } from '@/types/ir';

/**
 * The reviewer's three moves: **확정**, **반려**, and taking back a 확정 (ADR-0020).
 *
 * It used to be one button, and that was faithful to a model with one transition — there was no
 * `rejected` status and no `unlock` endpoint, so a reviewer who disagreed had nowhere to put it and
 * a mis-click had no way back. Both are gone; this is the surface for what replaced them.
 *
 * **반려 asks for a reason before it will send.** Not friction for its own sake: the count per
 * reason is the signal about extraction quality — a run whose drafts are mostly refused as
 * `not_an_obligation` is a classification regression, and that is invisible if the reason is free
 * text or absent. The note beside it is where the actual judgement goes.
 *
 * **확정 취소 returns the IR to 초안, not to 반려.** "This approval was a mistake" and "I have
 * reviewed this and refuse it" are different assertions, and merging them would write a judgement
 * nobody made. Refusing an IR that was locked by mistake is two steps, and the trail then says both
 * things happened.
 *
 * Hiding these from a `viewer` is cosmetic and known to be: every endpoint re-checks the role and
 * 403s regardless, and this component never sees a token to spend.
 */
export function ReviewActions({ irId, status }: { irId: string; status: IRStatus }) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState<IRRejectionReason>('not_an_obligation');
  const [note, setNote] = useState('');

  async function send(action: string, body?: unknown) {
    setPending(action);
    setError(null);
    try {
      const response = await fetch(`/api/regulation/irs/${irId}/${action}`, {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) {
        // The service's own reason, verbatim. The interesting failures are 409s that state
        // something true — the IR went stale, or somebody else acted on it first — and replacing
        // those with a generic message would hide a real change from the reviewer.
        const payload = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(payload?.message ?? `실패 (HTTP ${response.status})`);
        return;
      }
      setRejecting(false);
      setNote('');
      router.refresh();
    } catch {
      setError('서비스에 연결하지 못했습니다');
    } finally {
      setPending(null);
    }
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <span className="inline-flex items-center gap-1.5">
        {status === 'draft' ? (
          <>
            <button
              type="button"
              onClick={() => send('lock')}
              disabled={pending !== null}
              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-800 bg-emerald-950/40 px-2.5 py-1 text-xs text-emerald-300 transition-colors hover:border-emerald-600 disabled:opacity-50"
            >
              <Lock size={12} /> {pending === 'lock' ? '확정 중…' : '확정'}
            </button>
            <button
              type="button"
              onClick={() => setRejecting((open) => !open)}
              disabled={pending !== null}
              className="inline-flex items-center gap-1.5 rounded-md border border-rose-900 bg-rose-950/30 px-2.5 py-1 text-xs text-rose-300 transition-colors hover:border-rose-700 disabled:opacity-50"
            >
              <X size={12} /> 반려
            </button>
          </>
        ) : null}

        {status === 'locked' ? (
          <button
            type="button"
            onClick={() => send('unlock', { note: '확정 취소' })}
            disabled={pending !== null}
            className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200 disabled:opacity-50"
          >
            <RotateCcw size={12} /> {pending === 'unlock' ? '취소 중…' : '확정 취소'}
          </button>
        ) : null}
      </span>

      {rejecting ? (
        <span className="mt-1 flex w-72 flex-col gap-1.5 rounded-md border border-surface-border bg-surface-raised/80 p-2">
          <label className="text-[10px] uppercase tracking-wide text-slate-500">반려 사유</label>
          <select
            value={reason}
            onChange={(event) => setReason(event.target.value as IRRejectionReason)}
            className="rounded border border-surface-border bg-surface px-2 py-1 text-xs text-slate-200"
          >
            {IR_REJECTION_REASONS.map((value) => (
              <option key={value} value={value}>
                {IR_REJECTION_REASON_LABEL[value]}
              </option>
            ))}
          </select>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={2}
            placeholder="어디가 왜 잘못되었는지 (필수)"
            className="rounded border border-surface-border bg-surface px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
          />
          <span className="flex justify-end gap-1.5">
            <button
              type="button"
              onClick={() => setRejecting(false)}
              className="rounded px-2 py-1 text-[11px] text-slate-500 hover:text-slate-300"
            >
              취소
            </button>
            <button
              type="button"
              onClick={() => send('reject', { reason, note })}
              // The backend requires three characters; matching it here turns a 422 into a
              // disabled button, which is the same rule stated where the reviewer can see it.
              disabled={pending !== null || note.trim().length < 3}
              className="rounded-md border border-rose-800 bg-rose-950/50 px-2.5 py-1 text-[11px] text-rose-300 transition-colors hover:border-rose-600 disabled:opacity-40"
            >
              {pending === 'reject' ? '반려 중…' : '반려 확정'}
            </button>
          </span>
        </span>
      ) : null}

      {error ? <span className="text-right text-[11px] text-red-400">{error}</span> : null}
    </span>
  );
}
