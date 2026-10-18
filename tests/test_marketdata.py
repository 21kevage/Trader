"""All historical-data tests run offline with explicit mock CSV bars."""
import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from ai_trading_fleet.marketdata import (MarketDataError, RESEARCH_UNIVERSE,
                                         read_snapshot, write_snapshot)
from ai_trading_fleet.evaluation import buy_and_hold, summarize_holdout
from ai_trading_fleet.cli import main


def fixture_rows(count=120):
    rows = []
    i = 0
    day = date(2025, 1, 1)
    while i < count:
        if day.weekday() < 5:
            for j, symbol in enumerate(RESEARCH_UNIVERSE):
                price = 25 + j*3 + i*.02
                rows.append({"date": day.isoformat(), "symbol": symbol,
                             "open": price, "high": price*1.006, "low": price*.993,
                             "close": price*1.002, "volume": 10000, "spread_bps": 15})
            i += 1
        day += timedelta(days=1)
    return rows


class HistoricalDataTests(unittest.TestCase):
    def test_zero_volume_is_preserved_but_never_traded(self):
        from ai_trading_fleet.models import PendingOrder, Proposal, Bar
        from ai_trading_fleet.execution import SimulatedBroker
        from ai_trading_fleet.risk import RiskPolicy
        from ai_trading_fleet.engine import TradingFleet
        rows = fixture_rows()
        # Some vendors report a daily price bar without measurable exchange volume.
        for row in rows:
            if row["symbol"] == "EUNL.DE" and row["date"] == "2025-03-03":
                row["volume"] = 0
        with tempfile.TemporaryDirectory() as temp:
            csv_file, manifest_file = write_snapshot(rows, temp,
                start=date(2025,1,1), end=date(2025,7,1),
                received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})
            dataset, meta = read_snapshot(csv_file, manifest_file)
            self.assertEqual(meta["zero_volume_rows"]["EUNL.DE"], 1)
            self.assertEqual(dataset[date(2025,3,3)]["EUNL.DE"].volume, 0)
            policy = RiskPolicy(permitted_symbols=frozenset(RESEARCH_UNIVERSE))
            report = TradingFleet(policy, data_mode="OFFLINE_HISTORICAL_BACKTEST_ONLY").run(dataset)
            self.assertTrue(any(a["actor"] == "MarketData" and a["kind"] == "SKIP"
                                for a in report["audits"]))
            # A zero-volume next-open bar cannot result in a simulated fill.
            broker = SimulatedBroker()
            from ai_trading_fleet.models import Portfolio
            zero_bar = dataset[date(2025,3,3)]["EUNL.DE"]
            proposal = Proposal("EUNL.DE", "BUY", 1, date(2025,2,28), "fixture")
            order = PendingOrder(proposal, "test:zero", 9999)
            fill, why = broker.execute(order, zero_bar, Portfolio(), TradingFleet(policy).risk, {"EUNL.DE": zero_bar.open})
            self.assertIsNone(fill)
            self.assertIn("Illiquid", why)

    def test_negative_and_fractional_volume_still_rejected(self):
        for bad in (-1, 1.25, float("nan")):
            rows = fixture_rows()
            rows[0]["volume"] = bad
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(MarketDataError):
                    write_snapshot(rows, temp, start=date(2025,1,1), end=date(2025,7,1),
                        received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})

    def test_zero_volume_baseline_skips_untradable_open(self):
        from ai_trading_fleet.models import Bar
        data = {
            date(2025,1,1): {"A": Bar(date(2025,1,1),"A",10,10,10,10,100)},
            date(2025,1,2): {"A": Bar(date(2025,1,2),"A",11,11,11,11,0)},
            date(2025,1,3): {"A": Bar(date(2025,1,3),"A",12,12,12,12,100)},
        }
        self.assertEqual(buy_and_hold(data,"A",capital=100,fee=1)["quantity"],8)
        data[date(2025,1,3)]["A"] = Bar(date(2025,1,3),"A",12,12,12,12,0)
        with self.assertRaisesRegex(ValueError,"No tradable"):
            buy_and_hold(data,"A",capital=100,fee=1)

    def test_snapshot_roundtrip_with_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_file, manifest = write_snapshot(fixture_rows(), root,
                start=date(2025,1,1), end=date(2025,7,1),
                received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})
            dataset, metadata = read_snapshot(csv_file, manifest)
            self.assertEqual(sum(map(len, dataset.values())), 240)
            self.assertEqual(metadata["rows"], 240)
            with self.assertRaises(MarketDataError):
                write_snapshot(fixture_rows(), root, start=date(2025,1,1),
                    end=date(2025,7,1), received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})

    def test_reject_tampered_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_file, manifest = write_snapshot(fixture_rows(), temp,
                start=date(2025,1,1), end=date(2025,7,1),
                received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})
            csv_file.write_bytes(csv_file.read_bytes().replace(b"25.0", b"26.0", 1))
            with self.assertRaisesRegex(MarketDataError, "verification failed"):
                read_snapshot(csv_file, manifest)

    def test_reject_non_eur(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(MarketDataError, "EUR"):
                write_snapshot(fixture_rows(), temp, start=date(2025,1,1),
                    end=date(2025,7,1), received_currencies={s:"USD" for s in RESEARCH_UNIVERSE})

    def test_reject_split_and_gaps(self):
        rows = fixture_rows()
        rows[120]["close"] *= 2
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(MarketDataError):
                write_snapshot(rows, temp, start=date(2025,1,1), end=date(2025,7,1),
                    received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})

    def test_reject_missing_symbol(self):
        rows = [r for r in fixture_rows() if r["symbol"] == "EUNL.DE"]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(MarketDataError, "Too few"):
                write_snapshot(rows, temp, start=date(2025,1,1), end=date(2025,7,1),
                    received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})

    def test_offline_backtest_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_file, manifest = write_snapshot(fixture_rows(), root / "snapshot",
                start=date(2025,1,1), end=date(2025,7,1),
                received_currencies={s:"EUR" for s in RESEARCH_UNIVERSE})
            out = root / "report.json"
            main(["backtest", "--csv", str(csv_file), "--manifest", str(manifest),
                  "--out", str(out), "--holdout-start", "2025-05-01"])
            report = json.loads(out.read_text())
            self.assertEqual(report["mode"], "OFFLINE_HISTORICAL_BACKTEST_ONLY")
            self.assertEqual(report["initial_equity"], 1000)
            self.assertIn("IS3N.DE", report["comparisons"])
            self.assertEqual(report["holdout"]["start"], "2025-05-01")

    def test_benchmark_next_open_and_holdout_bounds(self):
        from ai_trading_fleet.models import Bar
        data = {date(2025,1,1):{"A":Bar(date(2025,1,1),"A",1,2,1,2,100)},
                date(2025,1,2):{"A":Bar(date(2025,1,2),"A",10,11,10,10,100)}}
        value = buy_and_hold(data, "A", capital=100, fee=1)
        self.assertEqual(value["quantity"], 9)
        self.assertEqual(value["final_equity"], 99)
        with self.assertRaises(ValueError):
            summarize_holdout([{"date":"2025-01-01", "equity":1000}], date(2025,1,2))

if __name__ == "__main__":
    unittest.main()
