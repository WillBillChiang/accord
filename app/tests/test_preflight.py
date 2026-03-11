"""Tests for preflight constraint enforcement.

Verifies NDAI Theorem 1 budget cap enforcement, concession rate
limiting, disclosure boundary enforcement, and round limit checks.
Copied from enclave/tests with imports updated for engine.agent
and engine.protocol.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.agent.preflight import preflight_check, PreflightViolation
from engine.protocol.schemas import (
    Proposal, PartyConfig, DisclosureTier, NegotiationRole,
)


class TestBudgetCap:
    """Test NDAI Theorem 1 budget cap enforcement."""

    def test_buyer_price_clamped_to_budget_cap(self, buyer_config):
        """Buyer price exceeding budget cap should be clamped, not rejected."""
        proposal = Proposal(
            round_number=1,
            from_party="buyer-001",
            price=250_000,  # Exceeds budget cap of 200_000
            terms={},
        )
        result = preflight_check(proposal, buyer_config, [])
        assert result.price == 200_000  # Clamped to budget cap

    def test_buyer_price_within_budget_passes(self, buyer_config):
        """Buyer price within budget cap should pass unchanged."""
        proposal = Proposal(
            round_number=1,
            from_party="buyer-001",
            price=150_000,
            terms={},
        )
        result = preflight_check(proposal, buyer_config, [])
        assert result.price == 150_000

    def test_seller_price_below_minimum_raises(self, seller_config):
        """Seller price below minimum should raise PreflightViolation."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=50_000,  # Below budget cap of 100_000
            terms={},
        )
        with pytest.raises(PreflightViolation) as exc_info:
            preflight_check(proposal, seller_config, [])
        assert exc_info.value.constraint == "BUDGET_CAP"

    def test_seller_price_at_minimum_passes(self, seller_config):
        """Seller price exactly at minimum should pass."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=100_000,
            terms={},
        )
        result = preflight_check(proposal, seller_config, [])
        assert result.price == 100_000

    def test_seller_price_above_minimum_passes(self, seller_config):
        """Seller price above minimum should pass."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=200_000,
            terms={},
        )
        result = preflight_check(proposal, seller_config, [])
        assert result.price == 200_000


class TestConcessionRate:
    """Test concession rate limiting."""

    def test_first_proposal_no_concession_check(self, seller_config):
        """First proposal has no previous to compare — should pass."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=180_000,
            terms={},
        )
        result = preflight_check(proposal, seller_config, [])
        assert result.price == 180_000

    def test_seller_excessive_concession_raises(self, seller_config):
        """Seller conceding more than max_concession_per_round should raise."""
        previous = Proposal(
            round_number=1,
            from_party="seller-001",
            price=200_000,
            terms={},
        )
        proposal = Proposal(
            round_number=2,
            from_party="seller-001",
            price=150_000,  # 25% concession, max is 15%
            terms={},
        )
        with pytest.raises(PreflightViolation) as exc_info:
            preflight_check(proposal, seller_config, [previous])
        assert exc_info.value.constraint == "CONCESSION_RATE"

    def test_seller_acceptable_concession_passes(self, seller_config):
        """Seller concession within limit should pass."""
        previous = Proposal(
            round_number=1,
            from_party="seller-001",
            price=200_000,
            terms={},
        )
        proposal = Proposal(
            round_number=2,
            from_party="seller-001",
            price=180_000,  # 10% concession, max is 15%
            terms={},
        )
        result = preflight_check(proposal, seller_config, [previous])
        assert result.price == 180_000

    def test_buyer_excessive_concession_raises(self, buyer_config):
        """Buyer conceding more than max should raise."""
        previous = Proposal(
            round_number=1,
            from_party="buyer-001",
            price=100_000,
            terms={},
        )
        proposal = Proposal(
            round_number=2,
            from_party="buyer-001",
            price=120_000,  # 20% concession, max is 15%
            terms={},
        )
        with pytest.raises(PreflightViolation) as exc_info:
            preflight_check(proposal, buyer_config, [previous])
        assert exc_info.value.constraint == "CONCESSION_RATE"

    def test_concession_only_compares_own_proposals(self, seller_config):
        """Concession rate should only compare against own previous proposals."""
        opponent_proposal = Proposal(
            round_number=1,
            from_party="buyer-001",  # Opponent
            price=100_000,
            terms={},
        )
        own_proposal = Proposal(
            round_number=2,
            from_party="seller-001",
            price=180_000,
            terms={},
        )
        # Should compare against no previous own proposals, so no concession check
        result = preflight_check(own_proposal, seller_config, [opponent_proposal])
        assert result.price == 180_000


class TestDisclosureBoundaries:
    """Test disclosure boundary enforcement."""

    def test_never_disclose_field_raises(self, seller_config):
        """Attempting to disclose a NEVER_DISCLOSE field should raise."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=180_000,
            terms={},
            disclosed_fields={"trade_secrets": "Our secret algorithm"},
        )
        with pytest.raises(PreflightViolation) as exc_info:
            preflight_check(proposal, seller_config, [])
        assert exc_info.value.constraint == "DISCLOSURE_BOUNDARY"

    def test_must_disclose_field_passes(self, seller_config):
        """Disclosing a MUST_DISCLOSE field should pass."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=180_000,
            terms={},
            disclosed_fields={"revenue": "$5M ARR"},
        )
        result = preflight_check(proposal, seller_config, [])
        assert "revenue" in result.disclosed_fields

    def test_may_disclose_field_passes(self, seller_config):
        """Disclosing a MAY_DISCLOSE field should pass."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=180_000,
            terms={},
            disclosed_fields={"customer_list": "50 enterprise"},
        )
        result = preflight_check(proposal, seller_config, [])
        assert "customer_list" in result.disclosed_fields

    def test_unknown_field_passes(self, seller_config):
        """Fields not in disclosure policy should pass."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=180_000,
            terms={},
            disclosed_fields={"team_size": "50 engineers"},
        )
        result = preflight_check(proposal, seller_config, [])
        assert "team_size" in result.disclosed_fields


class TestRoundLimit:
    """Test round limit enforcement."""

    def test_within_round_limit_passes(self, seller_config):
        """Proposal within round limit should pass."""
        proposal = Proposal(
            round_number=5,
            from_party="seller-001",
            price=180_000,
            terms={},
        )
        result = preflight_check(proposal, seller_config, [])
        assert result.round_number == 5

    def test_exceeding_round_limit_raises(self, seller_config):
        """Proposal exceeding round limit should raise."""
        proposal = Proposal(
            round_number=11,  # Max is 10
            from_party="seller-001",
            price=180_000,
            terms={},
        )
        with pytest.raises(PreflightViolation) as exc_info:
            preflight_check(proposal, seller_config, [])
        assert exc_info.value.constraint == "ROUND_LIMIT"

    def test_at_round_limit_passes(self, seller_config):
        """Proposal exactly at round limit should pass."""
        proposal = Proposal(
            round_number=10,
            from_party="seller-001",
            price=180_000,
            terms={},
        )
        result = preflight_check(proposal, seller_config, [])
        assert result.round_number == 10


class TestPreflightViolation:
    """Test PreflightViolation exception."""

    def test_violation_has_constraint_and_message(self):
        """PreflightViolation should contain constraint type and message."""
        violation = PreflightViolation("BUDGET_CAP", "Price too low")
        assert violation.constraint == "BUDGET_CAP"
        assert violation.message == "Price too low"
        assert "BUDGET_CAP" in str(violation)
        assert "Price too low" in str(violation)
