"""The response envelope every endpoint wears: ``{code, status, message, data, meta}``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class Meta(BaseModel):
    page: int | None = None
    page_size: int | None = None
    total: int | None = None


class Envelope[T](BaseModel):
    code: int = status.HTTP_200_OK
    status: str = "success"
    message: str = "OK"
    data: T | None = None
    meta: Meta | None = None


def ok(data: Any = None, *, message: str = "OK", meta: Meta | None = None) -> dict[str, Any]:
    return {
        "code": status.HTTP_200_OK,
        "status": "success",
        "message": message,
        "data": data,
        "meta": meta.model_dump() if meta else None,
    }


def error(code: int, message: str, *, data: Any = None) -> dict[str, Any]:
    """Errors carry ``status:"error"`` and ``data:null``.

    Optional diagnostics ride inside ``data``; the reason belongs in ``message``.
    """
    return {"code": code, "status": "error", "message": message, "data": data, "meta": None}


def install_exception_handlers(app: FastAPI) -> None:
    """Make every error path wear the envelope too — otherwise clients need two parsers."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=error(exc.status_code, str(exc.detail))
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Request validation failed",
                data={"errors": exc.errors()},
            ),
        )


__all__ = ["Envelope", "Meta", "error", "install_exception_handlers", "ok"]
