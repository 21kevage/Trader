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
