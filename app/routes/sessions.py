"""
Session management API routes.

CRUD operations for negotiation sessions.
Session metadata is stored in Firestore; confidential data
exists only in the Confidential VM's encrypted memory.
"""
import uuid
import time
import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from models.firestore import FirestoreClient
from engine.session import NegotiationSession
from engine.protocol.schemas import SessionStatus

logger = logging.getLogger("accord.sessions")
router = APIRouter()
db = FirestoreClient()

# In-memory session store (lives in Confidential VM encrypted memory)
_sessions: dict[str, NegotiationSession] = {}


def get_sessions() -> dict[str, NegotiationSession]:
    """Get the global sessions dict."""
    return _sessions


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

    # Create session in engine (in-memory, encrypted by SEV-SNP)
    session = NegotiationSession(
        session_id=session_id,
        max_duration_sec=req.max_duration_sec,
    )
    _sessions[session_id] = session

    # Store metadata in Firestore
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
    """Get session details including real-time status from engine."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get live status from in-memory engine
    engine_session = _sessions.get(session_id)
    if engine_session:
        session["engineStatus"] = {
            "status": engine_session.status.value,
            "current_round": engine_session.current_round,
            "is_expired": engine_session.is_expired(),
            "seller_onboarded": engine_session.seller_config is not None,
            "buyer_onboarded": engine_session.buyer_config is not None,
            "log": engine_session.get_redacted_log(),
        }
    else:
        session["engineStatus"] = {"status": "not_in_memory"}

    return session


@router.delete("/sessions/{session_id}")
async def terminate_session(session_id: str, request: Request):
    """Terminate a session and trigger provable deletion."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Terminate in engine (provable deletion via cryptographic zeroing)
    engine_session = _sessions.get(session_id)
    if engine_session:
        result = engine_session.terminate("user_terminated").model_dump()
        del _sessions[session_id]
    else:
        result = {"session_id": session_id, "outcome": "already_terminated"}

    # Update Firestore
    db.update_session_status(session_id, "terminated")

    return result
