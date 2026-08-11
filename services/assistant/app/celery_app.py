"""Celery app for assistant. Queue name = service folder name.

No beat here. Everything this service does is triggered — by a person asking a question, by the API
asking for an index build, or by `regulation`'s diff stage saying an amendment landed. A periodic
tick would only re-discover work that was already dispatched by name.
"""

from regops_shared.celery import make_celery

celery_app = make_celery("assistant", include=["app.tasks"])
