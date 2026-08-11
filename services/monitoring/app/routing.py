"""Subscription matching, fan-out, dedup, and alert composition.

This is the half of the phase that decides whether the detection-coverage gate is met honestly. Four
rules, and each of them is an acceptance criterion rather than a preference:

- **Matching is on cell.** One ``ChangeEvent`` reaches every claiming cell's subscribers and no
  others. The fan-out to claiming cells already happened in `regulation`'s diff stage (ADR-0003
  decision 8) — a document claimed by both gated cells emitted two events — so this side only has to
  route each event to its own cell's subscribers and never widen.
- **One amendment is one alert.** Every substantive event for a ``(tenant, cell, version)`` composes
  a single alert carrying N clause references. Forty alerts for a forty-clause amendment is the same
  information delivered as noise, and a subscriber who stops reading fails the coverage gate exactly
  as surely as a change nobody detected.
- **A renumbering-only amendment produces no alert at all.** Not a suppressed row, not a zero-clause
  alert — nothing. A renumber moves a clause's address without changing what it requires, and
  ``clause_diffs`` already resolves it explicitly rather than as delete + add (ADR-0002 decision 7)
  precisely so that this is answerable here. The count is returned by the task and logged, because
  "we saw it and deliberately said nothing" has to be visible somewhere.
- **No subscriber, no alert.** These tables are tenant-scoped; an alert composed for a cell nobody
  subscribes to would have no tenant to belong to and no reader. The metrics endpoint reports the
  subscriber count beside the coverage figure so that a cell at 0% reads as "nobody asked" rather
  than as a routing bug.

Re-running this over the same version is safe and is the retry: the ``(tenant, cell, version)``
unique key means a re-diff updates one alert in place instead of raising a second.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from regops_shared.constants import (
    NON_SUBSTANTIVE_CHANGE_KINDS,
    AlertStatus,
)
from regops_shared.models.base import utcnow

from .grade import compose_summary, compose_title, grade
from .models import Alert, AlertSubscription
from .store import (
    ChangeEventRow,
    amendment,
    cells_by_id,
    change_events_for_version,
    locked_ir_impact,
)

log = structlog.get_logger(__name__)

_NON_SUBSTANTIVE = {kind.value for kind in NON_SUBSTANTIVE_CHANGE_KINDS}


@dataclass(slots=True)
class RoutingResult:
    """What one routing pass over one amendment did — and what it deliberately did not do."""

    document_version_id: uuid.UUID
    events_seen: int = 0
    #: Events dropped as non-substantive. Counted because the false-positive rate has no gate
    #: (phase1.4 § Risks) and this is the only number that shows the suppression working.
    events_suppressed: int = 0
    cells_seen: int = 0
    #: Cells whose entire share of this amendment was renumbering. No alert row exists for them.
    cells_suppressed: int = 0
    #: Cells with substantive change and nobody subscribed. Not a failure — a coverage fact.
    cells_without_subscribers: int = 0
    alerts_created: int = 0
    alerts_updated: int = 0
    alert_ids: list[uuid.UUID] = field(default_factory=list)


def route_version(session: Session, version_id: uuid.UUID) -> RoutingResult:
    """Compose alerts for one amendment. Flushes and commits; returns the alerts to deliver."""
    result = RoutingResult(document_version_id=version_id)

    ref = amendment(session, version_id)
    if ref is None:
        log.warning("route.unknown_version", document_version_id=str(version_id))
        return result

    events = change_events_for_version(session, version_id)
    result.events_seen = len(events)
    if not events:
        # A baseline ingestion emits no events at all, and that is correct: the first version of a
        # document is not an amendment (ADR-0003). Nothing to route.
        return result

    by_cell: dict[uuid.UUID, list[ChangeEventRow]] = defaultdict(list)
    for event in events:
        by_cell[event.cell_id].append(event)
    result.cells_seen = len(by_cell)

    cells = cells_by_id(session, list(by_cell))
    ir_impact = locked_ir_impact(session, version_id)

    for cell_id, cell_events in by_cell.items():
        substantive = [row for row in cell_events if row.change_kind not in _NON_SUBSTANTIVE]
        if not substantive:
            result.cells_suppressed += 1
            result.events_suppressed += len(cell_events)
            log.info(
                "route.suppressed_non_substantive",
                document_version_id=str(version_id),
                cell_id=str(cell_id),
                events=len(cell_events),
            )
            continue
        result.events_suppressed += len(cell_events) - len(substantive)

        subscriptions = _subscriptions_for(session, cell_id)
        if not subscriptions:
            result.cells_without_subscribers += 1
            log.info("route.no_subscribers", cell_id=str(cell_id))
            continue

        cell = cells.get(cell_id)
        locked_irs = ir_impact.get(cell.domain, 0) if cell else 0

        for tenant_id in {subscription.tenant_id for subscription in subscriptions}:
            alert, created = _upsert_alert(
                session,
                ref=ref,
                cell_id=cell_id,
                tenant_id=tenant_id,
                events=substantive,
                locked_ir_count=locked_irs,
            )
            result.alert_ids.append(alert.id)
            if created:
                result.alerts_created += 1
            else:
                result.alerts_updated += 1

    session.commit()
    log.info(
        "route.done",
        document_version_id=str(version_id),
        events=result.events_seen,
        suppressed=result.events_suppressed,
        created=result.alerts_created,
        updated=result.alerts_updated,
    )
    return result


# --- composition -------------------------------------------------------------------------------


def _upsert_alert(
    session: Session,
    *,
    ref,
    cell_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    events: list[ChangeEventRow],
    locked_ir_count: int,
) -> tuple[Alert, bool]:
    """One alert per ``(tenant, cell, version)``, created or refreshed in place.

    Updating rather than inserting is what makes a re-diff idempotent — and it deliberately leaves
    ``owner_id`` and the delivery history alone: a re-parse that re-derives the same amendment must
    not un-assign the person who was told to deal with it.
    """
    kind_counts: dict[str, int] = defaultdict(int)
    for event in events:
        kind_counts[event.change_kind] += 1

    clause_paths = [event.clause_path for event in events]
    grade_result = grade(
        change_kinds=set(kind_counts),
        clause_count=len(events),
        locked_ir_count=locked_ir_count,
    )

    alert = session.scalar(
        select(Alert).where(
            Alert.cell_id == cell_id,
            Alert.document_version_id == ref.version_id,
            Alert.tenant_id.is_(None) if tenant_id is None else Alert.tenant_id == tenant_id,
        )
    )
    created = alert is None
    if alert is None:
        alert = Alert(
            tenant_id=tenant_id,
            cell_id=cell_id,
            document_id=ref.document_id,
            document_version_id=ref.version_id,
            detected_at=min(event.detected_at for event in events),
        )
        session.add(alert)

    alert.from_version_id = next(
        (event.from_version_id for event in events if event.from_version_id), None
    )
    alert.severity = grade_result.severity
    alert.title = compose_title(document_title=ref.document_title, clause_count=len(events))
    alert.summary = compose_summary(
        document_title=ref.document_title,
        version_label=ref.version_label,
        effective_date_iso=ref.effective_date.isoformat() if ref.effective_date else None,
        grade_result=grade_result,
        kind_counts=dict(kind_counts),
        clause_paths=clause_paths,
    )
    alert.clause_count = len(events)
    alert.change_event_ids = [event.event_id for event in events]
    alert.clause_references = [
        {
            "clause_path": event.clause_path,
            "from_clause_path": event.from_clause_path,
            "change_kind": event.change_kind,
            "clause_diff_id": str(event.clause_diff_id),
        }
        for event in events
    ]
    alert.cited_by_locked_ir = locked_ir_count > 0
    alert.locked_ir_count = locked_ir_count
    alert.published_at = ref.published_at
    alert.retrieved_at = ref.retrieved_at
    alert.detected_at = min(event.detected_at for event in events)
    if created:
        alert.status = AlertStatus.PENDING
        alert.created_at = utcnow()

    session.flush()
    return alert, created


def _subscriptions_for(session: Session, cell_id: uuid.UUID) -> list[AlertSubscription]:
    """Enabled subscriptions on one cell. **Never widened** — this is the "and no others" half."""
    return list(
        session.scalars(
            select(AlertSubscription).where(
                AlertSubscription.cell_id == cell_id,
                AlertSubscription.enabled.is_(True),
            )
        )
    )


__all__ = ["RoutingResult", "route_version"]
