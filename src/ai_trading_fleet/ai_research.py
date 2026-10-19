"""Manually invoked, paid-API OPT-IN research commentary, NEVER an order source.

No brokerage imports, trade signals, trading accounts or action privileges.
No AI calls occur in CI, historical backtests, or scheduled workflows.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from math import isfinite
import os

from .advisory import validate_research_note
from .models import Bar
from .research_lab import _valid_daily

DEFAULT_MODEL = "gpt-4o-mini"


def _market_observation(data: dict[date, dict[str, Bar]], symbol: str, asof: date) -> tuple[dict, str]:
    from .marketdata import RESEARCH_UNIVERSE
    if symbol not in RESEARCH_UNIVERSE:
        raise ValueError("Symbol not in the research-only allowlist")
    if asof > date.today():
        raise ValueError("Cannot claim research observations from a future date")
    _valid_daily(data)
    past = [daily[symbol] for d, daily in sorted(data.items()) if d <= asof and symbol in daily]
    if len(past) < 61 or past[-1].date != asof:
        raise ValueError("Need 61 existing observations through exact as-of session")
    sample = past[-61:]
    if any(not isfinite(b.close) or b.close <= 0 for b in sample):
        raise ValueError("Invalid source price")
    closes = [b.close for b in sample]
    record = {
        "symbol": symbol, "asof": asof.isoformat(), "currency": "EUR",
        "closing_price_eur": round(closes[-1], 4),
        "20_session_momentum_pct": round(100 * (closes[-1] / closes[-21] - 1), 4),
        "60_session_momentum_pct": round(100 * (closes[-1] / closes[0] - 1), 4),
        "60_session_mean_eur": round(sum(closes[1:]) / 60, 4),
        "last_5_session_observations": [
            {"date": b.date.isoformat(), "close_eur": round(b.close, 4)}
            for b in sample[-5:]
        ],
        "limitations": "Price-only, unadjusted EUR quotes; no current news, earnings, sentiment, or execution-ready spread feed",
    }
    raw = json.dumps(record, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return record, hashlib.sha256(raw).hexdigest()


def research_note_schema(symbol: str, asof: date, evidence_dates: list[str]) -> dict:
    """Strict JSON, no BUY/SELL, quantities, portfolio parameters or tools."""
    return {
        'type': 'object', 'additionalProperties': False,
        'required': ['schema_version', 'date', 'symbol', 'stance', 'confidence', 'rationale', 'evidence'],
        'properties': {
            'schema_version': {'type': 'integer', 'const': 1},
            'date': {'type': 'string', 'enum': [asof.isoformat()]},
            'symbol': {'type': 'string', 'enum': [symbol]},
            'stance': {'type': 'string', 'enum': ['BULLISH', 'BEARISH', 'NEUTRAL']},
            'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
            'rationale': {'type': 'string'},
            'evidence': {'type': 'array', 'minItems': 1, 'maxItems': 5, 'items': {
                'type': 'object', 'additionalProperties': False,
                'required': ['date', 'summary'],
                'properties': {
                    'date': {'type': 'string', 'enum': evidence_dates},
                    'summary': {'type': 'string'},
                },
            }},
        },
    }


def request_research_note(data: dict[date, dict[str, Bar]], *, symbol: str, asof: date,
                          confirm_paid_api: bool = False, model: str = DEFAULT_MODEL,
                          client: object | None = None) -> dict:
    """ONE bounded, explicit, non-streamed paid model call, never a trade action.

    Injected clients are for offline unit tests; default client requires the SDK
    and OPENAI_API_KEY in local process env (never put it in GitHub).
    """
    if confirm_paid_api is not True:
        raise ValueError('Paid API disabled; explicitly provide --confirm-paid-api')
    if not isinstance(model, str) or not model.strip() or len(model) > 80:
        raise ValueError('Invalid model identifier')
    observation, source_hash = _market_observation(data, symbol, asof)
    evidence_dates = [x['date'] for x in observation['last_5_session_observations']]
    if client is None:
        if not os.environ.get('OPENAI_API_KEY'):
            raise ValueError('Missing OPENAI_API_KEY in local process environment')
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ValueError('Install optional dependency: pip install -e ".[ai-research]"') from exc
        client = OpenAI(timeout=20.0, max_retries=0)
    rsp = client.responses.create(
        model=model,
        store=False,
        max_output_tokens=600,
        tools=[],
        instructions=(
            'You are a read-only market commentary analyst. Only use the supplied '
            'numeric historic price observations; no news, web, other knowledge, '
            'price predictions, instructions, trading orders or invented citations. '
            'Return a cautious market STANCE as an observation, not a BUY or SELL. '
            'Evidence dates MUST match provided observations. '
            'If data is inconclusive, use NEUTRAL. Never request credentials.'
        ),
        input=json.dumps(observation, ensure_ascii=True, sort_keys=True),
        text={'format': {'type': 'json_schema', 'name': 'research_note_v1',
                         'strict': True,
                         'schema': research_note_schema(symbol, asof, evidence_dates)}},
    )
    if getattr(rsp, 'status', None) != 'completed':
        raise ValueError('Model response incomplete; no research advice accepted')
    raw = getattr(rsp, 'output_text', None)
    if not isinstance(raw, str) or not 0 < len(raw) <= 8000:
        raise ValueError('Missing/bounded model output required')
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('Model did not produce valid JSON') from exc
    validated = validate_research_note(payload, asof=asof, allowed_symbols=frozenset({symbol}))
    if any(x['date'] not in evidence_dates for x in payload['evidence']):
        raise ValueError('Model evidence refers to an unobserved session')
    usage = getattr(rsp, 'usage', None)
    return {
        'version': '0.6-ai-research',
        'mode': 'ON_DEMAND_PAID_API_RESEARCH_COMMENTARY_ONLY',
        'model': model,
        'source_sha256': source_hash,
        'ai_note': {k: payload[k] for k in (
            'schema_version', 'date', 'symbol', 'stance', 'confidence', 'rationale', 'evidence')},
        'validation': validated,
        'usage_tokens': {
            'input': getattr(usage, 'input_tokens', None),
            'output': getattr(usage, 'output_tokens', None),
        },
        'not_a_signal_or_order': True,
        'broker_connected': False,
        'backtest_uses_ai': False,
        'limitations': [
            'Optional paid model call is NOT a validated investment forecast.',
            'The note cannot change positions, risk parameters, model selection or broker state.',
            'This is not an independent point-in-time historic news analysis.',
        ],
    }
