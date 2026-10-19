"""Strongly typed, read-only boundary for optional *future* AI research outputs.

There are no LLM API calls, broker calls, trading instructions, or side effects.
Untrusted model text never becomes a portfolio order, symbol approval or policy.
"""
from __future__ import annotations

from datetime import date
from math import isfinite

ALLOWED_STANCES = frozenset({'BULLISH', 'BEARISH', 'NEUTRAL'})
REQUIRED = frozenset({'schema_version', 'date', 'symbol', 'stance', 'confidence', 'rationale', 'evidence'})
EVIDENCE_REQUIRED = frozenset({'date', 'summary'})


def validate_research_note(payload: object, *, asof: date,
                           allowed_symbols: frozenset[str]) -> dict:
    """Return inert, schema-checked research commentary or reject entirely."""
    if not isinstance(payload, dict) or set(payload) != REQUIRED:
        raise ValueError('Unexpected research advisory fields')
    if payload['schema_version'] != 1 or payload['date'] != asof.isoformat():
        raise ValueError('Unexpected schema version or stale/future advisory')
    symbol = payload['symbol']
    if not isinstance(symbol, str) or symbol not in allowed_symbols:
        raise ValueError('Unapproved research symbol')
    if not isinstance(payload['stance'], str) or payload['stance'] not in ALLOWED_STANCES:
        raise ValueError('Invalid research stance')
    c = payload['confidence']
    if type(c) not in (int, float) or not isfinite(c) or not 0 <= c <= 1:
        raise ValueError('Confidence must be 0..1')
    rationale = payload['rationale']
    if not isinstance(rationale, str) or not 10 <= len(rationale.strip()) <= 400:
        raise ValueError('Invalid rationale')
    evidence = payload['evidence']
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 5:
        raise ValueError('1..5 evidence items required')
    for item in evidence:
        if not isinstance(item, dict) or set(item) != EVIDENCE_REQUIRED:
            raise ValueError('Bad evidence fields')
        try:
            evidence_date = date.fromisoformat(item['date'])
        except (ValueError, TypeError) as exc:
            raise ValueError('Bad evidence date') from exc
        if evidence_date > asof:
            raise ValueError('Evidence from future date')
        summary = item['summary']
        if not isinstance(summary, str) or not 5 <= len(summary.strip()) <= 240:
            raise ValueError('Invalid evidence summary')
    # These outputs are NEVER interpreted as executable orders.
    return {'validated': True, 'research_only': True, 'actionable_order': False,
            'asof': asof.isoformat(), 'symbol': symbol, 'stance': payload['stance'],
            'confidence': c, 'evidence_count': len(evidence),
            'broker_connected': False}
