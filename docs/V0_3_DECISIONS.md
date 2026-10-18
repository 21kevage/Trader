# v0.3 rationale / gates

This release prioritizes reliable trading economics over attempting to optimize raw profits from a single historical sample.

- Sizing and 0.25% planned stop-distance risk budget for a EUR 1,000 research portfolio are unchanged; percentage risk does **not** guarantee max loss after price gaps.
- Entry execution prices include the previously omitted half-spread in addition to adverse slippage; the price feed's spread is only assumed, not observed executable data.
- Cost gate rejects new buys when estimated two-sided costs exceed 1.5% of proposed notional. This is an **engineering starting threshold**; reject-all is acceptable. Fees stay 1.25 EUR per side. Never silently switch to zero-fee fantasy brokers.
- A 5% peak-to-current-equity drawdown latches the research engine in no-new-buys for the rest of the run. No automatic cooldown reset after recovery. Selling risk is still permitted.
- Buy-and-hold and capped passive exposure comparisons are both price-only, unadjusted and not risk-equivalent to a stop-based active system. Report these limitations in evaluations.
- No live paper orders, no real money, no AI models, no deployed service and no private credentials.
- Next separate step: true point-in-time data and realistic corporate actions, walk-forward evaluation, cost sensitivity across broker fee schedules, independent strategy benchmarks; then compare optional AI advice to these controls.
