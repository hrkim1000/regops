"""Celery app for regulation. Queue name = service folder name."""

from regops_shared.celery import make_celery

celery_app = make_celery("regulation")
