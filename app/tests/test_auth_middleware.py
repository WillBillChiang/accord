"""Tests for Firebase Auth authentication middleware.

Verifies token validation, MFA enforcement, public path access,
dev mode bypass, WebSocket path skipping, and custom claims
extraction. Replaces the Cognito JWT middleware tests from
the parent-app.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock Firebase Admin SDK before importing the middleware.
# IMPORTANT: set attributes on mock_firebase_admin so that
# `from firebase_admin import auth` resolves via attribute access.
mock_firebase_admin = MagicMock()
mock_firebase_auth = MagicMock()
mock_firebase_credentials = MagicMock()
mock_firebase_admin.auth = mock_firebase_auth
mock_firebase_admin.credentials = mock_firebase_credentials
sys.modules['firebase_admin'] = mock_firebase_admin
sys.modules['firebase_admin.auth'] = mock_firebase_auth
sys.modules['firebase_admin.credentials'] = mock_firebase_credentials

# Mock google.cloud for other imports
sys.modules.setdefault('google.cloud', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.kms', MagicMock())
sys.modules.setdefault('google.api_core', MagicMock())
sys.modules.setdefault('google.api_core.exceptions', MagicMock())

from middleware.auth import FirebaseAuthMiddleware, PUBLIC_PATHS, verify_token


@pytest.fixture(autouse=True)
def _ensure_firebase_mocks():
    """Re-set sys.modules to our mocks before each test.

    Other test files (e.g. test_routes.py) may overwrite sys.modules
    entries during collection. This fixture ensures our mocks are
    active for every test in this file.
    """
    sys.modules['firebase_admin'] = mock_firebase_admin
    sys.modules['firebase_admin.auth'] = mock_firebase_auth
    sys.modules['firebase_admin.credentials'] = mock_firebase_credentials
    mock_firebase_admin.auth = mock_firebase_auth
    mock_firebase_auth.reset_mock()
    yield


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

    def test_openapi_is_public(self):
        """OpenAPI JSON endpoint should be public."""
        assert "/openapi.json" in PUBLIC_PATHS


class TestFirebaseAuthMiddleware:
    """Test Firebase auth middleware behavior."""

    def test_middleware_exists(self):
        """FirebaseAuthMiddleware should exist and be importable."""
        assert FirebaseAuthMiddleware is not None

    def test_middleware_is_starlette_middleware(self):
        """Should be a Starlette BaseHTTPMiddleware subclass."""
        from starlette.middleware.base import BaseHTTPMiddleware
        assert issubclass(FirebaseAuthMiddleware, BaseHTTPMiddleware)

    @pytest.mark.asyncio
    async def test_public_path_no_auth_required(self):
        """Public paths should be accessible without any token."""
        middleware = FirebaseAuthMiddleware.__new__(FirebaseAuthMiddleware)

        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_response = MagicMock()

        mock_call_next = AsyncMock(return_value=mock_response)
        result = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_websocket_path_skips_auth(self):
        """WebSocket paths should skip authentication."""
        middleware = FirebaseAuthMiddleware.__new__(FirebaseAuthMiddleware)

        mock_request = MagicMock()
        mock_request.url.path = "/ws/negotiations/test-session"
        mock_response = MagicMock()

        mock_call_next = AsyncMock(return_value=mock_response)
        result = await middleware.dispatch(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_missing_bearer_token_returns_401(self):
        """Protected path without Bearer token should raise 401."""
        from fastapi import HTTPException

        middleware = FirebaseAuthMiddleware.__new__(FirebaseAuthMiddleware)

        mock_request = MagicMock()
        mock_request.url.path = "/api/v1/sessions"
        mock_request.headers = {"Authorization": ""}

        mock_call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(mock_request, mock_call_next)

        assert exc_info.value.status_code == 401
        assert "Missing authorization token" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_no_auth_header_returns_401(self):
        """Protected path without Authorization header should raise 401."""
        from fastapi import HTTPException

        middleware = FirebaseAuthMiddleware.__new__(FirebaseAuthMiddleware)

        mock_request = MagicMock()
        mock_request.url.path = "/api/v1/sessions"
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="")
        mock_request.headers = mock_headers

        mock_call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(mock_request, mock_call_next)

        assert exc_info.value.status_code == 401


class TestVerifyToken:
    """Test token verification logic."""

    @pytest.mark.asyncio
    async def test_dev_mode_returns_dev_user(self):
        """When FIREBASE_PROJECT_ID is not set, should return dev user."""
        with patch('middleware.auth.FIREBASE_PROJECT_ID', ''):
            claims = await verify_token("any-token")
            assert claims["uid"] == "dev-user"
            assert claims["email"] == "dev@localhost"
            assert "admin" in claims["groups"]

    @pytest.mark.asyncio
    async def test_valid_token_with_mfa(self):
        """Valid token with TOTP MFA should return decoded claims."""
        mock_firebase_auth.verify_id_token.return_value = {
            "uid": "user-123",
            "email": "user@example.com",
            "groups": ["users"],
            "firebase": {"sign_in_second_factor": "totp"},
        }

        with patch('middleware.auth.FIREBASE_PROJECT_ID', 'test-project'):
            with patch('middleware.auth._firebase_initialized', True):
                claims = await verify_token("valid-token")
                assert claims["uid"] == "user-123"
                assert claims["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_missing_mfa_raises(self):
        """Token without TOTP MFA claim should raise ValueError."""
        mock_firebase_auth.verify_id_token.return_value = {
            "uid": "user-456",
            "email": "user@example.com",
            "firebase": {"sign_in_second_factor": None},
        }

        with patch('middleware.auth.FIREBASE_PROJECT_ID', 'test-project'):
            with patch('middleware.auth._firebase_initialized', True):
                with pytest.raises(ValueError, match="Token verification failed"):
                    await verify_token("no-mfa-token")

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self):
        """Invalid token should raise ValueError."""
        mock_firebase_auth.verify_id_token.side_effect = Exception(
            "Token expired"
        )

        with patch('middleware.auth.FIREBASE_PROJECT_ID', 'test-project'):
            with patch('middleware.auth._firebase_initialized', True):
                with pytest.raises(ValueError, match="Token verification failed"):
                    await verify_token("expired-token")

        # Reset side_effect for other tests
        mock_firebase_auth.verify_id_token.side_effect = None


class TestValidTokenSetsRequestState:
    """Test that valid tokens correctly populate request.state."""

    @pytest.mark.asyncio
    async def test_valid_token_sets_user_id_and_email(self):
        """Valid token should set request.state.user_id and email."""
        mock_firebase_auth.verify_id_token.return_value = {
            "uid": "user-789",
            "email": "alice@example.com",
            "groups": ["users"],
            "firebase": {"sign_in_second_factor": "totp"},
        }
        mock_firebase_auth.verify_id_token.side_effect = None

        middleware = FirebaseAuthMiddleware.__new__(FirebaseAuthMiddleware)

        mock_request = MagicMock()
        mock_request.url.path = "/api/v1/sessions"
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(side_effect=lambda key, default="": (
            "Bearer valid-token-789" if key == "Authorization" else default
        ))
        mock_request.headers = mock_headers
        mock_request.state = MagicMock()
        mock_response = MagicMock()

        mock_call_next = AsyncMock(return_value=mock_response)

        with patch('middleware.auth.FIREBASE_PROJECT_ID', 'test-project'):
            with patch('middleware.auth._firebase_initialized', True):
                result = await middleware.dispatch(mock_request, mock_call_next)

        assert mock_request.state.user_id == "user-789"
        assert mock_request.state.email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_admin_claim_adds_admin_group(self):
        """Token with admin custom claim should add admin to groups."""
        mock_firebase_auth.verify_id_token.return_value = {
            "uid": "admin-user",
            "email": "admin@example.com",
            "groups": ["users"],
            "admin": True,
            "firebase": {"sign_in_second_factor": "totp"},
        }
        mock_firebase_auth.verify_id_token.side_effect = None

        middleware = FirebaseAuthMiddleware.__new__(FirebaseAuthMiddleware)

        mock_request = MagicMock()
        mock_request.url.path = "/api/v1/sessions"
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(side_effect=lambda key, default="": (
            "Bearer admin-token" if key == "Authorization" else default
        ))
        mock_request.headers = mock_headers
        mock_request.state = MagicMock()
        mock_response = MagicMock()

        mock_call_next = AsyncMock(return_value=mock_response)

        with patch('middleware.auth.FIREBASE_PROJECT_ID', 'test-project'):
            with patch('middleware.auth._firebase_initialized', True):
                result = await middleware.dispatch(mock_request, mock_call_next)

        assert "admin" in mock_request.state.groups
