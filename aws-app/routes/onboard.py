"""
Party onboarding API routes.

Handles encrypted configuration submission from negotiating parties.
The parent relays encrypted data to the enclave — it NEVER sees
plaintext confidential data.
"""
import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from vsock_client import get_vsock_client
from models.dynamodb import DynamoDBClient

logger = logging.getLogger("accord.parent.onboard")
router = APIRouter()
db = DynamoDBClient()


class OnboardPartyRequest(BaseModel):
    party_id: Optional[str] = None
    role: str = Field(..., pattern="^(seller|buyer)$")
    encrypted_config: Optional[str] = None  # Base64 KMS-encrypted config
    encrypted_data: Optional[str] = None    # Base64 KMS-encrypted confidential data
    config: Optional[dict] = None           # Plaintext config (dev mode only)


@router.post("/sessions/{session_id}/onboard")
async def onboard_party(session_id: str, req: OnboardPartyRequest, request: Request):
    """
    Submit encrypted party configuration to the enclave.

    In production, config and data are KMS-encrypted client-side.
    Only the attested enclave can decrypt via KMS attestation policy.
    """
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Relay to enclave
    vsock = get_vsock_client()
    payload = {
        "party_id": req.party_id,
        "role": req.role,
    }

    if req.encrypted_config:
        payload["encrypted_config"] = req.encrypted_config
    if req.encrypted_data:
        payload["encrypted_data"] = req.encrypted_data
    if req.config:
        payload["config"] = req.config

    result = vsock.send_command({
        "action": "onboard",
        "session_id": session_id,
        "payload": payload,
    })

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Update DynamoDB metadata
    if req.role == "seller":
        db.update_session_field(session_id, "sellerOnboarded", True)
    else:
        db.update_session_field(session_id, "buyerOnboarded", True)

    db.update_session_status(session_id, result.get("status", "onboarding"))

    return result
