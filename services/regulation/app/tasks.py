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

from regops_shared.constants import Domain
from regops_shared.db import sync_session
from regops_shared.models import DocumentVersion, Source, SourceSchedule
from regops_shared.models.base import utcnow

from .celery_app import celery_app
from .diff import diff_version
from .discovery import fetch_admrul_index, reconcile
from .extraction import domains_for, extract_version, rederive_version
from .extraction.extract import REDERIVE_TASK
from .ingest import ingest_source
from .parse import DIFF_TASK, parse_version
from .scheduling import advance

log = structlog.get_logger(__name__)

QUEUE = "regulation"

#: Cross-service dispatch is by task **name** only (CLAUDE.md § Celery Queue Architecture), so these
#: two strings are the entire coupling to `assistant`. Nothing here imports that service's task
#: graph, and nothing here writes its tables.
ASSISTANT_QUEUE = "assistant"
ANSWER_SUPERSEDE_TASK = "assistant.supersede_answer_citations"


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

    if result.irs_marked_stale:
        # Targeted, not a corpus sweep: only the IRs this amendment actually staled. Dispatched by
        # name so the extraction stage stays reachable without importing its task graph (ADR-0015).
        celery_app.send_task(REDERIVE_TASK, args=[document_version_id], queue=QUEUE)

    if not result.baseline and result.counts:
        # Stored answers cite clauses too, and an amendment moves their evidence the same way it
        # stales an IR — but into a *different* lifecycle, in a different service's table
        # (ADR-0006 decision 10). So this service does not write `answer_citations`; it says the
        # version has been diffed, by task name only, and `assistant` reads `clause_diffs` one-way
        # and flags its own rows.
        celery_app.send_task(
            ANSWER_SUPERSEDE_TASK, args=[document_version_id], queue=ASSISTANT_QUEUE
        )

    return {
        "document_version_id": document_version_id,
        "status": "baseline" if result.baseline else "diffed",
        "counts": result.counts,
        "change_events": result.change_events,
        "needs_review": result.needs_review,
        "citations_superseded": result.citations_superseded,
        "irs_marked_stale": result.irs_marked_stale,
    }


@celery_app.task(name="regulation.extract_document_version", bind=True, max_retries=0)
def extract_document_version(self, document_version_id: str, domain: str | None = None) -> dict:
    """Clauses → draft IRs, once per claiming domain (ADR-0004).

    **Not chained off the parse stage.** Every other stage in this service is deterministic and
    cheap enough to run on every fetch; this one calls an LLM per obligation-bearing clause, and the
    gated corpus is 25,729 clauses. Auto-running it on each poll would spend a full extraction to
    discover that nothing changed. Amendments are covered by the targeted re-derivation sweep
    instead, and a first extraction is triggered explicitly — by the API, or by this task.

    ``max_retries=0`` for the same reason the fetch task uses it: the run records its own failure
    and stays visibly incomplete, and a blind retry would re-spend the whole call budget.
    """
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        version = session.get(DocumentVersion, version_id)
        if version is None:
            log.warning("extract.unknown_version", document_version_id=document_version_id)
            return {"document_version_id": document_version_id, "status": "unknown_version"}

        targets = [Domain(domain)] if domain else domains_for(session, version.document_id)
        if not targets:
            # No claiming cell means no rule set to extract under. Silent extraction against a
            # guessed domain would put obligations in a taxonomy nobody chose.
            log.warning("extract.no_claiming_cell", version=document_version_id)
            return {"document_version_id": document_version_id, "status": "no_claiming_cell"}

        runs = [extract_version(session, version, domain=target) for target in targets]

    return {
        "document_version_id": document_version_id,
        "status": "extracted",
        "runs": [
            {
                "domain": run.domain_profile.value,
                "run_id": str(run.run_id) if run.run_id else None,
                "clauses_seen": run.clauses_seen,
                "obligation_bearing": run.obligation_bearing,
                "excluded": run.excluded,
                "irs": run.irs_written,
                "rejected_uncited": run.rejected_uncited,
            }
            for run in runs
        ],
    }


@celery_app.task(name=REDERIVE_TASK, bind=True, max_retries=0)
def rederive_stale_irs(self, document_version_id: str) -> dict:
    """Re-extract the IRs this version's amendment staled, into superseding IRs."""
    version_id = uuid.UUID(document_version_id)
    with sync_session() as session:
        version = session.get(DocumentVersion, version_id)
        if version is None:
            log.warning("rederive.unknown_version", document_version_id=document_version_id)
            return {"document_version_id": document_version_id, "status": "unknown_version"}
        result = rederive_version(session, version)

    return {
        "document_version_id": document_version_id,
        "status": "rederived",
        "stale_seen": result.stale_seen,
        "superseded": result.superseded,
        "irs_written": result.irs_written,
        "unresolved": result.unresolved,
    }


__all__ = [
    "diff_document_version",
    "discover_sources",
    "dispatch_due_sources",
    "extract_document_version",
    "fetch_source",
    "parse_document_version",
    "rederive_stale_irs",
]
