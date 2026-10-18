"""Pure simulated fills; deliberately NO live broker client or credential handling."""
from __future__ import annotations
from math import isfinite
from .models import Bar, Fill, PendingOrder, Portfolio, Position
from .risk import RiskEngine

class SimulatedBroker:
    def __init__(self, fee: float = 1.25, slippage_bps: float = 5.0):
        self.fee = fee
        self.slippage_bps = slippage_bps
        self.executed_ids: set[str] = set()

    def execute(self, order: PendingOrder, next_bar: Bar, portfolio: Portfolio,
                risk: RiskEngine, marks: dict[str, float]) -> tuple[Fill | None, str]:
        p = order.proposal
        if order.order_id in self.executed_ids:
            return None, "Duplicate order ignored"
        if next_bar.symbol != p.symbol or next_bar.date <= p.signal_date:
            return None, "Missing next-session open / future execution required"
        if (not all(isfinite(v) for v in (next_bar.open, next_bar.spread_bps))
            or next_bar.open <= 0 or not (0 <= next_bar.spread_bps <= risk.policy.max_spread_bps) or next_bar.volume <= 0):
            return None, "Illiquid next session"
        multiplier = 1 + (self.slippage_bps / 10000) * (1 if p.side == "BUY" else -1)
        price = round(next_bar.open * multiplier, 4)
        if p.side == "BUY" and price > order.limit_price:
            return None, "Buy limit not reached"
        if p.side == "SELL" and price < order.limit_price:
            return None, "Sell limit not reached"
        cost = price * p.quantity
        if p.side == "BUY":
            if p.symbol in portfolio.positions or cost + self.fee > portfolio.cash:
                return None, "Insufficient cash or duplicate position at fill"
            allowed, reason = risk.check_execution_buy(p, price, portfolio, marks, next_bar.date)
            if not allowed:
                return None, reason
            portfolio.cash -= cost + self.fee
            portfolio.positions[p.symbol] = Position(p.quantity, price, price * (1-p.stop_pct))
            portfolio.last_buy_date[p.symbol] = next_bar.date
        elif p.side == "SELL":
            position = portfolio.positions.get(p.symbol)
            if not position or position.quantity < p.quantity:
                return None, "Insufficient position at fill"
            portfolio.cash += cost - self.fee
            portfolio.realized_pnl += (price - position.average_price) * p.quantity - 2 * self.fee
            position.quantity -= p.quantity
            if not position.quantity:
                del portfolio.positions[p.symbol]
        else:
            return None, "Invalid side"
        portfolio.fees += self.fee
        portfolio.traded_date_count[next_bar.date] = portfolio.traded_date_count.get(next_bar.date, 0) + 1
        fill = Fill(next_bar.date, p.symbol, p.side, p.quantity, price, self.fee, order.order_id)
        portfolio.fills.append(fill)
        self.executed_ids.add(order.order_id)
        return fill, "Simulated fill"
