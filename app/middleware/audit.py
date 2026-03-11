"""
Audit logging middleware for SOC 2 Type II compliance.

Logs all API requests with user identity, action, resource,
timestamp, and outcome. Audit logs are emitted as structured
log entries for Cloud Logging ingestion.
"""
import time
import uuid
import logging
import json

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("accord.audit")


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Middleware that creates audit log entries for all API requests."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))

        # Execute request
        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Build audit entry
        user_id = getattr(request.state, 'user_id', 'anonymous')

        audit_entry = {
            "audit_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "request_id": request_id,
            "user_id": user_id,
            "method": request.method,
            "path": str(request.url.path),
            "query_params": str(request.query_params),
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "ip_address": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
        }

        # Emit structured log for Cloud Logging
        logger.info(json.dumps(audit_entry))

        # Add audit ID to response headers
        response.headers["X-Audit-ID"] = audit_entry["audit_id"]

        return response
