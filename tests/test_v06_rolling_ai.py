"""New v0.6 regression tests are all offline; API client fully stubbed."""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from ai_trading_fleet.models import Bar
from ai_trading_fleet.walk_forward import walk_forward
from ai_trading_fleet.ai_research import _market_observation, request_research_note
from ai_trading_fleet.cli import main
from ai_trading_fleet.marketdata import RESEARCH_UNIVERSE, write_snapshot


def fixture(days=470):
    first = date(2022, 1, 3)
    out = {}
    d = first
    while len(out) < days:
        if d.weekday() < 5:
            idx = len(out)
            # Fixed deterministic series with enough momentum and volatility.
            p = 28 * (1 + idx * .001 + .015 * __import__('math').sin(idx / 12))
            q = 31 * (1 + idx * .0007 + .011 * __import__('math').sin(idx / 16))
            out[d] = {
                'EUNL.DE': Bar(d, 'EUNL.DE', p, p*1.01, p*.99, p, 100000, 15, 0),
                'IS3N.DE': Bar(d, 'IS3N.DE', q, q*1.01, q*.99, q, 120000, 15, 0),
            }
        d += timedelta(days=1)
    return out


class RollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()

    def test_windows_non_overlapping_and_selection_chronological(self):
        report = walk_forward(self.data, cost='hypothetical_0_25_fractional',
                              training_sessions=180, evaluation_sessions=63)
        windows = report['windows']
        self.assertGreaterEqual(len(windows), 4)
        self.assertEqual(report['summary']['windows'], len(windows))
        for i, w in enumerate(windows):
            self.assertLess(w['training_last'], w['evaluation_first'])
            self.assertLessEqual(w['evaluation_first'], w['evaluation_last'])
            self.assertEqual(len(w['training_candidates']), 3)
            self.assertIn(w['selected_from_training_only'], ['CASH','swing','monthly_momentum','one_shot_stop'])
            self.assertEqual(w['evaluation']['final_equity_eur'] >= 0, True)
            if i:
                self.assertLess(windows[i-1]['evaluation_last'], w['evaluation_first'])
        self.assertEqual(report['capital_per_independent_window_eur'], 1000)
        self.assertIn('NO compounded', 'NO compounded' if 'NO compounded' in report['limitations'][2] else '')

    def test_replacing_future_bars_does_not_change_prior_window_selection(self):
        prior = walk_forward(self.data,cost='hypothetical_0_25_fractional',
                             training_sessions=180,evaluation_sessions=63)
        start = date.fromisoformat(prior['windows'][0]['evaluation_first'])
        altered = {d: dict(v) for d, v in self.data.items()}
        for d in altered:
            if d >= start:
                old = altered[d]['EUNL.DE']
                altered[d]['EUNL.DE'] = Bar(d, old.symbol, old.open*.7, old.high*.7,
                                             old.low*.7, old.close*.7, old.volume, old.spread_bps)
        changed = walk_forward(altered,cost='hypothetical_0_25_fractional',
                                training_sessions=180,evaluation_sessions=63)
        self.assertEqual(prior['windows'][0]['training_candidates'], changed['windows'][0]['training_candidates'])
        self.assertEqual(prior['windows'][0]['selected_from_training_only'],
                         changed['windows'][0]['selected_from_training_only'])

    def test_cost_sensitivity_and_invalid_window_inputs(self):
        one = walk_forward(self.data,cost='fixed_1_25_whole',training_sessions=180,evaluation_sessions=63)
        self.assertEqual(one['summary']['cash_windows'],one['summary']['windows'])
        with self.assertRaisesRegex(ValueError,'Unknown cost'):
            walk_forward(self.data,cost='foo')
        for train, test in [(100,63),(180,20),(180,63.0)]:
            with self.assertRaises(ValueError):
                walk_forward(self.data,cost='hypothetical_0_25_fractional',
                             training_sessions=train,evaluation_sessions=test)
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            walk_forward(dict(list(self.data.items())[:200]),cost='hypothetical_0_25_fractional',training_sessions=180,evaluation_sessions=63)

    def test_cli_research_snapshot_integration_offline(self):
        subset = dict(list(self.data.items())[:270])
        rows = []
        for d,daily in subset.items():
            for sym,b in daily.items():
                rows.append({'date':d.isoformat(),'symbol':sym,'open':b.open,'high':b.high,
                             'low':b.low,'close':b.close,'volume':b.volume,'spread_bps':b.spread_bps,'dividend':0})
        with tempfile.TemporaryDirectory() as temp:
            csvp,meta = write_snapshot(rows,Path(temp)/'data',start=min(subset),
                           end=max(subset)+timedelta(days=1),received_currencies={s:'EUR' for s in RESEARCH_UNIVERSE})
            out=Path(temp)/'report.json'
            with patch('builtins.print'):
                main(['walk-forward','--csv',str(csvp),'--manifest',str(meta),
                      '--cost','fixed_1_25_whole','--train-sessions','180',
                      '--test-sessions','63','--out',str(out)])
            result=json.loads(out.read_text())
            self.assertEqual(result['version'],'0.6-walk-forward')
            self.assertIn('snapshot_sha256',result)


class FakeResponses:
    def __init__(self, payload):
        self.payload=payload
        self.calls=[]
        self.responses=self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status='completed',output_text=json.dumps(self.payload),
                               usage=SimpleNamespace(input_tokens=150,output_tokens=90))


class AiResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=fixture(150)
        cls.asof=list(cls.data)[100]

    def payload(self):
        return {'schema_version':1,'date':self.asof.isoformat(),'symbol':'EUNL.DE',
                'stance':'NEUTRAL','confidence':0.2,
                'rationale':'Only recent price patterns are available; no strong evidence.',
                'evidence':[{'date':self.asof.isoformat(),'summary':'Most recent quoted closing price'}]}

    def test_no_paid_request_without_explicit_opt_in(self):
        fake=FakeResponses(self.payload())
        with self.assertRaisesRegex(ValueError,'disabled'):
            request_research_note(self.data,symbol='EUNL.DE',asof=self.asof,client=fake)
        self.assertEqual(fake.calls,[])

    def test_valid_structured_api_call_is_non_actionable_and_store_false(self):
        fake=FakeResponses(self.payload())
        r=request_research_note(self.data,symbol='EUNL.DE',asof=self.asof,
                                client=fake,confirm_paid_api=True)
        self.assertTrue(r['not_a_signal_or_order'])
        self.assertFalse(r['broker_connected'])
        self.assertEqual(r['validation']['actionable_order'],False)
        self.assertEqual(r['usage_tokens'],{'input':150,'output':90})
        self.assertEqual(len(fake.calls),1)
        params=fake.calls[0]
        self.assertIs(params['store'],False)
        self.assertEqual(params['tools'],[])
        self.assertEqual(params['text']['format']['type'],'json_schema')
        self.assertFalse('BUY' in str(params['text']['format']['schema']))
        self.assertIn('20_session_momentum_pct',params['input'])

    def test_injected_order_and_fake_evidence_rejected(self):
        p=self.payload();p['execute_order']={'side':'BUY','qty':10000}
        with self.assertRaises(ValueError):
            request_research_note(self.data,symbol='EUNL.DE',asof=self.asof,
                                  client=FakeResponses(p),confirm_paid_api=True)
        p=self.payload();p['evidence'][0]['date']='2022-01-03'
        with self.assertRaisesRegex(ValueError,'unobserved'):
            request_research_note(self.data,symbol='EUNL.DE',asof=self.asof,
                                  client=FakeResponses(p),confirm_paid_api=True)

    def test_data_cannot_contain_future_observations(self):
        cut={d:v for d,v in self.data.items() if d<=self.asof}
        full,_=_market_observation(self.data,'EUNL.DE',self.asof)
        trimmed,_=_market_observation(cut,'EUNL.DE',self.asof)
        self.assertEqual(full,trimmed)
        with self.assertRaises(ValueError):
            _market_observation(self.data,'UNAPPROVED',self.asof)
        with self.assertRaisesRegex(ValueError,'exact as-of'):
            _market_observation(self.data,'EUNL.DE',self.asof+timedelta(days=40))
        with self.assertRaisesRegex(ValueError,'future'):
            _market_observation(self.data,'EUNL.DE',date(2099,1,1))

    def test_failure_or_refusal_remains_non_actionable(self):
        p=self.payload()
        fake=FakeResponses(p)
        def refuse(**kwargs):
            return SimpleNamespace(status='incomplete',output_text=json.dumps(p))
        fake.create=refuse
        with self.assertRaisesRegex(ValueError,'incomplete'):
            request_research_note(self.data,symbol='EUNL.DE',asof=self.asof,
                                  client=fake,confirm_paid_api=True)


if __name__=='__main__':
    unittest.main()
