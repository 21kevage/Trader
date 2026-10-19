"""v0.7 deterministic mock and data-leakage / security regression suite."""
from __future__ import annotations
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from ai_trading_fleet.advisory import validate_research_note
from ai_trading_fleet.models import Bar
from ai_trading_fleet.shadow_research import (
    MOCK_SOURCE, make_mock_note, shadow_preview,
    render_mobile_html, render_github_summary,
)


def fixture(days: int = 165) -> dict:
    data = {}
    base = date(2025, 1, 2)
    cursor = base
    i = 0
    while len(data) < days:
        if cursor.weekday() < 5:
            row = {}
            for symbol, factor in (("EUNL.DE", 1.0), ("IS3N.DE", 0.67)):
                close = round((30 + i*0.11 + 0.5 * ((i % 11) - 5))*factor, 4)
                row[symbol] = Bar(cursor, symbol, close, close*1.002, close*.998,
                                  close, 900000, 15)
            data[cursor] = row
            i += 1
        cursor += timedelta(days=1)
    return data


class TestMockShadow(unittest.TestCase):
    def test_all_outputs_prominently_labeled_and_no_orders(self):
        r = shadow_preview(fixture(), last_sessions=6)
        self.assertTrue(r["not_real_ai"])
        self.assertEqual(r["real_llm_calls"], 0)
        self.assertTrue(r["not_a_trading_backtest"])
        self.assertFalse(r["broker_connected"])
        self.assertFalse(r["order_submission_possible"])
        self.assertEqual(r["actual_orders"], 0)
        self.assertEqual(r["capital_at_risk_eur"], 0)
        self.assertEqual(r["capital_reference_eur"], 1000)
        self.assertEqual(r["summary"]["mock_notes"], 12)
        self.assertEqual(len(r["decisions"]), 12)
        for note in r["decisions"]:
            self.assertEqual(note["mock_source"], MOCK_SOURCE)
            self.assertEqual(note["order_executed"], False)
            self.assertEqual(note["mock_note"]["confidence"], 0.5)

    def test_future_close_does_not_change_past_mock_or_rule(self):
        dataset = fixture()
        chosen = sorted(dataset)[-20]
        earlier = make_mock_note(dataset, "EUNL.DE", chosen)
        report = shadow_preview(dataset, last_sessions=12)
        changed = fixture()
        for day in sorted(changed):
            if day > chosen:
                original = changed[day]["EUNL.DE"]
                close = original.close * 1.5
                changed[day]["EUNL.DE"] = Bar(day, original.symbol, close,
                    close*1.002, close*.998, close, original.volume, original.spread_bps)
        later = make_mock_note(changed, "EUNL.DE", chosen)
        self.assertEqual(earlier, later)
        altered = shadow_preview(changed, last_sessions=12)
        by_day = lambda data: {(x['asof'],x['symbol']):(x['mock_stance'],x['rule_indicator_stance'],x['observation_sha256'])
                               for x in data['decisions'] if x['asof'] <= chosen.isoformat()}
        self.assertEqual(by_day(report), by_day(altered))

    def test_all_mock_research_notes_pass_existing_allowlist_boundary(self):
        dataset = fixture()
        r = shadow_preview(dataset, last_sessions=3)
        for d in r["decisions"]:
            valid = validate_research_note(d["mock_note"],
                asof=date.fromisoformat(d["asof"]),
                allowed_symbols=frozenset({"EUNL.DE", "IS3N.DE"}))
            self.assertFalse(valid["actionable_order"])

    def test_malicious_additional_trade_field_fails_closed(self):
        dataset = fixture()
        day = sorted(dataset)[-5]
        note = make_mock_note(dataset, "EUNL.DE", day)["note"]
        note["BUY"] = {"quantity": 1000}
        with self.assertRaisesRegex(ValueError, "Unexpected research"):
            validate_research_note(note, asof=day, allowed_symbols=frozenset({"EUNL.DE"}))

    def test_bogus_and_demo_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "allowlist"):
            make_mock_note(fixture(), "DEMO_WORLD", sorted(fixture())[-2])

    def test_no_future_session_evaluation_leak_at_latest_date(self):
        r = shadow_preview(fixture(), last_sessions=4, step_sessions=1, horizon_sessions=10)
        latest = [x for x in r["decisions"] if x["asof"] == r["asof_last_available"]]
        self.assertEqual(len(latest), 2)
        self.assertTrue(all(x["later_observation"]["status"] == "PENDING" for x in latest))
        self.assertTrue(all(x["later_observation"]["price_change_pct"] is None for x in latest))
        self.assertGreater(r["summary"]["pending_later_observations"], 0)

    def test_html_self_contained_no_script_and_escaped(self):
        report = shadow_preview(fixture(), last_sessions=3)
        report["decisions"][0]["asof"] = '<script>alert("x")</script>'
        text = render_mobile_html(report)
        self.assertIn("SIMULIERTE KI-ANTWORTEN", text)
        self.assertNotIn('<script>alert', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertNotIn('<script', text)
        self.assertNotIn('<iframe', text)
        self.assertNotIn('http:', text)
        self.assertNotIn('https:', text)
        self.assertIn('viewport', text)

    def test_reports_refuse_incorrect_mode(self):
        with self.assertRaises(ValueError):
            render_mobile_html({"mode":"LIVE_BROKER"})
        with self.assertRaises(ValueError):
            render_github_summary({"mode":"LIVE_BROKER"})

    def test_controls_reject_invalid_input(self):
        for options in ({"last_sessions": 100},{"step_sessions": 0},
                        {"horizon_sessions":21},{"last_sessions": True},
                        {"capital":1100}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                shadow_preview(fixture(), **options)

    def test_mock_never_uses_paid_api(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY":"accidentally_present"}):
            report = shadow_preview(fixture(), last_sessions=2)
            self.assertEqual(report["real_llm_calls"],0)
            self.assertEqual(report["actual_orders"],0)

    def test_github_summary_clear_and_no_live_claim(self):
        report = shadow_preview(fixture(), last_sessions=2)
        rendered = render_github_summary(report)
        self.assertIn("KEINE ECHTE KI", rendered)
        self.assertIn("KEINE ORDER", rendered)
        self.assertIn("v07-shadow-report", rendered)

    def test_cli_generates_report_html_and_github_summary_offline(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from ai_trading_fleet.cli import main
        demo = fixture()
        with tempfile.TemporaryDirectory() as folder, patch(
            "ai_trading_fleet.marketdata.read_snapshot",
            return_value=(demo, {"sha256": "test-snapshot", "source": "synthetic-fixture"})
        ) as reader:
            base = Path(folder)
            with redirect_stdout(StringIO()):
                main(["shadow-demo", "--csv", str(base/"input.csv"),
                      "--manifest", str(base/"manifest.json"),
                      "--last-sessions", "2", "--out", str(base/"v07.json"),
                      "--html", str(base/"report.html"),
                      "--summary", str(base/"summary.md")])
            reader.assert_called_once()
            saved = json.loads((base/"v07.json").read_text())
            self.assertTrue(saved["not_real_ai"])
            self.assertEqual(saved["snapshot_sha256"], "test-snapshot")
            self.assertIn("SIMULIERTE KI-ANTWORTEN", (base/"report.html").read_text())
            self.assertIn("KEINE ORDER", (base/"summary.md").read_text())

    def test_does_not_modify_source_market_data(self):
        original = fixture()
        before = {d:{s:b.close for s,b in m.items()} for d,m in original.items()}
        shadow_preview(original, last_sessions=5)
        after = {d:{s:b.close for s,b in m.items()} for d,m in original.items()}
        self.assertEqual(before,after)


if __name__ == "__main__":
    unittest.main()
