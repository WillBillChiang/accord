"""Tests for message padding (traffic analysis resistance)."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from crypto.padding import pad_message, unpad_message, PADDED_SIZE, MAX_PAYLOAD_SIZE


class TestPadding:
    """Test message padding and unpadding."""

    def test_pad_produces_fixed_size(self):
        """Padded message should always be exactly PADDED_SIZE bytes."""
        msg = b"Hello, world!"
        padded = pad_message(msg)
        assert len(padded) == PADDED_SIZE

    def test_roundtrip_preserves_message(self):
        """Padding then unpadding should return original message."""
        original = b'{"action": "test", "data": "confidential"}'
        padded = pad_message(original)
        recovered = unpad_message(padded)
        assert recovered == original

    def test_different_messages_same_padded_size(self):
        """Different messages should produce same padded size."""
        short_msg = b"hi"
        long_msg = b"x" * 1000
        assert len(pad_message(short_msg)) == len(pad_message(long_msg))

    def test_empty_message(self):
        """Empty message should pad and unpad correctly."""
        padded = pad_message(b"")
        assert len(padded) == PADDED_SIZE
        recovered = unpad_message(padded)
        assert recovered == b""

    def test_max_size_message(self):
        """Maximum size message should pad correctly."""
        msg = b"x" * MAX_PAYLOAD_SIZE
        padded = pad_message(msg)
        assert len(padded) == PADDED_SIZE
        recovered = unpad_message(padded)
        assert recovered == msg

    def test_oversized_message_raises(self):
        """Message exceeding max payload size should raise."""
        msg = b"x" * (MAX_PAYLOAD_SIZE + 1)
        with pytest.raises(ValueError, match="exceeds maximum"):
            pad_message(msg)

    def test_padding_is_random(self):
        """Padding bytes should be different each time."""
        msg = b"test"
        padded1 = pad_message(msg)
        padded2 = pad_message(msg)
        # The padding portion should differ (extremely unlikely to be same)
        assert padded1 != padded2  # Random padding makes them different

    def test_unpad_too_short_raises(self):
        """Unpadding a message shorter than length prefix should raise."""
        with pytest.raises(ValueError, match="too short"):
            unpad_message(b"ab")

    def test_unpad_wrong_size_raises(self):
        """Unpadding a message not of PADDED_SIZE should raise."""
        with pytest.raises(ValueError, match="Expected padded size"):
            unpad_message(b"x" * 100)

    def test_unpad_corrupted_length_raises(self):
        """Corrupted length prefix should raise."""
        # Create padded data with impossibly large length
        import struct
        corrupted = struct.pack('>I', MAX_PAYLOAD_SIZE + 100) + b'\x00' * (PADDED_SIZE - 4)
        with pytest.raises(ValueError, match="exceeds maximum"):
            unpad_message(corrupted)
