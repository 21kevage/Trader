from __future__ import annotations
import csv
from math import isfinite
from collections import defaultdict
from datetime import date
from pathlib import Path
from .models import Bar

def load_csv(path: str | Path, allowed: set[str], *, allow_zero_volume: bool = False) -> dict[date, dict[str, Bar]]:
    result: dict[date, dict[str, Bar]] = defaultdict(dict)
    with Path(path).open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            symbol = row["symbol"]
            if symbol not in allowed:
                raise ValueError(f"Unexpected symbol {symbol!r}; universe is fixed")
            bar = Bar(
                date=date.fromisoformat(row["date"]), symbol=symbol,
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=int(row["volume"]), spread_bps=float(row.get("spread_bps", 15)),
            )
            if (any(not isfinite(v) or v <= 0 for v in (bar.open, bar.high, bar.low, bar.close))
                or bar.volume < 0 or (bar.volume == 0 and not allow_zero_volume)):
                raise ValueError("Invalid price or volume")
            if not isfinite(bar.spread_bps) or bar.spread_bps < 0:
                raise ValueError("Invalid spread")
            if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
                raise ValueError("OHLC data inconsistent")
            if symbol in result[bar.date]:
                raise ValueError("Duplicate symbol/date")
            result[bar.date][symbol] = bar
    if not result:
        raise ValueError("Empty dataset")
    return dict(sorted(result.items()))


def synthetic_data(days: int = 180) -> dict[date, dict[str, Bar]]:
    """Reproducible, openly synthetic data; no external feed, no forecasts."""
    from datetime import timedelta
    from math import sin
    start = date(2025, 10, 1)
    levels = {"DEMO_WORLD": 30.0, "DEMO_BONDS": 24.0, "DEMO_CASH": 20.0}
    out: dict[date, dict[str, Bar]] = {}
    for i in range(days):
        day = start + timedelta(days=i)
        if day.weekday() > 4:
            continue
        row = {}
        for j, (symbol, base) in enumerate(levels.items()):
            c = round(base * (1 + 0.001 * i + 0.035 * sin(i / (9+j*4))), 4)
            o = round(c * (1 - .002 * sin(i + j)), 4)
            row[symbol] = Bar(day, symbol, o, max(c, o)*1.004, min(c, o)*.996, c, 1000000, 12+j*4)
        out[day] = row
    return out
