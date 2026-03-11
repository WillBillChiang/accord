"""Seller-side negotiation agent with role-specific logic."""
from agent.base_agent import NegotiationAgent
from agent.llm_engine import LLMEngine
from protocol.schemas import PartyConfig, NegotiationRole


class SellerAgent(NegotiationAgent):
    """
    Seller agent optimizes for maximum sale price while respecting
    minimum acceptable price (budget_cap) and disclosure constraints.
    """

    def __init__(self, config: PartyConfig, llm: LLMEngine) -> None:
        if config.role != NegotiationRole.SELLER:
            raise ValueError("SellerAgent requires seller role config")
        super().__init__(config, llm)
