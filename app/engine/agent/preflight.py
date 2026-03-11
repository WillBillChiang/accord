"""
Preflight Check -- Hard Constraint Enforcement.

Every message the LLM generates passes through preflight check BEFORE
being sent. This is a pure Python function (no LLM involved) enforcing
all hard constraints. If a message violates a constraint, it is blocked
and the LLM is asked to regenerate.

Implements NDAI budget cap mechanism (Theorem 1): safety constraints
must be enforced computationally, not by LLM prompt.
"""
from __future__ import annotations

import logging
from engine.protocol.schemas import Proposal, PartyConfig, DisclosureTier, NegotiationRole

logger = logging.getLogger(__name__)


class PreflightViolation(Exception):
    """Raised when a proposal violates hard constraints."""
    def __init__(self, constraint: str, message: str):
        self.constraint = constraint
        self.message = message
        super().__init__(f"[{constraint}] {message}")


def preflight_check(
    proposal: Proposal,
    config: PartyConfig,
    previous_proposals: list[Proposal],
) -> Proposal:
    """
    Enforce hard constraints on every outgoing proposal.

    Raises PreflightViolation if any constraint is breached (except budget
    cap for buyers, which is clamped per NDAI Theorem 1).

    Returns the (possibly clamped) proposal if valid.
    """
    _check_budget_cap(proposal, config)
    _check_concession_rate(proposal, config, previous_proposals)
    _check_disclosure_boundaries(proposal, config)
    _check_round_limit(proposal, config)

    logger.info(
        f"Preflight passed: party={config.party_id}, "
        f"round={proposal.round_number}, price={proposal.price}"
    )
    return proposal


def _check_budget_cap(proposal: Proposal, config: PartyConfig) -> None:
    """
    BUDGET CAP enforcement (NDAI Theorem 1).
    Buyer: clamp price down to budget cap (don't reject -- truncate).
    Seller: reject if price below minimum.
    """
    if config.role == NegotiationRole.BUYER:
        if proposal.price > config.budget_cap:
            logger.warning(
                f"Buyer price {proposal.price} clamped to budget cap {config.budget_cap}"
            )
            proposal.price = config.budget_cap
    elif config.role == NegotiationRole.SELLER:
        if proposal.price < config.budget_cap:
            raise PreflightViolation(
                "BUDGET_CAP",
                f"Price {proposal.price} below seller minimum {config.budget_cap}"
            )


def _check_concession_rate(
    proposal: Proposal,
    config: PartyConfig,
    previous_proposals: list[Proposal],
) -> None:
    """
    CONCESSION RATE LIMIT.
    Prevents agent from making excessively large concessions in a single round.
    """
    if not previous_proposals:
        return

    last_own = None
    for p in reversed(previous_proposals):
        if p.from_party == config.party_id:
            last_own = p
            break

    if last_own is None:
        return

    if last_own.price == 0:
        return

    if config.role == NegotiationRole.SELLER:
        concession = (last_own.price - proposal.price) / last_own.price
    else:
        concession = (proposal.price - last_own.price) / last_own.price

    if concession > config.max_concession_per_round:
        raise PreflightViolation(
            "CONCESSION_RATE",
            f"Concession {concession:.1%} exceeds maximum "
            f"{config.max_concession_per_round:.1%}"
        )


def _check_disclosure_boundaries(proposal: Proposal, config: PartyConfig) -> None:
    """
    DISCLOSURE BOUNDARY enforcement.
    Blocks any field marked NEVER_DISCLOSE from being sent.
    """
    for field_name in proposal.disclosed_fields:
        tier = config.disclosure_fields.get(field_name)
        if tier == DisclosureTier.NEVER_DISCLOSE:
            raise PreflightViolation(
                "DISCLOSURE_BOUNDARY",
                f"Field '{field_name}' is marked NEVER_DISCLOSE"
            )


def _check_round_limit(proposal: Proposal, config: PartyConfig) -> None:
    """
    ROUND LIMIT enforcement.
    Prevents negotiation from exceeding configured max rounds.
    """
    if proposal.round_number > config.max_rounds:
        raise PreflightViolation(
            "ROUND_LIMIT",
            f"Round {proposal.round_number} exceeds maximum {config.max_rounds}"
        )
