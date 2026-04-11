# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 5: Strategy Injection Flow (P3-PG-35).

Routes strategy injection workflow between GUI and Offline B4.
When P1/P2 completes a new run, Offline B4 produces a comparison report.
Command displays it in the Strategy Comparison Panel, collects the user
decision (ADOPT / PARALLEL_TRACK / REJECT), and forwards it to Offline.

Spec: Program3_Command.md lines 520-555
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Callable

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_COMMANDS
from shared.journal import write_checkpoint
from shared.constants import now_et

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection notification
# ---------------------------------------------------------------------------


def notify_new_candidate(asset: str, candidate_id: str,
                         gui_push_fn: Callable, user_id: str):
    """Notify the user that a new strategy candidate is available.

    Triggered when Offline B4 completes an injection comparison.

    Parameters
    ----------
    asset : str
        The asset for which the candidate was generated.
    candidate_id : str
        Identifier for the injection candidate (from P3-D06).
    gui_push_fn : callable
        ``gui_push_fn(user_id, message_dict)``
    user_id : str
        Target user for the notification.
    """
    gui_push_fn(user_id, {
        "type": "notification",
        "notif_id": f"INJ-{uuid.uuid4().hex[:12].upper()}",
        "priority": "HIGH",
        "message": f"New strategy candidate available for {asset}",
        "source": "INJECTION",
        "timestamp": now_et().isoformat(),
        "data": {
            "candidate_id": candidate_id,
            "asset": asset,
        },
    })

    logger.info("Injection notification sent: asset=%s candidate=%s user=%s",
                asset, candidate_id, user_id)


# ---------------------------------------------------------------------------
# Comparison panel data
# ---------------------------------------------------------------------------


def get_injection_comparison(candidate_id: str) -> dict:
    """Fetch injection comparison data for display in Strategy Comparison Panel.

    Reads from P3-D06 (injection_candidates) and P3-D11 (pseudotrader_results).

    Returns
    -------
    dict
        Side-by-side comparison of current vs. proposed strategy.
    """
    try:
        with get_cursor() as cur:
            # Candidate details
            cur.execute(
                """SELECT candidate_id, asset, recommendation,
                          sharpe_current, sharpe_proposed,
                          drawdown_current, drawdown_proposed,
                          winrate_current, winrate_proposed,
                          edge_current, edge_proposed,
                          details, timestamp
                   FROM p3_d06_injection_history
                   WHERE candidate_id = %s
                   ORDER BY timestamp DESC LIMIT 1""",
                (candidate_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": f"Candidate {candidate_id} not found"}

            comparison = {
                "candidate_id": row[0],
                "asset": row[1],
                "recommendation": row[2],
                "current": {
                    "sharpe": row[3],
                    "max_drawdown": row[4],
                    "win_rate": row[7],
                    "expected_edge": row[9],
                },
                "proposed": {
                    "sharpe": row[5],
                    "max_drawdown": row[6],
                    "win_rate": row[8],
                    "expected_edge": row[10],
                },
                "details": json.loads(row[11]) if row[11] else {},
                "timestamp": row[12],
            }

            # Pseudotrader results
            cur.execute(
                """SELECT pnl_impact, drawdown_impact, sharpe_delta,
                          pbo_score, dsr_score, details
                   FROM p3_d11_pseudotrader_results
                   WHERE candidate_id = %s
                   ORDER BY timestamp DESC LIMIT 1""",
                (candidate_id,),
            )
            pt_row = cur.fetchone()
            if pt_row:
                comparison["pseudotrader"] = {
                    "pnl_impact": pt_row[0],
                    "drawdown_impact": pt_row[1],
                    "sharpe_delta": pt_row[2],
                    "pbo_score": pt_row[3],
                    "dsr_score": pt_row[4],
                    "details": json.loads(pt_row[5]) if pt_row[5] else {},
                }

            return comparison

    except Exception as exc:
        logger.error("Injection comparison query failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Decision routing
# ---------------------------------------------------------------------------


def route_injection_decision(candidate_id: str, decision: str,
                             user_id: str, gui_push_fn: Callable):
    """Route a user's injection decision to Offline B4.

    Parameters
    ----------
    candidate_id : str
        The candidate being acted on.
    decision : str
        One of ``ADOPT``, ``PARALLEL_TRACK``, ``REJECT``.
    user_id : str
        The user making the decision.
    gui_push_fn : callable
        For acknowledgement push.
    """
    valid_decisions = {"ADOPT", "PARALLEL_TRACK", "REJECT"}
    if decision not in valid_decisions:
        logger.warning("Invalid injection decision: %s", decision)
        return

    redis_client = get_redis_client()
    redis_client.publish(CH_COMMANDS, json.dumps({
        "type": f"{decision}_STRATEGY" if decision != "PARALLEL_TRACK" else "PARALLEL_TRACK",
        "candidate_id": candidate_id,
        "user_id": user_id,
    }))

    # Log decision
    _log_injection_decision(candidate_id, decision, user_id)

    gui_push_fn(user_id, {
        "type": "command_ack",
        "command": "INJECTION_DECISION",
        "candidate_id": candidate_id,
        "decision": decision,
    })

    write_checkpoint("COMMAND", "INJECTION_DECISION", "routed", "waiting",
                     {"candidate_id": candidate_id, "decision": decision})

    logger.info("Injection decision routed: candidate=%s decision=%s user=%s",
                candidate_id, decision, user_id)


# ---------------------------------------------------------------------------
# Parallel tracking monitor
# ---------------------------------------------------------------------------


def get_parallel_tracking_status(asset: str) -> list[dict]:
    """Fetch active parallel-track candidates for an asset.

    After ~20 days of parallel tracking, a final comparison panel
    should be displayed.

    Returns
    -------
    list[dict]
        Active parallel-track candidates with tracking metrics.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT candidate_id, asset, recommendation, details, timestamp
                   FROM p3_d06_injection_history
                   WHERE asset = %s AND recommendation = 'PARALLEL_TRACK'
                   ORDER BY timestamp DESC""",
                (asset,),
            )
            return [
                {
                    "candidate_id": r[0],
                    "asset": r[1],
                    "recommendation": r[2],
                    "details": json.loads(r[3]) if r[3] else {},
                    "started_at": r[4],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Parallel tracking query failed: %s", exc, exc_info=True)
    return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_injection_decision(candidate_id: str, decision: str, user_id: str):
    """Log injection decision to P3-D17 session_log."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(),
                    user_id,
                    "INJECTION_DECISION",
                    candidate_id,
                    "",
                    json.dumps({"decision": decision}),
                ),
            )
    except Exception as exc:
        logger.error("Injection decision log failed: %s", exc, exc_info=True)
