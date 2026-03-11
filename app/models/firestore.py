"""
Firestore data access layer.

Handles all Firestore operations for session metadata, user data,
and audit logs. Confidential negotiation data is NEVER stored here —
it exists only inside the Confidential VM's encrypted memory.
"""
import time
import uuid
import logging
from typing import Optional

from google.cloud import firestore
from google.api_core import exceptions as gcp_exceptions

from config import (
    GCP_PROJECT_ID,
    FIRESTORE_DATABASE,
    SESSIONS_COLLECTION,
    AUDIT_LOGS_COLLECTION,
    USERS_COLLECTION,
)

logger = logging.getLogger("accord.firestore")


class FirestoreClient:
    """Firestore client for Accord metadata storage."""

    def __init__(self) -> None:
        self._db = None

    @property
    def db(self) -> firestore.Client:
        if self._db is None:
            kwargs = {}
            if GCP_PROJECT_ID:
                kwargs["project"] = GCP_PROJECT_ID
            if FIRESTORE_DATABASE and FIRESTORE_DATABASE != "(default)":
                kwargs["database"] = FIRESTORE_DATABASE
            self._db = firestore.Client(**kwargs)
        return self._db

    # ---- Sessions ----

    def put_session(self, session: dict) -> None:
        """Create or update a session record."""
        session.setdefault("createdAt", time.time())
        session.setdefault("updatedAt", time.time())
        session_id = session.get("sessionId")
        self.db.collection(SESSIONS_COLLECTION).document(session_id).set(session)

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        try:
            doc = self.db.collection(SESSIONS_COLLECTION).document(session_id).get()
            return doc.to_dict() if doc.exists else None
        except gcp_exceptions.GoogleAPICallError as e:
            logger.error(f"Firestore get_session error: {e}")
            return None

    def list_sessions(self, user_id: str) -> list[dict]:
        """List sessions created by a user."""
        try:
            docs = (
                self.db.collection(SESSIONS_COLLECTION)
                .where("createdBy", "==", user_id)
                .order_by("createdAt", direction=firestore.Query.DESCENDING)
                .stream()
            )
            return [doc.to_dict() for doc in docs]
        except gcp_exceptions.GoogleAPICallError as e:
            logger.error(f"Firestore list_sessions error: {e}")
            return []

    def update_session_status(self, session_id: str, status: str) -> None:
        """Update session status."""
        try:
            self.db.collection(SESSIONS_COLLECTION).document(session_id).update(
                {"status": status, "updatedAt": time.time()}
            )
        except gcp_exceptions.GoogleAPICallError as e:
            logger.error(f"Firestore update_session_status error: {e}")

    def update_session_field(self, session_id: str, field: str, value) -> None:
        """Update a specific field on a session."""
        try:
            self.db.collection(SESSIONS_COLLECTION).document(session_id).update(
                {field: value, "updatedAt": time.time()}
            )
        except gcp_exceptions.GoogleAPICallError as e:
            logger.error(f"Firestore update_session_field error: {e}")

    # ---- Audit Logs ----

    def put_audit_log(self, entry: dict) -> None:
        """Write an audit log entry."""
        entry.setdefault("auditId", str(uuid.uuid4()))
        entry.setdefault("timestamp", time.time())
        self.db.collection(AUDIT_LOGS_COLLECTION).document(entry["auditId"]).set(entry)

    def get_audit_logs(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get audit logs for a specific session."""
        try:
            docs = (
                self.db.collection(AUDIT_LOGS_COLLECTION)
                .where("sessionId", "==", session_id)
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [doc.to_dict() for doc in docs]
        except gcp_exceptions.GoogleAPICallError as e:
            logger.error(f"Firestore get_audit_logs error: {e}")
            return []

    def get_all_audit_logs(
        self, limit: int = 50, user_id_filter: Optional[str] = None
    ) -> list[dict]:
        """Get all audit logs (admin query)."""
        try:
            query = self.db.collection(AUDIT_LOGS_COLLECTION)
            if user_id_filter:
                query = query.where("userId", "==", user_id_filter)
            docs = (
                query.order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [doc.to_dict() for doc in docs]
        except gcp_exceptions.GoogleAPICallError as e:
            logger.error(f"Firestore get_all_audit_logs error: {e}")
            return []
