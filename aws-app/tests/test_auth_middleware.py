"""Tests for Cognito JWT authentication middleware."""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock external dependencies
sys.modules.setdefault('boto3', MagicMock())
sys.modules.setdefault('botocore', MagicMock())
sys.modules.setdefault('botocore.exceptions', MagicMock())

mock_jwt = MagicMock()
mock_jwt.get_unverified_claims.return_value = {
    "sub": "user-123",
    "email": "user@example.com",
    "cognito:groups": ["admin"],
}
mock_jwt.get_unverified_header.return_value = {"kid": "key-1"}
sys.modules['jose'] = MagicMock()
sys.modules['jose.jwt'] = mock_jwt
sys.modules['jose.jwk'] = MagicMock()

from middleware.auth import CognitoAuthMiddleware, PUBLIC_PATHS


class TestPublicPaths:
    """Test that public paths are correctly defined."""

    def test_health_is_public(self):
        """Health endpoint should be public."""
        assert "/health" in PUBLIC_PATHS

    def test_docs_is_public(self):
        """Docs endpoint should be public."""
        assert "/docs" in PUBLIC_PATHS

    def test_attestation_is_public(self):
        """Attestation endpoint should be public."""
        assert "/api/v1/attestation" in PUBLIC_PATHS


class TestCognitoAuthMiddleware:
    """Test Cognito auth middleware."""

    def test_middleware_exists(self):
        """CognitoAuthMiddleware should exist."""
        assert CognitoAuthMiddleware is not None
