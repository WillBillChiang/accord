"""Tests for Pydantic schema validation.

Validates all negotiation protocol schemas including PartyConfig,
Proposal, ProposalResponse, NegotiationOutcome, and enum values.
Copied from enclave/tests with imports updated for engine.protocol.schemas.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.protocol.schemas import (
    PartyConfig, Proposal, ProposalResponse, NegotiationOutcome,
    DisclosureTier, NegotiationRole, SessionStatus, ProposalAction,
    SessionConfig, OnboardRequest, AttestationDocument,
)


class TestPartyConfig:
    """Test PartyConfig validation."""

    def test_valid_seller_config(self):
        """Valid seller config should create successfully."""
        config = PartyConfig(
            role=NegotiationRole.SELLER,
            budget_cap=100_000,
            reservation_price=120_000,
        )
        assert config.role == NegotiationRole.SELLER
        assert config.budget_cap == 100_000
        assert config.party_id  # Auto-generated UUID

    def test_valid_buyer_config(self):
        """Valid buyer config should create successfully."""
        config = PartyConfig(
            role=NegotiationRole.BUYER,
            budget_cap=200_000,
            reservation_price=150_000,
        )
        assert config.role == NegotiationRole.BUYER

    def test_zero_budget_cap_raises(self):
        """Zero budget cap should raise validation error."""
        with pytest.raises(Exception):
            PartyConfig(
                role=NegotiationRole.BUYER,
                budget_cap=0,
                reservation_price=100,
            )

    def test_negative_budget_cap_raises(self):
        """Negative budget cap should raise validation error."""
        with pytest.raises(Exception):
            PartyConfig(
                role=NegotiationRole.BUYER,
                budget_cap=-1000,
                reservation_price=100,
            )

    def test_max_rounds_bounds(self):
        """Max rounds should be between 1 and 50."""
        config = PartyConfig(
            role=NegotiationRole.BUYER,
            budget_cap=100_000,
            reservation_price=80_000,
            max_rounds=50,
        )
        assert config.max_rounds == 50

        with pytest.raises(Exception):
            PartyConfig(
                role=NegotiationRole.BUYER,
                budget_cap=100_000,
                reservation_price=80_000,
                max_rounds=0,
            )

    def test_concession_rate_bounds(self):
        """Concession rate should be between 0.01 and 1.0."""
        config = PartyConfig(
            role=NegotiationRole.BUYER,
            budget_cap=100_000,
            reservation_price=80_000,
            max_concession_per_round=0.5,
        )
        assert config.max_concession_per_round == 0.5

    def test_disclosure_fields(self):
        """Disclosure fields should accept all tier values."""
        config = PartyConfig(
            role=NegotiationRole.SELLER,
            budget_cap=100_000,
            reservation_price=120_000,
            disclosure_fields={
                "revenue": DisclosureTier.MUST_DISCLOSE,
                "secrets": DisclosureTier.NEVER_DISCLOSE,
                "plans": DisclosureTier.MAY_DISCLOSE,
            },
        )
        assert len(config.disclosure_fields) == 3

    def test_defaults(self):
        """Default values should be set correctly."""
        config = PartyConfig(
            role=NegotiationRole.BUYER,
            budget_cap=100_000,
            reservation_price=80_000,
        )
        assert config.max_rounds == 10
        assert config.max_concession_per_round == 0.15
        assert config.strategy_notes == ""
        assert config.priority_issues == []
        assert config.disclosure_fields == {}


class TestProposal:
    """Test Proposal validation."""

    def test_valid_proposal(self):
        """Valid proposal should create successfully."""
        proposal = Proposal(
            round_number=1,
            from_party="seller-001",
            price=150_000,
            terms={"structure": "all cash"},
            rationale="Market price",
        )
        assert proposal.round_number == 1
        assert proposal.price == 150_000
        assert proposal.proposal_id  # Auto-generated

    def test_zero_round_raises(self):
        """Round number 0 should raise."""
        with pytest.raises(Exception):
            Proposal(round_number=0, from_party="s", price=100)

    def test_negative_price_raises(self):
        """Negative price should raise."""
        with pytest.raises(Exception):
            Proposal(round_number=1, from_party="s", price=-100)

    def test_auto_timestamp(self):
        """Proposal should have auto-generated timestamp."""
        proposal = Proposal(round_number=1, from_party="s", price=100)
        assert proposal.timestamp > 0


class TestProposalResponse:
    """Test ProposalResponse validation."""

    def test_accept_response(self):
        """Accept response should be valid."""
        response = ProposalResponse(
            action=ProposalAction.ACCEPT,
            rationale="Price acceptable",
        )
        assert response.action == ProposalAction.ACCEPT

    def test_counter_with_proposal(self):
        """Counter response should include counter_proposal."""
        counter = Proposal(round_number=2, from_party="b", price=120_000)
        response = ProposalResponse(
            action=ProposalAction.COUNTER,
            counter_proposal=counter,
            rationale="Countering",
        )
        assert response.counter_proposal is not None

    def test_reject_response(self):
        """Reject response should be valid."""
        response = ProposalResponse(
            action=ProposalAction.REJECT,
            rationale="Cannot agree",
        )
        assert response.action == ProposalAction.REJECT


class TestNegotiationOutcome:
    """Test NegotiationOutcome."""

    def test_deal_outcome(self):
        """Deal outcome should include final terms."""
        outcome = NegotiationOutcome(
            session_id="s-001",
            outcome="deal",
            final_terms={"price": 150_000},
            final_price=150_000,
            rounds_completed=5,
            started_at=1000.0,
        )
        assert outcome.outcome == "deal"
        assert outcome.final_price == 150_000

    def test_no_deal_outcome(self):
        """No-deal outcome should have reason."""
        outcome = NegotiationOutcome(
            session_id="s-002",
            outcome="no_deal",
            reason="no_zopa",
            rounds_completed=0,
        )
        assert outcome.outcome == "no_deal"
        assert outcome.reason == "no_zopa"


class TestEnums:
    """Test enum values."""

    def test_disclosure_tiers(self):
        """DisclosureTier enum values should match expected strings."""
        assert DisclosureTier.MUST_DISCLOSE.value == "must_disclose"
        assert DisclosureTier.MAY_DISCLOSE.value == "may_disclose"
        assert DisclosureTier.NEVER_DISCLOSE.value == "never_disclose"

    def test_session_statuses(self):
        """SessionStatus enum values should match expected strings."""
        assert SessionStatus.AWAITING_PARTIES.value == "awaiting_parties"
        assert SessionStatus.NEGOTIATING.value == "negotiating"
        assert SessionStatus.DEAL_REACHED.value == "deal_reached"

    def test_proposal_actions(self):
        """ProposalAction enum values should match expected strings."""
        assert ProposalAction.ACCEPT.value == "accept"
        assert ProposalAction.COUNTER.value == "counter"
        assert ProposalAction.REJECT.value == "reject"


class TestAttestationDocument:
    """Test AttestationDocument schema (GCP-specific)."""

    def test_valid_attestation_document(self):
        """Valid attestation document should create successfully."""
        doc = AttestationDocument(
            image_digest="sha256:abc123",
            sev_snp_enabled=True,
            secure_boot=True,
            vm_id="vm-12345",
        )
        assert doc.image_digest == "sha256:abc123"
        assert doc.sev_snp_enabled is True
        assert doc.secure_boot is True
        assert doc.vm_id == "vm-12345"
        assert doc.timestamp > 0

    def test_attestation_with_nonce(self):
        """Attestation document should accept optional nonce."""
        doc = AttestationDocument(
            image_digest="digest",
            sev_snp_enabled=False,
            secure_boot=False,
            vm_id="vm-1",
            nonce="random-nonce-value",
        )
        assert doc.nonce == "random-nonce-value"

    def test_attestation_nonce_defaults_none(self):
        """Nonce should default to None."""
        doc = AttestationDocument(
            image_digest="digest",
            sev_snp_enabled=False,
            secure_boot=False,
            vm_id="vm-1",
        )
        assert doc.nonce is None
