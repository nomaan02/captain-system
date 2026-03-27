# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Contract Roll Calendar — update contract IDs and roll dates.

Futures contracts expire quarterly. This script:
  1. Queries TopstepX API for currently available contracts per asset
  2. Updates config/contract_ids.json with the new front-month contract
  3. Updates P3-D00 roll_calendar with next_roll_date
  4. Invalidates the contract resolver cache
  5. Optionally sends a Telegram notification

Roll schedule (CME standard):
  - Equity index (ES, MES, NQ, MNQ, M2K, MYM, NKD): quarterly HMUZ
    Roll on 2nd Thursday before 3rd Friday of expiry month
  - Metals (MGC): bi-monthly GJMQVZ
    Roll ~3 business days before first notice (last business day of prior month)
  - Treasuries (ZB, ZN): quarterly HMUZ
    Roll ~7 business days before last business day of expiry month

Usage:
  python scripts/roll_calendar_update.py --check        # Show status only
  python scripts/roll_calendar_update.py --update       # Update config + QuestDB
  python scripts/roll_calendar_update.py --update --notify  # Also send Telegram alert
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from shared.questdb_client import get_cursor

_CONFIG_PATH = _PROJECT_ROOT / "config" / "contract_ids.json"

# CME month codes
MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
CODE_TO_MONTH = {v: k for k, v in MONTH_CODES.items()}

# Contract cycle per asset class
EQUITY_INDEX_CYCLE = [3, 6, 9, 12]       # H, M, U, Z
METALS_CYCLE = [2, 4, 6, 8, 10, 12]      # G, J, M, Q, V, Z
TREASURY_CYCLE = [3, 6, 9, 12]           # H, M, U, Z

# TopstepX contract ID prefixes (from contract_ids.json)
ASSET_CONFIG = {
    "ES":  {"prefix": "CON.F.US.EP",  "cycle": EQUITY_INDEX_CYCLE},
    "MES": {"prefix": "CON.F.US.MES", "cycle": EQUITY_INDEX_CYCLE},
    "NQ":  {"prefix": "CON.F.US.ENQ", "cycle": EQUITY_INDEX_CYCLE},
    "MNQ": {"prefix": "CON.F.US.MNQ", "cycle": EQUITY_INDEX_CYCLE},
    "M2K": {"prefix": "CON.F.US.M2K", "cycle": EQUITY_INDEX_CYCLE},
    "MYM": {"prefix": "CON.F.US.MYM", "cycle": EQUITY_INDEX_CYCLE},
    "NKD": {"prefix": "CON.F.US.NKD", "cycle": EQUITY_INDEX_CYCLE},
    "MGC": {"prefix": "CON.F.US.MGC", "cycle": METALS_CYCLE},
    "ZB":  {"prefix": "CON.F.US.USA", "cycle": TREASURY_CYCLE},
    "ZN":  {"prefix": "CON.F.US.TYA", "cycle": TREASURY_CYCLE},
}


def _third_friday(year: int, month: int) -> date:
    """Return 3rd Friday of given month (CME equity index expiry)."""
    # First day of month
    d = date(year, month, 1)
    # Find first Friday
    days_until_friday = (4 - d.weekday()) % 7
    first_friday = d + timedelta(days=days_until_friday)
    # Third Friday = first Friday + 14 days
    return first_friday + timedelta(days=14)


def _second_thursday_before_third_friday(year: int, month: int) -> date:
    """Equity index roll date: 2nd Thursday before 3rd Friday of expiry month."""
    third_fri = _third_friday(year, month)
    # Go back to find Thursdays before this Friday
    # 1st Thursday before = third_fri - 1 day
    # 2nd Thursday before = third_fri - 8 days
    return third_fri - timedelta(days=8)


def _last_business_day(year: int, month: int) -> date:
    """Last business day of the month."""
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


def compute_roll_date(asset: str, expiry_year: int, expiry_month: int) -> date:
    """Compute approximate roll date for an asset's expiring contract.

    This is when we should switch to the next contract — a few days before
    the contract actually expires, when liquidity shifts to the next month.
    """
    if asset in ("MGC",):
        # Metals: roll ~3 business days before last business day of month prior to expiry
        lbd = _last_business_day(expiry_year, expiry_month)
        roll = lbd
        bdays = 0
        while bdays < 3:
            roll -= timedelta(days=1)
            if roll.weekday() < 5:
                bdays += 1
        return roll
    elif asset in ("ZB", "ZN"):
        # Treasuries: roll ~7 business days before last business day of expiry month
        lbd = _last_business_day(expiry_year, expiry_month)
        roll = lbd
        bdays = 0
        while bdays < 7:
            roll -= timedelta(days=1)
            if roll.weekday() < 5:
                bdays += 1
        return roll
    else:
        # Equity index: 2nd Thursday before 3rd Friday of expiry month
        return _second_thursday_before_third_friday(expiry_year, expiry_month)


def get_next_expiry(asset: str, after: date) -> tuple[int, int]:
    """Get the next expiry month/year for an asset after a given date."""
    cycle = ASSET_CONFIG[asset]["cycle"]

    year = after.year
    for month in cycle:
        if date(year, month, 1) > after:
            return year, month

    # Wrap to next year
    return year + 1, cycle[0]


def get_current_contract_info(asset: str, today: date | None = None) -> dict:
    """Compute current and next contract info for an asset."""
    if today is None:
        today = date.today()

    cfg = ASSET_CONFIG[asset]
    prefix = cfg["prefix"]
    cycle = cfg["cycle"]

    # Find current front-month (the one we should be trading now)
    current_year, current_month = get_next_expiry(asset, today - timedelta(days=30))

    # If we're past the roll date for this contract, the front month is the next one
    roll_date = compute_roll_date(asset, current_year, current_month)
    if today >= roll_date:
        current_year, current_month = get_next_expiry(asset, today)
        roll_date = compute_roll_date(asset, current_year, current_month)

    # Next contract after current
    # Use the day after current expiry month starts to find the one after
    next_year, next_month = get_next_expiry(
        asset, date(current_year, current_month, 1)
    )
    next_roll_date = compute_roll_date(asset, next_year, next_month)

    # Build TopstepX contract ID
    year_suffix = str(current_year)[-2:]
    month_code = MONTH_CODES[current_month]
    contract_id = f"{prefix}.{month_code}{year_suffix}"

    next_year_suffix = str(next_year)[-2:]
    next_month_code = MONTH_CODES[next_month]
    next_contract_id = f"{prefix}.{next_month_code}{next_year_suffix}"

    days_to_roll = (roll_date - today).days

    return {
        "asset": asset,
        "contract_id": contract_id,
        "expiry_month": f"{current_year}-{current_month:02d}",
        "roll_date": roll_date.isoformat(),
        "days_to_roll": days_to_roll,
        "next_contract_id": next_contract_id,
        "next_expiry_month": f"{next_year}-{next_month:02d}",
        "next_roll_date": next_roll_date.isoformat(),
        "status": "URGENT" if days_to_roll <= 3 else "WARNING" if days_to_roll <= 10 else "OK",
    }


def check_all(today: date | None = None) -> list[dict]:
    """Check roll status for all 10 assets."""
    results = []
    for asset in ASSET_CONFIG:
        info = get_current_contract_info(asset, today)
        results.append(info)
    return results


def update_config(results: list[dict]) -> None:
    """Update config/contract_ids.json with current contract IDs."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    for info in results:
        asset = info["asset"]
        if asset in config["contracts"]:
            old_id = config["contracts"][asset]["contract_id"]
            new_id = info["contract_id"]
            if old_id != new_id:
                print(f"  [{asset}] CONTRACT CHANGED: {old_id} -> {new_id}")
                config["contracts"][asset]["contract_id"] = new_id
                config["contracts"][asset]["description"] = (
                    f"{asset}: {info['expiry_month']}"
                )

    config["description"] = (
        f"TopstepX contract IDs. Auto-updated {date.today().isoformat()} "
        f"via roll_calendar_update.py"
    )

    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
        f.write("\n")

    print(f"  config/contract_ids.json updated")


def update_questdb(results: list[dict]) -> None:
    """Update P3-D00 roll_calendar fields with roll dates."""
    import time

    updated = 0
    for info in results:
        asset = info["asset"]
        roll_calendar = json.dumps({
            "current_contract": info["contract_id"],
            "next_contract": info["next_contract_id"],
            "next_roll_date": info["roll_date"],
            "roll_confirmed": False,
            "topstep_contract_id": info["contract_id"],
        })

        for attempt in range(3):
            try:
                with get_cursor() as cur:
                    cur.execute(
                        """INSERT INTO p3_d00_asset_universe
                           (asset_id, roll_calendar, last_updated)
                           VALUES (%s, %s, now())""",
                        (asset, roll_calendar),
                    )
                updated += 1
                break
            except Exception as e:
                if "busy" in str(e).lower() and attempt < 2:
                    time.sleep(1)
                else:
                    print(f"  [WARN] Failed to update {asset}: {e}")
                    break

    print(f"  P3-D00 roll_calendar updated for {updated}/{len(results)} assets")


def invalidate_cache():
    """Clear contract resolver cache so it picks up new IDs."""
    try:
        from shared.contract_resolver import invalidate
        invalidate()
        print("  Contract resolver cache invalidated")
    except Exception as e:
        print(f"  [WARN] Cache invalidation failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Contract roll calendar management")
    parser.add_argument("--check", action="store_true", help="Show roll status only")
    parser.add_argument("--update", action="store_true", help="Update config + QuestDB")
    parser.add_argument("--notify", action="store_true", help="Send Telegram notification")
    parser.add_argument("--date", type=str, default=None,
                        help="Override today's date (YYYY-MM-DD) for testing")
    args = parser.parse_args()

    if not args.check and not args.update:
        args.check = True  # Default to check mode

    today = date.fromisoformat(args.date) if args.date else date.today()

    print("=" * 70)
    print(f"CAPTAIN — Contract Roll Calendar  ({today.isoformat()})")
    print("=" * 70)

    results = check_all(today)

    # Display status table
    print(f"\n{'Asset':6s} | {'Contract ID':22s} | {'Roll Date':12s} | {'Days':5s} | {'Status':8s} | Next")
    print("-" * 90)
    for info in results:
        print(f"{info['asset']:6s} | {info['contract_id']:22s} | {info['roll_date']:12s} | "
              f"{info['days_to_roll']:5d} | {info['status']:8s} | {info['next_contract_id']}")

    urgent = [r for r in results if r["status"] == "URGENT"]
    warning = [r for r in results if r["status"] == "WARNING"]

    if urgent:
        print(f"\n  URGENT: {', '.join(r['asset'] for r in urgent)} — roll within 3 days!")
    if warning:
        print(f"  WARNING: {', '.join(r['asset'] for r in warning)} — roll within 10 days")

    if args.update:
        print(f"\nUpdating...")
        update_config(results)
        update_questdb(results)
        invalidate_cache()
        print("  Done.")

    if args.notify and (urgent or warning):
        _send_telegram_alert(results, urgent, warning)

    return 0


def _send_telegram_alert(results, urgent, warning):
    """Send Telegram alert about upcoming rolls."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("  [SKIP] Telegram: no TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID set")
        return

    import urllib.request

    lines = ["CONTRACT ROLL ALERT"]
    if urgent:
        lines.append(f"URGENT (<=3 days): {', '.join(r['asset'] for r in urgent)}")
    if warning:
        lines.append(f"WARNING (<=10 days): {', '.join(r['asset'] for r in warning)}")
    lines.append("")
    for r in results:
        if r["status"] != "OK":
            lines.append(f"  {r['asset']}: {r['contract_id']} -> {r['next_contract_id']} "
                         f"in {r['days_to_roll']}d ({r['roll_date']})")

    text = "\n".join(lines)
    url = (f"https://api.telegram.org/bot{token}/sendMessage"
           f"?chat_id={chat_id}&text={urllib.parse.quote(text)}")
    try:
        urllib.request.urlopen(url, timeout=10)
        print("  Telegram alert sent")
    except Exception as e:
        print(f"  [WARN] Telegram failed: {e}")


if __name__ == "__main__":
    sys.exit(main())
