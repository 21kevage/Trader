"""Event-driven daily-bar historical simulation. Signal at close, fill at NEXT open."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from .agents import MarketScout, QuantAnalyst, SkepticAgent, StrategyAgent, NewsAnalyst
from .models import Audit, Bar, PendingOrder, Portfolio, Proposal
from .risk import RiskEngine, RiskPolicy
from .execution import SimulatedBroker

class TradingFleet:
    def __init__(self, policy: RiskPolicy | None = None, starting_cash: float = 1000.0,
                 data_mode: str = "OFFLINE_SYNTHETIC_SIMULATION_ONLY"):
        if data_mode not in {"OFFLINE_SYNTHETIC_SIMULATION_ONLY", "OFFLINE_HISTORICAL_BACKTEST_ONLY"}:
            raise ValueError("Unrecognized simulation mode")
        self.data_mode = data_mode
        self.policy = policy or RiskPolicy()
        if starting_cash <= 0:
            raise ValueError("Starting cash must be positive")
        self.portfolio = Portfolio(cash=starting_cash, peak_equity=starting_cash,
                                   last_equity=starting_cash, previous_equity=starting_cash,
                                   day_start_equity=starting_cash, week_start_equity=starting_cash)
        self.risk = RiskEngine(self.policy)
        self.broker = SimulatedBroker(fee=self.policy.assumed_fee)
        self.scout = MarketScout()
        self.quant = QuantAnalyst()
        self.skeptic = SkepticAgent()
        self.strategy = StrategyAgent()
        self.news = NewsAnalyst()
        self.audits: list[Audit] = []
        self.curve: list[dict] = []
        self.histories: dict[str, list[Bar]] = defaultdict(list)
        self.pending: list[PendingOrder] = []
        self.previous_marks: dict[str, float] = {}

    def log(self, date_: date, actor: str, kind: str, message: str):
        self.audits.append(Audit(date_, actor, kind, message))

    def run(self, data: dict[date, dict[str, Bar]]) -> dict:
        if not data:
            raise ValueError("Data required")
        first = True
        prev_week = None
        for today, bar_map in sorted(data.items()):
            # Price marking at yesterday's close avoids today's-close lookahead for opening orders.
            p = self.portfolio
            opening_marks = dict(self.previous_marks)
            for symbol, bar in bar_map.items():
                opening_marks[symbol] = bar.open
            if not first:
                p.day_start_equity = p.previous_equity
            iso_week = today.isocalendar()[:2]
            if iso_week != prev_week:
                p.week_start_equity = p.previous_equity
                prev_week = iso_week
            first = False
            due = self.pending
            self.pending = []
            for order in due:
                bar = bar_map.get(order.proposal.symbol)
                if bar is None:
                    self.log(today, "Broker", "REJECT", f"{order.order_id}: missing next-session bar")
                    continue
                fill, reason = self.broker.execute(order, bar, p, self.risk, opening_marks)
                self.log(today, "Broker", "FILL" if fill else "REJECT", f"{order.order_id}: {reason}")
            for symbol, bar in bar_map.items():
                self.histories[symbol].append(bar)
            marks = dict(self.previous_marks)
            marks.update({s: b.close for s, b in bar_map.items()})
            equity = p.equity(marks)
            p.peak_equity = max(p.peak_equity, equity)
            if self.risk.observe_drawdown(equity, p.peak_equity, today):
                self.log(today, "CircuitBreaker", "TRIP", "Drawdown threshold crossed; latch persists until offline run reset")
            self.curve.append({"date": today.isoformat(), "equity": round(equity, 2),
                               "cash": round(p.cash, 2)})
            p.previous_equity = equity
            p.last_equity = equity
            p.last_date = today
            candidates = self.scout.choose(self.histories)
            # Exits checked for all held positions, even if removed from scout list.
            for symbol in sorted(set(candidates) | set(p.positions)):
                if symbol not in bar_map:
                    continue
                bar = bar_map[symbol]
                if bar.volume <= 0:
                    self.log(today, "MarketData", "SKIP", f"{symbol}: zero volume")
                    continue
                assessment = self.quant.assess(symbol, self.histories[symbol])
                if assessment is None:
                    continue
                holds = symbol in p.positions
                skeptic_ok, skeptic_reason = self.skeptic.accept(assessment)
                action = self.strategy.decide(assessment, holds, skeptic_ok)
                if holds and bar.close <= p.positions[symbol].stop_price:
                    action = "SELL"
                    self.log(today, "RiskEngine", "STOP", f"{symbol}: stop threshold at CLOSE; next-open exit only")
                if action == "BUY" and symbol not in candidates:
                    action = "HOLD"
                self.log(today, "Quant/Skeptic", "ASSESSMENT",
                         f"{symbol}: {assessment.reason}; {skeptic_reason}; action={action}")
                if action == "HOLD":
                    continue
                qty = (p.positions[symbol].quantity if action == "SELL" else
                       self.risk.size_buy(bar.close, equity, p.cash, .04))
                if qty <= 0:
                    self.log(today, "RiskEngine", "REJECT", f"{symbol}: quantity=0")
                    continue
                proposal = Proposal(symbol, action, qty, today, assessment.reason)
                approved, reason = self.risk.check(proposal, bar, p, marks, today)
                self.log(today, "RiskEngine", "PASS" if approved else "REJECT",
                         f"{symbol} {action} {qty}: {reason}")
                if approved:
                    # A limit order can fail to fill if the next session gaps beyond 0.8% (buys)
                    # or 2% (sells). No filling at a known historical closing price.
                    limit_price = bar.close * (1.008 if action == "BUY" else .98)
                    order_id = f"sim:{today.isoformat()}:{symbol}:{action}"
                    self.pending.append(PendingOrder(proposal, order_id, limit_price))
            self.previous_marks = marks
        return self.report(data)

    def report(self, data: dict[date, dict[str, Bar]]) -> dict:
        p = self.portfolio
        first_equity = self.curve[0]["equity"]
        peak = first_equity
        drawdowns = []
        for point in self.curve:
            peak = max(peak, point["equity"])
            drawdowns.append((peak - point["equity"]) / peak if peak else 0)
        return {
            "mode": self.data_mode,
            "note": "Research simulation, not AI, live broker, a forecast or a validated strategy. Price-only, excludes corporate actions and dividends.",
            "initial_equity": first_equity,
            "final_equity": round(p.last_equity, 2),
            "return_pct": round((p.last_equity / first_equity - 1) * 100, 3),
            "max_observed_drawdown_pct": round(max(drawdowns, default=0) * 100, 3),
            "fees_paid": round(p.fees, 2),
            "trades": len(p.fills),
            "realized_pnl": round(p.realized_pnl, 2),
            "positions": {s: {"qty": x.quantity, "average_price": round(x.average_price, 4)}
                          for s, x in p.positions.items()},
            "curve": self.curve,
            "fills": [{"date": f.date.isoformat(), "symbol": f.symbol, "side": f.side,
                       "qty": f.quantity, "price": f.price, "fee": f.fee,
                       "order_id": f.order_id} for f in p.fills],
            "audits": [{"date": a.date.isoformat(), "actor": a.actor, "kind": a.kind,
                        "message": a.message} for a in self.audits],
            "unexecuted_orders": [x.order_id for x in self.pending],
            "news_status": self.news.status(),
            "risk_halt": {"drawdown_latched": self.risk.drawdown_latched,
                          "latched_on": self.risk.drawdown_latched_on.isoformat() if self.risk.drawdown_latched_on else None,
                          "no_automatic_restart": True},
            "expected_round_trip_cost_ceiling_pct": self.policy.max_estimated_round_trip_cost_fraction * 100,
            "assumed_commission_per_fill": self.policy.assumed_fee,
            "assumed_slippage_bps_per_fill": self.policy.assumed_slippage_bps,
            "blocked_buy_proposals_for_costs": sum(a.kind == "REJECT" and "Estimated round-trip costs" in a.message
                                                   for a in self.audits),

        }
