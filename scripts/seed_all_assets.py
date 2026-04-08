# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
Multi-asset seed script for Captain System.

Seeds all 17 assets from the multi-asset P1/P2 pipeline into QuestDB:
  - 10 active survivors: full bootstrap (EWMA, BOCPD, Kelly) → captain_status=ACTIVE
  - 1 P2-eliminated (ZT): registered with P2 data → captain_status=P2_ELIMINATED
  - 6 P1-eliminated: registered with P1 refs → captain_status=P1_ELIMINATED

Prerequisites: QuestDB tables must exist (run init_questdb.py first).

Usage (inside captain-offline container):
  python /captain/scripts/seed_all_assets.py [--dry-run]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

_DATA_CANDIDATES = [_PROJECT_ROOT / "data", Path("/captain/data")]


def _find_data_root() -> Path:
    for c in _DATA_CANDIDATES:
        if c.is_dir():
            return c
    raise RuntimeError(f"Cannot locate data directory. Tried: {[str(c) for c in _DATA_CANDIDATES]}")


# ---------------------------------------------------------------------------
# Asset definitions
# ---------------------------------------------------------------------------

# 10 active survivors — these get full bootstrap
ACTIVE_ASSETS = ["ES", "M2K", "MES", "MGC", "MNQ", "MYM", "NKD", "NQ", "ZB", "ZN"]

# P2-eliminated (passed P2 but OO too low for production)
P2_ELIMINATED = ["ZT"]

# P1-eliminated (did not survive P1 filtering)
P1_ELIMINATED = ["6J", "M6A", "M6B", "M6E", "MCL", "SIL"]

TIER1_AIMS = [4, 6, 8, 11, 12, 15]

# Contract specs: point_value, tick_size, margin_per_contract, exchange_timezone, sessions
# point_value = tick_value / tick_size (from contract_ids.json)
ASSET_SPECS = {
    # --- Active 10 ---
    "ES":  {"point_value": 50.0,   "tick_size": 0.25,     "margin": 12650.0, "tz": "America/New_York", "sessions": ["NY"]},
    "MES": {"point_value": 5.0,    "tick_size": 0.25,     "margin": 1265.0,  "tz": "America/New_York", "sessions": ["NY"]},
    "NQ":  {"point_value": 20.0,   "tick_size": 0.25,     "margin": 17600.0, "tz": "America/New_York", "sessions": ["NY"]},
    "MNQ": {"point_value": 2.0,    "tick_size": 0.25,     "margin": 1760.0,  "tz": "America/New_York", "sessions": ["NY"]},
    "M2K": {"point_value": 5.0,    "tick_size": 0.10,     "margin": 700.0,   "tz": "America/New_York", "sessions": ["NY"]},
    "MYM": {"point_value": 0.5,    "tick_size": 1.0,      "margin": 880.0,   "tz": "America/New_York", "sessions": ["NY"]},
    "NKD": {"point_value": 5.0,    "tick_size": 5.0,      "margin": 7700.0,  "tz": "Asia/Tokyo",       "sessions": ["APAC"]},
    "MGC": {"point_value": 10.0,   "tick_size": 0.10,     "margin": 1000.0,  "tz": "America/New_York", "sessions": ["NY"]},
    "ZB":  {"point_value": 1000.0, "tick_size": 0.03125,  "margin": 3300.0,  "tz": "America/Chicago",  "sessions": ["NY"]},
    "ZN":  {"point_value": 1000.0, "tick_size": 0.015625, "margin": 2000.0,  "tz": "America/Chicago",  "sessions": ["NY"]},
    # --- P2-eliminated ---
    "ZT":  {"point_value": 2000.0, "tick_size": 0.0078125,"margin": 1100.0,  "tz": "America/Chicago",  "sessions": ["NY"]},
    # --- P1-eliminated (placeholder specs — not traded) ---
    "6J":  {"point_value": 12500000.0, "tick_size": 0.0000005, "margin": 3300.0, "tz": "America/Chicago", "sessions": ["NY"]},
    "M6A": {"point_value": 10000.0,"tick_size": 0.0001,   "margin": 330.0,   "tz": "America/Chicago",  "sessions": ["NY"]},
    "M6B": {"point_value": 6250.0, "tick_size": 0.0001,   "margin": 330.0,   "tz": "America/Chicago",  "sessions": ["NY"]},
    "M6E": {"point_value": 12500.0,"tick_size": 0.0001,   "margin": 330.0,   "tz": "America/Chicago",  "sessions": ["NY"]},
    "MCL": {"point_value": 100.0,  "tick_size": 0.01,     "margin": 1000.0,  "tz": "America/New_York", "sessions": ["NY"]},
    "SIL": {"point_value": 1000.0, "tick_size": 0.005,    "margin": 5000.0,  "tz": "America/New_York", "sessions": ["NY"]},
}

# Regime label mapping: D-02 uses LOW/MEDIUM/HIGH, bootstrap uses LOW_VOL/HIGH_VOL
_REGIME_MAP = {"LOW": "LOW_VOL", "MEDIUM": "LOW_VOL", "HIGH": "HIGH_VOL"}


# ---------------------------------------------------------------------------
# Data loaders (generic per-asset)
# ---------------------------------------------------------------------------

def load_d22(data_root: Path, asset_id: str) -> list[dict]:
    """Load D-22 trade log for any asset."""
    path = data_root / "p1_outputs" / asset_id / f"d22_trade_log_{asset_id.lower()}.json"
    if not path.exists():
        raise FileNotFoundError(f"D-22 not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    trades = raw if isinstance(raw, list) else raw.get("trades", [])
    if len(trades) < 20:
        raise ValueError(f"D-22 for {asset_id} has only {len(trades)} trades (min 20)")
    print(f"    D-22: {len(trades)} trades ({trades[0]['trade_date']}..{trades[-1]['trade_date']})")
    return trades


def load_d02(data_root: Path, asset_id: str) -> dict[str, str]:
    """Load P2-D02 regime labels for any asset."""
    path = data_root / "p2_outputs" / asset_id / "p2_d02_regime_labels.json"
    if not path.exists():
        raise FileNotFoundError(f"D-02 not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    date_keys = {k for k in raw if not k.startswith("_")}
    if not date_keys:
        print(f"    D-02: PLACEHOLDER (no labels)")
        return {}
    print(f"    D-02: {len(date_keys)} regime labels")
    return {k: v for k, v in raw.items() if k in date_keys}


def load_d06(data_root: Path, asset_id: str) -> dict[str, Any]:
    """Load P2-D06 locked strategy for any asset."""
    path = data_root / "p2_outputs" / asset_id / "p2_d06_locked_strategy.json"
    if not path.exists():
        raise FileNotFoundError(f"D-06 not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    D-06: m={data['m']}, k={data['k']}, OO={data['OO']:.4f}")
    return data


def load_d08(data_root: Path, asset_id: str) -> dict[str, Any]:
    """Load P2-D08 classifier validation for any asset."""
    path = data_root / "p2_outputs" / asset_id / "p2_d08_classifier_validation.json"
    if not path.exists():
        raise FileNotFoundError(f"D-08 not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    D-08: confidence={data['confidence_flag']}")
    return data


# ---------------------------------------------------------------------------
# Data transforms
# ---------------------------------------------------------------------------

def transform_trades(raw: list[dict]) -> list[dict]:
    """D-22 format → bootstrap format: trade_date→date, r_mi→r."""
    return [{"date": t["trade_date"], "r": t["r_mi"], "regime_tag": t.get("regime_tag")} for t in raw]


def map_regimes(labels: dict[str, str]) -> dict[str, str]:
    """Map D-02 labels (LOW/MEDIUM/HIGH) → bootstrap labels (LOW_VOL/HIGH_VOL)."""
    return {date: _REGIME_MAP.get(label, "LOW_VOL") for date, label in labels.items()}


# ---------------------------------------------------------------------------
# QuestDB registration
# ---------------------------------------------------------------------------

def register_asset(
    asset_id: str,
    captain_status: str,
    p1_status: str,
    p2_status: str,
    strategy: dict[str, Any] | None = None,
    classifier: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> None:
    """Insert asset into P3-D00 with appropriate status."""
    spec = ASSET_SPECS[asset_id]

    locked_strategy = json.dumps({
        "model": strategy["m"],
        "feature": strategy["k"],
        "regime_class": strategy["regime_class"],
        "OO": strategy["OO"],
        "accuracy_OOS": classifier["accuracy_OOS"] if classifier else 0.0,
        "confidence_flag": classifier["confidence_flag"] if classifier else "NONE",
        "source": "P2-D06",
    }) if strategy else json.dumps({})

    session_hours = json.dumps({
        "NY":   {"open": "09:30", "close": "16:00"} if "NY" in spec["sessions"] else None,
        "LON":  {"open": "03:00", "close": "11:30"} if "LON" in spec["sessions"] else None,
        "APAC": {"open": "19:00", "close": "04:00"} if "APAC" in spec["sessions"] else None,
    })

    if dry_run:
        print(f"    [DRY-RUN] Would register {asset_id} → {captain_status}")
        return

    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d00_asset_universe (
                asset_id, p1_status, p2_status, captain_status,
                warm_up_progress, aim_warmup_progress, locked_strategy,
                roll_calendar, exchange_timezone, point_value, tick_size,
                margin_per_contract, session_hours, session_schedule,
                p1_data_path, p2_data_path, data_sources, data_quality_flag,
                created, last_updated
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                now(), now()
            )""",
            (
                asset_id, p1_status, p2_status, captain_status,
                0.0, json.dumps({}), locked_strategy,
                json.dumps({}), spec["tz"], spec["point_value"], spec["tick_size"],
                spec["margin"], session_hours, json.dumps(spec["sessions"]),
                f"/captain/data/p1_outputs/{asset_id}/",
                f"/captain/data/p2_outputs/{asset_id}/" if p2_status != "N/A" else "",
                json.dumps({}), "CLEAN",
            ),
        )
    print(f"    [OK] D-00: {asset_id} → captain_status={captain_status}")


def seed_aims(asset_id: str, dry_run: bool = False) -> None:
    """Seed Tier 1 AIMs as INSTALLED for an asset."""
    if dry_run:
        print(f"    [DRY-RUN] Would seed {len(TIER1_AIMS)} AIMs for {asset_id}")
        return
    from shared.questdb_client import get_cursor
    for aim_id in TIER1_AIMS:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d01_aim_model_states
                   (aim_id, asset_id, status, warmup_progress, last_updated)
                   VALUES (%s, %s, 'INSTALLED', 0.0, now())""",
                (aim_id, asset_id),
            )
    print(f"    [OK] D-01: {len(TIER1_AIMS)} Tier 1 AIMs seeded")


def promote_to_active(asset_id: str, dry_run: bool = False) -> None:
    """Set captain_status to ACTIVE after successful bootstrap."""
    if dry_run:
        print(f"    [DRY-RUN] Would promote {asset_id} → ACTIVE")
        return
    from shared.questdb_client import update_d00_fields
    update_d00_fields(asset_id, {
        "captain_status": "ACTIVE",
        "warm_up_progress": 1.0,
    })
    print(f"    [OK] D-00: {asset_id} → ACTIVE")


# ---------------------------------------------------------------------------
# Bootstrap runner
# ---------------------------------------------------------------------------

def run_bootstrap(
    asset_id: str,
    trades: list[dict],
    regime_labels: dict[str, str],
    dry_run: bool = False,
) -> bool:
    """Transform data and run asset_bootstrap()."""
    bootstrap_trades = transform_trades(trades)
    bootstrap_labels = map_regimes(regime_labels)

    if dry_run:
        label_counts = {}
        for v in bootstrap_labels.values():
            label_counts[v] = label_counts.get(v, 0) + 1
        print(f"    [DRY-RUN] Would bootstrap {asset_id}: {len(bootstrap_trades)} trades, labels={label_counts}")
        return True

    try:
        from captain_offline.blocks.bootstrap import asset_bootstrap
        asset_bootstrap(asset_id, bootstrap_trades, bootstrap_labels)
        print(f"    [OK] Bootstrap complete (D-05 EWMA, D-04 BOCPD, D-12 Kelly)")
        return True
    except Exception as exc:
        print(f"    [ERR] Bootstrap failed: {exc}")
        import traceback
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Seed all 17 assets from multi-asset P1/P2 pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing to QuestDB.")
    args = parser.parse_args()

    # Ensure imports resolve inside container
    sys.path.insert(0, str(_PROJECT_ROOT))
    sys.path.insert(0, str(_PROJECT_ROOT / "captain-offline"))
    sys.path.insert(0, "/app")
    sys.path.insert(0, "/app/captain_offline")

    print("=" * 70)
    print("CAPTAIN FUNCTION — Multi-Asset Seed (17 assets from P1/P2 pipeline)")
    print("=" * 70)

    try:
        data_root = _find_data_root()
        print(f"Data root: {data_root}")
    except RuntimeError as exc:
        print(f"[ERR] {exc}")
        return 1

    succeeded = []
    failed = []

    # ── Phase 1: 10 active survivors (full bootstrap) ────────────────────────
    print(f"\n{'='*70}")
    print(f"PHASE 1: Bootstrap 10 active survivors")
    print(f"{'='*70}")

    for asset_id in ACTIVE_ASSETS:
        print(f"\n  [{ACTIVE_ASSETS.index(asset_id)+1}/{len(ACTIVE_ASSETS)}] {asset_id}")
        print(f"  {'─'*40}")

        try:
            # Load data
            trades = load_d22(data_root, asset_id)
            regime_labels = load_d02(data_root, asset_id)
            strategy = load_d06(data_root, asset_id)
            classifier = load_d08(data_root, asset_id)

            # Register in D-00
            register_asset(asset_id, "WARM_UP", "VALIDATED", "VALIDATED",
                           strategy, classifier, dry_run=args.dry_run)

            # Seed AIMs
            seed_aims(asset_id, dry_run=args.dry_run)

            # Run bootstrap
            ok = run_bootstrap(asset_id, trades, regime_labels, dry_run=args.dry_run)
            if not ok:
                failed.append(asset_id)
                continue

            # Promote to ACTIVE
            promote_to_active(asset_id, dry_run=args.dry_run)
            succeeded.append(asset_id)

        except Exception as exc:
            print(f"    [ERR] {asset_id}: {exc}")
            failed.append(asset_id)

    # ── Phase 2: ZT (P2-eliminated) ──────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"PHASE 2: Register P2-eliminated asset (ZT)")
    print(f"{'='*70}")

    for asset_id in P2_ELIMINATED:
        print(f"\n  {asset_id}")
        print(f"  {'─'*40}")

        try:
            strategy = load_d06(data_root, asset_id)
            classifier = load_d08(data_root, asset_id)

            register_asset(asset_id, "P2_ELIMINATED", "VALIDATED", "ELIMINATED",
                           strategy, classifier, dry_run=args.dry_run)
            print(f"    NOTE: OO={strategy['OO']:.4f} — below threshold, not bootstrapped")
            print(f"    Available for future re-testing if strategy improves")
            succeeded.append(asset_id)
        except Exception as exc:
            print(f"    [ERR] {asset_id}: {exc}")
            failed.append(asset_id)

    # ── Phase 3: 6 P1-eliminated ─────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"PHASE 3: Register 6 P1-eliminated assets (dormant)")
    print(f"{'='*70}")

    for asset_id in P1_ELIMINATED:
        print(f"\n  {asset_id}")
        print(f"  {'─'*40}")

        try:
            register_asset(asset_id, "P1_ELIMINATED", "ELIMINATED", "N/A",
                           strategy=None, classifier=None, dry_run=args.dry_run)
            print(f"    Available for future P1 re-testing")
            succeeded.append(asset_id)
        except Exception as exc:
            print(f"    [ERR] {asset_id}: {exc}")
            failed.append(asset_id)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"SEED SUMMARY")
    print(f"{'='*70}")
    print(f"  Succeeded: {len(succeeded)}/{len(ACTIVE_ASSETS) + len(P2_ELIMINATED) + len(P1_ELIMINATED)}")
    print(f"    ACTIVE       : {[a for a in succeeded if a in ACTIVE_ASSETS]}")
    print(f"    P2_ELIMINATED: {[a for a in succeeded if a in P2_ELIMINATED]}")
    print(f"    P1_ELIMINATED: {[a for a in succeeded if a in P1_ELIMINATED]}")
    if failed:
        print(f"  FAILED: {failed}")

    if not args.dry_run and not failed:
        # Verification query
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT count() FROM p3_d00_asset_universe")
            d00_count = cur.fetchone()[0]
            cur.execute("SELECT count() FROM p3_d05_ewma_states")
            d05_count = cur.fetchone()[0]
            cur.execute("SELECT count() FROM p3_d04_decay_detector_states")
            d04_count = cur.fetchone()[0]
            cur.execute("SELECT count() FROM p3_d12_kelly_parameters")
            d12_count = cur.fetchone()[0]
            cur.execute("SELECT count() FROM p3_d01_aim_model_states")
            d01_count = cur.fetchone()[0]

        print(f"\n  QuestDB verification:")
        print(f"    D-00 (asset_universe)  : {d00_count} rows")
        print(f"    D-01 (aim_model_states): {d01_count} rows")
        print(f"    D-04 (decay_detector)  : {d04_count} rows")
        print(f"    D-05 (ewma_states)     : {d05_count} rows")
        print(f"    D-12 (kelly_params)    : {d12_count} rows")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
