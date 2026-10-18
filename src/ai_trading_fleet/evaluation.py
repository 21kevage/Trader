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
    ending = capital - invested + qty * bars[-1].close
    return {"symbol": symbol, "basis": "next-session-open buy-and-hold, price-only",
            "quantity": qty, "final_equity": round(ending, 2),
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
