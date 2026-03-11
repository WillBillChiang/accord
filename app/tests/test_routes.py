"""Tests for Accord API routes.

Verifies session CRUD, onboarding, negotiation start, status retrieval,
health check, and attestation endpoints. Uses FastAPI TestClient with
mocked Firestore and engine dependencies. Updated from the parent-app
version for the unified GCP Confidential VM architecture.
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock google.cloud modules before importing app modules
mock_firestore_module = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = mock_firestore_module
sys.modules['google.cloud.kms'] = MagicMock()
sys.modules['google.api_core'] = MagicMock()
sys.modules['google.api_core.exceptions'] = MagicMock()

# Mock Firebase Admin SDK
mock_firebase_admin = MagicMock()
mock_firebase_auth = MagicMock()
sys.modules['firebase_admin'] = mock_firebase_admin
sys.modules['firebase_admin.auth'] = mock_firebase_auth
sys.modules['firebase_admin.credentials'] = MagicMock()

# Mock httpx for attestation
sys.modules.setdefault('httpx', MagicMock())

from fastapi.testclient import TestClient


def get_test_app():
    """Create a test FastAPI app with mocked dependencies."""
    with patch.dict(os.environ, {
        'FIREBASE_PROJECT_ID': '',
        'GCP_PROJECT_ID': '',
        'SESSIONS_COLLECTION': 'test-sessions',
        'AUDIT_LOGS_COLLECTION': 'test-audit',
    }):
        from main import app
        return app


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_200(self):
        """Health check should return 200 with healthy status."""
        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "accord"
        assert data["platform"] == "gcp-confidential-vm"


class TestSessionRoutes:
    """Test session CRUD routes."""

    @patch('routes.sessions.db')
    def test_create_session(self, mock_db):
        """Creating a session should create engine session and store in Firestore."""
        mock_db.put_session.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/sessions",
            json={"max_duration_sec": 3600, "description": "Test negotiation"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "awaiting_parties"
        assert "created_at" in data
        mock_db.put_session.assert_called_once()

    @patch('routes.sessions.db')
    def test_list_sessions(self, mock_db):
        """Listing sessions should return user's sessions from Firestore."""
        mock_db.list_sessions.return_value = [
            {"sessionId": "s1", "status": "active", "createdBy": "dev-user"},
        ]

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/v1/sessions",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 1

    @patch('routes.sessions.db')
    def test_get_session(self, mock_db):
        """Getting a session should return session details with engine status."""
        mock_db.get_session.return_value = {
            "sessionId": "s1",
            "status": "awaiting_parties",
        }

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/v1/sessions/s1",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sessionId"] == "s1"

    @patch('routes.sessions.db')
    def test_get_nonexistent_session(self, mock_db):
        """Getting a nonexistent session should return 404."""
        mock_db.get_session.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/v1/sessions/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404

    @patch('routes.sessions.db')
    def test_terminate_session(self, mock_db):
        """Deleting a session should terminate and update Firestore."""
        mock_db.get_session.return_value = {
            "sessionId": "s1",
            "status": "active",
        }
        mock_db.update_session_status.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.delete(
            "/api/v1/sessions/s1",
            headers={"Authorization": "Bearer test-token"},
        )

        # Session may or may not be in engine memory, but should not 500
        assert response.status_code == 200

    @patch('routes.sessions.db')
    def test_terminate_nonexistent_session(self, mock_db):
        """Terminating a nonexistent session should return 404."""
        mock_db.get_session.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.delete(
            "/api/v1/sessions/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404


class TestOnboardRoutes:
    """Test party onboarding routes."""

    @patch('routes.onboard.db')
    @patch('routes.onboard.kms_client')
    def test_onboard_party(self, mock_kms, mock_db):
        """Onboarding a party should register config in engine."""
        # First create a session in engine
        from routes.sessions import _sessions, get_sessions
        from engine.session import NegotiationSession
        session = NegotiationSession(session_id="s-onboard")
        _sessions["s-onboard"] = session

        mock_db.get_session.return_value = {
            "sessionId": "s-onboard",
            "status": "awaiting_parties",
        }
        mock_db.update_session_field.return_value = None
        mock_db.update_session_status.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/sessions/s-onboard/onboard",
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
        data = response.json()
        assert data["role"] == "seller"

        # Clean up
        if "s-onboard" in _sessions:
            del _sessions["s-onboard"]

    @patch('routes.onboard.db')
    def test_onboard_nonexistent_session(self, mock_db):
        """Onboarding to nonexistent session should return 404."""
        mock_db.get_session.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/sessions/nonexistent/onboard",
            json={"role": "seller"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404


class TestNegotiateRoutes:
    """Test negotiation control routes."""

    @patch('routes.negotiate.db')
    def test_get_status_from_engine(self, mock_db):
        """GET /sessions/{id}/status should return engine status."""
        from routes.sessions import _sessions
        from engine.session import NegotiationSession
        session = NegotiationSession(session_id="s-status")
        _sessions["s-status"] = session

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/v1/sessions/s-status/status",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "s-status"
        assert data["status"] == "awaiting_parties"

        # Clean up
        if "s-status" in _sessions:
            del _sessions["s-status"]

    @patch('routes.negotiate.db')
    def test_get_status_fallback_to_firestore(self, mock_db):
        """Status should fall back to Firestore when session not in engine."""
        mock_db.get_session.return_value = {
            "sessionId": "s-stored",
            "status": "completed",
        }

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/v1/sessions/s-stored/status",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    @patch('routes.negotiate.db')
    def test_get_status_not_found(self, mock_db):
        """Status for nonexistent session should return 404."""
        mock_db.get_session.return_value = None

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/api/v1/sessions/nonexistent/status",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 404

    @patch('routes.negotiate.db')
    def test_start_negotiation_requires_both_parties(self, mock_db):
        """Starting negotiation without both parties should return 400."""
        mock_db.get_session.return_value = {
            "sessionId": "s-start",
            "status": "awaiting_parties",
            "sellerOnboarded": True,
            "buyerOnboarded": False,
        }

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/sessions/s-start/start",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 400


class TestAttestationRoutes:
    """Test attestation routes."""

    @patch('routes.attestation.get_attestation_document')
    def test_get_attestation(self, mock_get_attest):
        """GET /attestation should return attestation document."""
        from engine.protocol.schemas import AttestationDocument
        mock_get_attest.return_value = AttestationDocument(
            image_digest="abc123",
            sev_snp_enabled=True,
            secure_boot=True,
            vm_id="vm-001",
        )

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/attestation")

        assert response.status_code == 200
        data = response.json()
        assert data["image_digest"] == "abc123"
        assert data["sev_snp_enabled"] is True
        assert data["secure_boot"] is True
        assert data["vm_id"] == "vm-001"

    @patch('routes.attestation.verify_attestation')
    @patch('routes.attestation.get_attestation_document')
    def test_verify_attestation(self, mock_get_attest, mock_verify):
        """POST /attestation/verify should verify attestation claims."""
        from engine.protocol.schemas import AttestationDocument
        doc = AttestationDocument(
            image_digest="expected-digest",
            sev_snp_enabled=True,
            secure_boot=True,
            vm_id="vm-001",
        )
        mock_get_attest.return_value = doc
        mock_verify.return_value = True

        app = get_test_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/attestation/verify",
            json={
                "expected_image_digest": "expected-digest",
                "require_sev_snp": True,
                "require_secure_boot": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["image_digest_match"] is True
