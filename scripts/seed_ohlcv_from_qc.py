# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Seed P3-D30 daily_ohlcv from QuantConnect extracted daily bar CSVs.

Reads per-asset CSVs (date,open,high,low,close,volume) or a combined CSV
(asset,date,open,high,low,close,volume) and inserts into QuestDB.

Usage: python scripts/seed_ohlcv_from_qc.py
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor

# Active assets
ACTIVE_ASSETS = {"ES", "MES", "NQ", "MNQ", "M2K", "MYM", "NKD", "MGC", "ZB", "ZN"}

DATA_DIR = os.environ.get(
    "QC_AIM_DATA_DIR",
    "/home/nomaan/captain-system-data-extracts/aim_data",
)


def seed_from_combined(csv_path: str) -> int:
    """Seed from combined CSV (asset,date,open,high,low,close,volume)."""
    inserted = 0
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows_by_asset = {}
        for row in reader:
            asset = row["asset"].strip().strip("\r")
            if asset not in ACTIVE_ASSETS:
                continue
            if asset not in rows_by_asset:
                rows_by_asset[asset] = []
            rows_by_asset[asset].append({
                "asset_id": asset,
                "trade_date": row["date"].strip().strip("\r"),
                "open": float(row["open"].strip().strip("\r")),
                "high": float(row["high"].strip().strip("\r")),
                "low": float(row["low"].strip().strip("\r")),
                "close": float(row["close"].strip().strip("\r")),
                "volume": int(float(row["volume"].strip().strip("\r"))),
            })

    for asset, rows in sorted(rows_by_asset.items()):
        with get_cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO p3_d30_daily_ohlcv
                       (asset_id, trade_date, open, high, low, close, volume, ts)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
                    (r["asset_id"], r["trade_date"], r["open"], r["high"],
                     r["low"], r["close"], r["volume"]),
                )
        inserted += len(rows)
        print(f"  [OK] {asset}: {len(rows)} days "
              f"({rows[0]['trade_date']}→{rows[-1]['trade_date']})")

    return inserted


def seed_from_per_asset(data_dir: str) -> int:
    """Seed from per-asset CSVs (date,open,high,low,close,volume)."""
    inserted = 0
    for asset in sorted(ACTIVE_ASSETS):
        csv_path = os.path.join(data_dir, f"ohlcv_{asset}.csv")
        if not os.path.exists(csv_path):
            print(f"  [SKIP] {asset}: no file at {csv_path}")
            continue

        rows = []
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "asset_id": asset,
                    "trade_date": row["date"].strip().strip("\r"),
                    "open": float(row["open"].strip().strip("\r")),
                    "high": float(row["high"].strip().strip("\r")),
                    "low": float(row["low"].strip().strip("\r")),
                    "close": float(row["close"].strip().strip("\r")),
                    "volume": int(float(row["volume"].strip().strip("\r"))),
                })

        if not rows:
            print(f"  [WARN] {asset}: empty file")
            continue

        with get_cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO p3_d30_daily_ohlcv
                       (asset_id, trade_date, open, high, low, close, volume, ts)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
                    (r["asset_id"], r["trade_date"], r["open"], r["high"],
                     r["low"], r["close"], r["volume"]),
                )
        inserted += len(rows)
        print(f"  [OK] {asset}: {len(rows)} days "
              f"({rows[0]['trade_date']}→{rows[-1]['trade_date']})")

    return inserted


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Seed Daily OHLCV from QuantConnect Extract")
    print("=" * 60)

    combined = os.path.join(DATA_DIR, "ohlcv_combined.csv")
    if os.path.exists(combined):
        total = seed_from_combined(combined)
    else:
        total = seed_from_per_asset(DATA_DIR)

    print(f"\n  Total: {total} rows inserted into p3_d30_daily_ohlcv.")
