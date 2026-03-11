"""
Nash Bargaining Solution computation.

From NDAI Eq. (4)-(5): When agents cannot reach agreement through SAO,
the TEE computes Nash Bargaining Solution using both parties' private
reservation prices.

Seller's threat point is alpha_0 * omega (outside option).
Buyer's threat point is 0.
Equilibrium price is P* = theta * omega where theta = (1+alpha_0)/2.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def nash_bargaining_price(
    omega: float,
    alpha_0: float,
    seller_reservation: Optional[float] = None,
    buyer_reservation: Optional[float] = None,
) -> dict:
    """
    Compute the Nash Bargaining Solution from NDAI Eq. (4)-(5).

    Args:
        omega: Total value of the deal (estimated from buyer's max willingness)
        alpha_0: Seller's outside option as fraction of omega (0 to 1)
        seller_reservation: Seller's reservation price (optional override)
        buyer_reservation: Buyer's reservation price (optional override)

    Returns:
        Dict with price, shares, and payoffs
    """
    if omega <= 0:
        raise ValueError("Deal value (omega) must be positive")
    if not 0 <= alpha_0 <= 1:
        raise ValueError("Outside option fraction (alpha_0) must be between 0 and 1")

    theta = (1 + alpha_0) / 2
    price = theta * omega

    # Clamp to reservation prices if provided
    if seller_reservation is not None and price < seller_reservation:
        price = seller_reservation
    if buyer_reservation is not None and price > buyer_reservation:
        price = buyer_reservation

    seller_payoff = price
    buyer_payoff = omega - price

    result = {
        "price": round(price, 2),
        "seller_share": round(price / omega, 4) if omega > 0 else 0,
        "buyer_share": round((omega - price) / omega, 4) if omega > 0 else 0,
        "seller_payoff": round(seller_payoff, 2),
        "buyer_payoff": round(buyer_payoff, 2),
        "theta": round(theta, 4),
        "omega": round(omega, 2),
        "alpha_0": round(alpha_0, 4),
    }

    logger.info(f"Nash Bargaining computed: theta={theta:.4f}, price={price:.2f}")
    return result


def compute_outside_option_fraction(
    seller_min: float,
    estimated_deal_value: float,
) -> float:
    """
    Estimate alpha_0 (seller's outside option fraction) from reservation price.
    alpha_0 = seller_min / omega
    """
    if estimated_deal_value <= 0:
        raise ValueError("Estimated deal value must be positive")
    return min(1.0, max(0.0, seller_min / estimated_deal_value))
