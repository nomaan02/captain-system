# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Seed P3-D31 implied_vol from QuantConnect ES IV/RV extract.

Reads es_iv_rv.csv (date, atm_iv_30d, realized_vol_20d) and inserts
into QuestDB with asset_id='ES'.

Usage: python scripts/seed_iv_rv_from_extract.py
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor

DATA_DIR = os.environ.get(
    "QC_AIM_DATA_DIR",
    "/home/nomaan/captain-system-data-extracts/aim_data",
)


def seed_iv_rv(csv_path: str, asset_id: str = "ES") -> int:
    """Seed IV/RV data for a single asset."""
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "date": row["date"].strip(),
                "atm_iv_30d": float(row["atm_iv_30d"].strip()),
                "realized_vol_20d": float(row["realized_vol_20d"].strip()),
            })

    if not rows:
        print(f"  [WARN] {asset_id}: empty CSV")
        return 0

    with get_cursor() as cur:
        for r in rows:
            cur.execute(
                """INSERT INTO p3_d31_implied_vol
                   (asset_id, trade_date, atm_iv_30d, realized_vol_20d)
                   VALUES (%s, %s, %s, %s)""",
                (asset_id, r["date"], r["atm_iv_30d"], r["realized_vol_20d"]),
            )

    print(f"  [OK] {asset_id}: {len(rows)} days ({rows[0]['date']}→{rows[-1]['date']})")
    return len(rows)


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Seed IV/RV from QuantConnect Extract")
    print("=" * 60)

    csv_path = os.path.join(DATA_DIR, "es_iv_rv.csv")
    if not os.path.exists(csv_path):
        print(f"  [ERR] File not found: {csv_path}")
        sys.exit(1)

    total = seed_iv_rv(csv_path, "ES")
    print(f"\n  Total: {total} rows inserted into p3_d31_implied_vol.")
