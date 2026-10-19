# Practical delivery plan

## Sprint 0: packaged in v0.1 (this archive)
- Repo scaffold with Python package, synthetic deterministic daily prices, separate role modules, risk gate, next-session simulated limit orders, audit JSON, optional read-only dashboard, unittest and GitHub CI.
- It DOES NOT contain a live-data provider, LLM calls, TradingAgents import, cloud deployment or broker API implementation.

## Sprint 1: verified historical research-data MVP (v0.2 implemented; NOT fully research-grade)
- Opt-in yfinance daily OHLC data snapshots with EUR checks, dataset hashing and offline-only backtest.
- Descriptive holdout; cash and next-session buy-and-hold price-only baseline.

## Remaining Sprint 1: more rigorous backtesting
- Choose 3-6 eligible EUR-listed UCITS ETFs, verify exact ISIN/venue and historical price-data rights.
- Swap synthetic CSV for adjusted point-in-time prices incl. corporate actions, markets closed/holiday calendar, valid symbol mapping, exchange timezone.
- Trade cost model: commission min/fixed vs tiered, spread, FX, slippage, market impact; pass independent data validation.
- Add no-trade buy/hold, momentum baseline and buy-and-hold comparators. Walk-forward, no lookahead, bootstrap uncertainty.

## Sprint 2: advisory AI and audit
- TradingAgents adapter behind `AdvisoryAgent` contract, timestamped outputs, bounded parallelism, retry budgets, caching and model/provider cost caps.
- Require skeptic research and structured rationale grounded in immutable market snapshots.
- Continuous experiment logs and quantitative comparison: baseline vs AI-assisted system AFTER all costs.
- Research commentary from LLM MUST NOT bypass policy or access order submission.

## Sprint 3: real broker paper trading
- IBKR Paper via TWS API / IB Gateway, manual authentication and reconnection flow, dedicated segregated service.
- Dry-run creation and idempotent reconciliation, no live credentials; paper for 90+ market sessions.
- Mobile read-only authenticated dashboard and notifications on exceptions.

## Sprint 4: separately authorized live pilot
- Review data, fees, taxes, broker instrument eligibility and operational performance.
- Manual approval for small live deployment, stronger broker and server-side controls, no push-to-prod from coding agents.
- Stop pilot on any reconciliation mismatch, circuit-breaker trigger, material losses or security incident.

## Suggested GitHub issues
1. Data provider adapter and historical data provenance (P0)
2. Baselines and walk-forward evaluator (P0)
3. Full broker-cost and spread model (P0)
4. Persisted append-only order audit (P0)
5. Independent risk-gate adversarial test suite (P0)
6. TradingAgents advisor adapter, advisory-only (P1)
7. IBKR paper connector + reconciliation testnet (P1)
8. Mobile authenticated read-only UI (P2)

## v0.6 implementation
- Implemented rolling, nonoverlapping per-window research with trailing-only training and independent capital reset, passive comparison and explicitly non-compounded summaries.
- An optional paid API OpenAI research-only note command exists; its output is strictly schema checked and has no trading execution integration. It is never run in CI or any GitHub Action.
- Important next tasks: verify real broker price schedule and eligible fractional orders, validate truly new data, independent statistics, better adjusted/point-in-time prices, and long-lived paper-broker operational safety tests.
