from __future__ import annotations
import argparse
import json
from pathlib import Path
from .data import load_csv, synthetic_data
from .engine import TradingFleet
from .risk import RiskPolicy

def main():
    parser = argparse.ArgumentParser(description="OFFLINE demo only: synthetic prices, no broker")
    parser.add_argument("command", choices=["run-demo"])
    parser.add_argument("--csv", type=Path, default=Path("data/demo_prices.csv"))
    parser.add_argument("--out", type=Path, default=Path("output/report.json"))
    args = parser.parse_args()
    if args.command == "run-demo":
        policy = RiskPolicy()
        data = load_csv(args.csv, set(policy.permitted_symbols)) if args.csv.exists() else synthetic_data()
        report = TradingFleet(policy).run(data)
        args.out.parent.mkdir(exist_ok=True, parents=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {k: v for k, v in report.items() if k not in {"curve", "fills", "audits"}}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"Full report written to {args.out}")

if __name__ == "__main__":
    main()
