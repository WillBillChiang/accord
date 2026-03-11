"""
Nitro Enclave attestation document generation and verification.

Generates attestation documents via the Nitro Security Module (NSM).
The attestation document contains PCR measurements that prove the exact
code running inside the enclave. Both negotiating parties verify this
before submitting their confidential data.
"""
import json
import logging
import hashlib
from typing import Optional

from protocol.schemas import AttestationDocument

logger = logging.getLogger(__name__)


def get_attestation_document(nonce: Optional[str] = None) -> AttestationDocument:
    """
    Get attestation document from Nitro Security Module.

    In production, this calls /dev/nsm to get a signed attestation
    document with PCR values. In development/testing, returns a
    mock attestation document.
    """
    try:
        # Production: read from Nitro Security Module
        return _get_nsm_attestation(nonce)
    except (FileNotFoundError, OSError):
        # Development/testing: return mock attestation
        logger.warning("NSM not available — returning mock attestation")
        return _get_mock_attestation(nonce)


def _get_nsm_attestation(nonce: Optional[str] = None) -> AttestationDocument:
    """
    Get real attestation from Nitro Security Module (/dev/nsm).

    The NSM provides:
    - PCR0: Hash of enclave image file
    - PCR1: Hash of Linux kernel and bootstrap
    - PCR2: Hash of application
    - Signed by AWS Nitro attestation PKI
    """
    try:
        # In production, use the nsm-lib or cbor2 to interact with /dev/nsm
        # This is a simplified implementation
        import cbor2

        with open('/dev/nsm', 'rb') as nsm:
            # Send attestation request
            request = cbor2.dumps({
                "module": "nsm",
                "function": "Attestation",
                "nonce": nonce.encode() if nonce else b'',
            })
            nsm.write(request)
            response_data = nsm.read()
            response = cbor2.loads(response_data)

        document = response.get("document", {})
        pcrs = document.get("pcrs", {})

        return AttestationDocument(
            pcr0=pcrs.get(0, "").hex() if isinstance(pcrs.get(0), bytes) else str(pcrs.get(0, "")),
            pcr1=pcrs.get(1, "").hex() if isinstance(pcrs.get(1), bytes) else str(pcrs.get(1, "")),
            pcr2=pcrs.get(2, "").hex() if isinstance(pcrs.get(2), bytes) else str(pcrs.get(2, "")),
            nonce=nonce,
        )
    except Exception as e:
        logger.error(f"Failed to get NSM attestation: {e}")
        raise


def _get_mock_attestation(nonce: Optional[str] = None) -> AttestationDocument:
    """Generate mock attestation for development/testing."""
    return AttestationDocument(
        pcr0=hashlib.sha384(b"mock-enclave-image").hexdigest(),
        pcr1=hashlib.sha384(b"mock-linux-kernel").hexdigest(),
        pcr2=hashlib.sha384(b"mock-application").hexdigest(),
        nonce=nonce,
    )


def verify_attestation(
    document: AttestationDocument,
    expected_pcr0: str,
    expected_pcr1: Optional[str] = None,
    expected_pcr2: Optional[str] = None,
) -> bool:
    """
    Verify attestation document PCR values match expected values.

    Both negotiating parties should call this to verify the enclave
    is running the exact published code before submitting data.
    """
    if document.pcr0 != expected_pcr0:
        logger.error(f"PCR0 mismatch: expected={expected_pcr0}, got={document.pcr0}")
        return False

    if expected_pcr1 and document.pcr1 != expected_pcr1:
        logger.error(f"PCR1 mismatch: expected={expected_pcr1}, got={document.pcr1}")
        return False

    if expected_pcr2 and document.pcr2 != expected_pcr2:
        logger.error(f"PCR2 mismatch: expected={expected_pcr2}, got={document.pcr2}")
        return False

    logger.info("Attestation verification passed")
    return True
