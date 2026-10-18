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
