"""Explicit, opt-in research downloads; no live quotes or brokerage credentials.

Stores raw unadjusted daily OHLC for reproducibility. Corporate actions and cash
income are NOT accounted for: results are preliminary price-only comparisons.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path

from .data import load_csv

# Only Yahoo/Xetra tickers; not an authorization to place real trades.
RESEARCH_UNIVERSE = {
    "EUNL.DE": {"isin": "IE00B4L5Y983", "venue": "XETRA", "currency": "EUR"},
    "IS3N.DE": {"isin": "IE00BKM4GZ66", "venue": "XETRA", "currency": "EUR"},
}
FIELDNAMES = ["date", "symbol", "open", "high", "low", "close", "volume", "spread_bps"]


class MarketDataError(ValueError):
    """Fail closed rather than silently accepting suspect market data."""


def _validate_rows(rows: list[dict], *, minimum_bars: int = 90) -> None:
    per_symbol: dict[str, list[dict]] = {ticker: [] for ticker in RESEARCH_UNIVERSE}
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
        if not isfinite(vol) or vol <= 0 or int(vol) != vol:
            raise MarketDataError("Zero, missing or fractional volume")
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
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(rows, key=lambda row: (row["date"], row["symbol"])))
    return buffer.getvalue().encode("utf-8")


def write_snapshot(rows: list[dict], destination: str | Path, *, start: date,
                   end: date, received_currencies: dict[str, str],
                   minimum_bars: int = 90) -> tuple[Path, Path]:
    """Validate all symbols before writing the immutable CSV and SHA256 manifest."""
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
    # Refuse to overwrite an experiment, to keep published run provenance stable.
    csv_path, manifest_path = destination / "prices.csv", destination / "manifest.json"
    if csv_path.exists() or manifest_path.exists():
        raise MarketDataError("Destination has a snapshot; use a new directory")
    raw = _csv_bytes(rows)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": 1,
        "source": "Yahoo Finance via yfinance (research/personal-use only)",
        "obtained_utc": datetime.now(timezone.utc).isoformat(),
        "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
        "currency": "EUR", "quotes": "unadjusted OHLC, price-only; no dividend or split accounting",
        "assumed_spread_bps": 15, "symbols": RESEARCH_UNIVERSE,
        "rows": len(rows), "sha256": digest,
    }
    # Create manifest only after validated CSV has been persisted.
    csv_path.write_bytes(raw)
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except Exception:
        csv_path.unlink(missing_ok=True)
        raise
    return csv_path, manifest_path


def read_snapshot(csv_path: str | Path, manifest_path: str | Path):
    """Recheck provenance and content; rejects edited/incomplete/foreign datasets."""
    csv_path, manifest_path = Path(csv_path), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = csv_path.read_bytes()
    if (manifest.get("schema_version") != 1 or manifest.get("currency") != "EUR"
        or manifest.get("symbols") != RESEARCH_UNIVERSE
        or manifest.get("sha256") != hashlib.sha256(raw).hexdigest()
        or manifest.get("quotes") != "unadjusted OHLC, price-only; no dividend or split accounting"):
        raise MarketDataError("Snapshot manifest/provenance verification failed")
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != manifest.get("rows"):
        raise MarketDataError("Snapshot row count differs from manifest")
    _validate_rows(rows)
    start, end = date.fromisoformat(manifest["start_inclusive"]), date.fromisoformat(manifest["end_exclusive"])
    if any(not start <= date.fromisoformat(row["date"]) < end for row in rows):
        raise MarketDataError("Out-of-range bar in snapshot")
    return load_csv(csv_path, set(RESEARCH_UNIVERSE)), manifest


def fetch_yahoo_snapshot(start: date, end: date, out_dir: str | Path):
    """Network ONLY when user explicitly runs download-history; optional yfinance."""
    if start >= end or end > date.today():
        raise MarketDataError("End date is exclusive and cannot be in the future")
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataError('Install optional dependency: pip install -e ".[market-data]"') from exc
    rows: list[dict] = []
    currencies: dict[str, str] = {}
    for ticker in RESEARCH_UNIVERSE:
        instrument = yf.Ticker(ticker)
        # Verify a provider-reported quote currency, not simply the ticker suffix.
        try:
            currency = instrument.fast_info["currency"]
        except Exception as exc:
            raise MarketDataError(f"Currency not verifiable for {ticker}") from exc
        if currency != "EUR":
            raise MarketDataError(f"Currency mismatch for {ticker}: {currency!r}")
        currencies[ticker] = currency
        frame = instrument.history(start=start.isoformat(), end=end.isoformat(),
                                   interval="1d", auto_adjust=False, actions=False,
                                   raise_errors=True)
        if frame is None or frame.empty:
            raise MarketDataError(f"No data for {ticker}")
        for timestamp, bar in frame.iterrows():
            rows.append({"date": timestamp.date().isoformat(), "symbol": ticker,
                         "open": float(bar["Open"]), "high": float(bar["High"]),
                         "low": float(bar["Low"]), "close": float(bar["Close"]),
                         "volume": int(bar["Volume"]), "spread_bps": 15})
    return write_snapshot(rows, out_dir, start=start, end=end, received_currencies=currencies)
