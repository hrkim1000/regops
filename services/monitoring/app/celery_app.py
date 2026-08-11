"""Celery app for monitoring. Queue name = service folder name.

No beat. The scheduler lives with `regulation` — it drives ``source_schedules`` and has no other
consumer — and everything here is triggered: by the diff stage saying an amendment landed, or by a
failed delivery scheduling its own retry with a countdown.
"""

from regops_shared.celery import make_celery

celery_app = make_celery("monitoring", include=["app.tasks"])
