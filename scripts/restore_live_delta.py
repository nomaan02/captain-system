"""Re-insert the tower-captured delta over the committed seed baseline.

Pairs with ``scripts/backup_live_tables.py``. Run AFTER the committed seed
chain finishes on a fresh install: the committed CSVs under ``data/seed/``
only go up to the date the seed files were last refreshed (the "seed
frontier"), so any day the tower collected between that frontier and the
wipe would be lost without this delta-restore step.

For each backed-up table, this script:

  1. Determines the seed frontier (max date already covered by committed
     ``data/seed/`` CSVs, per asset where applicable).
  2. Filters the backup CSV to rows strictly after that frontier.
  3. Inserts the filtered rows into QuestDB via psycopg2.

D29 / D30 / D33 are filtered by session_date / trade_date. spread_history
has no committed seed baseline — every backed-up row is inserted, and
DEDUP ``UPSERT KEYS(timestamp, asset_id, session_id)`` prevents collisions
with whatever the newly-started container re-ingests.

Usage:
    python3 scripts/restore_live_delta.py --backup-dir ~/captain-backups/live-tables-20260421-130000
    python3 scripts/restore_live_delta.py --backup-dir <dir> --dry-run
"""

import argparse
import csv
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.questdb_client import get_cursor


REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_AIM = REPO_ROOT / "data" / "seed" / "aim_data"
SEED_OR = REPO_ROOT / "data" / "seed" / "or_volume_data"

ACTIVE_ASSETS = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM", "NKD", "MGC", "ZB", "ZN"]


# ---------------------------------------------------------------------------
# Seed-frontier discovery — max date currently covered by committed CSVs
# ---------------------------------------------------------------------------

def _max_date_in_csv(path: Path, date_col: str) -> str | None:
    """Return the max value of ``date_col`` as an ISO 'YYYY-MM-DD' string."""
    if not path.exists():
        return None
    best = ""
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            raw = row.get(date_col, "").strip()
            if not raw:
                continue
            # trim to date portion only (some CSVs use 'YYYY-MM-DD HH:MM:SS')
            d = raw[:10]
            if d > best:
                best = d
    return best or None


def ohlcv_frontier_per_asset() -> dict[str, str]:
    """Max trade_date in committed ohlcv CSVs — per asset."""
    out: dict[str, str] = {}
    # First look at the per-asset files; fall back to the combined file.
    for asset in ACTIVE_ASSETS:
        per_asset = SEED_AIM / f"ohlcv_{asset}.csv"
        mx = _max_date_in_csv(per_asset, "date")
        if mx:
            out[asset] = mx
    combined = SEED_AIM / "ohlcv_combined.csv"
    if combined.exists():
        # combined has columns: asset,date,open,high,low,close,volume
        with combined.open() as f:
            r = csv.DictReader(f)
            for row in r:
                a = row.get("asset") or row.get("asset_id")
                d = (row.get("date") or "").strip()[:10]
                if a and d:
                    if d > out.get(a, ""):
                        out[a] = d
    return out


def or_volume_frontier_per_asset() -> dict[str, str]:
    """Max session_date in committed OR-volume CSVs — per asset.

    The OR-volume CSVs are minute-bar files (datetime_et column); the
    session_date is the first 10 chars of datetime_et.
    """
    out: dict[str, str] = {}
    for asset in ACTIVE_ASSETS:
        path = SEED_OR / f"{asset}_or_volume.csv"
        mx = _max_date_in_csv(path, "datetime_et")
        if mx:
            out[asset] = mx
    return out


# ---------------------------------------------------------------------------
# Per-table restore
# ---------------------------------------------------------------------------

def _read_backup(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open() as f:
        r = csv.reader(f)
        header = next(r)
        rows = [row for row in r]
    return header, rows


def _idx(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        raise ValueError(f"column {name!r} not found in {header}")


def restore_d30(backup_dir: Path, dry_run: bool) -> tuple[int, int]:
    path = backup_dir / "p3_d30_daily_ohlcv.csv"
    if not path.exists():
        print(f"  [SKIP] d30: {path.name} not in backup dir")
        return 0, 0
    header, rows = _read_backup(path)
    i_asset = _idx(header, "asset_id")
    i_date = _idx(header, "trade_date")
    frontier = ohlcv_frontier_per_asset()
    # Use the trade_date itself as ts so DEDUP UPSERT KEYS(ts, asset_id,
    # trade_date) collapses duplicates on re-run (the live writer uses now()
    # which is unsuitable for idempotent restores).
    sql = (
        "INSERT INTO p3_d30_daily_ohlcv "
        "(asset_id, trade_date, open, high, low, close, volume, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )
    to_insert = []
    for row in rows:
        a = row[i_asset]
        d = (row[i_date] or "")[:10]
        fr = frontier.get(a, "")
        if d and d > fr:
            ts = datetime.strptime(d, "%Y-%m-%d")
            to_insert.append((
                a, d,
                float(row[_idx(header, "open")]),
                float(row[_idx(header, "high")]),
                float(row[_idx(header, "low")]),
                float(row[_idx(header, "close")]),
                int(row[_idx(header, "volume")]),
                ts,
            ))
    print(f"  d30: seed frontier by asset: "
          f"{ {a: frontier.get(a, '-') for a in ACTIVE_ASSETS} }")
    if dry_run:
        return len(rows), len(to_insert)
    if to_insert:
        with get_cursor() as cur:
            cur.executemany(sql, to_insert)
    return len(rows), len(to_insert)


def restore_d29(backup_dir: Path, dry_run: bool) -> tuple[int, int]:
    path = backup_dir / "p3_d29_opening_volumes.csv"
    if not path.exists():
        print(f"  [SKIP] d29: {path.name} not in backup dir")
        return 0, 0
    header, rows = _read_backup(path)
    i_asset = _idx(header, "asset_id")
    i_date = _idx(header, "session_date")
    frontier = or_volume_frontier_per_asset()
    # Session date doubles as ts so DEDUP UPSERT KEYS(ts, asset_id,
    # session_date) collapses duplicate restores.
    # Phase 2 (F-04): or_range_first_m_min restored when present in the backup
    # CSV; older backups predating the column will simply lack the header.
    has_or_range = "or_range_first_m_min" in header
    sql = (
        "INSERT INTO p3_d29_opening_volumes "
        "(asset_id, session_date, session_type, or_minutes, volume_first_m_min, "
        "or_range_first_m_min, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    to_insert = []
    for row in rows:
        a = row[i_asset]
        d = (row[i_date] or "")[:10]
        fr = frontier.get(a, "")
        if d and d > fr:
            ts = datetime.strptime(d, "%Y-%m-%d")
            or_range_val = None
            if has_or_range:
                raw = row[_idx(header, "or_range_first_m_min")]
                if raw not in (None, ""):
                    try:
                        or_range_val = float(raw)
                    except (TypeError, ValueError):
                        or_range_val = None
            to_insert.append((
                a, d,
                row[_idx(header, "session_type")],
                int(row[_idx(header, "or_minutes")]),
                int(row[_idx(header, "volume_first_m_min")]),
                or_range_val,
                ts,
            ))
    if dry_run:
        return len(rows), len(to_insert)
    if to_insert:
        with get_cursor() as cur:
            cur.executemany(sql, to_insert)
    return len(rows), len(to_insert)


def restore_d33(backup_dir: Path, dry_run: bool) -> tuple[int, int]:
    path = backup_dir / "p3_d33_opening_volatility.csv"
    if not path.exists():
        print(f"  [SKIP] d33: {path.name} not in backup dir")
        return 0, 0
    header, rows = _read_backup(path)
    i_asset = _idx(header, "asset_id")
    i_date = _idx(header, "session_date")
    # D33 session_date is a TIMESTAMP in the canonical DDL.
    # Frontier: use the OR-volume seed frontier (same session set).
    frontier = or_volume_frontier_per_asset()
    sql = (
        "INSERT INTO p3_d33_opening_volatility "
        "(asset_id, session_date, session_type, or_minutes, "
        " opening_range_pct, opening_vol_z, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s, now())"
    )
    to_insert = []
    for row in rows:
        a = row[i_asset]
        raw = (row[i_date] or "").strip()
        if not raw:
            continue
        d = raw[:10]
        fr = frontier.get(a, "")
        if d > fr:
            # session_date comes back as 'YYYY-MM-DD HH:MM:SS...' from QuestDB
            # and QuestDB accepts that string form for TIMESTAMP.
            to_insert.append((
                a, raw,
                row[_idx(header, "session_type")],
                int(row[_idx(header, "or_minutes")]) if row[_idx(header, "or_minutes")] else None,
                float(row[_idx(header, "opening_range_pct")]) if row[_idx(header, "opening_range_pct")] else None,
                float(row[_idx(header, "opening_vol_z")]) if row[_idx(header, "opening_vol_z")] else None,
            ))
    if dry_run:
        return len(rows), len(to_insert)
    if to_insert:
        with get_cursor() as cur:
            cur.executemany(sql, to_insert)
    return len(rows), len(to_insert)


def restore_spread_history(backup_dir: Path, dry_run: bool) -> tuple[int, int]:
    path = backup_dir / "p3_spread_history.csv"
    if not path.exists():
        print(f"  [SKIP] spread_history: {path.name} not in backup dir")
        return 0, 0
    header, rows = _read_backup(path)
    # No committed seed — restore everything. DEDUP UPSERT KEYS(timestamp,
    # asset_id, session_id) collapses duplicates naturally, and the
    # original timestamp is preserved from the backup.
    sql = (
        "INSERT INTO p3_spread_history "
        "(asset_id, session_id, spread, timestamp) "
        "VALUES (%s, %s, %s, %s)"
    )
    i_asset = _idx(header, "asset_id")
    i_sess = _idx(header, "session_id")
    i_spread = _idx(header, "spread")
    i_ts = _idx(header, "timestamp")
    to_insert = []
    for row in rows:
        to_insert.append((
            row[i_asset],
            int(row[i_sess]) if row[i_sess] else None,
            float(row[i_spread]) if row[i_spread] else None,
            row[i_ts],
        ))
    if dry_run:
        return len(rows), len(to_insert)
    if to_insert:
        with get_cursor() as cur:
            cur.executemany(sql, to_insert)
    return len(rows), len(to_insert)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backup-dir",
        required=True,
        type=Path,
        help="Directory produced by backup_live_tables.py "
             "(e.g. ~/captain-backups/live-tables-20260421-130000).",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be inserted, write nothing.",
    )
    args = ap.parse_args()
    backup_dir: Path = args.backup_dir.expanduser()
    if not backup_dir.is_dir():
        print(f"[FAIL] backup dir not found: {backup_dir}")
        return 1

    print(f"Restoring delta from: {backup_dir}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'INSERT'}\n")

    summary: list[tuple[str, int, int]] = []
    for label, fn in [
        ("p3_d30_daily_ohlcv",       restore_d30),
        ("p3_d29_opening_volumes",   restore_d29),
        ("p3_d33_opening_volatility", restore_d33),
        ("p3_spread_history",        restore_spread_history),
    ]:
        try:
            total, inserted = fn(backup_dir, args.dry_run)
        except Exception as exc:
            print(f"  [FAIL] {label}: {exc}")
            return 1
        print(f"  [OK] {label}: {inserted}/{total} rows {'would be ' if args.dry_run else ''}inserted")
        summary.append((label, total, inserted))

    print("\nSummary:")
    for label, total, inserted in summary:
        print(f"  {label}: backup had {total}, delta {inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
