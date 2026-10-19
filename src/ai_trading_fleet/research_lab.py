"""Offline-only, fixed-hypothesis research comparisons.

This module has no trading API or LLM hook. Never reuse its fractional fills
as evidence that a real broker can execute fractional ETF shares.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from math import floor, isfinite
from typing import Literal

from .models import Bar
from .risk import RiskPolicy

Strategy = Literal["swing", "monthly_momentum", "one_shot_stop"]


@dataclass(frozen=True)
class FeeScenario:
    name: str
    commission: float
    fractional: bool = False
    spread_bps: float = 15.0
    slippage_bps: float = 5.0

    def __post_init__(self):
        if any(not isfinite(n) or n < 0 for n in (self.commission, self.spread_bps, self.slippage_bps)):
            raise ValueError("Invalid cost scenario")


SCENARIOS = (
    FeeScenario("fixed_1_25_whole", 1.25),
    FeeScenario("hypothetical_0_25_whole", .25),
    FeeScenario("hypothetical_0_25_fractional", .25, fractional=True),
    FeeScenario("zero_fee_fractional_sensitivity_ONLY", 0.0, fractional=True),
)
STRATEGIES: tuple[Strategy, ...] = ("swing", "monthly_momentum", "one_shot_stop")
STOP_DISTANCE = .04


@dataclass
class _Holding:
    qty: float
    paid: float
    stop: float


@dataclass(frozen=True)
class _Order:
    signal_date: date
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float
    reason: str


def _size(price: float, equity: float, cash: float, policy: RiskPolicy, scenario: FeeScenario) -> float:
    """Same 0.25% stop-risk and 20% position ceilings as v0.3."""
    effective = price * (1 + (scenario.slippage_bps + scenario.spread_bps / 2) / 10000)
    allowance = min(
        equity * policy.max_trade_risk_fraction / (effective * STOP_DISTANCE * 1.025),
        equity * policy.max_position_fraction / effective,
        max(0, cash - scenario.commission) / effective,
    )
    if allowance <= 0:
        return 0.0
    if scenario.fractional:
        return floor((allowance + 1e-9) * 1000) / 1000
    return float(floor(allowance + 1e-9))


def _valid_daily(data: dict[date, dict[str, Bar]]) -> tuple[list[date], tuple[str, ...]]:
    if not data:
        raise ValueError("No market data")
    days = sorted(data)
    symbols = tuple(sorted({symbol for daily in data.values() for symbol in daily}))
    if len(days) < 90 or not symbols:
        raise ValueError("At least 90 sessions and one symbol required")
    for day, daily in data.items():
        for sym, b in daily.items():
            if b.date != day or b.symbol != sym or (not all(isfinite(x) and x > 0 for x in
                    (b.open, b.high, b.low, b.close))) or b.volume < 0:
                raise ValueError("Invalid research bar")
            if not isfinite(b.dividend) or b.dividend < 0:
                raise ValueError("Invalid dividend event")
            if b.low > min(b.open, b.close) or b.high < max(b.open, b.close):
                raise ValueError("Invalid research OHLC ordering")
    return days, symbols


def _signal(strategy: Strategy, closes: list[float], month_open: bool) -> tuple[bool, bool]:
    """Only past/current CLOSEs are used; orders must wait for next session."""
    if len(closes) < 61:
        return False, False
    if strategy == "one_shot_stop":
        return True, False
    if strategy == "swing":
        fast = sum(closes[-10:]) / 10
        slow = sum(closes[-30:]) / 30
        mom = closes[-1] / closes[-21] - 1
        return fast > slow * 1.002 and mom > .005, fast < slow or mom < -.02
    if strategy == "monthly_momentum":
        if not month_open:
            return False, False
        mom = closes[-1] / closes[-61] - 1
        mean = sum(closes[-60:]) / 60
        return mom > .02 and closes[-1] > mean, mom < 0 or closes[-1] < mean
    raise ValueError("Unknown strategy")


def run_scenario(data: dict[date, dict[str, Bar]], *, strategy: Strategy,
                 costs: FeeScenario, capital: float = 1000.0,
                 holdout_start: date | None = None,
                 policy: RiskPolicy | None = None,
                 trade_start: date | None = None) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy")
    if not isfinite(capital) or capital <= 0:
        raise ValueError("Invalid capital")
    policy = policy or RiskPolicy()
    if policy.kill_switch:
        raise ValueError("Research comparison cannot start with kill switch enabled")
    days, symbols = _valid_daily(data)
    if len(symbols) > 3:
        raise ValueError("Research universe restricted to at most three assets")
    if holdout_start is not None and not days[60] < holdout_start < days[-1]:
        raise ValueError("Holdout outside study interval")
    if trade_start is not None:
        if holdout_start is not None:
            raise ValueError("Separate forward test cannot request descriptive holdout")
        if not days[60] <= trade_start <= days[-30]:
            raise ValueError("Forward trading needs 60 warm-up sessions and 30 evaluation sessions")
    cash = capital
    holdings: dict[str, _Holding] = {}
    histories: dict[str, list[float]] = defaultdict(list)
    last_known: dict[str, float] = {}
    open_orders: list[_Order] = []
    tried_once: set[str] = set()  # one_shot_stop never re-enters a symbol
    fills: list[dict] = []
    rejected: Counter[str] = Counter()
    fee_total = 0.0
    dividends_credited = 0.0
    previous_equity = capital
    peak = capital
    max_dd = 0.0
    latch_on: date | None = None
    prev_month: tuple[int, int] | None = None
    week_key = None
    week_start = capital
    curve: list[dict] = []
    exposure_sum = 0.0
    last_bought: dict[str, date] = {}

    for day in days:
        daily = data[day]
        # The chronological test may read prior closes to warm indicators,
        # but must never trade, earn dividends, or change cash before trade_start.
        if trade_start is not None and day < trade_start:
            for symbol, bar in daily.items():
                histories[symbol].append(bar.close)
                last_known[symbol] = bar.close
            prev_month = (day.year, day.month)
            continue
        # Entitlement belongs to shares owned before ex-date session OPEN.
        # Payment is credited on ex-date as an explicit research approximation.
        for symbol, position in holdings.items():
            bar = daily.get(symbol)
            if bar is not None and bar.dividend:
                credited = position.qty * bar.dividend
                cash += credited
                dividends_credited += credited
        open_marks = dict(last_known)
        open_marks.update({s: b.open for s, b in daily.items()})
        day_start = previous_equity
        wk = day.isocalendar()[:2]
        if wk != week_key:
            week_start = previous_equity
            week_key = wk
        month = (day.year, day.month)
        is_month_open = month != prev_month
        prev_month = month
        fills_today = 0

        # Execute yesterday's proposals at today's OPEN; no same-bar lookahead.
        for order in sorted(open_orders, key=lambda o: o.side != "SELL"):
            bar = daily.get(order.symbol)
            if bar is None or bar.volume <= 0:
                rejected["missing_or_zero_volume_execution"] += 1
                continue
            if bar.spread_bps < 0 or bar.spread_bps > policy.max_spread_bps:
                rejected["invalid_spread_execution"] += 1
                continue
            direction = 1 if order.side == "BUY" else -1
            price = bar.open * (1 + direction * (costs.slippage_bps + costs.spread_bps / 2) / 10000)
            if price <= 0 or not isfinite(price):
                rejected["invalid_execution_price"] += 1
                continue
            shares = order.qty
            if order.side == "SELL":
                pos = holdings.get(order.symbol)
                if not pos:
                    rejected["sell_without_position"] += 1
                    continue
                shares = pos.qty
                cash += price * shares - costs.commission
                fee_total += costs.commission
                del holdings[order.symbol]
                fills.append({"date": day.isoformat(), "signal_date": order.signal_date.isoformat(),
                              "symbol": order.symbol, "side": "SELL", "quantity": round(shares, 3),
                              "price": round(price, 4), "fee": costs.commission, "reason": order.reason})
                fills_today += 1
                continue

            if latch_on or fills_today >= policy.max_trades_per_day:
                rejected["risk_halt_or_daily_limit"] += 1
                continue
            if (order.symbol in holdings or len(holdings) >= policy.max_open_positions or
                    (order.symbol in last_bought and (day - last_bought[order.symbol]).days < policy.cooldown_days)):
                rejected["existing_position_or_open_limit"] += 1
                continue
            pre_equity = cash + sum(h.qty * open_marks.get(s, h.paid) for s, h in holdings.items())
            gross = sum(h.qty * open_marks.get(s, h.paid) for s, h in holdings.items())
            notional = shares * price
            if (pre_equity <= 0 or pre_equity < day_start * (1 - policy.daily_loss_circuit_breaker)
                    or pre_equity < week_start * (1 - policy.weekly_loss_circuit_breaker)
                    or pre_equity < peak * (1 - policy.equity_drawdown_circuit_breaker)
                    or notional > pre_equity * policy.max_position_fraction + 1e-8
                    or notional * STOP_DISTANCE > pre_equity * policy.max_trade_risk_fraction + 1e-8
                    or gross + notional > pre_equity * policy.max_gross_exposure_fraction + 1e-8
                    or notional + costs.commission > cash + 1e-8):
                rejected["risk_or_cash_execution"] += 1
                continue
            # Flat fees apply per order, not per (possibly fractional) share.
            expected_fraction = (2 * costs.commission + notional *
                                 (costs.spread_bps + 2 * costs.slippage_bps) / 10000) / notional
            if expected_fraction > policy.max_estimated_round_trip_cost_fraction + 1e-9:
                rejected["cost_execution"] += 1
                continue
            cash -= notional + costs.commission
            fee_total += costs.commission
            holdings[order.symbol] = _Holding(shares, price, price * (1 - STOP_DISTANCE))
            tried_once.add(order.symbol)
            last_bought[order.symbol] = day
            fills.append({"date": day.isoformat(), "signal_date": order.signal_date.isoformat(),
                          "symbol": order.symbol, "side": "BUY", "quantity": round(shares, 3),
                          "price": round(price, 4), "fee": costs.commission, "reason": order.reason})
            fills_today += 1
        open_orders = []

        for symbol, bar in daily.items():
            histories[symbol].append(bar.close)
            last_known[symbol] = bar.close
        equity = cash + sum(h.qty * last_known.get(s, h.paid) for s, h in holdings.items())
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        if latch_on is None and (peak - equity) / peak >= policy.equity_drawdown_circuit_breaker - 1e-10:
            latch_on = day
        curve.append({"date": day.isoformat(), "equity": round(equity, 2)})
        gross_close = sum(h.qty * last_known.get(s, h.paid) for s, h in holdings.items())
        exposure_sum += gross_close / equity if equity > 0 else 0
        previous_equity = equity

        for symbol in symbols:
            bar = daily.get(symbol)
            if bar is None or bar.volume <= 0:
                continue
            closes = histories[symbol]
            buy, sell = _signal(strategy, closes, is_month_open)
            pos = holdings.get(symbol)
            if pos:
                if bar.close <= pos.stop or sell:
                    open_orders.append(_Order(day, symbol, "SELL", pos.qty,
                                              "close_stop" if bar.close <= pos.stop else "strategy_exit"))
                continue
            if latch_on or len(holdings) >= policy.max_open_positions:
                continue
            if symbol in last_bought and (day - last_bought[symbol]).days < policy.cooldown_days:
                rejected["cooldown"] += 1
                continue
            if strategy == "one_shot_stop" and symbol in tried_once:
                continue
            if not buy:
                continue
            if bar.spread_bps < 0 or bar.spread_bps > policy.max_spread_bps:
                rejected["invalid_spread_signal"] += 1
                continue
            if (equity < day_start * (1 - policy.daily_loss_circuit_breaker)
                    or equity < week_start * (1 - policy.weekly_loss_circuit_breaker)):
                rejected["daily_or_weekly_loss"] += 1
                continue
            qty = _size(bar.close, equity, cash, policy, costs)
            if qty == 0:
                rejected["quantity_zero"] += 1
                continue
            nominal = qty * bar.close
            estimated = (2 * costs.commission + nominal *
                         (costs.spread_bps + 2 * costs.slippage_bps) / 10000) / nominal
            if estimated > policy.max_estimated_round_trip_cost_fraction + 1e-9:
                rejected["cost_signal"] += 1
                continue
            # No pyramiding, at most one queued order per symbol.
            if any(o.symbol == symbol for o in open_orders):
                rejected["duplicate_pending"] += 1
                continue
            open_orders.append(_Order(day, symbol, "BUY", qty, "strategy_entry"))

    if not curve:
        raise ValueError("Empty active trading period")
    final_equity = curve[-1]["equity"]
    holdout = None
    if holdout_start:
        before = [point for point in curve if point["date"] < holdout_start.isoformat()]
        after = [point for point in curve if point["date"] >= holdout_start.isoformat()]
        if len(before) < 60 or len(after) < 30:
            raise ValueError("Insufficient holdout sessions")
        reference = before[-1]["equity"]
        holdout = {"start": holdout_start.isoformat(), "return_pct": round(100 * (final_equity / reference - 1), 3),
                   "sessions": len(after), "descriptive_only": True}
    return {
        "strategy": strategy, "cost_scenario": costs.name, "fractional_shares_simulated": costs.fractional,
        "not_a_broker_price_schedule": True, "initial_equity": capital,
        "final_equity": round(final_equity, 2), "return_pct": round(100 * (final_equity / capital - 1), 3),
        "max_drawdown_pct": round(100 * max_dd, 3),
        "average_gross_exposure_pct": round(100 * exposure_sum / len(curve), 2),
        "dividends_credited_eur": round(dividends_credited, 2),
        "trade_start": trade_start.isoformat() if trade_start else None,
        "fees_paid_eur": round(fee_total, 2), "executions": len(fills),
        "round_trips_closed": sum(f["side"] == "SELL" for f in fills),
        "zero_trade_diagnostic": "No transactions met all gates" if not fills else None,
        "rejections": dict(sorted(rejected.items())),
        "halted_on": latch_on.isoformat() if latch_on else None,
        "unfilled_end_orders": len(open_orders),
        "open_positions": {s: {"quantity": round(h.qty, 3), "entry": round(h.paid, 4)}
                           for s, h in sorted(holdings.items())},
        "holdout": holdout, "fills": fills, "curve": curve,
    }


def compare(data: dict[date, dict[str, Bar]], *, capital: float = 1000.0,
            holdout_start: date | None = None) -> dict:
    """Predeclared grid; never optimize against holdout results."""
    from .evaluation import capped_buy_and_hold
    dates, symbols = _valid_daily(data)
    runs = [run_scenario(data, strategy=strategy, costs=costs, capital=capital,
                         holdout_start=holdout_start)
            for strategy in STRATEGIES for costs in SCENARIOS]
    baselines = {}
    # Align benchmark start to the common 60-session indicator warm-up.
    aligned_data = {d: data[d] for d in dates[60:]}
    for sym in symbols:
        baseline = capped_buy_and_hold(aligned_data, sym, capital=capital)
        baselines[sym] = baseline
    return {"version": "0.4-research", "mode": "OFFLINE_HISTORICAL_RESEARCH_ONLY",
            "not_investment_advice": True,
            "period": {"first_bar": dates[0].isoformat(), "last_bar": dates[-1].isoformat()},
            "limitations": ["raw OHLC with ex-date dividends if supplied; settlement dates, taxes and reported stock splits not modeled",
                            "assumed spread and slippage, not actual executable quotes",
                            "fractional ETF trading scenarios are hypothetical; broker support unverified",
                            "no taxes, borrow costs, interest, impact, partial fills or intraday stop fills",
                            "stop signal at close, sale attempts at next open; gaps can exceed intended risk",
                            "holdout is descriptive; this is not walk-forward evaluation",
                            "zero-commission case is a sensitivity experiment, not a broker offer"],
            "capital": capital, "symbols": list(symbols),
            "strategies": list(STRATEGIES),
            "cost_scenarios": [{"name": c.name, "commission_eur_per_side": c.commission,
                                "fractional": c.fractional, "spread_bps_assumed": c.spread_bps,
                                "slippage_bps_per_side_assumed": c.slippage_bps}
                               for c in SCENARIOS],
            "passive_exposure_capped_not_risk_matched": baselines,
            "passive_entry_after_warmup_sessions": 60,
            "runs": runs}
