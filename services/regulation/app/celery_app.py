"""Celery app for regulation. Queue name = service folder name.

The beat lives here rather than in its own service: it drives ``source_schedules`` and has no other
consumer, so splitting it would add a deployment unit that only ever talks to this one.

The tick is one minute; actual cadence comes from ``source_schedules.next_due_at``, which is derived
from the source's block and tier (ADR-0003 decision 4). The tick only decides how *promptly* a due
source is noticed — with a daily interval and a ≤24h detection-latency gate, the minute matters.
"""

from datetime import UTC, datetime

import structlog
from celery.schedules import crontab
from celery.signals import worker_ready

from regops_shared.celery import make_celery

log = structlog.get_logger(__name__)

celery_app = make_celery("regulation", include=["app.tasks"])


#: When this process began. A run that started *after* it cannot be a leftover from the process
#: before, and the sweep below refuses to touch one.
_BOOTED_AT = datetime.now(UTC)


@worker_ready.connect
def _fail_orphaned_runs(**_kwargs: object) -> None:
    """Close out extraction runs the *previous* worker did not live to finish.

    ``extract_version`` marks a dying run ``failed`` from its own ``except`` block — *"a run that
    dies mid-corpus must be visibly incomplete"* — and that handler does not run when the worker is
    killed. A ``SIGTERM`` on restart, a redeploy or a crash therefore leaves the row reading
    ``running`` forever, which is the one state that comment exists to prevent. It happened on
    2026-08-26: a restart mid-extraction left one document stuck at 50 of 406 clauses, and the only
    way back was hand-written SQL.

    **Only runs that predate this process are touched.** ``worker_ready`` fires once per container
    start, but "once per start" is not the same as "nothing of mine is in flight": with
    ``task_acks_late`` a redelivered task can be picked up before the signal is handled, and
    sweeping by status alone would fail a run this worker had just begun. Comparing against
    ``_BOOTED_AT`` makes the rule say what it means — *close what the previous process left*.

    **It is still sound only because there is one worker container.** Compose declares a single
    ``regulation-worker`` — ``-c 2`` is two children inside one container, not two replicas — so
    a run older than this boot cannot belong to a live peer. **A second worker makes this wrong**
    in the damaging direction, and the fix would be to record the owner on the run and sweep only
    your own.

    Partial IRs are left alone: they are ``draft``, and a re-run's ``_clear_previous_drafts`` clears
    them. Deleting them here would destroy evidence nobody has looked at.
    """
    # Imported here, not at module scope: the beat and the API import this module for a schedule and
    # should not pull the ORM in to read one.
    from sqlalchemy import select

    from regops_shared.constants import ExtractionRunStatus
    from regops_shared.db import sync_session
    from regops_shared.models import ExtractionRun
    from regops_shared.models.base import utcnow

    try:
        with sync_session() as session:
            orphans = session.scalars(
                select(ExtractionRun).where(
                    ExtractionRun.status == ExtractionRunStatus.RUNNING,
                    ExtractionRun.started_at < _BOOTED_AT,
                )
            ).all()
            for run in orphans:
                run.status = ExtractionRunStatus.FAILED
                run.completed_at = utcnow()
                run.error = (
                    "orphaned: the worker that owned this run did not survive to finish it, so the "
                    f"failure handler never ran. Examined {run.clauses_seen} clauses and wrote "
                    f"{run.irs_written} draft IRs before it stopped. Re-run to complete; the "
                    "partial drafts are cleared by the next run."
                )
            session.commit()
            if orphans:
                log.warning("extraction.orphans_closed", runs=len(orphans))
    except Exception as exc:  # pragma: no cover - startup must not be blocked by this sweep
        # A worker that cannot tidy up is still a worker that can work. Say so and carry on.
        log.error("extraction.orphan_sweep_failed", error=f"{type(exc).__name__}: {exc}")


celery_app.conf.beat_schedule = {
    "dispatch-due-sources": {
        "task": "regulation.dispatch_due_sources",
        "schedule": crontab(minute="*"),
        "options": {"queue": "regulation"},
    },
    # Weekly, off-hours. The delta it reports is a human triage list, not an ingestion trigger, so
    # a faster cadence would only produce the same list more often (ADR-0003 decision 11).
    "discover-sources": {
        "task": "regulation.discover_sources",
        "schedule": crontab(minute=0, hour=3, day_of_week=1),
        "options": {"queue": "regulation"},
    },
}
