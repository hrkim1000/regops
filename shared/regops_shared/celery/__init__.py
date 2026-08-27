"""Celery factory. One queue per service; queue name = service folder name."""

from __future__ import annotations

from celery import Celery

from regops_shared.constants import CELERY_VISIBILITY_TIMEOUT
from regops_shared.settings import get_settings


def make_celery(name: str, include: list[str] | None = None) -> Celery:
    """Build the app for a service. Cross-service dispatch is by task *name* only:
    ``send_task("svc.task_name", args=[...], queue="svc")`` — never import another service's
    task graph."""
    settings = get_settings()
    app = Celery(name, broker=settings.redis_url, backend=settings.redis_url, include=include or [])
    app.conf.update(
        task_default_queue=name,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # Redis redelivers any task still unacked after its visibility timeout, and `acks_late`
        # means "unacked" == "not finished". At the broker's one-hour default, every task that runs
        # longer is handed to a second worker *while the first is still working* — which for
        # extraction means a duplicate that deletes the live run's drafts. See
        # `CELERY_VISIBILITY_TIMEOUT` for the incident this is set from.
        broker_transport_options={
            "visibility_timeout": int(CELERY_VISIBILITY_TIMEOUT.total_seconds())
        },
    )
    return app


__all__ = ["make_celery"]
