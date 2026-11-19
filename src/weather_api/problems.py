"""Errors as RFC 9457 problem details: one shape for every failure."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.exceptions import HTTPException

TITLES = {
    401: "Unauthorized",
    404: "Not found",
    422: "Invalid request",
    500: "Internal error",
    429: "Too many requests",
    503: "Service unavailable",
}


class DataUnavailable(Exception):
    """No data can be served: nothing loaded yet, or the database is unreachable."""


def problem(status: int, detail: str, headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        {"title": TITLES.get(status, "Error"), "status": status, "detail": detail},
        status_code=status,
        media_type="application/problem+json",
        headers=dict(headers or {}),
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        return problem(error.status_code, str(error.detail), error.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, error: RequestValidationError) -> JSONResponse:
        fields = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in error.errors()
        )
        return problem(422, fields or "Invalid parameters")

    @app.exception_handler(DataUnavailable)
    async def unavailable(_: Request, error: DataUnavailable) -> JSONResponse:
        return problem(503, str(error), {"Retry-After": "30"})

    @app.exception_handler(DBAPIError)
    @app.exception_handler(PoolTimeout)
    async def database_down(_: Request, __: Exception) -> JSONResponse:
        return problem(
            503, "The database is unreachable; try again shortly.", {"Retry-After": "30"}
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, __: Exception) -> JSONResponse:
        # Logged by the server; the caller gets a problem document, never a trace.
        return problem(500, "Something went wrong on our side.")
