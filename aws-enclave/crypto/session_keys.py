"""
Ephemeral session key management.

Every negotiation session uses ephemeral keys generated inside the enclave.
Keys never leave the enclave boundary. When session ends, keys are
cryptographically zeroed implementing "credible forgetting" from
Conditional Recall (Schlegel & Sun, 2025).
"""
from __future__ import annotations

import os
import logging
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from crypto.secure_delete import secure_zero_bytes

logger = logging.getLogger(__name__)

KEY_SIZE = 32  # 256-bit AES key
NONCE_SIZE = 12  # 96-bit nonce for AES-GCM


class SessionKeyManager:
    """Manages ephemeral encryption keys for a negotiation session."""

    def __init__(self) -> None:
        self._key: bytes = os.urandom(KEY_SIZE)
        self._cipher: AESGCM = AESGCM(self._key)
        self._destroyed: bool = False
        logger.info("Session key generated")

    def encrypt(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Encrypt data with session key using AES-256-GCM.
        Returns nonce || ciphertext (nonce prepended).
        """
        if self._destroyed:
            raise RuntimeError("Session key has been destroyed")
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self._cipher.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    def decrypt(self, data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Decrypt data with session key.
        Expects nonce || ciphertext format.
        """
        if self._destroyed:
            raise RuntimeError("Session key has been destroyed")
        if len(data) < NONCE_SIZE:
            raise ValueError("Data too short to contain nonce")
        nonce = data[:NONCE_SIZE]
        ciphertext = data[NONCE_SIZE:]
        return self._cipher.decrypt(nonce, ciphertext, associated_data)

    def destroy(self) -> None:
        """
        Securely destroy the session key.
        Implements provable deletion from Conditional Recall.
        """
        if not self._destroyed:
            secure_zero_bytes(self._key)
            self._key = b'\x00' * KEY_SIZE
            self._cipher = None  # type: ignore
            self._destroyed = True
            logger.info("Session key securely destroyed")

    @property
    def is_destroyed(self) -> bool:
        return self._destroyed

    def __del__(self) -> None:
        """Ensure key is destroyed on garbage collection."""
        if not self._destroyed:
            self.destroy()
