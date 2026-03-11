from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
import time, uuid

class DisclosureTier(str, Enum):
    MUST_DISCLOSE = "must_disclose"    # Always share
    MAY_DISCLOSE = "may_disclose"      # Agent decides strategically
    NEVER_DISCLOSE = "never_disclose"  # Hard block, never leaves enclave

class NegotiationRole(str, Enum):
    SELLER = "seller"
    BUYER = "buyer"

class SessionStatus(str, Enum):
    AWAITING_PARTIES = "awaiting_parties"
    ONBOARDING = "onboarding"
    ZOPA_CHECK = "zopa_check"
    NEGOTIATING = "negotiating"
    DEAL_REACHED = "deal_reached"
    NO_DEAL = "no_deal"
    EXPIRED = "expired"
    ERROR = "error"

class ProposalAction(str, Enum):
    ACCEPT = "accept"
    COUNTER = "counter"
    REJECT = "reject"

class PartyConfig(BaseModel):
    party_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: NegotiationRole
    budget_cap: float = Field(gt=0, description="Max payment (buyer) / min accept (seller)")
    reservation_price: float = Field(gt=0, description="Walk-away price")
    max_rounds: int = Field(default=10, ge=1, le=50)
    max_concession_per_round: float = Field(default=0.15, ge=0.01, le=1.0)
    disclosure_fields: dict[str, DisclosureTier] = Field(default_factory=dict)
    strategy_notes: str = ""
    priority_issues: list[str] = Field(default_factory=list)
    acceptable_deal_structures: list[str] = Field(default_factory=list)
    confidential_data: dict = Field(default_factory=dict, description="Encrypted data, only accessible inside enclave")

    @field_validator('reservation_price')
    @classmethod
    def validate_reservation_price(cls, v, info):
        # Validation happens at protocol level since it depends on role
        return v

class Proposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    round_number: int = Field(ge=1)
    from_party: str
    price: float = Field(gt=0)
    terms: dict = Field(default_factory=dict)
    disclosed_fields: dict[str, str] = Field(default_factory=dict)
    rationale: str = ""
    timestamp: float = Field(default_factory=time.time)

class ProposalResponse(BaseModel):
    response_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: ProposalAction
    counter_proposal: Optional[Proposal] = None
    rationale: str = ""
    timestamp: float = Field(default_factory=time.time)

class NegotiationOutcome(BaseModel):
    session_id: str
    outcome: str  # "deal" or "no_deal"
    reason: str = ""
    final_terms: Optional[dict] = None
    final_price: Optional[float] = None
    rounds_completed: int = 0
    started_at: float = 0.0
    completed_at: float = Field(default_factory=time.time)

class SessionConfig(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    max_duration_sec: int = Field(default=3600, description="Max session duration in seconds")
    created_at: float = Field(default_factory=time.time)
    status: SessionStatus = SessionStatus.AWAITING_PARTIES

class OnboardRequest(BaseModel):
    session_id: str
    party_id: str
    role: NegotiationRole
    encrypted_config: str  # Base64-encoded, KMS-encrypted config
    encrypted_data: str    # Base64-encoded, KMS-encrypted confidential data

class AttestationDocument(BaseModel):
    pcr0: str  # Hash of enclave image
    pcr1: str  # Hash of Linux kernel
    pcr2: str  # Hash of application
    timestamp: float = Field(default_factory=time.time)
    nonce: Optional[str] = None

class VsockMessage(BaseModel):
    action: str
    session_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
