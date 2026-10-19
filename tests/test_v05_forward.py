"""v0.5 isolated offline regression suite. No network, keys or brokerage."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from ai_trading_fleet.advisory import validate_research_note
from ai_trading_fleet.forward_research import compare_forward
from ai_trading_fleet.marketdata import (
    FIELDNAMES_V1, MarketDataError, PRICE_BASIS_V1, RESEARCH_UNIVERSE,
    read_snapshot, write_snapshot, fetch_yahoo_snapshot,
)
from ai_trading_fleet.models import Bar
from ai_trading_fleet.research_lab import FeeScenario, run_scenario
from ai_trading_fleet.evaluation import capped_buy_and_hold


def history(n=230, *, dividend_index=None, dividend=0, price=30):
    out = {}
    d = date(2023, 1, 2)
    index = 0
    while index < n:
        if d.weekday() < 5:
            close = price * (1 + 0.001 * index)
            out[d] = {"EUNL.DE": Bar(d, "EUNL.DE", close, close * 1.002,
                         close * .998, close, 50000, 15,
                         dividend if index == dividend_index else 0)}
            index += 1
        d += timedelta(days=1)
    return out


def example_note(asof=date(2025, 6, 2)):
    return {"schema_version": 1, "date": asof.isoformat(), "symbol": "EUNL.DE",
            "stance": "NEUTRAL", "confidence": 0.3,
            "rationale": "Fundamentals mixed; no recommendation or execution.",
            "evidence": [{"date": "2025-05-31", "summary": "Example archived observation"}]}


class DividendResearchTests(unittest.TestCase):
    def test_held_position_earns_dividend_without_new_orders(self):
        basis = history(dividend_index=90, dividend=0)
        earns = history(dividend_index=90, dividend=2.5)
        fee = FeeScenario("hypo", .25, True)
        a = run_scenario(basis, strategy="one_shot_stop", costs=fee)
        b = run_scenario(earns, strategy="one_shot_stop", costs=fee)
        self.assertGreater(b['dividends_credited_eur'], 0)
        self.assertEqual(a['dividends_credited_eur'], 0)
        self.assertAlmostEqual(b['final_equity']-a['final_equity'], b['dividends_credited_eur'], delta=.02)

    def test_no_dividend_if_buy_occurs_on_ex_date_open(self):
        fee = FeeScenario("hypo", .25, True)
        a = run_scenario(history(dividend_index=61, dividend=2),
                         strategy="one_shot_stop", costs=fee)
        self.assertTrue(any(f['side']=='BUY' for f in a['fills']))
        self.assertEqual(a['dividends_credited_eur'], 0)

    def test_dividend_in_passive_benchmark(self):
        data = history(dividend_index=20, dividend=1)
        base = capped_buy_and_hold(history(dividend_index=20), "EUNL.DE")
        new = capped_buy_and_hold(data, "EUNL.DE")
        self.assertGreater(new['dividends_credited_eur'], 0)
        self.assertAlmostEqual(new['final_equity']-base['final_equity'],
                               new['dividends_credited_eur'], delta=.02)

    def test_schema_v2_and_v1_backward_read(self):
        from tests.test_marketdata import fixture_rows
        rows = fixture_rows()
        rows[7]['dividend'] = 0.23
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p, m = write_snapshot(rows, root/'new', start=date(2025,1,1),
                end=date(2025,7,1), received_currencies={s:'EUR' for s in RESEARCH_UNIVERSE})
            bars,meta = read_snapshot(p,m)
            self.assertEqual(meta['schema_version'],2)
            event = rows[7]
            self.assertEqual(bars[date.fromisoformat(event['date'])][event['symbol']].dividend,.23)
            self.assertEqual(sum(meta['dividend_events'].values()),1)
            # Convert to a historically produced v1 snapshot, with fresh SHA.
            old_dir = root/'old';old_dir.mkdir()
            p1=old_dir/'prices.csv'; m1=old_dir/'manifest.json'
            with p1.open('w',encoding='utf-8',newline='') as fh:
                writer=csv.DictWriter(fh,fieldnames=FIELDNAMES_V1,lineterminator='\n')
                writer.writeheader()
                for item in sorted(rows,key=lambda r:(r['date'],r['symbol'])):
                    writer.writerow({k:item[k] for k in FIELDNAMES_V1})
            old=dict(meta);old['schema_version']=1;old['quotes']=PRICE_BASIS_V1
            old['sha256']=hashlib.sha256(p1.read_bytes()).hexdigest()
            old.pop('dividend_events',None)
            m1.write_text(json.dumps(old))
            legacy,man = read_snapshot(p1,m1)
            self.assertEqual(man['schema_version'],1)
            self.assertEqual(legacy[date.fromisoformat(event['date'])][event['symbol']].dividend,0)

    def test_invalid_dividend_rejected_and_snapshot_integrity(self):
        from tests.test_marketdata import fixture_rows
        for invalid in (-1,float('nan'),float('inf')):
            rows=fixture_rows();rows[0]['dividend']=invalid
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(MarketDataError):
                    write_snapshot(rows,temp,start=date(2025,1,1),end=date(2025,7,1),
                                  received_currencies={s:'EUR' for s in RESEARCH_UNIVERSE})
        with tempfile.TemporaryDirectory() as temp:
            p,m=write_snapshot(fixture_rows(),temp,start=date(2025,1,1),end=date(2025,7,1),
                               received_currencies={s:'EUR' for s in RESEARCH_UNIVERSE})
            p.write_bytes(p.read_bytes().replace(b',0\n',b',0.1\n',1))
            with self.assertRaisesRegex(MarketDataError,'verification failed'):
                read_snapshot(p,m)

    def test_split_event_fail_closed_vendor_mock(self):
        import sys
        from types import SimpleNamespace
        class StubFrame:
            empty=False
            columns=('Dividends','Stock Splits')
            def iterrows(self):
                d = date(2025,1,2)
                return iter([(SimpleNamespace(date=lambda: d),{
                    'Stock Splits': 2.0,'Dividends':0.0,
                    'Open':10,'High':11,'Low':9,'Close':10,'Volume':500})])
        class StubTicker:
            fast_info={'currency':'EUR'}
            def history(self,**kwargs):
                self.kwargs=kwargs
                return StubFrame()
        with patch.dict(sys.modules,{'yfinance':SimpleNamespace(Ticker=lambda ticker:StubTicker())}):
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(MarketDataError,'Reported stock split'):
                    fetch_yahoo_snapshot(date(2025,1,1),date(2025,7,1),Path(temp)/'data')


class ChronologicalTests(unittest.TestCase):
    def test_model_selection_does_not_read_future_prices(self):
        data=history()
        split=list(data)[150]
        old=compare_forward(data,split=split,selected_cost='hypothetical_0_25_fractional')
        future={k:dict(v) for k,v in data.items()}
        for d in future:
            if d >= split:
                b=future[d]['EUNL.DE']
                future[d]['EUNL.DE']=Bar(d,b.symbol,b.open*1.1,b.high*1.1,b.low*1.1,
                                          b.close*1.1,b.volume,b.spread_bps,b.dividend)
        new=compare_forward(future,split=split,selected_cost='hypothetical_0_25_fractional')
        self.assertEqual(old['selected_from_training_only'],new['selected_from_training_only'])
        self.assertEqual(old['training_candidates'],new['training_candidates'])
        self.assertEqual(old['period']['split'],new['period']['split'])

    def test_forward_portfolio_starts_with_fresh_cash(self):
        data=history();split=list(data)[150]
        r=run_scenario(data,strategy='one_shot_stop',costs=FeeScenario('h',.25,True),trade_start=split)
        self.assertEqual(r['initial_equity'],1000)
        self.assertEqual(r['curve'][0]['date'],split.isoformat())
        self.assertTrue(all(f['date'] >= split.isoformat() and f['signal_date'] >= split.isoformat() for f in r['fills']))
        self.assertEqual(r['trade_start'],split.isoformat())
        self.assertEqual(len(r['curve']),80)

    def test_invalid_splits_fail_and_cash_option(self):
        data=history()
        with self.assertRaisesRegex(ValueError,'Need >=120'):
            compare_forward(data,split=list(data)[70],selected_cost='fixed_1_25_whole')
        with self.assertRaisesRegex(ValueError,'Unknown cost'):
            compare_forward(data,split=list(data)[160],selected_cost='free_imaginary')
        result=compare_forward(data,split=list(data)[150],selected_cost='fixed_1_25_whole')
        self.assertEqual(result['selected_from_training_only'],'CASH')
        self.assertEqual(result['forward_selected']['return_pct'],0.0)

    def test_forward_provides_only_training_chosen_strategy(self):
        r=compare_forward(history(),split=list(history())[150],selected_cost='hypothetical_0_25_fractional')
        self.assertEqual(len(r['training_candidates']),3)
        self.assertIn(r['selected_from_training_only'],('CASH','swing','monthly_momentum','one_shot_stop'))
        self.assertIn('truly unseen',str(r['limitations']))
        self.assertEqual(r['mode'],'OFFLINE_CHRONOLOGICAL_RESEARCH_ONLY')
        self.assertTrue(r['cost_scenario']['fractional_shares_hypothetical'])


class ResearchBoundaryTests(unittest.TestCase):
    def test_valid_note_is_non_actionable(self):
        r=validate_research_note(example_note(),asof=date(2025,6,2),
                                 allowed_symbols=frozenset({'EUNL.DE'}))
        self.assertFalse(r['actionable_order'])
        self.assertFalse(r['broker_connected'])

    def test_reject_prompt_injection_order_and_future_evidence(self):
        p=example_note();p['place_order']={'side':'BUY','quantity':10}
        with self.assertRaises(ValueError):
            validate_research_note(p,asof=date(2025,6,2),allowed_symbols=frozenset({'EUNL.DE'}))
        p=example_note();p['evidence'][0]['date']='2025-06-03'
        with self.assertRaisesRegex(ValueError,'future'):
            validate_research_note(p,asof=date(2025,6,2),allowed_symbols=frozenset({'EUNL.DE'}))

    def test_reject_bad_confidence_symbol_and_dates(self):
        for v in (math.inf,float('nan'),True,-.1,1.1,'0.5'):
            p=example_note();p['confidence']=v
            with self.assertRaises(ValueError):
                validate_research_note(p,asof=date(2025,6,2),allowed_symbols=frozenset({'EUNL.DE'}))
        p=example_note();p['symbol']='UNAPPROVED'
        with self.assertRaises(ValueError):
            validate_research_note(p,asof=date(2025,6,2),allowed_symbols=frozenset({'EUNL.DE'}))
        p=example_note();p['date']='2025-06-03'
        with self.assertRaises(ValueError):
            validate_research_note(p,asof=date(2025,6,2),allowed_symbols=frozenset({'EUNL.DE'}))

    def test_no_llm_network_or_broker_packages(self):
        import inspect,ai_trading_fleet.advisory as advisory
        s=inspect.getsource(advisory)
        self.assertNotIn('placeOrder',s)
        self.assertNotIn('requests.',s)
        self.assertNotIn('openai.',s)

if __name__ == '__main__':
    unittest.main()
