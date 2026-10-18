"""Deterministic research roles. LLM integration is a future, untrusted advisory adapter."""
from __future__ import annotations
from dataclasses import dataclass
from statistics import pstdev
from .models import Bar

@dataclass(frozen=True)
class Assessment:
    symbol: str
    buy: bool
    exit: bool
    momentum_20: float
    daily_volatility: float
    reason: str

class MarketScout:
    def choose(self, histories: dict[str, list[Bar]], max_candidates: int = 2) -> list[str]:
        momentum = []
        for symbol, bars in histories.items():
            if len(bars) < 31:
                continue
            closes = [b.close for b in bars]
            momentum.append((closes[-1] / closes[-21] - 1, symbol))
        return [symbol for value, symbol in sorted(momentum, reverse=True) if value > 0][:max_candidates]

class QuantAnalyst:
    def assess(self, symbol: str, bars: list[Bar]) -> Assessment | None:
        if len(bars) < 31:
            return None
        closes = [b.close for b in bars]
        fast = sum(closes[-10:]) / 10
        slow = sum(closes[-30:]) / 30
        momentum = closes[-1] / closes[-21] - 1
        returns = [closes[i] / closes[i-1] - 1 for i in range(len(closes)-19, len(closes))]
        volatility = pstdev(returns)
        buy = fast > slow * 1.002 and momentum > 0.005
        exit_ = fast < slow or momentum < -0.02
        return Assessment(symbol, buy, exit_, momentum, volatility,
                          f"SMA10={fast:.2f}; SMA30={slow:.2f}; momentum20={momentum:.2%}; vol={volatility:.2%}")

class SkepticAgent:
    def accept(self, assessment: Assessment) -> tuple[bool, str]:
        if assessment.daily_volatility > 0.025:
            return False, "Volatility veto: >2.5% daily"
        if assessment.momentum_20 > 0.20:
            return False, "Momentum-extreme veto: >20% in 20 bars"
        return True, "Deterministic skeptical checks passed"

class NewsAnalyst:
    def status(self) -> str:
        return "UNAVAILABLE: no licensed, point-in-time news feed wired; no news-based alpha claims"

class StrategyAgent:
    @staticmethod
    def decide(assessment: Assessment, holds_position: bool, skeptic_ok: bool) -> str:
        if holds_position and assessment.exit:
            return "SELL"
        if not holds_position and assessment.buy and skeptic_ok:
            return "BUY"
        return "HOLD"
