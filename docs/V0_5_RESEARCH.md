# v0.5 – Chronological research and inert AI advice interface

**Offline research only. No LLM calls, broker connection, live orders, deployment, or real-money access.**

## Why v0.5

The v0.4 grid tested 3 predetermined strategies against 4 hypothetical cost models using two EUR Xetra ETF symbols. Looking at returns across the full period and choosing the best introduces **selection bias**. We can improve chronology without claiming genuinely untouched independent results.

## Chronological split

`fleet forward-research --csv ... --manifest ... --split 2025-01-01 --cost fixed_1_25_whole`

- The **user preselects one cost schedule**; it is not optimized based on results. Lower-commission, fractional-share scenarios are only hypotheses. Broker support has not been verified.
- Train the choice among the three fixed strategies using **only data before `--split`**. Score = training net portfolio return (%) minus 0.5 × training maximum drawdown (%), with at least one closed round trip and score > 0; otherwise choose CASH. All scoring thresholds are explicit, not evidence of statistical significance.
- Evaluate **only that selected choice** from `--split` onward with EUR 1,000 fresh capital. Before the split, past prices only warm indicators; no previous positions, transactions, or dividend cash transfer into the evaluation account.
- Passively-held ETFs are displayed separately (20% initial allocation and no stop) **without claiming stop-risk matching**. No credit is given for interest on cash.
- This is **one descriptive chronological split, not rigorous walk-forward optimization and not independent out-of-sample proof**. The project developers have already seen 2025–2026 data from v0.2–v0.4, contaminating any claim that this period is unseen.
- A genuine new-data test requires a fresh later period not examined during development, plus rolling windows, unchanged hypotheses and decision timestamps.

## Dividend and corporate-action approach

- Snapshot schema v2 adds `dividend` (EUR cash per ETF unit, **ex-date**), source field from Yahoo Finance history (`actions=True`, `auto_adjust=False`). It remains SHA256-linked to an explicit, immutable CSV and the research-only manifest. Schema v1 snapshot reading remains supported.
- Credit distributions only for positions owned **before the ex-date session opens**; on ex-date this is a simplified cash entitlement, **not actual dividend payment or German tax calculation**. Benchmarks count payments after their buy date.
- Reported nonzero split events **abort** the download. Raw Yahoo historic OHLC may already be split-adjusted; until corporate actions are independently reconciled, this system must not guess adjusted order quantities.
- **Both currently tested ETFs are accumulating products.** We expect no ordinary cash distributions for these share classes; this feature may have *zero observable effect* on the current ETF universe. Accumulation is reflected in fund value instead.
- This does **not** make historical data point-in-time licensed, execution-quality or fully total-return correct. Bid-ask spreads, exchange liquidity, and slippage remain assumptions.

## AI-research note contract

`fleet validate-advice --file note.json --asof 2025-06-02` validates an **inert research note**, containing exactly:

```json
{
  "schema_version": 1,
  "date": "2025-06-02",
  "symbol": "EUNL.DE",
  "stance": "NEUTRAL",
  "confidence": 0.3,
  "rationale": "Trend strength is not persuasive from available evidence.",
  "evidence": [{"date": "2025-05-30", "summary": "Historic price-only research observation"}]
}
```

The validator rejects unknown symbols, dates after the stated decision time, additional fields (including broker-order instructions), invalid confidence and malformed evidence. It returns a deliberately non-actionable summary with `broker_connected: false`. **No actual AI service or paid model is connected; the interface merely prepares a future advisory integration.**

## Remaining work before broker paper integration

1. Legitimate vendor/venue data and complete corporate action verification (including tax and pay-date handling if necessary).
2. Deterministic realistic fee schedules from a chosen broker (currently not confirmed).
3. Actual rolling walk-forward, broad market regimes, liquidity checks, risk-matched baselines, reproducibility and statistical uncertainty.
4. Human-reviewed optional LLM suggestions, versioned prompts, independent skepticism, token budgets, injection defense, and **zero privilege to trade**.
5. Separate paper-broker adapter with durable order ledger/reconciliation, kill switch, monitoring, authentication.

**Any investment losses in a later live pilot could exceed planned stop-distance estimates.**
