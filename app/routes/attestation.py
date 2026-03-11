"""
Attestation verification API routes.

Allows parties to verify the Confidential VM is running the exact
published code before submitting their confidential data.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from engine.attestation import get_attestation_document, verify_attestation

logger = logging.getLogger("accord.attestation")
router = APIRouter()


class AttestationResponse(BaseModel):
    image_digest: str
    sev_snp_enabled: bool
    secure_boot: bool
    vm_id: str
    timestamp: float
    nonce: Optional[str] = None


class VerifyRequest(BaseModel):
    expected_image_digest: str
    require_sev_snp: bool = True
    require_secure_boot: bool = True


@router.get("/attestation", response_model=AttestationResponse)
async def get_attestation(nonce: Optional[str] = None):
    """
    Get the Confidential VM attestation document.

    Returns integrity claims that prove the exact code running inside
    the VM and its confidential computing status. Parties should compare
    these against the published values before submitting data.
    """
    try:
        doc = get_attestation_document(nonce=nonce)
        return AttestationResponse(**doc.model_dump())
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Attestation unavailable: {e}")


@router.post("/attestation/verify")
async def verify_attestation_endpoint(req: VerifyRequest):
    """Verify Confidential VM attestation against expected values."""
    try:
        doc = get_attestation_document()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Attestation unavailable: {e}")

    verified = verify_attestation(
        document=doc,
        expected_image_digest=req.expected_image_digest,
        require_sev_snp=req.require_sev_snp,
        require_secure_boot=req.require_secure_boot,
    )

    return {
        "verified": verified,
        "image_digest_match": doc.image_digest == req.expected_image_digest,
        "sev_snp_enabled": doc.sev_snp_enabled,
        "secure_boot_enabled": doc.secure_boot,
        "attestation": doc.model_dump(),
    }
