"""Tests for audit logging middleware."""
import pytest
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock boto3
sys.modules.setdefault('boto3', MagicMock())
sys.modules.setdefault('botocore', MagicMock())
sys.modules.setdefault('botocore.exceptions', MagicMock())
sys.modules.setdefault('jose', MagicMock())
sys.modules.setdefault('jose.jwt', MagicMock())
sys.modules.setdefault('jose.jwk', MagicMock())

from middleware.audit import AuditLogMiddleware


class TestAuditLogMiddleware:
    """Test audit logging."""

    def test_middleware_exists(self):
        """AuditLogMiddleware class should exist."""
        assert AuditLogMiddleware is not None

    def test_middleware_is_starlette_middleware(self):
        """Should be a Starlette BaseHTTPMiddleware subclass."""
        from starlette.middleware.base import BaseHTTPMiddleware
        assert issubclass(AuditLogMiddleware, BaseHTTPMiddleware)
