"""Fix corrupted locked_strategy data in p3_d00_asset_universe.

On 2026-03-24, all assets were overwritten with the same hardcoded strategy
(model_id=4, feature_id="017") using a schema that doesn't exist in the
codebase. This script restores each asset's correct per-asset strategy
from the staged P2-D06 files.

The correct multi-asset data was originally loaded on 2026-03-22 by
load_p2_multi_asset.py and exists in data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json.

Usage (inside captain-offline container):
    python /captain/scripts/fix_locked_strategies.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Path resolution
_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

_DATA_CANDIDATES = [
    _PROJECT_ROOT / "data",
    Path("/captain/data"),
]

ASSETS = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM", "NKD", "MGC", "ZB", "ZN"]

# ZT excluded: OO=0.366 < 0.50 threshold, marked INACTIVE
INACTIVE_ASSETS = ["ZT"]

# OO floor — assets below this are INACTIVE
OO_FLOOR = 0.50


def _find_data_root() -> Path:
    for candidate in _DATA_CANDIDATES:
        if candidate.is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate data directory. Tried: {_DATA_CANDIDATES}")


def load_d06(data_root: Path, asset: str) -> dict | None:
    path = data_root / "p2_outputs" / asset / "p2_d06_locked_strategy.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_d08(data_root: Path, asset: str) -> dict:
    path = data_root / "p2_outputs" / asset / "p2_d08_classifier_validation.json"
    if not path.exists():
        return {"accuracy_OOS": 0.0, "confidence_flag": "NO_CLASSIFIER"}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_locked_strategy(d06: dict, d08: dict) -> str:
    """Build locked_strategy JSON matching the schema used by load_p2_multi_asset.py."""
    return json.dumps({
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix corrupted locked_strategy data")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("FIX: Restore correct per-asset locked strategies from P2-D06")
    print("=" * 60)

    data_root = _find_data_root()
    print(f"  Data root: {data_root}\n")

    # Step 1: Read all P2-D06 files and show what will be written
    fixes = []
    for asset in ASSETS + INACTIVE_ASSETS:
        d06 = load_d06(data_root, asset)
        if d06 is None:
            print(f"  [SKIP] {asset}: no P2-D06 file found")
            continue
        d08 = load_d08(data_root, asset)
        status = "INACTIVE" if d06["OO"] < OO_FLOOR else "ACTIVE"
        locked = build_locked_strategy(d06, d08)

        print(f"  {asset:5} | m={d06['m']:>2}  k={d06['k']:>3}  OO={d06['OO']:.4f}  "
              f"regime={d06['regime_class']:20}  tier={d06.get('complexity_tier','C1')}  "
              f"-> {status}")
        fixes.append((asset, locked, status))

    if not fixes:
        print("\n  [ERR] No P2-D06 files found. Nothing to fix.")
        return 1

    print(f"\n  Total: {len(fixes)} assets to update")

    if args.dry_run:
        print("\n  [DRY-RUN] No database changes made.")
        return 0

    # Step 2: Write correct data to QuestDB
    sys.path.insert(0, str(_PROJECT_ROOT))
    from shared.questdb_client import get_cursor

    print("\n  Writing to QuestDB...")
    for asset, locked_strategy, status in fixes:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d00_asset_universe
                   (asset_id, p1_status, p2_status, captain_status,
                    locked_strategy, last_updated)
                   VALUES (%s, 'VALIDATED', 'VALIDATED', %s, %s, now())""",
                (asset, status, locked_strategy),
            )
        print(f"  [OK] {asset} -> {status}")

    # Step 3: Verify
    print("\n  Verifying...")
    for asset, _, expected_status in fixes:
        with get_cursor() as cur:
            cur.execute(
                """SELECT locked_strategy, captain_status
                   FROM p3_d00_asset_universe
                   WHERE asset_id = %s
                   ORDER BY last_updated DESC
                   LIMIT 1""",
                (asset,),
            )
            row = cur.fetchone()
            if row:
                strat = json.loads(row[0])
                actual_status = row[1]
                has_model = "model" in strat
                has_model_id = "model_id" in strat
                if has_model and not has_model_id and actual_status == expected_status:
                    print(f"  [OK] {asset}: model={strat['model']}, feature={strat['feature']}, "
                          f"OO={strat['OO']:.4f}, status={actual_status}")
                else:
                    print(f"  [WARN] {asset}: unexpected data — {strat}")
            else:
                print(f"  [WARN] {asset}: no rows found")

    print("\n  Fix complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
