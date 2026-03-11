"""
Vsock communication layer for Nitro Enclave.

Nitro Enclaves have NO network access. All communication flows through
vsock (AF_VSOCK), a local socket between enclave and parent EC2 instance.
This module handles the vsock server inside the enclave.
"""
import socket
import struct
import json
import logging
from typing import Optional

from crypto.padding import pad_message, unpad_message

logger = logging.getLogger(__name__)

VSOCK_PORT = 5000
RECV_BUFFER_SIZE = 4096
MSG_LENGTH_SIZE = 4  # 4 bytes for uint32 length prefix


class VsockServer:
    """
    Vsock server running inside the Nitro Enclave.
    Handles length-prefixed JSON messages with fixed-size padding.
    """

    def __init__(self, port: int = VSOCK_PORT) -> None:
        self.port = port
        self.sock: Optional[socket.socket] = None

    def start(self) -> None:
        """Bind and listen on vsock."""
        self.sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((socket.VMADDR_CID_ANY, self.port))
        self.sock.listen(5)
        logger.info(f"Vsock server listening on port {self.port}")

    def accept(self) -> socket.socket:
        """Accept incoming connection."""
        if self.sock is None:
            raise RuntimeError("Server not started")
        conn, addr = self.sock.accept()
        logger.debug(f"Connection accepted from CID={addr[0]}, port={addr[1]}")
        return conn

    @staticmethod
    def recv_message(conn: socket.socket) -> Optional[dict]:
        """
        Receive a padded, length-prefixed JSON message.
        Returns parsed dict or None if connection closed.
        """
        try:
            # Read the padded message (fixed 64KB)
            padded_data = _recv_exact(conn, 65536)  # PADDED_SIZE
            if padded_data is None:
                return None

            # Unpad to get actual message
            raw_data = unpad_message(padded_data)
            return json.loads(raw_data.decode('utf-8'))
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse message: {e}")
            return None
        except ConnectionError:
            logger.warning("Connection lost during receive")
            return None

    @staticmethod
    def send_message(conn: socket.socket, msg: dict) -> None:
        """
        Send a padded, length-prefixed JSON message.
        All messages padded to fixed 64KB to resist traffic analysis.
        """
        try:
            raw_data = json.dumps(msg).encode('utf-8')
            padded_data = pad_message(raw_data)
            conn.sendall(padded_data)
        except (ConnectionError, BrokenPipeError) as e:
            logger.error(f"Failed to send message: {e}")
            raise

    def shutdown(self) -> None:
        """Close the server socket."""
        if self.sock:
            self.sock.close()
            self.sock = None
            logger.info("Vsock server shut down")


def _recv_exact(conn: socket.socket, size: int) -> Optional[bytes]:
    """Receive exactly `size` bytes from socket."""
    data = b''
    while len(data) < size:
        chunk = conn.recv(min(size - len(data), RECV_BUFFER_SIZE))
        if not chunk:
            return None
        data += chunk
    return data
