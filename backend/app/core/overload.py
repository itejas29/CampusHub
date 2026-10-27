"""Staying responsive under overload (QA-18).

Under a burst, every request queued for a worker thread or a database
connection was eventually served, even for clients that had long given up, so
the portal took 88–153 s to recover (QA load test, spike run). Three limits
bound that queue; each is a setting, chosen from the staging load test:

* `DB_STATEMENT_TIMEOUT_MS` — PostgreSQL cancels a statement running longer
  (set on every connection, `db/session.py`).
* `DB_POOL_TIMEOUT_S` — the longest a request waits for a connection.
* `MAX_IN_FLIGHT_REQUESTS` — beyond this many requests at once, new ones are
  answered 503 at once instead of joining the queue. 0 (the default) means no
  limit, so nothing changes until a value is chosen.

All three answer **503 with `Retry-After`**, never 500: the request was
refused, not broken, and the client may try again.
"""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import settings

RETRY_AFTER_S = 5
#: PostgreSQL's code for a statement cancelled by `statement_timeout`.
QUERY_CANCELED = "57014"
_NEVER_SHED = ("/health",)


def _busy_body(message: str) -> dict:
    return {"error": {"code": "service_busy", "message": message}}


def is_statement_timeout(exc: BaseException) -> bool:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) == QUERY_CANCELED


class LoadShedMiddleware:
    """Answers 503 when `MAX_IN_FLIGHT_REQUESTS` requests are already running.

    Pure ASGI and single-threaded (the event loop), so a plain counter is safe.
    """

    def __init__(self, app):
        self.app = app
        self.in_flight = 0

    async def __call__(self, scope, receive, send):
        limit = settings.MAX_IN_FLIGHT_REQUESTS
        if scope["type"] != "http" or not limit or scope.get("path") in _NEVER_SHED:
            return await self.app(scope, receive, send)
        if self.in_flight >= limit:
            body = json.dumps(_busy_body(
                "The portal is busy. Please try again in a few seconds.")).encode()
            await send({"type": "http.response.start", "status": 503,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode()),
                                    (b"retry-after", str(RETRY_AFTER_S).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        self.in_flight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1


def register_overload_handlers(app: FastAPI) -> None:
    busy = {"Retry-After": str(RETRY_AFTER_S)}

    @app.exception_handler(PoolTimeoutError)
    async def _pool_timeout(_: Request, __: PoolTimeoutError) -> JSONResponse:
        return JSONResponse(status_code=503, headers=busy, content=_busy_body(
            "The portal is busy. Please try again in a few seconds."))

    @app.exception_handler(OperationalError)
    async def _operational(_: Request, exc: OperationalError) -> JSONResponse:
        if not is_statement_timeout(exc):
            raise exc
        return JSONResponse(status_code=503, headers=busy, content=_busy_body(
            "That took too long and was stopped. Please try again."))
