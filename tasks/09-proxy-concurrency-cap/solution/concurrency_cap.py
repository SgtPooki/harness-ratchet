"""Concurrent-request ceiling middleware.

Caps the number of in-flight requests forwarded to the vLLM backend. When
the cap is reached, returns 503 + Retry-After instead of admitting more
work that the backend cannot serve. Closes the second half of homelab2#157
(catalog --max-num-seqs is a soft cap; this middleware enforces it at the
front door regardless of who is calling).

Defaults are deliberately permissive: 16 in-flight requests, which is
2x the typical catalog --max-num-seqs=8. The intent is "only reject under
genuinely abusive load (e.g. unbounded benchmarks)", not "shape healthy
traffic". Tune via VLLM_PROXY_MAX_CONCURRENCY.

Health and SSE endpoints bypass the cap so liveness probes and the
swap-phase stream are not affected by load.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("vllm-proxy.concurrency-cap")

MAX_CONCURRENCY = int(os.environ.get("VLLM_PROXY_MAX_CONCURRENCY", "16"))
RETRY_AFTER = int(os.environ.get("VLLM_PROXY_RETRY_AFTER", "5"))

# Paths that must never be capped (probes, observability, swap-phase awareness).
_BYPASS_PATHS = frozenset(
    {
        "/health",
        "/healthz",
        "/metrics",
        "/api/outcomes",
    }
)


class ConcurrencyCap(BaseHTTPMiddleware):
    """Counter-gated cap on in-flight upstream requests.

    A plain counter (under an asyncio.Lock) is used instead of a Semaphore so
    that requests above the cap are *rejected immediately* rather than queued
    waiting for an upstream slot. Queueing here would silently grow latency
    on healthy clients while the abusive caller keeps holding their slot.
    """

    def __init__(self, app, max_concurrency: int = MAX_CONCURRENCY):
        super().__init__(app)
        self._max = max_concurrency
        self._in_flight = 0
        self._rejections = 0
        self._lock = asyncio.Lock()

    async def _try_admit(self) -> bool:
        async with self._lock:
            if self._in_flight >= self._max:
                self._rejections += 1
                return False
            self._in_flight += 1
            return True

    async def _release(self) -> None:
        async with self._lock:
            self._in_flight -= 1

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _BYPASS_PATHS:
            return await call_next(request)

        admitted = await self._try_admit()
        if not admitted:
            log.warning(
                "concurrency cap hit: in_flight=%d max=%d total_rejections=%d path=%s",
                self._in_flight,
                self._max,
                self._rejections,
                request.url.path,
            )
            return JSONResponse(
                {
                    "error": {
                        "type": "rate_limit",
                        "message": (
                            f"vLLM backend at concurrency cap "
                            f"({self._in_flight}/{self._max} in flight). Retry after "
                            f"{RETRY_AFTER}s."
                        ),
                    }
                },
                status_code=503,
                headers={
                    "Retry-After": str(RETRY_AFTER),
                    "X-Concurrency-In-Flight": str(self._in_flight),
                    "X-Concurrency-Max": str(self._max),
                },
            )

        started = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            await self._release()
        response.headers["X-Concurrency-In-Flight"] = str(self._in_flight)
        response.headers["X-Concurrency-Max"] = str(self._max)
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "served path=%s in_flight=%d duration_ms=%.0f",
                request.url.path,
                self._in_flight,
                (time.monotonic() - started) * 1000,
            )
        return response
