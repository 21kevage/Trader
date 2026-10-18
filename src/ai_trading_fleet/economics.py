"""Transparent *assumed* execution economics, not observed executable quotes."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class EstimatedTradeCosts:
    notional: float
    two_sided_commission: float
    assumed_round_trip_spread_slippage: float
    total: float
    fraction: float


def estimate_round_trip(price: float, quantity: int, *, fee: float,
                        spread_bps: float, slippage_bps: float) -> EstimatedTradeCosts:
    """Estimate two-sided costs at a constant quote, *excluding* overnight price gaps.

    One half the assumed spread plus adverse slippage is charged on each side.
    Does not include tax, market impact, venue-specific charges or dividends.
    """
    if (quantity <= 0 or not isinstance(quantity, int) or
        not all(isfinite(v) and v >= 0 for v in (price, fee, spread_bps, slippage_bps))
        or price <= 0):
        raise ValueError("Invalid economic inputs")
    notional = price * quantity
    commissions = 2 * fee
    spread_slippage = notional * (spread_bps + 2 * slippage_bps) / 10_000
    total = commissions + spread_slippage
    return EstimatedTradeCosts(notional, commissions, spread_slippage,
                               total, total / notional)
