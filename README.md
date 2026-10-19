# AI Trading Fleet · MVP v0.5

An offline, **offline-only** research prototype with synthetic demo and opt-in historical research data for a future multi-agent trading system inspired by Firstmate's crew-supervision principle.

> **NO REAL OR IBKR PAPER TRADING.** This build has no streaming quotes, LLM API, broker API, credentials or order-submission endpoints. The demo is synthetic. The historical mode uses a user-downloaded Yahoo Finance research snapshot; neither mode is a validated investment strategy.

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

## Offline backtest of *real* historical prices (research-only)

The data download is **explicit** and never runs in GitHub CI. Network access plus `yfinance` are required on your machine; this environment cannot fetch vendor data directly.

```bash
pip install -e '.[market-data]'
fleet download-history --start 2022-01-01 --end 2026-10-17 --out-dir datasets/research-20261017
fleet backtest --csv datasets/research-20261017/prices.csv \
  --manifest datasets/research-20261017/manifest.json \
  --holdout-start 2025-01-01 --out output/historical-report.json
```

On Windows PowerShell, enter the final `fleet backtest` command on one line, or use PowerShell's own continuation character. `--end` is **exclusive**: this example includes market sessions up to 2026-10-16. Do not assume that these price histories are freely redistributable; snapshots are gitignored.

- Research allowlist: Xetra ticker `EUNL.DE` (MSCI World, ISIN IE00B4L5Y983) and `IS3N.DE` (EM IMI, ISIN IE00BKM4GZ66), both *EUR-traded* shares. Instruments are not automatically cleared for live brokerage execution.
- Downloads use raw/unadjusted daily OHLC (`auto_adjust=False`) and verify provider currency, completeness, gaps, OHLC bounds and major discontinuities. Zero reported volumes are retained and counted in the snapshot/report; zero-volume bars never generate buy/sell signals or fills. They do **not** establish market liquidity. Missing, negative and fractional volumes still fail. Data and metadata are SHA256-linked. A hash is for *accidental corruption detection*, not signed vendor provenance.
- The 15 bps spread field is an **assumption**, not a real quote. Fee default is EUR 1.25 per simulated fill; slippage assumption is 5 bps. Dividend distributions, split adjustments, tax, trading venue opening auctions and funding rates are NOT modeled: price-only research outcomes can be misleading. Any split/anomaly flagged requires a human review of the dataset.
- The portfolio is limited to EUR 1,000 in the scenario, with a EUR 2.50 planned per-trade stop-risk budget. For high-priced ETFs this can mean **zero trades**, which is an acceptable research result.
- Reports compare simulation against all-cash (0% price return) and each ETF's approximate next-session-open buy-and-hold (not risk matched). Optional holdout is descriptive; no hyperparameter optimization or walk-forward calibration has been built yet.
- Yahoo Finance/yfinance provides research/personal use data subject to applicable provider terms, not a licensed execution-quality dataset. Failures abort the download; no synthetic fallback during `backtest`.


## Structure

```text
src/ai_trading_fleet/
  agents.py       deterministic MarketScout, Quant, Skeptic, NewsStatus and Strategy roles
  data.py         defensive CSV data parser
  models.py       typed records and paper portfolio
  risk.py         hard-coded risk checks and order sizing
  execution.py    offline-only broker simulator, no network
  engine.py       end-of-day signals -> NEXT open only; audit trail
  marketdata.py   opt-in yfinance historical download + immutable snapshot SHA checks
  evaluation.py   cash and buy-and-hold baselines + descriptive holdout
  cli.py          offline demo, download-history, backtest CLI
  api.py          optional read-only local report UI
tests/             standard-library unittest safety/integrity checks
config/            proposed market universe, NOT an order whitelist for a real broker
data/              generated synthetic sample prices
.github/workflows/ci.yml  safe no-secret test workflow
docs/              architecture, security policy, phased roadmap
```

## Key design decisions

- Firstmate is a CODING assistant orchestration distribution; do not run it as the live trading core.
- TradingAgents is a separate LLM research framework; evaluate as advisory adapter in Sprint 2 after real-data benchmarks. Neither project is bundled.
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

### From your phone via GitHub (manual action)

In **Actions** select **Historical research backtest (manual only)** → **Run workflow**. Set date inputs (the end date is exclusive) and run. Download the `historical-research-report` artifact from that workflow run once successful. If Yahoo blocks GitHub-hosted runners, the workflow will fail closed; run the local CLI instead. No licensed raw market dataset is uploaded as a GitHub artifact, and no broker credentials are supported. This action is intentionally **never scheduled**.

## v0.3 – Fee-aware research (branch proposal)

This version remains offline historical simulation. **No actual trading, account credentials, LLM calls or broker APIs**. Starting capital remains EUR 1,000.

- Estimated two-way commissions and assumed bid/ask spread plus slippage are checked before allowing new purchases. Configured maximum estimated round-trip cost is 1.5% of proposed notional. At the existing 0.25%-NAV stop-distance risk per position, this may deliberately lead to **zero trades** with a EUR 1,000 account.
- Simulated executions include half the assumed spread *in addition to* slippage. Quotes are research OHLC prices; the 15-bps spread is a fixed assumption rather than measured historical bid/ask quotes.
- The offline 5% portfolio peak-to-current drawdown circuit breaker latches new purchases OFF for the remaining backtest; exits remain allowed. Resuming an actual deployed system will require independent approval and durable state management.
- Backtest reports add `capped_comparisons` (up to 20% initial investment, remainder cash, no stop, assumed entry costs), estimated trade cost limit, blocked candidate buy count and halt status.
- These benchmarks are **not risk-matched** and are price-only (without corporate actions/dividends/tax/real executable spreads); a good backtest is not proof of profitability.

Run the existing manual `Historical research backtest` GitHub Action to see changes in `historical-research-report`; offline unit tests are run by CI. See `docs/V0_3_DECISIONS.md`.

## v0.4 – Offline research comparison

**Still NO LLM agent, no broker API, no paper brokerage or live orders.** This separate research module runs three fixed experimental strategies against four *assumed* cost and whole/fractional share execution scenarios using the same EUR 1,000 simulated capital and existing 0.25%-of-equity planned stop-risk budget. Fractional shares and discounted/zero commissions are **hypothetical sensitivity experiments**, not verified broker capabilities or offers. The v0.3 backtest remains available unchanged.

Run `fleet compare-research --csv datasets/research/prices.csv --manifest datasets/research/manifest.json --holdout-start 2025-01-01 --out output/research-v04.json` on a previously downloaded and verified snapshot. Or from GitHub **Actions** manually run **v0.4 research cost and strategy comparison (manual only)**. Its `v04-research-comparison` artifact provides all twelve scenarios, costs, trades, risk metrics, audit-style rejections and descriptive holdout. The default CI remains network-free.

This is **not** a validated performance evaluation: unadjusted price-only OHLC data omit distributions and corporate actions, and the holdout has not been evaluated with a proper walk-forward design. See [docs/V0_4_RESEARCH.md](docs/V0_4_RESEARCH.md).

## v0.5 – Historical dividend events, chronological strategy selection and inert AI interface

> Offline research only: no live broker, no order API, no paid AI model, no actual investment.

v0.5 adds dividend event columns to new immutable research snapshots (`schema_version=2`), while reading legacy v1 snapshots without treating the entire history as if future dividends were known. Reported split actions are rejected pending human reconciliation. Ex-date cash dividends are approximated for **already held** ETF shares and compared in passive benchmarks; taxes and payment delays are not modeled. The two currently researched ETFs are accumulating share classes, so we expect no ordinary cash-dividend events for them.

The new `fleet forward-research` command chooses one of the three strategies from strictly earlier data (or CASH) under one *preselected* fee schedule, then tests only that choice in the later interval with a new EUR 1,000 virtual portfolio. A descriptive chronological split is **not** a genuine unseen independent forward test, especially since these dates have already been examined during v0.2–v0.4. See `docs/V0_5_RESEARCH.md`.

```bash
fleet download-history --start 2022-01-01 --end 2026-10-17 --out-dir datasets/new-v05
fleet forward-research --csv datasets/new-v05/prices.csv --manifest datasets/new-v05/manifest.json --split 2025-01-01 --cost fixed_1_25_whole --out output/forward-v05.json
```

Alternatively, manually start **v0.5 chronological research (manual only)** under GitHub Actions. Discounted-commission, fractional-share, and zero-commission models remain hypothetical until actual broker offerings are verified.

`fleet validate-advice --file note.json --asof 2025-06-02` checks the schema of future untrusted AI commentary but cannot execute or propose executable orders. There is still **no LLM or model API integrated**.
