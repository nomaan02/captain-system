# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Update VIX and VXV (VIX3M) daily close CSVs from Yahoo Finance.

Fetches yesterday's closing values via Yahoo Finance v8 chart API
(no API key required) and appends to the bundled CSVs if not already present.

Idempotent: safe to run multiple times — skips dates already in file.

Usage: python scripts/update_vix_daily.py
"""

import csv
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Resolve paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
VIX_CSV = REPO_ROOT / "data" / "vix" / "vix_daily_close.csv"
VXV_CSV = REPO_ROOT / "data" / "vix" / "vxv_daily_close.csv"

# Yahoo Finance chart API — returns JSON, no auth needed
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"

SYMBOLS = [
    {"symbol": "^VIX", "csv_path": VIX_CSV, "col_name": "vix_close", "label": "VIX"},
    {"symbol": "^VIX3M", "csv_path": VXV_CSV, "col_name": "vxv_close", "label": "VXV"},
]


def _fetch_yahoo_daily(symbol: str) -> list[tuple[date, float]]:
    """Fetch recent daily closes from Yahoo Finance v8 chart API.

    Returns list of (date, close) pairs for the last ~5 trading days.
    """
    url = YAHOO_URL.format(symbol=symbol)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (captain-system VIX updater)",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  [ERR] Yahoo Finance HTTP {e.code} for {symbol}: {e.reason}")
        return []
    except (urllib.error.URLError, OSError) as e:
        print(f"  [ERR] Network error fetching {symbol}: {e}")
        return []

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        print(f"  [ERR] Unexpected Yahoo Finance response format for {symbol}")
        return []

    pairs = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        pairs.append((d, round(close, 2)))

    return pairs


def _get_last_date_in_csv(csv_path: Path, date_col: str = "date") -> date | None:
    """Read the last date present in a CSV file."""
    if not csv_path.exists():
        return None
    last = None
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                last = datetime.strptime(row[date_col].strip(), "%Y-%m-%d").date()
            except (KeyError, ValueError):
                continue
    return last


def _append_rows(csv_path: Path, col_name: str, rows: list[tuple[date, float]]) -> int:
    """Append new rows to CSV. Returns count of rows appended."""
    last_date = _get_last_date_in_csv(csv_path)
    new_rows = []
    for d, close in sorted(rows):
        if last_date and d <= last_date:
            continue
        new_rows.append((d, close))

    if not new_rows:
        return 0

    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        for d, close in new_rows:
            f.write(f"{d.strftime('%Y-%m-%d')},{close}\n")

    return len(new_rows)


def update_all() -> dict:
    """Fetch and append VIX + VXV data. Returns summary dict."""
    results = {}
    for spec in SYMBOLS:
        label = spec["label"]
        csv_path = spec["csv_path"]

        if not csv_path.exists():
            print(f"  [SKIP] {label}: CSV not found at {csv_path}")
            results[label] = "csv_missing"
            continue

        last_date = _get_last_date_in_csv(csv_path)
        print(f"  {label}: last CSV date = {last_date}")

        # If already up to date (last date is yesterday or today), skip fetch
        today = date.today()
        if last_date and last_date >= today - timedelta(days=1):
            # Could still be missing today for weekday after market close
            # but fetch anyway to check
            pass

        pairs = _fetch_yahoo_daily(spec["symbol"])
        if not pairs:
            print(f"  [WARN] {label}: no data from Yahoo Finance (weekend/holiday?)")
            results[label] = "no_new_data"
            continue

        appended = _append_rows(csv_path, spec["col_name"], pairs)
        if appended > 0:
            new_last = _get_last_date_in_csv(csv_path)
            print(f"  [OK] {label}: appended {appended} row(s), new last date = {new_last}")
            results[label] = f"appended_{appended}"
        else:
            print(f"  [OK] {label}: already up to date (last = {last_date})")
            results[label] = "up_to_date"

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — VIX/VXV Daily Update")
    print(f"Date: {date.today()}")
    print("=" * 60)
    results = update_all()
    print(f"\nResults: {results}")
