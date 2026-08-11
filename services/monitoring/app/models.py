"""Tables owned by `monitoring` (CLAUDE.md § Table ownership).

Re-exported from the canonical models in ``regops_shared.models`` — never redefined here.

Everything this service *routes on* belongs to `regulation`: ``change_events``, ``clause_diffs``,
``documents``, ``document_versions``, ``cells``, ``irs``. Those are read one-way and by raw SQL, all
of it in :mod:`app.store`, exactly the way `assistant` reads the clause store.

``structure_drift_alerts`` is **not** here and must not be migrated here (ADR-0009 decision 3).
It is scraper structure-drift adjudication — an ingestion concern despite the name — and it is
never an end-user alert.
"""

from regops_shared.models import Alert, AlertDelivery, AlertSubscription

__all__ = [
    "Alert",
    "AlertDelivery",
    "AlertSubscription",
]
