import tempfile
import unittest
from datetime import date, timedelta
from ai_trading_fleet.data import synthetic_data
from ai_trading_fleet.models import Bar, Portfolio, Proposal, PendingOrder
from ai_trading_fleet.risk import RiskEngine, RiskPolicy
from ai_trading_fleet.execution import SimulatedBroker
from ai_trading_fleet.engine import TradingFleet

D = date(2026, 1, 12)
BAR = Bar(D, "DEMO_WORLD", 100, 101, 99, 100, 10000, 15)

class RiskTests(unittest.TestCase):
    def setUp(self):
        self.risk = RiskEngine(RiskPolicy())
        self.p = Portfolio()

    def test_reject_unknown_symbol(self):
        proposal = Proposal("UNKNOWN", "BUY", 1, D, "x")
        ok, _ = self.risk.check(proposal, BAR, self.p, {"UNKNOWN": 100}, D)
        self.assertFalse(ok)

    def test_reject_stale_quote(self):
        proposal = Proposal("DEMO_WORLD", "BUY", 1, D-timedelta(days=1), "x")
        ok, _ = self.risk.check(proposal, BAR, self.p, {"DEMO_WORLD": 100}, D)
        self.assertFalse(ok)

    def test_reject_large_position(self):
        proposal = Proposal("DEMO_WORLD", "BUY", 30, D, "x")
        ok, _ = self.risk.check(proposal, BAR, self.p, {"DEMO_WORLD": 100}, D)
        self.assertFalse(ok)

    def test_kill_switch(self):
        risk = RiskEngine(RiskPolicy(kill_switch=True))
        ok, reason = risk.check(Proposal("DEMO_WORLD", "BUY", 1, D, "x"), BAR,
                                self.p, {"DEMO_WORLD": 100}, D)
        self.assertFalse(ok)
        self.assertIn("KILL", reason)

    def test_deterministic_sizing(self):
        self.assertEqual(self.risk.size_buy(100, 5000, 5000, 0.04), 3)
        self.assertEqual(self.risk.size_buy(30, 1000, 1000, 0.04), 2)

    def test_no_same_bar_execution(self):
        broker = SimulatedBroker()
        proposal = Proposal("DEMO_WORLD", "BUY", 1, D, "x")
        order = PendingOrder(proposal, "id1", 110)
        fill, _ = broker.execute(order, BAR, self.p, self.risk, {"DEMO_WORLD": 100})
        self.assertIsNone(fill)

    def test_execution_rechecks_gap(self):
        broker = SimulatedBroker()
        self.p = Portfolio(cash=5000, peak_equity=5000, day_start_equity=5000, week_start_equity=5000)
        proposal = Proposal("DEMO_WORLD", "BUY", 3, D, "x")
        order = PendingOrder(proposal, "id1", 200)
        future = Bar(D + timedelta(days=1), "DEMO_WORLD", 160, 162, 159, 161, 10000)
        fill, reason = broker.execute(order, future, self.p, self.risk, {"DEMO_WORLD": 160})
        self.assertIsNone(fill)
        self.assertIn("risk budget", reason)

    def test_idempotent_fill(self):
        broker = SimulatedBroker()
        self.p = Portfolio(cash=5000, peak_equity=5000, day_start_equity=5000, week_start_equity=5000)
        proposal = Proposal("DEMO_WORLD", "BUY", 1, D, "x")
        order = PendingOrder(proposal, "id1", 110)
        future = Bar(D + timedelta(days=1), "DEMO_WORLD", 100, 102, 99, 101, 10000)
        fill, _ = broker.execute(order, future, self.p, self.risk, {"DEMO_WORLD": 100})
        self.assertIsNotNone(fill)
        duplicate, reason = broker.execute(order, future, self.p, self.risk, {"DEMO_WORLD": 100})
        self.assertIsNone(duplicate)
        self.assertIn("Duplicate", reason)

    def test_no_network_in_demo_run(self):
        data = synthetic_data()
        report = TradingFleet().run(data)
        self.assertEqual(report["mode"], "OFFLINE_SYNTHETIC_SIMULATION_ONLY")
        self.assertEqual(report["initial_equity"], 1000.0)
        self.assertGreater(len(report["curve"]), 100)
        for f in report["fills"]:
            signal_day = date.fromisoformat(f["order_id"].split(":")[1])
            self.assertGreater(date.fromisoformat(f["date"]), signal_day)

if __name__ == "__main__":
    unittest.main()

class PolicyRegressionTests(unittest.TestCase):
    def test_sell_allowed_with_kill_switch_for_risk_reduction(self):
        from ai_trading_fleet.models import Position
        p = Portfolio()
        p.positions["DEMO_WORLD"] = Position(2, 100, 96)
        risk = RiskEngine(RiskPolicy(kill_switch=True))
        allowed, reason = risk.check(Proposal("DEMO_WORLD", "SELL", 2, D, "exit"),
                                     BAR, p, {"DEMO_WORLD": 100}, D)
        self.assertTrue(allowed, reason)

    def test_daily_loss_blocks_new_entry(self):
        p = Portfolio(day_start_equity=5000, cash=4900)
        risk = RiskEngine(RiskPolicy())
        allowed, reason = risk.check(Proposal("DEMO_WORLD", "BUY", 1, D, "x"),
                                     BAR, p, {"DEMO_WORLD": 100}, D)
        self.assertFalse(allowed)
        self.assertIn("Daily loss", reason)

    def test_execution_respects_daily_fill_limit(self):
        p = Portfolio(cash=5000, peak_equity=5000, day_start_equity=5000, week_start_equity=5000)
        tomorrow = D + timedelta(days=1)
        p.traded_date_count[tomorrow] = 2
        b = Bar(tomorrow, "DEMO_WORLD", 100, 102, 99, 101, 10000)
        broker = SimulatedBroker()
        order = PendingOrder(Proposal("DEMO_WORLD", "BUY", 1, D, "x"), "test", 110)
        fill, reason = broker.execute(order, b, p, RiskEngine(RiskPolicy()), {"DEMO_WORLD": 100})
        self.assertIsNone(fill)
        self.assertEqual(reason, "Trade limit")
