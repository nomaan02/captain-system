"""
Load P2 multi-asset results into the Captain system (P3-D00).

Reads P2-D06 locked strategies for all 11 assets from the P2 output runs,
filters D-22 trade logs from pipeline_p2/staging/ to the locked (m, k) pair,
loads P2-D02 regime labels, and prepares each asset for bootstrap.

Data flow:
  P2-D06 (locked strategy)  →  P3-D00.locked_strategy (JSON)
  D-22 (filtered trades)    →  captain-system/data/p1_outputs/{asset}/
  P2-D02 (regime labels)    →  captain-system/data/p2_outputs/{asset}/

Usage:
  python scripts/load_p2_multi_asset.py --dry-run        # Preview without DB writes
  python scripts/load_p2_multi_asset.py                   # Stage data + register in QuestDB
  python scripts/load_p2_multi_asset.py --bootstrap       # Stage + register + run bootstrap
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent          # captain-system/
_REPO_ROOT = _PROJECT_ROOT.parent           # most-production/

# P2 output directories (from the multi-asset runs)
_P2_MAIN_RUN = _REPO_ROOT / "p2_outputs" / "run_20260321_111438"
_P2_NKD_FIX = _REPO_ROOT / "p2_outputs" / "run_20260322_142153"

# D-22 staging (full trade logs from P1 screening)
_D22_STAGING = _REPO_ROOT / "pipeline_p2" / "staging"

# Captain data directory (output target)
_DATA_DIR = _PROJECT_ROOT / "data"

# TopstepX contract IDs (for roll_calendar enrichment)
_CONTRACT_CONFIG_PATH = _PROJECT_ROOT / "config" / "contract_ids.json"
if _CONTRACT_CONFIG_PATH.exists():
    with open(_CONTRACT_CONFIG_PATH, encoding="utf-8") as _f:
        _CONTRACT_CONFIG = json.load(_f)
else:
    _CONTRACT_CONFIG = {}

# ---------------------------------------------------------------------------
# Asset metadata — contract specifications for all 11 assets
# ---------------------------------------------------------------------------

ASSET_METADATA: dict[str, dict[str, Any]] = {
    "ES":  {"point_value": 50.0,   "tick_size": 0.25,     "margin": 15400, "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "ES"},
    "MES": {"point_value": 5.0,    "tick_size": 0.25,     "margin": 1540,  "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "MES"},
    "NQ":  {"point_value": 20.0,   "tick_size": 0.25,     "margin": 18700, "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "NQ"},
    "MNQ": {"point_value": 2.0,    "tick_size": 0.25,     "margin": 1870,  "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "MNQ"},
    "M2K": {"point_value": 5.0,    "tick_size": 0.10,     "margin": 770,   "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "M2K"},
    "MYM": {"point_value": 0.50,   "tick_size": 1.0,      "margin": 880,   "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "MYM"},
    "NKD": {"point_value": 5.0,    "tick_size": 5.0,      "margin": 11000, "tz": "Asia/Tokyo",       "sessions": ["APAC"],        "contract_prefix": "NKD"},
    "MGC": {"point_value": 10.0,   "tick_size": 0.10,     "margin": 1100,  "tz": "America/New_York", "sessions": ["NY", "LON"],   "contract_prefix": "MGC"},
    "ZB":  {"point_value": 1000.0, "tick_size": 0.03125,  "margin": 4400,  "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "ZB"},
    "ZN":  {"point_value": 1000.0, "tick_size": 0.015625, "margin": 2200,  "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "ZN"},
    "ZT":  {"point_value": 2000.0, "tick_size": 0.0078125,"margin": 660,   "tz": "America/New_York", "sessions": ["NY"],          "contract_prefix": "ZT"},
}

# OO threshold — assets below this are excluded from active trading
OO_FLOOR = 0.50

# Tier 1 AIMs to seed (same as seed_real_asset.py)
TIER1_AIMS = [4, 6, 8, 11, 12, 15]

# Regime label mapping: P2-D02 uses LOW/MEDIUM/HIGH → bootstrap uses LOW_VOL/HIGH_VOL
_REGIME_MAP = {"LOW": "LOW_VOL", "MEDIUM": "LOW_VOL", "HIGH": "HIGH_VOL"}


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def load_p2_d06(asset: str) -> dict[str, Any]:
    """Load P2-D06 locked strategy for an asset from the P2 run output."""
    # NKD was in a separate fix run
    if asset == "NKD":
        path = _P2_NKD_FIX / "NKD" / "p2_d06_locked_strategy.json"
    else:
        path = _P2_MAIN_RUN / asset / "p2_d06_locked_strategy.json"

    if not path.exists():
        raise FileNotFoundError(f"P2-D06 not found for {asset}: {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    return data


def load_p2_d02_regime_labels(asset: str) -> dict[str, str]:
    """Load P2-D02 regime labels from the P2 run output.

    The new P2 format is an array: [{"date": "...", "regime_label": "LOW"|null, ...}]
    Returns a dict mapping date → label (LOW/MEDIUM/HIGH), skipping nulls.
    """
    if asset == "NKD":
        path = _P2_NKD_FIX / "NKD" / "p2_d02_regime_labels.json"
    else:
        path = _P2_MAIN_RUN / asset / "p2_d02_regime_labels.json"

    if not path.exists():
        print(f"    [WARN] P2-D02 not found for {asset}: {path} — using empty labels")
        return {}

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # Handle array-of-objects format from P2 pipeline
    if isinstance(raw, list):
        labels = {}
        for entry in raw:
            date = entry.get("date")
            label = entry.get("regime_label")
            if date and label and isinstance(label, str):
                labels[date] = label
        return labels

    # Handle dict format (legacy, from old seed_real_asset.py path)
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}

    return {}


def load_d22_filtered(asset: str, locked_m: int, locked_k: int) -> list[dict[str, Any]]:
    """Load D-22 trade log from staging and filter to the locked (m, k) pair.

    Args:
        asset: Asset identifier (e.g. "ES")
        locked_m: Locked model ID from P2-D06
        locked_k: Locked feature ID from P2-D06

    Returns:
        List of trade dicts filtered to the locked strategy only.
    """
    filename = f"d22_trade_log_{asset.lower()}.json"
    path = _D22_STAGING / filename

    if not path.exists():
        raise FileNotFoundError(f"D-22 staging file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if not isinstance(raw, list):
        raise ValueError(f"D-22 unexpected format for {asset}: expected list, got {type(raw)}")

    # Filter to locked (m, k) pair
    filtered = [t for t in raw if t.get("m") == locked_m and t.get("k") == locked_k]

    return filtered


# ---------------------------------------------------------------------------
# Data transformations
# ---------------------------------------------------------------------------


def transform_trades(raw_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform D-22 format → bootstrap format (date, r, regime_tag)."""
    return [
        {"date": t["trade_date"], "r": t["r_mi"], "regime_tag": t.get("regime_tag")}
        for t in raw_trades
    ]


def map_regime_labels(labels: dict[str, str]) -> dict[str, str]:
    """Map D-02 labels (LOW/MEDIUM/HIGH) → bootstrap labels (LOW_VOL/HIGH_VOL)."""
    return {date: _REGIME_MAP.get(label, "LOW_VOL") for date, label in labels.items()}


# ---------------------------------------------------------------------------
# Data staging — copy filtered data into captain-system/data/
# ---------------------------------------------------------------------------


def stage_asset_data(
    asset: str,
    d06: dict[str, Any],
    d02_labels: dict[str, str],
    d22_filtered: list[dict[str, Any]],
) -> None:
    """Write processed P2 data into captain-system/data/ for the asset."""
    # P2 outputs directory
    p2_dir = _DATA_DIR / "p2_outputs" / asset
    p2_dir.mkdir(parents=True, exist_ok=True)

    # Write D-06
    d06_path = p2_dir / "p2_d06_locked_strategy.json"
    d06_path.write_text(json.dumps(d06, indent=2), encoding="utf-8")

    # Write D-02 as dict format (compatible with seed_real_asset.py)
    d02_path = p2_dir / "p2_d02_regime_labels.json"
    d02_path.write_text(json.dumps(d02_labels, indent=2), encoding="utf-8")

    # Write D-08 placeholder (all assets are C4/BINARY_ONLY — no trained classifier)
    d08 = {
        "asset": asset,
        "accuracy_OOS": 0.0,
        "precision_OOS": 0.0,
        "recall_OOS": 0.0,
        "f1_OOS": 0.0,
        "confidence_flag": "NO_CLASSIFIER",
        "model_type": d06.get("prediction_model_ref", {}).get("model_type", "BINARY_ONLY"),
        "complexity_tier": d06.get("complexity_tier", "C4"),
    }
    d08_path = p2_dir / "p2_d08_classifier_validation.json"
    d08_path.write_text(json.dumps(d08, indent=2), encoding="utf-8")

    # P1 outputs directory — filtered D-22 trades
    p1_dir = _DATA_DIR / "p1_outputs" / asset
    p1_dir.mkdir(parents=True, exist_ok=True)

    d22_path = p1_dir / f"d22_trade_log_{asset.lower()}.json"
    d22_path.write_text(json.dumps(d22_filtered, indent=2), encoding="utf-8")

    print(f"    Staged: D-06, D-02 ({len(d02_labels)} labels), D-08, D-22 ({len(d22_filtered)} trades)")


# ---------------------------------------------------------------------------
# QuestDB registration
# ---------------------------------------------------------------------------


def register_asset_in_d00(
    asset: str,
    d06: dict[str, Any],
    d08: dict[str, Any],
    meta: dict[str, Any],
    status: str = "WARM_UP",
) -> None:
    """Insert asset row into P3-D00 (asset_universe)."""
    sys.path.insert(0, str(_PROJECT_ROOT))
    from shared.questdb_client import get_cursor

    locked_strategy = json.dumps({
        "model": d06["m"],
        "feature": d06["k"],
        "threshold": d06.get("threshold"),
        "regime_class": d06["regime_class"],
        "OO": d06["OO"],
        "composite_score": d06.get("composite_score"),
        "complexity_tier": d06.get("complexity_tier", "C1"),
        "dominant_regime": d06.get("dominant_regime"),
        "accuracy_OOS": d08.get("accuracy_OOS", 0.0),
        "confidence_flag": d08.get("confidence_flag", "NO_CLASSIFIER"),
        "source": "P2-D06",
    })

    session_hours = {}
    for sess in meta["sessions"]:
        if sess == "NY":
            session_hours["NY"] = {"open": "09:30", "close": "16:00"}
        elif sess == "LON":
            session_hours["LON"] = {"open": "03:00", "close": "11:30"}
        elif sess == "APAC":
            session_hours["APAC"] = {"open": "20:00", "close": "04:00"}

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
                asset, "VALIDATED", "VALIDATED", status,
                0.0, json.dumps({}), locked_strategy,
                json.dumps({
                    "current_contract": f"{meta['contract_prefix']}M6",
                    "next_contract": None,
                    "next_roll_date": None,
                    "roll_confirmed": False,
                    "topstep_contract_id": _CONTRACT_CONFIG.get("contracts", {}).get(asset, {}).get("contract_id"),
                }),
                meta["tz"], meta["point_value"], meta["tick_size"],
                meta["margin"], json.dumps(session_hours), json.dumps(meta["sessions"]),
                f"/captain/data/p1_outputs/{asset}/",
                f"/captain/data/p2_outputs/{asset}/",
                json.dumps({}), "CLEAN",
            ),
        )

    # Seed Tier 1 AIMs
    for aim_id in TIER1_AIMS:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d01_aim_model_states
                   (aim_id, asset_id, status, warmup_progress, last_updated)
                   VALUES (%s, %s, 'INSTALLED', 0.0, now())""",
                (aim_id, asset),
            )


# ---------------------------------------------------------------------------
# Bootstrap runner
# ---------------------------------------------------------------------------


def run_bootstrap_for_asset(asset: str) -> bool:
    """Run asset_bootstrap() for a single asset using staged data."""
    sys.path.insert(0, str(_PROJECT_ROOT))
    sys.path.insert(0, str(_PROJECT_ROOT / "captain-offline"))

    from captain_offline.blocks.bootstrap import asset_bootstrap

    # Load staged data
    p1_dir = _DATA_DIR / "p1_outputs" / asset
    p2_dir = _DATA_DIR / "p2_outputs" / asset

    d22_path = p1_dir / f"d22_trade_log_{asset.lower()}.json"
    d02_path = p2_dir / "p2_d02_regime_labels.json"

    with d22_path.open("r") as fh:
        raw_trades = json.load(fh)

    with d02_path.open("r") as fh:
        raw_labels = json.load(fh)

    # Transform
    trades = transform_trades(raw_trades)
    labels = map_regime_labels(raw_labels if isinstance(raw_labels, dict) else {})

    # Run bootstrap
    asset_bootstrap(asset, trades, labels)
    return True


def promote_to_active(asset: str, d06: dict, d08: dict, meta: dict) -> None:
    """Re-insert full asset row with captain_status=ACTIVE after bootstrap.

    QuestDB is append-only — a sparse INSERT with only status fields would
    create a row with NULLs for locked_strategy, point_value, etc.  Instead
    we re-insert the complete row so the latest entry has all fields.
    """
    register_asset_in_d00(asset, d06, d08, meta, status="ACTIVE")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load P2 multi-asset results into Captain system."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing files or DB rows.")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Also run asset_bootstrap() after staging (requires QuestDB).")
    parser.add_argument("--assets", nargs="*", default=None,
                        help="Process specific assets only (default: all 11).")
    args = parser.parse_args()

    assets = args.assets if args.assets else list(ASSET_METADATA.keys())

    print("=" * 70)
    print("CAPTAIN FUNCTION — P2 Multi-Asset Data Bridge")
    print("=" * 70)
    print(f"  P2 main run : {_P2_MAIN_RUN}")
    print(f"  P2 NKD fix  : {_P2_NKD_FIX}")
    print(f"  D-22 staging: {_D22_STAGING}")
    print(f"  Output dir  : {_DATA_DIR}")
    print(f"  Assets      : {', '.join(assets)}")
    print(f"  Mode        : {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Bootstrap   : {'YES' if args.bootstrap else 'NO'}")
    print()

    # Verify P2 run directories exist
    if not _P2_MAIN_RUN.exists():
        print(f"  [ERR] P2 main run not found: {_P2_MAIN_RUN}")
        return 1
    if not _D22_STAGING.exists():
        print(f"  [ERR] D-22 staging not found: {_D22_STAGING}")
        return 1

    results = {}

    for i, asset in enumerate(assets, 1):
        print(f"\n[{i}/{len(assets)}] Processing {asset}")
        print("-" * 50)

        meta = ASSET_METADATA.get(asset)
        if not meta:
            print(f"  [SKIP] No metadata for {asset}")
            results[asset] = "SKIP_NO_METADATA"
            continue

        # Step 1: Load P2-D06 locked strategy
        try:
            d06 = load_p2_d06(asset)
            print(f"  D-06: m={d06['m']}, k={d06['k']}, regime={d06['regime_class']}, OO={d06['OO']:.4f}")
        except FileNotFoundError as exc:
            print(f"  [ERR] {exc}")
            results[asset] = "ERR_NO_D06"
            continue

        # Determine captain_status based on OO score
        if d06["OO"] < OO_FLOOR:
            status = "INACTIVE"
            print(f"  [INFO] OO={d06['OO']:.4f} < {OO_FLOOR} -> INACTIVE (excluded from trading)")
        else:
            status = "WARM_UP"

        # Step 2: Load D-22 trade log (filtered to locked m, k)
        try:
            d22_raw = load_d22_filtered(asset, d06["m"], d06["k"])
            print(f"  D-22: {len(d22_raw)} trades for locked m={d06['m']}, k={d06['k']}")
        except FileNotFoundError as exc:
            print(f"  [ERR] {exc}")
            results[asset] = "ERR_NO_D22"
            continue

        if len(d22_raw) < 20 and status != "INACTIVE":
            print(f"  [WARN] Only {len(d22_raw)} trades — below minimum 20 for bootstrap")
            if len(d22_raw) == 0:
                results[asset] = "ERR_ZERO_TRADES"
                continue

        # Step 3: Load P2-D02 regime labels
        d02_labels = load_p2_d02_regime_labels(asset)
        print(f"  D-02: {len(d02_labels)} regime labels loaded")

        # Step 4: Build D-08 placeholder
        d08 = {
            "accuracy_OOS": 0.0,
            "confidence_flag": "NO_CLASSIFIER",
        }

        if args.dry_run:
            print(f"  [DRY-RUN] Would stage data + register {asset} as {status}")
            date_range = ""
            if d22_raw:
                dates = [t["trade_date"] for t in d22_raw]
                date_range = f" ({min(dates)} .. {max(dates)})"
            print(f"    D-22 filtered: {len(d22_raw)} trades{date_range}")

            label_counts: dict[str, int] = {}
            for v in d02_labels.values():
                mapped = _REGIME_MAP.get(v, "LOW_VOL")
                label_counts[mapped] = label_counts.get(mapped, 0) + 1
            print(f"    D-02 mapped  : {label_counts}")
            results[asset] = f"DRY_RUN_{status}"
            continue

        # Step 5: Stage data files
        print(f"  Staging data files ...")
        stage_asset_data(asset, d06, d02_labels, d22_raw)

        # Step 6: Register in QuestDB (if not dry-run)
        try:
            register_asset_in_d00(asset, d06, d08, meta, status)
            print(f"  [OK] Registered in P3-D00 (captain_status={status})")
        except Exception as exc:
            print(f"  [ERR] QuestDB registration failed: {exc}")
            print(f"        (Data files are staged — retry registration later)")
            results[asset] = "ERR_QUESTDB"
            continue

        # Step 7: Bootstrap (optional)
        if args.bootstrap and status != "INACTIVE":
            print(f"  Running bootstrap ...")
            try:
                run_bootstrap_for_asset(asset)
                promote_to_active(asset, d06, d08, meta)
                print(f"  [OK] Bootstrap complete — {asset} is ACTIVE")
                results[asset] = "ACTIVE"
            except Exception as exc:
                print(f"  [ERR] Bootstrap failed: {exc}")
                results[asset] = "ERR_BOOTSTRAP"
                continue
        else:
            results[asset] = status

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    active = [a for a, s in results.items() if s == "ACTIVE"]
    warmup = [a for a, s in results.items() if s == "WARM_UP"]
    inactive = [a for a, s in results.items() if s == "INACTIVE"]
    errors = [a for a, s in results.items() if s.startswith("ERR")]
    dry_runs = [a for a, s in results.items() if s.startswith("DRY_RUN")]

    for asset, status in sorted(results.items()):
        oo = ""
        try:
            d06 = load_p2_d06(asset)
            oo = f" (OO={d06['OO']:.3f})"
        except Exception:
            pass
        print(f"  {asset:5s} -> {status}{oo}")

    print(f"\n  ACTIVE  : {len(active)}  {active}")
    print(f"  WARM_UP : {len(warmup)}  {warmup}")
    print(f"  INACTIVE: {len(inactive)}  {inactive}")
    print(f"  ERRORS  : {len(errors)}  {errors}")
    if dry_runs:
        print(f"  DRY_RUN : {len(dry_runs)}  {dry_runs}")

    print(f"\n  Total: {len(results)} assets processed")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
