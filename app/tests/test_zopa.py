"""Tests for ZOPA (Zone of Possible Agreement) computation.

Verifies ZOPA existence checks, range calculations, input validation,
and privacy of internal fields.
Copied from enclave/tests with imports updated for engine.protocol.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.protocol.zopa import compute_zopa
from engine.protocol.schemas import PartyConfig, NegotiationRole


class TestZOPAExistence:
    """Test ZOPA existence checks."""

    def test_zopa_exists_when_seller_min_below_buyer_max(self, seller_config, buyer_config):
        """ZOPA exists when seller's minimum <= buyer's maximum."""
        result = compute_zopa(seller_config, buyer_config)
        assert result["zopa_exists"] is True

    def test_zopa_not_exists_when_seller_min_above_buyer_max(
        self, no_zopa_seller_config, buyer_config
    ):
        """ZOPA doesn't exist when seller's minimum > buyer's maximum."""
        result = compute_zopa(no_zopa_seller_config, buyer_config)
        assert result["zopa_exists"] is False

    def test_zopa_exists_at_boundary(self):
        """ZOPA exists when seller min exactly equals buyer max."""
        seller = PartyConfig(
            party_id="s", role=NegotiationRole.SELLER,
            budget_cap=100_000, reservation_price=120_000,
        )
        buyer = PartyConfig(
            party_id="b", role=NegotiationRole.BUYER,
            budget_cap=100_000, reservation_price=80_000,
        )
        result = compute_zopa(seller, buyer)
        assert result["zopa_exists"] is True

    def test_zopa_range_computed_correctly(self, seller_config, buyer_config):
        """Internal ZOPA range should be buyer_max - seller_min."""
        result = compute_zopa(seller_config, buyer_config)
        expected_range = buyer_config.budget_cap - seller_config.budget_cap
        assert result["_zopa_range"] == expected_range

    def test_zopa_range_zero_when_no_zopa(self, no_zopa_seller_config, buyer_config):
        """ZOPA range should be 0 when no ZOPA exists."""
        result = compute_zopa(no_zopa_seller_config, buyer_config)
        assert result["_zopa_range"] == 0.0


class TestZOPAValidation:
    """Test ZOPA input validation."""

    def test_wrong_seller_role_raises(self, buyer_config):
        """Passing buyer config as seller should raise ValueError."""
        with pytest.raises(ValueError, match="seller"):
            compute_zopa(buyer_config, buyer_config)

    def test_wrong_buyer_role_raises(self, seller_config):
        """Passing seller config as buyer should raise ValueError."""
        with pytest.raises(ValueError, match="buyer"):
            compute_zopa(seller_config, seller_config)


class TestZOPAPrivacy:
    """Test that ZOPA output doesn't leak confidential values externally."""

    def test_output_contains_zopa_exists_bool(self, seller_config, buyer_config):
        """Output must contain zopa_exists as boolean."""
        result = compute_zopa(seller_config, buyer_config)
        assert isinstance(result["zopa_exists"], bool)

    def test_internal_fields_prefixed(self, seller_config, buyer_config):
        """Internal fields should be prefixed with underscore."""
        result = compute_zopa(seller_config, buyer_config)
        internal_fields = [k for k in result if k.startswith("_")]
        assert len(internal_fields) > 0  # Has internal fields
        # These should never be sent outside the enclave
