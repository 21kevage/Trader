"""v0.7 shadow demonstration: deterministic MOCK commentary, never an actual model.

This module has no network/client/broker import. It cannot submit or size an order.
It creates a read-only, price-observation report suitable for an HTML artifact.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from html import escape
from statistics import mean
from typing import Any

from .advisory import validate_research_note
from .ai_research import _market_observation
from .agents import QuantAnalyst
from .marketdata import RESEARCH_UNIVERSE
from .models import Bar
from .research_lab import _valid_daily

MOCK_SOURCE = "MOCK_DETERMINISTIC_RULE_NOT_REAL_AI"
HUMAN_LABEL = "SIMULIERTE KI-ANTWORT — KEIN ECHTES KI-MODELL"


def make_mock_note(data: dict[date, dict[str, Bar]], symbol: str, asof: date) -> dict:
    """Deterministic stand-in complying with existing research-note boundary.

    No response, label, or evaluation outcome consumes prices after ``asof``.
    """
    observation, sha = _market_observation(data, symbol, asof)
    m20 = observation["20_session_momentum_pct"]
    m60 = observation["60_session_momentum_pct"]
    stance = ("BULLISH" if m20 > 1 and m60 > 0 else
              "BEARISH" if m20 < -1 and m60 < 0 else "NEUTRAL")
    evidence = observation["last_5_session_observations"][-1]
    payload = {
        "schema_version": 1,
        "date": asof.isoformat(),
        "symbol": symbol,
        "stance": stance,
        "confidence": 0.5,  # FIXTURE ONLY; not a calibrated probability.
        "rationale": "Deterministic MOCK only: signs of 20/60-session historical momentum.",
        "evidence": [{
            "date": evidence["date"],
            "summary": f"Last available close EUR {evidence['close_eur']:.4f}, no forecast.",
        }],
    }
    validate_research_note(payload, asof=asof, allowed_symbols=frozenset({symbol}))
    return {"note": payload, "observation_sha256": sha,
            "source": MOCK_SOURCE, "paid_model_called": False}


def _rule_stance(bars: list[Bar]) -> str:
    """Compare price *indicators*, not a live portfolio BUY/SELL decision."""
    score = QuantAnalyst().assess(bars[-1].symbol, bars)
    if score is None:
        raise ValueError("Rule comparator needs 31 observations")
    return "BULLISH" if score.buy else "BEARISH" if score.exit else "NEUTRAL"


def shadow_preview(data: dict[date, dict[str, Bar]], *,
                   last_sessions: int = 12, step_sessions: int = 5,
                   horizon_sessions: int = 5, capital: float = 1000.0) -> dict:
    """Create a labelled demo with later observations, without actual predictions.

    The mock is intentionally built from historical trend math, **not an AI**.
    The data feed can include later prices for diagnostic evaluation, but the
    mock/rule decision at each asof uses only data through that asof date.
    """
    if any(type(v) is not int for v in (last_sessions, step_sessions, horizon_sessions)):
        raise ValueError("Window controls must be integers")
    if not 1 <= last_sessions <= 30 or not 1 <= step_sessions <= 30 or not 1 <= horizon_sessions <= 20:
        raise ValueError("Window controls outside safe bounds")
    if capital != 1000.0:
        raise ValueError("Fixed educational paper capital only: EUR 1,000")
    dates, all_symbols = _valid_daily(data)
    symbols = tuple(sorted(set(all_symbols) & set(RESEARCH_UNIVERSE)))
    if not symbols or set(symbols) != set(all_symbols):
        raise ValueError("Research-only EUR ETF symbol universe required")
    eligible_indexes = list(range(60, len(dates), step_sessions))
    if not eligible_indexes:
        raise ValueError("At least 61 sessions required")
    # Include the final completed as-of bar for a useful latest-status card.
    if eligible_indexes[-1] != len(dates) - 1:
        eligible_indexes.append(len(dates) - 1)
    indexes = eligible_indexes[-last_sessions:]
    decisions = []
    for idx in indexes:
        asof = dates[idx]
        for sym in symbols:
            past = [data[d][sym] for d in dates[:idx+1] if sym in data[d]]
            if len(past) < 61 or past[-1].date != asof:
                raise ValueError("Missing exact as-of quote or insufficient warmup")
            mock = make_mock_note(data, sym, asof)
            rule_stance = _rule_stance(past)
            current = past[-1].close
            # Evaluation ONLY, after both observations were fixed.
            future_index = idx + horizon_sessions
            future = (data[dates[future_index]].get(sym)
                      if future_index < len(dates) else None)
            outcome = (round(100 * (future.close / current - 1), 3)
                       if future is not None else None)
            decisions.append({
                "asof": asof.isoformat(), "symbol": sym,
                "mock_stance": mock["note"]["stance"],
                "mock_confidence_is_fixture_not_probability": mock["note"]["confidence"],
                "mock_note": mock["note"], "mock_source": mock["source"],
                "observation_sha256": mock["observation_sha256"],
                "rule_indicator_stance": rule_stance,
                "stance_agrees": mock["note"]["stance"] == rule_stance,
                "close_eur_at_asof": round(current, 4),
                "later_observation": {
                    "status": "OBSERVED_PRICE_CHANGE_ONLY" if outcome is not None else "PENDING",
                    "session_horizon": horizon_sessions,
                    "end_date": dates[future_index].isoformat() if future is not None else None,
                    "price_change_pct": outcome,
                },
                "order_executed": False,
            })
    counts = Counter(d["mock_stance"] for d in decisions)
    agreements = sum(d["stance_agrees"] for d in decisions)
    evaluated = [d for d in decisions if d["later_observation"]["price_change_pct"] is not None]
    return {
        "version": "0.7-shadow-mock", "mode": "OFFLINE_DETERMINISTIC_MOCK_SHADOW_ONLY",
        "headline": HUMAN_LABEL, "not_real_ai": True, "real_llm_calls": 0,
        "not_a_trading_backtest": True, "broker_connected": False,
        "order_submission_possible": False, "actual_orders": 0,
        "capital_reference_eur": capital, "capital_at_risk_eur": 0.0,
        "price_source": "Research snapshot supplied to CLI; verify snapshot provenance separately",
        "asof_last_available": dates[-1].isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": {
            "last_sessions": last_sessions, "step_sessions": step_sessions,
            "later_price_horizon_sessions": horizon_sessions,
        },
        "summary": {
            "mock_notes": len(decisions), "bullish": counts["BULLISH"],
            "bearish": counts["BEARISH"], "neutral": counts["NEUTRAL"],
            "agreement_with_rule_indicator": agreements,
            "disagreement_with_rule_indicator": len(decisions)-agreements,
            "later_price_observations_available": len(evaluated),
            "pending_later_observations": len(decisions)-len(evaluated),
            "average_later_price_change_pct_NOT_STRATEGY_RETURN":
                round(mean(d["later_observation"]["price_change_pct"] for d in evaluated), 3)
                if evaluated else None,
        },
        "decisions": decisions,
        "warnings": [
            "SIMULATED AI: outputs are a fixed, deterministic mock. They are NOT actual AI calls.",
            "No investment recommendation, forecast accuracy, simulated order, or strategy P&L is reported.",
            "The comparator is an indicator stance, not an executable BUY/SELL order.",
            "Later prices only evaluate historical observations, not prospective predictions.",
            "Historic data was already examined in previous project versions; not independent validation.",
            "No spread, broker costs, funding, taxes or corporate action effects on any fictitious trade.",
            "The EUR 1,000 amount is informational only; no virtual position was opened.",
        ],
    }


def render_mobile_html(report: dict) -> str:
    """Self-contained, responsive and script-free HTML. Escape all data values."""
    if report.get("mode") != "OFFLINE_DETERMINISTIC_MOCK_SHADOW_ONLY":
        raise ValueError("Refuse to render other reports as mocked preview")
    def e(value: Any) -> str:
        return escape(str(value), quote=True)
    counts = report["summary"]
    def card(label: str, value: Any) -> str:
        return (f'<section class="metric"><small>{e(label)}</small>'
                f'<strong>{e(value)}</strong></section>')
    latest = sorted(report["decisions"],key=lambda d:(d["asof"],d["symbol"]),reverse=True)
    items = []
    for x in latest:
        end = x["later_observation"]
        outcome = ("Noch kein Folgezeitraum" if end["price_change_pct"] is None else
                   f"{end['price_change_pct']:+.3f} % Kursbewegung in {end['session_horizon']} Sitzungen")
        items.append('<article class="decision">'
            f'<div class="meta"><span>{e(x["asof"])} · {e(x["symbol"])}</span><span>{e(x["mock_stance"])}</span></div>'
            f'<p>Mock-Einschätzung: <b>{e(x["mock_stance"])}</b></p>'
            f'<p>Regelindikator: <b>{e(x["rule_indicator_stance"])}</b></p>'
            f'<p class="sub">{e(outcome)}</p>'
            '<p class="stamp">FAKE / KEIN LIVE-SIGNAL · KEINE ORDER</p></article>')
    return '''<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI Trading Fleet — MOCK Shadow Research</title><style>
:root {color-scheme:dark; font-family: system-ui, sans-serif; background:#0d1421;color:#e6edf7}
* {box-sizing:border-box}body{margin:0}main{max-width:820px;margin:0 auto;padding:22px 16px 56px}
h1{font-size:1.5rem;letter-spacing:-.025em;margin:14px 0 8px}.sub,p{line-height:1.5;color:#abb9cd}
.warning{border:2px solid #e3a14c;background:#312819;border-radius:14px;padding:14px;color:#ffdda7;font-weight:800}
.meta,header{display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap}.kicker{font-size:.75rem;color:#9fb1c7;text-transform:uppercase;letter-spacing:.12em}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:20px 0}
.metric,.decision{border:1px solid #2b3e56;background:#142235;border-radius:13px;padding:14px}
.metric small{display:block;color:#a4b7ce;font-size:.75rem}.metric strong{font-size:1.5rem;display:block;margin-top:7px}
h2{font-size:1.12rem;margin:28px 0 12px}.decision{margin-bottom:10px}.decision p{margin:8px 0}
.stamp{font-size:.71rem;letter-spacing:.04em;color:#ffce83;font-weight:bold}.meta{color:#8cdbcb;font-size:.79rem}
footer{border-top:1px solid #2b3e56;margin-top:24px;padding-top:16px;font-size:.8rem;color:#9babc1}
@media(max-width:340px){.cards{grid-template-columns:1fr}}
</style></head><body><main>
<div class="kicker">AI Trading Fleet · v0.7 · Offline Research</div>
<h1>Shadow Research – Handydashboard</h1>
<div class="warning">SIMULIERTE KI-ANTWORTEN — KEIN ECHTES KI-MODELL</div>
<p>Deterministische Demo-Einschätzungen gegen regelbasierte Kursindikatoren. Keine Signale an eine Börse, keine echten Prognosen.</p>
<div class="cards">''' + ''.join([
    card("Startkapital (nur Referenz)", "1.000 €"),
    card("Ausgeführte Orders", "0"),
    card("Simulierte Einschätzungen", counts["mock_notes"]),
    card("Übereinstimmung (keine Trefferquote)",f'{counts["agreement_with_rule_indicator"]} / {counts["mock_notes"]}'),
    card("5-Tage-Folgedaten verfügbar",counts["later_price_observations_available"]),
    card("Noch ohne Folgedaten",counts["pending_later_observations"]),
]) + '''</div><h2>Vergleich vergangener Beobachtungen</h2>''' + ''.join(items) + f'''
<footer>Letzter Datenstand: {e(report["asof_last_available"])} · Abruf: {e(report["generated_utc"])} UTC.
<br/>Research-Only. Die späteren Kursbewegungen sind <b>keine Handelsrenditen</b>.
Die Mock-Einschätzungen sind bewusst keine echten KI-Empfehlungen. Nicht als Anlageberatung verwenden.</footer>
</main></body></html>'''


def render_github_summary(report: dict) -> str:
    """Compact readable GitHub Actions summary, no executable markup."""
    if report.get("mode") != "OFFLINE_DETERMINISTIC_MOCK_SHADOW_ONLY":
        raise ValueError("Unknown report")
    s = report["summary"]
    return (
        "# v0.7 Shadow Research – NUR SIMULIERTE KI-ANTWORTEN\n\n"
        "> **KEINE ECHTE KI · KEINE ORDER · KEIN ECHTGELD**\n\n"
        f"Letzter Kursstand: **{report['asof_last_available']}** · "
        f"Virtuelles Referenzkapital: **1.000 €**, nicht investiert.\n\n"
        "| Kennzahl | Wert |\n|---|---:|\n"
        f"| Mock-Einschätzungen | {s['mock_notes']} |\n"
        f"| Übereinstimmung mit Kursregeln (keine Prognosequote) | {s['agreement_with_rule_indicator']} |\n"
        f"| Beobachtete spätere Kursänderungen | {s['later_price_observations_available']} |\n"
        f"| Späterer Kurs noch nicht vorhanden | {s['pending_later_observations']} |\n\n"
        "Das HTML-Dashboard liegt im Artefakt **v07-shadow-report**. "
        "Es handelt sich um rückblickende Demo-Daten und **keinen Beleg für Handelsgewinne**.\n"
    )
