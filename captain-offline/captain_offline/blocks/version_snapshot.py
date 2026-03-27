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
from datetime import datetime

from shared.questdb_client import get_cursor

MAX_VERSIONS_PER_COMPONENT = 50

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


def _compute_hash(state: dict) -> str:
    """Compute SHA-256 hash of a state dict for integrity verification."""
    raw = json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def snapshot_before_update(component_id: str, trigger_reason: str, state: dict) -> str:
    """Save a timestamped snapshot of component state BEFORE modifying it.

    Args:
        component_id: One of VERSIONED_COMPONENTS (e.g., "P3-D01")
        trigger_reason: One of TRIGGERS (e.g., "DMA_UPDATE")
        state: Deep copy of the current component state

    Returns:
        version_id (UUID string)
    """
    if component_id not in VERSIONED_COMPONENTS:
        raise ValueError(f"Component {component_id} is not versioned. Valid: {VERSIONED_COMPONENTS}")
    if trigger_reason not in TRIGGERS:
        raise ValueError(f"Invalid trigger: {trigger_reason}. Valid: {TRIGGERS}")

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
