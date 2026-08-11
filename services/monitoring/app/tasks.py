"""Celery tasks for `monitoring`. Queue name = service folder name.

**No beat here.** The scheduler lives with `regulation` because it drives ``source_schedules`` and
has no other consumer (CLAUDE.md § Celery Queue Architecture). Everything this service does is
triggered: by `regulation`'s diff stage saying an amendment landed, or by a delivery that failed and
scheduled its own retry with a countdown. A periodic tick would spend a query re-discovering work
that was already dispatched.

The only coupling to `regulation` is one task **name**, declared here because this service owns it.
Nothing here imports that service's task graph, and nothing here writes its tables — every read
across the seam goes through :mod:`app.store`.
"""

from __future__ import annotations

import uuid

import structlog

from regops_shared.db import sync_session

from .celery_app import celery_app
from .delivery import deliver_alert
from .routing import route_version

log = structlog.get_logger(__name__)

QUEUE = "monitoring"

#: Dispatched by `regulation`'s diff stage, by name. The constant exists so the string is written
#: once on this side of the seam.
ROUTE_TASK = "monitoring.route_change_events"
DELIVER_TASK = "monitoring.deliver_alert"


@celery_app.task(name=ROUTE_TASK, bind=True, max_retries=0)
def route_change_events(self, document_version_id: str) -> dict[str, object]:
    """An amendment landed: match subscriptions, grade it, compose alerts, hand them to delivery.

    ``max_retries=0`` for the reason the ingestion tasks use it: routing is idempotent by
    construction — the ``(tenant, cell, version)`` key means a re-run updates the same alert — so
    re-running the task *is* the retry, and a blind Celery retry would only redo work that
    already succeeded.
    """
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        result = route_version(session, version_id)

    for alert_id in result.alert_ids:
        celery_app.send_task(DELIVER_TASK, args=[str(alert_id)], queue=QUEUE)

    return {
        "document_version_id": document_version_id,
        "status": "routed",
        "events_seen": result.events_seen,
        # Non-substantive events dropped before composition. Surfaced rather than silent: a
        # renumbering-only amendment must generate no alert, and this is the only number that shows
        # the suppression working rather than the routing being broken.
        "events_suppressed": result.events_suppressed,
        "cells_seen": result.cells_seen,
        "cells_suppressed": result.cells_suppressed,
        "cells_without_subscribers": result.cells_without_subscribers,
        "alerts_created": result.alerts_created,
        "alerts_updated": result.alerts_updated,
    }


@celery_app.task(name=DELIVER_TASK, bind=True, max_retries=0)
def deliver(self, alert_id: str) -> dict[str, object]:
    """Attempt delivery to every eligible subscriber, then reschedule itself if anything failed.

    The retry is a ``countdown`` rather than a Celery ``retry()``: the backoff schedule belongs to
    the *delivery*, is recorded on the row as ``next_retry_at``, and has to survive a worker
    restart — none of which a task-level retry counter does. Re-running is safe, because a
    subscriber who has already been reached is skipped rather than told twice.
    """
    target = uuid.UUID(alert_id)
    with sync_session() as session:
        result = deliver_alert(session, target)

    if result.retry_in_seconds is not None:
        celery_app.send_task(
            DELIVER_TASK, args=[alert_id], queue=QUEUE, countdown=result.retry_in_seconds
        )
        log.info("deliver.retry_scheduled", alert_id=alert_id, seconds=result.retry_in_seconds)

    return {
        "alert_id": alert_id,
        "status": result.status.value,
        "attempted": result.attempted,
        "sent": result.sent,
        "failed": result.failed,
        "skipped": result.skipped,
        "exhausted": result.exhausted,
        "retry_in_seconds": result.retry_in_seconds,
    }


__all__ = ["DELIVER_TASK", "ROUTE_TASK", "deliver", "route_change_events"]
