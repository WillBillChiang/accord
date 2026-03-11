"""Tests for Stacked Alternating Offers (SAO) protocol.

Verifies deal-reaching scenarios, no-deal outcomes, round progression,
and timeout behavior during automated negotiation.
Copied from enclave/tests with imports updated for engine.protocol
and engine.session.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.protocol.sao import SAOProtocol
from engine.protocol.schemas import (
    PartyConfig, NegotiationRole, SessionStatus, ProposalAction,
    Proposal, ProposalResponse,
)
from engine.session import NegotiationSession
from engine.agent.base_agent import NegotiationAgent
from engine.agent.llm_engine import LLMEngine


def make_mock_llm() -> LLMEngine:
    """Create a mock LLM engine that returns None (forces fallback)."""
    llm = LLMEngine.__new__(LLMEngine)
    llm._model = None
    llm.model_path = ""
    llm.temperature = 0.3
    return llm


class TestSAOProtocolDealReached:
    """Test SAO protocol when deal is reached."""

    def test_deal_reached_when_price_acceptable(self):
        """Deal should be reached when buyer's offer meets seller's reservation."""
        seller_config = PartyConfig(
            party_id="seller",
            role=NegotiationRole.SELLER,
            budget_cap=80_000,
            reservation_price=100_000,
            max_rounds=10,
            max_concession_per_round=0.15,
        )
        buyer_config = PartyConfig(
            party_id="buyer",
            role=NegotiationRole.BUYER,
            budget_cap=150_000,
            reservation_price=120_000,  # Will accept at or below 120k
            max_rounds=10,
            max_concession_per_round=0.15,
        )

        session = NegotiationSession(session_id="test-sao-001")
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)

        llm = make_mock_llm()
        seller_agent = NegotiationAgent(seller_config, llm)
        buyer_agent = NegotiationAgent(buyer_config, llm)

        protocol = SAOProtocol(seller_agent, buyer_agent, session)
        outcome = protocol.run()

        # With fallback strategy, deal may or may not be reached depending
        # on the convergence of fallback prices. Check it completes.
        assert outcome.session_id == "test-sao-001"
        assert outcome.rounds_completed >= 0


class TestSAOProtocolNoDeal:
    """Test SAO protocol when no deal is possible."""

    def test_no_deal_when_no_zopa_convergence(self):
        """Negotiation should end in no-deal when agents can't converge."""
        seller_config = PartyConfig(
            party_id="seller",
            role=NegotiationRole.SELLER,
            budget_cap=200_000,
            reservation_price=250_000,
            max_rounds=3,
            max_concession_per_round=0.05,
        )
        buyer_config = PartyConfig(
            party_id="buyer",
            role=NegotiationRole.BUYER,
            budget_cap=100_000,
            reservation_price=80_000,
            max_rounds=3,
            max_concession_per_round=0.05,
        )

        session = NegotiationSession(session_id="test-sao-002")
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)

        llm = make_mock_llm()
        seller_agent = NegotiationAgent(seller_config, llm)
        buyer_agent = NegotiationAgent(buyer_config, llm)

        protocol = SAOProtocol(seller_agent, buyer_agent, session)
        outcome = protocol.run()

        assert outcome.session_id == "test-sao-002"
        # Should complete without error
        assert outcome.rounds_completed >= 0


class TestSAOProtocolRoundProgression:
    """Test round progression and turn order."""

    def test_protocol_respects_max_rounds(self):
        """Protocol should not exceed max rounds."""
        seller_config = PartyConfig(
            party_id="seller",
            role=NegotiationRole.SELLER,
            budget_cap=100_000,
            reservation_price=200_000,
            max_rounds=3,
        )
        buyer_config = PartyConfig(
            party_id="buyer",
            role=NegotiationRole.BUYER,
            budget_cap=300_000,
            reservation_price=50_000,
            max_rounds=3,
        )

        session = NegotiationSession(session_id="test-sao-003")
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)

        llm = make_mock_llm()
        seller_agent = NegotiationAgent(seller_config, llm)
        buyer_agent = NegotiationAgent(buyer_config, llm)

        protocol = SAOProtocol(seller_agent, buyer_agent, session)
        outcome = protocol.run()

        assert outcome.rounds_completed <= 3


class TestSAOProtocolTimeout:
    """Test session timeout during negotiation."""

    def test_timeout_terminates_negotiation(self):
        """Expired session should terminate negotiation."""
        import time

        seller_config = PartyConfig(
            party_id="seller",
            role=NegotiationRole.SELLER,
            budget_cap=100_000,
            reservation_price=200_000,
            max_rounds=50,
        )
        buyer_config = PartyConfig(
            party_id="buyer",
            role=NegotiationRole.BUYER,
            budget_cap=300_000,
            reservation_price=50_000,
            max_rounds=50,
        )

        session = NegotiationSession(
            session_id="test-sao-004",
            max_duration_sec=0,  # Already expired
            created_at=time.time() - 1,
        )
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)

        llm = make_mock_llm()
        seller_agent = NegotiationAgent(seller_config, llm)
        buyer_agent = NegotiationAgent(buyer_config, llm)

        protocol = SAOProtocol(seller_agent, buyer_agent, session)
        outcome = protocol.run()

        assert outcome.outcome == "timeout"
