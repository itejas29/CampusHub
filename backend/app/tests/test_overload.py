"""Overload is refused quickly and cleanly, not queued (QA-18).

* Beyond `MAX_IN_FLIGHT_REQUESTS`, new requests get 503 + Retry-After at once;
  the health check is never refused; 0 means no limit.
* Waiting too long for a database connection, or a statement cancelled by
  PostgreSQL's `statement_timeout`, is a 503 the client may retry — not a 500.
* Every PostgreSQL connection the app opens carries the statement timeout.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import settings
from app.core.overload import LoadShedMiddleware, register_overload_handlers
from app.db.session import engine_options
from app.tests.test_mentor_one_active import PG, needs_pg


def _held_app():
    """An app whose /work waits until released, so requests overlap for real."""
    release = asyncio.Event()
    inner = FastAPI()

    @inner.get("/work")
    async def work():
        await release.wait()
        return {"ok": True}

    @inner.get("/health")
    async def health():
        return {"status": "ok"}

    return LoadShedMiddleware(inner), release


async def _second_while_first_runs(path="/work"):
    """Start /work, then ask for `path` while it is still running."""
    app, release = _held_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://t") as client:
        first = asyncio.create_task(client.get("/work"))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(client.get(path))
        await asyncio.sleep(0.05)
        answered_at_once = second.done()
        release.set()
        first, second = await first, await second
        after = await client.get("/work")
    return first, second, answered_at_once, after, app


def test_requests_beyond_the_limit_are_refused_at_once(monkeypatch):
    monkeypatch.setattr(settings, "MAX_IN_FLIGHT_REQUESTS", 1)
    first, second, at_once, after, app = asyncio.run(_second_while_first_runs())
    assert first.status_code == 200
    assert at_once and second.status_code == 503
    assert second.headers["retry-after"] == "5"
    assert second.json()["error"]["code"] == "service_busy"
    assert after.status_code == 200 and app.in_flight == 0     # the slot was given back


def test_the_health_check_is_never_refused(monkeypatch):
    monkeypatch.setattr(settings, "MAX_IN_FLIGHT_REQUESTS", 1)
    _first, second, _at_once, _after, _app = asyncio.run(_second_while_first_runs("/health"))
    assert second.status_code == 200


def test_no_limit_by_default(monkeypatch):
    assert settings.model_fields["MAX_IN_FLIGHT_REQUESTS"].default == 0
    monkeypatch.setattr(settings, "MAX_IN_FLIGHT_REQUESTS", 0)
    _first, second, at_once, _after, _app = asyncio.run(_second_while_first_runs())
    assert not at_once and second.status_code == 200          # waited its turn


def _raising(exc):
    app = FastAPI()
    register_overload_handlers(app)

    @app.get("/boom")
    def boom():
        raise exc

    return app


class _Cancelled(Exception):
    sqlstate = "57014"


class _Other(Exception):
    sqlstate = "08006"


@pytest.mark.parametrize("exc", [
    PoolTimeoutError("QueuePool limit reached"),
    OperationalError("SELECT 1", {}, _Cancelled("canceling statement due to statement timeout")),
])
def test_a_database_timeout_is_a_503_to_retry(exc):
    from fastapi.testclient import TestClient
    response = TestClient(_raising(exc)).get("/boom")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["error"]["code"] == "service_busy"


def test_any_other_database_failure_is_still_an_error():
    from fastapi.testclient import TestClient
    client = TestClient(_raising(OperationalError("SELECT 1", {}, _Other("connection lost"))),
                        raise_server_exceptions=False)
    assert client.get("/boom").status_code == 500


def test_postgres_connections_carry_the_statement_timeout():
    options = engine_options("postgresql+psycopg://u:p@h/db", statement_timeout_ms=1234)
    assert options["connect_args"] == {"options": "-c statement_timeout=1234"}
    assert "connect_args" not in engine_options("sqlite:///x.db")
    assert "connect_args" not in engine_options("postgresql+psycopg://u:p@h/db",
                                                statement_timeout_ms=0)


@needs_pg
def test_postgres_cancels_a_statement_that_runs_too_long():
    from sqlalchemy import create_engine, text

    from app.core.overload import is_statement_timeout
    url = settings.__class__(DATABASE_URL=PG).sqlalchemy_url
    engine = create_engine(url, **engine_options(url, statement_timeout_ms=200))
    try:
        with engine.connect() as c:
            assert c.execute(text("SHOW statement_timeout")).scalar() == "200ms"
            with pytest.raises(OperationalError) as caught:
                c.execute(text("SELECT pg_sleep(2)"))
        assert is_statement_timeout(caught.value)
    finally:
        engine.dispose()
