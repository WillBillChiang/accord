"""
Message padding for traffic analysis resistance.

All vsock messages are padded to a fixed size to prevent traffic analysis.
An observer monitoring vsock message sizes cannot infer negotiation progress
or content from message length patterns.
"""
import os
import struct
import logging

logger = logging.getLogger(__name__)

PADDED_SIZE = 65536  # 64KB fixed message size
LENGTH_PREFIX_SIZE = 4  # 4 bytes for uint32 length
MAX_PAYLOAD_SIZE = PADDED_SIZE - LENGTH_PREFIX_SIZE


def pad_message(data: bytes) -> bytes:
    """
    Pad message to fixed 64KB size.
    Format: [4-byte length][payload][random padding]
    """
    if len(data) > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Message size {len(data)} exceeds maximum payload "
            f"size {MAX_PAYLOAD_SIZE}"
        )
    length_prefix = struct.pack('>I', len(data))
    padding_size = MAX_PAYLOAD_SIZE - len(data)
    padding = os.urandom(padding_size)
    return length_prefix + data + padding


def unpad_message(padded: bytes) -> bytes:
    """
    Remove padding and extract original message.
    """
    if len(padded) < LENGTH_PREFIX_SIZE:
        raise ValueError("Padded message too short")
    if len(padded) != PADDED_SIZE:
        raise ValueError(
            f"Expected padded size {PADDED_SIZE}, got {len(padded)}"
        )
    actual_len = struct.unpack('>I', padded[:LENGTH_PREFIX_SIZE])[0]
    if actual_len > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Declared length {actual_len} exceeds maximum {MAX_PAYLOAD_SIZE}"
        )
    return padded[LENGTH_PREFIX_SIZE:LENGTH_PREFIX_SIZE + actual_len]
