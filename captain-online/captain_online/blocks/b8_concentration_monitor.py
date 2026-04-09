# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B8: Network Concentration Monitor — P3-PG-28 (Task 3.9 / ON lines 1434-1533).

Runs ONCE per session AFTER all per-user deployment loops.
Aggregates exposure across all users to detect network-level concentration.
Does NOT modify signals — monitoring and alerting only.
Skips in V1 (single user).

Reads: signal_queue (all signals this session), P3-D07, P3-D17
Writes: P3-D17 (concentration_history, capacity_recommendations)
"""

import json
import logging
from datetime import datetime

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS

logger = logging.getLogger(__name__)

DEFAULT_CONCENTRATION_THRESHOLD = 0.8


def run_concentration_monitor(
    session_id: int,
    active_users: list[dict],
    all_signals: list[dict],
) -> dict:
    """P3-PG-28: Network concentration monitor.

    Skips if only 1 user (V1).
    """
    if len(active_users) <= 1:
        logger.info("ON-B8: Single user — skipping concentration monitor")
        return {"skipped": True}

    concentration_threshold = _load_param("concentration_threshold", DEFAULT_CONCENTRATION_THRESHOLD)

    # Step 1: Aggregate exposure
    network_exposure = {}
    for signal in all_signals:
        asset = signal.get("asset")
        direction = signal.get("direction", 0)
        user_id = signal.get("user_id")
        per_account = signal.get("per_account", {})

        total_contracts = sum(
            pa.get("contracts", 0) for pa in per_account.values()
        )
        trade_accounts = sum(
            1 for pa in per_account.values() if pa.get("recommendation") == "TRADE"
        )

        key = (asset, direction)
        if key not in network_exposure:
            network_exposure[key] = {"users": [], "total_contracts": 0, "account_count": 0}

        network_exposure[key]["users"].append(user_id)
        network_exposure[key]["total_contracts"] += total_contracts
        network_exposure[key]["account_count"] += trade_accounts

    # Step 2: Check thresholds
    alerts = []
    for (asset, direction), exposure in network_exposure.items():
        user_concentration = len(exposure["users"]) / len(active_users)

        if user_concentration >= concentration_threshold:
            alert = {
                "session": session_id,
                "timestamp": datetime.now().isoformat(),
                "asset": asset,
                "direction": direction,
                "user_count": len(exposure["users"]),
                "total_users": len(active_users),
                "concentration_pct": user_concentration,
                "total_contracts": exposure["total_contracts"],
                "account_count": exposure["account_count"],
                "admin_response": "PENDING",
            }
            alerts.append(alert)

            # Notify ADMINs
            _notify_admins(
                f"Network concentration: {asset} dir={direction} across "
                f"{len(exposure['users'])}/{len(active_users)} users, "
                f"{exposure['total_contracts']} contracts. Acknowledge or Pause."
            )

            # Log
            _log_concentration_event(alert)

    # Step 3: Proactive tracking
    recent_count = _get_recent_alert_count(days=30)
    if recent_count > 10:
        _log_capacity_recommendation(
            "CONCENTRATION_FREQUENCY",
            f"Concentration alerts fired {recent_count} times in 30 days. "
            f"Universe may be too narrow.",
            "HIGH",
        )

    logger.info("ON-B8: Concentration monitor: %d alerts fired", len(alerts))
    return {"alerts": alerts, "skipped": False}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notify_admins(message: str):
    try:
        client = get_redis_client()
        payload = json.dumps({
            "priority": "CRITICAL",
            "message": message,
            "source": "ONLINE_B8",
            "action_required": True,
            "timestamp": datetime.now().isoformat(),
        })
        client.publish(CH_ALERTS, payload)
    except Exception as e:
        logger.error("ON-B8: Failed to notify admins: %s", e)


def _log_concentration_event(event: dict):
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d17_system_monitor_state
               (param_key, param_value, category, last_updated)
               VALUES (%s, %s, %s, now())""",
            (f"concentration_{event['session']}_{event['asset']}",
             json.dumps(event, default=str), "concentration"),
        )


def _get_recent_alert_count(days: int = 30) -> int:
    """Count recent concentration alerts (approximate via P3-D17)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT count() FROM p3_d17_system_monitor_state
               WHERE category = 'concentration'
               AND last_updated > dateadd('d', -%s, now())""",
            (days,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else 0


def _log_capacity_recommendation(rec_type: str, message: str, severity: str):
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d17_system_monitor_state
               (param_key, param_value, category, last_updated)
               VALUES (%s, %s, %s, now())""",
            (f"capacity_rec_{rec_type}",
             json.dumps({"type": rec_type, "message": message, "severity": severity}),
             "capacity_recommendation"),
        )


def _load_param(key: str, default):
    with get_cursor() as cur:
        cur.execute(
            """SELECT param_value FROM p3_d17_system_monitor_state
               LATEST ON last_updated PARTITION BY param_key
               WHERE param_key = %s""",
            (key,),
        )
        row = cur.fetchone()
    if row and row[0]:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            return default
    return default
