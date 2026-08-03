"""Celery tasks for `regulation`. Queue name = service folder name.

The beat lives with this service because it drives ``source_schedules`` and has no other consumer.
Dispatch is two-stage on purpose: the beat only *claims* due sources and moves their next due time
forward, then fans out one task per source. A long fetch therefore cannot hold the scheduler, and a
worker crash mid-fetch loses one source rather than the tick.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from regops_shared.db import sync_session
from regops_shared.models import Source, SourceSchedule
from regops_shared.models.base import utcnow

from .celery_app import celery_app
from .discovery import fetch_admrul_index, reconcile
from .ingest import ingest_source
from .scheduling import advance

log = structlog.get_logger(__name__)

QUEUE = "regulation"


@celery_app.task(name="regulation.dispatch_due_sources")
def dispatch_due_sources(limit: int = 50) -> dict[str, int]:
    """Claim every schedule that is due and hand each to its own fetch task."""
    dispatched = 0
    now = utcnow()

    with sync_session() as session:
        due = session.scalars(
            select(SourceSchedule)
            .where(SourceSchedule.enabled.is_(True), SourceSchedule.next_due_at <= now)
            .order_by(SourceSchedule.next_due_at)
            .limit(limit)
        ).all()
        for schedule in due:
            # Advance before dispatching: if the fetch fails, the next tick retries on cadence
            # rather than hammering a host that has just proven fragile.
            schedule.last_started_at = now
            advance(schedule, now=now)
            session.commit()

            celery_app.send_task(
                "regulation.fetch_source", args=[str(schedule.source_id)], queue=QUEUE
            )
            dispatched += 1

    log.info("scheduler.dispatched", count=dispatched)
    return {"dispatched": dispatched}


@celery_app.task(name="regulation.fetch_source", bind=True, max_retries=0)
def fetch_source(self, source_id: str) -> dict[str, object]:
    """Fetch one source: fetch → archive → version. Stops before parse (phase 1.1).

    ``max_retries=0`` is deliberate. A failed fetch already records an observation and a drift
    alert, and the schedule fires again on cadence; a Celery-level retry would poll a struggling
    government host harder than the interval we committed to.
    """
    with sync_session() as session:
        source = session.get(Source, uuid.UUID(source_id))
        if source is None:
            log.warning("fetch.unknown_source", source_id=source_id)
            return {"source_id": source_id, "outcome": "unknown_source"}

        result = ingest_source(session, source)

        schedule = session.get(SourceSchedule, source.id)
        if schedule is not None:
            schedule.last_completed_at = utcnow()
            schedule.consecutive_failures = schedule.consecutive_failures + 1 if result.error else 0
            session.commit()

    return {
        "source": result.source_slug,
        "outcome": result.outcome.value,
        "new_versions": len(result.new_version_ids),
        "unchanged_artifacts": result.unchanged_artifacts,
        "standards_seen": result.standards_seen,
    }


@celery_app.task(name="regulation.discover_sources")
def discover_sources() -> dict[str, int | bool]:
    """Reconcile the curated catalog against the authority's own 행정규칙 list.

    A hand-maintained list caps detection coverage at whatever someone remembered to add
    (ADR-0003 decision 11). This turns that from an unknown into a row in
    ``source_discovery_runs``.

    Nothing here is archived: the 목록 endpoint echoes the ``OC`` key back in every row, so these
    responses are consumed in memory and discarded.
    """
    rules, truncated = fetch_admrul_index()
    with sync_session() as session:
        run = reconcile(session, rules, truncated=truncated)
        result = {
            "upstream_count": run.upstream_count,
            "matched": run.matched,
            "unmatched": run.unmatched,
            "truncated": truncated,
        }
        session.commit()
    return result


@celery_app.task(name="regulation.parse_document_version")
def parse_document_version(document_version_id: str) -> dict[str, str]:
    """Phase 1.1 owns this. Registered here so 1.0's hand-off has a real endpoint to reach.

    Phase 1.0 stops at "bytes are archived and a version row exists"; parsing, clause segmentation,
    ``effective_date`` extraction and diffing are the next slice. This logs the hand-off so the
    queue depth is observable before there is anything to consume it.
    """
    log.info("parse.pending", document_version_id=document_version_id, phase="1.1")
    return {"document_version_id": document_version_id, "status": "pending_phase_1_1"}


__all__ = [
    "discover_sources",
    "dispatch_due_sources",
    "fetch_source",
    "parse_document_version",
]
