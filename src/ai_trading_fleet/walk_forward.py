"""Offline rolling walk-forward evaluation; no future observations used in selection.

Each evaluation window has a *new* EUR 1,000 paper account. Returns are NOT
compounded across windows because positions are marked, not liquidated, at the
window boundary. Models and thresholds are fixed before test evaluation.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from math import isfinite

from .models import Bar
from .research_lab import SCENARIOS, STRATEGIES, _valid_daily, run_scenario
from .evaluation import capped_buy_and_hold


def walk_forward(data: dict[date, dict[str, Bar]], *, cost: str,
                 training_sessions: int = 252, evaluation_sessions: int = 63,
                 capital: float = 1000.0, max_windows: int = 30) -> dict:
    """Rolling chronological research with nonoverlapping forward windows.

    For every window, only trailing ``training_sessions`` closes determine the
    strategy. The next window can re-use previously evaluated observations as
    training history (the ordinary walk-forward procedure).
    """
    dates, symbols = _valid_daily(data)
    scenario = next((s for s in SCENARIOS if s.name == cost), None)
    if scenario is None:
        raise ValueError("Unknown cost scenario")
    if (type(training_sessions) is not int or type(evaluation_sessions) is not int
            or training_sessions < 120 or evaluation_sessions < 40
            or type(max_windows) is not int or not 1 <= max_windows <= 30):
        raise ValueError("Training needs >=120 sessions; evaluation >=40; 1..30 windows")
    if not isfinite(capital) or capital <= 0:
        raise ValueError("Invalid capital")
    if len(dates) < training_sessions + evaluation_sessions:
        raise ValueError("Insufficient market history for even one complete window")
    windows = []
    for idx in range(training_sessions, len(dates), evaluation_sessions):
        if len(windows) >= max_windows:
            raise ValueError("Too many windows; raise evaluation_sessions or shorten period")
        last = min(idx + evaluation_sessions, len(dates))
        if last - idx < 40:  # no partial windows below minimum evaluation length
            break
        train_dates = dates[idx - training_sessions:idx]
        forward_dates = dates[idx:last]
        train = {d: data[d] for d in train_dates}
        candidates = []
        for strategy in STRATEGIES:
            backtest = run_scenario(train, strategy=strategy, costs=scenario, capital=capital)
            score = round(backtest['return_pct'] - 0.5 * backtest['max_drawdown_pct'], 5)
            # Fixed selection rule from v0.5, zero tweaking for v0.6.
            eligible = backtest['round_trips_closed'] >= 1 and score > 0
            candidates.append({
                'strategy': strategy, 'training_score': score,
                'eligible': eligible,
                'training_return_pct': backtest['return_pct'],
                'training_max_drawdown_pct': backtest['max_drawdown_pct'],
                'training_completed_round_trips': backtest['round_trips_closed'],
            })
        choices = [c for c in candidates if c['eligible']]
        winner = min(choices, key=lambda r: (-r['training_score'], r['strategy'])) if choices else None
        if winner:
            # Use trailing 60 pre-evaluation sessions solely to warm indicators;
            # portfolio/cash reset on evaluation start. Nothing after forward end
            # enters this call. No boundary carry-over from prior windows.
            warmup = dates[max(0, idx - 61):idx]
            eval_data = {d: data[d] for d in warmup + forward_dates}
            result = run_scenario(eval_data, strategy=winner['strategy'], costs=scenario,
                                  capital=capital, trade_start=forward_dates[0])
            selected = winner['strategy']
            outcome = {
                'final_equity_eur': result['final_equity'],
                'return_pct': result['return_pct'],
                'max_drawdown_pct': result['max_drawdown_pct'],
                'executions': result['executions'],
                'fees_paid_eur': result['fees_paid_eur'],
                'average_gross_exposure_pct': result['average_gross_exposure_pct'],
                'open_positions_at_end': list(result['open_positions']),
                'unfilled_orders_at_end': result['unfilled_end_orders'],
                'halted_on': result['halted_on'],
            }
        else:
            selected = 'CASH'
            outcome = {
                'final_equity_eur': capital, 'return_pct': 0.0,
                'max_drawdown_pct': 0.0, 'executions': 0, 'fees_paid_eur': 0.0,
                'average_gross_exposure_pct': 0.0, 'open_positions_at_end': [],
                'unfilled_orders_at_end': 0, 'halted_on': None,
            }
        future_data = {d: data[d] for d in forward_dates}
        passive = {
            symbol: capped_buy_and_hold(future_data, symbol, capital=capital,
                                        allocation_fraction=0.20,
                                        fee=scenario.commission,
                                        slippage_bps=scenario.slippage_bps)
            for symbol in symbols
        }
        windows.append({
            'number': len(windows) + 1,
            'capital_reset_eur': capital,
            'training_first': train_dates[0].isoformat(),
            'training_last': train_dates[-1].isoformat(),
            'evaluation_first': forward_dates[0].isoformat(),
            'evaluation_last': forward_dates[-1].isoformat(),
            'evaluation_sessions': len(forward_dates),
            'selected_from_training_only': selected,
            'training_candidates': candidates,
            'evaluation': outcome,
            'passive_20pct_initial_exposure_not_risk_matched': passive,
        })
    if not windows:
        raise ValueError("No qualifying evaluation windows")
    passive_means = {
        symbol: round(sum(w['passive_20pct_initial_exposure_not_risk_matched'][symbol]['return_pct']
                          for w in windows) / len(windows), 3)
        for symbol in symbols
    }
    counts = Counter(w['selected_from_training_only'] for w in windows)
    returns = [w['evaluation']['return_pct'] for w in windows]
    active = [w for w in windows if w['selected_from_training_only'] != 'CASH']
    return {
        'version': '0.6-walk-forward',
        'mode': 'OFFLINE_ROLLING_RESEARCH_ONLY',
        'capital_per_independent_window_eur': capital,
        'cost_scenario': {
            'name': scenario.name, 'fee_per_fill_eur': scenario.commission,
            'fractional_shares_hypothetical': scenario.fractional,
        },
        'configuration': {
            'training_sessions': training_sessions,
            'training_window_type': 'trailing_rolling',
            'evaluation_sessions': evaluation_sessions,
            'overlapping_forward_windows': False,
            'accounts_reset_at_each_test_window': True,
            'initial_training_warmup_sessions': 60,
            'model_selection': 'return_pct - 0.5 * max_drawdown_pct > 0 and >=1 closed trade, else CASH',
        },
        'period': {'first_available': dates[0].isoformat(),
                   'last_available': dates[-1].isoformat(),
                   'symbols': list(symbols)},
        'summary': {
            'windows': len(windows), 'cash_windows': counts['CASH'],
            'active_windows': len(active),
            'selected_strategy_counts': dict(sorted(counts.items())),
            'positive_windows': sum(r > 0 for r in returns),
            'negative_windows': sum(r < 0 for r in returns),
            'mean_window_return_pct': round(sum(returns) / len(returns), 3),
            'mean_passive_window_returns_pct_NOT_RISK_MATCHED': passive_means,
            'median_window_return_pct': round(sorted(returns)[len(returns)//2] if len(returns)%2
                                               else (sorted(returns)[len(returns)//2-1] + sorted(returns)[len(returns)//2])/2, 3),
            'total_executions_across_independent_windows': sum(w['evaluation']['executions'] for w in windows),
            'sum_fee_eur_across_independent_windows': round(sum(w['evaluation']['fees_paid_eur'] for w in windows), 2),
        },
        'windows': windows,
        'limitations': [
            'Previous project iterations used portions of this history; results are NOT untouched out-of-sample.',
            'Training windows roll forward and legitimately learn from previously evaluated historical windows.',
            'Every forward window starts with a new 1000 EUR account; there is NO compounded performance estimate.',
            'Open end-of-window positions are marked to market; an actual rebalance/liquidation could incur additional costs.',
            'No risk-matched passive baseline or independent statistical significance test has been established.',
            'Yahoo Finance OHLC is research-only and does not provide execution-grade spread/liquidity.',
            'Fractional ETF shares and discounted commission are hypothetical; no broker is connected.',
            'Cash accrues zero interest; tax, funding, partial fills and intraday stop execution are not modeled.',
            'No LLM/model was used to select or execute trades; AI commentary is explicitly isolated.',
        ],
    }
