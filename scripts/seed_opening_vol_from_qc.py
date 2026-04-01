# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Seed P3-D33 opening_volatility from QuantConnect 1-min OR bar extracts.

Reads per-asset OR volume CSVs, filters to is_or=1 bars (first 5 minutes),
computes std_dev of 1-min close-to-close returns per session, and inserts
into QuestDB. This provides immediate history for AIM-12 vol_z without
waiting 60 days.

Usage: python scripts/seed_opening_vol_from_qc.py
"""

import csv
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor

ACTIVE_ASSETS = {"ES", "MES", "NQ", "MNQ", "M2K", "MYM", "NKD", "MGC", "ZB", "ZN"}

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get(
    "QC_OR_DATA_DIR",
    os.path.join(_REPO_ROOT, "data", "seed", "or_volume_data"),
)


def _compute_vol_from_bars(bars: list[dict]) -> float | None:
    """Compute std dev of 1-min returns from OR bars.

    bars: list of dicts with 'close' key, sorted by time (ascending).
    Returns std dev of log returns, or None if insufficient bars.
    """
    if len(bars) < 3:  # need at least 2 returns
        return None

    closes = [float(b["close"]) for b in bars]
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append(math.log(closes[i] / closes[i - 1]))

    if len(returns) < 2:
        return None

    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance)


def seed_asset(asset: str, csv_path: str) -> int:
    """Seed opening vol for one asset. Returns number of sessions seeded."""
    # Group OR bars by session date
    sessions = defaultdict(list)
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("is_or", "0").strip() != "1":
                continue
            dt = row["datetime_et"].strip()
            session_date = dt.split()[0]
            sessions[session_date].append(row)

    if not sessions:
        print(f"  [SKIP] {asset}: no OR bars found")
        return 0

    inserted = 0
    with get_cursor() as cur:
        for session_date in sorted(sessions):
            bars = sessions[session_date]
            vol = _compute_vol_from_bars(bars)
            if vol is None:
                continue
            cur.execute(
                """INSERT INTO p3_d33_opening_volatility
                   (asset_id, session_date, vol_5min)
                   VALUES (%s, %s, %s)""",
                (asset, session_date, vol),
            )
            inserted += 1

    dates = sorted(sessions.keys())
    print(f"  [OK] {asset}: {inserted} sessions ({dates[0]}→{dates[-1]})")
    return inserted


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Seed Opening Volatility from QC OR Bars")
    print("=" * 60)

    total = 0
    for asset in sorted(ACTIVE_ASSETS):
        csv_path = os.path.join(DATA_DIR, f"{asset}_or_volume.csv")
        if not os.path.exists(csv_path):
            print(f"  [SKIP] {asset}: no file at {csv_path}")
            continue
        total += seed_asset(asset, csv_path)

    print(f"\n  Total: {total} session-rows inserted into p3_d33_opening_volatility.")
