# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Decay Level Escalation — P3-PG-08 (Task 2.2d / OFF lines 318-358).

Level 2: cp_prob > 0.8 -> autonomous sizing reduction
  reduction_factor = max(0.5, 1.0 - (severity - 0.8) * 2.5)
  Written to P3-D12.sizing_override

Level 3: cp_prob > 0.9 for 5+ consecutive trades -> halt + P1/P2 rerun + AIM-14
  captain_status = DECAYED
  Schedule reruns

Both levels log to P3-D04.decay_events and trigger notifications.

Reads: P3-D04 (cp_probability, cp_history)
Writes: P3-D00 (captain_status), P3-D04 (decay_events), P3-D12 (sizing_override)
"""

import json
import logging
from datetime import datetime

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS

logger = logging.getLogger(__name__)

# Thresholds
LEVEL2_THRESHOLD = 0.8
LEVEL3_THRESHOLD = 0.9
LEVEL3_SUSTAINED_WINDOW = 5

# Sizing reduction formula: factor = max(0.5, 1.0 - (severity - 0.8) * 2.5)
REDUCTION_SLOPE = 2.5
REDUCTION_FLOOR = 0.5


def _compute_reduction_factor(severity: float) -> float:
    """Level 2 sizing reduction formula.

    severity=0.80 -> 1.0 (no reduction)
    severity=0.85 -> 0.875
    severity=0.90 -> 0.75
    severity=1.00 -> 0.5 (floor)
    """
    factor = 1.0 - (severity - LEVEL2_THRESHOLD) * REDUCTION_SLOPE
    return max(REDUCTION_FLOOR, min(1.0, factor))


def _log_decay_event(asset_id: str, level: int, severity: float, source: str):
    """Append decay event to P3-D04.decay_events."""
    event = json.dumps({
        "timestamp": datetime.now().isoformat(),
        "asset": asset_id,
        "level": level,
        "severity": severity,
        "source": source,
    })
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, decay_events, last_updated)
               VALUES (%s, %s, now())""",
            (asset_id, event),
        )


def _set_sizing_override(asset_id: str, reduction_factor: float):
    """Write sizing override to P3-D12."""
    override = json.dumps({asset_id: reduction_factor})
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d12_kelly_parameters
               (asset_id, regime, session, kelly_full, shrinkage_factor,
                sizing_override, last_updated)
               VALUES (%s, 'ALL', 0, 0.0, %s, %s, now())""",
            (asset_id, None, override),
        )


def _set_captain_status_decayed(asset_id: str):
    """Set captain_status = DECAYED in P3-D00."""
    from shared.questdb_client import update_d00_fields
    update_d00_fields(asset_id, {"captain_status": "DECAYED"})


def _publish_alert(asset_id: str, level: int, severity: float, source: str):
    """Publish decay alert to Redis captain:alerts channel."""
    try:
        client = get_redis_client()
        alert = json.dumps({
            "type": "DECAY_ALERT",
            "asset": asset_id,
            "level": level,
            "severity": severity,
            "source": source,
            "priority": "CRITICAL" if level >= 3 else "HIGH",
            "timestamp": datetime.now().isoformat(),
        })
        client.publish(CH_ALERTS, alert)
    except Exception as e:
        logger.error("Failed to publish decay alert: %s", e)


def trigger_level2(asset_id: str, severity: float, source: str):
    """Level 2: Autonomous sizing reduction.

    Args:
        asset_id: Affected asset
        severity: BOCPD cp_probability (0.8-1.0)
        source: "BOCPD" or "CUSUM"
    """
    factor = _compute_reduction_factor(severity)
    _set_sizing_override(asset_id, factor)
    _log_decay_event(asset_id, 2, severity, source)
    _publish_alert(asset_id, 2, severity, source)

    logger.warning("LEVEL 2 [%s]: sizing reduced to %.0f%% (severity=%.3f, source=%s)",
                   asset_id, factor * 100, severity, source)


def _enqueue_job(job_type: str, asset_id: str, priority: str = "CRITICAL",
                  params: dict | None = None):
    """Enqueue a job in the offline job queue (p3_offline_job_queue).

    Jobs are picked up by the orchestrator's job dispatcher on the next
    daily/event cycle.
    """
    import uuid
    job_id = f"JOB-{job_type[:3]}-{asset_id}-{uuid.uuid4().hex[:8]}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_offline_job_queue
               (job_id, job_type, asset_id, priority, status, params,
                created_at, last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, now(), now())""",
            (job_id, job_type, asset_id, priority, "PENDING",
             json.dumps(params or {})),
        )
    logger.info("Job enqueued: %s [%s] for %s (priority=%s)",
                 job_id, job_type, asset_id, priority)
    return job_id


def trigger_level3(asset_id: str, source: str):
    """Level 3: Halt signals + schedule P1/P2 rerun + AIM-14.

    Args:
        asset_id: Affected asset
        source: "BOCPD_sustained" or "CUSUM_sustained"
    """
    _set_captain_status_decayed(asset_id)
    _log_decay_event(asset_id, 3, 1.0, source)
    _publish_alert(asset_id, 3, 1.0, source)

    # Enqueue P1/P2 rerun job
    _enqueue_job("P1P2_RERUN", asset_id, "CRITICAL",
                  {"source": source, "trigger": "LEVEL3_DECAY"})

    # Enqueue AIM-14 auto-expansion search
    _enqueue_job("AIM14_EXPANSION", asset_id, "CRITICAL",
                  {"source": source, "trigger": "LEVEL3_DECAY"})

    logger.critical("LEVEL 3 [%s]: STRATEGY REVIEW — signals halted, "
                    "P1/P2 rerun + AIM-14 search enqueued (source=%s)",
                    asset_id, source)


def check_level_escalation(asset_id: str, cp_probability: float,
                            cp_history: list[float], cusum_signal: str):
    """Check if Level 2 or Level 3 should be triggered.

    Called after each BOCPD + CUSUM update.

    Args:
        asset_id: Asset being monitored
        cp_probability: Latest BOCPD changepoint probability
        cp_history: Recent cp_probability values
        cusum_signal: "BREACH" or "OK" from CUSUM update
    """
    # Level 2: BOCPD cp_prob > 0.8
    if cp_probability > LEVEL2_THRESHOLD:
        trigger_level2(asset_id, cp_probability, "BOCPD")

    # Level 2: CUSUM breach
    if cusum_signal == "BREACH":
        trigger_level2(asset_id, 0.85, "CUSUM")

    # Level 3: BOCPD sustained > 0.9 for 5+ consecutive
    if len(cp_history) >= LEVEL3_SUSTAINED_WINDOW:
        recent = cp_history[-LEVEL3_SUSTAINED_WINDOW:]
        if all(p > LEVEL3_THRESHOLD for p in recent):
            trigger_level3(asset_id, "BOCPD_sustained")
