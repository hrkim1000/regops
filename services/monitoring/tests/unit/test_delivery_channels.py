"""The channel seam and the backoff schedule — everything about delivery that needs no database.

The three channels differ in exactly the way that matters: one cannot fail, one fails on the
transport, and one refuses because it is not configured. That last is the point of the test file: an
unimplemented channel that quietly returned success would be a silent hole in the coverage story,
and the delivery log would show a delivery that never happened.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.delivery import DeliveryError, EmailChannel, InAppChannel, WebhookChannel
from regops_shared.constants import (
    DELIVERY_BACKOFF_BASE_SECONDS,
    DELIVERY_BACKOFF_CAP_SECONDS,
    DELIVERY_MAX_ATTEMPTS,
    AlertSeverity,
    delivery_backoff_seconds,
)
from regops_shared.models import Alert


def _alert() -> Alert:
    return Alert(
        id=uuid.uuid4(),
        cell_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        severity=AlertSeverity.HIGH,
        title="화장품법 — 조문 3건 변경",
        summary="…",
        clause_count=3,
        detected_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_in_app_delivery_cannot_fail() -> None:
    """The alert row *is* the delivery. Recording the attempt is still the point: "delivered
    in-app" and "never routed to this subscriber" are different facts."""
    assert InAppChannel().send(alert=_alert(), destination=None) is None


def test_email_refuses_loudly_rather_than_dropping() -> None:
    with pytest.raises(DeliveryError, match="not configured"):
        EmailChannel().send(alert=_alert(), destination="ra@example.test")


def test_a_webhook_without_a_destination_is_a_delivery_error_not_a_crash() -> None:
    with pytest.raises(DeliveryError, match="no destination"):
        WebhookChannel().send(alert=_alert(), destination=None)


def test_a_webhook_posts_the_alert_and_succeeds_on_2xx(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(202)

    monkeypatch.setattr(httpx, "post", fake_post)
    alert = _alert()

    WebhookChannel().send(alert=alert, destination="https://receiver.test/hook")

    assert captured["url"] == "https://receiver.test/hook"
    payload = captured["json"]
    assert payload["alert_id"] == str(alert.id)
    assert payload["severity"] == AlertSeverity.HIGH.value
    # The clause list is deliberately not in the payload: a webhook is a signal to go and look, and
    # a 40-clause body is what some receivers silently truncate.
    assert "clause_references" not in payload


def test_a_receiver_error_is_a_retryable_delivery_error(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: httpx.Response(503))

    with pytest.raises(DeliveryError, match="HTTP 503"):
        WebhookChannel().send(alert=_alert(), destination="https://receiver.test/hook")


def test_a_transport_failure_is_a_retryable_delivery_error(monkeypatch) -> None:
    def explode(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", explode)

    with pytest.raises(DeliveryError, match="transport failure"):
        WebhookChannel().send(alert=_alert(), destination="https://receiver.test/hook")


# --- backoff ------------------------------------------------------------------------------------


def test_backoff_doubles_from_one_minute() -> None:
    assert delivery_backoff_seconds(1) == DELIVERY_BACKOFF_BASE_SECONDS
    assert delivery_backoff_seconds(2) == DELIVERY_BACKOFF_BASE_SECONDS * 2
    assert delivery_backoff_seconds(3) == DELIVERY_BACKOFF_BASE_SECONDS * 4


def test_backoff_is_capped_so_a_late_recovery_cannot_outlast_the_gate() -> None:
    """The gate is publication → alert within 24h. Unbounded backoff would let a receiver that
    recovers on day two report a success that missed the only deadline that matters."""
    assert delivery_backoff_seconds(50) == DELIVERY_BACKOFF_CAP_SECONDS

    total = sum(delivery_backoff_seconds(n) for n in range(1, DELIVERY_MAX_ATTEMPTS))
    assert total < 24 * 60 * 60
