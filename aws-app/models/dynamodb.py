"""
DynamoDB data access layer.

Handles all DynamoDB operations for session metadata, user data,
and audit logs. Confidential negotiation data is NEVER stored here —
it exists only inside the Nitro Enclave.
"""
import os
import time
import uuid
import logging
from typing import Optional
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("accord.parent.dynamodb")

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "accord-sessions")
AUDIT_TABLE = os.environ.get("AUDIT_TABLE", "accord-audit-log")
USERS_TABLE = os.environ.get("USERS_TABLE", "accord-users")


def _convert_floats(obj):
    """Convert floats to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_floats(v) for v in obj]
    return obj


def _convert_decimals(obj):
    """Convert Decimals back to floats for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(v) for v in obj]
    return obj


class DynamoDBClient:
    """DynamoDB client for Accord metadata storage."""

    def __init__(self) -> None:
        self._dynamodb = None

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            self._dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        return self._dynamodb

    # ---- Sessions ----

    def put_session(self, session: dict) -> None:
        """Create or update a session record."""
        table = self.dynamodb.Table(SESSIONS_TABLE)
        item = _convert_floats(session)
        item.setdefault("createdAt", Decimal(str(time.time())))
        item.setdefault("updatedAt", Decimal(str(time.time())))
        table.put_item(Item=item)

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        table = self.dynamodb.Table(SESSIONS_TABLE)
        try:
            response = table.get_item(Key={"sessionId": session_id})
            item = response.get("Item")
            return _convert_decimals(item) if item else None
        except ClientError as e:
            logger.error(f"DynamoDB get_session error: {e}")
            return None

    def list_sessions(self, user_id: str) -> list[dict]:
        """List sessions created by a user."""
        table = self.dynamodb.Table(SESSIONS_TABLE)
        try:
            response = table.scan(
                FilterExpression="createdBy = :uid",
                ExpressionAttributeValues={":uid": user_id},
            )
            return [_convert_decimals(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(f"DynamoDB list_sessions error: {e}")
            return []

    def update_session_status(self, session_id: str, status: str) -> None:
        """Update session status."""
        table = self.dynamodb.Table(SESSIONS_TABLE)
        try:
            table.update_item(
                Key={"sessionId": session_id},
                UpdateExpression="SET #s = :status, updatedAt = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":status": status,
                    ":now": Decimal(str(time.time())),
                },
            )
        except ClientError as e:
            logger.error(f"DynamoDB update_session_status error: {e}")

    def update_session_field(self, session_id: str, field: str, value) -> None:
        """Update a specific field on a session."""
        table = self.dynamodb.Table(SESSIONS_TABLE)
        try:
            table.update_item(
                Key={"sessionId": session_id},
                UpdateExpression=f"SET {field} = :val, updatedAt = :now",
                ExpressionAttributeValues={
                    ":val": _convert_floats(value),
                    ":now": Decimal(str(time.time())),
                },
            )
        except ClientError as e:
            logger.error(f"DynamoDB update_session_field error: {e}")

    # ---- Audit Logs ----

    def put_audit_log(self, entry: dict) -> None:
        """Write an audit log entry."""
        table = self.dynamodb.Table(AUDIT_TABLE)
        item = _convert_floats(entry)
        item.setdefault("auditId", str(uuid.uuid4()))
        item.setdefault("timestamp", Decimal(str(time.time())))
        table.put_item(Item=item)

    def get_audit_logs(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get audit logs for a specific session."""
        table = self.dynamodb.Table(AUDIT_TABLE)
        try:
            response = table.query(
                KeyConditionExpression="sessionId = :sid",
                ExpressionAttributeValues={":sid": session_id},
                ScanIndexForward=False,  # Newest first
                Limit=limit,
            )
            return [_convert_decimals(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(f"DynamoDB get_audit_logs error: {e}")
            return []

    def get_all_audit_logs(
        self, limit: int = 50, user_id_filter: Optional[str] = None
    ) -> list[dict]:
        """Get all audit logs (admin query)."""
        table = self.dynamodb.Table(AUDIT_TABLE)
        try:
            scan_kwargs = {"Limit": limit}
            if user_id_filter:
                scan_kwargs["FilterExpression"] = "userId = :uid"
                scan_kwargs["ExpressionAttributeValues"] = {":uid": user_id_filter}
            response = table.scan(**scan_kwargs)
            return [_convert_decimals(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(f"DynamoDB get_all_audit_logs error: {e}")
            return []
