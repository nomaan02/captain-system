# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Bootstrap P3-D29 opening_volumes from TopstepX historical minute bars.

Fetches 1-minute bars for the last 30 days per active asset, sums
volume during the first m minutes after session open, and stores
in p3_d29_opening_volumes. This eliminates the AIM-15 warm-up period.

Usage: run inside captain-command container after init_questdb.py:
    python scripts/bootstrap_opening_volumes.py
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta, time as dtime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.questdb_client import get_cursor
from shared.topstep_client import get_topstep_client
from shared.contract_resolver import resolve_contract_id

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Session open times (ET) from config/session_registry.json
SESSION_OPEN_TIMES = {
    "NY":     dtime(9, 30),
    "LONDON": dtime(3, 0),
    "NY_PRE": dtime(6, 0),
    "APAC":   dtime(18, 0),
}

# Asset → session type mapping
ASSET_SESSION_MAP = {
    "ES": "NY", "NQ": "NY", "MES": "NY", "MNQ": "NY",
    "M2K": "NY", "MYM": "NY",
    "NKD": "APAC",
    "ZN": "NY_PRE", "ZB": "NY_PRE",
    "MGC": "LONDON",
}

LOOKBACK_DAYS = 35  # fetch extra to ensure 20+ trading days


def _get_or_minutes(locked_strategy: dict) -> int:
    """Extract OR window minutes from locked strategy."""
    if not locked_strategy:
        return 5  # default
    params = locked_strategy.get("strategy_params", {})
    return params.get("OR_window_minutes", 5)


def _parse_bar_time(bar: dict) -> datetime | None:
    """Parse bar timestamp. TopstepX returns 't' or 'timestamp' field."""
    for key in ("t", "timestamp", "time"):
        val = bar.get(key)
        if val:
            try:
                # Handle ISO format with or without Z
                if isinstance(val, str):
                    val = val.replace("Z", "+00:00")
                    return datetime.fromisoformat(val)
                elif isinstance(val, (int, float)):
                    return datetime.utcfromtimestamp(val)
            except (ValueError, OSError):
                continue
    return None


def _convert_utc_to_et(dt: datetime) -> datetime:
    """Simple UTC to ET conversion (EST = UTC-5, EDT = UTC-4)."""
    # Approximate: use -4 for March-November, -5 for November-March
    month = dt.month
    if 3 <= month <= 10:
        offset = timedelta(hours=-4)  # EDT
    else:
        offset = timedelta(hours=-5)  # EST
    return dt + offset


def bootstrap_opening_volumes():
    """Fetch historical minute bars and compute first-m-minute volumes."""
    client = get_topstep_client()

    # Load active assets and their locked strategies
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, locked_strategy FROM p3_d00_asset_universe "
            "WHERE captain_status = 'ACTIVE' ORDER BY asset_id"
        )
        assets = cur.fetchall()

    if not assets:
        print("  [WARN] No active assets found in D00.")
        return False

    today = datetime.utcnow().date()
    start_date = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end_date = (today - timedelta(days=1)).isoformat()

    total_inserted = 0

    for asset_id, locked_strategy_raw in assets:
        locked_strategy = json.loads(locked_strategy_raw) if isinstance(locked_strategy_raw, str) else (locked_strategy_raw or {})
        or_minutes = _get_or_minutes(locked_strategy)
        session_type = ASSET_SESSION_MAP.get(asset_id, "NY")
        session_open = SESSION_OPEN_TIMES.get(session_type, dtime(9, 30))

        contract_id = resolve_contract_id(asset_id)
        if not contract_id:
            print(f"  [SKIP] {asset_id}: no contract ID")
            continue

        print(f"  {asset_id}: fetching 1-min bars ({start_date} to {end_date}), "
              f"OR={or_minutes}min, session={session_type} open={session_open}")

        try:
            bars = client.get_bars(contract_id, 2, 1, start_date, end_date)
        except Exception as e:
            print(f"  [ERR] {asset_id}: {e}")
            continue

        if not bars:
            print(f"  [WARN] {asset_id}: no bars returned")
            continue

        # Group bars by trading date and sum first-m-minute volumes
        daily_volumes = {}  # date_str -> total volume in first m minutes

        for bar in bars:
            bar_time = _parse_bar_time(bar)
            if bar_time is None:
                continue

            # Convert to ET
            bar_et = _convert_utc_to_et(bar_time)
            bar_date = bar_et.date()
            bar_t = bar_et.time()

            # Check if this bar falls within [session_open, session_open + or_minutes)
            open_minutes = session_open.hour * 60 + session_open.minute
            bar_minutes = bar_t.hour * 60 + bar_t.minute
            diff = bar_minutes - open_minutes

            # Handle overnight sessions (APAC: open at 18:00, bars after midnight)
            if session_type == "APAC" and diff < -720:
                diff += 1440  # next day

            if 0 <= diff < or_minutes:
                date_str = bar_date.isoformat()
                vol = bar.get("volume", 0) or bar.get("v", 0) or 0
                daily_volumes[date_str] = daily_volumes.get(date_str, 0) + int(vol)

        # Insert into QuestDB
        if daily_volumes:
            with get_cursor() as cur:
                for date_str, volume in sorted(daily_volumes.items()):
                    cur.execute(
                        """INSERT INTO p3_d29_opening_volumes
                           (asset_id, session_date, session_type, or_minutes,
                            volume_first_m_min, ts)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (asset_id, date_str, session_type, or_minutes,
                         volume, f"{date_str}T12:00:00.000000Z"),
                    )
                    total_inserted += 1

            print(f"  [OK] {asset_id}: {len(daily_volumes)} days of opening volume stored "
                  f"(avg={sum(daily_volumes.values()) / len(daily_volumes):.0f})")
        else:
            print(f"  [WARN] {asset_id}: no bars matched first {or_minutes} minutes")

    print(f"\n  Total: {total_inserted} rows inserted into p3_d29_opening_volumes.")
    return total_inserted > 0


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Bootstrap Opening Volumes (P3-D29)")
    print("AIM-15: Historical first-m-minute volume baseline")
    print("=" * 60)
    success = bootstrap_opening_volumes()
    sys.exit(0 if success else 1)
