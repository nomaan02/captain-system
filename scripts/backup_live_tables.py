"""Export live-written and monetary-migration tables from QuestDB to CSV.

Captures:

  Original runtime tables (beyond committed ``data/seed/`` CSVs):

  * p3_d30_daily_ohlcv       — daily OHLCV per asset (written by b1_features)
  * p3_d29_opening_volumes   — first-m-minute OR volume per session
  * p3_d33_opening_volatility — opening-range volatility per session
  * p3_spread_history        — bid/ask spread samples

  All eight tables targeted by the monetary DECIMAL migration (Phases A–C):

  * p3_d08_tsm_state
  * p3_d23_circuit_breaker_intraday
  * p3_d25_circuit_breaker_params
  * p3_d28_account_lifecycle
  * p3_d03_trade_outcome_log
  * p3_d16_user_capital_silos
  * p3_d00_asset_universe
  * (p3_d30_daily_ohlcv is already in the live set)

Output: one CSV per table under ``<backup_root>/live-tables-<timestamp>/``.

Optional: copy QuestDB on-disk table directories (partition snapshots) for a
subset of tables — ``--questdb-db-root`` (default ``$QUESTDB_DATA_DIR`` or
``/var/lib/questdb/db``).

Usage:
    python3 scripts/backup_live_tables.py
    python3 scripts/backup_live_tables.py --backup-root ~/captain-backups
    python3 scripts/backup_live_tables.py --tables p3_d30_daily_ohlcv

    # Phase A partition snapshots (example)
    python3 scripts/backup_live_tables.py \\
        --partition-snapshot-tables p3_d08_tsm_state p3_d23_circuit_breaker_intraday \\
            p3_d25_circuit_breaker_params p3_d28_account_lifecycle \\
        --questdb-db-root /var/lib/questdb/db

Pair with ``scripts/restore_live_delta.py`` after the committed seed chain
to re-insert rows the committed seeds don't cover.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.questdb_client import get_cursor

# Historical live-export set (market data accumulators).
LIVE_TABLES = [
    "p3_d30_daily_ohlcv",
    "p3_d29_opening_volumes",
    "p3_d33_opening_volatility",
    "p3_spread_history",
]

# All eight monetary-migration targets (Phases A–C). D30 appears in both lists;
# dedupe preserves order.
MONETARY_MIGRATION_TABLES = [
    "p3_d08_tsm_state",
    "p3_d23_circuit_breaker_intraday",
    "p3_d25_circuit_breaker_params",
    "p3_d28_account_lifecycle",
    "p3_d03_trade_outcome_log",
    "p3_d16_user_capital_silos",
    "p3_d00_asset_universe",
    "p3_d30_daily_ohlcv",
]

DEFAULT_EXPORT_TABLES: list[str] = list(
    dict.fromkeys(LIVE_TABLES + MONETARY_MIGRATION_TABLES),
)


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


def verify_csv_readable(csv_path: Path) -> tuple[bool, str]:
    """Basic restorability check: non-empty header and at least header row read OK."""
    try:
        with csv_path.open(newline="") as f:
            r = csv.reader(f)
            header = next(r, None)
            if not header:
                return False, "empty file"
            n = sum(1 for _ in r)
        return True, f"header_cols={len(header)} data_rows={n}"
    except Exception as exc:
        return False, str(exc)


def snapshot_questdb_partition_dirs(
    db_root: Path,
    tables: list[str],
    dest_dir: Path,
) -> list[str]:
    """Copy on-disk QuestDB table directories into ``dest_dir``. Returns log lines."""
    log: list[str] = []
    if not db_root.is_dir():
        log.append(f"[SKIP] db root not a directory: {db_root}")
        return log
    dest_dir.mkdir(parents=True, exist_ok=True)
    for t in tables:
        copied = False
        primary = db_root / t
        if primary.is_dir():
            dst = dest_dir / primary.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(primary, dst, symlinks=True)
            log.append(f"[OK] {primary} -> {dst}")
            copied = True
        else:
            for alt in sorted(db_root.glob(f"{t}~*")):
                if alt.is_dir():
                    dst = dest_dir / alt.name
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(alt, dst, symlinks=True)
                    log.append(f"[OK] {alt} -> {dst}")
                    copied = True
                    break
        if not copied:
            log.append(f"[MISSING] no partition dir for {t} under {db_root}")
    return log


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
        default=DEFAULT_EXPORT_TABLES,
        help="Subset of tables to export (defaults: LIVE_TABLES + monetary migration set).",
    )
    ap.add_argument(
        "--questdb-db-root",
        default=os.environ.get("QUESTDB_DATA_DIR", "/var/lib/questdb/db"),
        type=Path,
        help="QuestDB ``db`` directory for partition snapshots.",
    )
    ap.add_argument(
        "--partition-snapshot-tables",
        nargs="*",
        default=[],
        metavar="TABLE",
        help="If set, copy each table's on-disk dir under db/ into partition-snap-<stamp>/.",
    )
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.backup_root) / f"live-tables-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Backup destination: {out_dir}")
    print(f"Default export set includes {len(DEFAULT_EXPORT_TABLES)} tables "
          f"(live + monetary migration, deduped).")
    total = 0
    for table in args.tables:
        out_path = out_dir / f"{table}.csv"
        try:
            n = dump_table(table, out_path)
        except Exception as exc:
            print(f"  [FAIL] {table}: {exc}")
            return 1
        ok, msg = verify_csv_readable(out_path)
        status = "OK" if ok else "VERIFY_FAIL"
        print(f"  [{status}] {table}: {n} rows -> {out_path.name} ({msg})")
        if not ok:
            return 1
        total += n

    if args.partition_snapshot_tables:
        snap_dir = Path(args.backup_root) / f"partition-snap-{stamp}"
        print(f"\nPartition snapshot dir: {snap_dir}")
        for line in snapshot_questdb_partition_dirs(
            args.questdb_db_root,
            list(args.partition_snapshot_tables),
            snap_dir,
        ):
            print(f"  {line}")

    print(f"\nTotal rows exported: {total}")
    print(f"Pass to restore_live_delta.py via --backup-dir {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
