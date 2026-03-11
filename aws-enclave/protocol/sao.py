"""
Stacked Alternating Offers (SAO) Protocol Engine.

SAO is the core negotiation mechanism. Agent A makes an offer, Agent B
evaluates and responds with accept/counter/reject. Repeats up to
configured maximum rounds. The TEE orchestrates the protocol, enforcing
turn order, round limits, and timeouts.
"""
import logging
from typing import Optional

from agent.base_agent import NegotiationAgent
from protocol.schemas import ProposalAction, NegotiationOutcome
from protocol.nash_bargaining import nash_bargaining_price, compute_outside_option_fraction
from session import NegotiationSession

logger = logging.getLogger(__name__)


class SAOProtocol:
    """
    Orchestrates the Stacked Alternating Offers negotiation protocol.
    """

    def __init__(
        self,
        seller_agent: NegotiationAgent,
        buyer_agent: NegotiationAgent,
        session: NegotiationSession,
    ) -> None:
        self.seller = seller_agent
        self.buyer = buyer_agent
        self.session = session
        self.max_rounds = min(
            seller_agent.config.max_rounds,
            buyer_agent.config.max_rounds,
        )

    def run(self) -> NegotiationOutcome:
        """
        Execute the full negotiation protocol.

        Returns NegotiationOutcome with deal terms or no-deal reason.
        """
        self.session.status = self.session.status.NEGOTIATING

        current_proposer = self.seller
        current_evaluator = self.buyer
        last_proposal = None

        for round_num in range(1, self.max_rounds + 1):
            self.session.current_round = round_num

            # Check session expiry
            if self.session.is_expired():
                logger.warning(f"Session expired at round {round_num}")
                return self.session.terminate("timeout")

            # Generate proposal
            try:
                proposal = current_proposer.generate_proposal(
                    opponent_proposal=last_proposal
                )
            except RuntimeError as e:
                logger.error(f"Agent failure at round {round_num}: {e}")
                return self.session.terminate("agent_failure")

            # Log proposal
            self.session.add_to_log({
                "action": "proposal",
                "from_party": proposal.from_party,
                "price": proposal.price,
                "terms": proposal.terms,
                "round": round_num,
            })

            logger.info(
                f"Round {round_num}: {current_proposer.config.role.value} "
                f"proposes ${proposal.price:,.2f}"
            )

            # Evaluate proposal
            response = current_evaluator.evaluate_proposal(proposal)

            # Log response
            self.session.add_to_log({
                "action": response.action.value,
                "from_party": current_evaluator.config.party_id,
                "round": round_num,
            })

            if response.action == ProposalAction.ACCEPT:
                logger.info(f"Deal reached at round {round_num}: ${proposal.price:,.2f}")
                self.session.add_to_log({
                    "action": "deal_reached",
                    "price": proposal.price,
                    "terms": proposal.terms,
                    "round": round_num,
                })
                return self.session.terminate("deal_reached")

            if response.action == ProposalAction.REJECT:
                logger.info(f"Negotiation rejected at round {round_num}")
                return self.session.terminate("rejected")

            # Counter — swap roles
            last_proposal = response.counter_proposal
            current_proposer, current_evaluator = (
                current_evaluator, current_proposer
            )

        # Exhausted all rounds — attempt Nash Bargaining fallback
        logger.info("Max rounds exhausted, attempting Nash Bargaining fallback")
        return self._nash_fallback()

    def _nash_fallback(self) -> NegotiationOutcome:
        """
        Compute Nash Bargaining Solution as fallback when SAO fails.
        Uses both parties' private reservation prices (available only inside enclave).
        """
        seller_config = self.seller.config
        buyer_config = self.buyer.config

        omega = buyer_config.budget_cap  # Estimated deal value
        alpha_0 = compute_outside_option_fraction(
            seller_config.budget_cap, omega
        )

        nash_result = nash_bargaining_price(
            omega=omega,
            alpha_0=alpha_0,
            seller_reservation=seller_config.reservation_price,
            buyer_reservation=buyer_config.reservation_price,
        )

        nash_price = nash_result["price"]

        # Check if Nash price is acceptable to both parties
        seller_accepts = nash_price >= seller_config.reservation_price
        buyer_accepts = nash_price <= buyer_config.reservation_price

        if seller_accepts and buyer_accepts:
            logger.info(f"Nash Bargaining deal at ${nash_price:,.2f}")
            self.session.add_to_log({
                "action": "nash_deal",
                "price": nash_price,
                "nash_details": nash_result,
            })
            return self.session.terminate("deal_reached")

        logger.info("Nash Bargaining failed — no acceptable price found")
        return self.session.terminate("no_agreement")
