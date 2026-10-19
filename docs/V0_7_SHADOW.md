# v0.7: Mock AI shadow research and mobile report

**Status: no actual AI model is invoked.** This release uses a deterministic mathematical fixture pretending to emit an AI-style research note. Its output is always marked `MOCK_DETERMINISTIC_RULE_NOT_REAL_AI`, `not_real_ai=true`, `real_llm_calls=0`, `actual_orders=0`. All readouts are educational and never investment advice.

## Objective

Show the full end-to-end shape of a future observer-only agent process:

1. Download a verified historical snapshot **on explicit GitHub manual dispatch** only.
2. Generate per-ETF, per-session *mock* commentary from previous or current closing prices alone.
3. Compare this commentary with a separate deterministic quant indicator (not an actual approved trade).
4. Attach the later five-session price change when available; otherwise label `PENDING`. This retrospective diagnostic is **not a return that could have been earned** and is not prospective AI performance.
5. Present a responsive, completely standalone and script-free HTML report for a phone, plus a JSON audit and a GitHub Actions run summary.

**The mock does not place simulated orders or update portfolio holdings.** EUR 1,000 is a reference value and the capital at risk is zero. Our v0.6 rolling walk-forward remains available independently. There are no brokerage, execution, or credential imports in `shadow_research.py`, and it does not call the existing paid `research-ai` interface.

## Manually run on GitHub

Open **Actions → v0.7 MOCK AI shadow dashboard (manual only) → Run workflow**. The default historical range is 2025-01-01 to 2026-10-17 exclusive. The workflow will not fetch the current incomplete market session, since the default ends on 16 October 2026. The script uses the last ten weekly-spaced observations and a five-session observation horizon. Do not interpret the reported mock/rule agreement as trading profitability or AI forecast accuracy.

The **Summary** tab for the run contains an immediately readable summary. Under **Artifacts → v07-shadow-report** download the ZIP to open `v07-shadow.html` in your smartphone browser, offline. `v07-shadow.json` supplies full details and source hashes. HTML escapes all injected text; it does not require external scripts, fonts, tracking, or internet access.

## Local replay

```bash
pip install -e '.[market-data]'
fleet download-history --start 2025-01-01 --end 2026-10-17 --out-dir datasets/local
fleet shadow-demo --csv datasets/local/prices.csv --manifest datasets/local/manifest.json \
  --out output/v07-shadow.json --html output/v07-shadow.html
```

Snapshot data stays gitignored. CI runs **no market downloader and no AI**; unit tests use synthetic fixtures. A future optional paid model adapter exists as the distinct, opt-in local `fleet research-ai` CLI introduced in v0.6. Connecting that to ongoing research requires a separate user decision, a spend limit, and a strict provenance audit. It must not silently change any trading strategy.

## Honest limitations

- Historical research prices may lack point-in-time adjustments, distributions, and execution-grade spreads.
- The mock is deliberately untrained and has no validated performance. Its 50% confidence is a noncalibrated placeholder, not a probability.
- This is NOT live-paper brokerage; no automatic daily schedule or durable database is running. A human dispatches the workflow.
- Forward price labels recorded retrospectively do not validate a real AI prediction. Future testing must record real notes *before* the subsequent trading sessions occur and compare against matched-risk baselines.
- Broker credentials, real orders, ETF fractional availability, live execution and capital at risk remain out of scope.
