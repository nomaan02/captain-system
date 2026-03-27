# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 9: Incident Response (P3-PG-40).

Auto-generated incident reports with severity classification (P1-P4),
resolution tracking.  Writes to P3-D21.

Notification routing:
- P1_CRITICAL → ADMIN + DEV on ALL channels (GUI, Telegram, Email)
- P2_HIGH     → ADMIN on GUI + Telegram
- P3_MEDIUM   → ADMIN on GUI only
- P4_LOW      → Logged only (visible in System Overview)

Spec: Program3_Command.md lines 721-778
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from shared.questdb_client import get_cursor
from shared.journal import write_checkpoint
from shared.constants import INCIDENT_SEVERITY_VALUES

logger = logging.getLogger(__name__)

# Incident types
INCIDENT_TYPES = {
    "CRASH", "DATA_QUALITY", "RECONCILIATION",
    "PERFORMANCE", "SECURITY", "OPERATIONAL",
}

# Severity → notification routing
SEVERITY_ROUTING = {
    "P1_CRITICAL": {"channels": ["GUI", "TELEGRAM"], "targets": ["ADMIN"]},
    "P2_HIGH":     {"channels": ["GUI", "TELEGRAM"], "targets": ["ADMIN"]},
    "P3_MEDIUM":   {"channels": ["GUI"],             "targets": ["ADMIN"]},
    "P4_LOW":      {"channels": [],                  "targets": []},
}


# ---------------------------------------------------------------------------
# Incident creation
# ---------------------------------------------------------------------------


def create_incident(incident_type: str, severity: str, component: str,
                    details: str, affected_users: list[str] | None = None,
                    system_snapshot: dict | None = None,
                    notify_fn: Callable | None = None) -> dict:
    """Create a new incident and route notifications.

    Parameters
    ----------
    incident_type : str
        One of INCIDENT_TYPES.
    severity : str
        One of INCIDENT_SEVERITY_VALUES.
    component : str
        Affected component: ONLINE, OFFLINE, COMMAND, DATA_FEED, API.
    details : str
        Human-readable description.
    affected_users : list[str] or None
        User IDs affected (None = system-wide).
    system_snapshot : dict or None
        Current system state at time of incident.
    notify_fn : callable or None
        ``notify_fn(notif_dict)`` for sending notifications.

    Returns
    -------
    dict
        The created incident record.
    """
    if severity not in INCIDENT_SEVERITY_VALUES:
        logger.warning("Invalid severity: %s, defaulting to P3_MEDIUM", severity)
        severity = "P3_MEDIUM"

    incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
    ts = datetime.now().isoformat()

    incident = {
        "incident_id": incident_id,
        "timestamp": ts,
        "type": incident_type,
        "severity": severity,
        "component": component,
        "details": details,
        "affected_users": affected_users or [],
        "system_snapshot": system_snapshot or {},
        "status": "OPEN",
        "resolution": None,
        "resolved_by": None,
        "resolved_at": None,
    }

    # Persist to P3-D21
    _store_incident(incident)

    # Route notifications based on severity
    routing = SEVERITY_ROUTING.get(severity, {})
    if routing.get("channels") and notify_fn:
        priority_map = {
            "P1_CRITICAL": "CRITICAL",
            "P2_HIGH": "HIGH",
            "P3_MEDIUM": "MEDIUM",
            "P4_LOW": "LOW",
        }
        notify_fn({
            "priority": priority_map.get(severity, "LOW"),
            "message": f"[{severity}] {incident_type} in {component}: {details}",
            "source": "INCIDENT",
            "data": {"incident_id": incident_id},
        })

    write_checkpoint("COMMAND", "INCIDENT_CREATED", "logged", "monitoring",
                     {"incident_id": incident_id, "severity": severity})

    logger.info("Incident created: %s [%s] %s — %s",
                incident_id, severity, incident_type, details[:100])

    return incident


# ---------------------------------------------------------------------------
# Incident resolution
# ---------------------------------------------------------------------------


def resolve_incident(incident_id: str, resolution: str,
                     resolved_by: str) -> dict:
    """Mark an incident as resolved.

    Parameters
    ----------
    incident_id : str
        The incident to resolve.
    resolution : str
        Description of how it was resolved.
    resolved_by : str
        User/admin who resolved it.

    Returns
    -------
    dict
        Updated incident record.
    """
    ts = datetime.now().isoformat()

    try:
        with get_cursor() as cur:
            # QuestDB is append-only — insert a resolution row
            cur.execute(
                """INSERT INTO p3_d21_incident_log(
                       timestamp, incident_id, incident_type, severity,
                       component, details, status,
                       resolution, resolved_by, resolved_at
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    ts, incident_id,
                    "",  # type carried from original
                    "",  # severity carried from original
                    "",  # component carried from original
                    "",
                    "RESOLVED",
                    resolution,
                    resolved_by,
                    ts,
                ),
            )

        logger.info("Incident %s resolved by %s: %s", incident_id, resolved_by, resolution[:100])

        return {
            "incident_id": incident_id,
            "status": "RESOLVED",
            "resolution": resolution,
            "resolved_by": resolved_by,
            "resolved_at": ts,
        }
    except Exception as exc:
        logger.error("Incident resolution failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Incident queries
# ---------------------------------------------------------------------------


def get_open_incidents() -> list[dict]:
    """Fetch all open incidents from P3-D21."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT incident_id, incident_type, severity,
                          component, details, status, timestamp
                   FROM p3_d21_incident_log
                   WHERE status = 'OPEN'
                   ORDER BY timestamp DESC"""
            )
            return [
                {
                    "incident_id": r[0], "type": r[1], "severity": r[2],
                    "component": r[3], "details": r[4], "status": r[5],
                    "timestamp": r[6],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Open incidents query failed: %s", exc, exc_info=True)
    return []


def get_incident_detail(incident_id: str) -> dict:
    """Fetch full incident detail including resolution history."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT incident_id, incident_type, severity,
                          component, details, status,
                          resolution, resolved_by, resolved_at, timestamp
                   FROM p3_d21_incident_log
                   WHERE incident_id = %s
                   ORDER BY timestamp""",
                (incident_id,),
            )
            rows = cur.fetchall()
            if not rows:
                return {"error": f"Incident {incident_id} not found"}

            # First row is creation, last may be resolution
            first = rows[0]
            last = rows[-1]

            return {
                "incident_id": first[0],
                "type": first[1],
                "severity": first[2],
                "component": first[3],
                "details": first[4],
                "status": last[5],
                "resolution": last[6],
                "resolved_by": last[7],
                "resolved_at": last[8],
                "created_at": first[9],
                "history_count": len(rows),
            }
    except Exception as exc:
        logger.error("Incident detail query failed: %s", exc, exc_info=True)
    return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store_incident(incident: dict):
    """Insert incident into P3-D21."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d21_incident_log(
                       timestamp, incident_id, incident_type, severity,
                       component, details, affected_users,
                       system_snapshot, status
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    incident["timestamp"],
                    incident["incident_id"],
                    incident["type"],
                    incident["severity"],
                    incident["component"],
                    incident["details"],
                    json.dumps(incident.get("affected_users", [])),
                    json.dumps(incident.get("system_snapshot", {})),
                    incident["status"],
                ),
            )
    except Exception as exc:
        logger.error("Incident store failed: %s", exc, exc_info=True)
