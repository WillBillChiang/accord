"""
Vsock client for communicating with the Nitro Enclave.

The parent EC2 instance communicates with the enclave exclusively
through vsock. This client sends commands and receives responses
using length-prefixed JSON messages with fixed-size padding.
"""
import socket
import struct
import json
import os
import logging
from typing import Optional

logger = logging.getLogger("accord.parent.vsock")

ENCLAVE_CID = int(os.environ.get("ENCLAVE_CID", "16"))
ENCLAVE_PORT = int(os.environ.get("ENCLAVE_PORT", "5000"))
PADDED_SIZE = 65536  # Must match enclave padding size
RECV_BUFFER_SIZE = 4096


class VsockClient:
    """Client for sending messages to the Nitro Enclave via vsock."""

    def __init__(
        self,
        enclave_cid: int = ENCLAVE_CID,
        enclave_port: int = ENCLAVE_PORT,
    ) -> None:
        self.enclave_cid = enclave_cid
        self.enclave_port = enclave_port

    def send_command(self, message: dict, timeout: float = 120.0) -> dict:
        """
        Send a command to the enclave and wait for response.

        Uses fixed-size padding on both send and receive to prevent
        traffic analysis.
        """
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((self.enclave_cid, self.enclave_port))

            # Pad and send
            raw = json.dumps(message).encode('utf-8')
            padded = self._pad(raw)
            sock.sendall(padded)

            # Receive padded response
            resp_padded = self._recv_exact(sock, PADDED_SIZE)
            if resp_padded is None:
                raise ConnectionError("No response from enclave")

            resp_raw = self._unpad(resp_padded)
            return json.loads(resp_raw.decode('utf-8'))
        except socket.timeout:
            logger.error("Enclave communication timeout")
            raise RuntimeError("Enclave request timed out")
        except OSError as e:
            logger.error(f"Vsock communication error: {e}")
            raise RuntimeError(f"Cannot communicate with enclave: {e}")
        finally:
            sock.close()

    def _pad(self, data: bytes) -> bytes:
        """Pad message to fixed size."""
        if len(data) > PADDED_SIZE - 4:
            raise ValueError("Message too large")
        length_prefix = struct.pack('>I', len(data))
        padding = os.urandom(PADDED_SIZE - 4 - len(data))
        return length_prefix + data + padding

    def _unpad(self, padded: bytes) -> bytes:
        """Remove padding from message."""
        actual_len = struct.unpack('>I', padded[:4])[0]
        return padded[4:4 + actual_len]

    def _recv_exact(self, sock: socket.socket, size: int) -> Optional[bytes]:
        """Receive exactly `size` bytes."""
        data = b''
        while len(data) < size:
            chunk = sock.recv(min(size - len(data), RECV_BUFFER_SIZE))
            if not chunk:
                return None
            data += chunk
        return data


# Singleton for use across routes
_client: Optional[VsockClient] = None


def get_vsock_client() -> VsockClient:
    """Get or create the vsock client singleton."""
    global _client
    if _client is None:
        _client = VsockClient()
    return _client
