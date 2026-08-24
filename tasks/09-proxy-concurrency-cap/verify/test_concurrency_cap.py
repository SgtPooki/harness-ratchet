"""Tests for vllm-proxy ConcurrencyCap middleware (homelab2#157)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from concurrency_cap import ConcurrencyCap
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


def _build_app(max_concurrency: int, gate: asyncio.Event | None = None) -> Starlette:
    """Tiny app with a slow endpoint that holds an upstream slot until released
    via the optional `gate`. Lets tests drive concurrency precisely."""

    async def slow(request):  # noqa: ARG001
        if gate is not None:
            await gate.wait()
        return PlainTextResponse("ok")

    async def health(request):  # noqa: ARG001
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/{path:path}", slow, methods=["GET", "POST"]),
        ]
    )
    app.add_middleware(ConcurrencyCap, max_concurrency=max_concurrency)
    return app


@pytest.mark.asyncio
async def test_cap_admits_under_limit():
    app = _build_app(max_concurrency=3)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            r = await client.get("/v1/chat/completions")
            assert r.status_code == 200
            assert r.headers["X-Concurrency-Max"] == "3"


@pytest.mark.asyncio
async def test_cap_rejects_over_limit_with_503_and_retry_after():
    """Two requests hold the slots; a third is rejected with 503 + Retry-After."""
    gate = asyncio.Event()
    app = _build_app(max_concurrency=2, gate=gate)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Two in-flight, hung at the gate.
        in_flight = [asyncio.create_task(client.get("/v1/chat/completions")) for _ in range(2)]
        # Yield so the in-flight tasks reach the gate (i.e. acquire their slots).
        for _ in range(20):
            if app.user_middleware[0].kwargs is None:
                pass  # placeholder to advance loop
            await asyncio.sleep(0.01)

        # Third request must reject immediately.
        r3 = await client.get("/v1/chat/completions")
        assert r3.status_code == 503
        assert r3.headers["Retry-After"] == "5"
        assert r3.headers["X-Concurrency-In-Flight"] == "2"
        assert r3.headers["X-Concurrency-Max"] == "2"
        assert r3.json()["error"]["type"] == "rate_limit"

        # Release the gate; the held requests complete.
        gate.set()
        for fut in in_flight:
            r = await fut
            assert r.status_code == 200

        # Capacity restored — next request admitted.
        r_after = await client.get("/v1/chat/completions")
        assert r_after.status_code == 200


@pytest.mark.asyncio
async def test_cap_bypasses_health_endpoint():
    """Liveness / readiness probes must never be capped."""
    gate = asyncio.Event()  # never set — the slow endpoint hangs forever
    app = _build_app(max_concurrency=1, gate=gate)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Hold the only slot.
        in_flight = asyncio.create_task(client.get("/v1/chat/completions"))
        for _ in range(20):
            await asyncio.sleep(0.01)

        # /health bypasses — succeeds even though cap is full.
        r = await client.get("/health")
        assert r.status_code == 200

        # Cleanup.
        gate.set()
        await in_flight
