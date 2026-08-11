"""monitoring — subscription matching, impact grading, alert composition and delivery.

Two of the six Phase 1 gates are measured here, and both end to end: detection coverage ≥ 95% and
detection latency ≤ 24h, from the authority's publication to the owner's alert. Neither is an
ingestion property — a change detected and never routed fails both.

This service **begins where writing ends** (ADR-0009 decision 2). Everything that writes the clause
store is `regulation`; `monitoring` reads ``change_events`` one-way by raw SQL, all of it in
:mod:`app.store`, and writes only its own three tables. A wedged scraper does not stop delivery of
changes already detected, and a wedged receiver does not stop ingestion.

Phase 1 routes on **cell**, not on product (ADR-0007; ADR-0009 decision 5), and every alert says so
in its own body rather than implying a precision the data cannot support.
"""

from __future__ import annotations

from fastapi import FastAPI

from regops_shared.api import install_exception_handlers, ok
from regops_shared.logging import configure_logging

from .api.v1.alerts import router as alerts_router
from .api.v1.subscriptions import router as subscriptions_router

SERVICE_NAME = "monitoring"

configure_logging(SERVICE_NAME)

app = FastAPI(title="RegOps monitoring", version="0.2.0")
install_exception_handlers(app)
app.include_router(subscriptions_router)
app.include_router(alerts_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return ok({"service": SERVICE_NAME, "version": app.version})
