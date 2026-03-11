"""
Audit log query API routes.

Provides access to audit logs for compliance and dispute resolution.
All audit logs contain only redacted/non-confidential data.
"""
import logging

from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional

from models.dynamodb import DynamoDBClient

logger = logging.getLogger("accord.parent.audit")
router = APIRouter()
db = DynamoDBClient()


@router.get("/sessions/{session_id}/audit")
async def get_session_audit_log(
    session_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
):
    """
    Get audit log entries for a specific session.
    Returns redacted entries safe for external viewing.
    """
    logs = db.get_audit_logs(session_id, limit=limit)
    return {"session_id": session_id, "audit_logs": logs}


@router.get("/audit")
async def get_audit_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    user_id: Optional[str] = None,
):
    """
    Get audit logs (admin only).
    """
    user_groups = getattr(request.state, 'groups', [])
    if 'admin' not in user_groups:
        # Non-admins can only see their own logs
        user_id = getattr(request.state, 'user_id', 'anonymous')

    logs = db.get_all_audit_logs(limit=limit, user_id_filter=user_id)
    return {"audit_logs": logs}
