"""Reading alerts, assigning an owner, the daily briefing, and the two gates this pillar carries.

Four surfaces:

- **The list and the detail.** An alert carries every clause it covers, so "what actually changed"
  is answerable without going back across the seam into ``clause_diffs``.
- **Assignment.** Recorded, attributed and written to the audit chain (ADR-0011). An alert nobody
  owns is an alert nobody actions, and "who was told to deal with this" is the first question asked
  after a missed amendment.
- **The briefing.** Composed on read, per subscriber, rolling 24 hours, dates rendered in the
  authority's own timezone.
- **The metrics.** Detection coverage and detection latency are two of the six Go/No-Go gates, and
  neither is self-guarding: a system that alerts on everything scores perfectly on coverage, and one
  that never resolves a publication date can report a latency of zero. So coverage is reported
  against the *emitted* event count from the other side of the seam, and latency separates the
  measurable cases from the ones where the authority published no date at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from regops_shared.api import Meta, ok
from regops_shared.audit import record
from regops_shared.auth import Principal, get_current_principal, require_roles
from regops_shared.constants import (
    DETECTION_LATENCY_TARGET_HOURS,
    AlertSeverity,
    AlertStatus,
    Role,
)
from regops_shared.db import AsyncSession, get_db
from regops_shared.models.base import utcnow

from ...briefing import compose_briefing, local_timestamp
from ...models import Alert, AlertDelivery, AlertSubscription
from ...store import cells_by_id_async, change_event_totals_async, document_titles_async

router = APIRouter(prefix="/api/v1", tags=["monitoring"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]

SERVICE = "monitoring"

ALERT_PAGE_SIZE = 50
ALERT_PAGE_SIZE_MAX = 200


class AssignRequest(BaseModel):
    owner_id: uuid.UUID = Field(description="Who is to deal with this change")


@router.get("/alerts")
async def list_alerts(
    db: DbSession,
    _: CurrentUser,
    cell_id: uuid.UUID | None = None,
    severity: Annotated[list[AlertSeverity] | None, Query(description="Filter by grade")] = None,
    alert_status: Annotated[
        list[AlertStatus] | None, Query(alias="status", description="Filter by delivery state")
    ] = None,
    unassigned: Annotated[
        bool | None, Query(description="true returns only alerts nobody owns yet")
    ] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(ALERT_PAGE_SIZE, ge=1, le=ALERT_PAGE_SIZE_MAX),
) -> dict[str, Any]:
    """Alerts, most recently detected first."""
    stmt = select(Alert)
    count_stmt = select(func.count()).select_from(Alert)

    for predicate in _filters(
        cell_id=cell_id, severity=severity, alert_status=alert_status, unassigned=unassigned
    ):
        stmt = stmt.where(predicate)
        count_stmt = count_stmt.where(predicate)

    total = await db.scalar(count_stmt) or 0
    rows = list(
        await db.scalars(
            stmt.order_by(Alert.detected_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    cells = await cells_by_id_async(db, [row.cell_id for row in rows])
    titles = await document_titles_async(db, [row.document_id for row in rows])
    deliveries = await _delivery_counts(db, [row.id for row in rows])

    return ok(
        [
            _alert_summary(
                row,
                cell_slug=cells[row.cell_id].slug if row.cell_id in cells else "",
                document_title=titles.get(row.document_id, ""),
                delivery_counts=deliveries.get(row.id, (0, 0, 0)),
            )
            for row in rows
        ],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    """One alert with every clause it covers and every delivery attempt made for it."""
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")

    cells = await cells_by_id_async(db, [alert.cell_id])
    titles = await document_titles_async(db, [alert.document_id])
    attempts = list(
        await db.scalars(
            select(AlertDelivery)
            .where(AlertDelivery.alert_id == alert_id)
            .order_by(AlertDelivery.subscription_id, AlertDelivery.attempt)
        )
    )
    cell = cells.get(alert.cell_id)

    payload = _alert_summary(
        alert,
        cell_slug=cell.slug if cell else "",
        document_title=titles.get(alert.document_id, ""),
        delivery_counts=_counts_from(attempts),
    )
    payload["summary"] = alert.summary
    payload["clause_references"] = alert.clause_references or []
    payload["change_event_ids"] = [str(value) for value in alert.change_event_ids]
    payload["detected_at_local"] = local_timestamp(
        alert.detected_at, cell.authority if cell else ""
    )
    payload["deliveries"] = [
        {
            "id": str(row.id),
            "subscription_id": str(row.subscription_id),
            "channel": row.channel.value,
            "attempt": row.attempt,
            "status": row.status.value,
            "error": row.error,
            "attempted_at": row.attempted_at.isoformat(),
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
        }
        for row in attempts
    ]
    return ok(payload)


@router.post("/alerts/{alert_id}/assign")
async def assign_alert(
    alert_id: uuid.UUID,
    body: AssignRequest,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
) -> dict[str, Any]:
    """Give this change an owner. **Audited.**

    Reassignment is allowed and is also audited: the chain records every hand-off rather than only
    the last one, because "it sat with the wrong person for three weeks" is a finding the final
    state cannot show.
    """
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")

    previous = alert.owner_id
    alert.owner_id = body.owner_id
    alert.assigned_by = principal.id
    alert.assigned_at = utcnow()
    await record(
        db,
        service=SERVICE,
        action="alert.assigned",
        actor_id=principal.id,
        entity_type="alert",
        entity_id=alert_id,
        payload={
            "owner_id": str(body.owner_id),
            "previous_owner_id": str(previous) if previous else None,
            "severity": alert.severity.value,
            "cell_id": str(alert.cell_id),
            "document_version_id": str(alert.document_version_id),
        },
    )
    await db.commit()
    return ok(
        {
            "id": str(alert_id),
            "owner_id": str(alert.owner_id),
            "assigned_by": str(principal.id),
            "assigned_at": alert.assigned_at.isoformat(),
        }
    )


@router.get("/briefing")
async def get_briefing(
    db: DbSession,
    principal: CurrentUser,
    subscriber_id: Annotated[
        uuid.UUID | None, Query(description="Admin only; defaults to the caller")
    ] = None,
    window_hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    """The daily change briefing, composed on read."""
    target = subscriber_id or principal.id
    if target != principal.id and principal.role is not Role.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an admin may read another user's briefing"
        )

    briefing = await compose_briefing(db, subscriber_id=target, window_hours=window_hours)
    return ok(
        {
            "subscriber_id": str(briefing.subscriber_id),
            "window_start": briefing.window_start.isoformat(),
            "window_end": briefing.window_end.isoformat(),
            "cells": briefing.cell_slugs,
            "severity_counts": briefing.severity_counts,
            "unassigned": briefing.unassigned,
            "entries": [
                {
                    "alert_id": str(entry.alert_id),
                    "cell": entry.cell_slug,
                    "severity": entry.severity.value,
                    "title": entry.title,
                    "document_title": entry.document_title,
                    "clause_count": entry.clause_count,
                    "locked_ir_count": entry.locked_ir_count,
                    "detected_at_local": entry.detected_at_local,
                    "owner_id": str(entry.owner_id) if entry.owner_id else None,
                }
                for entry in briefing.entries
            ],
        }
    )


@router.get("/metrics/alerts")
async def alert_metrics(
    db: DbSession,
    _: CurrentUser,
    days: int = Query(30, ge=1, le=365, description="Window, in days back from now"),
) -> dict[str, Any]:
    """Detection coverage and detection latency, per cell — the two gates this pillar carries.

    **Coverage** is alerted events over emitted events, and the denominator is read across the seam
    from ``change_events``. Reporting only what was alerted would let a routing bug look like
    perfect coverage. ``subscribers`` is beside it so a cell at 0% reads as *nobody asked* rather
    than as a failure.

    **Latency** is publication → alert, reported twice on purpose: ``from_published`` where the
    authority stated a publication date, and ``from_retrieved`` — always measurable — as the bound
    our own clock puts on it. ``unmeasurable`` counts the alerts with no publication date, which
    ADR-0003 decision 5 requires be reported as unmeasurable rather than as zero.
    """
    since = utcnow() - timedelta(days=days)

    alerts = list(await db.scalars(select(Alert).where(Alert.detected_at >= since)))
    emitted = await change_event_totals_async(db, since=since)
    cells = await cells_by_id_async(db, list({*emitted, *(alert.cell_id for alert in alerts)}))
    subscribers = dict(
        (
            await db.execute(
                select(AlertSubscription.cell_id, func.count())
                .where(AlertSubscription.enabled.is_(True))
                .group_by(AlertSubscription.cell_id)
            )
        ).all()
    )

    per_cell: list[dict[str, Any]] = []
    for cell_id in sorted(cells, key=lambda key: cells[key].slug):
        scoped = [alert for alert in alerts if alert.cell_id == cell_id]
        alerted_events = {event_id for alert in scoped for event_id in alert.change_event_ids}
        total_emitted = emitted.get(cell_id, 0)
        per_cell.append(
            {
                "cell": cells[cell_id].slug,
                "subscribers": subscribers.get(cell_id, 0),
                "alerts": len(scoped),
                "change_events_emitted": total_emitted,
                "change_events_alerted": len(alerted_events),
                "coverage": (
                    round(len(alerted_events) / total_emitted, 4) if total_emitted else None
                ),
                "severity": {
                    grade.value: sum(1 for alert in scoped if alert.severity is grade)
                    for grade in AlertSeverity
                },
                "latency_hours": _latency(scoped),
            }
        )

    return ok(
        {
            "window_days": days,
            "target_hours": DETECTION_LATENCY_TARGET_HOURS,
            "cells": per_cell,
        }
    )


# --- shaping ---------------------------------------------------------------------------------


def _filters(
    *,
    cell_id: uuid.UUID | None,
    severity: list[AlertSeverity] | None,
    alert_status: list[AlertStatus] | None,
    unassigned: bool | None,
) -> list[Any]:
    predicates: list[Any] = []
    if cell_id is not None:
        predicates.append(Alert.cell_id == cell_id)
    if severity:
        predicates.append(Alert.severity.in_(tuple(severity)))
    if alert_status:
        predicates.append(Alert.status.in_(tuple(alert_status)))
    if unassigned is not None:
        predicates.append(Alert.owner_id.is_(None) if unassigned else Alert.owner_id.is_not(None))
    return predicates


def _latency(alerts: list[Alert]) -> dict[str, Any]:
    """Publication → alert, in hours, from both clocks.

    ``max`` rather than a mean: the gate is a ceiling, and a mean that hides one 40-hour outlier
    behind ninety fast ones would report a pass on a run that failed.
    """

    def hours(start: datetime | None, alert: Alert) -> float | None:
        if start is None:
            return None
        return round((alert.created_at - start).total_seconds() / 3600.0, 3)

    published = [
        value for alert in alerts if (value := hours(alert.published_at, alert)) is not None
    ]
    retrieved = [
        value for alert in alerts if (value := hours(alert.retrieved_at, alert)) is not None
    ]

    def block(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "max": None, "within_target": None}
        return {
            "count": len(values),
            "max": max(values),
            "within_target": sum(1 for value in values if value <= DETECTION_LATENCY_TARGET_HOURS),
        }

    return {
        "from_published": block(published),
        "from_retrieved": block(retrieved),
        # Not zero, and not silently dropped: a source that publishes no date makes its own latency
        # unmeasurable, and a gate report has to say so (ADR-0003 decision 5).
        "unmeasurable": sum(1 for alert in alerts if alert.published_at is None),
    }


async def _delivery_counts(
    db: AsyncSession, alert_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int, int]]:
    """``{alert_id: (attempts, sent, failed)}`` for a whole page in one query."""
    if not alert_ids:
        return {}
    rows = list(
        await db.scalars(select(AlertDelivery).where(AlertDelivery.alert_id.in_(alert_ids)))
    )
    grouped: dict[uuid.UUID, list[AlertDelivery]] = {}
    for row in rows:
        grouped.setdefault(row.alert_id, []).append(row)
    return {alert_id: _counts_from(history) for alert_id, history in grouped.items()}


def _counts_from(attempts: list[AlertDelivery]) -> tuple[int, int, int]:
    from regops_shared.constants import DeliveryStatus

    return (
        len(attempts),
        sum(1 for row in attempts if row.status is DeliveryStatus.SENT),
        sum(1 for row in attempts if row.status is DeliveryStatus.FAILED),
    )


def _alert_summary(
    alert: Alert,
    *,
    cell_slug: str,
    document_title: str,
    delivery_counts: tuple[int, int, int],
) -> dict[str, Any]:
    attempts, sent, failed = delivery_counts
    return {
        "id": str(alert.id),
        "cell_id": str(alert.cell_id),
        "cell": cell_slug,
        "severity": alert.severity.value,
        "status": alert.status.value,
        "title": alert.title,
        "document_id": str(alert.document_id),
        "document_title": document_title,
        "document_version_id": str(alert.document_version_id),
        "from_version_id": str(alert.from_version_id) if alert.from_version_id else None,
        "clause_count": alert.clause_count,
        "cited_by_locked_ir": alert.cited_by_locked_ir,
        "locked_ir_count": alert.locked_ir_count,
        "published_at": alert.published_at.isoformat() if alert.published_at else None,
        "retrieved_at": alert.retrieved_at.isoformat() if alert.retrieved_at else None,
        "detected_at": alert.detected_at.isoformat(),
        "created_at": alert.created_at.isoformat(),
        "owner_id": str(alert.owner_id) if alert.owner_id else None,
        "assigned_at": alert.assigned_at.isoformat() if alert.assigned_at else None,
        "delivery": {"attempts": attempts, "sent": sent, "failed": failed},
    }


__all__ = ["router"]
