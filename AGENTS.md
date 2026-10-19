# Agent contract for future Firstmate coding crews

This is a software-development repository, NOT a broker execution channel.

## Permitted roles

- Scout: read-only code review and data provenance analysis.
- Implementer: changes in a dedicated Git worktree, PR only.
- Test crew: independent regression, adversarial risk tests, no secrets.
- Security reviewer: check fail-closed behavior, authorization, dependency and supply-chain risks.
- Maintainer / captain (human): authorize merges, rule changes and any deployment stage.

## Hard prohibitions

- Never request, read, store, print or commit broker API passwords, sessions or API tokens.
- Never connect this MVP to a real or paper brokerage account without a separately reviewed change.
- Never give LLMs access to a broker order tool or network destination for direct order placement.
- Never auto-merge changes to `risk.py`, `execution.py`, production config, secrets handling, or CI deployment permissions.
- Never hide failed tests or erase trade/audit events.
- Do not assert that synthetic profits validate a strategy.

## Quality gate

- Standard library `python -m unittest discover -s tests -v` passes.
- Reviewer confirms new strategy features use only information available at the decision time.
- Independent reviewer checks any risk, broker or authorization changes.
- PR describes risk model delta, test evidence, rollback path and data licensing.

## Historical research data (v0.2)
- `download-history` is the *only* intentionally networked research-download command; NEVER add network behavior to `run-demo`, `backtest`, test cases or CI.
- Hash and validate local snapshots before simulating; fail on unavailable or non-EUR price feeds.
- Do not treat dividend-ignorant/raw OHLC strategies as research-grade alpha; benchmark and full cost modeling must be reviewed before any brokerage integration.
- Do not let LLMs expand the allowlist or invoke a broker.

## v0.4 research guardrails
- `src/ai_trading_fleet/research_lab.py` and `fleet compare-research` run offline-only scenario analysis; no broker/client, LLM tool calls or account credentials.
- Do not loosen `RiskPolicy` to force profitable-looking results. Mark alternative commissions and fractional shares hypothetical and require real broker checks before any paper brokerage wiring.
- Do not claim a descriptive holdout is independent validation or select best 2025 holdout then reuse it as evidence.

## v0.5 new constraints
- Training strategy selection must depend on pre-split data only; never advertise the already-examined 2025+ dates as independent out-of-sample validation.
- Ex-date cash dividends may be counted only for prior holdings; fail closed for split actions and unverified provenance. Never substitute adjusted synthetic OHLC for broker fills.
- Research advice JSON must remain non-actionable: no API key handling, LLM calls, trade tool or order instructions. Validate exact schemas and timestamp bounds.
- Never treat a zero-fee or fractional-share sensitivity analysis as a verified broker capability.
