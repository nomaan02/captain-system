# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""AIM Lifecycle Manager — P3-PG-01 (Task 2.1a / OFF lines 50-99).

State machine for each AIM (1-15 + AIM-16 HMM):
    INSTALLED -> COLLECTING -> WARM_UP -> ELIGIBLE -> ACTIVE
    BOOTSTRAPPED -> ACTIVE (shortcut via asset_bootstrap)
    ACTIVE <-> SUPPRESSED (auto-recovery)

Writes: P3-D01 (status updates), P3-D00 (aim_warmup_progress)
Reads: P3-D01 (current states), P3-D02 (meta-weights)
Trigger: Every update cycle (after trade outcomes)
"""

import json
import logging
from datetime import datetime

from shared.questdb_client import get_cursor
from shared.constants import AIM_STATUS_VALUES

from captain_offline.blocks.version_snapshot import snapshot_before_update

logger = logging.getLogger(__name__)

# Number of AIMs (15 original + AIM-16 HMM)
NUM_AIMS = 16

# Suppression: meta_weight == 0 for this many consecutive trades
SUPPRESSION_CONSECUTIVE_ZERO = 20

# Recovery: meta_weight > this for RECOVERY_CONSECUTIVE trades
RECOVERY_WEIGHT_THRESHOLD = 0.1
RECOVERY_CONSECUTIVE = 10


def _load_aim_states(asset_id: str) -> list[dict]:
    """Load latest AIM states for an asset from P3-D01."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id, asset_id, status, model_object, warmup_progress,
                      current_modifier, last_retrained, missing_data_rate_30d
               FROM p3_d01_aim_model_states
               WHERE asset_id = %s
               ORDER BY aim_id, last_updated DESC""",
            (asset_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "aim_id": r[0],
            "asset_id": r[1],
            "status": r[2],
            "model_object": r[3],
            "warmup_progress": r[4],
            "current_modifier": json.loads(r[5]) if r[5] else {},
            "last_retrained": r[6],
            "missing_data_rate_30d": r[7],
        }
        for r in rows
    ]


def _load_meta_weight(aim_id: int, asset_id: str) -> float:
    """Load inclusion_probability for an AIM from P3-D02."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT inclusion_probability FROM p3_d02_aim_meta_weights
               WHERE aim_id = %s AND asset_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (aim_id, asset_id),
        )
        row = cur.fetchone()
    return row[0] if row else 0.0


def _update_aim_status(aim_id: int, asset_id: str, new_status: str):
    """Update an AIM's status in P3-D01."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d01_aim_model_states
               (aim_id, asset_id, status, warmup_progress, last_updated)
               VALUES (%s, %s, %s, %s, now())""",
            (aim_id, asset_id, new_status, 1.0 if new_status == "ACTIVE" else 0.0),
        )


def _update_warmup_progress(aim_id: int, asset_id: str, progress: float):
    """Update warmup progress for an AIM in both P3-D01 and P3-D00."""
    clamped = min(progress, 1.0)
    with get_cursor() as cur:
        # P3-D01: AIM-level warmup progress
        cur.execute(
            """INSERT INTO p3_d01_aim_model_states
               (aim_id, asset_id, status, warmup_progress, last_updated)
               VALUES (%s, %s, %s, %s, now())""",
            (aim_id, asset_id, "WARM_UP", clamped),
        )
        # P3-D00: asset-level aim_warmup_progress (per spec requirement)
        from shared.questdb_client import read_d00_row, update_d00_fields
        current = read_d00_row(asset_id, cur=cur)
        existing = json.loads(current["aim_warmup_progress"]) if current and current.get("aim_warmup_progress") else {}
        existing[str(aim_id)] = clamped
        update_d00_fields(asset_id, {"aim_warmup_progress": json.dumps(existing)}, cur=cur)


def data_pipeline_connected(aim_id: int, asset_id: str) -> bool:
    """Check if data sources for this AIM are available.

    In V1, this checks P3-D00.data_sources for the required feeds.
    Simplified: returns True if asset is in universe.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT count() FROM p3_d00_asset_universe WHERE asset_id = %s",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] > 0 if row else False


def observations_collected(aim_id: int, asset_id: str) -> int:
    """Count observations collected for this AIM since COLLECTING started."""
    # In practice, this depends on the AIM type.
    # For now, count trade outcomes for this asset as a proxy.
    with get_cursor() as cur:
        cur.execute(
            "SELECT count() FROM p3_d03_trade_outcome_log WHERE asset = %s",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row else 0


def warmup_required(aim_id: int) -> int:
    """Minimum observations required for warmup completion."""
    # AIM-specific thresholds. Default: 50 trades (from Arch §9).
    thresholds = {
        5: 100,   # AIM-05 (DEFERRED — higher threshold)
        16: 240,  # AIM-16 HMM needs 60 days * 4 sessions
    }
    return thresholds.get(aim_id, 50)


def run_aim_lifecycle(asset_id: str, user_activated_aims: set[int] | None = None):
    """Execute P3-PG-01 for all AIMs on a given asset.

    Args:
        asset_id: Asset to process
        user_activated_aims: Set of AIM IDs the user has activated via GUI.
                            None means no new activations this cycle.
    """
    if user_activated_aims is None:
        user_activated_aims = set()

    aim_states = _load_aim_states(asset_id)

    # Build lookup by aim_id (use latest state per AIM)
    latest_by_aim = {}
    for s in aim_states:
        aid = s["aim_id"]
        if aid not in latest_by_aim:
            latest_by_aim[aid] = s

    for aim_id in range(1, NUM_AIMS + 1):
        state = latest_by_aim.get(aim_id)
        if state is None:
            # AIM not yet registered — skip (will be initialized by bootstrap or setup)
            continue

        current_status = state["status"]

        if current_status == "INSTALLED":
            if data_pipeline_connected(aim_id, asset_id):
                _update_aim_status(aim_id, asset_id, "COLLECTING")
                logger.info("AIM-%d [%s]: INSTALLED -> COLLECTING", aim_id, asset_id)

        elif current_status == "COLLECTING":
            obs = observations_collected(aim_id, asset_id)
            if obs > 0:
                _update_aim_status(aim_id, asset_id, "WARM_UP")
                logger.info("AIM-%d [%s]: COLLECTING -> WARM_UP (obs=%d)", aim_id, asset_id, obs)

        elif current_status == "WARM_UP":
            obs = observations_collected(aim_id, asset_id)
            required = warmup_required(aim_id)
            progress = obs / required if required > 0 else 0.0
            _update_warmup_progress(aim_id, asset_id, progress)

            if progress >= 1.0:
                _update_aim_status(aim_id, asset_id, "ELIGIBLE")
                logger.info("AIM-%d [%s]: WARM_UP -> ELIGIBLE (warmup complete)", aim_id, asset_id)

        elif current_status == "ELIGIBLE":
            # Outputs neutral modifier (1.0) until user activates via GUI
            if aim_id in user_activated_aims:
                snapshot_before_update("P3-D01", "AIM_RETRAIN", state)
                _update_aim_status(aim_id, asset_id, "ACTIVE")
                logger.info("AIM-%d [%s]: ELIGIBLE -> ACTIVE (user activated)", aim_id, asset_id)

        elif current_status == "BOOTSTRAPPED":
            # Same gate as ELIGIBLE — user must activate
            if aim_id in user_activated_aims:
                snapshot_before_update("P3-D01", "AIM_RETRAIN", state)
                _update_aim_status(aim_id, asset_id, "ACTIVE")
                logger.info("AIM-%d [%s]: BOOTSTRAPPED -> ACTIVE (user activated)", aim_id, asset_id)

        elif current_status == "ACTIVE":
            # Check for suppression: meta_weight == 0 for 20+ consecutive trades
            weight = _load_meta_weight(aim_id, asset_id)
            if weight == 0:
                # Track consecutive zero weight (simplified — in production,
                # maintain a counter in P3-D02.days_below_threshold)
                meta = _load_meta_weight_history(aim_id, asset_id)
                if meta.get("consecutive_zero", 0) >= SUPPRESSION_CONSECUTIVE_ZERO:
                    _update_aim_status(aim_id, asset_id, "SUPPRESSED")
                    logger.warning("AIM-%d [%s]: ACTIVE -> SUPPRESSED (zero weight %d trades)",
                                   aim_id, asset_id, SUPPRESSION_CONSECUTIVE_ZERO)

        elif current_status == "SUPPRESSED":
            # Auto-recovery: meta_weight > 0.1 for 10+ consecutive trades
            weight = _load_meta_weight(aim_id, asset_id)
            if weight > RECOVERY_WEIGHT_THRESHOLD:
                meta = _load_meta_weight_history(aim_id, asset_id)
                if meta.get("consecutive_above", 0) >= RECOVERY_CONSECUTIVE:
                    _update_aim_status(aim_id, asset_id, "ACTIVE")
                    logger.info("AIM-%d [%s]: SUPPRESSED -> ACTIVE (auto-recovery)", aim_id, asset_id)


# AIM tier definitions for scheduled retraining
TIER_1_AIMS = [4, 6, 8, 11, 12, 15]   # Weekly retrain
TIER_2_AIMS = [1, 2, 3, 7, 9, 10]     # Monthly retrain
TIER_3_AIMS = [13, 14]                  # Monthly retrain
TIER_23_AIMS = TIER_2_AIMS + TIER_3_AIMS


def run_tier_retrain(asset_id: str, aim_ids: list[int]):
    """Trigger scheduled retraining for a set of AIMs on an asset.

    For each specified AIM that is ACTIVE, updates the last_retrained
    timestamp and runs the lifecycle check. When individual AIM model
    trainers are implemented, they plug in here.

    Args:
        asset_id: Asset to retrain AIMs for
        aim_ids: List of AIM IDs to retrain (e.g., TIER_1_AIMS)
    """
    retrained = 0

    for aim_id in aim_ids:
        with get_cursor() as cur:
            cur.execute(
                """SELECT status FROM p3_d01_aim_model_states
                   WHERE aim_id = %s AND asset_id = %s
                   ORDER BY last_updated DESC LIMIT 1""",
                (aim_id, asset_id),
            )
            row = cur.fetchone()

        if not row:
            continue

        status = row[0]

        # Only retrain ACTIVE or BOOTSTRAPPED AIMs
        if status not in ("ACTIVE", "BOOTSTRAPPED"):
            continue

        # Snapshot before retrain
        snapshot_before_update("P3-D01", "AIM_RETRAIN",
                               {"aim_id": aim_id, "asset_id": asset_id, "status": status})

        # Update last_retrained timestamp
        # When individual AIM trainers exist, actual model retraining happens here:
        #   trained_model = aim_trainer_registry[aim_id].retrain(asset_id)
        #   _save_model_object(aim_id, asset_id, trained_model)
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d01_aim_model_states
                   (aim_id, asset_id, status, warmup_progress, last_retrained, last_updated)
                   VALUES (%s, %s, %s, 1.0, now(), now())""",
                (aim_id, asset_id, status),
            )

        retrained += 1

    if retrained > 0:
        logger.info("Tier retrain for %s: %d/%d AIMs retrained (IDs: %s)",
                     asset_id, retrained, len(aim_ids), aim_ids)

    # Run lifecycle check after retraining to process any state transitions
    run_aim_lifecycle(asset_id)

    return retrained


def _load_meta_weight_history(aim_id: int, asset_id: str) -> dict:
    """Load recent meta-weight history for suppression/recovery tracking.

    Returns dict with consecutive_zero and consecutive_above counts.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT days_below_threshold FROM p3_d02_aim_meta_weights
               WHERE aim_id = %s AND asset_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (aim_id, asset_id),
        )
        row = cur.fetchone()
    days_below = row[0] if row else 0
    return {
        "consecutive_zero": days_below,
        "consecutive_above": 0 if days_below > 0 else 10,  # simplified
    }
