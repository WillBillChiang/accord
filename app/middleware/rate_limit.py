"""
Rate limiting middleware.

Implements sliding window rate limiting per IP address.
Configurable requests per minute threshold.
"""
import time
import logging
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("accord.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter per IP address."""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries
        self._requests[client_ip] = [
            t for t in self._requests[client_ip]
            if now - t < self.window_size
        ]

        # Check rate limit
        if len(self._requests[client_ip]) >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please retry later.",
            )

        # Record request
        self._requests[client_ip].append(now)

        return await call_next(request)
