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
from regops_shared.models import DocumentVersion, Source, SourceSchedule
from regops_shared.models.base import utcnow

from .celery_app import celery_app
from .diff import diff_version
from .discovery import fetch_admrul_index, reconcile
from .ingest import ingest_source
from .parse import DIFF_TASK, parse_version
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
def parse_document_version(document_version_id: str) -> dict[str, object]:
    """Archived bytes → clauses, then hand off to the diff stage by name (ADR-0015).

    Reads from the WORM archive, never the network, so re-running this over the corpus after a
    profile improvement costs nothing at the authority.
    """
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        version = session.get(DocumentVersion, version_id)
        if version is None:
            log.warning("parse.unknown_version", document_version_id=document_version_id)
            return {"document_version_id": document_version_id, "status": "unknown_version"}
        result = parse_version(session, version)

    if not result.ok:
        # The version was removed and a drift alert raised. Nothing to diff, and emitting a change
        # event here is exactly what ADR-0003 decision 6 forbids.
        return {
            "document_version_id": document_version_id,
            "status": "drift",
            "signal": result.drift.value if result.drift else None,
        }

    celery_app.send_task(DIFF_TASK, args=[document_version_id], queue=QUEUE)
    if result.successor_to_rediff is not None:
        # A re-parse invalidated the successor's diff against this version too. Re-enqueue it so
        # the change history heals rather than losing a link (ADR-0015).
        celery_app.send_task(DIFF_TASK, args=[str(result.successor_to_rediff)], queue=QUEUE)

    return {
        "document_version_id": document_version_id,
        "status": "parsed",
        "profile": result.profile,
        "clauses": result.clauses_written,
        "rediff_successor": str(result.successor_to_rediff) if result.successor_to_rediff else None,
    }


@celery_app.task(name="regulation.diff_document_version")
def diff_document_version(document_version_id: str) -> dict[str, object]:
    """Diff against the previous version, emit change events, flag superseded citations."""
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        version = session.get(DocumentVersion, version_id)
        if version is None:
            log.warning("diff.unknown_version", document_version_id=document_version_id)
            return {"document_version_id": document_version_id, "status": "unknown_version"}
        result = diff_version(session, version)

    return {
        "document_version_id": document_version_id,
        "status": "baseline" if result.baseline else "diffed",
        "counts": result.counts,
        "change_events": result.change_events,
        "needs_review": result.needs_review,
        "citations_superseded": result.citations_superseded,
    }


__all__ = [
    "diff_document_version",
    "discover_sources",
    "dispatch_due_sources",
    "fetch_source",
    "parse_document_version",
]
