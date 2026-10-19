"""Chronological, research-only model selection and forward evaluation.

Selection observes training outcomes only; 2025+ historical samples have been
seen by project developers already, so they are NOT genuinely untouched OOS.
"""
from __future__ import annotations

from datetime import date

from .models import Bar
from .research_lab import SCENARIOS, STRATEGIES, run_scenario, _valid_daily
from .evaluation import capped_buy_and_hold


def _condense(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in ('fills', 'curve')}


def compare_forward(data: dict[date, dict[str, Bar]], *, split: date,
                    selected_cost: str, capital: float = 1000.0) -> dict:
    """Fit *choice*, never signals, on pre-split data. Evaluate chosen plan once.

    This is one chronological split, NOT rigorous rolling walk-forward, and
    not independent validation of project decisions informed by the period.
    The broker fee scenario is fixed *before* training, not selected by profit.
    """
    dates, symbols = _valid_daily(data)
    scenario = next((s for s in SCENARIOS if s.name == selected_cost), None)
    if scenario is None:
        raise ValueError('Unknown cost scenario; specify fixed hypothetical fee schedule')
    training = {d: data[d] for d in dates if d < split}
    evaluation_dates = [d for d in dates if d >= split]
    if len(training) < 120 or len(evaluation_dates) < 40:
        raise ValueError('Need >=120 training and >=40 forward sessions')
    # The fee schedule is fixed; do not optimize hypothetical broker fees.
    scored = []
    for strategy in STRATEGIES:
        train = run_scenario(training, strategy=strategy, costs=scenario, capital=capital)
        score = round(train['return_pct'] - 0.5 * train['max_drawdown_pct'], 5)
        # A single fill cannot establish trading evidence; 1 completed round trip
        # is the *bare* eligibility floor, not a claim of statistical power.
        eligible = train['round_trips_closed'] >= 1 and score > 0
        scored.append({'strategy': strategy, 'training_score': score,
                       'eligible': eligible, 'training': _condense(train)})
    choices = [c for c in scored if c['eligible']]
    winner = sorted(choices, key=lambda r: (-r['training_score'], r['strategy']))[0] if choices else None
    if winner:
        forward = run_scenario(data, strategy=winner['strategy'], costs=scenario,
                               capital=capital, trade_start=split)
        verdict = winner['strategy']
    else:
        forward = {'initial_equity': capital, 'final_equity': capital,
                   'return_pct': 0.0, 'max_drawdown_pct': 0.0,
                   'executions': 0, 'fees_paid_eur': 0.0,
                   'dividends_credited_eur': 0.0, 'trade_start': split.isoformat(),
                   'note': 'cash fallback; no training strategy met predeclared selection gate'}
        verdict = 'CASH'
    future_data = {d: data[d] for d in evaluation_dates}
    benchmarks = {symbol: capped_buy_and_hold(future_data, symbol, capital=capital,
                  allocation_fraction=0.20, fee=scenario.commission,
                  slippage_bps=scenario.slippage_bps) for symbol in symbols}
    return {
        'version': '0.5-forward-research',
        'mode': 'OFFLINE_CHRONOLOGICAL_RESEARCH_ONLY',
        'initial_capital_eur': capital,
        'period': {'train_first': dates[0].isoformat(),
                   'train_last': max(training).isoformat(),
                   'forward_first': evaluation_dates[0].isoformat(),
                   'forward_last': evaluation_dates[-1].isoformat(),
                   'split': split.isoformat()},
        'cost_scenario': {'name': scenario.name,
                          'fee_per_fill_eur': scenario.commission,
                          'fractional_shares_hypothetical': scenario.fractional},
        'selection_rule': 'training return % minus half of training peak-to-trough drawdown %; must have >=1 closed round trip, score > 0; otherwise CASH',
        'training_candidates': scored,
        'selected_from_training_only': verdict,
        'forward_selected': _condense(forward),
        'forward_passive_20pct_initial_allocation_not_risk_matched': benchmarks,
        'limitations': [
            'This is a single chronological evaluation, not rolling walk-forward or statistically independent validation.',
            'The 2025+ evaluation era has already influenced this project; cannot call it truly unseen out-of-sample.',
            'Dividend events credited on ex-date without payment delay, tax, distribution eligibility reconciliation or accrued interest.',
            'Provider OHLC may be split-adjusted; reported splits are refused on new downloads; vendor feed and spread are not execution-quality.',
            'Fractional shares and reduced fees are purely hypothetical and require broker confirmation.',
            'Portfolio stop triggered on close and exits attempted next open; gaps can exceed planned risk.',
            'Passive benchmarks have 20% initial capital exposure but are not matched for trade stop risk.',
            'No LLM model, automatic execution, paper brokerage or real capital involved.',
        ],
    }
