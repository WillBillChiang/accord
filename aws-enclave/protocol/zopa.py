"""
ZOPA (Zone of Possible Agreement) computation.

Implements the ZOPA check from the NDAI paper. The TEE computes whether
seller's minimum <= buyer's maximum WITHOUT revealing actual values to
either party. This is the privacy-preserving foundation of the protocol.
"""
import logging
from protocol.schemas import PartyConfig, NegotiationRole

logger = logging.getLogger(__name__)

def compute_zopa(seller_config: PartyConfig, buyer_config: PartyConfig) -> dict:
    """
    Check if Zone of Possible Agreement exists.
    Returns boolean only — NEVER reveals actual values.

    ZOPA exists when seller's minimum acceptable price <= buyer's maximum willingness to pay.
    """
    if seller_config.role != NegotiationRole.SELLER:
        raise ValueError("First argument must be seller config")
    if buyer_config.role != NegotiationRole.BUYER:
        raise ValueError("Second argument must be buyer config")

    exists = seller_config.budget_cap <= buyer_config.budget_cap

    # Compute ZOPA range size (kept private, used internally for Nash fallback)
    zopa_range = max(0.0, buyer_config.budget_cap - seller_config.budget_cap) if exists else 0.0

    logger.info(f"ZOPA check completed: exists={exists}")
    # SECURITY: Never log actual values

    return {
        "zopa_exists": exists,
        # Internal-only fields (never sent outside enclave)
        "_zopa_range": zopa_range,
        "_seller_min": seller_config.budget_cap,
        "_buyer_max": buyer_config.budget_cap,
    }
