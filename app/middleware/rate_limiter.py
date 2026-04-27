"""
Rate-limiter middleware for SentinelFlow-AIOps.

Uses a sliding-window token-bucket algorithm per client IP to protect
/ingest and /ingest/batch from telemetry floods.  Limits are configurable
via environment variables (see config.py).
"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter.

    Attributes:
        max_requests: Maximum requests allowed in the window.
        window_seconds: Rolling window duration in seconds.
        protected_paths: Path prefixes that are rate-limited.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.protected_paths = ("/ingest",)
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not any(request.url.path.startswith(p) for p in self.protected_paths):
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._windows[key]
            # Evict timestamps outside the rolling window
            self._windows[key] = [t for t in timestamps if t > cutoff]
            if len(self._windows[key]) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - self._windows[key][0]))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": (
                            f"Too many requests. Limit: {self.max_requests} "
                            f"per {self.window_seconds}s window."
                        ),
                        "retry_after_seconds": max(retry_after, 1),
                    },
                    headers={"Retry-After": str(max(retry_after, 1))},
                )
            self._windows[key].append(now)

        return await call_next(request)
