"""Tests for parent app API routes."""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock boto3 before importing modules that use it
mock_dynamodb = MagicMock()
mock_boto3 = MagicMock()
mock_boto3.resource.return_value = mock_dynamodb
sys.modules['boto3'] = mock_boto3

# Mock jose
mock_jose = MagicMock()
mock_jose_jwt = MagicMock()
mock_jose_jwt.get_unverified_claims.return_value = {"sub": "test-user", "email": "test@test.com"}
mock_jose_jwt.get_unverified_header.return_value = {"kid": "test-key"}
sys.modules['jose'] = mock_jose
sys.modules['jose.jwt'] = mock_jose_jwt
sys.modules['jose.jwk'] = MagicMock()

from fastapi.testclient import TestClient


def get_test_app():
    """Create a test FastAPI app with mocked dependencies."""
    # Need to import after mocking
    with patch.dict(os.environ, {
        'COGNITO_USER_POOL_ID': '',
        'COGNITO_APP_CLIENT_ID': '',
        'SESSIONS_TABLE': 'test-sessions',
        'AUDIT_TABLE': 'test-audit',
    }):
        from server import app
        return app


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_200(self):
        """Health check should return 200."""
        app = get_test_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "accord-parent"


class TestSessionRoutes:
    """Test session CRUD routes."""

    @patch('routes.sessions.get_vsock_client')
    @patch('routes.sessions.db')
    def test_create_session(self, mock_db, mock_vsock_fn):
        """Creating a session should call enclave and store in DynamoDB."""
        mock_vsock = MagicMock()
        mock_vsock.send_command.return_value = {
            "session_id": "test-session-001",
            "status": "awaiting_parties",
            "created_at": 1234567890.0,
        }
        mock_vsock_fn.return_value = mock_vsock

        app = get_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/sessions",
            json={"max_duration_sec": 3600, "description": "Test negotiation"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "awaiting_parties"

    @patch('routes.sessions.db')
    def test_list_sessions(self, mock_db):
        """Listing sessions should return user's sessions."""
        mock_db.list_sessions.return_value = [
            {"sessionId": "s1", "status": "active", "createdBy": "test-user"},
        ]

        app = get_test_app()
        client = TestClient(app)
        response = client.get(
            "/api/v1/sessions",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data

    @patch('routes.sessions.get_vsock_client')
    @patch('routes.sessions.db')
    def test_get_session(self, mock_db, mock_vsock_fn):
        """Getting a session should return session details."""
        mock_db.get_session.return_value = {
            "sessionId": "s1",
            "status": "awaiting_parties",
        }
        mock_vsock = MagicMock()
        mock_vsock.send_command.return_value = {"status": "awaiting_parties"}
        mock_vsock_fn.return_value = mock_vsock

        app = get_test_app()
        client = TestClient(app)
        response = client.get(
            "/api/v1/sessions/s1",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200

    @patch('routes.sessions.db')
    def test_get_nonexistent_session(self, mock_db):
        """Getting a nonexistent session should return 404."""
        mock_db.get_session.return_value = None

        app = get_test_app()
        client = TestClient(app)
        response = client.get(
            "/api/v1/sessions/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404


class TestOnboardRoutes:
    """Test party onboarding routes."""

    @patch('routes.onboard.get_vsock_client')
    @patch('routes.onboard.db')
    def test_onboard_seller(self, mock_db, mock_vsock_fn):
        """Onboarding a seller should relay to enclave."""
        mock_db.get_session.return_value = {"sessionId": "s1", "status": "awaiting_parties"}
        mock_vsock = MagicMock()
        mock_vsock.send_command.return_value = {
            "session_id": "s1",
            "status": "onboarding",
            "party_id": "p1",
            "role": "seller",
        }
        mock_vsock_fn.return_value = mock_vsock

        app = get_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/sessions/s1/onboard",
            json={
                "role": "seller",
                "config": {
                    "role": "seller",
                    "budget_cap": 100000,
                    "reservation_price": 120000,
                },
            },
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200

    @patch('routes.onboard.db')
    def test_onboard_nonexistent_session(self, mock_db):
        """Onboarding to nonexistent session should return 404."""
        mock_db.get_session.return_value = None

        app = get_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/sessions/nonexistent/onboard",
            json={"role": "seller"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404


class TestAttestationRoutes:
    """Test attestation routes."""

    @patch('routes.attestation.get_vsock_client')
    def test_get_attestation(self, mock_vsock_fn):
        """Getting attestation should return PCR values."""
        mock_vsock = MagicMock()
        mock_vsock.send_command.return_value = {
            "pcr0": "abc123",
            "pcr1": "def456",
            "pcr2": "ghi789",
            "timestamp": 1234567890.0,
        }
        mock_vsock_fn.return_value = mock_vsock

        app = get_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/attestation")

        assert response.status_code == 200
        data = response.json()
        assert "pcr0" in data
        assert "pcr1" in data
        assert "pcr2" in data
