# AI Trading Fleet · MVP v0.1

An offline, **deterministic and synthetic** research prototype for a future multi-agent trading system inspired by Firstmate's crew-supervision principle.

> **NO REAL OR IBKR PAPER TRADING.** This build has no live data, LLM API, broker API, credentials or order-submission endpoints. Demo symbols/prices are synthetic. Any shown performance is meaningless for investment decisions.

**Default simulated starting capital: 1,000 EUR.** At this scale, 20% per position = 200 EUR, 60% maximum aggregate exposure = 600 EUR, planned trade risk 0.25% = 2.50 EUR; daily/weekly/drawdown circuit breakers at 10/25/50 EUR initially. Demo fees may outweigh gains.

## Run (Python 3.11+)

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -e .
fleet run-demo
python -m unittest discover -s tests -v
```

To view demo report locally:

```bash
pip install -e '.[web]'
uvicorn ai_trading_fleet.api:app --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765
```

CLI generates deterministic synthetic demonstration data when `data/demo_prices.csv` is absent (or reads the local CSV when supplied) and writes `output/report.json` containing every assessment, risk rejection, queued order and simulated fill. Always verify the report's `mode` field.

## Structure

```text
src/ai_trading_fleet/
  agents.py       deterministic MarketScout, Quant, Skeptic, NewsStatus and Strategy roles
  data.py         defensive CSV data parser
  models.py       typed records and paper portfolio
  risk.py         hard-coded risk checks and order sizing
  execution.py    offline-only broker simulator, no network
  engine.py       end-of-day signals -> NEXT open only; audit trail
  cli.py          offline demo CLI
  api.py          optional read-only local report UI
tests/             standard-library unittest safety/integrity checks
config/            proposed market universe, NOT an order whitelist for a real broker
data/              generated synthetic sample prices
.github/workflows/ci.yml  safe no-secret test workflow
docs/              architecture, security policy, phased roadmap
```

## Key design decisions

- Firstmate is a CODING assistant orchestration distribution; do not run it as the live trading core.
- TradingAgents is a separate LLM research framework; evaluate as advisory adapter in Sprint 2. Neither project is bundled.
- Live instrument selection must be human-approved whitelist at broker contract/ISIN/venue level.
- Risk Engine may reject ALL buys when missing reliable data; no LLM can override it.
- Demo uses next-session opens, NOT the same candle's close; more robust fill handling remains necessary for real paper trading.
- Fee and price gap risks remain; backtests and simulated fills are not forecasts.

## References

- https://www.thelad.de/blog/firstmate-multi-agent-setup
- https://github.com/kunchenguid/firstmate
- https://github.com/TauricResearch/TradingAgents
- https://www.interactivebrokers.com/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway
- https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/tws-api-limitations

See `docs/ARCHITECTURE.md`, `docs/RISK_AND_SECURITY.md`, `docs/ROADMAP.md`.
