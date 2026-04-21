"""Export live-written market-data tables from QuestDB to CSV for pre-wipe backup.

Captures the four tables that accumulate rows at runtime beyond what the
committed ``data/seed/`` CSVs provide:

  * p3_d30_daily_ohlcv       — daily OHLCV per asset (written by b1_features)
  * p3_d29_opening_volumes   — first-m-minute OR volume per session
  * p3_d33_opening_volatility — opening-range volatility per session
  * p3_spread_history        — bid/ask spread samples

Output: one CSV per table under ``<backup_root>/live-tables-<timestamp>/``.

Usage:
    python3 scripts/backup_live_tables.py
    python3 scripts/backup_live_tables.py --backup-root ~/captain-backups
    python3 scripts/backup_live_tables.py --tables p3_d30_daily_ohlcv

Pair with ``scripts/restore_live_delta.py`` after the committed seed chain
to re-insert the rows the committed seeds don't cover.
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.questdb_client import get_cursor

LIVE_TABLES = [
    "p3_d30_daily_ohlcv",
    "p3_d29_opening_volumes",
    "p3_d33_opening_volatility",
    "p3_spread_history",
]


def dump_table(table: str, out_path: Path) -> int:
    """Dump every row of ``table`` into ``out_path`` as CSV. Returns row count."""
    with get_cursor() as cur:
        cur.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(r)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backup-root",
        default=os.path.expanduser("~/captain-backups"),
        help="Directory where the live-tables-<stamp> folder is created.",
    )
    ap.add_argument(
        "--tables",
        nargs="+",
        default=LIVE_TABLES,
        help="Subset of tables to export (defaults to all four).",
    )
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.backup_root) / f"live-tables-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Backup destination: {out_dir}")
    total = 0
    for table in args.tables:
        out_path = out_dir / f"{table}.csv"
        try:
            n = dump_table(table, out_path)
        except Exception as exc:
            print(f"  [FAIL] {table}: {exc}")
            return 1
        print(f"  [OK] {table}: {n} rows -> {out_path.name}")
        total += n

    print(f"\nTotal rows exported: {total}")
    print(f"Pass to restore_live_delta.py via --backup-dir {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
