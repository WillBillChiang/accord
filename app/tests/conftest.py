"""Shared test fixtures for Accord app tests.

Provides standard negotiation party configurations, proposals, and other
reusable fixtures used across the test suite. Updated for the GCP
Confidential VM architecture with engine.protocol.schemas imports.
"""
import sys
import os
import pytest

# Add app root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.protocol.schemas import (
    PartyConfig, DisclosureTier, NegotiationRole,
    Proposal, SessionConfig,
)


@pytest.fixture
def seller_config() -> PartyConfig:
    """Standard seller configuration for testing."""
    return PartyConfig(
        party_id="seller-001",
        role=NegotiationRole.SELLER,
        budget_cap=100_000,  # Min accept
        reservation_price=120_000,  # Walk-away (ideal)
        max_rounds=10,
        max_concession_per_round=0.15,
        disclosure_fields={
            "revenue": DisclosureTier.MUST_DISCLOSE,
            "customer_list": DisclosureTier.MAY_DISCLOSE,
            "trade_secrets": DisclosureTier.NEVER_DISCLOSE,
        },
        strategy_notes="Be firm on IP valuation",
        priority_issues=["IP protection", "Employee retention"],
        confidential_data={
            "revenue": "$5M ARR",
            "customer_list": "50 enterprise customers",
            "trade_secrets": "Proprietary algorithm X",
        },
    )


@pytest.fixture
def buyer_config() -> PartyConfig:
    """Standard buyer configuration for testing."""
    return PartyConfig(
        party_id="buyer-001",
        role=NegotiationRole.BUYER,
        budget_cap=200_000,  # Max payment
        reservation_price=150_000,  # Walk-away (ideal)
        max_rounds=10,
        max_concession_per_round=0.15,
        disclosure_fields={
            "proof_of_funds": DisclosureTier.MUST_DISCLOSE,
            "integration_plans": DisclosureTier.MAY_DISCLOSE,
            "other_targets": DisclosureTier.NEVER_DISCLOSE,
        },
        strategy_notes="Focus on synergies",
        priority_issues=["Quick close", "Team retention"],
        confidential_data={
            "proof_of_funds": "Bank statement verified",
            "integration_plans": "Merge with division B",
            "other_targets": "Company Y also in consideration",
        },
    )


@pytest.fixture
def sample_proposal() -> Proposal:
    """Sample proposal for testing."""
    return Proposal(
        round_number=1,
        from_party="seller-001",
        price=180_000,
        terms={"payment_structure": "50% upfront, 50% on close"},
        disclosed_fields={"revenue": "$5M ARR"},
        rationale="Opening offer based on market multiples",
    )


@pytest.fixture
def no_zopa_seller_config() -> PartyConfig:
    """Seller config where ZOPA doesn't exist (min > buyer max)."""
    return PartyConfig(
        party_id="seller-002",
        role=NegotiationRole.SELLER,
        budget_cap=300_000,  # Min accept is higher than buyer's max
        reservation_price=350_000,
        max_rounds=10,
        max_concession_per_round=0.15,
    )
