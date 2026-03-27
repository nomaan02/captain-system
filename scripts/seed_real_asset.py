from __future__ import annotations
# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
Seed real P1/P2 asset data for ES into the Captain system.

Reads the extracted P1/P2 JSON files from the data directory and calls
asset_bootstrap() to initialise EWMA, BOCPD, and Kelly state in QuestDB.

Data file locations (host-side paths, mapped into Docker as /captain/data/):
  P1-D22:  captain-system/data/p1_outputs/ES/d22_trade_log_es.json
  P2-D02:  captain-system/data/p2_outputs/ES/p2_d02_regime_labels.json
  P2-D06:  captain-system/data/p2_outputs/ES/p2_d06_locked_strategy.json
  P2-D08:  captain-system/data/p2_outputs/ES/p2_d08_classifier_validation.json

Note on D-22 coverage:
  Early trades from 2009-01-01 through approximately 2012-11-06 were
  truncated during QC Object Store extraction. The 400+ trades present
  in the file exceed the minimum 20 required for asset_bootstrap().

Note on D-02:
  The p2_d02_regime_labels.json file contains 4426 regime labels (LOW/MEDIUM/HIGH).
  These are mapped to LOW_VOL/HIGH_VOL for bootstrap consumption.

Note on data transformations:
  D-22 fields (trade_date, r_mi) are mapped to bootstrap fields (date, r).
  D-02 labels (LOW, MEDIUM, HIGH) are mapped to (LOW_VOL, LOW_VOL, HIGH_VOL).

Usage:
  python scripts/seed_real_asset.py [--dry-run]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path resolution — works both from project root and from within Docker
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent  # captain-system/

# On Docker the data directory is mounted at /captain/data/; on the host it
# lives at captain-system/data/.  We probe both.
_DATA_CANDIDATES = [
    _PROJECT_ROOT / "data",
    Path("/captain/data"),
]


def _find_data_root() -> Path:
    """Return the first data directory candidate that exists."""
    for candidate in _DATA_CANDIDATES:
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        f"Cannot locate data directory.  Tried: {[str(c) for c in _DATA_CANDIDATES]}"
    )


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------


def load_d22_trade_log(data_root: Path) -> list[dict[str, Any]]:
    """Load the D-22 trade log for ES.

    Args:
        data_root: Root data directory containing p1_outputs/.

    Returns:
        List of trade dicts with keys: trade_date, r_mi, regime_tag, s.

    Raises:
        FileNotFoundError: If the JSON file is missing.
        ValueError: If the file structure is unexpected.
    """
    path = data_root / "p1_outputs" / "ES" / "d22_trade_log_es.json"
    if not path.exists():
        raise FileNotFoundError(f"D-22 trade log not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if isinstance(raw, list):
        trades = raw
    elif isinstance(raw, dict) and "trades" in raw:
        trades = raw["trades"]
    else:
        raise ValueError(f"Unexpected D-22 structure in {path}")

    if len(trades) < 20:
        raise ValueError(
            f"D-22 has only {len(trades)} trades — bootstrap requires at least 20."
        )

    print(f"  [OK] D-22: loaded {len(trades)} trades  ({trades[0]['trade_date']} .. {trades[-1]['trade_date']})")
    return trades


def load_d02_regime_labels(data_root: Path) -> dict[str, str]:
    """Load the P2-D02 regime labels for ES.

    Args:
        data_root: Root data directory containing p2_outputs/.

    Returns:
        Dict mapping ISO date string -> regime label (LOW | MEDIUM | HIGH).
        Returns an empty dict if the file is the placeholder.
    """
    path = data_root / "p2_outputs" / "ES" / "p2_d02_regime_labels.json"
    if not path.exists():
        raise FileNotFoundError(f"P2-D02 regime labels not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # Placeholder detection — only has _meta, no actual date keys
    date_keys = {k for k in raw if not k.startswith("_")}
    if not date_keys:
        print(
            "  [WARN] P2-D02 is a placeholder — no regime labels loaded.  "
            "Run generate_d02_from_inline() or populate the file first."
        )
        return {}

    valid_labels = {"LOW", "MEDIUM", "HIGH"}
    bad = [v for v in raw.values() if v not in valid_labels and not str(v).startswith("{")]
    if bad:
        print(f"  [WARN] D-02: {len(bad)} unexpected label values found.")

    print(f"  [OK] D-02: loaded {len(date_keys)} regime labels  (sample: {list(date_keys)[:3]})")
    return {k: v for k, v in raw.items() if k in date_keys}


def load_d06_locked_strategy(data_root: Path) -> dict[str, Any]:
    """Load the P2-D06 locked strategy for ES.

    Args:
        data_root: Root data directory containing p2_outputs/.

    Returns:
        Dict with keys: asset, m, k, threshold, regime_class, OO, etc.
    """
    path = data_root / "p2_outputs" / "ES" / "p2_d06_locked_strategy.json"
    if not path.exists():
        raise FileNotFoundError(f"P2-D06 locked strategy not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    print(f"  [OK] D-06: m={data['m']}, k={data['k']}, regime_class={data['regime_class']}, OO={data['OO']:.4f}")
    return data


def load_d08_classifier_validation(data_root: Path) -> dict[str, Any]:
    """Load the P2-D08 classifier validation for ES.

    Args:
        data_root: Root data directory containing p2_outputs/.

    Returns:
        Dict with keys: accuracy_OOS, precision_OOS, recall_OOS, f1_OOS, etc.
    """
    path = data_root / "p2_outputs" / "ES" / "p2_d08_classifier_validation.json"
    if not path.exists():
        raise FileNotFoundError(f"P2-D08 classifier validation not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    print(f"  [OK] D-08: accuracy_OOS={data['accuracy_OOS']:.4f}, confidence={data['confidence_flag']}")
    return data


# ---------------------------------------------------------------------------
# D-02 inline population helper
# ---------------------------------------------------------------------------


def generate_d02_from_inline() -> dict[str, str]:
    """Return the full P2-D02 regime labels dict from inline data.

    Populate the ``_INLINE_D02`` dict below with the 4268 entries extracted
    from the QC Object Store.  Each key is an ISO date string (YYYY-MM-DD)
    and each value is one of: "LOW", "MEDIUM", "HIGH".

    The dict is intentionally left empty here — paste the extracted CSV rows
    as ``"YYYY-MM-DD": "LABEL"`` entries before calling this function.

    Returns:
        Dict mapping date string -> regime label.

    Example usage::

        labels = generate_d02_from_inline()
        out = data_root / "p2_outputs" / "ES" / "p2_d02_regime_labels.json"
        out.write_text(json.dumps(labels, indent=2))
        print(f"Wrote {len(labels)} labels to {out}")
    """
    # ---------------------------------------------------------------------------
    # PASTE EXTRACTED D-02 DATA BELOW (format: "YYYY-MM-DD": "LOW|MEDIUM|HIGH")
    # Expected: 4268 entries from 2009-03-12 to 2026-02-27
    # ---------------------------------------------------------------------------
    _INLINE_D02: dict[str, str] = {
        # "2009-03-12": "LOW",
        # "2009-03-13": "LOW",
        # ... paste all 4268 rows here ...
        # "2026-02-27": "LOW",
    }
    # ---------------------------------------------------------------------------

    if not _INLINE_D02:
        print("  [WARN] generate_d02_from_inline(): inline dict is empty — paste D-02 data first.")

    return _INLINE_D02


def write_d02_from_inline(data_root: Path) -> int:
    """Generate D-02 from inline data and write to disk.

    Args:
        data_root: Root data directory.

    Returns:
        Number of labels written.
    """
    labels = generate_d02_from_inline()
    if not labels:
        print("  [SKIP] D-02 write skipped — inline dict is empty.")
        return 0

    out_path = data_root / "p2_outputs" / "ES" / "p2_d02_regime_labels.json"
    out_path.write_text(json.dumps(labels, indent=2), encoding="utf-8")
    print(f"  [OK] D-02: wrote {len(labels)} labels to {out_path}")
    return len(labels)


# ---------------------------------------------------------------------------
# Data transformations — bridge file formats to bootstrap expectations
# ---------------------------------------------------------------------------

# Regime label mapping: D-02 uses LOW/MEDIUM/HIGH, bootstrap uses LOW_VOL/HIGH_VOL
_REGIME_MAP = {"LOW": "LOW_VOL", "MEDIUM": "LOW_VOL", "HIGH": "HIGH_VOL"}


def _transform_trades(raw_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform D-22 trade format to bootstrap format.

    D-22 fields: trade_date, r_mi, regime_tag, s, m, k
    Bootstrap expects: date, r, regime_tag
    """
    return [
        {"date": t["trade_date"], "r": t["r_mi"], "regime_tag": t.get("regime_tag")}
        for t in raw_trades
    ]


def _map_regime_labels(labels: dict[str, str]) -> dict[str, str]:
    """Map D-02 labels (LOW/MEDIUM/HIGH) to bootstrap labels (LOW_VOL/HIGH_VOL)."""
    return {date: _REGIME_MAP.get(label, "LOW_VOL") for date, label in labels.items()}


# ---------------------------------------------------------------------------
# QuestDB pre-registration — asset must exist before bootstrap
# ---------------------------------------------------------------------------

TIER1_AIMS = [4, 6, 8, 11, 12, 15]


def _ensure_asset_registered(
    asset_id: str,
    strategy: dict[str, Any],
    classifier: dict[str, Any],
    dry_run: bool = False,
) -> None:
    """Insert asset into P3-D00 and Tier 1 AIMs into P3-D01 if not present."""
    if dry_run:
        print(f"  [DRY-RUN] Would register {asset_id} in P3-D00 + {len(TIER1_AIMS)} AIMs in P3-D01")
        return

    sys.path.insert(0, str(_PROJECT_ROOT))
    from shared.questdb_client import get_cursor

    locked_strategy = json.dumps({
        "model": strategy["m"],
        "feature": strategy["k"],
        "regime_class": strategy["regime_class"],
        "OO": strategy["OO"],
        "accuracy_OOS": classifier["accuracy_OOS"],
        "confidence_flag": classifier["confidence_flag"],
        "source": "P2-D06",
    })
    session_hours = json.dumps({
        "NY": {"open": "09:30", "close": "16:00"},
        "LON": None,
        "APAC": None,
    })

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
                asset_id, "VALIDATED", "VALIDATED", "WARM_UP",
                0.0, json.dumps({}), locked_strategy,
                json.dumps({"current_contract": "ESM6", "next_contract": "ESU6",
                            "next_roll_date": "2026-09-18", "roll_confirmed": False}),
                "America/New_York", 50.0, 0.25,
                12650.0, session_hours, json.dumps(["NY"]),
                "/captain/data/p1_outputs/ES/", "/captain/data/p2_outputs/ES/",
                json.dumps({}), "CLEAN",
            ),
        )
    print(f"  [OK] P3-D00: {asset_id} registered (captain_status=WARM_UP)")

    # Seed Tier 1 AIMs as INSTALLED so bootstrap can promote to BOOTSTRAPPED
    for aim_id in TIER1_AIMS:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d01_aim_model_states
                   (aim_id, asset_id, status, warmup_progress, last_updated)
                   VALUES (%s, %s, 'INSTALLED', 0.0, now())""",
                (aim_id, asset_id),
            )
    print(f"  [OK] P3-D01: {len(TIER1_AIMS)} Tier 1 AIMs seeded as INSTALLED")


def _promote_to_active(asset_id: str, dry_run: bool = False) -> None:
    """Set captain_status to ACTIVE after successful bootstrap."""
    if dry_run:
        print(f"  [DRY-RUN] Would set {asset_id} captain_status=ACTIVE")
        return

    from shared.questdb_client import get_cursor

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d00_asset_universe
               (asset_id, captain_status, warm_up_progress, last_updated)
               VALUES (%s, 'ACTIVE', 1.0, now())""",
            (asset_id,),
        )
    print(f"  [OK] P3-D00: {asset_id} captain_status -> ACTIVE")


# ---------------------------------------------------------------------------
# Bootstrap bridge
# ---------------------------------------------------------------------------


def run_asset_bootstrap(
    asset_id: str,
    trades: list[dict[str, Any]],
    regime_labels: dict[str, str],
    strategy: dict[str, Any],
    classifier: dict[str, Any],
    dry_run: bool = False,
) -> bool:
    """Call asset_bootstrap() with real P1/P2 data for the given asset.

    Transforms data formats and pre-registers the asset before calling bootstrap.

    Args:
        asset_id: Asset identifier (e.g. "ES").
        trades: List of trade dicts from D-22 (raw format).
        regime_labels: Dict of date -> label from D-02 (raw format).
        strategy: Locked strategy dict from D-06.
        classifier: Classifier validation dict from D-08.
        dry_run: If True, print what would be written without committing.

    Returns:
        True on success, False on failure.
    """
    # Transform data to bootstrap-expected formats
    bootstrap_trades = _transform_trades(trades)
    bootstrap_labels = _map_regime_labels(regime_labels)

    if dry_run:
        print(f"\n  [DRY-RUN] asset_bootstrap payload for {asset_id}:")
        print(f"    trades         : {len(bootstrap_trades)} records (date/r/regime_tag)")
        print(f"    regime_labels  : {len(bootstrap_labels)} records (LOW_VOL/HIGH_VOL)")
        print(f"    m={strategy['m']}, k={strategy['k']}, OO={strategy['OO']:.4f}")
        print(f"    accuracy_OOS   : {classifier['accuracy_OOS']:.4f}")
        sample = bootstrap_trades[0] if bootstrap_trades else {}
        print(f"    sample trade   : {sample}")
        label_counts = {}
        for v in bootstrap_labels.values():
            label_counts[v] = label_counts.get(v, 0) + 1
        print(f"    label counts   : {label_counts}")
        _ensure_asset_registered(asset_id, strategy, classifier, dry_run=True)
        _promote_to_active(asset_id, dry_run=True)
        print("  [DRY-RUN] No DB writes performed.")
        return True

    # Add all package directories to sys.path so imports resolve
    sys.path.insert(0, str(_PROJECT_ROOT))
    sys.path.insert(0, str(_PROJECT_ROOT / "captain-offline"))
    sys.path.insert(0, str(_PROJECT_ROOT / "captain-online"))
    sys.path.insert(0, str(_PROJECT_ROOT / "captain-command"))

    # Step 1: Register asset in D-00 + seed AIM states
    try:
        _ensure_asset_registered(asset_id, strategy, classifier)
    except Exception as exc:
        print(f"  [ERR] Asset registration failed: {exc}")
        return False

    # Step 2: Run bootstrap (writes D-05 EWMA, D-04 BOCPD, D-12 Kelly, promotes AIMs)
    try:
        from captain_offline.blocks.bootstrap import asset_bootstrap
        asset_bootstrap(asset_id, bootstrap_trades, bootstrap_labels)
        print(f"  [OK] asset_bootstrap() completed for {asset_id}")
    except ImportError as exc:
        print(f"  [ERR] Cannot import captain_offline.blocks.bootstrap: {exc}")
        print("        Ensure captain-offline is installed or PYTHONPATH is set correctly.")
        return False
    except Exception as exc:
        print(f"  [ERR] asset_bootstrap() raised: {exc}")
        return False

    # Step 3: Promote to ACTIVE
    try:
        _promote_to_active(asset_id)
    except Exception as exc:
        print(f"  [ERR] Promotion to ACTIVE failed: {exc}")
        return False

    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Main entry point for the seed script.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    parser = argparse.ArgumentParser(
        description="Seed real P1/P2 ES data and call asset_bootstrap()."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching QuestDB.",
    )
    parser.add_argument(
        "--write-d02",
        action="store_true",
        help="Regenerate p2_d02_regime_labels.json from inline data before bootstrapping.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("CAPTAIN FUNCTION — Real Asset Seed (ES, k=17)")
    print("=" * 60)

    try:
        data_root = _find_data_root()
        print(f"  [OK] Data root: {data_root}")
    except RuntimeError as exc:
        print(f"  [ERR] {exc}")
        return 1

    # Optionally regenerate D-02 from inline data
    if args.write_d02:
        print("\n[1/5] Writing D-02 from inline data ...")
        write_d02_from_inline(data_root)

    # Load all four data files
    print("\n[2/5] Loading P1/P2 data files ...")
    try:
        trades = load_d22_trade_log(data_root)
        regime_labels = load_d02_regime_labels(data_root)
        strategy = load_d06_locked_strategy(data_root)
        classifier = load_d08_classifier_validation(data_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"  [ERR] {exc}")
        return 1

    # Summary
    print(f"\n[3/6] Data summary:")
    print(f"  D-22 trades       : {len(trades)}")
    print(f"  D-02 regime labels: {len(regime_labels)}  ({'populated' if regime_labels else 'PLACEHOLDER — bootstrap will use trade-level VIX tags only'})")
    print(f"  D-06 strategy     : m={strategy['m']}, k={strategy['k']}, {strategy['regime_class']}")
    print(f"  D-08 accuracy     : {classifier['accuracy_OOS']:.4f} ({classifier['confidence_flag']})")

    # Transform data
    print(f"\n[4/6] Transforming data formats ...")
    transformed_trades = _transform_trades(trades)
    mapped_labels = _map_regime_labels(regime_labels)
    label_counts: dict[str, int] = {}
    for v in mapped_labels.values():
        label_counts[v] = label_counts.get(v, 0) + 1
    print(f"  [OK] Trades: trade_date->date, r_mi->r  ({len(transformed_trades)} records)")
    print(f"  [OK] Labels: LOW/MEDIUM->LOW_VOL, HIGH->HIGH_VOL  {label_counts}")

    # Call bootstrap
    print(f"\n[5/6] Running bootstrap pipeline for ES {'(dry-run)' if args.dry_run else ''} ...")
    success = run_asset_bootstrap(
        asset_id="ES",
        trades=trades,
        regime_labels=regime_labels,
        strategy=strategy,
        classifier=classifier,
        dry_run=args.dry_run,
    )

    # Result
    print(f"\n[6/6] {'DRY-RUN complete.' if args.dry_run else ('Bootstrap SUCCEEDED — ES is ACTIVE.' if success else 'Bootstrap FAILED.')}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
