"""
Correlation ID middleware for SentinelFlow-AIOps.

Reads or generates an X-Correlation-ID header on every request and echoes
it back in the response.  This enables end-to-end trace stitching across
the FastAPI backend, WebSocket fan-out, and any downstream webhooks.
"""
from __future__ import annotations

import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

HEADER_NAME = "X-Correlation-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Injects or propagates a correlation ID for every HTTP request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get(HEADER_NAME) or str(uuid.uuid4())
        # Make the correlation ID available to route handlers via request.state
        request.state.correlation_id = correlation_id

        response: Response = await call_next(request)
        response.headers[HEADER_NAME] = correlation_id
        return response
