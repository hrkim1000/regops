'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import {
  ALERT_CHANNEL_LABEL,
  ALERT_SEVERITY_LABEL,
  ALERT_SEVERITY_ORDER,
} from '@/types/constants';
import type { AlertSeverity, AlertSubscription } from '@/types/monitoring';

/**
 * One standing subscription: raise the floor, or switch it off.
 *
 * **Disable rather than delete, and the copy says why.** A deleted subscription takes its delivery
 * history with it (`ON DELETE CASCADE`), and *"we did tell them, three times"* is exactly the
 * record an audit after a missed amendment asks for. There is deliberately no delete control here.
 */
export function SubscriptionRow({ subscription }: { subscription: AlertSubscription }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function patch(body: Record<string, unknown>) {
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`/api/monitoring/subscriptions/${subscription.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(payload?.message ?? `변경 실패 (HTTP ${response.status})`);
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
    <li
      className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-surface-border bg-surface-raised/40 px-4 py-3 ${
        subscription.enabled ? '' : 'opacity-60'
      }`}
    >
      <span className="font-mono text-xs text-slate-200">{subscription.cell}</span>

      <span className="text-[11px] text-slate-500">
        {ALERT_CHANNEL_LABEL[subscription.channel] ?? subscription.channel}
      </span>

      {subscription.destination ? (
        <span
          className="max-w-xs truncate font-mono text-[11px] text-slate-600"
          title={subscription.destination}
        >
          {subscription.destination}
        </span>
      ) : null}

      <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
        최소 등급
        <select
          value={subscription.min_severity}
          onChange={(event) => patch({ min_severity: event.target.value as AlertSeverity })}
          disabled={pending}
          className="rounded-md border border-surface-border bg-surface px-2 py-1 text-xs text-slate-200 focus:border-accent focus:outline-none disabled:opacity-50"
        >
          {ALERT_SEVERITY_ORDER.map((option) => (
            <option key={option} value={option}>
              {ALERT_SEVERITY_LABEL[option]} 이상
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        onClick={() => patch({ enabled: !subscription.enabled })}
        disabled={pending}
        className="ml-auto rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
      >
        {pending ? '변경 중…' : subscription.enabled ? '중지' : '재개'}
      </button>

      {error ? <span className="w-full text-[11px] text-red-400">{error}</span> : null}
    </li>
  );
}
