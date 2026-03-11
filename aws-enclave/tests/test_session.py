"""Tests for session lifecycle management."""
import pytest
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from session import NegotiationSession
from protocol.schemas import (
    PartyConfig, NegotiationRole, SessionStatus, DisclosureTier,
)


class TestSessionCreation:
    """Test session creation and initialization."""

    def test_session_creates_with_defaults(self):
        """Session should initialize with correct defaults."""
        session = NegotiationSession(session_id="test-001")
        assert session.session_id == "test-001"
        assert session.status == SessionStatus.AWAITING_PARTIES
        assert session.seller_config is None
        assert session.buyer_config is None
        assert session.current_round == 0
        assert len(session.negotiation_log) == 0

    def test_session_has_key_manager(self):
        """Session should have an active key manager."""
        session = NegotiationSession(session_id="test-002")
        assert session.key_manager is not None
        assert not session.key_manager.is_destroyed


class TestSessionOnboarding:
    """Test party onboarding."""

    def test_onboard_seller(self, seller_config):
        """Onboarding seller should update session."""
        session = NegotiationSession(session_id="test-003")
        result = session.onboard_party(seller_config)
        assert session.seller_config is not None
        assert session.status == SessionStatus.ONBOARDING
        assert result["role"] == "seller"

    def test_onboard_buyer(self, buyer_config):
        """Onboarding buyer should update session."""
        session = NegotiationSession(session_id="test-004")
        result = session.onboard_party(buyer_config)
        assert session.buyer_config is not None
        assert result["role"] == "buyer"

    def test_onboard_both_parties_triggers_zopa_check(self, seller_config, buyer_config):
        """Onboarding both parties should transition to ZOPA_CHECK."""
        session = NegotiationSession(session_id="test-005")
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)
        assert session.status == SessionStatus.ZOPA_CHECK
        assert session.is_ready()

    def test_duplicate_seller_raises(self, seller_config):
        """Onboarding a second seller should raise."""
        session = NegotiationSession(session_id="test-006")
        session.onboard_party(seller_config)
        with pytest.raises(RuntimeError, match="Seller already"):
            session.onboard_party(seller_config)

    def test_duplicate_buyer_raises(self, buyer_config):
        """Onboarding a second buyer should raise."""
        session = NegotiationSession(session_id="test-007")
        session.onboard_party(buyer_config)
        with pytest.raises(RuntimeError, match="Buyer already"):
            session.onboard_party(buyer_config)


class TestSessionExpiry:
    """Test session timeout."""

    def test_session_not_expired_initially(self):
        """New session should not be expired."""
        session = NegotiationSession(session_id="test-008")
        assert not session.is_expired()

    def test_session_expires_after_duration(self):
        """Session should expire after max duration."""
        session = NegotiationSession(
            session_id="test-009",
            max_duration_sec=0,  # Expire immediately
            created_at=time.time() - 1,
        )
        assert session.is_expired()


class TestSessionTermination:
    """Test session termination and provable deletion."""

    def test_terminate_returns_outcome(self, seller_config, buyer_config):
        """Termination should return NegotiationOutcome."""
        session = NegotiationSession(session_id="test-010")
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)
        outcome = session.terminate("no_deal")
        assert outcome.session_id == "test-010"
        assert outcome.outcome == "no_deal"

    def test_terminate_destroys_configs(self, seller_config, buyer_config):
        """Termination should destroy party configs."""
        session = NegotiationSession(session_id="test-011")
        session.onboard_party(seller_config)
        session.onboard_party(buyer_config)
        session.terminate("no_deal")
        assert session.seller_config is None
        assert session.buyer_config is None

    def test_terminate_destroys_keys(self, seller_config):
        """Termination should destroy session keys."""
        session = NegotiationSession(session_id="test-012")
        session.onboard_party(seller_config)
        session.terminate("no_deal")
        assert session.key_manager.is_destroyed

    def test_terminate_clears_log(self, seller_config):
        """Termination should clear the negotiation log."""
        session = NegotiationSession(session_id="test-013")
        session.onboard_party(seller_config)
        session.add_to_log({"action": "test"})
        session.terminate("no_deal")
        assert len(session.negotiation_log) == 0


class TestSessionLog:
    """Test negotiation logging."""

    def test_add_to_log(self):
        """Adding to log should include timestamp."""
        session = NegotiationSession(session_id="test-014")
        session.add_to_log({"action": "proposal", "price": 100_000})
        assert len(session.negotiation_log) == 1
        assert "timestamp" in session.negotiation_log[0]

    def test_redacted_log_hides_prices(self):
        """Redacted log should not contain actual prices."""
        session = NegotiationSession(session_id="test-015")
        session.add_to_log({"action": "proposal", "price": 100_000, "from_party": "s1"})
        redacted = session.get_redacted_log()
        assert len(redacted) == 1
        assert "price" not in redacted[0] or redacted[0].get("price") is None
        assert redacted[0]["price_offered"] is True
