'use client';

import { BellPlus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import {
  ALERT_CHANNEL_CHOICES,
  ALERT_CHANNEL_LABEL,
  ALERT_SEVERITY_LABEL,
  ALERT_SEVERITY_ORDER,
} from '@/types/constants';
import type { AlertChannel, AlertSeverity } from '@/types/monitoring';
import type { Cell } from '@/types/regulation';

/**
 * Subscribe to a cell.
 *
 * **The cell is picked here rather than taken from the ScopeBar, and that is the one deliberate
 * exception.** Everywhere else the ScopeBar decides what a page shows (frontend-page skill: no
 * per-page cell pickers) — but this page does not *show* a cell, it manages a standing list of
 * them, and forcing a reader to switch scope four times to subscribe to four cells would make the
 * rule serve itself rather than the reader. Nothing here reads scoped data.
 *
 * `email` is absent from the choices on purpose: the enum has it, but Phase 1 ships no mail relay,
 * so offering it would produce subscriptions whose every delivery is recorded as failed.
 */
export function SubscriptionForm({ cells }: { cells: Cell[] }) {
  const router = useRouter();
  const [cell, setCell] = useState('');
  const [channel, setChannel] = useState<AlertChannel>('in_app');
  const [destination, setDestination] = useState('');
  const [minSeverity, setMinSeverity] = useState<AlertSeverity>('low');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsDestination = channel !== 'in_app';

  async function subscribe(event: React.FormEvent) {
    event.preventDefault();
    if (!cell || pending) return;
    if (needsDestination && !destination.trim()) {
      setError('웹훅 주소를 입력하세요 — 보낼 곳이 없는 구독은 조용한 커버리지 구멍입니다');
      return;
    }

    setPending(true);
    setError(null);
    try {
      const response = await fetch('/api/monitoring/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cell,
          channel,
          destination: needsDestination ? destination.trim() : null,
          min_severity: minSeverity,
        }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(body?.message ?? `구독 실패 (HTTP ${response.status})`);
        return;
      }
      setCell('');
      setDestination('');
      router.refresh();
    } catch {
      setError('서비스에 연결하지 못했습니다');
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={subscribe}
      className="space-y-3 rounded-lg border border-surface-border bg-surface-raised/40 p-4"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block text-[11px] text-slate-500">
          셀
          <select
            value={cell}
            onChange={(event) => setCell(event.target.value)}
            disabled={pending}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface px-2.5 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none disabled:opacity-50"
          >
            <option value="">선택…</option>
            {cells.map((option) => (
              <option key={option.id} value={option.slug}>
                {option.slug}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-[11px] text-slate-500">
          전달 방법
          <select
            value={channel}
            onChange={(event) => setChannel(event.target.value as AlertChannel)}
            disabled={pending}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface px-2.5 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none disabled:opacity-50"
          >
            {ALERT_CHANNEL_CHOICES.map((option) => (
              <option key={option} value={option}>
                {ALERT_CHANNEL_LABEL[option]}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-[11px] text-slate-500">
          최소 등급
          <select
            value={minSeverity}
            onChange={(event) => setMinSeverity(event.target.value as AlertSeverity)}
            disabled={pending}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface px-2.5 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none disabled:opacity-50"
          >
            {ALERT_SEVERITY_ORDER.map((option) => (
              <option key={option} value={option}>
                {ALERT_SEVERITY_LABEL[option]} 이상
              </option>
            ))}
          </select>
        </label>

        <label className="block text-[11px] text-slate-500">
          웹훅 주소
          <input
            type="url"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            disabled={pending || !needsDestination}
            placeholder={needsDestination ? 'https://…' : '앱 내 알림은 불필요'}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface px-2.5 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none disabled:opacity-40"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] text-slate-600">
          최소 등급은 하한입니다 — 「보통 이상」을 고르면 높음도 받습니다. 등급에 미치지 못한 알림도
          목록에는 남고, 전달만 되지 않습니다.
        </p>
        <button
          type="submit"
          disabled={pending || !cell}
          className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
        >
          <BellPlus size={12} /> {pending ? '구독 중…' : '구독'}
        </button>
      </div>

      {error ? <p className="text-[11px] text-red-400">{error}</p> : null}
    </form>
  );
}
