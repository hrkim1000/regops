"""regulation — L1 ingestion: crawl → archive → version.

Phase 1.0 stops there. Parse, diff and change-event emission are phase 1.1; everything that
*writes* the clause store belongs to this service, and `monitoring` begins where writing ends
(CLAUDE.md § The seam).
"""

from __future__ import annotations

from fastapi import FastAPI

from regops_shared.api import install_exception_handlers, ok
from regops_shared.logging import configure_logging

from .api.v1.documents import router as documents_router
from .api.v1.sources import router as sources_router

SERVICE_NAME = "regulation"

configure_logging(SERVICE_NAME)

app = FastAPI(title="RegOps regulation", version="0.2.0")
install_exception_handlers(app)
app.include_router(sources_router)
app.include_router(documents_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return ok({"service": SERVICE_NAME, "version": app.version})
