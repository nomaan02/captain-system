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
import os
import secrets
import uuid
import hashlib
import logging
import warnings
from datetime import datetime

from shared.questdb_client import get_cursor, qexecute
from shared.redis_client import get_redis_client, CH_ALERTS
from shared.constants import now_et

logger = logging.getLogger(__name__)

MAX_VERSIONS_PER_COMPONENT = 50
COLD_STORAGE_AGE_DAYS = 90

# Pending rollback proposals (F-08 / Q-08): two-phase request → admin approval → commit.
# Redis STRING value = JSON blob; survives offline restarts until TTL.
ROLLBACK_PROPOSAL_KEY_PREFIX = "captain:rollback_proposal:"
_PROPOSAL_TTL_SEC = int(os.environ.get("CAPTAIN_ROLLBACK_PROPOSAL_TTL_SEC", "604800"))

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
    "AIM_LIFECYCLE",  # lifecycle state transitions (WARM_UP, ELIGIBLE, ACTIVE, etc.)
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
    """Log when snapshots exceed MAX_VERSIONS_PER_COMPONENT.

    QuestDB is append-only (no DELETE support), so this function only
    monitors overflow for observability.  The version history table grows
    slowly (~few rows/day across 5 components) and unbounded retention is
    acceptable.
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

    oldest_excess_ts = versions[-1][1]
    logger.info("Version overflow for %s: %d versions (MAX=%d) "
                "— oldest retained: %s (append-only, no pruning)",
                component_id, len(versions), MAX_VERSIONS_PER_COMPONENT,
                oldest_excess_ts)


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
        qexecute(
            cur,
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
                            admin_user_id: str, status: str, reason: str,
                            rollback_request_id: str | None = None,
                            message_type: str = "VERSION_ROLLBACK"):
    """Publish rollback event to captain:alerts channel (priority HIGH)."""
    try:
        client = get_redis_client()
        payload: dict = {
            "type": message_type,
            "component": component_id,
            "version_id": version_id,
            "admin_user_id": admin_user_id,
            "status": status,
            "reason": reason,
            "priority": "HIGH",
            "timestamp": now_et().isoformat(),
        }
        if rollback_request_id:
            payload["rollback_request_id"] = rollback_request_id
        client.publish(CH_ALERTS, json.dumps(payload))
    except Exception as e:
        logger.error("Failed to publish rollback alert: %s", e)


def _proposal_redis_key(rollback_request_id: str) -> str:
    return f"{ROLLBACK_PROPOSAL_KEY_PREFIX}{rollback_request_id}"


def _save_rollback_proposal(data: dict) -> None:
    """Persist pending proposal JSON in Redis with TTL."""
    rid = data["rollback_request_id"]
    key = _proposal_redis_key(rid)
    client = get_redis_client()
    client.set(key, json.dumps(data, default=str), ex=_PROPOSAL_TTL_SEC)


def _load_rollback_proposal(rollback_request_id: str) -> dict | None:
    key = _proposal_redis_key(rollback_request_id)
    try:
        client = get_redis_client()
        raw = client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)
    except Exception as e:
        logger.warning("Failed to load rollback proposal %s: %s",
                       rollback_request_id, e)
        return None


def _update_rollback_proposal(rollback_request_id: str, data: dict) -> None:
    key = _proposal_redis_key(rollback_request_id)
    client = get_redis_client()
    client.set(key, json.dumps(data, default=str), ex=_PROPOSAL_TTL_SEC)


def request_rollback(
    component_id: str,
    version_id: str,
    requester_admin_user_id: str,
) -> dict:
    """Phase 1 of two-phase rollback (doc 32: NOTIFY only — no live restore).

    Runs comparison; on ADOPT persists a pending proposal in Redis and alerts.
    Does **not** call snapshot_before_update(ROLLBACK) or _restore_state.

    Returns:
        On REJECT: ``{"status": "REJECTED", "comparison": ...}``
        On ADOPT: ``{"status": "PENDING_APPROVAL", "rollback_request_id",
            "approval_token": <secret>, "comparison": ...}``
    """
    if component_id not in VERSIONED_COMPONENTS:
        raise ValueError(f"Component {component_id} is not versioned")

    target = _get_version(version_id)
    if target is None:
        raise ValueError(f"Version {version_id} not found in D18")
    if target["component"] != component_id:
        raise ValueError(
            f"Version {version_id} belongs to {target['component']}, "
            f"not {component_id}"
        )

    current_state = get_current_state(component_id)
    target_state = target["state"]
    comparison = _run_rollback_comparison(
        component_id, current_state, target_state)

    if comparison["recommendation"] == "REJECT":
        _publish_rollback_alert(
            component_id, version_id, requester_admin_user_id,
            status="REJECTED", reason=comparison.get("reason", ""))
        logger.warning(
            "Rollback REJECTED at request stage for %s -> %s: %s",
            component_id, version_id, comparison.get("reason"),
        )
        return {"status": "REJECTED", "comparison": comparison}

    rollback_request_id = str(uuid.uuid4())
    # Opaque proof for commit_rollback; treat like a capability URL (Q-08).
    approval_token = secrets.token_urlsafe(32)

    proposal = {
        "status": "PENDING",
        "rollback_request_id": rollback_request_id,
        "component_id": component_id,
        "version_id": version_id,
        "requester_admin_user_id": requester_admin_user_id,
        "comparison": comparison,
        "approval_token": approval_token,
        "created_iso": now_et().isoformat(),
        "proposal_version": 1,
    }
    _save_rollback_proposal(proposal)

    _publish_rollback_alert(
        component_id, version_id, requester_admin_user_id,
        status="PENDING_APPROVAL",
        reason="Rollback comparison ready — awaiting commit_rollback",
        rollback_request_id=rollback_request_id,
        message_type="VERSION_ROLLBACK_PROPOSAL",
    )

    return {
        "status": "PENDING_APPROVAL",
        "rollback_request_id": rollback_request_id,
        "approval_token": approval_token,
        "comparison": comparison,
    }


def commit_rollback(
    rollback_request_id: str,
    approving_admin_user_id: str,
    approval_proof: str,
) -> dict:
    """Phase 2: ON admin_approval — apply undo snapshot, restore, regression.

    ``approval_proof`` must match the ``approval_token`` issued by
    ``request_rollback`` for this ``rollback_request_id``.

    Successful completion sets proposal status COMPLETED in Redis; a second call
    with the same id returns ALREADY_COMPLETED without mutating QuestDB again.
    """
    blob = _load_rollback_proposal(rollback_request_id)
    if blob is None:
        return {
            "status": "ERROR",
            "reason": "NOT_FOUND_OR_EXPIRED",
        }

    if blob.get("status") == "COMPLETED":
        logger.info(
            "commit_rollback idempotent hit for completed %s",
            rollback_request_id,
        )
        return {
            "status": "ALREADY_COMPLETED",
            "rollback_request_id": rollback_request_id,
            "undo_version_id": blob.get("completed_undo_version_id"),
        }

    if blob.get("status") != "PENDING":
        return {
            "status": "ERROR",
            "reason": f"INVALID_PROPOSAL_STATE:{blob.get('status')}",
        }

    if not approval_proof or approval_proof != blob.get("approval_token"):
        logger.warning(
            "commit_rollback: invalid approval proof for %s",
            rollback_request_id,
        )
        return {
            "status": "REJECTED",
            "reason": "INVALID_APPROVAL_PROOF",
        }

    component_id = blob["component_id"]
    version_id = blob["version_id"]

    target = _get_version(version_id)
    if target is None:
        return {
            "status": "ERROR",
            "reason": "VERSION_NO_LONGER_IN_D18",
        }
    target_state = target["state"]

    current_state = get_current_state(component_id)
    comparison = blob.get("comparison") or {}

    undo_version_id = snapshot_before_update(
        component_id, "ROLLBACK", current_state)
    _restore_state(component_id, target_state)

    if not _run_regression_tests(component_id, target_state):
        logger.error(
            "Regression tests FAILED after commit rollback %s -> %s; reverting",
            component_id,
            version_id,
        )
        _restore_state(component_id, current_state)
        _publish_rollback_alert(
            component_id, version_id, approving_admin_user_id,
            status="REVERTED", reason="Regression tests failed",
            rollback_request_id=rollback_request_id,
        )
        blob["status"] = "FAILED_REGRESSION"
        blob["completed_undo_version_id"] = undo_version_id
        _update_rollback_proposal(rollback_request_id, blob)
        return {
            "status": "REVERTED",
            "undo_version_id": undo_version_id,
            "comparison": comparison,
        }

    _publish_rollback_alert(
        component_id, version_id, approving_admin_user_id,
        status="COMPLETED", reason="Rollback successful",
        rollback_request_id=rollback_request_id,
    )

    logger.info(
        "Rollback COMMITTED: %s -> version %s (undo=%s, approved_by=%s)",
        component_id,
        version_id,
        undo_version_id,
        approving_admin_user_id,
    )

    blob["status"] = "COMPLETED"
    blob["completed_undo_version_id"] = undo_version_id
    blob["approved_by"] = approving_admin_user_id
    blob["completed_iso"] = now_et().isoformat()
    _update_rollback_proposal(rollback_request_id, blob)

    return {
        "status": "COMPLETED",
        "undo_version_id": undo_version_id,
        "comparison": comparison,
    }


def rollback_to_version(component_id: str, version_id: str,
                        admin_user_id: str) -> dict:
    """Deprecated: single-phase rollback violated doc 32 admin gate (F-08).

    Use ``request_rollback`` then ``commit_rollback`` with the issued token.
    """
    warnings.warn(
        "rollback_to_version is removed: use request_rollback then "
        "commit_rollback after admin approval (F-08 / doc 32 Version Snapshot "
        "Policy).",
        DeprecationWarning,
        stacklevel=2,
    )
    raise NotImplementedError(
        "Single-phase rollback is disabled. Call request_rollback(), then "
        "commit_rollback(rollback_request_id, approving_admin_user_id, "
        "approval_token)."
    )

