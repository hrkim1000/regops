"""assistant — retrieval, citation-enforced generation, and evidence verification.

Two of the six Phase 1 gates are measured here: citation accuracy ≥ 90% and hallucination rate
≤ 2%. Neither is an ingestion problem — they are won or lost in what gets retrieved and how
generation is constrained (ADR-0006).

The contract this service keeps is the one in RegOps.md: **no answer without evidence.** An answer
carries a clause-level citation pinned to an immutable version and the date that version took
effect, or it is returned as "needs verification". Returning that is a success.
"""

from __future__ import annotations

from fastapi import FastAPI

from regops_shared.api import install_exception_handlers, ok
from regops_shared.logging import configure_logging

from .api.v1.index import router as index_router
from .api.v1.queries import router as queries_router

SERVICE_NAME = "assistant"

configure_logging(SERVICE_NAME)

app = FastAPI(title="RegOps assistant", version="0.2.0")
install_exception_handlers(app)
app.include_router(index_router)
app.include_router(queries_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return ok({"service": SERVICE_NAME, "version": app.version})
