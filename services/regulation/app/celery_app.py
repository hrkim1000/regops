"""Celery app for regulation. Queue name = service folder name.

The beat lives here rather than in its own service: it drives ``source_schedules`` and has no other
consumer, so splitting it would add a deployment unit that only ever talks to this one.

The tick is one minute; actual cadence comes from ``source_schedules.next_due_at``, which is derived
from the source's block and tier (ADR-0003 decision 4). The tick only decides how *promptly* a due
source is noticed — with a daily interval and a ≤24h detection-latency gate, the minute matters.
"""

from celery.schedules import crontab

from regops_shared.celery import make_celery

celery_app = make_celery("regulation", include=["app.tasks"])

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
