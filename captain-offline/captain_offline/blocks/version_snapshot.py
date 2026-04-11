# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Version Snapshot Policy (Task 2.1e / OFF lines 159-225).

VERSIONED_COMPONENTS = [P3-D01, P3-D02, P3-D05, P3-D12, P3-D17.system_params]

Every update to these components MUST call snapshot_before_update() first.
Snapshots are stored in P3-D18 (version_history_store).
Max 50 versions per component in hot storage.
"""

import json
import uuid
import hashlib
import logging
from datetime import datetime

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS
from shared.constants import now_et

logger = logging.getLogger(__name__)

MAX_VERSIONS_PER_COMPONENT = 50
COLD_STORAGE_AGE_DAYS = 90

VERSIONED_COMPONENTS = [
    "P3-D01",  # AIM model states
    "P3-D02",  # AIM meta-weights
    "P3-D05",  # EWMA states
    "P3-D12",  # Kelly parameters
    "P3-D17.system_params",  # System parameters
]

# Valid trigger reasons
TRIGGERS = {
    "DMA_UPDATE",
    "AIM_RETRAIN",
    "KELLY_UPDATE",
    "EWMA_UPDATE",
    "PARAM_CHANGE",
    "INJECTION_ADOPT",
    "ROLLBACK",
}

# Component → live table mapping for get_current_state / restore_state
_COMPONENT_TABLES = {
    "P3-D01": {
        "table": "p3_d01_aim_model_states",
        "columns": ["aim_id", "asset_id", "status", "model_object",
                     "warmup_progress", "current_modifier",
                     "last_retrained", "missing_data_rate_30d"],
        "key_cols": ["aim_id", "asset_id"],
        "update_type": None,  # not directly tradeable
    },
    "P3-D02": {
        "table": "p3_d02_aim_meta_weights",
        "columns": ["aim_id", "asset_id", "inclusion_probability",
                     "inclusion_flag", "recent_effectiveness",
                     "days_below_threshold"],
        "key_cols": ["aim_id", "asset_id"],
        "update_type": "AIM_WEIGHT_CHANGE",
    },
    "P3-D05": {
        "table": "p3_d05_ewma_states",
        "columns": ["asset_id", "regime", "session", "win_rate",
                     "avg_win", "avg_loss", "n_trades"],
        "key_cols": ["asset_id", "regime", "session"],
        "update_type": "KELLY_UPDATE",
    },
    "P3-D12": {
        "table": "p3_d12_kelly_parameters",
        "columns": ["asset_id", "regime", "session", "kelly_full",
                     "shrinkage_factor", "sizing_override"],
        "key_cols": ["asset_id", "regime", "session"],
        "update_type": "KELLY_UPDATE",
    },
    "P3-D17.system_params": {
        "table": "p3_d17_system_monitor_state",
        "columns": ["param_key", "param_value", "category"],
        "key_cols": ["param_key"],
        "update_type": None,
    },
}


def _compute_hash(state: dict) -> str:
    """Compute SHA-256 hash of a state dict for integrity verification."""
    raw = json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# G-OFF-048: get_current_state helper
# ---------------------------------------------------------------------------

def get_current_state(component_id: str) -> dict:
    """Load current live state from the backing table for a versioned component.

    Returns:
        Dict with 'component' and 'rows' keys, matching the snapshot format.
    """
    if component_id not in _COMPONENT_TABLES:
        raise ValueError(f"Unknown component: {component_id}. "
                         f"Valid: {list(_COMPONENT_TABLES)}")

    spec = _COMPONENT_TABLES[component_id]
    col_str = ", ".join(spec["columns"])

    with get_cursor() as cur:
        cur.execute(f"SELECT {col_str} FROM {spec['table']}")
        raw_rows = cur.fetchall()

    # Deduplicate by key columns — keep last occurrence (latest insert)
    key_indices = [spec["columns"].index(k) for k in spec["key_cols"]]
    seen: dict[tuple, dict] = {}
    for row in raw_rows:
        key = tuple(row[i] for i in key_indices)
        seen[key] = dict(zip(spec["columns"], row))

    return {"component": component_id, "rows": list(seen.values())}


# ---------------------------------------------------------------------------
# G-OFF-047: MAX_VERSIONS enforcement + cold storage pruning
# ---------------------------------------------------------------------------

def _enforce_max_versions(component_id: str):
    """Prune snapshots exceeding MAX_VERSIONS_PER_COMPONENT.

    Versions older than COLD_STORAGE_AGE_DAYS are logged as cold-storage
    migrations. Oldest excess versions are deleted from D18.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT version_id, ts FROM p3_d18_version_history
               WHERE component = %s ORDER BY ts DESC""",
            (component_id,),
        )
        versions = cur.fetchall()

    if len(versions) <= MAX_VERSIONS_PER_COMPONENT:
        return

    to_prune = versions[MAX_VERSIONS_PER_COMPONENT:]
    for vid, ts in to_prune:
        logger.info("Cold-storage migration: pruning version %s "
                     "(component=%s, ts=%s)", vid, component_id, ts)

    # Batch delete by timestamp cutoff
    cutoff_ts = versions[MAX_VERSIONS_PER_COMPONENT - 1][1]
    try:
        with get_cursor() as cur:
            cur.execute(
                """DELETE FROM p3_d18_version_history
                   WHERE component = %s AND ts < %s""",
                (component_id, cutoff_ts),
            )
        logger.info("Pruned %d versions for %s (MAX_VERSIONS=%d)",
                     len(to_prune), component_id, MAX_VERSIONS_PER_COMPONENT)
    except Exception as e:
        logger.warning("Could not prune old versions for %s: %s "
                       "(manual cleanup needed)", component_id, e)


def snapshot_before_update(component_id: str, trigger_reason: str,
                           state: dict | None = None) -> str:
    """Save a timestamped snapshot of component state BEFORE modifying it.

    Args:
        component_id: One of VERSIONED_COMPONENTS (e.g., "P3-D01")
        trigger_reason: One of TRIGGERS (e.g., "DMA_UPDATE")
        state: Component state dict. If None, loads automatically via
               get_current_state() (spec: Doc 32 Version Snapshot Policy).

    Returns:
        version_id (UUID string)
    """
    if component_id not in VERSIONED_COMPONENTS:
        raise ValueError(f"Component {component_id} is not versioned. "
                         f"Valid: {VERSIONED_COMPONENTS}")
    if trigger_reason not in TRIGGERS:
        raise ValueError(f"Invalid trigger: {trigger_reason}. Valid: {TRIGGERS}")

    # G-OFF-048: auto-load current state if not provided
    if state is None:
        state = get_current_state(component_id)

    version_id = str(uuid.uuid4())
    model_hash = _compute_hash(state)
    state_json = json.dumps(state, default=str)

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d18_version_history
               (version_id, component, trigger, state, model_hash, ts)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (version_id, component_id, trigger_reason, state_json, model_hash),
        )

    # G-OFF-047: enforce MAX_VERSIONS after each write
    _enforce_max_versions(component_id)

    return version_id


def get_latest_version(component_id: str) -> dict | None:
    """Get the most recent snapshot for a component."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT version_id, component, trigger, state, model_hash, ts
               FROM p3_d18_version_history
               WHERE component = %s
               ORDER BY ts DESC
               LIMIT 1""",
            (component_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "version_id": row[0],
        "component": row[1],
        "trigger": row[2],
        "state": json.loads(row[3]) if row[3] else None,
        "model_hash": row[4],
        "timestamp": row[5],
    }


def _get_version(version_id: str) -> dict | None:
    """Load a specific version snapshot from D18 by version_id."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT version_id, component, trigger, state, model_hash, ts
               FROM p3_d18_version_history
               WHERE version_id = %s""",
            (version_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "version_id": row[0],
        "component": row[1],
        "trigger": row[2],
        "state": json.loads(row[3]) if row[3] else None,
        "model_hash": row[4],
        "timestamp": row[5],
    }


# ---------------------------------------------------------------------------
# G-OFF-046: rollback_to_version with pseudotrader comparison
# ---------------------------------------------------------------------------

def _restore_state(component_id: str, state: dict):
    """Restore a saved state to the live backing table.

    Inserts new rows with current timestamp so they become the latest state.
    """
    spec = _COMPONENT_TABLES[component_id]
    rows = state.get("rows", [])
    if not rows:
        logger.warning("No rows to restore for %s", component_id)
        return

    columns = spec["columns"]
    col_str = ", ".join(columns + ["last_updated"])
    placeholders = ", ".join(["%s"] * len(columns) + ["now()"])

    with get_cursor() as cur:
        for row_dict in rows:
            vals = tuple(row_dict.get(c) for c in columns)
            cur.execute(
                f"INSERT INTO {spec['table']} ({col_str}) VALUES ({placeholders})",
                vals,
            )

    logger.info("Restored %d rows to %s for %s",
                len(rows), spec["table"], component_id)


def _run_rollback_comparison(component_id: str, current_state: dict,
                             target_state: dict) -> dict:
    """Run pseudotrader comparison between current and target (rollback) states.

    For tradeable components (D02, D05, D12), runs signal replay comparison
    per asset. For non-tradeable components (D01, D17), skips comparison.
    """
    spec = _COMPONENT_TABLES.get(component_id)
    if not spec or not spec["update_type"]:
        return {"recommendation": "ADOPT", "reason": "NO_COMPARISON_NEEDED"}

    from captain_offline.blocks.b3_pseudotrader import run_signal_replay_comparison

    target_rows = target_state.get("rows", [])
    assets = sorted({r["asset_id"] for r in target_rows if "asset_id" in r})

    if not assets:
        return {"recommendation": "ADOPT", "reason": "NO_ASSETS_IN_STATE"}

    results = []
    for asset_id in assets:
        proposed_update = {"update_type": spec["update_type"]}

        if spec["update_type"] == "AIM_WEIGHT_CHANGE":
            proposed_update["proposed_aim_weights"] = {
                r["aim_id"]: r["inclusion_probability"]
                for r in target_rows if r.get("asset_id") == asset_id
            }
        elif spec["update_type"] == "KELLY_UPDATE":
            kelly_by_regime: dict[str, dict] = {}
            for r in target_rows:
                if r.get("asset_id") != asset_id:
                    continue
                regime = r.get("regime", "LOW_VOL")
                kelly_by_regime[regime] = {
                    "kelly_full": r.get("kelly_full", 0),
                    "shrinkage_factor": r.get("shrinkage_factor", 1.0),
                }
            proposed_update["proposed_kelly_params"] = kelly_by_regime

        try:
            result = run_signal_replay_comparison(asset_id, proposed_update)
            results.append(result)
        except Exception as e:
            logger.warning("Rollback comparison failed for %s: %s", asset_id, e)
            results.append({"recommendation": "REJECT", "reason": str(e)})

    rejections = [r for r in results if r.get("recommendation") == "REJECT"]
    if rejections:
        return {
            "recommendation": "REJECT",
            "reason": f"{len(rejections)}/{len(results)} assets rejected",
            "details": results,
        }
    return {
        "recommendation": "ADOPT",
        "reason": f"{len(results)}/{len(results)} assets approved",
        "details": results,
    }


def _run_regression_tests(component_id: str, expected_state: dict) -> bool:
    """Validate that restored state matches expectations and invariants hold."""
    current = get_current_state(component_id)
    current_rows = current.get("rows", [])
    expected_rows = expected_state.get("rows", [])

    # Check row count matches
    if len(current_rows) != len(expected_rows):
        logger.error("Regression FAILED for %s: row count mismatch "
                     "(expected=%d, actual=%d)",
                     component_id, len(expected_rows), len(current_rows))
        return False

    # Check domain invariants by component type
    if component_id == "P3-D02":
        for row in current_rows:
            prob = row.get("inclusion_probability", 0)
            if not (0 <= prob <= 1):
                logger.error("Regression FAILED: invalid "
                             "inclusion_probability=%.4f in %s", prob,
                             component_id)
                return False
    elif component_id == "P3-D12":
        for row in current_rows:
            kelly = row.get("kelly_full", 0)
            if kelly < 0:
                logger.error("Regression FAILED: negative kelly_full=%.4f "
                             "in %s", kelly, component_id)
                return False

    logger.info("Regression tests PASSED for %s (%d rows verified)",
                component_id, len(current_rows))
    return True


def _publish_rollback_alert(component_id: str, version_id: str,
                            admin_user_id: str, status: str, reason: str):
    """Publish rollback event to captain:alerts channel (priority HIGH)."""
    try:
        client = get_redis_client()
        client.publish(CH_ALERTS, json.dumps({
            "type": "VERSION_ROLLBACK",
            "component": component_id,
            "version_id": version_id,
            "admin_user_id": admin_user_id,
            "status": status,
            "reason": reason,
            "priority": "HIGH",
            "timestamp": now_et().isoformat(),
        }))
    except Exception as e:
        logger.error("Failed to publish rollback alert: %s", e)


def rollback_to_version(component_id: str, version_id: str,
                        admin_user_id: str) -> dict:
    """Roll back a versioned component to a previous snapshot (Doc 32 spec).

    Steps:
        1. Load target version from D18
        2. Load current live state via get_current_state
        3. Run pseudotrader comparison (current vs target)
        4. If REJECT → abort rollback, notify admin
        5. If ADOPT → snapshot current for undo, restore target, run
           regression tests, revert if tests fail
        6. Publish HIGH notification for audit trail

    Args:
        component_id: One of VERSIONED_COMPONENTS
        version_id: UUID of the target version in D18
        admin_user_id: ID of the admin initiating the rollback

    Returns:
        Dict with 'status' key: COMPLETED | REJECTED | REVERTED
    """
    if component_id not in VERSIONED_COMPONENTS:
        raise ValueError(f"Component {component_id} is not versioned")

    # Step 1: load target version from D18
    target = _get_version(version_id)
    if target is None:
        raise ValueError(f"Version {version_id} not found in D18")
    if target["component"] != component_id:
        raise ValueError(f"Version {version_id} belongs to "
                         f"{target['component']}, not {component_id}")

    # Step 2: load current live state
    current_state = get_current_state(component_id)
    target_state = target["state"]

    # Step 3: pseudotrader comparison
    comparison = _run_rollback_comparison(
        component_id, current_state, target_state)

    # Step 4: if REJECT → abort
    if comparison["recommendation"] == "REJECT":
        _publish_rollback_alert(component_id, version_id, admin_user_id,
                                status="REJECTED",
                                reason=comparison.get("reason", ""))
        logger.warning("Rollback REJECTED for %s -> %s: %s",
                       component_id, version_id, comparison.get("reason"))
        return {"status": "REJECTED", "comparison": comparison}

    # Step 5: snapshot current state for undo, then restore target
    undo_version_id = snapshot_before_update(
        component_id, "ROLLBACK", current_state)
    _restore_state(component_id, target_state)

    # Step 6: regression tests — revert if failed
    if not _run_regression_tests(component_id, target_state):
        logger.error("Regression tests FAILED after rollback %s -> %s; "
                     "reverting to undo snapshot", component_id, version_id)
        _restore_state(component_id, current_state)
        _publish_rollback_alert(component_id, version_id, admin_user_id,
                                status="REVERTED",
                                reason="Regression tests failed")
        return {"status": "REVERTED", "undo_version_id": undo_version_id}

    # Step 7: notify for audit trail
    _publish_rollback_alert(component_id, version_id, admin_user_id,
                            status="COMPLETED",
                            reason="Rollback successful")

    logger.info("Rollback COMPLETED: %s -> version %s "
                "(undo=%s, admin=%s)",
                component_id, version_id, undo_version_id, admin_user_id)

    return {
        "status": "COMPLETED",
        "undo_version_id": undo_version_id,
        "comparison": comparison,
    }
