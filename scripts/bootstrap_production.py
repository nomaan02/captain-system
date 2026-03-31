# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
Production Bootstrap — Populates all data gaps required for live trading.

Fixes 5 blockers:
  1. D00: locked_strategy + asset specs (point_value, tick_size, margin, session_hours)
  2. D16: Capital silo linkage (account → user, capital, position limits)
  3. D02: AIM meta-weights (initial equal weights for Tier 1 AIMs)
  4. D25: Circuit breaker params (cold-start defaults)
  5. D00: captain_status → ACTIVE for all 10 survivors

QuestDB is append-only — new rows supersede old ones via ORDER BY last_updated DESC.

Usage (inside captain-command container):
  python /captain/scripts/bootstrap_production.py [--dry-run]
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/app")


# ---------------------------------------------------------------------------
# P2-D06 Locked Strategies (from data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json)
# Each asset has its OWN best (m,k) pair from P2. NEVER use a single pair for all.
# ---------------------------------------------------------------------------

P2_STRATEGIES = {
    "ES":  {"m": 7,  "k": 33,  "feature_threshold": -1.378816,        "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8832, "complexity_tier": "C1"},
    "MES": {"m": 7,  "k": 32,  "feature_threshold": 0.041167,         "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8879, "complexity_tier": "C1"},
    "NQ":  {"m": 3,  "k": 32,  "feature_threshold": -0.020306,        "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8242, "complexity_tier": "C1"},
    "MNQ": {"m": 5,  "k": 32,  "feature_threshold": -0.031505,        "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8236, "complexity_tier": "C1"},
    "M2K": {"m": 5,  "k": 32,  "feature_threshold": -0.015674,        "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.9245, "complexity_tier": "C3"},
    "MYM": {"m": 9,  "k": 115, "feature_threshold": 65.873016,        "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.7705, "complexity_tier": "C1"},
    "NKD": {"m": 6,  "k": 6,   "feature_threshold": 0.174242,         "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8533, "complexity_tier": "C1"},
    "MGC": {"m": 2,  "k": 29,  "feature_threshold": -0.543427,        "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8892, "complexity_tier": "C1"},
    "ZB":  {"m": 10, "k": 113, "feature_threshold": 0.759294,         "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.8054, "complexity_tier": "C1"},
    "ZN":  {"m": 4,  "k": 37,  "feature_threshold": 2.678498,         "regime_method": 1, "regime_class": "REGIME_NEUTRAL", "OO": 0.9058, "complexity_tier": "C1"},
}

# ---------------------------------------------------------------------------
# Asset Specifications (from contract_ids.json / seed_all_assets.py)
# ---------------------------------------------------------------------------

ASSET_SPECS = {
    "ES":  {"point_value": 50.0,   "tick_size": 0.25,     "margin": 12650.0, "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 4.0},
    "MES": {"point_value": 5.0,    "tick_size": 0.25,     "margin": 1265.0,  "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 4.0},
    "NQ":  {"point_value": 20.0,   "tick_size": 0.25,     "margin": 17600.0, "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 20.0},
    "MNQ": {"point_value": 2.0,    "tick_size": 0.25,     "margin": 1760.0,  "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 20.0},
    "M2K": {"point_value": 5.0,    "tick_size": 0.10,     "margin": 700.0,   "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 5.0},
    "MYM": {"point_value": 0.5,    "tick_size": 1.0,      "margin": 880.0,   "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 100.0},
    "NKD": {"point_value": 5.0,    "tick_size": 5.0,      "margin": 7700.0,  "tz": "Asia/Tokyo",       "sessions": ["APAC"], "sl_distance": 125.0},
    "MGC": {"point_value": 10.0,   "tick_size": 0.10,     "margin": 1000.0,  "tz": "America/New_York", "sessions": ["NY"],   "sl_distance": 5.0},
    "ZB":  {"point_value": 1000.0, "tick_size": 0.03125,  "margin": 3300.0,  "tz": "America/Chicago",  "sessions": ["NY"],   "sl_distance": 0.5},
    "ZN":  {"point_value": 1000.0, "tick_size": 0.015625, "margin": 2000.0,  "tz": "America/Chicago",  "sessions": ["NY"],   "sl_distance": 0.25},
}

ACTIVE_ASSETS = list(ASSET_SPECS.keys())
TIER1_AIMS = [4, 6, 8, 11, 12, 15]

# Account and capital config — read from env vars for multi-instance deployment.
# Defaults match Nomaan's primary instance; override via .env on other machines.
ACCOUNT_ID = os.environ.get("BOOTSTRAP_ACCOUNT_ID", "20319811")
USER_ID = os.environ.get("BOOTSTRAP_USER_ID", "primary_user")
STARTING_CAPITAL = float(os.environ.get("BOOTSTRAP_STARTING_CAPITAL", "150000.0"))
MAX_SIMULTANEOUS_POSITIONS = int(os.environ.get("BOOTSTRAP_MAX_POSITIONS", "5"))
MAX_CONTRACTS = int(os.environ.get("BOOTSTRAP_MAX_CONTRACTS", "15"))


def _build_locked_strategy(asset_id: str) -> str:
    """Build the locked_strategy JSON for D00.

    Combines P2-D06 strategy metadata with runtime ORB trading parameters.
    """
    p2 = P2_STRATEGIES[asset_id]
    spec = ASSET_SPECS[asset_id]

    strategy = {
        # P2-D06 strategy identity
        "model": p2["m"],
        "feature": p2["k"],
        "regime_class": p2["regime_class"],
        "OO": p2["OO"],
        "complexity_tier": p2["complexity_tier"],
        "confidence_flag": "NO_CLASSIFIER",
        "accuracy_OOS": 0.0,
        "source": "P2-D06",
        # Feature threshold from P2 (signal generation)
        "feature_threshold": p2["feature_threshold"],
        "regime_method": p2["regime_method"],
        # Regime model fields for B2 _load_regime_models()
        "regime_model_type": "BINARY_ONLY",
        "regime_label": "REGIME_NEUTRAL",
        # Runtime ORB trading parameters for B4/B6
        "default_direction": 0,     # ORB: resolved at Opening Range close
        "tp_multiple": 0.70,        # TP = 0.70x Opening Range width (2:1 ratio with SL)
        "sl_multiple": 0.35,        # SL = 0.35x Opening Range width
        "sl_method": "OR_RANGE",
        "threshold": spec["sl_distance"],  # SL distance in points (B4 Kelly fallback)
        "entry_conditions": {},
    }
    return json.dumps(strategy)


def _build_session_hours(spec: dict) -> str:
    """Build session_hours JSON for D00."""
    hours = {
        "NY":   {"open": "09:30", "close": "16:00"} if "NY" in spec["sessions"] else None,
        "LON":  {"open": "03:00", "close": "11:30"} if "LON" in spec["sessions"] else None,
        "APAC": {"open": "19:00", "close": "04:00"} if "APAC" in spec["sessions"] else None,
    }
    return json.dumps(hours)


# ---------------------------------------------------------------------------
# Phase 1: D00 — Locked strategies + asset specs
# ---------------------------------------------------------------------------

def phase1_update_d00(dry_run: bool = False):
    """INSERT new D00 rows with locked_strategy and asset specs for all 10 active assets.

    QuestDB append-only — these supersede older rows.
    """
    print("\n  PHASE 1: D00 locked strategies + asset specs")
    print("  " + "─" * 50)

    if not dry_run:
        from shared.questdb_client import get_cursor

    for asset_id in ACTIVE_ASSETS:
        spec = ASSET_SPECS[asset_id]
        locked_strategy = _build_locked_strategy(asset_id)
        session_hours = _build_session_hours(spec)
        session_schedule = json.dumps(spec["sessions"])

        if dry_run:
            p2 = P2_STRATEGIES[asset_id]
            print(f"    [DRY-RUN] {asset_id}: m={p2['m']}, k={p2['k']}, "
                  f"OO={p2['OO']:.4f}, pv={spec['point_value']}, "
                  f"tick={spec['tick_size']}, margin={spec['margin']}")
            continue

        from shared.questdb_client import update_d00_fields
        update_d00_fields(asset_id, {
            "captain_status": "ACTIVE",
            "locked_strategy": locked_strategy,
            "point_value": spec["point_value"],
            "tick_size": spec["tick_size"],
            "margin_per_contract": spec["margin"],
            "session_hours": session_hours,
            "session_schedule": session_schedule,
            "exchange_timezone": spec["tz"],
            "warm_up_progress": 1.0,
            "data_quality_flag": "CLEAN",
        })
        p2 = P2_STRATEGIES[asset_id]
        print(f"    [OK] {asset_id}: m={p2['m']}, k={p2['k']}, OO={p2['OO']:.4f}, "
              f"pv={spec['point_value']}, margin={spec['margin']}")

    print(f"  Phase 1 complete: {len(ACTIVE_ASSETS)} assets updated")


# ---------------------------------------------------------------------------
# Phase 2: D16 — Capital silo linkage
# ---------------------------------------------------------------------------

def phase2_update_capital_silo(dry_run: bool = False):
    """INSERT new D16 row linking account to user with capital."""
    print("\n  PHASE 2: D16 capital silo linkage")
    print("  " + "─" * 50)

    accounts_json = json.dumps([ACCOUNT_ID])

    if dry_run:
        print(f"    [DRY-RUN] {USER_ID}: capital={STARTING_CAPITAL}, "
              f"accounts=[{ACCOUNT_ID}], max_pos={MAX_SIMULTANEOUS_POSITIONS}")
        return

    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d16_user_capital_silos (
                user_id, status, role,
                starting_capital, total_capital, accounts,
                max_simultaneous_positions, max_portfolio_risk_pct,
                correlation_threshold, user_kelly_ceiling,
                capital_history, telegram_chat_id, created, last_updated
            ) VALUES (
                %s, 'ACTIVE', 'ADMIN',
                %s, %s, %s,
                %s, 0.10, 0.70, 1.0,
                %s, NULL, now(), now()
            )""",
            (
                USER_ID,
                STARTING_CAPITAL, STARTING_CAPITAL, accounts_json,
                MAX_SIMULTANEOUS_POSITIONS,
                json.dumps([{"date": "2026-03-27", "event": "initial_bootstrap", "capital": STARTING_CAPITAL}]),
            ),
        )
    print(f"    [OK] {USER_ID}: capital=${STARTING_CAPITAL:,.0f}, "
          f"accounts=[{ACCOUNT_ID}], max_pos={MAX_SIMULTANEOUS_POSITIONS}")


# ---------------------------------------------------------------------------
# Phase 3: D02 — AIM meta-weights (initial equal weights)
# ---------------------------------------------------------------------------

def phase3_seed_aim_weights(dry_run: bool = False):
    """Seed D02 with initial equal-weight DMA meta-weights for all Tier 1 AIMs."""
    print("\n  PHASE 3: D02 AIM meta-weights")
    print("  " + "─" * 50)

    # Equal initial weight: each AIM starts fully included
    initial_probability = 1.0 / len(TIER1_AIMS)
    count = 0

    if not dry_run:
        from shared.questdb_client import get_cursor

    for asset_id in ACTIVE_ASSETS:
        for aim_id in TIER1_AIMS:
            if dry_run:
                count += 1
                continue

            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d02_aim_meta_weights (
                        aim_id, asset_id, inclusion_probability, inclusion_flag,
                        recent_effectiveness, days_below_threshold, last_updated
                    ) VALUES (%s, %s, %s, true, 0.0, 0, now())""",
                    (aim_id, asset_id, initial_probability),
                )
            count += 1

    if dry_run:
        print(f"    [DRY-RUN] Would seed {count} rows "
              f"({len(ACTIVE_ASSETS)} assets x {len(TIER1_AIMS)} AIMs)")
    else:
        print(f"    [OK] {count} rows ({len(ACTIVE_ASSETS)} assets x {len(TIER1_AIMS)} AIMs, "
              f"initial_p={initial_probability:.4f})")


# ---------------------------------------------------------------------------
# Phase 4: D25 — Circuit breaker params (cold-start)
# ---------------------------------------------------------------------------

def phase4_seed_circuit_breaker(dry_run: bool = False):
    """Seed D25 with cold-start circuit breaker params for account.

    beta_b=0 disables layers 3-4 until enough trade history accumulates.
    """
    print("\n  PHASE 4: D25 circuit breaker params")
    print("  " + "─" * 50)

    if dry_run:
        print(f"    [DRY-RUN] {ACCOUNT_ID}: cold-start (beta_b=0, layers 3-4 disabled)")
        return

    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d25_circuit_breaker_params (
                account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                n_observations, p_value, last_updated
            ) VALUES (%s, 0, 0.0, 0.0, 1.0, 0.0, 0, 1.0, now())""",
            (ACCOUNT_ID,),
        )
    print(f"    [OK] {ACCOUNT_ID}: cold-start (beta_b=0, layers 3-4 disabled until history accumulates)")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(dry_run: bool = False):
    """Verify all data gaps are filled."""
    if dry_run:
        print("\n  [DRY-RUN] Skipping verification")
        return True

    print("\n  VERIFICATION")
    print("  " + "─" * 50)

    from shared.questdb_client import get_cursor
    ok = True

    with get_cursor() as cur:
        # Check D00 locked strategies
        cur.execute(
            """SELECT asset_id, locked_strategy, point_value, tick_size, margin_per_contract
               FROM p3_d00_asset_universe
               ORDER BY last_updated DESC"""
        )
        rows = cur.fetchall()
        seen = set()
        active_with_strategy = 0
        for r in rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            if r[0] in ACTIVE_ASSETS:
                strat = json.loads(r[1]) if r[1] else {}
                has_model = strat.get("model") is not None
                has_pv = r[2] is not None and r[2] > 0
                if has_model and has_pv:
                    active_with_strategy += 1
                else:
                    print(f"    [FAIL] {r[0]}: model={has_model}, pv={has_pv}")
                    ok = False

        print(f"    D00 locked strategies: {active_with_strategy}/{len(ACTIVE_ASSETS)} active assets")
        if active_with_strategy < len(ACTIVE_ASSETS):
            ok = False

        # Check D16 capital silo
        cur.execute(
            """SELECT user_id, total_capital, accounts, max_simultaneous_positions
               FROM p3_d16_user_capital_silos
               WHERE user_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (USER_ID,),
        )
        row = cur.fetchone()
        if row and row[1] > 0:
            accounts = json.loads(row[2]) if row[2] else []
            print(f"    D16 capital silo: capital=${row[1]:,.0f}, "
                  f"accounts={accounts}, max_pos={row[3]}")
            if not accounts:
                print(f"    [FAIL] D16: accounts list is empty")
                ok = False
        else:
            print(f"    [FAIL] D16: no capital silo or zero capital")
            ok = False

        # Check D02 AIM meta-weights
        cur.execute("SELECT count() FROM p3_d02_aim_meta_weights")
        d02_count = cur.fetchone()[0]
        expected_d02 = len(ACTIVE_ASSETS) * len(TIER1_AIMS)
        print(f"    D02 AIM meta-weights: {d02_count} rows (need >= {expected_d02})")
        if d02_count < expected_d02:
            ok = False

        # Check D25 circuit breaker params
        cur.execute("SELECT count() FROM p3_d25_circuit_breaker_params")
        d25_count = cur.fetchone()[0]
        print(f"    D25 circuit breaker: {d25_count} rows")
        if d25_count < 1:
            ok = False

        # Check supporting tables
        cur.execute("SELECT count() FROM p3_d05_ewma_states")
        d05 = cur.fetchone()[0]
        cur.execute("SELECT count() FROM p3_d12_kelly_parameters")
        d12 = cur.fetchone()[0]
        cur.execute("SELECT count() FROM p3_d01_aim_model_states")
        d01 = cur.fetchone()[0]
        cur.execute("SELECT count() FROM p3_d08_tsm_state")
        d08 = cur.fetchone()[0]
        print(f"    Supporting: D01={d01}, D05={d05}, D08={d08}, D12={d12}")

    status = "PASS" if ok else "FAIL"
    print(f"\n  Verification: {status}")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Production bootstrap — fill all data gaps for live trading.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing.")
    args = parser.parse_args()

    print("=" * 60)
    print("CAPTAIN FUNCTION — Production Bootstrap")
    print("Fills 5 data gaps required for live trading")
    print("=" * 60)

    phase1_update_d00(dry_run=args.dry_run)
    phase2_update_capital_silo(dry_run=args.dry_run)
    phase3_seed_aim_weights(dry_run=args.dry_run)
    phase4_seed_circuit_breaker(dry_run=args.dry_run)
    ok = verify(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    if ok:
        print("BOOTSTRAP COMPLETE — System ready for live trading")
    else:
        print("BOOTSTRAP INCOMPLETE — Check failures above")
    print("=" * 60)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
