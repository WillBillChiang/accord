"""
Attestation verification API routes.

Allows parties to verify the enclave is running the exact
published code before submitting their confidential data.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from vsock_client import get_vsock_client

logger = logging.getLogger("accord.parent.attestation")
router = APIRouter()


class AttestationResponse(BaseModel):
    pcr0: str
    pcr1: str
    pcr2: str
    timestamp: float
    nonce: Optional[str] = None


class VerifyRequest(BaseModel):
    expected_pcr0: str
    expected_pcr1: Optional[str] = None
    expected_pcr2: Optional[str] = None


@router.get("/attestation", response_model=AttestationResponse)
async def get_attestation(nonce: Optional[str] = None):
    """
    Get the enclave attestation document.

    Returns PCR values that prove the exact code running inside
    the enclave. Parties should compare these against the published
    PCR values before submitting data.
    """
    vsock = get_vsock_client()

    try:
        result = vsock.send_command({
            "action": "get_attestation",
            "payload": {"nonce": nonce},
        })
        return AttestationResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Enclave unreachable: {e}")


@router.post("/attestation/verify")
async def verify_attestation(req: VerifyRequest):
    """Verify enclave attestation against expected PCR values."""
    vsock = get_vsock_client()

    try:
        attestation = vsock.send_command({
            "action": "get_attestation",
            "payload": {},
        })
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Enclave unreachable: {e}")

    # Compare PCR values
    pcr0_match = attestation.get("pcr0") == req.expected_pcr0
    pcr1_match = req.expected_pcr1 is None or attestation.get("pcr1") == req.expected_pcr1
    pcr2_match = req.expected_pcr2 is None or attestation.get("pcr2") == req.expected_pcr2

    verified = pcr0_match and pcr1_match and pcr2_match

    return {
        "verified": verified,
        "pcr0_match": pcr0_match,
        "pcr1_match": pcr1_match,
        "pcr2_match": pcr2_match,
        "attestation": attestation,
    }
