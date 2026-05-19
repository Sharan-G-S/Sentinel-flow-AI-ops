"""Adds X-Response-Time-Ms header to every HTTP response."""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        return response
