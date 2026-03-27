# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 7: Notification System (Phase 6).

Full notification routing with:
- 26 event types mapped to 4 priority levels (CRITICAL/HIGH/MEDIUM/LOW)
- Per-user preferences (channel, priority threshold, quiet hours, asset filter)
- Quiet hours queue (max 50, CRITICAL bypasses, flush at quiet_hours_end)
- Telegram integration via CaptainTelegramBot
- GUI WebSocket push (always delivered)
- Full delivery logging to P3-D10
- Incident severity routing by role tags

Spec: NotificationSpec.md (full), Program3_Command.md lines 619-658
"""

import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from shared.questdb_client import get_cursor
from shared.constants import NOTIFICATION_PRIORITY_VALUES, SYSTEM_TIMEZONE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priority ordering (lower = more severe)
# ---------------------------------------------------------------------------

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# ---------------------------------------------------------------------------
# 26 notification event types → default priority + recipient roles
# Spec: NotificationSpec.md §2.1-2.4
# ---------------------------------------------------------------------------

EVENT_REGISTRY: dict[str, dict[str, Any]] = {
    # --- CRITICAL (9 events) ---
    "TP_HIT":                   {"priority": "CRITICAL", "roles": ["TRADER"],           "template": "[CRITICAL] {asset}: Position closed — TP hit. PnL: {pnl}."},
    "SL_HIT":                   {"priority": "CRITICAL", "roles": ["TRADER"],           "template": "[CRITICAL] {asset}: Position closed — SL hit. PnL: {pnl}."},
    "DECAY_LEVEL3":             {"priority": "CRITICAL", "roles": ["ADMIN", "DEV"],     "template": "[CRITICAL] {asset}: Strategy review triggered. Signals halted."},
    "TSM_MDD_BREACH":           {"priority": "CRITICAL", "roles": ["TRADER", "ADMIN"],  "template": "[CRITICAL] {account}: Drawdown at {pct}% of limit."},
    "TSM_MLL_BREACH":           {"priority": "CRITICAL", "roles": ["TRADER", "ADMIN"],  "template": "[CRITICAL] {account}: Daily loss limit reached. No more trades today."},
    "SYSTEM_CRASH":             {"priority": "CRITICAL", "roles": ["ADMIN", "DEV"],     "template": "[CRITICAL] Captain system failure. Signals unavailable."},
    "MID_TRADE_REGIME_SHIFT":   {"priority": "CRITICAL", "roles": ["TRADER"],           "template": "[CRITICAL] {asset}: Regime shift detected while position open."},
    "API_KEY_COMPROMISE":       {"priority": "CRITICAL", "roles": ["ADMIN", "DEV"],     "template": "[CRITICAL] API key compromise detected for {account}. Keys rotated. Review incident log."},
    "API_CONNECTION_LOST":      {"priority": "CRITICAL", "roles": ["ADMIN", "DEV"],     "template": "[CRITICAL] API connection lost for {account}. Auto-reconnect failed after 3 retries."},
    "ENTRY_PRICE_MISSING":      {"priority": "CRITICAL", "roles": ["TRADER"],           "template": "[CRITICAL] Actual entry price not recorded for {asset} trade after 5 minutes."},
    # --- HIGH (9 events) ---
    "SIGNAL_GENERATED":         {"priority": "HIGH", "roles": ["TRADER"],               "template": "[HIGH] {asset}: Signal available — check GUI for details."},
    "DECAY_LEVEL2":             {"priority": "HIGH", "roles": ["ADMIN"],                "template": "[HIGH] {asset}: Sizing reduced to {pct}% — decay detected."},
    "REGIME_CHANGE":            {"priority": "HIGH", "roles": ["ADMIN"],                "template": "[HIGH] {asset}: Regime changed to {regime}."},
    "AIM_FRAGILE":              {"priority": "HIGH", "roles": ["ADMIN"],                "template": "[HIGH] {asset}: Strategy flagged FRAGILE — review RPT-03."},
    "INJECTION_AVAILABLE":      {"priority": "HIGH", "roles": ["ADMIN"],                "template": "[HIGH] {asset}: New strategy candidate — review RPT-05."},
    "VIX_SPIKE":                {"priority": "HIGH", "roles": ["TRADER"],               "template": "[HIGH] {asset}: VIX spike detected ({value})."},
    "AUTO_EXEC_GATE":           {"priority": "HIGH", "roles": ["ADMIN"],                "template": "[HIGH] Automated execution compliance gate: {satisfied}/{total} requirements met. ADMIN approval required."},
    "HEALTH_DIAGNOSTIC":        {"priority": "HIGH", "roles": ["ADMIN", "DEV"],         "template": "[HIGH] System Health Diagnostic: {count} CRITICAL action items. Overall health: {score}%. Review System Overview."},
    "ACTION_ITEM_REOPENED":     {"priority": "HIGH", "roles": ["ADMIN"],                "template": "[HIGH] Action item {action_id} reopened — resolution did not improve metric."},
    # --- MEDIUM (4 events) ---
    "AIM_WARMUP_COMPLETE":      {"priority": "MEDIUM", "roles": ["ADMIN"],              "template": "[MEDIUM] AIM-{aim_id} warm-up complete — eligible for activation."},
    "WEEKLY_REPORT_READY":      {"priority": "MEDIUM", "roles": ["ADMIN"],              "template": "[MEDIUM] RPT-02 Weekly Performance ready."},
    "PARALLEL_TRACKING_DONE":   {"priority": "MEDIUM", "roles": ["ADMIN"],              "template": "[MEDIUM] {asset}: Parallel tracking complete — final decision needed."},
    "API_KEY_ROTATION_DUE":     {"priority": "MEDIUM", "roles": ["ADMIN"],              "template": "[MEDIUM] API key for {account} expires in {days} days."},
    # --- LOW (4 events) ---
    "MONTHLY_REPORT_READY":     {"priority": "LOW", "roles": ["ADMIN"],                 "template": "[LOW] RPT-03 Monthly Health ready."},
    "RETRAIN_COMPLETE":         {"priority": "LOW", "roles": ["DEV"],                   "template": "[LOW] AIM models retrained successfully."},
    "SYSTEM_STATUS":            {"priority": "LOW", "roles": ["ADMIN"],                 "template": "[LOW] Captain system healthy. Uptime: {days}d {hours}h."},
    "ANNUAL_REVIEW_READY":      {"priority": "LOW", "roles": ["ADMIN"],                 "template": "[LOW] RPT-10 Annual Review ready."},
}

NOTIFICATION_EVENTS = set(EVENT_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Default user notification preferences (spec §5)
# ---------------------------------------------------------------------------

DEFAULT_PREFERENCES = {
    "gui_notifications": True,           # Always on, cannot disable
    "telegram_enabled": True,
    "telegram_chat_id": None,
    "email_enabled": False,              # Future v2
    "email_address": None,
    "min_telegram_priority": "HIGH",     # Receive HIGH + CRITICAL
    "min_email_priority": "MEDIUM",
    "gui_min_priority": "LOW",           # Everything in GUI
    "quiet_hours_enabled": True,
    "quiet_hours_start": 22,             # 10 PM
    "quiet_hours_end": 6,                # 6 AM (spec: 06:00)
    "quiet_hours_timezone": "America/New_York",
    "notify_assets": ["ALL"],
    "sound_on_critical": True,
    "sound_on_high": True,
    "sound_on_medium": False,
}

# ---------------------------------------------------------------------------
# Quiet hours queue (spec §4)
# Max 50 messages per user. Oldest dropped if exceeded.
# ---------------------------------------------------------------------------

QUIET_QUEUE_MAX = 50

# {user_id: [(notif_dict, timestamp), ...]}
_quiet_queue: dict[str, list[tuple[dict, str]]] = defaultdict(list)
_quiet_queue_lock = threading.Lock()


def _enqueue_quiet(user_id: str, notif: dict, ts: str):
    """Add a notification to the quiet hours queue."""
    with _quiet_queue_lock:
        queue = _quiet_queue[user_id]
        queue.append((notif, ts))
        # Enforce max size — drop oldest
        while len(queue) > QUIET_QUEUE_MAX:
            queue.pop(0)


def flush_quiet_queue(user_id: str, telegram_send_fn: Callable | None = None):
    """Flush queued notifications for a user when quiet hours end.

    Called by the scheduler when quiet_hours_end is reached.
    """
    with _quiet_queue_lock:
        queue = _quiet_queue.pop(user_id, [])

    if not queue:
        return

    logger.info("Flushing %d queued notifications for user %s", len(queue), user_id)

    for notif, ts in queue:
        priority = notif.get("priority", "LOW")
        message = notif.get("message", "")
        chat_id = notif.get("_chat_id")

        if telegram_send_fn and chat_id:
            telegram_send_fn(chat_id, message, priority)


def get_quiet_queue_size(user_id: str) -> int:
    """Get count of queued messages for a user."""
    with _quiet_queue_lock:
        return len(_quiet_queue.get(user_id, []))


# ---------------------------------------------------------------------------
# Notification routing — main entry point
# ---------------------------------------------------------------------------


def route_notification(
    notif: dict,
    gui_push_fn: Callable,
    telegram_bot=None,
):
    """Route a notification to GUI, Telegram, and log to P3-D10.

    Parameters
    ----------
    notif : dict
        Must contain:
        - ``event_type`` (str) — one of NOTIFICATION_EVENTS, OR
        - ``priority`` + ``message`` (for ad-hoc notifications)
        Optional:
        - ``user_id`` — target user (broadcasts if absent)
        - ``asset``, ``data`` — context for template rendering
    gui_push_fn : callable
        ``gui_push_fn(user_id, message_dict)``
    telegram_bot : CaptainTelegramBot or None
        Telegram bot instance for sending messages.
    """
    event_type = notif.get("event_type", notif.get("source", ""))
    notif_id = notif.get("notif_id", f"NOTIF-{uuid.uuid4().hex[:12].upper()}")
    ts = notif.get("timestamp", datetime.now().isoformat())

    # Resolve priority and message from event registry
    registry_entry = EVENT_REGISTRY.get(event_type)
    if registry_entry:
        priority = notif.get("priority", registry_entry["priority"])
        template = registry_entry["template"]
        template_data = notif.get("data", {})
        template_data.update({
            k: notif.get(k, "")
            for k in ("asset", "account", "pnl", "pct", "regime", "value",
                       "aim_id", "action_id", "days", "hours", "score",
                       "count", "satisfied", "total")
        })
        try:
            message = template.format(**{
                k: template_data.get(k, f"{{{k}}}")
                for k in _extract_placeholders(template)
            })
        except (KeyError, IndexError):
            message = notif.get("message", template)
        target_roles = registry_entry["roles"]
    else:
        priority = notif.get("priority", "LOW")
        message = notif.get("message", "")
        target_roles = notif.get("roles", ["ADMIN"])

    if priority not in NOTIFICATION_PRIORITY_VALUES:
        logger.warning("Invalid notification priority: %s", priority)
        priority = "LOW"

    # Determine target users
    user_id = notif.get("user_id")
    asset = notif.get("asset")

    if user_id:
        target_users = [user_id]
    else:
        target_users = _get_users_by_roles(target_roles)

    # Delivery tracking
    delivery = {
        "gui_delivered": False,
        "telegram_delivered": False,
        "email_delivered": False,
    }

    for uid in target_users:
        prefs = _get_user_preferences(uid)

        # Asset filter check
        asset_filter = prefs.get("notify_assets", ["ALL"])
        if asset and asset_filter != ["ALL"] and asset not in asset_filter:
            continue

        # --- GUI — always deliver (cannot disable) ---
        gui_min = prefs.get("gui_min_priority", "LOW")
        if PRIORITY_ORDER.get(priority, 3) <= PRIORITY_ORDER.get(gui_min, 3):
            gui_push_fn(uid, {
                "type": "notification",
                "notif_id": notif_id,
                "priority": priority,
                "event_type": event_type,
                "message": message,
                "source": notif.get("source", "SYSTEM"),
                "timestamp": ts,
                "asset": asset,
                "action_required": notif.get("action_required", False),
                "data": notif.get("data"),
                "sound": _should_play_sound(priority, prefs),
            })
            delivery["gui_delivered"] = True

        # --- Telegram ---
        if telegram_bot and prefs.get("telegram_enabled", True):
            chat_id = prefs.get("telegram_chat_id") or _get_telegram_chat_id(uid)
            tg_min = prefs.get("min_telegram_priority", "HIGH")

            if (chat_id and
                    PRIORITY_ORDER.get(priority, 3) <= PRIORITY_ORDER.get(tg_min, 3)):

                if _is_in_quiet_hours(prefs) and priority != "CRITICAL":
                    # Queue for later delivery
                    _enqueue_quiet(uid, {
                        "priority": priority,
                        "message": message,
                        "_chat_id": chat_id,
                    }, ts)
                else:
                    # Determine if this is a signal notification (needs inline buttons)
                    signal_id = notif.get("data", {}).get("signal_id") if notif.get("data") else None
                    if event_type == "SIGNAL_GENERATED" and signal_id:
                        sent = telegram_bot.send_signal_notification(
                            chat_id=chat_id,
                            asset=asset or "",
                            direction=notif.get("data", {}).get("direction", ""),
                            confidence=notif.get("data", {}).get("confidence", ""),
                            signal_id=signal_id,
                        )
                    else:
                        # Format with priority emoji
                        prefix = {
                            "CRITICAL": "\U0001f6a8",
                            "HIGH": "\u26a0\ufe0f",
                            "MEDIUM": "\u2139\ufe0f",
                            "LOW": "\U0001f4dd",
                        }.get(priority, "")
                        formatted = f"{prefix} {message}"
                        sent = telegram_bot.send_message(
                            chat_id, formatted, priority,
                        )

                    delivery["telegram_delivered"] = sent

    # Log to P3-D10
    _log_notification_full(
        notif_id=notif_id,
        user_id=user_id or "SYSTEM",
        timestamp=ts,
        priority=priority,
        event_type=event_type,
        asset=asset or "",
        message=message,
        action_required=notif.get("action_required", False),
        delivery=delivery,
    )


# ---------------------------------------------------------------------------
# Quiet hours check
# ---------------------------------------------------------------------------


def _is_in_quiet_hours(prefs: dict) -> bool:
    """Check if current time is in the user's quiet hours window."""
    if not prefs.get("quiet_hours_enabled", True):
        return False

    try:
        import zoneinfo
        tz_name = prefs.get("quiet_hours_timezone", SYSTEM_TIMEZONE)
        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()

    hour = now.hour
    quiet_start = prefs.get("quiet_hours_start", 22)
    quiet_end = prefs.get("quiet_hours_end", 6)

    if quiet_start > quiet_end:
        # Wraps midnight: e.g., 22:00 → 06:00
        return hour >= quiet_start or hour < quiet_end
    else:
        return quiet_start <= hour < quiet_end


def _should_play_sound(priority: str, prefs: dict) -> bool:
    """Determine if GUI should play a sound for this notification."""
    if priority == "CRITICAL":
        return prefs.get("sound_on_critical", True)
    elif priority == "HIGH":
        return prefs.get("sound_on_high", True)
    elif priority == "MEDIUM":
        return prefs.get("sound_on_medium", False)
    return False


# ---------------------------------------------------------------------------
# User preferences and lookups
# ---------------------------------------------------------------------------


def _get_user_preferences(user_id: str) -> dict:
    """Load notification preferences for a user.

    Checks P3-D17 session_event_log for NOTIFICATION_PREFS events.
    Falls back to DEFAULT_PREFERENCES.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT details FROM p3_session_event_log
                   WHERE user_id = %s AND event_type = 'NOTIFICATION_PREFS'
                   ORDER BY ts DESC LIMIT 1""",
                (user_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                saved = json.loads(row[0])
                return {**DEFAULT_PREFERENCES, **saved}
    except Exception:
        pass
    return DEFAULT_PREFERENCES.copy()


def save_user_preferences(user_id: str, prefs: dict):
    """Persist notification preferences for a user to P3-D17."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    datetime.now().isoformat(),
                    user_id,
                    "NOTIFICATION_PREFS",
                    f"PREFS-{user_id}",
                    "",
                    json.dumps(prefs),
                ),
            )
    except Exception as exc:
        logger.error("Save preferences failed: %s", exc)


def _get_telegram_chat_id(user_id: str) -> str | None:
    """Lookup Telegram chat_id for a user from P3-D16."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT telegram_chat_id FROM p3_d16_user_capital_silos
                   WHERE user_id = %s AND telegram_chat_id IS NOT NULL
                   ORDER BY last_updated DESC LIMIT 1""",
                (user_id,),
            )
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else None
    except Exception:
        return None


def _get_users_by_roles(roles: list[str]) -> list[str]:
    """Fetch user IDs that have any of the specified roles.

    For TRADER role: returns all active users (each user is their own trader).
    For ADMIN/DEV/RISK/SUPPORT: queries user roles.
    """
    try:
        with get_cursor() as cur:
            if "TRADER" in roles:
                # All active users are potential traders
                cur.execute(
                    "SELECT DISTINCT user_id FROM p3_d16_user_capital_silos "
                    "WHERE status = 'ACTIVE'"
                )
            else:
                # Query by role tags
                role_list = ",".join(f"'{r}'" for r in roles)
                cur.execute(
                    f"SELECT DISTINCT user_id FROM p3_d16_user_capital_silos "
                    f"WHERE status = 'ACTIVE' AND role IN ({role_list})"
                )
            return [row[0] for row in cur.fetchall()]
    except Exception as exc:
        logger.error("Role-based user query failed: %s", exc)
        return []


def _get_all_active_user_ids() -> list[str]:
    """Fetch all active user IDs."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT DISTINCT user_id FROM p3_d16_user_capital_silos "
                "WHERE status = 'ACTIVE'"
            )
            return [row[0] for row in cur.fetchall()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Full delivery logging to P3-D10 (spec §6)
# ---------------------------------------------------------------------------


def _log_notification_full(
    notif_id: str,
    user_id: str,
    timestamp: str,
    priority: str,
    event_type: str,
    asset: str,
    message: str,
    action_required: bool,
    delivery: dict,
):
    """Insert full notification record into P3-D10.

    Schema: notification_id, user_id, priority, event_type, asset, message,
            action_required, gui_delivered, gui_read, gui_read_at,
            telegram_delivered, telegram_read, email_delivered,
            user_response, response_at, ts
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d10_notification_log(
                       notification_id, user_id, priority,
                       event_type, asset, message, action_required,
                       gui_delivered, gui_read,
                       telegram_delivered, telegram_read,
                       email_delivered, ts
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    notif_id,
                    user_id,
                    priority,
                    event_type,
                    asset,
                    message[:500],  # Truncate for storage
                    action_required,
                    delivery.get("gui_delivered", False),
                    False,  # gui_read — not read yet
                    delivery.get("telegram_delivered", False),
                    False,  # telegram_read — unknown at send time
                    delivery.get("email_delivered", False),
                    timestamp,
                ),
            )
    except Exception as exc:
        logger.error("Notification log failed: %s", exc, exc_info=True)


def log_notification_response(notif_id: str, user_id: str,
                              response: str):
    """Log a user's response to an actionable notification (P3-D10 §6)."""
    ts = datetime.now().isoformat()
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d10_notification_log(
                       notification_id, user_id, priority,
                       event_type, asset, message, action_required,
                       gui_delivered, gui_read, telegram_delivered,
                       telegram_read, email_delivered,
                       user_response, response_at, ts
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    notif_id, user_id, "",
                    "USER_RESPONSE", "", response, False,
                    False, False, False,
                    False, False,
                    response, ts, ts,
                ),
            )
    except Exception as exc:
        logger.error("Notification response log failed: %s", exc)


def mark_gui_read(notif_id: str, user_id: str):
    """Record that a GUI notification was read (append-only, P3-D10 §6)."""
    ts = datetime.now().isoformat()
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d10_notification_log(
                       notification_id, user_id, priority,
                       event_type, asset, message, action_required,
                       gui_delivered, gui_read, gui_read_at,
                       telegram_delivered, telegram_read,
                       email_delivered, ts
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    notif_id, user_id, "",
                    "GUI_READ", "", "", False,
                    True, True, ts,
                    False, False,
                    False, ts,
                ),
            )
    except Exception as exc:
        logger.error("GUI read log failed: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_placeholders(template: str) -> list[str]:
    """Extract {placeholder} names from a template string."""
    import re
    return re.findall(r"\{(\w+)\}", template)
