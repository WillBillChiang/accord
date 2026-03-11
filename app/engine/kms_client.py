"""
Cloud KMS client for decrypting data inside the Confidential VM.

The Confidential VM calls Cloud KMS directly over HTTPS. The Cloud KMS
key's IAM policy restricts the decrypter role to the VM's service account,
which is bound to Confidential VM instances with the correct image.
"""
import base64
import logging
from typing import Optional

from google.cloud import kms

from config import KMS_KEY_NAME

logger = logging.getLogger(__name__)


class CloudKMSClient:
    """
    Cloud KMS client for attestation-conditioned decryption.

    The Cloud KMS key's IAM binding ensures only the Confidential VM's
    service account (attached to VMs with the correct image and SEV-SNP
    enabled) can perform decrypt operations.
    """

    def __init__(self, key_name: Optional[str] = None) -> None:
        self.key_name = key_name or KMS_KEY_NAME
        self._client = None

    @property
    def client(self) -> kms.KeyManagementServiceClient:
        if self._client is None:
            self._client = kms.KeyManagementServiceClient()
        return self._client

    def decrypt(self, ciphertext_b64: str) -> bytes:
        """
        Decrypt Cloud KMS-encrypted data.

        Args:
            ciphertext_b64: Base64-encoded KMS ciphertext

        Returns:
            Decrypted plaintext bytes
        """
        try:
            ciphertext = base64.b64decode(ciphertext_b64)
        except Exception as e:
            raise ValueError(f"Invalid base64 ciphertext: {e}")

        try:
            response = self.client.decrypt(
                request={
                    "name": self.key_name,
                    "ciphertext": ciphertext,
                }
            )
            return response.plaintext
        except Exception as e:
            logger.error(f"Cloud KMS decrypt failed: {e}")
            raise RuntimeError(f"KMS decrypt failed: {e}")

    def encrypt(self, plaintext: bytes) -> str:
        """
        Encrypt data with Cloud KMS.

        Args:
            plaintext: Data to encrypt

        Returns:
            Base64-encoded ciphertext
        """
        try:
            response = self.client.encrypt(
                request={
                    "name": self.key_name,
                    "plaintext": plaintext,
                }
            )
            return base64.b64encode(response.ciphertext).decode("utf-8")
        except Exception as e:
            logger.error(f"Cloud KMS encrypt failed: {e}")
            raise RuntimeError(f"KMS encrypt failed: {e}")
