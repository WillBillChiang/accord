"""Tests for GCP Confidential VM attestation generation and verification.

Verifies that attestation documents are correctly generated from
GCE metadata service calls, that mock attestation is returned when
metadata is unavailable, and that verification checks work for
image digest, SEV-SNP, and Secure Boot claims.
"""
import pytest
import sys
import os
import hashlib
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock google.cloud modules
sys.modules.setdefault('google.cloud', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.kms', MagicMock())
sys.modules.setdefault('google.api_core', MagicMock())
sys.modules.setdefault('google.api_core.exceptions', MagicMock())

from engine.attestation import (
    get_attestation_document,
    verify_attestation,
    _get_mock_attestation,
    _get_gcp_attestation,
)
from engine.protocol.schemas import AttestationDocument


class TestGetAttestationDocument:
    """Test attestation document generation."""

    @patch('engine.attestation._get_gcp_attestation')
    def test_returns_attestation_document(self, mock_gcp_attest):
        """get_attestation_document should return an AttestationDocument."""
        expected_doc = AttestationDocument(
            image_digest="abc123digest",
            sev_snp_enabled=True,
            secure_boot=True,
            vm_id="test-vm-1",
            nonce="test-nonce",
        )
        mock_gcp_attest.return_value = expected_doc

        result = get_attestation_document(nonce="test-nonce")
        assert isinstance(result, AttestationDocument)
        assert result.image_digest == "abc123digest"
        assert result.sev_snp_enabled is True
        assert result.secure_boot is True
        assert result.vm_id == "test-vm-1"
        assert result.nonce == "test-nonce"

    @patch('engine.attestation._get_gcp_attestation')
    def test_returns_mock_when_metadata_unavailable(self, mock_gcp_attest):
        """Should return mock attestation when GCE metadata is not available."""
        mock_gcp_attest.side_effect = Exception("metadata not available")

        result = get_attestation_document(nonce="fallback-nonce")
        assert isinstance(result, AttestationDocument)
        assert result.sev_snp_enabled is False
        assert result.secure_boot is False
        assert result.vm_id == "mock-vm-12345"
        assert result.nonce == "fallback-nonce"

    @patch('engine.attestation._fetch_metadata')
    def test_gcp_attestation_correct_fields(self, mock_fetch):
        """GCP attestation should populate all fields from metadata."""
        def side_effect(path):
            responses = {
                "instance/id": "12345678",
                "instance/image": "projects/accord/images/confidential-v2",
                "instance/zone": "us-central1-a",
                "instance/attributes/confidential-instance-type": "SEV_SNP",
                "instance/attributes/enable-secure-boot": "true",
            }
            if path in responses:
                return responses[path]
            raise Exception(f"unknown path: {path}")

        mock_fetch.side_effect = side_effect

        result = _get_gcp_attestation(nonce="gcp-nonce")
        assert isinstance(result, AttestationDocument)
        expected_digest = hashlib.sha256(
            b"projects/accord/images/confidential-v2"
        ).hexdigest()
        assert result.image_digest == expected_digest
        assert result.sev_snp_enabled is True
        assert result.secure_boot is True
        assert result.vm_id == "12345678"
        assert result.nonce == "gcp-nonce"

    @patch('engine.attestation._fetch_metadata')
    def test_gcp_attestation_sev_only(self, mock_fetch):
        """SEV (non-SNP) should also set sev_snp_enabled to True."""
        def side_effect(path):
            responses = {
                "instance/id": "99999",
                "instance/image": "test-image",
                "instance/zone": "us-east1-b",
                "instance/attributes/confidential-instance-type": "SEV",
                "instance/attributes/enable-secure-boot": "false",
            }
            if path in responses:
                return responses[path]
            raise Exception(f"unknown path: {path}")

        mock_fetch.side_effect = side_effect

        result = _get_gcp_attestation()
        assert result.sev_snp_enabled is True
        assert result.secure_boot is False


class TestMockAttestation:
    """Test mock attestation document generation."""

    def test_mock_attestation_has_expected_fields(self):
        """Mock attestation should have all required fields."""
        result = _get_mock_attestation(nonce="mock-nonce")
        assert isinstance(result, AttestationDocument)
        assert result.image_digest != ""
        assert result.sev_snp_enabled is False
        assert result.secure_boot is False
        assert result.vm_id == "mock-vm-12345"
        assert result.nonce == "mock-nonce"

    def test_mock_attestation_uses_deterministic_digest(self):
        """Mock attestation should use a deterministic image digest."""
        expected = hashlib.sha256(b"mock-confidential-vm-image").hexdigest()
        result = _get_mock_attestation()
        assert result.image_digest == expected


class TestVerifyAttestation:
    """Test attestation verification."""

    def test_verify_passes_with_matching_digest(self):
        """Verification should pass when image digest matches."""
        digest = hashlib.sha256(b"test-image").hexdigest()
        doc = AttestationDocument(
            image_digest=digest,
            sev_snp_enabled=True,
            secure_boot=True,
            vm_id="vm-1",
        )
        assert verify_attestation(doc, expected_image_digest=digest) is True

    def test_verify_fails_on_digest_mismatch(self):
        """Verification should fail when image digest does not match."""
        doc = AttestationDocument(
            image_digest="actual-digest",
            sev_snp_enabled=True,
            secure_boot=True,
            vm_id="vm-1",
        )
        assert verify_attestation(doc, expected_image_digest="wrong-digest") is False

    def test_verify_fails_when_sev_snp_required_but_disabled(self):
        """Verification should fail when SEV-SNP is required but not enabled."""
        digest = "matching-digest"
        doc = AttestationDocument(
            image_digest=digest,
            sev_snp_enabled=False,
            secure_boot=True,
            vm_id="vm-1",
        )
        result = verify_attestation(
            doc,
            expected_image_digest=digest,
            require_sev_snp=True,
        )
        assert result is False

    def test_verify_passes_when_sev_snp_not_required(self):
        """Verification should pass when SEV-SNP is not required."""
        digest = "matching-digest"
        doc = AttestationDocument(
            image_digest=digest,
            sev_snp_enabled=False,
            secure_boot=True,
            vm_id="vm-1",
        )
        result = verify_attestation(
            doc,
            expected_image_digest=digest,
            require_sev_snp=False,
        )
        assert result is True

    def test_verify_fails_when_secure_boot_required_but_disabled(self):
        """Verification should fail when Secure Boot required but not enabled."""
        digest = "matching-digest"
        doc = AttestationDocument(
            image_digest=digest,
            sev_snp_enabled=True,
            secure_boot=False,
            vm_id="vm-1",
        )
        result = verify_attestation(
            doc,
            expected_image_digest=digest,
            require_sev_snp=True,
            require_secure_boot=True,
        )
        assert result is False

    def test_verify_passes_when_secure_boot_not_required(self):
        """Verification should pass when Secure Boot is not required."""
        digest = "matching-digest"
        doc = AttestationDocument(
            image_digest=digest,
            sev_snp_enabled=True,
            secure_boot=False,
            vm_id="vm-1",
        )
        result = verify_attestation(
            doc,
            expected_image_digest=digest,
            require_sev_snp=False,
            require_secure_boot=False,
        )
        assert result is True

    def test_verify_fails_all_checks(self):
        """Verification should fail when digest mismatches (first check)."""
        doc = AttestationDocument(
            image_digest="wrong",
            sev_snp_enabled=False,
            secure_boot=False,
            vm_id="vm-1",
        )
        result = verify_attestation(
            doc,
            expected_image_digest="expected",
            require_sev_snp=True,
            require_secure_boot=True,
        )
        assert result is False
