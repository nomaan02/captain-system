# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Seed P3-D29 opening_volumes from QuantConnect extracted 1-min bar CSVs.

Reads CSV files with columns: datetime_et, open, high, low, close, volume, is_or
Sums volume where is_or=1 per trading day, inserts into QuestDB.

Usage: python scripts/seed_or_volumes_from_qc.py
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor

# Our 10 active assets and their session types + OR minutes from locked strategies
ASSET_CONFIG = {
    "ES":  {"session": "NY", "or_min": 7},
    "MES": {"session": "NY", "or_min": 7},
    "NQ":  {"session": "NY", "or_min": 3},
    "MNQ": {"session": "NY", "or_min": 5},
    "M2K": {"session": "NY", "or_min": 5},
    "MYM": {"session": "NY", "or_min": 9},
    "NKD": {"session": "APAC", "or_min": 6},
    "MGC": {"session": "NY", "or_min": 2},
    "ZB":  {"session": "NY", "or_min": 10},
    "ZN":  {"session": "NY", "or_min": 4},
}

DATA_DIR = os.environ.get(
    "QC_OR_VOLUME_DIR",
    "/home/nomaan/captain-system-data-extracts/or_volume_data",
)


def parse_or_volumes(asset_id: str, csv_path: str) -> list[dict]:
    """Parse a QC 1-min bar CSV, sum volume where is_or=1 per trading day."""
    daily_volumes = defaultdict(int)

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean Windows line endings
            is_or = row.get("is_or", "0").strip().strip("\r")
            if is_or != "1":
                continue
            dt_str = row["datetime_et"].strip().strip("\r")
            date_str = dt_str.split(" ")[0]
            vol = int(float(row["volume"].strip().strip("\r")))
            daily_volumes[date_str] += vol

    cfg = ASSET_CONFIG.get(asset_id, {"session": "NY", "or_min": 5})
    results = []
    for date_str, total_vol in sorted(daily_volumes.items()):
        results.append({
            "asset_id": asset_id,
            "session_date": date_str,
            "session_type": cfg["session"],
            "or_minutes": cfg["or_min"],
            "volume_first_m_min": total_vol,
        })
    return results


def seed_all():
    """Parse all asset CSVs and insert into P3-D29."""
    total_inserted = 0

    for asset_id in ASSET_CONFIG:
        csv_path = os.path.join(DATA_DIR, f"{asset_id}_or_volume.csv")
        if not os.path.exists(csv_path):
            print(f"  [SKIP] {asset_id}: file not found at {csv_path}")
            continue

        rows = parse_or_volumes(asset_id, csv_path)
        if not rows:
            print(f"  [WARN] {asset_id}: no OR volume data found")
            continue

        with get_cursor() as cur:
            for r in rows:
                cur.execute(
                    """INSERT INTO p3_d29_opening_volumes
                       (asset_id, session_date, session_type, or_minutes,
                        volume_first_m_min, ts)
                       VALUES (%s, %s, %s, %s, %s, now())""",
                    (r["asset_id"], r["session_date"], r["session_type"],
                     r["or_minutes"], r["volume_first_m_min"]),
                )
            total_inserted += len(rows)

        print(f"  [OK] {asset_id}: {len(rows)} days inserted "
              f"(session={rows[0]['session_type']}, or_min={rows[0]['or_minutes']}, "
              f"range={rows[0]['session_date']}→{rows[-1]['session_date']})")

    return total_inserted


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Seed OR Volumes from QuantConnect Extract")
    print("=" * 60)
    total = seed_all()
    print(f"\n  Total: {total} rows inserted into p3_d29_opening_volumes.")
