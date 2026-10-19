"""Shared helpers for the QA concurrency and load tools.

Targets an ISOLATED server (default http://127.0.0.1:8201) backed by a disposable
PostgreSQL database seeded with synthetic data. Never point these at production.
"""
from __future__ import annotations

import asyncio
import os
import subprocess

import httpx

BASE = os.environ.get("QA_BASE_URL", "http://127.0.0.1:8201/api/v1")
PASSWORD = os.environ.get("QA_PASSWORD", "Campus@123")          # synthetic demo accounts only
PG_CONTAINER = os.environ.get("QA_PG_CONTAINER", "campushub-qa-pg")
PG_DB = os.environ.get("QA_PG_DB", "campushub_qa")

assert "railway.app" not in BASE and "vercel.app" not in BASE, "refusing to target production"


def sql(query: str) -> list[list[str]]:
    out = subprocess.run(["docker", "exec", PG_CONTAINER, "psql", "-U", "qa", "-d", PG_DB, "-tA",
                          "-F", "\t", "-c", query], capture_output=True, text=True, check=True).stdout
    return [line.split("\t") for line in out.strip().splitlines() if line]


async def login(client: httpx.AsyncClient, email: str) -> dict:
    r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


async def login_all(client: httpx.AsyncClient, emails: list[str], parallel: int = 8) -> list[dict]:
    sem = asyncio.Semaphore(parallel)

    async def one(email):
        async with sem:
            return await login(client, email)
    return await asyncio.gather(*(one(e) for e in emails))


async def burst(requests: list) -> list[httpx.Response | Exception]:
    """Fire every request at once (each a zero-arg coroutine factory)."""
    gate = asyncio.Event()

    async def run(make):
        await gate.wait()
        try:
            return await make()
        except Exception as exc:          # noqa: BLE001 — recorded, not hidden
            return exc
    tasks = [asyncio.create_task(run(m)) for m in requests]
    await asyncio.sleep(0.05)
    gate.set()
    return await asyncio.gather(*tasks)


def tally(results) -> dict:
    counts: dict = {}
    for r in results:
        key = type(r).__name__ if isinstance(r, Exception) else r.status_code
        counts[key] = counts.get(key, 0) + 1
    return counts
