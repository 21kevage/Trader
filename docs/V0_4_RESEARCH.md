# v0.4 — falsifiable, offline market research

## Goal and scope

Determine whether a €1,000 **simulated** research portfolio could even trade economically without relaxing its original planned-risk policy. Compare a deliberately fixed set of strategies and assumed broker-cost schedules. None of the fee schedules with discounts, fractional fills or zero commissions are advertised real-world offers or verified executable fills. The standard v0.3 simulation continues to exist independently.

## Research experiment

- **Data:** verified immutable market snapshot produced by the existing explicit-download command. ETFs: `EUNL.DE` and `IS3N.DE`, research only. No lookahead: signals use today's **close** (after a common ≥60-session warm-up); simulated executions use only the **next day open** with adverse assumed spread/slippage. Orders missing a valid next-session bar expire. Open positions are marked at each session close. A pending stop can encounter an adverse opening gap.
- **Swing:** SMA10 > SMA30 × 1.002 and positive 20-session momentum >0.5%; exit on weakening trend or the fixed 4% close-stop.
- **Monthly momentum:** at first available day of a month, require 60-session momentum >2% and close above the 60-session average; exit when the monthly condition fails or the 4% close-stop triggers.
- **One-shot hold with stop:** buy at most once per instrument after the warm-up, exit on a 4% close-stop (it is NOT a conventional stop-free buy-and-hold benchmark).
- **External benchmark:** buy-and-hold up to 20% initial capital, remaining capital held as zero-yield cash. Starts after common warm-up, but no stop and not risk-matched.
- **Comparison grid:** 3 strategies × 4 cost assumptions (12 cases), all with starting capital €1,000. Keep the strategy set and cost assumptions unchanged when examining the 2025–2026 holdout; results on this holdout are only descriptive and not a substitute for genuinely out-of-sample testing.

## Safeguards

- Preserve the original risk limits in *every* strategy cell: maximum 0.25% of account planned loss at 4% position stop, 20% NAV per holding, 60% gross exposure, maximum two buy executions each day, 3 concurrent holdings, 5 calendar day buy cooldown, 1% daily/2.5% weekly/5% total observed drawdown triggers. Portfolio 5% drawdown latches new buys off for remaining run; sells always allowed.
- Fractional simulated shares are quantized to 0.001 units. Do not infer any broker supports them. Transaction costs include **both** sides of commissions and assumed full spread + twice adverse slippage; no fills when estimated round-trip cost >1.5% of notional.
- This *standalone research* engine is intentionally not a BrokerAdapter: it has no network, no live paper API and no production pathway. Only the data-download command initiates network requests.
- The order book has no persistent broker order state, exchange calendar, actual opening auction depth, real spreads, variable fees, intraday stops, funding rates, taxes, corporate actions or distributions. The backtest is **not research-grade or independently validated**.

## Acceptance criteria for next work

1. GitHub CI passes all unit/regression tests; manual downloaded-data comparison completes and yields all 12 cases with clear zero-trade reasons where applicable.
2. Validate cost arithmetic, opening-gap stop losses, missing next-day bars, no same-session fills, cooldown, buying power, actual drawdown and exposure against independent reference implementations.
3. Obtain an actual target broker's executable fee schedule, supported fractional instruments, custody requirements and data license; replace illustrative profiles only after verification.
4. Add dividend/corporate-action adjusted, point-in-time data and true walk-forward design before making any strategy-selection or profitability claims. Start separate advisory LLM experiments only after research baselines are reproducible; AI must not bypass any safety policies.

Do not initiate real or paper broker orders from this repository version.
