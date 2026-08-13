import { formatDateTime } from '@/lib/format';
import {
  ALERT_CHANNEL_LABEL,
  DELIVERY_STATUS_LABEL,
  DELIVERY_STATUS_STYLE,
} from '@/types/constants';
import type { AlertDelivery } from '@/types/monitoring';

/**
 * Every attempt made to reach every subscriber — an append-only log, not a status field.
 *
 * *"It failed twice and then succeeded at 04:12"* is the fact an operator needs, and one row
 * overwritten in place cannot say it. The failure reason is the service's own, shown verbatim:
 * "HTTP 503" and "email delivery is not configured" send someone to entirely different places, and
 * a generic "전달 실패" would send them nowhere.
 *
 * An alert with **no attempts at all** is not a failure — it means no subscription was eligible,
 * usually because the alert sits below someone's severity floor. Saying so is the point; a blank
 * list would read as a bug.
 */
export function DeliveryList({ deliveries }: { deliveries: AlertDelivery[] }) {
  if (deliveries.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-surface-border px-3 py-2 text-[11px] text-slate-600">
        전달 시도가 없습니다 — 이 등급을 받기로 한 구독이 없다는 뜻입니다. 알림 자체는 이 목록에
        남아 있고, 구독 설정에서 최소 등급을 낮추면 다음 알림부터 전달됩니다.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {deliveries.map((delivery) => (
        <li
          key={delivery.id}
          className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-surface-border bg-surface px-3 py-2"
        >
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              DELIVERY_STATUS_STYLE[delivery.status] ?? ''
            }`}
          >
            {DELIVERY_STATUS_LABEL[delivery.status] ?? delivery.status}
          </span>
          <span className="font-mono text-[11px] text-slate-500">{delivery.attempt}회차</span>
          <span className="text-[11px] text-slate-500">
            {ALERT_CHANNEL_LABEL[delivery.channel] ?? delivery.channel}
          </span>
          <span className="font-mono text-[11px] text-slate-600">
            {formatDateTime(delivery.delivered_at ?? delivery.attempted_at)}
          </span>
          {delivery.next_retry_at ? (
            <span className="font-mono text-[11px] text-amber-400/80">
              재시도 {formatDateTime(delivery.next_retry_at)}
            </span>
          ) : null}
          {delivery.error ? (
            <span className="w-full font-mono text-[11px] text-red-400/90">{delivery.error}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
