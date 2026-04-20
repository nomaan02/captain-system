#!/usr/bin/env python3
"""Session C — verify_bootstrap.py

Confirms that every reference row seeded by bootstrap_production.py is present
in the live QuestDB.  Expected values are read directly from bootstrap_production
itself — nothing is hardcoded here.

Exits 0 if all checks pass; exits 1 and prints a missing-row report otherwise.

Usage (locally):
    python scripts/verify_bootstrap.py

Usage (inside container):
    python /captain/scripts/verify_bootstrap.py
"""
import json
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, "/app")
# bootstrap_production.py lives in scripts/
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import bootstrap_production as bp  # source of truth for expected values
from shared.questdb_client import get_cursor

failures = []


def _fail(msg: str):
    failures.append(msg)
    print(f"  [FAIL] {msg}")


def _ok(msg: str):
    print(f"  [OK]   {msg}")


def check_d00():
    """Every active asset must have locked_strategy and point_value populated."""
    print("\nD00 — asset_universe:")
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, locked_strategy, point_value, tick_size, captain_status
               FROM p3_d00_asset_universe
               ORDER BY last_updated DESC"""
        )
        rows = cur.fetchall()

    # Keep only the latest row per asset (LATEST ON equivalent without WAL)
    seen = set()
    latest = {}
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            latest[r[0]] = r

    for asset_id in bp.ACTIVE_ASSETS:
        row = latest.get(asset_id)
        if row is None:
            _fail(f"{asset_id}: no row in D00")
            continue

        _, strategy_json, point_value, tick_size, captain_status = row

        missing = []
        if not strategy_json:
            missing.append("locked_strategy is NULL")
        else:
            try:
                strat = json.loads(strategy_json)
                if strat.get("model") is None:
                    missing.append("locked_strategy.model is NULL")
            except Exception:
                missing.append("locked_strategy is not valid JSON")

        if point_value is None or point_value <= 0:
            missing.append(f"point_value={point_value}")
        if tick_size is None or tick_size <= 0:
            missing.append(f"tick_size={tick_size}")
        if captain_status != "ACTIVE":
            missing.append(f"captain_status={captain_status!r} (want ACTIVE)")

        if missing:
            _fail(f"{asset_id}: " + ", ".join(missing))
        else:
            _ok(
                f"{asset_id}: m={json.loads(strategy_json)['model']} "
                f"pv={point_value} tick={tick_size}"
            )


def check_d16():
    """Capital silo for USER_ID must exist with correct account linkage."""
    print("\nD16 — user_capital_silos:")
    with get_cursor() as cur:
        cur.execute(
            """SELECT user_id, total_capital, accounts, max_simultaneous_positions
               FROM p3_d16_user_capital_silos
               WHERE user_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (bp.USER_ID,),
        )
        row = cur.fetchone()

    if row is None:
        _fail(f"{bp.USER_ID}: no capital silo row found")
        return

    user_id, total_capital, accounts_json, max_pos = row
    accounts = json.loads(accounts_json) if accounts_json else []

    if total_capital is None or total_capital <= 0:
        _fail(f"{bp.USER_ID}: total_capital={total_capital}")
    else:
        _ok(f"{bp.USER_ID}: capital=${total_capital:,.0f}")

    if bp.ACCOUNT_ID not in accounts:
        _fail(f"{bp.USER_ID}: account {bp.ACCOUNT_ID} not in accounts list {accounts}")
    else:
        _ok(f"{bp.USER_ID}: account {bp.ACCOUNT_ID} linked, max_pos={max_pos}")


def check_d02():
    """D02 must have >= (active_assets * tier1_aims) rows."""
    print("\nD02 — aim_meta_weights:")
    expected = len(bp.ACTIVE_ASSETS) * len(bp.TIER1_AIMS)
    with get_cursor() as cur:
        cur.execute("SELECT count() FROM p3_d02_aim_meta_weights")
        actual = cur.fetchone()[0]

    if actual < expected:
        _fail(f"only {actual} rows, need >= {expected} ({len(bp.ACTIVE_ASSETS)} assets x {len(bp.TIER1_AIMS)} AIMs)")
    else:
        _ok(f"{actual} rows ({len(bp.ACTIVE_ASSETS)} assets x {len(bp.TIER1_AIMS)} AIMs, need >= {expected})")

    # Spot-check: each active asset x each tier-1 AIM has at least one row
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, aim_id, inclusion_probability FROM p3_d02_aim_meta_weights"
        )
        all_rows = cur.fetchall()

    present = {(r[0], r[1]) for r in all_rows}
    missing_pairs = [
        (asset, aim)
        for asset in bp.ACTIVE_ASSETS
        for aim in bp.TIER1_AIMS
        if (asset, aim) not in present
    ]
    if missing_pairs:
        for asset, aim in missing_pairs:
            _fail(f"missing row: asset={asset}, aim_id={aim}")
    else:
        _ok(f"all {len(bp.ACTIVE_ASSETS) * len(bp.TIER1_AIMS)} (asset, aim) pairs present")


def check_d25():
    """D25 must have a circuit-breaker row for ACCOUNT_ID."""
    print("\nD25 — circuit_breaker_params:")
    with get_cursor() as cur:
        cur.execute(
            """SELECT account_id, beta_b, cold_start, model_m
               FROM p3_d25_circuit_breaker_params
               WHERE account_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (bp.ACCOUNT_ID,),
        )
        row = cur.fetchone()

    if row is None:
        _fail(f"{bp.ACCOUNT_ID}: no circuit-breaker row found")
    else:
        _, beta_b, cold_start, model_m = row
        _ok(
            f"{bp.ACCOUNT_ID}: beta_b={beta_b}, cold_start={cold_start}, model_m={model_m}"
        )


def main():
    check_d00()
    check_d16()
    check_d02()
    check_d25()

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed — see report above")
        sys.exit(1)
    else:
        n = len(bp.ACTIVE_ASSETS)
        k = len(bp.TIER1_AIMS)
        print(
            f"PASS: D00 {n} assets, D16 {bp.USER_ID}, "
            f"D02 {n * k} rows, D25 {bp.ACCOUNT_ID} — all seed rows confirmed"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
