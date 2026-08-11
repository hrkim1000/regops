"""Delivery: one row per attempt, a pluggable channel seam, and backoff that respects the gate.

A wedged mail relay must not stop ingestion, and a failed delivery must not disappear. Both fall out
of the same shape: the attempt row is written **before** the send, so a worker killed mid-attempt
leaves a ``PENDING`` row rather than no trace, and every outcome — including the exhausted one — is
a row somebody can query.

**Retries are Celery countdowns, not a table poll.** `monitoring` runs no beat: the scheduler lives
with `regulation` because it drives ``source_schedules`` and has no other consumer (CLAUDE.md
§ Celery Queue Architecture), and a sweep here would spend a periodic query re-discovering work that
was already scheduled the moment it failed.

**Backoff is capped at six hours** rather than growing without bound. The gate is publication →
alert within 24 hours; a delay schedule that stretches into day two would let a relay that recovers
late report a success that missed the only deadline that matters.

The channel seam is a protocol with three implementations, and one of them refuses on purpose:
there is no mail relay in the stack, so ``EMAIL`` fails loudly and lands in ``alert_deliveries``
with a reason. A channel that quietly returned success would be a silent hole in the coverage story
— the alerting equivalent of an answer with no citation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    DELIVERY_MAX_ATTEMPTS,
    SEVERITY_ORDER,
    AlertChannel,
    AlertStatus,
    DeliveryStatus,
    delivery_backoff_seconds,
)
from regops_shared.models.base import utcnow
from regops_shared.settings import get_settings

from .models import Alert, AlertDelivery, AlertSubscription

log = structlog.get_logger(__name__)

#: Longest error text kept on the row. The full exception goes to the log; this is what an operator
#: reads next to the delivery in a list.
ERROR_MAX_CHARS = 512


class DeliveryError(RuntimeError):
    """A delivery attempt failed in a way worth retrying."""


class Channel(Protocol):
    """The seam. A new transport is a class here, never a branch in the delivery loop."""

    name: AlertChannel

    def send(self, *, alert: Alert, destination: str | None) -> None:
        """Deliver, or raise :class:`DeliveryError`. Returning is success."""


class InAppChannel:
    """The default, and the one that cannot fail: the alert row *is* the delivery.

    Recording it anyway is the point — "delivered in-app at 04:12" and "never routed to this
    subscriber" are different facts, and only the attempt log can tell them apart.
    """

    name = AlertChannel.IN_APP

    def send(self, *, alert: Alert, destination: str | None) -> None:
        return None


class WebhookChannel:
    """POST the alert to a subscriber-configured URL.

    The payload is the alert as the API renders it, minus the clause list: a webhook is a signal to
    go and look, and a 40-clause body is a payload some receivers silently truncate.
    """

    name = AlertChannel.WEBHOOK

    def __init__(self, timeout: float | None = None) -> None:
        self._timeout = timeout if timeout is not None else get_settings().http_timeout_seconds

    def send(self, *, alert: Alert, destination: str | None) -> None:
        if not destination:
            raise DeliveryError("webhook subscription has no destination")
        payload = {
            "alert_id": str(alert.id),
            "cell_id": str(alert.cell_id),
            "severity": alert.severity.value,
            "title": alert.title,
            "summary": alert.summary,
            "clause_count": alert.clause_count,
            "document_id": str(alert.document_id),
            "document_version_id": str(alert.document_version_id),
            "detected_at": alert.detected_at.isoformat(),
        }
        try:
            response = httpx.post(destination, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise DeliveryError(f"transport failure: {exc}") from exc
        if response.status_code >= 400:
            raise DeliveryError(f"receiver returned HTTP {response.status_code}")


class EmailChannel:
    """Declared, unimplemented, and failing loudly until a relay exists.

    Phase 1 ships no SMTP configuration. Refusing here puts the fact in ``alert_deliveries`` with a
    reason, where an operator finds it; a silent success would put it nowhere at all.
    """

    name = AlertChannel.EMAIL

    def send(self, *, alert: Alert, destination: str | None) -> None:
        raise DeliveryError("email delivery is not configured in this deployment")


def default_channels() -> dict[AlertChannel, Channel]:
    return {
        AlertChannel.IN_APP: InAppChannel(),
        AlertChannel.WEBHOOK: WebhookChannel(),
        AlertChannel.EMAIL: EmailChannel(),
    }


@dataclass(slots=True)
class DeliveryPass:
    """One pass over an alert's subscribers."""

    alert_id: uuid.UUID
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    #: Subscriptions already delivered, or below the alert's severity — no attempt was made.
    skipped: int = 0
    #: Subscriptions whose attempts ran out. Abandoned, and visible as abandoned.
    exhausted: int = 0
    #: Seconds until this alert should be retried, or ``None`` when nothing is retriable.
    retry_in_seconds: int | None = None
    status: AlertStatus = AlertStatus.PENDING


def deliver_alert(
    session: Session,
    alert_id: uuid.UUID,
    *,
    channels: dict[AlertChannel, Channel] | None = None,
) -> DeliveryPass:
    """Attempt delivery to every eligible subscriber. Idempotent; re-running is the retry."""
    result = DeliveryPass(alert_id=alert_id)
    alert = session.get(Alert, alert_id)
    if alert is None:
        log.warning("deliver.unknown_alert", alert_id=str(alert_id))
        return result

    channels = channels or default_channels()
    backoffs: list[int] = []

    for subscription in _eligible(session, alert):
        history = _attempts(session, alert_id, subscription.id)
        if any(row.status is DeliveryStatus.SENT for row in history):
            result.skipped += 1
            continue
        if len(history) >= DELIVERY_MAX_ATTEMPTS:
            result.exhausted += 1
            continue

        attempt = len(history) + 1
        delivery = AlertDelivery(
            tenant_id=alert.tenant_id,
            alert_id=alert.id,
            subscription_id=subscription.id,
            channel=subscription.channel,
            destination=subscription.destination,
            attempt=attempt,
            status=DeliveryStatus.PENDING,
            attempted_at=utcnow(),
        )
        session.add(delivery)
        # Committed before the send so that a worker killed mid-attempt leaves the attempt on the
        # record. Without this the retry would reuse the same attempt number and the history would
        # show fewer tries than were actually made against a struggling receiver.
        session.commit()
        result.attempted += 1

        channel = channels.get(subscription.channel)
        try:
            if channel is None:
                raise DeliveryError(f"no channel implementation for {subscription.channel.value}")
            channel.send(alert=alert, destination=subscription.destination)
        except DeliveryError as exc:
            delivery.status = DeliveryStatus.FAILED
            delivery.error = str(exc)[:ERROR_MAX_CHARS]
            result.failed += 1
            if attempt < DELIVERY_MAX_ATTEMPTS:
                wait = delivery_backoff_seconds(attempt)
                delivery.next_retry_at = utcnow() + timedelta(seconds=wait)
                backoffs.append(wait)
            else:
                result.exhausted += 1
            log.warning(
                "deliver.failed",
                alert_id=str(alert_id),
                subscription_id=str(subscription.id),
                attempt=attempt,
                error=str(exc),
            )
        else:
            delivery.status = DeliveryStatus.SENT
            delivery.delivered_at = utcnow()
            result.sent += 1
        session.commit()

    result.retry_in_seconds = min(backoffs) if backoffs else None
    result.status = refresh_status(session, alert)
    session.commit()
    log.info(
        "deliver.done",
        alert_id=str(alert_id),
        sent=result.sent,
        failed=result.failed,
        exhausted=result.exhausted,
        status=result.status.value,
    )
    return result


def refresh_status(session: Session, alert: Alert) -> AlertStatus:
    """Derive the alert's status from its attempt log. Flushes; the caller commits.

    Three values, and the ordering matters. ``PENDING`` means *delivery work is outstanding* — so an
    alert with no eligible subscription at all is ``DELIVERED`` with zero deliveries rather than
    pending forever over work nobody is going to do. The delivery count is on the API response, so
    "delivered to nobody" stays legible instead of hiding behind the word.
    """
    rows = list(session.scalars(select(AlertDelivery).where(AlertDelivery.alert_id == alert.id)))
    by_subscription: dict[uuid.UUID, list[AlertDelivery]] = {}
    for row in rows:
        by_subscription.setdefault(row.subscription_id, []).append(row)

    retriable = any(
        not any(row.status is DeliveryStatus.SENT for row in history)
        and len(history) < DELIVERY_MAX_ATTEMPTS
        for history in by_subscription.values()
    )
    if retriable:
        alert.status = AlertStatus.PENDING
    elif any(row.status is DeliveryStatus.SENT for row in rows):
        alert.status = AlertStatus.DELIVERED
    elif rows:
        alert.status = AlertStatus.FAILED
    else:
        alert.status = AlertStatus.DELIVERED

    session.flush()
    return alert.status


# --- lookups -----------------------------------------------------------------------------------


def _eligible(session: Session, alert: Alert) -> list[AlertSubscription]:
    """Enabled subscriptions on this alert's cell and tenant, at or below its severity.

    ``min_severity`` is a floor, not an equality: someone asking for ``MEDIUM`` still hears about a
    ``HIGH``. Filtering here rather than at composition time is deliberate — a below-threshold alert
    still exists and is still readable in the list, it is simply not pushed.
    """
    threshold = SEVERITY_ORDER.index(alert.severity)
    subscriptions = session.scalars(
        select(AlertSubscription).where(
            AlertSubscription.cell_id == alert.cell_id,
            AlertSubscription.enabled.is_(True),
            AlertSubscription.tenant_id.is_(None)
            if alert.tenant_id is None
            else AlertSubscription.tenant_id == alert.tenant_id,
        )
    )
    return [
        subscription
        for subscription in subscriptions
        if SEVERITY_ORDER.index(subscription.min_severity) <= threshold
    ]


def _attempts(
    session: Session, alert_id: uuid.UUID, subscription_id: uuid.UUID
) -> list[AlertDelivery]:
    return list(
        session.scalars(
            select(AlertDelivery)
            .where(
                AlertDelivery.alert_id == alert_id,
                AlertDelivery.subscription_id == subscription_id,
            )
            .order_by(AlertDelivery.attempt)
        )
    )


__all__ = [
    "Channel",
    "DeliveryError",
    "DeliveryPass",
    "EmailChannel",
    "InAppChannel",
    "WebhookChannel",
    "default_channels",
    "deliver_alert",
    "refresh_status",
]
