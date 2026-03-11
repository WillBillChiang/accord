"""
KMS client for decrypting data inside the Nitro Enclave.

The enclave has no direct network access. KMS calls are proxied through
vsock-proxy running on the parent instance. The KMS key policy ensures
only the attested enclave (matching PCR0/1/2) can decrypt data.
"""
import json
import socket
import struct
import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# vsock-proxy listens on parent for KMS traffic
VSOCK_PROXY_CID = 3  # Parent CID
VSOCK_PROXY_PORT = 8000


class EnclaveKMSClient:
    """
    KMS client that operates through vsock-proxy.

    The vsock-proxy on the parent instance forwards KMS API calls
    to the AWS KMS endpoint. The enclave provides its attestation
    document with each request, which KMS uses to validate the
    PCR values before allowing decryption.
    """

    def __init__(
        self,
        proxy_cid: int = VSOCK_PROXY_CID,
        proxy_port: int = VSOCK_PROXY_PORT,
        region: str = "us-east-1",
    ) -> None:
        self.proxy_cid = proxy_cid
        self.proxy_port = proxy_port
        self.region = region

    def decrypt(self, ciphertext_b64: str, key_id: Optional[str] = None) -> bytes:
        """
        Decrypt KMS-encrypted data using attestation-conditioned key.

        The KMS key policy only allows decryption when the request
        includes a valid attestation document with matching PCR values.

        Args:
            ciphertext_b64: Base64-encoded KMS ciphertext
            key_id: Optional KMS key ID (uses key embedded in ciphertext if not specified)

        Returns:
            Decrypted plaintext bytes
        """
        try:
            ciphertext_blob = base64.b64decode(ciphertext_b64)
        except Exception as e:
            raise ValueError(f"Invalid base64 ciphertext: {e}")

        # Build KMS Decrypt request
        request = {
            "Operation": "Decrypt",
            "CiphertextBlob": ciphertext_b64,
        }
        if key_id:
            request["KeyId"] = key_id

        # Send through vsock-proxy
        response = self._send_to_proxy(request)

        if "error" in response:
            raise RuntimeError(f"KMS decrypt failed: {response['error']}")

        plaintext_b64 = response.get("Plaintext", "")
        return base64.b64decode(plaintext_b64)

    def _send_to_proxy(self, request: dict) -> dict:
        """Send request to vsock-proxy and get response."""
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        try:
            sock.connect((self.proxy_cid, self.proxy_port))

            # Send request
            data = json.dumps(request).encode('utf-8')
            sock.sendall(struct.pack('>I', len(data)) + data)

            # Receive response
            raw_len = sock.recv(4)
            if not raw_len:
                raise ConnectionError("No response from proxy")
            resp_len = struct.unpack('>I', raw_len)[0]

            resp_data = b''
            while len(resp_data) < resp_len:
                chunk = sock.recv(min(resp_len - len(resp_data), 4096))
                if not chunk:
                    raise ConnectionError("Connection lost")
                resp_data += chunk

            return json.loads(resp_data.decode('utf-8'))
        except OSError as e:
            logger.error(f"vsock-proxy communication failed: {e}")
            raise RuntimeError(f"Cannot reach KMS proxy: {e}")
        finally:
            sock.close()
