# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
Fix bootstrapped data issues:
1. Convert EWMA avg_win/avg_loss from r_mi units to dollars
2. Activate Tier 1 AIMs (INSTALLED → ACTIVE) in D01
3. Set max_daily_loss in D08 TSM (TopstepX 150K combine = $2,250)

READ from QuestDB, WRITE corrected rows (append-only, latest wins).

Usage (inside captain-command container):
    python /app/fix_bootstrap_data.py [--dry-run]
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/app")

# Dollar conversion factors: r_mi * or_range * point_value = dollars
# From shared/signal_replay.py DEFAULT_OR_RANGES and POINT_VALUES
DOLLAR_FACTOR = {
    "ES":  4.0 * 50.0,    # $200 per r_mi
    "MES": 4.0 * 5.0,     # $20
    "NQ":  15.0 * 20.0,   # $300
    "MNQ": 15.0 * 2.0,    # $30
    "M2K": 8.0 * 5.0,     # $40
    "MYM": 100.0 * 0.5,   # $50
    "NKD": 100.0 * 5.0,   # $500
    "MGC": 5.0 * 10.0,    # $50
    "ZB":  0.25 * 1000.0,  # $250
    "ZN":  0.125 * 1000.0, # $125
}

TIER1_AIMS = [4, 6, 8, 11, 12, 15]
ACTIVE_ASSETS = list(DOLLAR_FACTOR.keys())


def fix_ewma(dry_run=False):
    """Convert D05 EWMA avg_win/avg_loss from r_mi to dollars."""
    print("\n  FIX 1: Convert EWMA values from r_mi to dollars")
    print("  " + "─" * 50)

    from shared.questdb_client import get_cursor

    # Read current EWMA (latest per key)
    with get_cursor() as cur:
        cur.execute("SELECT asset_id, regime, session, win_rate, avg_win, avg_loss, n_trades FROM p3_d05_ewma_states ORDER BY last_updated DESC")
        rows = cur.fetchall()

    seen = set()
    to_fix = []
    for r in rows:
        key = (r[0], r[1], r[2])
        if key in seen:
            continue
        seen.add(key)
        if r[0] in DOLLAR_FACTOR:
            factor = DOLLAR_FACTOR[r[0]]
            old_win = r[4] or 0.01
            old_loss = r[5] or 0.01
            # Only fix if values look like r_mi (< 10.0 — dollar values would be >> 10)
            if old_win < 10.0 and old_loss < 10.0:
                to_fix.append({
                    "asset_id": r[0], "regime": r[1], "session": r[2],
                    "win_rate": r[3], "n_trades": r[6],
                    "old_win": old_win, "old_loss": old_loss,
                    "new_win": round(old_win * factor, 4),
                    "new_loss": round(old_loss * factor, 4),
                    "factor": factor,
                })

    print(f"    Found {len(to_fix)} EWMA entries to convert")

    for entry in to_fix[:3]:  # Show sample
        print(f"    {entry['asset_id']}/{entry['regime']}/s{entry['session']}: "
              f"avg_loss {entry['old_loss']:.4f} r_mi → ${entry['new_loss']:.2f} "
              f"(x{entry['factor']})")

    if dry_run:
        print(f"    [DRY-RUN] Would update {len(to_fix)} rows")
        return

    for entry in to_fix:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d05_ewma_states
                   (asset_id, regime, session, win_rate, avg_win, avg_loss, n_trades, last_updated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
                (entry["asset_id"], entry["regime"], entry["session"],
                 entry["win_rate"], entry["new_win"], entry["new_loss"], entry["n_trades"]),
            )

    print(f"    [OK] Updated {len(to_fix)} EWMA entries to dollar units")


def fix_aim_status(dry_run=False):
    """Set Tier 1 AIMs to ACTIVE for all active assets."""
    print("\n  FIX 2: Activate Tier 1 AIMs")
    print("  " + "─" * 50)

    from shared.questdb_client import get_cursor
    count = 0

    for asset_id in ACTIVE_ASSETS:
        for aim_id in TIER1_AIMS:
            if dry_run:
                count += 1
                continue
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d01_aim_model_states
                       (aim_id, asset_id, status, warmup_progress, last_updated)
                       VALUES (%s, %s, 'ACTIVE', 1.0, now())""",
                    (aim_id, asset_id),
                )
            count += 1

    if dry_run:
        print(f"    [DRY-RUN] Would activate {count} AIMs")
    else:
        print(f"    [OK] {count} Tier 1 AIMs set to ACTIVE ({len(ACTIVE_ASSETS)} assets x {len(TIER1_AIMS)} AIMs)")


def fix_tsm_daily_loss(dry_run=False):
    """Set max_daily_loss for TopstepX 150K Trading Combine.

    TopstepX 150K combine rules: max daily loss = $2,250.
    """
    print("\n  FIX 3: Set TSM max_daily_loss")
    print("  " + "─" * 50)

    if dry_run:
        print("    [DRY-RUN] Would set max_daily_loss=$2250 for account 20319811")
        return

    import json as _json
    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        # Must insert COMPLETE row — QuestDB append-only, partial row overwrites all fields
        cur.execute(
            """INSERT INTO p3_d08_tsm_state (
                account_id, user_id, name, classification,
                starting_balance, current_balance, current_drawdown, daily_loss_used,
                profit_target, max_drawdown_limit, max_daily_loss, max_contracts,
                commission_per_contract, instrument_permissions,
                overnight_allowed, margin_buffer_pct,
                topstep_optimisation, scaling_plan_active, scaling_tier_micros,
                last_updated
            ) VALUES (
                '20319811', 'primary_user', 'Topstep 150K Trading Combine', %s,
                150000.0, 150000.0, 0.0, 0.0,
                6000.0, 4500.0, 2250.0, 15,
                0.0, %s, false, 1.5, true, false, 0, now()
            )""",
            (
                _json.dumps({"provider": "TopstepX", "category": "PROP_EVAL", "stage": "STAGE_1", "risk_goal": "PASS_EVAL"}),
                _json.dumps([]),
            ),
        )
    print("    [OK] account 20319811: complete TSM row with max_daily_loss=$2,250")


def verify(dry_run=False):
    """Verify all fixes."""
    if dry_run:
        return True

    print("\n  VERIFICATION")
    print("  " + "─" * 50)

    from shared.questdb_client import get_cursor
    ok = True

    # Check EWMA values are in dollars (> 10)
    with get_cursor() as cur:
        cur.execute("SELECT asset_id, regime, session, avg_win, avg_loss FROM p3_d05_ewma_states ORDER BY last_updated DESC")
        seen = set()
        rmi_count = 0
        dollar_count = 0
        for r in cur.fetchall():
            key = (r[0], r[1], r[2])
            if key in seen:
                continue
            seen.add(key)
            if r[0] in ACTIVE_ASSETS:
                if r[3] and r[3] > 10:
                    dollar_count += 1
                elif r[3] and r[3] < 10:
                    rmi_count += 1

    print(f"    EWMA: {dollar_count} in dollars, {rmi_count} still in r_mi")
    if rmi_count > 0:
        ok = False

    # Check AIM status
    with get_cursor() as cur:
        cur.execute("SELECT aim_id, asset_id, status FROM p3_d01_aim_model_states ORDER BY last_updated DESC")
        seen = set()
        active_count = 0
        for r in cur.fetchall():
            key = (r[0], r[1])
            if key in seen:
                continue
            seen.add(key)
            if r[1] in ACTIVE_ASSETS and r[0] in TIER1_AIMS and r[2] == "ACTIVE":
                active_count += 1

    expected = len(ACTIVE_ASSETS) * len(TIER1_AIMS)
    print(f"    AIM ACTIVE: {active_count}/{expected} Tier 1 AIMs")
    if active_count < expected:
        ok = False

    # Check TSM daily loss
    with get_cursor() as cur:
        cur.execute("SELECT max_daily_loss FROM p3_d08_tsm_state WHERE account_id = '20319811' ORDER BY last_updated DESC LIMIT 1")
        row = cur.fetchone()
    mdl = row[0] if row else None
    print(f"    TSM max_daily_loss: ${mdl}")
    if mdl is None or mdl <= 0:
        ok = False

    print(f"\n  Result: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("CAPTAIN FUNCTION — Bootstrap Data Fixes")
    print("=" * 60)

    fix_ewma(dry_run=args.dry_run)
    fix_aim_status(dry_run=args.dry_run)
    fix_tsm_daily_loss(dry_run=args.dry_run)
    ok = verify(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("FIXES COMPLETE" if ok else "FIXES INCOMPLETE — check above")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
