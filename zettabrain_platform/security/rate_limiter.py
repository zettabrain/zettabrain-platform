"""Lightweight rate limiting middleware (SOC2 CC6.6 — protection against abuse)."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class RateLimitState:
    def __init__(self, requests_per_minute: int = 60, burst: int = 10):
        self.rpm = requests_per_minute
        self.burst = burst
        self._windows: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - 60.0
        hits = self._windows[key]
        hits[:] = [t for t in hits if t > window_start]

        if len(hits) >= self.rpm:
            retry_after = int(hits[0] - window_start) + 1
            return False, retry_after

        hits.append(now)
        return True, 0


_state = RateLimitState()


def create_rate_limiter(requests_per_minute: int = 60) -> "RateLimitMiddleware":
    global _state
    _state = RateLimitState(requests_per_minute=requests_per_minute)
    return RateLimitMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/static"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = _state.is_allowed(client_ip)

        if not allowed:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "Content-Type": "application/json",
                },
            )

        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers (HSTS, CSP, etc.) to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
