"""Tests for Nash Bargaining Solution computation.

Verifies the Nash Bargaining Solution price calculation from
NDAI Eq. (4)-(5), including symmetric/asymmetric bargaining,
payoff sums, clamping to reservation prices, and input validation.
Copied from enclave/tests with imports updated for engine.protocol.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.protocol.nash_bargaining import (
    nash_bargaining_price,
    compute_outside_option_fraction,
)


class TestNashBargainingPrice:
    """Test Nash Bargaining Solution from NDAI Eq. (4)-(5)."""

    def test_symmetric_bargaining(self):
        """With no outside option (alpha_0=0), price should be omega/2."""
        result = nash_bargaining_price(omega=100_000, alpha_0=0.0)
        assert result["price"] == 50_000.0
        assert result["theta"] == 0.5
        assert result["seller_share"] == 0.5
        assert result["buyer_share"] == 0.5

    def test_full_outside_option(self):
        """With alpha_0=1, price should equal omega (seller takes all)."""
        result = nash_bargaining_price(omega=100_000, alpha_0=1.0)
        assert result["price"] == 100_000.0
        assert result["theta"] == 1.0

    def test_partial_outside_option(self):
        """With alpha_0=0.6, theta should be 0.8, price = 0.8 * omega."""
        result = nash_bargaining_price(omega=100_000, alpha_0=0.6)
        assert result["theta"] == 0.8
        assert result["price"] == 80_000.0

    def test_payoffs_sum_to_omega(self):
        """Seller and buyer payoffs should sum to omega."""
        result = nash_bargaining_price(omega=200_000, alpha_0=0.3)
        total = result["seller_payoff"] + result["buyer_payoff"]
        assert abs(total - 200_000) < 0.01

    def test_shares_sum_to_one(self):
        """Seller and buyer shares should sum to 1."""
        result = nash_bargaining_price(omega=150_000, alpha_0=0.4)
        total = result["seller_share"] + result["buyer_share"]
        assert abs(total - 1.0) < 0.001

    def test_clamp_to_seller_reservation(self):
        """Price should not go below seller's reservation price."""
        result = nash_bargaining_price(
            omega=100_000, alpha_0=0.0,
            seller_reservation=60_000,
        )
        assert result["price"] >= 60_000

    def test_clamp_to_buyer_reservation(self):
        """Price should not exceed buyer's reservation price."""
        result = nash_bargaining_price(
            omega=100_000, alpha_0=0.8,
            buyer_reservation=80_000,
        )
        assert result["price"] <= 80_000


class TestNashBargainingValidation:
    """Test input validation."""

    def test_negative_omega_raises(self):
        """Negative deal value should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            nash_bargaining_price(omega=-100, alpha_0=0.5)

    def test_zero_omega_raises(self):
        """Zero deal value should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            nash_bargaining_price(omega=0, alpha_0=0.5)

    def test_alpha_below_zero_raises(self):
        """Alpha_0 below 0 should raise ValueError."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            nash_bargaining_price(omega=100_000, alpha_0=-0.1)

    def test_alpha_above_one_raises(self):
        """Alpha_0 above 1 should raise ValueError."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            nash_bargaining_price(omega=100_000, alpha_0=1.1)


class TestOutsideOptionFraction:
    """Test outside option fraction computation."""

    def test_basic_computation(self):
        """alpha_0 = seller_min / omega."""
        result = compute_outside_option_fraction(60_000, 100_000)
        assert abs(result - 0.6) < 0.001

    def test_clamped_to_max_one(self):
        """Should clamp to 1.0 if seller_min > omega."""
        result = compute_outside_option_fraction(150_000, 100_000)
        assert result == 1.0

    def test_clamped_to_min_zero(self):
        """Should clamp to 0.0 if seller_min is 0."""
        result = compute_outside_option_fraction(0, 100_000)
        assert result == 0.0

    def test_zero_deal_value_raises(self):
        """Zero deal value should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            compute_outside_option_fraction(50_000, 0)
