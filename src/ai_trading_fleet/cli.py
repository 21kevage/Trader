from __future__ import annotations
import argparse
import json
from datetime import date
from pathlib import Path
from .data import load_csv, synthetic_data
from .engine import TradingFleet
from .risk import RiskPolicy


def _write_report(report: dict, out: Path):
    out.parent.mkdir(exist_ok=True, parents=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in {"curve", "fills", "audits"}}
    if "windows" in summary:
        summary["windows"] = [{"number": w["number"], "selected": w["selected_from_training_only"],
                                "evaluation": w["evaluation"]} for w in summary["windows"]]
    if "runs" in summary:
        summary["runs"] = [{k: v for k, v in run.items() if k not in {"curve", "fills"}}
                           for run in summary["runs"]]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Full offline report written to {out}")


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Research simulations only. No broker/order API.")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("run-demo", help="Offline synthetic demo")
    demo.add_argument("--csv", type=Path, default=Path("data/demo_prices.csv"))
    demo.add_argument("--out", type=Path, default=Path("output/report.json"))

    download = sub.add_parser("download-history", help="Explicit Yahoo/yfinance network research download")
    download.add_argument("--start", required=True, type=date.fromisoformat)
    download.add_argument("--end", required=True, type=date.fromisoformat, help="Exclusive end date")
    download.add_argument("--out-dir", type=Path, required=True, help="New, empty snapshot directory")

    historical = sub.add_parser("backtest", help="Offline backtest of a verified local snapshot")
    historical.add_argument("--csv", required=True, type=Path)
    historical.add_argument("--manifest", required=True, type=Path)
    historical.add_argument("--out", type=Path, default=Path("output/historical-report.json"))
    historical.add_argument("--holdout-start", type=date.fromisoformat)
    research = sub.add_parser("compare-research", help="v0.4 offline scenario grid, NO BROKER")
    research.add_argument("--csv", required=True, type=Path)
    research.add_argument("--manifest", required=True, type=Path)
    research.add_argument("--out", type=Path, default=Path("output/research-v04.json"))
    research.add_argument("--holdout-start", type=date.fromisoformat)
    forward = sub.add_parser("forward-research", help="v0.5 train-only model selection then isolated forward simulation")
    forward.add_argument("--csv", required=True, type=Path)
    forward.add_argument("--manifest", required=True, type=Path)
    forward.add_argument("--split", required=True, type=date.fromisoformat)
    forward.add_argument("--cost", required=True, choices=["fixed_1_25_whole", "hypothetical_0_25_whole",
                    "hypothetical_0_25_fractional", "zero_fee_fractional_sensitivity_ONLY"])
    forward.add_argument("--out", type=Path, default=Path("output/forward-v05.json"))
    walk = sub.add_parser("walk-forward", help="v0.6 rolling train-only selection and nonoverlapping forward windows")
    walk.add_argument("--csv", required=True, type=Path)
    walk.add_argument("--manifest", required=True, type=Path)
    walk.add_argument("--cost", required=True, choices=["fixed_1_25_whole", "hypothetical_0_25_whole",
                      "hypothetical_0_25_fractional", "zero_fee_fractional_sensitivity_ONLY"])
    walk.add_argument("--train-sessions", type=int, default=252)
    walk.add_argument("--test-sessions", type=int, default=63)
    walk.add_argument("--out", type=Path, default=Path("output/walk-forward-v06.json"))
    research_ai = sub.add_parser("research-ai", help="Explicit paid, read-only AI research note (NO BROKER)")
    research_ai.add_argument("--csv", required=True, type=Path)
    research_ai.add_argument("--manifest", required=True, type=Path)
    research_ai.add_argument("--symbol", required=True)
    research_ai.add_argument("--asof", required=True, type=date.fromisoformat)
    research_ai.add_argument("--model", default="gpt-4o-mini")
    research_ai.add_argument("--confirm-paid-api", action="store_true", required=False)
    research_ai.add_argument("--out", type=Path, default=Path("output/ai-research-note.json"))
    advice = sub.add_parser("validate-advice", help="Offline-only schema validation of non-actionable research notes")
    advice.add_argument("--file", required=True, type=Path)
    advice.add_argument("--asof", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)

    if args.command == "run-demo":
        policy = RiskPolicy()
        data = load_csv(args.csv, set(policy.permitted_symbols)) if args.csv.exists() else synthetic_data()
        _write_report(TradingFleet(policy).run(data), args.out)
    elif args.command == "download-history":
        from .marketdata import fetch_yahoo_snapshot
        csv_file, manifest_file = fetch_yahoo_snapshot(args.start, args.end, args.out_dir)
        print(f"Saved research snapshot: {csv_file} | {manifest_file}")
    elif args.command == "compare-research":
        from .marketdata import read_snapshot
        from .research_lab import compare
        dataset, manifest = read_snapshot(args.csv, args.manifest)
        report = compare(dataset, capital=1000.0, holdout_start=args.holdout_start)
        report["snapshot_sha256"] = manifest["sha256"]
        report["data_source"] = manifest["source"]
        _write_report(report, args.out)
    elif args.command == "forward-research":
        from .marketdata import read_snapshot
        from .forward_research import compare_forward
        dataset, manifest = read_snapshot(args.csv, args.manifest)
        report = compare_forward(dataset, split=args.split, selected_cost=args.cost)
        report["snapshot_sha256"] = manifest["sha256"]
        report["snapshot_schema"] = manifest["schema_version"]
        report["data_source"] = manifest["source"]
        report["dividend_events"] = manifest.get("dividend_events", {})
        _write_report(report, args.out)
    elif args.command == "walk-forward":
        from .marketdata import read_snapshot
        from .walk_forward import walk_forward
        dataset, manifest = read_snapshot(args.csv, args.manifest)
        report = walk_forward(dataset, cost=args.cost,
                              training_sessions=args.train_sessions,
                              evaluation_sessions=args.test_sessions)
        report["snapshot_sha256"] = manifest["sha256"]
        report["data_source"] = manifest["source"]
        report["snapshot_schema"] = manifest["schema_version"]
        _write_report(report, args.out)
    elif args.command == "research-ai":
        from .marketdata import read_snapshot
        from .ai_research import request_research_note
        if not args.confirm_paid_api:
            parser.error("Explicit --confirm-paid-api required; this API call may cost money")
        dataset, manifest = read_snapshot(args.csv, args.manifest)
        report = request_research_note(dataset, symbol=args.symbol, asof=args.asof,
                                       model=args.model, confirm_paid_api=True)
        report["snapshot_sha256"] = manifest["sha256"]
        _write_report(report, args.out)
    elif args.command == "validate-advice":
        from .advisory import validate_research_note
        from .marketdata import RESEARCH_UNIVERSE
        note = json.loads(args.file.read_text(encoding="utf-8"))
        print(json.dumps(validate_research_note(note, asof=args.asof,
              allowed_symbols=frozenset(RESEARCH_UNIVERSE)), ensure_ascii=False, indent=2))
    elif args.command == "backtest":
        from .marketdata import RESEARCH_UNIVERSE, read_snapshot
        from .evaluation import buy_and_hold, capped_buy_and_hold, summarize_holdout
        dataset, manifest = read_snapshot(args.csv, args.manifest)
        policy = RiskPolicy(permitted_symbols=frozenset(RESEARCH_UNIVERSE))
        report = TradingFleet(policy, data_mode="OFFLINE_HISTORICAL_BACKTEST_ONLY").run(dataset)
        report["snapshot_sha256"] = manifest["sha256"]
        report["source"] = manifest["source"]
        report["price_basis"] = manifest["quotes"]
        report["zero_volume_rows"] = manifest.get("zero_volume_rows", {})
        report["comparisons"] = {sym: buy_and_hold(dataset, sym) for sym in RESEARCH_UNIVERSE}
        report["capped_comparisons"] = {sym: capped_buy_and_hold(dataset, sym,
            fee=policy.assumed_fee, slippage_bps=policy.assumed_slippage_bps)
            for sym in RESEARCH_UNIVERSE}
        report["cash_baseline"] = {"initial_equity": 1000.0, "final_equity": 1000.0,
                                   "return_pct": 0.0, "ignores_cash_interest": True}
        if args.holdout_start:
            report["holdout"] = summarize_holdout(report["curve"], args.holdout_start)
        _write_report(report, args.out)

if __name__ == "__main__":
    main()
