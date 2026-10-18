# Risk, security and operability policy

## Scope and limitations

MVP is **offline simulated historical replay using generated prices**, not a working LLM service, live quotes, real broker paper account, or a validated profitable strategy. Fixed stop references are checked at daily close with a proposed sale at next open. These are not guaranteed stop-loss orders and CANNOT guarantee the maximum loss after gaps/outages.

## Conservative reference policy for 1,000 EUR simulated account

- Max 20% NAV (~200 EUR) per position; max gross long exposure 60%; no borrowing/margin/shorting/options/CFDs.
- Max planned stop-distance risk 0.25% NAV (~2.50 EUR) per trade excluding transaction costs and gaps.
- 4% conceptual stop distance; at 1,000 EUR this usually means about 62 EUR position for the risk budget, *before integer-share rounding*.
- Circuit breaker blocks NEW purchases at 1% daily, 2.5% weekly or 5% from observed peak equity; a broker gap can lose more than these figures.
- Max 2 new orders/filled orders per trading day, cooldown 5 calendar days, no pyramiding.
- Spread must be <=35 bps; any missing quote/invalid bar/excluded instrument must fail closed.
- Simulated fee EUR 1.25 each fill + 5 bps slippage. Actual broker/exchange fees, FX charges and bid-ask spread may differ. Current simulator does NOT explicitly model additional half-spread costs.
- Never loosen limits based on LLM recommendation or a good backtest.

## Security controls needed BEFORE connecting even a paper brokerage account

1. Secrets only in a password vault / cloud secret manager, not Git commits, logs, browser JavaScript or prompts. No re-use of production credentials for tests. Rotate after any accidental exposure.
2. External news, website and filings are untrusted DATA; no prompt instructions, URLs, or embedded code may directly invoke shell/filesystem/broker actions. Use structured schema and allowlists.
3. Coding agents and trading agents run with distinct users, containers and networks. CI has no broker credentials. No code changes in runtime by LLMs. Branch protection and pinned dependencies.
4. Trading execution is separate, has least-privilege broker access, TLS and authentication; no order endpoint from the read-only dashboard. Never expose IB Gateway/TWS API ports to the public internet.
5. Real trading requires account reconciliation before each batch, durable idempotency keys, order status state machine, broker-side limits where offered, stale-feed detection, configurable kill switch and alerts.
6. Paper and live accounts must have separate credentials/configuration and deployment approval; no runtime "LIVE=true" switch in the same unaudited environment. Hard production allowlisting/limits independently verified.
7. Alert on latency, provider outages, broker disconnect, data gaps, duplicate orders, market-data mismatch, >expected fees, rapid drawdown and unrecognized position changes. Default to new-trade OFF.
8. Minimal broker and trade data retention, no sensitive secrets in LLM context, encrypted backup and audit history with retention strategy. Record decision timestamp, data snapshot hash, model/prompt versions and execution responses.
9. Security tests: malicious news prompt injection, replay orders, stale quotes, wrong instrument, corrupted price, gap beyond stop, disconnected broker, restart mid-order, duplicated webhook, lost reconciliation, privilege escalation.
10. Tax: maintain exportable order/fill/FX/corporate-action records; check applicable German tax reporting with broker or tax professional.

## Broker reality check

Interactive Brokers supports TWS API/PaperTrader, but paper fills differ from live fills. Official IBKR docs also state GUI authentication is required for TWS / IB Gateway, and unattended headless login is not supported. Expect periodic manual re-authentication and design reconnection procedures, rather than promising a 24/7 fully hands-off service. Live market data via its API generally requires appropriate market-data subscriptions.

## Go/no-go for limited live pilot

- Backtest on licensed verified historical data, with date-safe feature generation and survivorship-free universe. Out-of-sample / walk-forward regimes, simulated market and broker costs.
- At least 90 live market sessions on broker paper environment, sufficiently many closed trades for significance, positive AFTER-FEE results relative to simple ETF buy-and-hold and cash benchmarks; no breached policy, unmatched broker executions, or unexplained operational failures.
- Re-test under 2x transaction costs, delayed data, missing trades, adverse execution and plausible price-gap shock; fail if an edge depends entirely on narrow parameter optimization.
- Monitoring + emergency disable demonstrably tested, manual live enable approval, legal/product access verified, loss-bearing budget explicitly separated.
- Proposed live pilot is separately approved e.g. 500–1,000 EUR funded, small positions and without leverage, but per-order costs may make it economically pointless at that size. Do not initiate until after a separate review.

Passing thresholds never establishes certainty of profitability. If insufficient data, the correct decision is no live deployment.
