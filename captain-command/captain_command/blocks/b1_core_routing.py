# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 1: Core Routing (P3-PG-30).

Central message bus. Subscribes to Redis channels (signals, commands, alerts,
status), routes messages to GUI sessions, API adapters, and back to
Online/Offline.  Command NEVER modifies signals — it only formats, routes,
and logs.

Spec: Program3_Command.md lines 32-161
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable

from shared.questdb_client import get_cursor
from shared.redis_client import (
    get_redis_client,
    get_redis_pubsub,
    CH_COMMANDS,
    CH_ALERTS,
    CH_STATUS,
    CH_TRADE_OUTCOMES,
    signals_channel,
    publish_to_stream,
    STREAM_COMMANDS,
)
from shared.journal import write_checkpoint
from shared.constants import (
    COMMAND_TYPE_VALUES,
    NOTIFICATION_PRIORITY_VALUES,
    PROHIBITED_EXTERNAL_FIELDS,
    SYSTEM_TIMEZONE,
    now_et,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal routing
# ---------------------------------------------------------------------------


def route_signal_batch(payload: dict, gui_push_fn: Callable, api_route_fn: Callable | None = None):
    """Route a signal batch from Online B6 to GUI and optional API adapters.

    Parameters
    ----------
    payload : dict
        Full signal batch as published by Online B6 to captain:signals:{user_id}.
        Contains ``user_id``, ``session_id``, ``timestamp``, ``signals``,
        and ``below_threshold``.
    gui_push_fn : callable
        ``gui_push_fn(user_id, message_dict)`` — pushes to the user's
        WebSocket session(s).
    api_route_fn : callable or None
        ``api_route_fn(account_id, sanitised_order)`` — sends to external
        API adapter.  None means no API adapters active.
    """
    user_id = payload.get("user_id")
    signals = payload.get("signals", [])
    below_threshold = payload.get("below_threshold", [])

    for signal in signals:
        signal_id = signal.get("signal_id", f"SIG-{uuid.uuid4().hex[:12].upper()}")

        # --- Store in P3-D17 session_log ---
        _log_signal_received(signal_id, user_id, signal)

        # --- Push sanitised signal to GUI (strip PROHIBITED_EXTERNAL_FIELDS) ---
        gui_push_fn(user_id, {
            "type": "signal",
            "signal": sanitise_for_gui(signal),
        })

        # --- Route to API adapters (per-account, sanitised) ---
        if api_route_fn:
            per_account = signal.get("per_account", {})
            for ac_id, ac_detail in per_account.items():
                if ac_detail.get("contracts", 0) <= 0:
                    continue
                sanitised = sanitise_for_api(signal, ac_id, ac_detail)
                try:
                    api_route_fn(ac_id, sanitised)
                except Exception as exc:
                    logger.error("API route failed for account %s: %s", ac_id, exc, exc_info=True)

    # Push below-threshold info so GUI can show suppressed signals
    if below_threshold:
        gui_push_fn(user_id, {
            "type": "below_threshold",
            "items": below_threshold,
        })


def sanitise_for_gui(signal: dict) -> dict:
    """Strip PROHIBITED_EXTERNAL_FIELDS before GUI WebSocket push.

    Spec: Doc 20 PG-26.  The GUI may display signal metadata (asset,
    direction, confidence tier, quality score, etc.) but must never
    receive proprietary model internals.
    """
    return {k: v for k, v in signal.items() if k not in PROHIBITED_EXTERNAL_FIELDS}


def sanitise_for_api(signal: dict, ac_id: str, ac_detail: dict) -> dict:
    """Return the 6-field sanitised order — nothing else leaves Captain.

    Spec: Command lines 139-160.  PROHIBITED_FIELDS never sent externally.
    """
    return {
        "asset": signal.get("asset"),
        "direction": signal.get("direction"),
        "size": ac_detail.get("contracts", 0),
        "tp": signal.get("tp_level"),
        "sl": signal.get("sl_level"),
        "timestamp": signal.get("timestamp", now_et().isoformat()),
    }


# ---------------------------------------------------------------------------
# Command routing
# ---------------------------------------------------------------------------

# Command types that get forwarded to Offline via captain:commands
_OFFLINE_COMMANDS = {
    "ADOPT_STRATEGY", "REJECT_STRATEGY", "PARALLEL_TRACK",
    "ACTIVATE_AIM", "DEACTIVATE_AIM", "TRIGGER_DIAGNOSTIC",
}

# Command types forwarded to Online via captain:commands
_ONLINE_COMMANDS = {"TAKEN_SKIPPED", "MANUAL_PAUSE", "MANUAL_RESUME"}


def route_command(data: dict, gui_push_fn: Callable):
    """Route an inbound command from GUI/API to the correct subsystem.

    Commands arrive on ``captain:commands`` (published by the API/WebSocket
    layer when a user takes an action).  This function decides where to
    forward them.

    Parameters
    ----------
    data : dict
        Must contain ``type`` (one of COMMAND_TYPE_VALUES) and ``user_id``.
    gui_push_fn : callable
        For acknowledgement pushes back to the user's GUI.
    """
    cmd_type = data.get("type", "")
    user_id = data.get("user_id", "SYSTEM")

    if cmd_type not in COMMAND_TYPE_VALUES:
        logger.warning("Unknown command type: %s from user %s", cmd_type, user_id)
        return

    logger.info("Routing command %s from user %s", cmd_type, user_id)

    redis_client = get_redis_client()

    # ------------------------------------------------------------------
    # TAKEN / SKIPPED  — forward to Online (position creation / logging)
    # ------------------------------------------------------------------
    if cmd_type == "TAKEN_SKIPPED":
        action = data.get("action")  # "TAKEN" or "SKIPPED"
        signal_id = data.get("signal_id")

        _log_trade_confirmation(signal_id, user_id, action, data)

        # Forward to Online orchestrator (durable stream delivery)
        publish_to_stream(STREAM_COMMANDS, {
            "type": "TAKEN_SKIPPED",
            "action": action,
            "signal_id": signal_id,
            "user_id": user_id,
            "asset": data.get("asset"),
            "direction": data.get("direction"),
            "actual_entry_price": data.get("actual_entry_price"),
            "entry_price": data.get("entry_price"),
            "contracts": data.get("contracts"),
            "tp_level": data.get("tp_level"),
            "sl_level": data.get("sl_level"),
            "point_value": data.get("point_value", 50.0),
            "risk_amount": data.get("risk_amount", 0),
            "account_id": data.get("account_id"),
            "session": data.get("session"),
            "regime_state": data.get("regime_state"),
            "combined_modifier": data.get("combined_modifier"),
            "aim_breakdown": data.get("aim_breakdown"),
            "tsm_id": data.get("tsm_id"),
        })

        gui_push_fn(user_id, {
            "type": "command_ack",
            "command": "TAKEN_SKIPPED",
            "action": action,
            "signal_id": signal_id,
        })

    # ------------------------------------------------------------------
    # Strategy injection decisions — forward to Offline
    # ------------------------------------------------------------------
    elif cmd_type in ("ADOPT_STRATEGY", "REJECT_STRATEGY", "PARALLEL_TRACK"):
        publish_to_stream(STREAM_COMMANDS, {
            "type": cmd_type,
            "user_id": user_id,
            "asset": data.get("asset"),
            "candidate_id": data.get("candidate_id"),
        })
        gui_push_fn(user_id, {"type": "command_ack", "command": cmd_type})

    # ------------------------------------------------------------------
    # TSM selection
    # ------------------------------------------------------------------
    elif cmd_type == "SELECT_TSM":
        _handle_tsm_switch(data)
        gui_push_fn(user_id, {
            "type": "command_ack",
            "command": "SELECT_TSM",
            "account_id": data.get("account_id"),
            "tsm_name": data.get("tsm_name"),
        })

    # ------------------------------------------------------------------
    # AIM control — forward to Offline
    # ------------------------------------------------------------------
    elif cmd_type in ("ACTIVATE_AIM", "DEACTIVATE_AIM"):
        publish_to_stream(STREAM_COMMANDS, {
            "type": cmd_type,
            "user_id": user_id,
            "aim_id": data.get("aim_id"),
            "asset": data.get("asset"),
        })
        gui_push_fn(user_id, {"type": "command_ack", "command": cmd_type})

    # ------------------------------------------------------------------
    # Concentration response
    # ------------------------------------------------------------------
    elif cmd_type in ("CONCENTRATION_PROCEED", "CONCENTRATION_PAUSE"):
        _handle_concentration_response(
            data.get("event_id"),
            "PROCEED" if cmd_type == "CONCENTRATION_PROCEED" else "PAUSE",
            user_id,
        )
        gui_push_fn(user_id, {"type": "command_ack", "command": cmd_type})

    # ------------------------------------------------------------------
    # Contract roll confirmation
    # ------------------------------------------------------------------
    elif cmd_type == "CONFIRM_ROLL":
        _confirm_contract_roll(data.get("asset"), data.get("new_contract"), user_id)
        gui_push_fn(user_id, {"type": "command_ack", "command": "CONFIRM_ROLL"})

    # ------------------------------------------------------------------
    # Action item update (from diagnostic queue)
    # ------------------------------------------------------------------
    elif cmd_type == "UPDATE_ACTION_ITEM":
        _update_action_item(
            user_id, data.get("action_id"),
            data.get("new_status"), data.get("notes"),
        )
        gui_push_fn(user_id, {"type": "command_ack", "command": "UPDATE_ACTION_ITEM"})

    # ------------------------------------------------------------------
    # Trigger on-demand diagnostic — forward to Offline
    # ------------------------------------------------------------------
    elif cmd_type == "TRIGGER_DIAGNOSTIC":
        publish_to_stream(STREAM_COMMANDS, {
            "type": "TRIGGER_DIAGNOSTIC",
            "user_id": user_id,
            "mode": "ON_DEMAND",
        })
        gui_push_fn(user_id, {"type": "command_ack", "command": "TRIGGER_DIAGNOSTIC"})

    # ------------------------------------------------------------------
    # Manual pause / resume
    # ------------------------------------------------------------------
    elif cmd_type in ("MANUAL_PAUSE", "MANUAL_RESUME"):
        paused = cmd_type == "MANUAL_PAUSE"
        _set_asset_pause(data.get("asset"), paused, user_id)
        redis_client.publish(CH_COMMANDS, json.dumps({
            "type": "MANUAL_HALT" if paused else "MANUAL_RESUME",
            "user_id": user_id,
            "asset": data.get("asset"),
        }))
        gui_push_fn(user_id, {"type": "command_ack", "command": cmd_type})


# ---------------------------------------------------------------------------
# Notification routing
# ---------------------------------------------------------------------------


def route_notification(notif: dict, gui_push_fn: Callable,
                       telegram_fn: Callable | None = None):
    """Route a notification to GUI, Telegram, and log to P3-D10.

    Parameters
    ----------
    notif : dict
        Must contain ``priority``, ``message``, and optionally ``user_id``.
        If ``user_id`` is absent, broadcasts to all active users.
    gui_push_fn : callable
        ``gui_push_fn(user_id, message_dict)``
    telegram_fn : callable or None
        ``telegram_fn(user_id, message, priority)``
    """
    priority = notif.get("priority", "LOW")
    user_id = notif.get("user_id")
    message = notif.get("message", "")
    notif_id = notif.get("notif_id", f"NOTIF-{uuid.uuid4().hex[:12].upper()}")
    ts = notif.get("timestamp", now_et().isoformat())

    if user_id:
        target_users = [user_id]
    else:
        target_users = _get_all_active_user_ids()

    for uid in target_users:
        gui_push_fn(uid, {
            "type": "notification",
            "notif_id": notif_id,
            "priority": priority,
            "message": message,
            "timestamp": ts,
            "source": notif.get("source", "SYSTEM"),
        })

        if telegram_fn and priority in ("CRITICAL", "HIGH"):
            try:
                telegram_fn(uid, message, priority)
            except Exception as exc:
                logger.error("Telegram send failed for user %s: %s", uid, exc)

    _log_notification(notif_id, user_id or "SYSTEM", priority, message, ts)


# ---------------------------------------------------------------------------
# Status / heartbeat handling
# ---------------------------------------------------------------------------


def handle_status_message(data: dict, process_health: dict):
    """Update in-memory process health from a heartbeat message.

    Parameters
    ----------
    data : dict
        ``{role, status, timestamp, ...}`` from a Captain process.
    process_health : dict
        Mutable dict keyed by role ("OFFLINE", "ONLINE", "COMMAND")
        storing latest heartbeat info.
    """
    role = data.get("role", "UNKNOWN")
    process_health[role] = {
        "status": data.get("status", "unknown"),
        "timestamp": data.get("timestamp", now_et().isoformat()),
        "details": data.get("details", {}),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _log_signal_received(signal_id: str, user_id: str, signal: dict):
    """Insert a row into P3-D17 session_log for auditing."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id,
                       asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(),
                    user_id,
                    "SIGNAL_RECEIVED",
                    signal_id,
                    signal.get("asset", ""),
                    json.dumps({
                        "direction": signal.get("direction"),
                        "entry_price": signal.get("entry_price"),
                        "tp_level": signal.get("tp_level"),
                        "sl_level": signal.get("sl_level"),
                        "confidence_tier": signal.get("confidence_tier"),
                        "quality_score": signal.get("quality_score"),
                    }),
                ),
            )
    except Exception as exc:
        logger.error("Failed to log signal %s: %s", signal_id, exc, exc_info=True)


def mark_signals_cleared(user_id: str, signal_ids: list[str]):
    """Insert SIGNAL_CLEARED events so cleared signals don't reappear on refresh."""
    try:
        with get_cursor() as cur:
            for sid in signal_ids:
                cur.execute(
                    """INSERT INTO p3_session_event_log(
                           ts, user_id, event_type, event_id,
                           asset, details
                       ) VALUES(%s, %s, %s, %s, %s, %s)""",
                    (
                        now_et().isoformat(),
                        user_id,
                        "SIGNAL_CLEARED",
                        sid,
                        "",
                        "{}",
                    ),
                )
    except Exception as exc:
        logger.error("Failed to mark signals cleared: %s", exc, exc_info=True)


def _log_trade_confirmation(signal_id: str, user_id: str, action: str, data: dict):
    """Log TAKEN/SKIPPED to P3-D17."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id,
                       asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(),
                    user_id,
                    f"TRADE_{action}",
                    signal_id,
                    data.get("asset", ""),
                    json.dumps({
                        "account_id": data.get("account_id"),
                        "contracts": data.get("contracts"),
                        "actual_entry_price": data.get("actual_entry_price"),
                    }),
                ),
            )
    except Exception as exc:
        logger.error("Failed to log trade confirmation %s: %s", signal_id, exc, exc_info=True)


def _log_notification(notif_id: str, user_id: str, priority: str,
                      message: str, timestamp: str):
    """Insert into P3-D10 notification_log."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d10_notification_log(
                       notification_id, user_id, priority,
                       message, gui_delivered, ts
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (notif_id, user_id, priority, message, True, timestamp),
            )
    except Exception as exc:
        logger.error("Failed to log notification %s: %s", notif_id, exc, exc_info=True)


def _handle_tsm_switch(data: dict):
    """Update P3-D08 with new TSM selection for an account."""
    account_id = data.get("account_id")
    tsm_name = data.get("tsm_name")
    user_id = data.get("user_id")
    logger.info("TSM switch: account=%s tsm=%s user=%s", account_id, tsm_name, user_id)
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), user_id, "TSM_SWITCH",
                    account_id, "", json.dumps({"tsm_name": tsm_name}),
                ),
            )
    except Exception as exc:
        logger.error("TSM switch log failed: %s", exc, exc_info=True)


def _handle_concentration_response(event_id: str, decision: str, user_id: str):
    """Log concentration decision to P3-D17."""
    logger.info("Concentration %s for event %s by %s", decision, event_id, user_id)
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), user_id,
                    "CONCENTRATION_RESPONSE", event_id, "",
                    json.dumps({"decision": decision}),
                ),
            )
    except Exception as exc:
        logger.error("Concentration response log failed: %s", exc, exc_info=True)


def _confirm_contract_roll(asset: str, new_contract: str, user_id: str):
    """Update P3-D00 roll_calendar with confirmed new contract."""
    logger.info("Roll confirmed: asset=%s contract=%s user=%s", asset, new_contract, user_id)
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), user_id, "ROLL_CONFIRMED",
                    f"ROLL-{asset}", asset,
                    json.dumps({"new_contract": new_contract}),
                ),
            )
    except Exception as exc:
        logger.error("Roll confirmation log failed: %s", exc, exc_info=True)


def _update_action_item(user_id: str, action_id: str, new_status: str, notes: str):
    """Update action item status — logged to session event log."""
    logger.info("Action item %s → %s by %s", action_id, new_status, user_id)
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(),
                    user_id,
                    "ACTION_ITEM_UPDATE",
                    action_id,
                    "",
                    json.dumps({
                        "new_status": new_status,
                        "notes": notes,
                    }),
                ),
            )
    except Exception as exc:
        logger.error("Action item update failed: %s", exc, exc_info=True)


def _set_asset_pause(asset: str, paused: bool, user_id: str):
    """Set manual pause flag via P3-D17."""
    logger.info("Asset %s %s by %s", asset, "PAUSED" if paused else "RESUMED", user_id)
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), user_id,
                    "MANUAL_PAUSE" if paused else "MANUAL_RESUME",
                    f"PAUSE-{asset}", asset,
                    json.dumps({"paused": paused}),
                ),
            )
    except Exception as exc:
        logger.error("Asset pause toggle failed: %s", exc, exc_info=True)


def _get_all_active_user_ids() -> list[str]:
    """Fetch all active user IDs from P3-D16 capital_silos."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT DISTINCT user_id FROM p3_d16_user_capital_silos WHERE status = 'ACTIVE'"
            )
            return [row[0] for row in cur.fetchall()]
    except Exception as exc:
        logger.error("Failed to fetch active users: %s", exc, exc_info=True)
        return []
