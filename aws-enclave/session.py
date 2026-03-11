"""
Negotiation session lifecycle management.

Manages the complete lifecycle of a negotiation session inside the
Nitro Enclave. Implements provable deletion from Conditional Recall:
when a session ends (agreement, failure, or timeout), all confidential
data is cryptographically zeroed and session keys destroyed.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from protocol.schemas import (
    PartyConfig, NegotiationRole, SessionStatus,
    NegotiationOutcome, Proposal
)
from crypto.session_keys import SessionKeyManager
from crypto.secure_delete import secure_zero_dict, secure_zero_list

logger = logging.getLogger(__name__)


@dataclass
class NegotiationSession:
    """
    Represents a single negotiation session inside the enclave.
    All data exists only in enclave memory and is destroyed on termination.
    """
    session_id: str
    max_duration_sec: int = 3600
    created_at: float = field(default_factory=time.time)
    status: SessionStatus = SessionStatus.AWAITING_PARTIES

    # Party configurations (decrypted inside enclave only)
    seller_config: Optional[PartyConfig] = None
    buyer_config: Optional[PartyConfig] = None

    # Session encryption
    key_manager: SessionKeyManager = field(default_factory=SessionKeyManager)

    # Negotiation state
    negotiation_log: list[dict] = field(default_factory=list)
    current_round: int = 0

    def onboard_party(self, config: PartyConfig) -> dict:
        """Register a party's configuration for this session."""
        if self.status not in (SessionStatus.AWAITING_PARTIES, SessionStatus.ONBOARDING):
            raise RuntimeError(f"Cannot onboard in status {self.status}")

        if config.role == NegotiationRole.SELLER:
            if self.seller_config is not None:
                raise RuntimeError("Seller already onboarded")
            self.seller_config = config
        elif config.role == NegotiationRole.BUYER:
            if self.buyer_config is not None:
                raise RuntimeError("Buyer already onboarded")
            self.buyer_config = config

        self.status = SessionStatus.ONBOARDING

        # Check if both parties are onboarded
        if self.seller_config is not None and self.buyer_config is not None:
            self.status = SessionStatus.ZOPA_CHECK

        logger.info(f"Party onboarded: role={config.role}, session={self.session_id}")
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "party_id": config.party_id,
            "role": config.role.value,
        }

    def is_expired(self) -> bool:
        """Check if session has exceeded maximum duration."""
        return (time.time() - self.created_at) > self.max_duration_sec

    def is_ready(self) -> bool:
        """Check if both parties are onboarded and ready to negotiate."""
        return (
            self.seller_config is not None
            and self.buyer_config is not None
        )

    def add_to_log(self, entry: dict) -> None:
        """Add an entry to the negotiation log."""
        entry["timestamp"] = time.time()
        entry["round"] = self.current_round
        self.negotiation_log.append(entry)

    def get_redacted_log(self) -> list[dict]:
        """
        Return negotiation log with confidential data redacted.
        Safe to send outside enclave for audit purposes.
        """
        redacted = []
        for entry in self.negotiation_log:
            redacted_entry = {
                "round": entry.get("round"),
                "timestamp": entry.get("timestamp"),
                "action": entry.get("action"),
                "from_party": entry.get("from_party"),
                # Redact actual prices and terms
                "price_offered": entry.get("price") is not None,
                "terms_included": bool(entry.get("terms")),
            }
            redacted.append(redacted_entry)
        return redacted

    def terminate(self, reason: str) -> NegotiationOutcome:
        """
        Provably destroy all session data.
        Implements "credible forgetting" from Conditional Recall.
        """
        outcome_status = reason
        final_terms = None
        final_price = None

        if reason == "deal_reached" and self.negotiation_log:
            last_entry = self.negotiation_log[-1]
            final_terms = last_entry.get("terms")
            final_price = last_entry.get("price")

        outcome = NegotiationOutcome(
            session_id=self.session_id,
            outcome=outcome_status,
            reason=reason,
            final_terms=final_terms,
            final_price=final_price,
            rounds_completed=self.current_round,
            started_at=self.created_at,
        )

        # Securely destroy all confidential data
        self._destroy_session_data()

        logger.info(
            f"Session terminated: id={self.session_id}, "
            f"reason={reason}, rounds={self.current_round}"
        )
        return outcome

    def _destroy_session_data(self) -> None:
        """Securely zero all session data in memory."""
        # Destroy encryption keys
        self.key_manager.destroy()

        # Zero party configs
        if self.seller_config:
            if self.seller_config.confidential_data:
                secure_zero_dict(self.seller_config.confidential_data)
            self.seller_config = None

        if self.buyer_config:
            if self.buyer_config.confidential_data:
                secure_zero_dict(self.buyer_config.confidential_data)
            self.buyer_config = None

        # Zero negotiation log
        secure_zero_list(self.negotiation_log)

        self.status = SessionStatus.NO_DEAL
