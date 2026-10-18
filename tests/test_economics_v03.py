"""v0.3 policy regressions and cost-aware, non-AI benchmark checks."""
import unittest
from datetime import date, timedelta
from ai_trading_fleet.economics import estimate_round_trip
from ai_trading_fleet.evaluation import capped_buy_and_hold
from ai_trading_fleet.models import Bar, Portfolio, Proposal, Position, PendingOrder
from ai_trading_fleet.engine import TradingFleet
from ai_trading_fleet.risk import RiskEngine, RiskPolicy
from ai_trading_fleet.execution import SimulatedBroker
from ai_trading_fleet.data import synthetic_data

D = date(2026, 1, 12)
BAR = Bar(D, "DEMO_WORLD", 30, 31, 29, 30, 10000, 15)

class EconomicsTests(unittest.TestCase):
    def test_full_round_trip_cost_breakdown(self):
        estimate = estimate_round_trip(30, 2, fee=1.25, spread_bps=15, slippage_bps=5)
        self.assertAlmostEqual(estimate.two_sided_commission, 2.5)
        self.assertAlmostEqual(estimate.assumed_round_trip_spread_slippage, .15)
        self.assertAlmostEqual(estimate.total, 2.65)
        self.assertAlmostEqual(estimate.fraction, 2.65 / 60)

    def test_small_trade_rejected_after_all_other_risk_checks(self):
        policy = RiskPolicy()
        check = RiskEngine(policy)
        proposal = Proposal("DEMO_WORLD", "BUY", 2, D, "positive trend")
        approved, reason = check.check(proposal, BAR, Portfolio(), {"DEMO_WORLD":30}, D)
        self.assertFalse(approved)
        self.assertIn("Estimated round-trip costs", reason)

    def test_sells_still_permitted_during_cost_pause_and_latched_drawdown(self):
        engine = RiskEngine(RiskPolicy(kill_switch=False))
        p = Portfolio()
        p.positions["DEMO_WORLD"] = Position(2, 30, 28.8)
        self.assertTrue(engine.observe_drawdown(940, 1000, D))
        self.assertFalse(engine.observe_drawdown(990, 1000, D + timedelta(days=1)))
        self.assertTrue(engine.drawdown_latched)
        ok, _ = engine.check(Proposal("DEMO_WORLD", "SELL", 2, D, "exit"), BAR, p,
                             {"DEMO_WORLD":30}, D)
        self.assertTrue(ok)
        ok, reason = engine.check(Proposal("DEMO_WORLD", "BUY", 1, D, "enter"), BAR,
                                   Portfolio(), {"DEMO_WORLD":30}, D)
        self.assertFalse(ok)
        self.assertIn("LATCHED", reason)

    def test_execution_side_cost_guard_cannot_be_bypassed(self):
        broker = SimulatedBroker()
        p = Portfolio()
        risk = RiskEngine(RiskPolicy())
        order = PendingOrder(Proposal("DEMO_WORLD", "BUY", 2, D, "test"), "x", 35)
        tomorrow = Bar(D + timedelta(days=1), "DEMO_WORLD", 30, 31, 29, 30, 10000, 15)
        fill, reason = broker.execute(order, tomorrow, p, risk, {"DEMO_WORLD":30})
        self.assertIsNone(fill)
        self.assertIn("Estimated round-trip costs", reason)

    def test_execution_price_includes_half_spread_and_slippage(self):
        broker = SimulatedBroker(fee=0.0, slippage_bps=5)
        risk = RiskEngine(RiskPolicy(assumed_fee=0.0))
        p = Portfolio()
        order = PendingOrder(Proposal("DEMO_WORLD", "BUY", 2, D, "test"), "price", 35)
        tomorrow = Bar(D + timedelta(days=1), "DEMO_WORLD", 30, 31, 29, 30, 10000, 20)
        fill, reason = broker.execute(order, tomorrow, p, risk, {"DEMO_WORLD":30})
        self.assertIsNotNone(fill, reason)
        self.assertAlmostEqual(fill.price, 30 * (1 + 15 / 10000), places=4)

    def test_higher_quote_spread_can_reject_illiquid_buy(self):
        risk = RiskEngine(RiskPolicy())
        bar = Bar(D, "DEMO_WORLD", 30, 31, 29, 30, 10000, 40)
        allowed, reason = risk.check(Proposal("DEMO_WORLD","BUY",2,D,"x"),bar,
                                      Portfolio(),{"DEMO_WORLD":30},D)
        self.assertFalse(allowed)
        self.assertIn("spread", reason)

    def test_zero_trade_portfolio_does_not_fabricate_profit(self):
        report = TradingFleet().run(synthetic_data())
        self.assertEqual(report["initial_equity"], 1000)
        self.assertEqual(report["trades"], 0)
        self.assertEqual(report["fees_paid"], 0)
        self.assertEqual(report["final_equity"], 1000)
        self.assertGreater(report["blocked_buy_proposals_for_costs"], 0)

    def test_capped_benchmark_uses_at_most_20_percent_initial_allocation(self):
        dates = [D, D + timedelta(days=1), D + timedelta(days=2)]
        data = {dates[0]:{"ABC":Bar(dates[0],"ABC",25,25,25,25,10000)},
                dates[1]:{"ABC":Bar(dates[1],"ABC",25,25,25,25,10000)},
                dates[2]:{"ABC":Bar(dates[2],"ABC",30,30,30,30,10000)}}
        bench = capped_buy_and_hold(data,"ABC",capital=1000)
        self.assertEqual(bench["allocation_cap_pct"],20)
        self.assertLessEqual(1000 - bench["initial_cash_uninvested"], 200)
        self.assertGreater(bench["final_equity"],1000)
        self.assertIn("no stop",bench["basis"])

    def test_invalid_economic_values_rejected(self):
        for kw in ({"price":0}, {"quantity":0}, {"fee":-1}, {"spread_bps":-1}):
            values={"price":30,"quantity":1,"fee":1.25,"spread_bps":15,"slippage_bps":5}
            values.update(kw)
            with self.assertRaises(ValueError):
                estimate_round_trip(**values)

if __name__ == "__main__":
    unittest.main()
