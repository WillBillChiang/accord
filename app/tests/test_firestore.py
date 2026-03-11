"""Tests for Firestore data access layer.

Verifies all Firestore CRUD operations for sessions and audit logs.
Replaces the DynamoDB tests from the parent-app, adapted for the
Google Cloud Firestore backend. No Decimal conversion tests are
needed because Firestore handles floats natively.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock google.cloud.firestore before importing the module
mock_firestore_module = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = mock_firestore_module

# Set up GoogleAPICallError as a real exception class.
# IMPORTANT: we must set the exceptions attribute on the api_core mock
# because `from google.api_core import exceptions` resolves via attribute
# access on the parent module, not via sys.modules lookup.
GoogleAPICallError = type('GoogleAPICallError', (Exception,), {})
mock_gcp_exceptions = MagicMock()
mock_gcp_exceptions.GoogleAPICallError = GoogleAPICallError
mock_api_core = MagicMock()
mock_api_core.exceptions = mock_gcp_exceptions
sys.modules['google.api_core'] = mock_api_core
sys.modules['google.api_core.exceptions'] = mock_gcp_exceptions

from models.firestore import FirestoreClient


class TestFirestoreClientCreation:
    """Test FirestoreClient instantiation."""

    def test_client_creation(self):
        """FirestoreClient should instantiate without error."""
        client = FirestoreClient()
        assert client is not None

    def test_client_lazy_init(self):
        """Firestore connection should not be created until first use."""
        client = FirestoreClient()
        assert client._db is None


class TestPutSession:
    """Test session creation in Firestore."""

    def test_put_session_calls_document_set(self):
        """put_session should call Firestore document.set()."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_doc
        client._db = mock_db

        session_data = {
            "sessionId": "test-001",
            "status": "active",
            "createdAt": 1234567890.0,
        }
        client.put_session(session_data)

        mock_db.collection.assert_called_once()
        mock_collection.document.assert_called_once_with("test-001")
        mock_doc.set.assert_called_once()

    def test_put_session_sets_default_timestamps(self):
        """put_session should set default createdAt and updatedAt."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_doc
        client._db = mock_db

        session_data = {"sessionId": "test-002", "status": "new"}
        client.put_session(session_data)

        call_args = mock_doc.set.call_args[0][0]
        assert "createdAt" in call_args
        assert "updatedAt" in call_args


class TestGetSession:
    """Test session retrieval from Firestore."""

    def test_get_session_found(self):
        """get_session should return session dict when document exists."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "sessionId": "test-001",
            "status": "active",
        }
        mock_doc_ref.get.return_value = mock_snapshot
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        result = client.get_session("test-001")
        assert result is not None
        assert result["sessionId"] == "test-001"
        assert result["status"] == "active"

    def test_get_session_not_found(self):
        """get_session should return None when document does not exist."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        result = client.get_session("nonexistent")
        assert result is None

    def test_get_session_handles_api_error(self):
        """get_session should return None on GoogleAPICallError."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.get.side_effect = GoogleAPICallError("test error")
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        result = client.get_session("test-error")
        assert result is None


class TestListSessions:
    """Test session listing with Firestore where filter."""

    def test_list_sessions_filters_by_user(self):
        """list_sessions should query Firestore with user_id where clause."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_query = MagicMock()

        mock_doc1 = MagicMock()
        mock_doc1.to_dict.return_value = {
            "sessionId": "s1",
            "status": "active",
            "createdBy": "user-123",
        }

        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.stream.return_value = [mock_doc1]

        mock_db.collection.return_value = mock_query
        client._db = mock_db

        result = client.list_sessions("user-123")
        assert len(result) == 1
        assert result[0]["sessionId"] == "s1"
        mock_query.where.assert_called_once_with("createdBy", "==", "user-123")

    def test_list_sessions_returns_empty_on_error(self):
        """list_sessions should return empty list on GoogleAPICallError."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.where.side_effect = GoogleAPICallError("test error")
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        result = client.list_sessions("user-123")
        assert result == []


class TestUpdateSessionStatus:
    """Test session status updates."""

    def test_update_session_status_calls_update(self):
        """update_session_status should call document.update()."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        client.update_session_status("test-001", "negotiating")

        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "negotiating"
        assert "updatedAt" in call_args

    def test_update_session_status_handles_error(self):
        """update_session_status should handle GoogleAPICallError gracefully."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = GoogleAPICallError("test error")
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        # Should not raise
        client.update_session_status("test-001", "error")


class TestPutAuditLog:
    """Test audit log creation."""

    def test_put_audit_log_calls_set(self):
        """put_audit_log should call Firestore document.set()."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        entry = {
            "sessionId": "s1",
            "action": "negotiation_started",
            "userId": "user-123",
        }
        client.put_audit_log(entry)

        mock_doc_ref.set.assert_called_once()

    def test_put_audit_log_generates_defaults(self):
        """put_audit_log should generate auditId and timestamp if missing."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        entry = {"sessionId": "s1", "action": "test"}
        client.put_audit_log(entry)

        assert "auditId" in entry
        assert "timestamp" in entry


class TestGetAuditLogs:
    """Test audit log retrieval."""

    def test_get_audit_logs_filters_by_session(self):
        """get_audit_logs should filter by session_id."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_query = MagicMock()

        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "auditId": "a1",
            "sessionId": "s1",
            "action": "negotiation_started",
        }

        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = [mock_doc]
        mock_db.collection.return_value = mock_query
        client._db = mock_db

        result = client.get_audit_logs("s1")
        assert len(result) == 1
        assert result[0]["sessionId"] == "s1"
        mock_query.where.assert_called_once_with("sessionId", "==", "s1")

    def test_get_audit_logs_returns_empty_on_error(self):
        """get_audit_logs should return empty list on error."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.where.side_effect = GoogleAPICallError("test error")
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        result = client.get_audit_logs("s1")
        assert result == []


class TestGetAllAuditLogs:
    """Test admin audit log query."""

    def test_get_all_audit_logs_no_filter(self):
        """get_all_audit_logs without filter should query all logs."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_query = MagicMock()

        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "auditId": "a1",
            "action": "test",
        }

        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = [mock_doc]
        mock_db.collection.return_value = mock_query
        client._db = mock_db

        result = client.get_all_audit_logs()
        assert len(result) == 1

    def test_get_all_audit_logs_with_user_filter(self):
        """get_all_audit_logs with user_id_filter should add where clause."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_query = MagicMock()

        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []
        mock_db.collection.return_value = mock_query
        client._db = mock_db

        result = client.get_all_audit_logs(user_id_filter="user-123")
        assert result == []
        mock_query.where.assert_called_once_with("userId", "==", "user-123")

    def test_get_all_audit_logs_returns_empty_on_error(self):
        """get_all_audit_logs should return empty list on error."""
        client = FirestoreClient()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.order_by.side_effect = GoogleAPICallError("test error")
        mock_db.collection.return_value = mock_collection
        client._db = mock_db

        result = client.get_all_audit_logs()
        assert result == []
