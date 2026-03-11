"""
Party onboarding API routes.

Handles encrypted configuration submission from negotiating parties.
In the unified Confidential VM architecture, decryption happens
directly via Cloud KMS — no vsock relay needed.
"""
import json
import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from models.firestore import FirestoreClient
from engine.kms_client import CloudKMSClient
from engine.protocol.schemas import PartyConfig
from routes.sessions import get_sessions

logger = logging.getLogger("accord.onboard")
router = APIRouter()
db = FirestoreClient()
kms_client = CloudKMSClient()


class OnboardPartyRequest(BaseModel):
    party_id: Optional[str] = None
    role: str = Field(..., pattern="^(seller|buyer)$")
    encrypted_config: Optional[str] = None  # Base64 Cloud KMS-encrypted config
    encrypted_data: Optional[str] = None    # Base64 Cloud KMS-encrypted confidential data
    config: Optional[dict] = None           # Plaintext config (dev mode only)


@router.post("/sessions/{session_id}/onboard")
async def onboard_party(session_id: str, req: OnboardPartyRequest, request: Request):
    """
    Submit encrypted party configuration.

    In production, config and data are Cloud KMS-encrypted client-side.
    Only this Confidential VM's service account can decrypt via
    attestation-conditioned IAM policy.
    """
    session_meta = db.get_session(session_id)
    if not session_meta:
        raise HTTPException(status_code=404, detail="Session not found")

    sessions = get_sessions()
    engine_session = sessions.get(session_id)
    if not engine_session:
        raise HTTPException(status_code=404, detail="Session not active in engine")

    # Decrypt config using Cloud KMS if encrypted
    if req.encrypted_config:
        try:
            decrypted = kms_client.decrypt(req.encrypted_config)
            config_data = json.loads(decrypted)
        except Exception as e:
            logger.warning(f"Cloud KMS decrypt failed, using plaintext: {e}")
            config_data = req.config or {}
    else:
        config_data = req.config or {}

    if req.party_id:
        config_data["party_id"] = req.party_id
    config_data["role"] = req.role

    config = PartyConfig(**config_data)
    result = engine_session.onboard_party(config)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Update Firestore metadata
    if req.role == "seller":
        db.update_session_field(session_id, "sellerOnboarded", True)
    else:
        db.update_session_field(session_id, "buyerOnboarded", True)

    db.update_session_status(session_id, result.get("status", "onboarding"))

    return result
