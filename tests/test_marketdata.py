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
