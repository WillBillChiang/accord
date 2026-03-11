"""Buyer-side negotiation agent with role-specific logic."""
from engine.agent.base_agent import NegotiationAgent
from engine.agent.llm_engine import LLMEngine
from engine.protocol.schemas import PartyConfig, NegotiationRole


class BuyerAgent(NegotiationAgent):
    """
    Buyer agent optimizes for minimum purchase price while respecting
    maximum budget cap and disclosure constraints.
    """

    def __init__(self, config: PartyConfig, llm: LLMEngine) -> None:
        if config.role != NegotiationRole.BUYER:
            raise ValueError("BuyerAgent requires buyer role config")
        super().__init__(config, llm)
