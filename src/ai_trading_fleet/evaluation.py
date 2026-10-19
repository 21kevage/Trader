"""Deliberately simple, price-only offline performance comparisons."""
from __future__ import annotations
from datetime import date
from .models import Bar


def buy_and_hold(data: dict[date, dict[str, Bar]], symbol: str,
                 capital: float = 1000, fee: float = 1.25) -> dict:
    """Buy at second available session OPEN, value at final CLOSE. Not risk-matched."""
    bars = [daily[symbol] for day, daily in sorted(data.items()) if symbol in daily]
    if len(bars) < 2:
        raise ValueError("Insufficient sessions for baseline")
    execution = next((bar for bar in bars[1:] if bar.volume > 0), None)
    if execution is None:
        raise ValueError("No tradable session with reported volume for buy-and-hold")
    qty = int(max(0, (capital - fee) // execution.open))
    invested = qty * execution.open + (fee if qty else 0)
    dividend_cash = qty * sum(bar.dividend for bar in bars if bar.date > execution.date)
    ending = capital - invested + qty * bars[-1].close + dividend_cash
    return {"symbol": symbol, "basis": "next-session-open buy-and-hold, price-only",
            "quantity": qty, "dividends_credited_eur": round(dividend_cash, 2),
            "final_equity": round(ending, 2),
            "return_pct": round((ending / capital - 1) * 100, 3)}


def summarize_holdout(curve: list[dict], holdout_start: date) -> dict:
    """A descriptive split, not model fitting or a statistically valid alpha claim."""
    prior = [p for p in curve if date.fromisoformat(p["date"]) < holdout_start]
    after = [p for p in curve if date.fromisoformat(p["date"]) >= holdout_start]
    if len(prior) < 60 or len(after) < 30:
        raise ValueError("Need at least 60 pre-holdout and 30 holdout observations")
    initial = prior[-1]["equity"]
    ending = after[-1]["equity"]
    return {"start": holdout_start.isoformat(), "start_equity": initial,
            "final_equity": ending, "return_pct": round(100*(ending/initial-1), 3),
            "sessions": len(after), "note": "Descriptive split only; no strategy optimization"}


def capped_buy_and_hold(data: dict[date, dict[str, Bar]], symbol: str,
                        capital: float = 1000.0, allocation_fraction: float = 0.20,
                        fee: float = 1.25, slippage_bps: float = 5.0) -> dict:
    """Long-only, initial-investment-capped passive benchmark; no stop / rebalancing.

    It is NOT stop-risk matched to the active trading strategy, only exposure-capped.
    The remaining cash earns zero interest. One half spread and assumed adverse
    slippage are applied at entry. No exit is simulated at the period endpoint.
    """
    from math import floor
    if capital <= 0 or not 0 <= allocation_fraction <= 1 or fee < 0 or slippage_bps < 0:
        raise ValueError("Invalid benchmark inputs")
    bars = [daily[symbol] for _, daily in sorted(data.items()) if symbol in daily]
    if len(bars) < 2:
        raise ValueError("Insufficient sessions for benchmark")
    execution = next((bar for bar in bars[1:] if bar.volume > 0), None)
    if execution is None:
        raise ValueError("No tradable session with reported volume for benchmark")
    effective_open = execution.open * (1 + (execution.spread_bps / 2 + slippage_bps) / 10000)
    budget = min(capital * allocation_fraction, capital)
    qty = max(0, floor((budget - fee) / effective_open))
    entry_cost = qty * effective_open + (fee if qty else 0)
    dividend_cash = qty * sum(bar.dividend for bar in bars if bar.date > execution.date)
    final_equity = capital - entry_cost + qty * bars[-1].close + dividend_cash
    return {"symbol": symbol, "basis": "initial allocation cap, entry costs, no stop or dividends",
            "allocation_cap_pct": allocation_fraction * 100, "quantity": qty,
            "initial_cash_uninvested": round(capital - entry_cost, 2),
            "dividends_credited_eur": round(dividend_cash, 2),
            "final_equity": round(final_equity, 2),
            "return_pct": round(100 * (final_equity / capital - 1), 3)}
