"""Tests for Cloud KMS client encryption and decryption.

Verifies that the CloudKMSClient correctly calls Cloud KMS for
encrypt/decrypt operations, handles base64 encoding/decoding,
and raises appropriate errors on failure.
"""
import pytest
import sys
import os
import base64
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock google.cloud.kms before importing
mock_kms_module = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.kms'] = mock_kms_module
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.api_core'] = MagicMock()
sys.modules['google.api_core.exceptions'] = MagicMock()

from engine.kms_client import CloudKMSClient


class TestCloudKMSClientCreation:
    """Test CloudKMSClient instantiation."""

    def test_client_creation_with_default_key(self):
        """CloudKMSClient should instantiate with the default KMS key."""
        client = CloudKMSClient()
        assert client is not None
        assert client.key_name is not None

    def test_client_creation_with_custom_key(self):
        """CloudKMSClient should accept a custom key name."""
        custom_key = "projects/my-project/locations/us/keyRings/ring/cryptoKeys/key"
        client = CloudKMSClient(key_name=custom_key)
        assert client.key_name == custom_key

    def test_client_lazy_init(self):
        """KMS client should not be created until first use."""
        client = CloudKMSClient()
        assert client._client is None


class TestDecrypt:
    """Test Cloud KMS decryption."""

    def test_decrypt_valid_base64_calls_kms(self):
        """Decrypt with valid base64 should call KMS client.decrypt."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()

        plaintext = b"secret negotiation data"
        mock_kms_client.decrypt.return_value = MagicMock(plaintext=plaintext)
        client._client = mock_kms_client

        ciphertext_b64 = base64.b64encode(b"encrypted-data").decode("utf-8")
        result = client.decrypt(ciphertext_b64)

        assert result == plaintext
        mock_kms_client.decrypt.assert_called_once()
        call_kwargs = mock_kms_client.decrypt.call_args[1]
        assert call_kwargs["request"]["name"] == "test-key"
        assert call_kwargs["request"]["ciphertext"] == base64.b64decode(ciphertext_b64)

    def test_decrypt_invalid_base64_raises_value_error(self):
        """Decrypt with invalid base64 should raise ValueError."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()
        client._client = mock_kms_client

        with pytest.raises(ValueError, match="Invalid base64"):
            client.decrypt("not-valid-base64!!!")

    def test_decrypt_kms_error_raises_runtime_error(self):
        """Decrypt with KMS API error should raise RuntimeError."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()
        mock_kms_client.decrypt.side_effect = Exception("Permission denied")
        client._client = mock_kms_client

        ciphertext_b64 = base64.b64encode(b"encrypted-data").decode("utf-8")

        with pytest.raises(RuntimeError, match="KMS decrypt failed"):
            client.decrypt(ciphertext_b64)

    def test_decrypt_returns_bytes(self):
        """Decrypted result should be bytes."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()
        mock_kms_client.decrypt.return_value = MagicMock(plaintext=b"data")
        client._client = mock_kms_client

        ciphertext_b64 = base64.b64encode(b"something").decode("utf-8")
        result = client.decrypt(ciphertext_b64)

        assert isinstance(result, bytes)


class TestEncrypt:
    """Test Cloud KMS encryption."""

    def test_encrypt_calls_kms_and_returns_base64(self):
        """Encrypt should call KMS client.encrypt and return base64 string."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()

        encrypted_bytes = b"kms-encrypted-ciphertext"
        mock_kms_client.encrypt.return_value = MagicMock(
            ciphertext=encrypted_bytes
        )
        client._client = mock_kms_client

        plaintext = b"secret data to encrypt"
        result = client.encrypt(plaintext)

        # Result should be base64 encoded
        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded == encrypted_bytes

        mock_kms_client.encrypt.assert_called_once()
        call_kwargs = mock_kms_client.encrypt.call_args[1]
        assert call_kwargs["request"]["name"] == "test-key"
        assert call_kwargs["request"]["plaintext"] == plaintext

    def test_encrypt_kms_error_raises_runtime_error(self):
        """Encrypt with KMS API error should raise RuntimeError."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()
        mock_kms_client.encrypt.side_effect = Exception("Quota exceeded")
        client._client = mock_kms_client

        with pytest.raises(RuntimeError, match="KMS encrypt failed"):
            client.encrypt(b"test data")

    def test_encrypt_empty_plaintext(self):
        """Encrypt should handle empty plaintext bytes."""
        client = CloudKMSClient(key_name="test-key")
        mock_kms_client = MagicMock()
        mock_kms_client.encrypt.return_value = MagicMock(ciphertext=b"enc")
        client._client = mock_kms_client

        result = client.encrypt(b"")
        assert isinstance(result, str)
        mock_kms_client.encrypt.assert_called_once()


class TestRoundTrip:
    """Test encrypt-then-decrypt round-trip logic."""

    def test_encrypt_decrypt_key_consistency(self):
        """Both encrypt and decrypt should use the same KMS key name."""
        key_name = "projects/p/locations/l/keyRings/r/cryptoKeys/k"
        client = CloudKMSClient(key_name=key_name)
        mock_kms_client = MagicMock()
        mock_kms_client.encrypt.return_value = MagicMock(ciphertext=b"enc")
        mock_kms_client.decrypt.return_value = MagicMock(plaintext=b"dec")
        client._client = mock_kms_client

        client.encrypt(b"test")
        encrypt_key = mock_kms_client.encrypt.call_args[1]["request"]["name"]

        ciphertext_b64 = base64.b64encode(b"enc").decode()
        client.decrypt(ciphertext_b64)
        decrypt_key = mock_kms_client.decrypt.call_args[1]["request"]["name"]

        assert encrypt_key == decrypt_key == key_name
