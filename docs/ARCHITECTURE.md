# Architecture Decision Record — AI Trading Fleet v0.1

## Separation of control planes

1. **Development plane (future):** Firstmate coordinates coding agents in worktrees. All changes via PR/CI/manual approval. Firstmate is a coding-agent distribution, not a market execution framework. It never has broker secrets.
2. **Trading research plane (future):** MarketScout, QuantAnalyst, NewsAnalyst, StrategyAgent and SkepticAgent produce structured *advisory* signals. TradingAgents is a candidate integration for the financial research stage; it is not bundled in this offline MVP.
3. **Deterministic policy plane:** Python `RiskEngine` is not prompt-controlled. It enforces whitelist, notional, sizing, drawdown/circuit breakers, cash, exposure, and no leveraged/short positions.
4. **Execution plane:** Only `SimulatedBroker` exists in v0.1. Paper-broker and real-broker adapters intentionally DO NOT EXIST. Research code cannot import an order client.
5. **Observability plane:** JSON decisions, rejected signals, fills, equity curve. `api.py` is an optional localhost-only read-only report viewer.

## Runtime flow (v0.1)

`synthetic CSV -> daily bars -> MarketScout -> QuantAnalyst -> SkepticAgent -> StrategyAgent -> RiskEngine -> queued next-open limit -> SimulatedBroker -> JSON report`

`NewsAnalyst` explicitly reports unavailable rather than fabricating news. All signal input data is from the session close or earlier. Orders created after that close can only be simulated at the NEXT session open, with a gap-dependent limit price and slippage; unfilled orders expire. There is no intraday execution and no paper live feed yet.

## Explicit future contracts

- `MarketDataProvider.fetch_bars(symbol, until)` returns exchange timezone, licensed and point-in-time bars, eligibility and data-quality metadata.
- `AdvisoryAgent.analyze(snapshot)` returns structured `{symbol, confidence, direction, rationale, source_time, model_version}`; schema validation and source freshness are mandatory; confidence is not calibrated by default.
- `BrokerAdapter.preview(order)` / `submit(idempotency_key, order)` / `reconcile()` / `cancel()` / `health()`; broker credentials must only exist in an isolated execution service.
- `RiskEngine.authorize(order, account_snapshot, quotes)` rechecks limits using current independent broker position/cash data. Rejects by default if values missing or stale. For a live system, a second pre-send check and broker-side protections are mandatory.
- `Ledger`: immutable events in SQL + append-only backup; every execution has stable idempotency key, parent decision and risk-approval IDs.

## Markets

Universe discovery is research-only until human approval. Initial live research shortlist: high-volume EUR-listed UCITS ETFs, long only. No free-form LLM-generated ticker orders. A whitelist contains exact exchange, ISIN and broker contract identifiers, NOT only ambiguous ticker symbols.

## Compatibility

Python >=3.11. Standard library for CLI/simulation/tests. `fastapi` and `uvicorn` only for optional local dashboard. No external network requests in the simulation. No external code from Firstmate/TradingAgents copied or vendored.
