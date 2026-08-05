"""Source registry and ingestion-observability endpoints.

Reads are open to any authenticated principal; the two writes are role-gated. Resolving a
structure-drift alert is one of the two restricted actions in Phase 1 (CLAUDE.md § Security) because
it puts a human assertion into the audit trail: someone is stating that the *page* changed and the
regulation did not.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from regops_shared.api import Meta, ok
from regops_shared.audit import record
from regops_shared.auth import Principal, get_current_principal, require_roles
from regops_shared.constants import Role
from regops_shared.db import AsyncSession, get_db
from regops_shared.models.base import utcnow

from ...models import (
    FetchObservation,
    Source,
    SourceSchedule,
    StructureDriftAlert,
)

router = APIRouter(prefix="/api/v1", tags=["regulation"])

SERVICE = "regulation"
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[Principal, Depends(get_current_principal)]


def _source_out(source: Source, schedule: SourceSchedule | None) -> dict[str, Any]:
    """Note what is absent: ``url_template`` is exposed, a resolved URL never is. The template
    carries a placeholder, so this response cannot leak a credential."""
    return {
        "id": str(source.id),
        "slug": source.slug,
        "cell_id": str(source.cell_id),
        "block": source.block.value,
        "ordinal": source.ordinal,
        "title": source.title,
        "tier": source.tier.value,
        "ingestible": source.ingestible,
        "connector": source.connector,
        "url_template": source.url_template,
        "interval_seconds": schedule.interval_seconds if schedule else None,
        "next_due_at": schedule.next_due_at.isoformat() if schedule else None,
        "enabled": schedule.enabled if schedule else False,
        "consecutive_failures": schedule.consecutive_failures if schedule else 0,
        "notes": source.notes,
    }


@router.get("/sources")
async def list_sources(
    db: DbSession,
    _: CurrentUser,
    cell_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(Source).order_by(Source.slug)
    if cell_id is not None:
        stmt = stmt.where(Source.cell_id == cell_id)

    total = len(list(await db.scalars(stmt)))
    rows = list(await db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    schedules = {
        s.source_id: s
        for s in await db.scalars(
            select(SourceSchedule).where(SourceSchedule.source_id.in_([r.id for r in rows]))
        )
    }
    return ok(
        [_source_out(row, schedules.get(row.id)) for row in rows],
        meta=Meta(page=page, page_size=page_size, total=total),
    )


@router.get("/sources/{source_id}/observations")
async def list_observations(
    source_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Every fetch attempt, changed or not — this is what makes detection coverage auditable."""
    rows = list(
        await db.scalars(
            select(FetchObservation)
            .where(FetchObservation.source_id == source_id)
            .order_by(FetchObservation.fetched_at.desc())
            .limit(limit)
        )
    )
    return ok(
        [
            {
                "id": str(row.id),
                "fetched_at": row.fetched_at.isoformat(),
                "outcome": row.outcome.value,
                "http_status": row.http_status,
                "content_hash": row.content_hash,
                "connector_version": row.connector_version,
                "published_at": row.published_at.isoformat() if row.published_at else None,
                "artifact_count": row.artifact_count,
                "duration_ms": row.duration_ms,
                "notes": row.notes,
            }
            for row in rows
        ]
    )


@router.post("/sources/{source_id}/fetch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_fetch(
    source_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
) -> dict[str, Any]:
    """Fetch now, out of band. Long work returns 202 and the worker commits incrementally."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    if not source.ingestible or not source.connector:
        # The same refusal the scheduler and the connector API make. A non-ingestible source has
        # no fetch path, and a manual trigger is not an exception to that.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Source '{source.slug}' is not ingestible — Tier D and portal rows have no fetch path",
        )

    from ...celery_app import celery_app

    task = celery_app.send_task(
        "regulation.fetch_source", args=[str(source_id)], queue="regulation"
    )
    await record(
        db,
        service=SERVICE,
        action="source.fetch_triggered",
        actor_id=principal.id,
        entity_type="source",
        entity_id=source_id,
        payload={"slug": source.slug, "task_id": task.id},
    )
    await db.commit()
    return {
        "code": status.HTTP_202_ACCEPTED,
        "status": "success",
        "message": "Fetch enqueued",
        "data": {"id": str(source_id), "task_id": task.id},
        "meta": None,
    }


@router.get("/drift-alerts")
async def list_drift_alerts(
    db: DbSession, _: CurrentUser, unresolved_only: bool = True
) -> dict[str, Any]:
    stmt = select(StructureDriftAlert).order_by(StructureDriftAlert.detected_at.desc())
    if unresolved_only:
        stmt = stmt.where(StructureDriftAlert.resolved_at.is_(None))
    rows = list(await db.scalars(stmt))
    return ok(
        [
            {
                "id": str(row.id),
                "source_id": str(row.source_id),
                "detected_at": row.detected_at.isoformat(),
                "signal": row.signal.value,
                "expected": row.expected,
                "actual": row.actual,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            }
            for row in rows
        ]
    )


@router.post("/drift-alerts/{alert_id}/resolve")
async def resolve_drift_alert(
    alert_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_roles([Role.RA, Role.ADMIN]))],
    note: str = Query(..., min_length=1, max_length=2000),
) -> dict[str, Any]:
    """A human states whether the regulation changed or the page did.

    Restricted, and audited, because that assertion is the whole point of failing closed on drift:
    it is the step that keeps a site redesign from being published as thousands of change events.
    """
    alert = await db.get(StructureDriftAlert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    if alert.resolved_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert is already resolved")

    alert.resolved_at = utcnow()
    alert.resolved_by = principal.id
    alert.resolution_note = note
    await record(
        db,
        service=SERVICE,
        action="drift_alert.resolved",
        actor_id=principal.id,
        entity_type="structure_drift_alert",
        entity_id=alert_id,
        payload={"signal": alert.signal.value, "note": note},
    )
    await db.commit()
    return ok({"id": str(alert_id), "resolved_at": alert.resolved_at.isoformat()})


__all__ = ["router"]
