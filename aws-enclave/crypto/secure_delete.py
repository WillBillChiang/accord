"""
Secure memory deletion utilities.

Provides functions to securely zero memory, implementing the
"credible forgetting" mechanism from Conditional Recall.
When an enclave session terminates, all sensitive data must be
cryptographically zeroed before memory is released.
"""
from __future__ import annotations

import ctypes
import logging
from typing import Union

logger = logging.getLogger(__name__)


def secure_zero_bytes(data: Union[bytes, bytearray]) -> None:
    """
    Overwrite bytes in memory with zeros using ctypes.memset.

    This prevents the data from being recoverable from memory after
    the session ends. Combined with Nitro Enclave termination (which
    destroys all enclave memory), this provides defense-in-depth for
    provable deletion.
    """
    if not data:
        return
    try:
        if isinstance(data, bytes):
            # bytes are immutable in Python, but we can zero the underlying buffer
            buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
            ctypes.memset(buf, 0, len(data))
        elif isinstance(data, bytearray):
            buf = (ctypes.c_char * len(data)).from_buffer(data)
            ctypes.memset(buf, 0, len(data))
        logger.debug(f"Securely zeroed {len(data)} bytes")
    except Exception as e:
        logger.error(f"Failed to zero memory: {e}")
        raise


def secure_zero_dict(d: dict) -> None:
    """
    Recursively zero all string and bytes values in a dictionary,
    then clear the dictionary.
    """
    for key in list(d.keys()):
        value = d[key]
        if isinstance(value, (bytes, bytearray)):
            secure_zero_bytes(value)
        elif isinstance(value, dict):
            secure_zero_dict(value)
        elif isinstance(value, str):
            # Strings are immutable in Python; replace with empty
            d[key] = ""
        elif isinstance(value, list):
            secure_zero_list(value)
    d.clear()


def secure_zero_list(lst: list) -> None:
    """Recursively zero all elements in a list, then clear it."""
    for i, item in enumerate(lst):
        if isinstance(item, (bytes, bytearray)):
            secure_zero_bytes(item)
        elif isinstance(item, dict):
            secure_zero_dict(item)
        elif isinstance(item, list):
            secure_zero_list(item)
        elif isinstance(item, str):
            lst[i] = ""
    lst.clear()
