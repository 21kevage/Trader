"""Fail-closed policy. No LLM or supervisor method may change these limits."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from math import floor, isfinite
from .models import Bar, Portfolio, Proposal

@dataclass(frozen=True)
class RiskPolicy:
    permitted_symbols: frozenset[str] = frozenset({"DEMO_WORLD", "DEMO_BONDS", "DEMO_CASH"})
    max_position_fraction: float = 0.20
    max_gross_exposure_fraction: float = 0.60
    max_trade_risk_fraction: float = 0.0025
    daily_loss_circuit_breaker: float = 0.01
    weekly_loss_circuit_breaker: float = 0.025
    equity_drawdown_circuit_breaker: float = 0.05
    max_spread_bps: float = 35.0
    max_trades_per_day: int = 2
    max_open_positions: int = 3
    assumed_fee: float = 1.25
    cooldown_days: int = 5
    kill_switch: bool = False

class RiskEngine:
    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    def size_buy(self, price: float, equity: float, cash: float, stop_pct: float) -> int:
        if not all(isfinite(v) and v > 0 for v in (price, equity, stop_pct)) or cash <= 0:
            return 0
        p = self.policy
        allowance = min(
            equity * p.max_trade_risk_fraction / (price * stop_pct),
            equity * p.max_position_fraction / price,
            max(0, cash - p.assumed_fee) / (price * 1.01),
        )
        return max(0, floor(allowance))

    def check(self, proposal: Proposal, bar: Bar, portfolio: Portfolio,
              marks: dict[str, float], asof: date) -> tuple[bool, str]:
        p = self.policy
        if proposal.side not in {"BUY", "SELL"} or proposal.quantity <= 0:
            return False, "Invalid side or quantity"
        if proposal.symbol != bar.symbol or proposal.symbol not in p.permitted_symbols:
            return False, "Symbol not allowed"
        if proposal.signal_date != asof or bar.date != asof:
            return False, "Stale/mismatched quote"
        if not all(isfinite(v) for v in (bar.close, bar.spread_bps)) or bar.close <= 0 or not (0 <= bar.spread_bps <= p.max_spread_bps):
            return False, "Invalid price or spread"
        pos = portfolio.positions.get(proposal.symbol)
        if proposal.side == "SELL":
            return (True, "Exit permitted") if pos and pos.quantity >= proposal.quantity else (False, "No position")
        if p.kill_switch:
            return False, "KILL SWITCH"
        if portfolio.traded_date_count.get(asof, 0) >= p.max_trades_per_day:
            return False, "Max daily trades"
        equity = portfolio.equity(marks)
        if equity <= 0:
            return False, "No equity"
        if (portfolio.peak_equity - equity) / portfolio.peak_equity >= p.equity_drawdown_circuit_breaker:
            return False, "Max drawdown circuit breaker"
        if portfolio.day_start_equity > 0 and ((portfolio.day_start_equity - equity) /
            portfolio.day_start_equity >= p.daily_loss_circuit_breaker):
            return False, "Daily loss circuit breaker"
        if portfolio.week_start_equity > 0 and ((portfolio.week_start_equity - equity) /
            portfolio.week_start_equity >= p.weekly_loss_circuit_breaker):
            return False, "Weekly loss circuit breaker"
        if pos:
            return False, "No pyramiding"
        if len(portfolio.positions) >= p.max_open_positions:
            return False, "Max open positions"
        last_buy = portfolio.last_buy_date.get(proposal.symbol)
        if last_buy and (asof - last_buy).days < p.cooldown_days:
            return False, "Cooldown"
        notional = bar.close * proposal.quantity
        if notional > equity * p.max_position_fraction:
            return False, "Position exceeds cap"
        if notional + p.assumed_fee > portfolio.cash:
            return False, "Insufficient cash"
        if notional * proposal.stop_pct > equity * p.max_trade_risk_fraction:
            return False, "Stop-based risk budget exceeded"
        gross = sum(position.quantity * marks.get(sym, position.average_price)
                    for sym, position in portfolio.positions.items())
        if gross + notional > equity * p.max_gross_exposure_fraction:
            return False, "Gross exposure exceeded"
        return True, "Risk checks passed"

    def check_execution_buy(self, proposal: Proposal, actual_fill_price: float,
                            portfolio: Portfolio, marks: dict[str, float], execution_date: date) -> tuple[bool, str]:
        """Independent order-time recheck; gaps cannot bypass notional/exposure cap."""
        p = self.policy
        if p.kill_switch:
            return False, "KILL SWITCH"
        equity = portfolio.equity(marks)
        if equity <= 0:
            return False, "No equity"
        if actual_fill_price * proposal.quantity + p.assumed_fee > portfolio.cash:
            return False, "Insufficient funds at execution"
        if actual_fill_price * proposal.quantity > equity * p.max_position_fraction:
            return False, "Gap exceeds position cap"
        if actual_fill_price * proposal.quantity * proposal.stop_pct > equity * p.max_trade_risk_fraction:
            return False, "Gap exceeds risk budget"
        gross = sum(position.quantity * marks.get(sym, position.average_price)
                    for sym, position in portfolio.positions.items())
        if gross + actual_fill_price * proposal.quantity > equity * p.max_gross_exposure_fraction:
            return False, "Gap exceeds gross exposure cap"
        if portfolio.traded_date_count.get(execution_date, 0) >= p.max_trades_per_day:
            return False, "Trade limit"
        if portfolio.peak_equity > 0 and (portfolio.peak_equity - equity) / portfolio.peak_equity >= p.equity_drawdown_circuit_breaker:
            return False, "Drawdown circuit breaker at execution"
        if portfolio.day_start_equity > 0 and (portfolio.day_start_equity - equity) / portfolio.day_start_equity >= p.daily_loss_circuit_breaker:
            return False, "Daily loss circuit breaker at execution"
        if portfolio.week_start_equity > 0 and (portfolio.week_start_equity - equity) / portfolio.week_start_equity >= p.weekly_loss_circuit_breaker:
            return False, "Weekly loss circuit breaker at execution"
        return True, "Execution checks passed"
