"""Opt-in research data snapshots: prices + ex-date dividend cash flows.

Not an execution feed. Yahoo raw Close is typically split adjusted already. We
reject *reported* stock splits rather than risk double-counting them. Dividend
cash is booked on the ex-date for research only, not on actual settlement date.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path

from .data import load_csv

RESEARCH_UNIVERSE = {
    "EUNL.DE": {"isin": "IE00B4L5Y983", "venue": "XETRA", "currency": "EUR"},
    "IS3N.DE": {"isin": "IE00BKM4GZ66", "venue": "XETRA", "currency": "EUR"},
}
FIELDNAMES_V1 = ["date", "symbol", "open", "high", "low", "close", "volume", "spread_bps"]
FIELDNAMES = FIELDNAMES_V1 + ["dividend"]
PRICE_BASIS_V1 = "unadjusted OHLC, price-only; no dividend or split accounting"
PRICE_BASIS_V2 = ("raw provider OHLC, ex-date cash dividend approximation; "
                  "split events rejected, not adjusted total-return bars")


class MarketDataError(ValueError):
    """Fail closed rather than silently accepting corrupt or incomplete prices."""


def _validate_rows(rows: list[dict], *, minimum_bars: int = 90) -> None:
    per_symbol = {ticker: [] for ticker in RESEARCH_UNIVERSE}
    seen = set()
    for row in rows:
        symbol = row["symbol"]
        if symbol not in per_symbol:
            raise MarketDataError("Unknown research ticker")
        key = (symbol, row["date"])
        if key in seen:
            raise MarketDataError("Duplicate OHLC date")
        seen.add(key)
        values = [float(row[k]) for k in ("open", "high", "low", "close")]
        if not all(isfinite(x) and x > 0 for x in values):
            raise MarketDataError("Missing, nonfinite or nonpositive market price")
        opening, high, low, closing = values
        if not (low <= opening <= high and low <= closing <= high):
            raise MarketDataError("Invalid OHLC ordering")
        vol = float(row["volume"])
        if not isfinite(vol) or vol < 0 or int(vol) != vol:
            raise MarketDataError("Missing, negative or fractional volume")
        div = float(row.get("dividend", 0) or 0)
        if not isfinite(div) or div < 0:
            raise MarketDataError("Missing, negative or nonfinite dividend")
        per_symbol[symbol].append(row)
    for ticker, ticker_rows in per_symbol.items():
        if len(ticker_rows) < minimum_bars:
            raise MarketDataError(f"Too few usable bars for {ticker}: {len(ticker_rows)}")
        ordered = sorted(ticker_rows, key=lambda r: r["date"])
        for old, new in zip(ordered, ordered[1:]):
            days = (date.fromisoformat(new["date"]) - date.fromisoformat(old["date"])).days
            if days > 12:
                raise MarketDataError(f"Suspicious market-data gap in {ticker}: {days} days")
            ratio = float(new["close"]) / float(old["close"])
            if ratio < .55 or ratio > 1.45:
                raise MarketDataError(f"Possible unhandled split or data anomaly in {ticker}")


def _csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(({**r, "dividend": r.get("dividend", 0)} for r in rows),
                           key=lambda r: (r["date"], r["symbol"])))
    return buffer.getvalue().encode("utf-8")


def write_snapshot(rows: list[dict], destination: str | Path, *, start: date,
                   end: date, received_currencies: dict[str, str],
                   minimum_bars: int = 90) -> tuple[Path, Path]:
    if end <= start or end > date.today():
        raise MarketDataError("Invalid requested historical period")
    if received_currencies != {ticker: "EUR" for ticker in RESEARCH_UNIVERSE}:
        raise MarketDataError("Data feed must confirm EUR for every ticker")
    for row in rows:
        when = date.fromisoformat(row["date"])
        if not start <= when < end:
            raise MarketDataError("Price date outside requested interval")
    _validate_rows(rows, minimum_bars=minimum_bars)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path, manifest_path = destination / "prices.csv", destination / "manifest.json"
    if csv_path.exists() or manifest_path.exists():
        raise MarketDataError("Destination has a snapshot; use a new directory")
    raw = _csv_bytes(rows)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": 2,
        "source": "Yahoo Finance via yfinance (research/personal-use only)",
        "obtained_utc": datetime.now(timezone.utc).isoformat(),
        "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
        "currency": "EUR", "quotes": PRICE_BASIS_V2,
        "assumed_spread_bps": 15, "symbols": RESEARCH_UNIVERSE,
        "rows": len(rows), "sha256": digest,
        "zero_volume_rows": {ticker: sum(row["symbol"] == ticker and int(row["volume"]) == 0
                                         for row in rows) for ticker in RESEARCH_UNIVERSE},
        "dividend_events": {ticker: sum(row["symbol"] == ticker and float(row.get("dividend", 0) or 0) > 0
                                        for row in rows) for ticker in RESEARCH_UNIVERSE},
        "dividend_treatment": "ex-date cash attribution; payment timing and tax excluded",
        "splits": "reported split events rejected at download",
    }
    csv_path.write_bytes(raw)
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except Exception:
        csv_path.unlink(missing_ok=True)
        raise
    return csv_path, manifest_path


def read_snapshot(csv_path: str | Path, manifest_path: str | Path):
    csv_path, manifest_path = Path(csv_path), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = csv_path.read_bytes()
    version = manifest.get("schema_version")
    price_basis = PRICE_BASIS_V2 if version == 2 else PRICE_BASIS_V1
    if (version not in (1, 2) or manifest.get("currency") != "EUR"
        or manifest.get("symbols") != RESEARCH_UNIVERSE
        or manifest.get("sha256") != hashlib.sha256(raw).hexdigest()
        or manifest.get("quotes") != price_basis):
        raise MarketDataError("Snapshot manifest/provenance verification failed")
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != (FIELDNAMES if version == 2 else FIELDNAMES_V1):
            raise MarketDataError("Snapshot columns do not match schema version")
        rows = list(reader)
    if len(rows) != manifest.get("rows"):
        raise MarketDataError("Snapshot row count differs from manifest")
    _validate_rows(rows)
    start, end = date.fromisoformat(manifest["start_inclusive"]), date.fromisoformat(manifest["end_exclusive"])
    if any(not start <= date.fromisoformat(row["date"]) < end for row in rows):
        raise MarketDataError("Out-of-range bar in snapshot")
    zero_counts = {ticker: sum(row["symbol"] == ticker and int(row["volume"]) == 0
                               for row in rows) for ticker in RESEARCH_UNIVERSE}
    if manifest.get("zero_volume_rows", zero_counts) != zero_counts:
        raise MarketDataError("Zero-volume metadata mismatch")
    div_counts = {ticker: sum(row["symbol"] == ticker and float(row.get("dividend", 0) or 0) > 0
                             for row in rows) for ticker in RESEARCH_UNIVERSE}
    if version == 2 and manifest.get("dividend_events") != div_counts:
        raise MarketDataError("Dividend metadata mismatch")
    return load_csv(csv_path, set(RESEARCH_UNIVERSE), allow_zero_volume=True), manifest


def fetch_yahoo_snapshot(start: date, end: date, out_dir: str | Path):
    """Opt-in external research download; never a broker/CI side-effect."""
    if start >= end or end > date.today():
        raise MarketDataError("End date is exclusive and cannot be in the future")
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataError('Install optional dependency: pip install -e ".[market-data]"') from exc
    rows = []
    currencies = {}
    for ticker in RESEARCH_UNIVERSE:
        instrument = yf.Ticker(ticker)
        try:
            currency = instrument.fast_info["currency"]
        except Exception as exc:
            raise MarketDataError(f"Currency not verifiable for {ticker}") from exc
        if currency != "EUR":
            raise MarketDataError(f"Currency mismatch for {ticker}: {currency!r}")
        currencies[ticker] = currency
        frame = instrument.history(start=start.isoformat(), end=end.isoformat(),
                                   interval="1d", auto_adjust=False, actions=True,
                                   raise_errors=True)
        if frame is None or frame.empty:
            raise MarketDataError(f"No data for {ticker}")
        if "Dividends" not in frame.columns or "Stock Splits" not in frame.columns:
            raise MarketDataError(f"Missing corporate-action columns for {ticker}")
        for timestamp, bar in frame.iterrows():
            split = float(bar["Stock Splits"])
            if not isfinite(split) or split != 0:
                raise MarketDataError(f"Reported stock split in {ticker} on {timestamp.date()}; manual reconciliation required")
            volume = float(bar["Volume"])
            if not isfinite(volume) or volume < 0 or int(volume) != volume:
                raise MarketDataError(f"Bad volume from vendor for {ticker}")
            rows.append({"date": timestamp.date().isoformat(), "symbol": ticker,
                         "open": float(bar["Open"]), "high": float(bar["High"]),
                         "low": float(bar["Low"]), "close": float(bar["Close"]),
                         "volume": int(volume), "spread_bps": 15,
                         "dividend": float(bar["Dividends"])})
    return write_snapshot(rows, out_dir, start=start, end=end, received_currencies=currencies)
