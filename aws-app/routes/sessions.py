"""
Session management API routes.

CRUD operations for negotiation sessions.
Sessions metadata is stored in DynamoDB; confidential data
is only inside the enclave.
"""
import uuid
import time
import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from vsock_client import get_vsock_client
from models.dynamodb import DynamoDBClient

logger = logging.getLogger("accord.parent.sessions")
router = APIRouter()
db = DynamoDBClient()


class CreateSessionRequest(BaseModel):
    max_duration_sec: int = Field(default=3600, ge=60, le=86400)
    description: Optional[str] = None
    use_case: Optional[str] = None  # "ma", "ip_licensing", "vc_funding", "nda_replacement"


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: float
    created_by: str


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest, request: Request):
    """Create a new negotiation session."""
    user_id = getattr(request.state, 'user_id', 'anonymous')
    session_id = str(uuid.uuid4())

    # Create session in enclave
    vsock = get_vsock_client()
    enclave_response = vsock.send_command({
        "action": "create_session",
        "payload": {
            "session_id": session_id,
            "max_duration_sec": req.max_duration_sec,
        },
    })

    if "error" in enclave_response:
        raise HTTPException(status_code=500, detail=enclave_response["error"])

    # Store metadata in DynamoDB
    session_metadata = {
        "sessionId": session_id,
        "status": "awaiting_parties",
        "createdAt": time.time(),
        "createdBy": user_id,
        "description": req.description or "",
        "useCase": req.use_case or "",
        "maxDurationSec": req.max_duration_sec,
        "sellerOnboarded": False,
        "buyerOnboarded": False,
    }
    db.put_session(session_metadata)

    return CreateSessionResponse(
        session_id=session_id,
        status="awaiting_parties",
        created_at=session_metadata["createdAt"],
        created_by=user_id,
    )


@router.get("/sessions")
async def list_sessions(request: Request):
    """List all sessions for the authenticated user."""
    user_id = getattr(request.state, 'user_id', 'anonymous')
    sessions = db.list_sessions(user_id)
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """Get session details including real-time status from enclave."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get live status from enclave
    vsock = get_vsock_client()
    try:
        enclave_status = vsock.send_command({
            "action": "get_status",
            "session_id": session_id,
        })
        session["enclaveStatus"] = enclave_status
    except RuntimeError:
        session["enclaveStatus"] = {"status": "enclave_unreachable"}

    return session


@router.delete("/sessions/{session_id}")
async def terminate_session(session_id: str, request: Request):
    """Terminate a session and trigger provable deletion in enclave."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    vsock = get_vsock_client()
    result = vsock.send_command({
        "action": "terminate",
        "session_id": session_id,
        "payload": {"reason": "user_terminated"},
    })

    # Update DynamoDB
    db.update_session_status(session_id, "terminated")

    return result
