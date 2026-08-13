import { ChevronLeft } from 'lucide-react';
import Link from 'next/link';

import { EmptyState } from '@/components/EmptyState';
import { serverGet } from '@/lib/server-api';
import type { AlertSubscription } from '@/types/monitoring';
import type { Cell } from '@/types/regulation';

import { SubscriptionForm } from './_components/SubscriptionForm';
import { SubscriptionRow } from './_components/SubscriptionRow';

export const dynamic = 'force-dynamic';

/**
 * Standing subscriptions — the routing rule, managed by the person it routes to.
 *
 * **Cell is the only routing dimension in Phase 1**, and the copy says so rather than leaving a
 * reader to infer that "구독" means their product is covered. Per ADR-0007 an IR applies to a cell
 * until the Product context exists, so a subscription can promise *"something in this cell changed"*
 * and nothing more; product-profile routing arrives with `compliance` in phase 2.2, where it is
 * tenant-scoped by construction (ADR-0009 decision 5).
 *
 * Subscribing is an ordinary action — the two restricted ones in Phase 1 are locking an IR and
 * resolving a structure-drift alert, because those are where a human assertion enters the audit
 * trail. So there is no role gate here; the endpoint scopes every read and write to the caller.
 */
export default async function SubscriptionsPage() {
  // Independent fetches — a failed cell list must still leave existing subscriptions manageable.
  const subscriptions = await serverGet<AlertSubscription[]>('monitoring', '/subscriptions');
  const cells = await serverGet<Cell[]>('regulation', '/cells');

  const subscribed = new Set((subscriptions ?? []).map((row) => row.cell));
  const available = (cells ?? []).filter((cell) => !subscribed.has(cell.slug));

  return (
    <div className="space-y-6">
      <Link
        href="/monitoring"
        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
      >
        <ChevronLeft size={12} /> 변경 모니터링
      </Link>

      <div>
        <h1 className="text-lg font-semibold text-slate-100">구독 설정</h1>
        <p className="mt-1 text-xs text-slate-500">
          구독 단위는 <span className="font-mono text-slate-400">셀</span>(규제기관 × 제품군)입니다.
          이 셀에서 개정이 감지되면 알림을 받습니다 — 개별 제품에 실제로 영향이 있는지까지는 판단하지
          않습니다. 제품 단위 판단은 Phase 2의 적합성 분석에서 다룹니다.
        </p>
      </div>

      {cells === null ? (
        <EmptyState
          title="셀 목록을 불러오지 못했습니다"
          hint="regulation 서비스 상태를 확인하세요."
        />
      ) : available.length > 0 ? (
        <SubscriptionForm cells={available} />
      ) : (
        <p className="rounded-lg border border-dashed border-surface-border px-4 py-3 text-[11px] text-slate-600">
          8개 셀을 모두 구독하고 있습니다. 각 구독의 최소 등급은 아래에서 조정할 수 있습니다.
        </p>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-slate-300">
          내 구독{' '}
          <span className="font-mono text-xs text-slate-600">{subscriptions?.length ?? 0}</span>
        </h2>

        {subscriptions === null ? (
          <EmptyState
            title="구독 목록을 불러오지 못했습니다"
            hint="monitoring 서비스 상태를 확인하세요."
          />
        ) : subscriptions.length === 0 ? (
          <EmptyState
            title="구독 중인 셀이 없습니다"
            hint="구독하지 않아도 개정 감지는 계속됩니다 — 다만 알림이 만들어지지 않고, 그 셀의 탐지 커버리지는 0%로 보고됩니다."
          />
        ) : (
          <ul className="space-y-2">
            {subscriptions.map((subscription) => (
              <SubscriptionRow key={subscription.id} subscription={subscription} />
            ))}
          </ul>
        )}

        <p className="text-[11px] text-slate-600">
          구독을 삭제하는 대신 «중지»합니다 — 삭제하면 전달 이력이 함께 사라지고, 「세 번 알렸다」는
          기록은 개정을 놓친 뒤 감사에서 가장 먼저 확인하는 것입니다.
        </p>
      </section>
    </div>
  );
}
