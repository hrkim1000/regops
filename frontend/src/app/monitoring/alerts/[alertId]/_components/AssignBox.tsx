'use client';

import { UserCheck } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { UserSummary } from '@/types/monitoring';

/**
 * Give a change an owner. **Audited** — the assignment is written to the hash chain (ADR-0011).
 *
 * A client island because it writes. Reassignment is allowed and is audited too: the chain records
 * every hand-off rather than only the last one, because *"it sat with the wrong person for three
 * weeks"* is a finding the final state cannot show.
 *
 * Hiding this from a `viewer` is cosmetic and known to be: the endpoint re-checks the role and 403s
 * regardless, and this component never sees a token to spend.
 */
export function AssignBox({
  alertId,
  users,
  currentOwnerId,
}: {
  alertId: string;
  users: UserSummary[];
  currentOwnerId: string | null;
}) {
  const router = useRouter();
  const [ownerId, setOwnerId] = useState(currentOwnerId ?? '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function assign(event: React.FormEvent) {
    event.preventDefault();
    if (!ownerId || pending) return;

    setPending(true);
    setError(null);
    try {
      const response = await fetch(`/api/monitoring/alerts/${alertId}/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner_id: ownerId }),
      });
      if (!response.ok) {
        // The service's own reason: a 403 here means the role does not permit it, which is a
        // different thing to say than "assignment failed".
        const body = (await response.json().catch(() => null)) as { message?: string } | null;
        setError(body?.message ?? `담당자 지정 실패 (HTTP ${response.status})`);
        return;
      }
      router.refresh();
    } catch {
      setError('서비스에 연결하지 못했습니다');
    } finally {
      setPending(false);
    }
  }

  const changed = ownerId !== (currentOwnerId ?? '');

  return (
    <form onSubmit={assign} className="flex flex-wrap items-center gap-2">
      <label htmlFor="alert-owner" className="sr-only">
        담당자
      </label>
      <select
        id="alert-owner"
        value={ownerId}
        onChange={(event) => setOwnerId(event.target.value)}
        disabled={pending}
        className="rounded-md border border-surface-border bg-surface px-2.5 py-1.5 text-xs text-slate-200 focus:border-accent focus:outline-none disabled:opacity-50"
      >
        <option value="">담당자 선택…</option>
        {users.map((user) => (
          <option key={user.id} value={user.id}>
            {user.email} ({user.role})
          </option>
        ))}
      </select>

      <button
        type="submit"
        disabled={pending || !ownerId || !changed}
        className="inline-flex items-center gap-1.5 rounded-md border border-surface-border px-2.5 py-1.5 text-xs text-slate-300 transition-colors hover:border-slate-500 disabled:opacity-50"
      >
        <UserCheck size={12} />
        {pending ? '지정 중…' : currentOwnerId ? '담당자 변경' : '담당자 지정'}
      </button>

      {error ? <span className="text-[11px] text-red-400">{error}</span> : null}
    </form>
  );
}
