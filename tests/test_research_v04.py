"""v0.4 research simulations must fail closed and remain non-executable."""
import math
import unittest
from datetime import date, timedelta
from ai_trading_fleet.models import Bar
from ai_trading_fleet.risk import RiskPolicy
from ai_trading_fleet.research_lab import FeeScenario, _size, _signal, compare, run_scenario


def fixture(n=180, *, price=28.0, rising=True, zero_volume_day=None):
    out = {}
    start = date(2023, 1, 2)
    i = 0
    t = start
    while i < n:
        if t.weekday() <= 4:
            close = price * (1 + (.002 if rising else -.002) * i)
            vol = 0 if zero_volume_day == i else 50000
            out[t] = {"ASSET": Bar(t, "ASSET", close, close * 1.005,
                                    close * .995, close, vol, 15)}
            i += 1
        t += timedelta(days=1)
    return out


class ResearchV04Tests(unittest.TestCase):
    def test_sizing_preserves_original_risk_limit(self):
        risk = RiskPolicy()
        self.assertEqual(_size(30, 1000, 1000, risk, FeeScenario('whole', 1.25)), 2)
        self.assertLessEqual(_size(75,1000,1000,risk,FeeScenario('fraction', .25,True))*75*.04,2.50)
        self.assertEqual(_size(75,1000,1000,risk,FeeScenario('whole', .25)),0)

    def test_fixed_fee_economics_correctly_blocks_all(self):
        result = run_scenario(fixture(), strategy='swing', costs=FeeScenario('fixed',1.25))
        self.assertEqual(result['executions'],0)
        self.assertGreater(result['rejections'].get('cost_signal',0),0)
        self.assertEqual(result['final_equity'],1000)

    def test_low_fee_fractional_is_explicitly_hypothetical(self):
        result=run_scenario(fixture(),strategy='swing',costs=FeeScenario('hypothetical',.25,True))
        self.assertTrue(result['fractional_shares_simulated'])
        self.assertTrue(result['not_a_broker_price_schedule'])
        self.assertGreater(result['executions'],0)
        self.assertLessEqual(result['average_gross_exposure_pct'],20.01)
        buys=[fill for fill in result['fills'] if fill['side']=='BUY']
        self.assertTrue(buys)
        self.assertTrue(all(fill['date']>fill['signal_date'] for fill in buys))
        self.assertTrue(all(fill['quantity']>0 for fill in buys))

    def test_fee_comparison_keeps_policy_fixed(self):
        fixed = run_scenario(fixture(), strategy='swing', costs=FeeScenario('fixed',1.25))
        cheap = run_scenario(fixture(), strategy='swing', costs=FeeScenario('cheap',.25,True))
        self.assertEqual(fixed['initial_equity'],cheap['initial_equity'])
        self.assertEqual(fixed['executions'],0)
        self.assertGreater(cheap['executions'],0)

    def test_only_close_history_generates_signal(self):
        prices=[20 + .06*x for x in range(61)]
        self.assertFalse(_signal('swing',prices[:60],False)[0])
        self.assertTrue(_signal('swing',prices,False)[0])
        self.assertFalse(_signal('monthly_momentum',prices,False)[0])
        self.assertTrue(_signal('monthly_momentum',prices,True)[0])

    def test_one_shot_stop_does_not_reenter_after_exit(self):
        data = fixture(n=150, price=30)
        # After first potential entry, sharp losses should trigger a stop at the close.
        days=list(data)
        for idx in range(73,len(days)):
            date_=days[idx]
            bar=data[date_]['ASSET']
            px=bar.close*.8
            data[date_]={'ASSET':Bar(date_,'ASSET',px,px*1.005,px*.995,px,bar.volume,15)}
        r=run_scenario(data,strategy='one_shot_stop',costs=FeeScenario('cheap',.25,True))
        self.assertLessEqual(len([x for x in r['fills'] if x['side']=='BUY']),1)
        self.assertEqual(r['executions'],len(r['fills']))

    def test_zero_volume_next_open_refuses_pending_buy(self):
        data = fixture(n=150, zero_volume_day=61)
        r=run_scenario(data,strategy='one_shot_stop',costs=FeeScenario('cheap',.25,True))
        self.assertGreaterEqual(r['rejections'].get('missing_or_zero_volume_execution',0),1)
        self.assertFalse(any(x['date']==list(data)[61].isoformat() for x in r['fills']))

    def test_comparison_grid_is_predeclared(self):
        r=compare(fixture(),capital=1000,holdout_start=date(2023,7,10))
        self.assertEqual(r['mode'],'OFFLINE_HISTORICAL_RESEARCH_ONLY')
        self.assertEqual(len(r['runs']),12)
        self.assertEqual(len(r['cost_scenarios']),4)
        self.assertIn('ASSET',r['passive_exposure_capped_not_risk_matched'])
        self.assertTrue(all('holdout' in item for item in r['runs']))
        self.assertTrue(all(item['holdout']['descriptive_only'] for item in r['runs']))

    def test_bad_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            run_scenario(fixture(),strategy='invalid',costs=FeeScenario('cheap',.25,True))
        with self.assertRaises(ValueError):
            run_scenario(fixture(),strategy='swing',costs=FeeScenario('cheap',.25,True),capital=-1)
        with self.assertRaises(ValueError):
            FeeScenario('bad',math.nan)
        with self.assertRaises(ValueError):
            run_scenario(fixture(n=50),strategy='swing',costs=FeeScenario('cheap',.25,True))

    def test_kill_switch_policy_raises(self):
        with self.assertRaisesRegex(ValueError,'kill switch'):
            run_scenario(fixture(),strategy='swing',costs=FeeScenario('cheap',.25,True),policy=RiskPolicy(kill_switch=True))

    def test_offline_cli_on_verified_snapshot(self):
        import json
        import tempfile
        from pathlib import Path
        from ai_trading_fleet.cli import main
        from ai_trading_fleet.marketdata import RESEARCH_UNIVERSE, write_snapshot
        from tests.test_marketdata import fixture_rows
        rows = fixture_rows()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            prices, manifest = write_snapshot(rows, target / "source",
                start=date(2025,1,1), end=date(2025,7,1),
                received_currencies={ticker:"EUR" for ticker in RESEARCH_UNIVERSE})
            report_path = target / "results.json"
            main(["compare-research", "--csv", str(prices), "--manifest", str(manifest),
                  "--holdout-start", "2025-05-01", "--out", str(report_path)])
            report = json.loads(report_path.read_text())
            self.assertEqual(report["mode"], "OFFLINE_HISTORICAL_RESEARCH_ONLY")
            self.assertEqual(len(report["runs"]), 12)
            self.assertTrue(report["snapshot_sha256"])

    def test_gap_can_exceed_planned_loss_so_no_false_guarantee(self):
        data = fixture(n=150, price=28)
        days = list(data)
        for idx in range(72, len(days)):
            day = days[idx]
            before = data[day]['ASSET']
            px = before.close * .75
            data[day] = {'ASSET': Bar(day, 'ASSET', px, px * 1.005,
                                       px * .995, px, before.volume, 15)}
        r = run_scenario(data, strategy='one_shot_stop',
                         costs=FeeScenario('cheap', .25, True))
        self.assertGreaterEqual(r['executions'], 2)
        self.assertLess(r['final_equity'], 997.50)  # loss is worse than planned €2.50
        self.assertTrue(any(f['side'] == 'SELL' and f['reason'] == 'close_stop'
                            for f in r['fills']))

    def test_fractional_units_are_quantized(self):
        r = run_scenario(fixture(), strategy='swing',
                         costs=FeeScenario('hypothesis', .25, True))
        for fill in r['fills']:
            self.assertAlmostEqual(fill['quantity'] * 1000,
                                   round(fill['quantity'] * 1000),places=6)

    def test_no_live_or_broker_import(self):
        import inspect
        import ai_trading_fleet.research_lab as module
        src=inspect.getsource(module)
        self.assertNotIn('ib_insync',src)
        self.assertNotIn('placeOrder(',src)
        self.assertNotIn('requests.',src)


if __name__=='__main__':
    unittest.main()
