"""
Base negotiation agent powered by LLM inference.

Design Principle from NDAI: Hard constraints in code, soft strategy in LLM.
The LLM handles natural-language reasoning, proposal generation, and evaluation.
The TEE enforces budget caps, acceptance thresholds, disclosure boundaries,
and round limits as hard code constraints the LLM cannot override.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from protocol.schemas import (
    Proposal, ProposalResponse, ProposalAction,
    PartyConfig, NegotiationRole
)
from agent.preflight import preflight_check, PreflightViolation
from agent.llm_engine import LLMEngine

logger = logging.getLogger(__name__)

MAX_GENERATION_RETRIES = 3


class NegotiationAgent:
    """
    AI negotiation agent that generates proposals using an LLM
    with hard constraint enforcement via preflight checks.
    """

    def __init__(self, config: PartyConfig, llm: LLMEngine) -> None:
        self.config = config
        self.llm = llm
        self.history: list[Proposal] = []
        self._all_proposals: list[Proposal] = []  # All proposals (own + opponent)

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM with role and constraints."""
        role_desc = "seller" if self.config.role == NegotiationRole.SELLER else "buyer"

        if self.config.role == NegotiationRole.BUYER:
            constraint_desc = f"Maximum price: {self.config.budget_cap}"
        else:
            constraint_desc = f"Minimum price: {self.config.budget_cap}"

        return f"""You are a negotiation agent representing the {role_desc}.
Your goal is to reach the best possible deal for your principal within their stated constraints.

HARD CONSTRAINTS (enforced by system, cannot override):
- {constraint_desc}
- Max concession per round: {self.config.max_concession_per_round:.0%}
- Max rounds remaining: {self.config.max_rounds - len(self.history)}
- Reservation (walk-away) price: {self.config.reservation_price}

STRATEGY GUIDANCE FROM PRINCIPAL:
{self.config.strategy_notes}
Priority issues: {', '.join(self.config.priority_issues) if self.config.priority_issues else 'None specified'}
Acceptable structures: {', '.join(self.config.acceptable_deal_structures) if self.config.acceptable_deal_structures else 'Any'}

DISCLOSURE POLICY:
{self._format_disclosure_policy()}

You MUST respond with valid JSON containing these fields:
- "price": numeric value for your offer
- "terms": object with deal terms
- "disclosed_fields": object mapping field names to values you choose to disclose
- "rationale": string explaining your reasoning
"""

    def _format_disclosure_policy(self) -> str:
        """Format disclosure policy for LLM prompt."""
        if not self.config.disclosure_fields:
            return "No specific disclosure policy set."

        lines = []
        for field_name, tier in self.config.disclosure_fields.items():
            if tier.value == "must_disclose":
                lines.append(f"- {field_name}: MUST disclose (required)")
            elif tier.value == "may_disclose":
                lines.append(f"- {field_name}: MAY disclose (your decision)")
            elif tier.value == "never_disclose":
                lines.append(f"- {field_name}: NEVER disclose (system-enforced block)")
        return "\n".join(lines) if lines else "No specific disclosure policy set."

    def _build_negotiation_prompt(self, opponent_proposal: Optional[Proposal] = None) -> str:
        """Build the user prompt with negotiation history and opponent's latest offer."""
        parts = []

        if self._all_proposals:
            parts.append("NEGOTIATION HISTORY:")
            for p in self._all_proposals[-6:]:  # Last 6 proposals for context
                who = "You" if p.from_party == self.config.party_id else "Opponent"
                parts.append(
                    f"  Round {p.round_number} ({who}): "
                    f"Price=${p.price:,.2f}, Terms={p.terms}"
                )

        if opponent_proposal:
            parts.append(f"\nOPPONENT'S LATEST OFFER:")
            parts.append(f"  Price: ${opponent_proposal.price:,.2f}")
            parts.append(f"  Terms: {opponent_proposal.terms}")
            parts.append(f"  Rationale: {opponent_proposal.rationale}")
            parts.append(f"\nGenerate your counter-proposal.")
        else:
            parts.append("\nGenerate your opening proposal.")

        return "\n".join(parts)

    def generate_proposal(self, opponent_proposal: Optional[Proposal] = None) -> Proposal:
        """
        Generate a proposal using LLM, enforce preflight constraints.
        Retries up to MAX_GENERATION_RETRIES times if constraints violated.
        """
        if opponent_proposal:
            self._all_proposals.append(opponent_proposal)

        round_number = len(self.history) + 1

        for attempt in range(MAX_GENERATION_RETRIES):
            proposal = self._generate_raw_proposal(round_number, opponent_proposal)

            try:
                proposal = preflight_check(proposal, self.config, self.history)
                self.history.append(proposal)
                self._all_proposals.append(proposal)
                return proposal
            except PreflightViolation as e:
                logger.warning(
                    f"Preflight violation (attempt {attempt + 1}): {e}"
                )
                continue

        # Fallback: generate a safe default proposal
        proposal = self._generate_fallback_proposal(round_number)
        self.history.append(proposal)
        self._all_proposals.append(proposal)
        return proposal

    def _generate_raw_proposal(
        self, round_number: int, opponent_proposal: Optional[Proposal]
    ) -> Proposal:
        """Generate a proposal using LLM or fallback strategy."""
        llm_output = None
        if self.llm.is_available:
            llm_output = self.llm.generate_json(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_negotiation_prompt(opponent_proposal),
            )

        if llm_output:
            return Proposal(
                round_number=round_number,
                from_party=self.config.party_id,
                price=float(llm_output.get("price", self.config.budget_cap)),
                terms=llm_output.get("terms", {}),
                disclosed_fields=llm_output.get("disclosed_fields", {}),
                rationale=llm_output.get("rationale", ""),
            )

        return self._generate_fallback_proposal(round_number)

    def _generate_fallback_proposal(self, round_number: int) -> Proposal:
        """
        Generate a safe fallback proposal without LLM.
        Uses a simple concession strategy within hard constraints.
        """
        if self.config.role == NegotiationRole.SELLER:
            # Start high, concede toward reservation price
            start_price = self.config.budget_cap * 1.5
            target = self.config.reservation_price
            progress = min(1.0, (round_number - 1) / max(1, self.config.max_rounds - 1))
            price = start_price - (start_price - target) * progress * 0.5
            price = max(price, self.config.budget_cap)
        else:
            # Start low, concede toward reservation price
            start_price = self.config.budget_cap * 0.5
            target = self.config.reservation_price
            progress = min(1.0, (round_number - 1) / max(1, self.config.max_rounds - 1))
            price = start_price + (target - start_price) * progress * 0.5
            price = min(price, self.config.budget_cap)

        # Include MUST_DISCLOSE fields
        disclosed = {}
        for field_name, tier in self.config.disclosure_fields.items():
            if tier.value == "must_disclose":
                value = self.config.confidential_data.get(field_name, "")
                if value:
                    disclosed[field_name] = str(value)

        return Proposal(
            round_number=round_number,
            from_party=self.config.party_id,
            price=round(price, 2),
            terms={},
            disclosed_fields=disclosed,
            rationale="Fallback proposal generated within hard constraints",
        )

    def evaluate_proposal(self, incoming: Proposal) -> ProposalResponse:
        """
        Evaluate opponent's proposal against acceptance threshold.
        """
        self._all_proposals.append(incoming)

        # Hard check: is price acceptable?
        if self.config.role == NegotiationRole.SELLER:
            price_acceptable = incoming.price >= self.config.reservation_price
        else:
            price_acceptable = incoming.price <= self.config.reservation_price

        if price_acceptable:
            return ProposalResponse(
                action=ProposalAction.ACCEPT,
                rationale=f"Price ${incoming.price:,.2f} meets reservation threshold",
            )

        # Check if we've exhausted rounds
        if len(self.history) >= self.config.max_rounds:
            return ProposalResponse(
                action=ProposalAction.REJECT,
                rationale="Maximum rounds exhausted",
            )

        # Generate counter-proposal
        counter = self.generate_proposal(opponent_proposal=incoming)
        return ProposalResponse(
            action=ProposalAction.COUNTER,
            counter_proposal=counter,
            rationale=f"Price ${incoming.price:,.2f} does not meet threshold, countering",
        )
