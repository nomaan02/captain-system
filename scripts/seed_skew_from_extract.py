# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Seed P3-D32 options_skew from QuantConnect ES CBOE SKEW extract.

Reads es_skew.csv (date, cboe_skew, skew_spread_proxy) and inserts
into QuestDB with asset_id='ES'.

Usage: python scripts/seed_skew_from_extract.py
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get(
    "QC_AIM_DATA_DIR",
    os.path.join(_REPO_ROOT, "data", "seed", "aim_data"),
)


def seed_skew(csv_path: str, asset_id: str = "ES") -> int:
    """Seed skew data for a single asset."""
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "date": row["date"].strip(),
                "cboe_skew": float(row["cboe_skew"].strip()),
                "skew_spread_proxy": float(row["skew_spread_proxy"].strip()),
            })

    if not rows:
        print(f"  [WARN] {asset_id}: empty CSV")
        return 0

    with get_cursor() as cur:
        for r in rows:
            cur.execute(
                """INSERT INTO p3_d32_options_skew
                   (asset_id, trade_date, cboe_skew, skew_spread_proxy)
                   VALUES (%s, %s, %s, %s)""",
                (asset_id, r["date"], r["cboe_skew"], r["skew_spread_proxy"]),
            )

    print(f"  [OK] {asset_id}: {len(rows)} days ({rows[0]['date']}→{rows[-1]['date']})")
    return len(rows)


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Seed Options Skew from QuantConnect Extract")
    print("=" * 60)

    csv_path = os.path.join(DATA_DIR, "es_skew.csv")
    if not os.path.exists(csv_path):
        print(f"  [ERR] File not found: {csv_path}")
        sys.exit(1)

    total = seed_skew(csv_path, "ES")
    print(f"\n  Total: {total} rows inserted into p3_d32_options_skew.")
