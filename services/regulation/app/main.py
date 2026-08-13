"""regulation — L1–L2: crawl → archive → version → parse → diff → change event → IR.

Everything that *writes* the clause store belongs to this service, and `monitoring` begins where
writing ends (CLAUDE.md § The seam). Phase 1.0 built ingestion, 1.1 the clause store and its diffs,
1.2 the Requirement Extraction agent and the draft → locked lifecycle.
"""

from __future__ import annotations

from fastapi import FastAPI

from regops_shared.api import install_exception_handlers, ok
from regops_shared.logging import configure_logging

from .api.v1.clauses import router as clauses_router
from .api.v1.diffs import router as diffs_router
from .api.v1.documents import router as documents_router
from .api.v1.irs import router as irs_router
from .api.v1.sources import router as sources_router
from .api.v1.submissions import router as submissions_router

SERVICE_NAME = "regulation"

configure_logging(SERVICE_NAME)

app = FastAPI(title="RegOps regulation", version="0.3.0")
install_exception_handlers(app)
app.include_router(sources_router)
app.include_router(documents_router)
app.include_router(clauses_router)
app.include_router(diffs_router)
app.include_router(irs_router)
app.include_router(submissions_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return ok({"service": SERVICE_NAME, "version": app.version})
