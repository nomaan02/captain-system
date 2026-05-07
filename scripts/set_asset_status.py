"""Set captain_status for one or more assets in p3_d00_asset_universe.

Idempotent: re-running --apply after success is a no-op (already at target).
Touches only p3_d00_asset_universe; no other table is modified.

Usage (via cap-run on towers):
  cap-run set_asset_status.py --check  --assets ZB ZN --status PAUSED
  cap-run set_asset_status.py --apply  --assets ZB ZN --status PAUSED

Valid statuses: ACTIVE, WARM_UP, TRAINING_ONLY, PAUSED, HALTED, DECAYED, INACTIVE
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.questdb_client import read_d00_row, update_d00_fields  # noqa: E402

VALID_STATUSES = {"ACTIVE", "WARM_UP", "TRAINING_ONLY", "PAUSED", "HALTED", "DECAYED", "INACTIVE",
                  "P1_ELIMINATED", "P2_ELIMINATED"}

# Statuses that participate in trading (B1 filter)
TRADING_STATUSES = {"ACTIVE", "WARM_UP", "TRAINING_ONLY"}


def main():
    parser = argparse.ArgumentParser(description="Set captain_status for assets in D00")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", default=True,
                      help="Read-only: show current status (default)")
    mode.add_argument("--apply", action="store_true",
                      help="Write the new status to QuestDB")
    parser.add_argument("--assets", nargs="+", required=True,
                        help="Asset IDs to update (e.g. ZB ZN)")
    parser.add_argument("--status", required=True,
                        help="Target captain_status (e.g. PAUSED, ACTIVE)")
    args = parser.parse_args()

    target = args.status.upper()
    if target not in VALID_STATUSES:
        print(f"ERROR: '{target}' is not a valid captain_status.")
        print(f"  Valid: {', '.join(sorted(VALID_STATUSES))}")
        sys.exit(1)

    assets = [a.upper() for a in args.assets]
    will_trade = target in TRADING_STATUSES

    print(f"Target status: {target}  (will trade: {'YES' if will_trade else 'NO'})")
    print(f"Assets: {', '.join(assets)}")
    print()

    errors = []
    for asset_id in assets:
        row = read_d00_row(asset_id)
        if row is None:
            print(f"  {asset_id}: NOT FOUND in D00")
            errors.append(asset_id)
            continue

        current = row["captain_status"]
        current_trades = current in TRADING_STATUSES

        if current == target:
            print(f"  {asset_id}: already {current} -> SKIP (no-op)")
            continue

        if args.apply:
            update_d00_fields(asset_id, {"captain_status": target})
            time.sleep(1.5)  # WAL commit lag (QDB_CAIRO_COMMIT_LAG=1000ms)
            verify = read_d00_row(asset_id)
            actual = verify["captain_status"] if verify else "???"
            ok = "OK" if actual == target else "FAILED"
            print(f"  {asset_id}: {current} -> {actual}  [{ok}]"
                  f"  (was trading: {'YES' if current_trades else 'NO'}"
                  f" -> now: {'YES' if will_trade else 'NO'})")
        else:
            print(f"  {asset_id}: {current}  (currently trading: {'YES' if current_trades else 'NO'})"
                  f"  -> would become {target} ({'YES' if will_trade else 'NO'})")

    if errors:
        print(f"\nWARNING: {len(errors)} asset(s) not found: {', '.join(errors)}")
        sys.exit(1)

    if not args.apply:
        print("\n  (--check mode, no changes made. Use --apply to write.)")


if __name__ == "__main__":
    main()
