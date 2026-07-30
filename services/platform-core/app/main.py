"""platform-core — identity, roles, sessions, audit trail.

Every other service depends on this one and nothing depends on them (ADR-0005 decision 1). Auth is
issued here; verification is stateless and local to each service.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.v1 import audit, auth, users
from regops_shared.api import install_exception_handlers, ok
from regops_shared.logging import configure_logging

SERVICE_NAME = "platform-core"

configure_logging(SERVICE_NAME)

app = FastAPI(
    title="RegOps platform-core",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
install_exception_handlers(app)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return ok({"service": SERVICE_NAME, "version": app.version})
