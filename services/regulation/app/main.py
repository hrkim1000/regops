"""regulation — scaffolded in phase 0, health check only.

No regulation logic lives here yet. Content arrives in the phase 1.x plans:
see docs/plan/README.md for which slice fills this service.
"""

from __future__ import annotations

from fastapi import FastAPI

from regops_shared.api import install_exception_handlers, ok
from regops_shared.logging import configure_logging

SERVICE_NAME = "regulation"

configure_logging(SERVICE_NAME)

app = FastAPI(title="RegOps regulation", version="0.1.0")
install_exception_handlers(app)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return ok({"service": SERVICE_NAME, "version": app.version})
