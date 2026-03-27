# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""HDWM Diversity Maintenance — P3-PG-03 (Task 2.1c / OFF lines 227-252).

Weekly check: if ALL AIMs of a seed type are SUPPRESSED, force-reactivate
the one with the highest recent_effectiveness to maintain ensemble diversity.

6 seed types covering all 16 AIMs.
"""

import logging

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# Seed type taxonomy — maps type name to list of AIM IDs
SEED_TYPES = {
    "options": [1, 2, 3],
    "microstructure": [4, 5, 15],
    "macro_event": [6, 7],
    "cross_asset": [8, 9],
    "temporal": [10, 11],
    "internal": [12, 13, 14],
    # AIM-16 (HMM) is standalone — not part of diversity groups
}


def _get_aim_status(aim_id: int, asset_id: str) -> str | None:
    """Get current status for an AIM."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT status FROM p3_d01_aim_model_states
               WHERE aim_id = %s AND asset_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (aim_id, asset_id),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _get_recent_effectiveness(aim_id: int, asset_id: str) -> float:
    """Get recent_effectiveness from P3-D02."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT recent_effectiveness FROM p3_d02_aim_meta_weights
               WHERE aim_id = %s AND asset_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (aim_id, asset_id),
        )
        row = cur.fetchone()
    return row[0] if row else 0.0


def _count_active_aims(asset_id: str) -> int:
    """Count AIMs with ACTIVE status for this asset."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT count() FROM p3_d01_aim_model_states
               WHERE asset_id = %s AND status = 'ACTIVE'""",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row else 0


def _reactivate_aim(aim_id: int, asset_id: str, num_active: int):
    """Reactivate a suppressed AIM with equal weight."""
    equal_weight = 1.0 / max(num_active + 1, 1)

    with get_cursor() as cur:
        # Update status to ACTIVE
        cur.execute(
            """INSERT INTO p3_d01_aim_model_states
               (aim_id, asset_id, status, warmup_progress, last_updated)
               VALUES (%s, %s, 'ACTIVE', 1.0, now())""",
            (aim_id, asset_id),
        )
        # Set equal weight
        cur.execute(
            """INSERT INTO p3_d02_aim_meta_weights
               (aim_id, asset_id, inclusion_probability, inclusion_flag,
                recent_effectiveness, days_below_threshold, last_updated)
               VALUES (%s, %s, %s, true, 0.0, 0, now())""",
            (aim_id, asset_id, equal_weight),
        )


def run_hdwm_diversity_check(asset_id: str):
    """Execute P3-PG-03: weekly diversity maintenance.

    For each seed type, check if all AIMs are suppressed.
    If so, reactivate the one with highest recent_effectiveness.
    """
    num_active = _count_active_aims(asset_id)
    reactivated = 0

    for type_name, aim_ids in SEED_TYPES.items():
        active_in_type = []
        suppressed_in_type = []

        for aid in aim_ids:
            status = _get_aim_status(aid, asset_id)
            if status == "ACTIVE":
                active_in_type.append(aid)
            elif status == "SUPPRESSED":
                suppressed_in_type.append(aid)

        if len(active_in_type) == 0 and len(suppressed_in_type) > 0:
            # All AIMs of this type are suppressed — force reactivate best one
            best_aid = max(
                suppressed_in_type,
                key=lambda aid: _get_recent_effectiveness(aid, asset_id),
            )
            _reactivate_aim(best_aid, asset_id, num_active)
            num_active += 1
            reactivated += 1
            logger.warning(
                "HDWM diversity recovery: reactivated AIM-%d as seed for '%s' [%s]",
                best_aid, type_name, asset_id,
            )

    if reactivated > 0:
        logger.info("HDWM check for %s: %d AIMs reactivated", asset_id, reactivated)
    else:
        logger.debug("HDWM check for %s: diversity OK", asset_id)
