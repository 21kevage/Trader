# v0.6 – Rolling walk-forward plus opt-in AI research commentary

**Scope: offline historical research and isolated, optional paid AI commentary; NO live quotes, broker orders, paper broker connection or real-money trading.** Starting capital is **EUR 1,000** for each *independent* window.

## 1. Rolling walk-forward (manual GitHub workflow)

`fleet walk-forward --csv datasets/research/prices.csv --manifest datasets/research/manifest.json --cost hypothetical_0_25_fractional --train-sessions 252 --test-sessions 63 --out output/walk-forward-v06.json`

- For each quarter-sized, **nonoverlapping test period**, the previous **252 trading sessions** are used to choose from 3 fixed deterministic strategies (`swing`, `monthly_momentum`, `one_shot_stop`). The test period contributes **nothing to its own selection**. Then the train window advances by 63 sessions, repeating with newly available previously evaluated history (normal walk-forward).
- Training score is unchanged from v0.5: net simulated return (%) minus half of historical maximum drawdown (%). Eligible strategies require >=1 completed trade and positive score, otherwise **CASH**. Costs are fixed **before** research, not optimized.
- Each test period uses a *new EUR 1,000 portfolio* with past 61 price bars to warm trend features **without historical positions, orders, payouts or cash carry-over**. Adjacent forward periods never overlap. This checks repeated selection robustness but does **not** create one continuous live-trading history.
- A separate 20%-initial-exposure ETF buy-and-hold benchmark is displayed for each forward period, but is NOT risk-matched. Like the existing benchmark it buys at next open; open positions are marked at period end without final sales/exit fees.
- Summary: how often selection chooses CASH vs active, number of positive/negative windows, mean and median *per-window* returns, assumed commissions and trade counts. **DO NOT COMPOUND** those individual window returns or claim a yearly performance based on their arithmetic average.
- The 2022–2026 era has already been examined in the project: despite the rolling chronology, results do **not** constitute genuinely untouched out-of-sample validation.

GitHub Actions → **v0.6 rolling walk-forward research (manual only)**. Defaults: start `2022-01-01`, exclusive end `2026-10-17`, hypothetical fractional/0.25 EUR fee scenario, 252 prior bars and 63 following sessions. Data fetch requires explicit user action and outputs only a JSON report, **never raw market vendor data**. GitHub CI does not fetch data.

## 2. Optional actual AI read-only commentary (manual local invocation ONLY)

No AI API keys exist in this repo or CI. This mode is **completely independent** of walk-forward strategy selection and trade execution. It uses a bounded numeric-only observation (last 61 closing prices reduced to 20/60 session momentum, mean, last 5 closing quotes), with no news, web content, account balances or trading credentials.

```bash
python -m pip install -e '.[market-data,ai-research]'
# Make a local validated data snapshot with fleet download-history if needed.
# Set OPENAI_API_KEY locally via your OS secret store / environment; never paste it in GitHub Actions.
fleet research-ai --csv datasets/research/prices.csv \
  --manifest datasets/research/manifest.json \
  --symbol EUNL.DE --asof 2026-10-16 \
  --model gpt-4o-mini --confirm-paid-api \
  --out output/ai-research-note.json
```

- **Requires** `--confirm-paid-api` and a locally configured `OPENAI_API_KEY`. One OpenAI Responses API call with `store=False`, no tools, no streaming, max output tokens 600, structured JSON; it **may incur API charges**. No scheduled calls or GitHub Actions secret setup.
- The model has no ability to choose a new symbol, alter RiskPolicy, decide execution, see credentials or perform API functions beyond generating strict commentary with stance (`BULLISH`, `BEARISH`, `NEUTRAL`), confidence, reasoning and 1–5 cited *provided session dates*.
- Returned content undergoes independent schema validation. Extra fields such as `order`, `quantity`, `broker`, future dates, unknown evidence, malformed JSON, refusals, and incomplete responses cause failures. Do not treat a valid JSON schema as proof of true reasoning: commentary could still be inaccurate.
- Use is *forward research reading only*. **No AI suggestions feed into run_scenario or walk-forward strategy selection**, so any existing backtest comparison remains AI-free. Before using AI as part of a strategy, define a forward-only evaluation protocol and compare model expenses and uncertainty against baseline.
- OpenAI Python SDK uses a paid API account **separate from the ChatGPT subscription**. Do not place keys, costs, identity, sensitive documents or accounts in prompts.

## 3. Remaining blockers before paper-broker connectivity

1. Verify lawful, reliable adjusted market data, corporate actions and point-in-time instrument listings. Our Yahoo feed is unadjusted/price-only and not execution grade.
2. Confirm real broker minimum commission, ETF fractional order support, minimum investment, venue, settlement, spread/liquidity and German tax recording. All discount/fractional models remain **hypothetical**.
3. Validate truly new periods not observed during model development, benchmark risks, bootstrap confidence and strategy stability across regimes; implement a real continuous evaluation with controlled boundary handling.
4. Add authenticated read-only monitoring, persistent order ledger, broker reconciliation, independent hard trade gating, idempotency, incident alerts and a proven kill switch before any broker-paper pilot.
5. Paper-broker trial for 90+ market sessions and separately explicit human go-live approval, if independently convincing. No automatic escalation from v0.6.
