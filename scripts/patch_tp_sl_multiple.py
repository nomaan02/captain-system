"""Per-tower D00 patch: revert tp_multiple/sl_multiple to 0.70/0.35.

Idempotent migration script for towers bootstrapped under the brief 0.90/0.10
TP/SL era. Mutates ONLY the tp_multiple and sl_multiple keys inside each
active asset's locked_strategy JSON; preserves every other field
(model, feature, threshold, regime_class, OO, fees, etc.).

Modes
-----
--check    (default) Read-only diagnostic. Prints current vs target per asset.
--dry-run  Same as --check but also prints the exact JSON that WOULD be written.
--apply    Write the new JSON. Skips assets already at target.

Safety
------
- Idempotent: re-running --apply after success is a no-op (Skipped N / Patched 0).
- Touches only p3_d00_asset_universe; no other table is modified.
- Never re-runs bootstrap_production.py (which would create duplicate D00 rows
  on already-bootstrapped towers).
- Honours the TARGET_TP / TARGET_SL constants below; flip them and re-run to
  perform a rollback patch.

Usage (inside captain-offline container, matches TOWER_DEPLOYMENT_GUIDE.md style)
--------------------------------------------------------------------------------
  docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
      -e PYTHONPATH=/app captain-offline \
      python /captain/scripts/patch_tp_sl_multiple.py --check

  docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
      -e PYTHONPATH=/app captain-offline \
      python /captain/scripts/patch_tp_sl_multiple.py --apply
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Allow running directly without PYTHONPATH being set when invoked outside
# the container.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.questdb_client import get_cursor, update_d00_fields  # noqa: E402

TARGET_TP = 0.70
TARGET_SL = 0.35

# Match B4 / B6 read filter — only patch assets that B4 will actually size for.
_ELIGIBLE_STATUSES = ("ACTIVE", "WARM_UP")

_FLOAT_TOL = 1e-9


def _eq(a, b) -> bool:
    """Tolerant float equality so 0.7 / 0.70 / 0.7000000001 all match."""
    if a is None or b is None:
        return a is b
    try:
        return math.isclose(float(a), float(b), abs_tol=_FLOAT_TOL)
    except (TypeError, ValueError):
        return False


def _fetch_eligible_assets() -> list[tuple[str, str | None]]:
    """Return [(asset_id, locked_strategy_json), ...] for ACTIVE / WARM_UP rows."""
    placeholders = ", ".join(["%s"] * len(_ELIGIBLE_STATUSES))
    sql = (
        "SELECT asset_id, locked_strategy "
        "FROM p3_d00_asset_universe "
        f"WHERE captain_status IN ({placeholders}) "
        "LATEST ON last_updated PARTITION BY asset_id"
    )
    with get_cursor() as cur:
        cur.execute(sql, _ELIGIBLE_STATUSES)
        rows = cur.fetchall()
    return [(r[0], r[1]) for r in rows]


def _classify(asset_id: str, locked_json: str | None):
    """Return ('OK'|'SKIP'|'FAIL', current_tp, current_sl, new_dict_or_None, error)."""
    if not locked_json:
        return "FAIL", None, None, None, "locked_strategy is empty"

    try:
        data = json.loads(locked_json)
    except json.JSONDecodeError as exc:
        return "FAIL", None, None, None, f"invalid JSON: {exc}"

    cur_tp = data.get("tp_multiple")
    cur_sl = data.get("sl_multiple")

    if _eq(cur_tp, TARGET_TP) and _eq(cur_sl, TARGET_SL):
        return "SKIP", cur_tp, cur_sl, None, None

    new_data = dict(data)
    new_data["tp_multiple"] = TARGET_TP
    new_data["sl_multiple"] = TARGET_SL
    return "OK", cur_tp, cur_sl, new_data, None


def _format_value(v) -> str:
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Revert tp_multiple/sl_multiple to "
                    f"{TARGET_TP}/{TARGET_SL} in p3_d00_asset_universe.locked_strategy"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="Read-only: print current state per asset (default).")
    mode.add_argument("--dry-run", action="store_true",
                      help="Print full JSON diff without writing.")
    mode.add_argument("--apply", action="store_true",
                      help="Write the patched JSON to QuestDB.")
    args = parser.parse_args()

    if not (args.check or args.dry_run or args.apply):
        args.check = True

    print("=" * 64)
    print(f"  patch_tp_sl_multiple.py  target tp={TARGET_TP} sl={TARGET_SL}")
    mode_label = "APPLY" if args.apply else ("DRY-RUN" if args.dry_run else "CHECK")
    print(f"  mode: {mode_label}")
    print("=" * 64)

    try:
        rows = _fetch_eligible_assets()
    except Exception as exc:
        print(f"  [ERR] failed to query p3_d00_asset_universe: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print(f"  [WARN] no assets matched captain_status IN {_ELIGIBLE_STATUSES}.")
        return 0

    n_ok = n_skip = n_fail = 0

    for asset_id, locked_json in sorted(rows):
        status, cur_tp, cur_sl, new_data, err = _classify(asset_id, locked_json)

        cur_str = f"tp={_format_value(cur_tp)} sl={_format_value(cur_sl)}"
        new_str = f"tp={TARGET_TP} sl={TARGET_SL}"

        if status == "SKIP":
            n_skip += 1
            print(f"  [SKIP] {asset_id:5}  already at target ({cur_str})")
            continue

        if status == "FAIL":
            n_fail += 1
            print(f"  [FAIL] {asset_id:5}  {err}")
            continue

        if args.apply:
            try:
                update_d00_fields(asset_id, {"locked_strategy": json.dumps(new_data)})
            except Exception as exc:
                n_fail += 1
                print(f"  [FAIL] {asset_id:5}  write failed: {exc}", file=sys.stderr)
                continue
            n_ok += 1
            print(f"  [OK]   {asset_id:5}  {cur_str}  ->  {new_str}")
        else:
            n_ok += 1
            tag = "WOULD-PATCH" if args.dry_run else "NEEDS-PATCH"
            print(f"  [{tag}] {asset_id:5}  {cur_str}  ->  {new_str}")
            if args.dry_run:
                print(f"           new locked_strategy = {json.dumps(new_data)}")

    print("-" * 64)
    verb = "Patched" if args.apply else "Eligible"
    print(f"  {verb}: {n_ok}   Skipped: {n_skip}   Failed: {n_fail}   "
          f"Total: {len(rows)}")

    if args.apply and n_ok > 0:
        print("\n  Reminder: restart Captain services (bash captain-update.sh) so "
              "any in-memory caches reload.")

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
