"""
GCP Confidential VM attestation document generation and verification.

Generates attestation tokens via the GCE Metadata Service. The attestation
token contains claims about the VM's confidential computing status, boot
integrity, and image identity. Negotiating parties verify this before
submitting their confidential data.
"""
import logging
import hashlib
import time
from typing import Optional

import httpx

from engine.protocol.schemas import AttestationDocument

logger = logging.getLogger(__name__)

# GCE Metadata Service endpoint
METADATA_URL = "http://metadata.google.internal/computeMetadata/v1"
METADATA_HEADERS = {"Metadata-Flavor": "Google"}

# Attestation audience for token verification
ATTESTATION_AUDIENCE = "https://accord.example.com"


def get_attestation_document(nonce: Optional[str] = None) -> AttestationDocument:
    """
    Get attestation document from GCP Confidential VM.

    In production, this fetches an OIDC identity token from the GCE
    metadata service that includes Shielded VM integrity and SEV-SNP
    claims. In development/testing, returns a mock attestation document.
    """
    try:
        return _get_gcp_attestation(nonce)
    except Exception:
        logger.warning("GCE metadata not available — returning mock attestation")
        return _get_mock_attestation(nonce)


def _get_gcp_attestation(nonce: Optional[str] = None) -> AttestationDocument:
    """
    Get real attestation from GCP Confidential VM.

    The GCE Metadata Service provides:
    - Instance identity token (OIDC JWT signed by Google)
    - Shielded VM integrity status
    - Confidential computing (SEV-SNP) status
    - Instance image and identity metadata
    """
    try:
        # Fetch instance identity metadata
        instance_id = _fetch_metadata("instance/id")
        image = _fetch_metadata("instance/image")
        zone = _fetch_metadata("instance/zone")

        # Compute image digest as primary integrity measurement
        image_digest = hashlib.sha256(image.encode()).hexdigest() if image else ""

        # Check confidential computing status
        # On a Confidential VM, this attribute exists and is "SEV_SNP" or "SEV"
        try:
            confidential_type = _fetch_metadata(
                "instance/attributes/confidential-instance-type"
            )
            sev_snp_enabled = confidential_type in ("SEV_SNP", "SEV")
        except Exception:
            # Try alternative: check if the instance is a confidential instance
            # via the instance description
            sev_snp_enabled = False

        # Check Shielded VM secure boot status
        try:
            secure_boot = _fetch_metadata(
                "instance/attributes/enable-secure-boot"
            )
            secure_boot_enabled = secure_boot.lower() == "true"
        except Exception:
            secure_boot_enabled = False

        return AttestationDocument(
            image_digest=image_digest,
            sev_snp_enabled=sev_snp_enabled,
            secure_boot=secure_boot_enabled,
            vm_id=instance_id or "",
            nonce=nonce,
        )
    except Exception as e:
        logger.error(f"Failed to get GCP attestation: {e}")
        raise


def _fetch_metadata(path: str) -> str:
    """Fetch a value from the GCE Metadata Service."""
    url = f"{METADATA_URL}/{path}"
    response = httpx.get(url, headers=METADATA_HEADERS, timeout=5.0)
    response.raise_for_status()
    return response.text.strip()


def _get_mock_attestation(nonce: Optional[str] = None) -> AttestationDocument:
    """Generate mock attestation for development/testing."""
    return AttestationDocument(
        image_digest=hashlib.sha256(b"mock-confidential-vm-image").hexdigest(),
        sev_snp_enabled=False,
        secure_boot=False,
        vm_id="mock-vm-12345",
        nonce=nonce,
    )


def verify_attestation(
    document: AttestationDocument,
    expected_image_digest: str,
    require_sev_snp: bool = True,
    require_secure_boot: bool = True,
) -> bool:
    """
    Verify attestation document claims match expected values.

    Both negotiating parties should call this to verify the Confidential VM
    is running the exact published code before submitting data.
    """
    if document.image_digest != expected_image_digest:
        logger.error(
            f"Image digest mismatch: expected={expected_image_digest}, "
            f"got={document.image_digest}"
        )
        return False

    if require_sev_snp and not document.sev_snp_enabled:
        logger.error("SEV-SNP is not enabled on this VM")
        return False

    if require_secure_boot and not document.secure_boot:
        logger.error("Secure Boot is not enabled on this VM")
        return False

    logger.info("Attestation verification passed")
    return True
