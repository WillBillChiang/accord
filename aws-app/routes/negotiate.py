"""
Negotiation control API routes.

Start, monitor, and manage active negotiations.
"""
import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from vsock_client import get_vsock_client
from models.dynamodb import DynamoDBClient

logger = logging.getLogger("accord.parent.negotiate")
router = APIRouter()
db = DynamoDBClient()


@router.post("/sessions/{session_id}/start")
async def start_negotiation(session_id: str, request: Request):
    """
    Start the negotiation for a session.

    Both parties must be onboarded. The enclave will:
    1. Check ZOPA existence
    2. If ZOPA exists, run SAO protocol
    3. Return deal terms or no-deal outcome
    """
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get("sellerOnboarded") or not session.get("buyerOnboarded"):
        raise HTTPException(
            status_code=400,
            detail="Both parties must be onboarded before starting",
        )

    # Start negotiation in enclave
    vsock = get_vsock_client()
    db.update_session_status(session_id, "negotiating")

    try:
        result = vsock.send_command(
            {
                "action": "start_negotiation",
                "session_id": session_id,
            },
            timeout=300.0,  # 5 minute timeout for full negotiation
        )
    except RuntimeError as e:
        db.update_session_status(session_id, "error")
        raise HTTPException(status_code=500, detail=str(e))

    # Update session with outcome
    outcome = result.get("outcome", "error")
    db.update_session_status(session_id, outcome)

    if outcome == "deal_reached":
        db.update_session_field(session_id, "finalTerms", result.get("final_terms"))
        db.update_session_field(session_id, "finalPrice", result.get("final_price"))

    db.update_session_field(session_id, "roundsCompleted", result.get("rounds_completed", 0))

    # Log audit entry
    user_id = getattr(request.state, 'user_id', 'anonymous')
    db.put_audit_log({
        "sessionId": session_id,
        "action": "negotiation_completed",
        "userId": user_id,
        "outcome": outcome,
        "roundsCompleted": result.get("rounds_completed", 0),
    })

    return result


@router.get("/sessions/{session_id}/status")
async def get_negotiation_status(session_id: str):
    """Get real-time negotiation status from enclave."""
    vsock = get_vsock_client()

    try:
        result = vsock.send_command({
            "action": "get_status",
            "session_id": session_id,
        })
        return result
    except RuntimeError:
        # Fall back to DynamoDB metadata
        session = db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session_id": session_id,
            "status": session.get("status", "unknown"),
            "note": "Enclave unreachable, showing cached status",
        }
