"""The daily change briefing — composed on read, never stored.

Storing it would be a third copy of facts ``alerts`` already holds, and the copy that goes stale the
moment an alert is assigned or re-graded. Composing on read also means a subscriber who changes
their subscriptions sees the briefing their *current* interests imply rather than the one a batch
job wrote at 06:00.

**Dates are rendered in the authority's own timezone.** This is the one thing
:func:`regops_shared.constants.version_status` explicitly defers to this phase: it evaluates the
effective-date boundary in UTC and notes that a Korean date reads as pending for nine hours after it
takes effect in Korea — harmless on a browser label, wrong on a briefing whose whole subject is
*when* things changed.

The window is a **rolling 24 hours** rather than a calendar day. A subscriber may hold cells across
authorities in different timezones, and a calendar-day briefing would need a day boundary that is
wrong for at least one of them; a rolling window has no boundary to get wrong and no gap for an
alert to fall into between two runs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from regops_shared.constants import (
    AUTHORITY_TIMEZONE,
    BRIEFING_WINDOW_HOURS,
    SEVERITY_ORDER,
    AlertSeverity,
    Authority,
)
from regops_shared.db import AsyncSession
from regops_shared.models.base import utcnow

from .models import Alert, AlertSubscription
from .store import CellRef, cells_by_id_async, document_titles_async


@dataclass(slots=True)
class BriefingEntry:
    """One alert as it appears in a briefing."""

    alert_id: uuid.UUID
    cell_slug: str
    severity: AlertSeverity
    title: str
    document_title: str
    clause_count: int
    locked_ir_count: int
    #: ``detected_at`` in the authority's timezone, ISO-8601 with offset. The UTC value is on the
    #: alert detail; this is the one a reader compares against their own calendar.
    detected_at_local: str
    owner_id: uuid.UUID | None


@dataclass(slots=True)
class Briefing:
    subscriber_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    cell_slugs: list[str] = field(default_factory=list)
    entries: list[BriefingEntry] = field(default_factory=list)
    severity_counts: dict[str, int] = field(default_factory=dict)
    #: Alerts in the window nobody owns yet. The number a briefing exists to make uncomfortable.
    unassigned: int = 0


def local_timestamp(moment: datetime, authority: str) -> str:
    """Render a UTC instant in the authority's own timezone.

    Falls back to the value as given for an authority with no mapping — a wrong-looking timestamp is
    better than a briefing that raises, and the four in scope are all mapped.
    """
    try:
        zone = ZoneInfo(AUTHORITY_TIMEZONE[Authority(authority)])
    except (KeyError, ValueError):
        return moment.isoformat()
    return moment.astimezone(zone).isoformat()


async def compose_briefing(
    db: AsyncSession,
    *,
    subscriber_id: uuid.UUID,
    now: datetime | None = None,
    window_hours: int = BRIEFING_WINDOW_HOURS,
) -> Briefing:
    """Everything that changed in this subscriber's cells inside the window, worst first."""
    window_end = now or utcnow()
    window_start = window_end - timedelta(hours=window_hours)
    briefing = Briefing(
        subscriber_id=subscriber_id, window_start=window_start, window_end=window_end
    )

    cell_ids = list(
        await db.scalars(
            select(AlertSubscription.cell_id).where(
                AlertSubscription.subscriber_id == subscriber_id,
                AlertSubscription.enabled.is_(True),
            )
        )
    )
    if not cell_ids:
        return briefing

    cells = await cells_by_id_async(db, cell_ids)
    briefing.cell_slugs = sorted(cell.slug for cell in cells.values())

    alerts = list(
        await db.scalars(
            select(Alert).where(
                Alert.cell_id.in_(cell_ids),
                Alert.detected_at >= window_start,
                Alert.detected_at <= window_end,
            )
        )
    )
    if not alerts:
        return briefing

    titles = await document_titles_async(db, [alert.document_id for alert in alerts])

    # Worst first, then most recent. Ordering by time alone buries the one high-severity alert under
    # a morning's worth of routine ones, which is the failure mode a briefing exists to prevent.
    alerts.sort(key=lambda alert: (SEVERITY_ORDER.index(alert.severity), alert.detected_at))
    alerts.reverse()

    briefing.entries = [_entry(alert, cells.get(alert.cell_id), titles) for alert in alerts]
    for entry in briefing.entries:
        briefing.severity_counts[entry.severity.value] = (
            briefing.severity_counts.get(entry.severity.value, 0) + 1
        )
    briefing.unassigned = sum(1 for entry in briefing.entries if entry.owner_id is None)
    return briefing


def _entry(alert: Alert, cell: CellRef | None, titles: dict[uuid.UUID, str]) -> BriefingEntry:
    authority = cell.authority if cell else ""
    return BriefingEntry(
        alert_id=alert.id,
        cell_slug=cell.slug if cell else "",
        severity=alert.severity,
        title=alert.title,
        document_title=titles.get(alert.document_id, ""),
        clause_count=alert.clause_count,
        locked_ir_count=alert.locked_ir_count,
        detected_at_local=local_timestamp(alert.detected_at, authority),
        owner_id=alert.owner_id,
    )


__all__ = ["Briefing", "BriefingEntry", "compose_briefing", "local_timestamp"]
