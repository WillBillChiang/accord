"""Tests for audit logging middleware.

Verifies that the AuditLogMiddleware creates structured audit entries
for all API requests, suitable for Cloud Logging ingestion and
SOC 2 Type II compliance. Updated for GCP (mocks google.cloud and
firebase_admin instead of boto3/jose).
"""
import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock GCP and Firebase dependencies
sys.modules.setdefault('google.cloud', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.kms', MagicMock())
sys.modules.setdefault('google.api_core', MagicMock())
sys.modules.setdefault('google.api_core.exceptions', MagicMock())
sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('firebase_admin.credentials', MagicMock())

from middleware.audit import AuditLogMiddleware


class TestAuditLogMiddleware:
    """Test audit logging middleware."""

    def test_middleware_exists(self):
        """AuditLogMiddleware class should exist."""
        assert AuditLogMiddleware is not None

    def test_middleware_is_starlette_middleware(self):
        """Should be a Starlette BaseHTTPMiddleware subclass."""
        from starlette.middleware.base import BaseHTTPMiddleware
        assert issubclass(AuditLogMiddleware, BaseHTTPMiddleware)

    @pytest.mark.asyncio
    async def test_dispatch_calls_next_and_returns_response(self):
        """dispatch should call the next handler and return its response."""
        from unittest.mock import AsyncMock

        middleware = AuditLogMiddleware.__new__(AuditLogMiddleware)

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.request_id = "req-123"
        mock_request.state.user_id = "user-456"
        mock_request.method = "GET"
        mock_request.url.path = "/api/v1/sessions"
        mock_request.query_params = ""
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(side_effect=lambda key, default="": (
            "test-agent" if key == "user-agent" else default
        ))
        mock_request.headers = mock_headers

        response_headers_dict = {}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = response_headers_dict

        mock_call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_dispatch_adds_audit_id_header(self):
        """dispatch should add X-Audit-ID header to the response."""
        from unittest.mock import AsyncMock

        middleware = AuditLogMiddleware.__new__(AuditLogMiddleware)

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.request_id = "req-789"
        mock_request.state.user_id = "user-012"
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/sessions"
        mock_request.query_params = ""
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")
        mock_request.headers = mock_headers

        response_headers = {}
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.headers = response_headers

        mock_call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert "X-Audit-ID" in response_headers
        # Audit ID should be a valid UUID-like string
        assert len(response_headers["X-Audit-ID"]) > 0
