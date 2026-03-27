# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Orchestrator (P3-ORCH-COMMAND).

Always-on event loop:
1. Redis listener thread  — subscribes to signals, commands, alerts, status
2. Scheduler thread       — periodic tasks (health checks, dashboard refresh,
                            reconciliation at 19:00 EST, quiet queue flush)
3. FastAPI thread         — HTTP/WebSocket server (started in main.py)
4. Telegram bot thread    — long-polling bot (started in main.py, injected here)

Spec: Program3_Command.md lines 881-907 + NotificationSpec.md
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

from shared.questdb_client import get_cursor
from shared.redis_client import (
    get_redis_client,
    get_redis_pubsub,
    CH_COMMANDS,
    CH_ALERTS,
    CH_STATUS,
    CH_TRADE_OUTCOMES,
    signals_channel,
    ensure_consumer_group,
    read_stream,
    ack_message,
    STREAM_SIGNALS,
    GROUP_COMMAND_SIGNALS,
)
from shared.journal import write_checkpoint
from shared.constants import SOD_RESET_HOUR, SOD_RESET_MINUTE, SYSTEM_TIMEZONE

from captain_command.blocks.b1_core_routing import (
    route_signal_batch,
    route_command,
    route_notification as core_route_notification,
    handle_status_message,
)
from captain_command.blocks.b2_gui_data_server import (
    build_dashboard_snapshot,
    build_system_overview,
    build_live_market_update,
)
from captain_command.blocks.b3_api_adapter import (
    run_health_checks,
    get_connection_summary,
)
from captain_command.blocks.b5_injection_flow import (
    notify_new_candidate,
    get_injection_comparison,
)
from captain_command.blocks.b7_notifications import (
    route_notification as notify_route,
    flush_quiet_queue,
    _get_all_active_user_ids,
    _is_in_quiet_hours,
    _get_user_preferences,
)
from captain_command.blocks.b8_reconciliation import run_daily_reconciliation
from captain_command.blocks.b9_incident_response import create_incident
from captain_command.api import (
    gui_push,
    update_process_health,
    update_api_connections,
    update_last_signal_time,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class CommandOrchestrator:
    """Captain Command event loop and scheduler.

    Attributes
    ----------
    running : bool
        Set to False to gracefully stop.
    process_health : dict
        Latest heartbeat info keyed by role.
    """

    def __init__(self):
        self.running = False
        self.telegram_bot = None  # Injected by main.py after bot creation
        self.process_health: dict = {
            "OFFLINE": {"status": "unknown", "timestamp": None},
            "ONLINE": {"status": "unknown", "timestamp": None},
            "COMMAND": {"status": "ok", "timestamp": datetime.now().isoformat()},
        }
        self._last_reconciliation_date: str | None = None
        self._last_dashboard_refresh: float = 0
        self._last_market_push: float = 0
        self._last_health_check: float = 0
        self._last_heartbeat: float = 0
        self._last_quiet_flush: float = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the signal stream reader, pub/sub listener, and scheduler."""
        self.running = True
        write_checkpoint("COMMAND", "ORCHESTRATOR_START", "starting", "running")
        logger.info("Command Orchestrator starting")

        # Background thread 1: Signal stream reader (durable delivery)
        self._signal_thread = threading.Thread(
            target=self._signal_stream_reader, daemon=True, name="cmd-signals"
        )
        self._signal_thread.start()

        # Background thread 2: Pub/sub for alerts + status (non-critical)
        self._redis_thread = threading.Thread(
            target=self._redis_listener, daemon=True, name="cmd-redis"
        )
        self._redis_thread.start()

        # Main loop: scheduler (runs in caller thread)
        self._run_scheduler()

    def stop(self):
        """Gracefully stop the orchestrator."""
        self.running = False
        write_checkpoint("COMMAND", "ORCHESTRATOR_STOP", "stopping", "stopped")
        logger.info("Command Orchestrator stopped")

    # ------------------------------------------------------------------
    # Redis listener (background thread)
    # ------------------------------------------------------------------

    def _signal_stream_reader(self):
        """Read signals from Redis Stream with durable delivery guarantee.

        Replaces the old pub/sub pattern-subscribe for captain:signals:*.
        """
        backoff = 1
        while self.running:
            try:
                ensure_consumer_group(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS)
                logger.info("Signal stream consumer group ready")
                backoff = 1

                while self.running:
                    for msg_id, data in read_stream(
                        STREAM_SIGNALS, GROUP_COMMAND_SIGNALS,
                        "command_1", block=2000,
                    ):
                        self._handle_signal(data)
                        ack_message(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, msg_id)

            except Exception as exc:
                if not self.running:
                    return
                logger.error("Signal stream error: %s — reconnecting in %ds", exc, backoff)
                if self.running:
                    try:
                        create_incident(
                            "RECONNECT", "P2_HIGH", "COMMAND",
                            f"Signal stream reconnecting after: {exc}",
                            notify_fn=lambda n: notify_route(n, gui_push, telegram_bot=self.telegram_bot),
                        )
                    except Exception:
                        pass
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)

    def _redis_listener(self):
        """Subscribe to non-critical pub/sub channels (alerts, status, commands).

        Signals are now read from Redis Streams in _signal_stream_reader().
        """
        logger.info("Redis pub/sub listener started (alerts + status)")
        backoff = 1

        while self.running:
            try:
                pubsub = get_redis_pubsub()
                pubsub.subscribe(CH_COMMANDS, CH_ALERTS, CH_STATUS)
                backoff = 1
                logger.info("Subscribed to pub/sub: %s, %s, %s",
                            CH_COMMANDS, CH_ALERTS, CH_STATUS)

                for message in pubsub.listen():
                    if not self.running:
                        return

                    if message["type"] != "message":
                        continue

                    try:
                        data = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue

                    channel = message.get("channel", "")

                    if channel == CH_COMMANDS:
                        self._handle_command(data)
                    elif channel == CH_ALERTS:
                        self._handle_alert(data)
                    elif channel == CH_STATUS:
                        self._handle_status(data)

            except Exception as exc:
                logger.error("Redis pub/sub error: %s — reconnecting in %ds",
                             exc, backoff)
                if self.running:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def _handle_signal(self, data: dict):
        """Route signal batch from Online B6 to GUI + API (if auto-execute)."""
        user_id = data.get("user_id", "")
        ts = data.get("timestamp", datetime.now().isoformat())

        update_last_signal_time(ts)

        # Auto-execute: route signals directly to TopstepX API adapter
        auto_execute = os.environ.get("AUTO_EXECUTE", "").lower() in ("1", "true", "yes")
        api_fn = self._auto_execute_signal if auto_execute else None

        route_signal_batch(
            payload=data,
            gui_push_fn=gui_push,
            api_route_fn=api_fn,
        )

        # Send Telegram notification for each signal (Phase 6)
        for signal in data.get("signals", []):
            notify_route({
                "event_type": "SIGNAL_GENERATED",
                "user_id": user_id,
                "asset": signal.get("asset"),
                "timestamp": ts,
                "data": {
                    "signal_id": signal.get("signal_id"),
                    "direction": signal.get("direction"),
                    "confidence": signal.get("confidence_tier", ""),
                    "auto_executed": auto_execute,
                },
            }, gui_push, telegram_bot=self.telegram_bot)

        logger.debug("Signal routed for user %s at %s (auto_execute=%s)",
                      user_id, ts, auto_execute)

    def _auto_execute_signal(self, account_id: str, sanitised_order: dict):
        """Execute a signal immediately via the TopstepX API adapter."""
        from captain_command.blocks.b3_api_adapter import _active_connections

        direction = sanitised_order.get("direction")
        if direction not in ("BUY", "SELL"):
            logger.info("AUTO-EXECUTE SKIP: direction=%s for %s (ORB pending breakout)",
                        direction, sanitised_order.get("asset"))
            gui_push("primary_user", {
                "type": "signal_pending",
                "message": f"Signal for {sanitised_order.get('asset')} awaiting OR breakout direction",
                "order": sanitised_order,
            })
            return

        state = _active_connections.get(account_id)
        if not state:
            logger.warning("Auto-execute: no adapter for account %s", account_id)
            return

        adapter = state.get("adapter")
        if not adapter or not adapter.connected:
            logger.warning("Auto-execute: adapter not connected for account %s", account_id)
            return

        logger.info("AUTO-EXECUTE: %s %s x%s (account=%s, TP=%s, SL=%s)",
                     direction, sanitised_order.get("asset"),
                     sanitised_order.get("size"), account_id,
                     sanitised_order.get("tp"), sanitised_order.get("sl"))

        result = adapter.send_signal(sanitised_order)
        status = result.get("status", "UNKNOWN")

        if status == "PLACED":
            logger.info("AUTO-EXECUTE SUCCESS: order_id=%s", result.get("order_id"))
            gui_push("primary_user", {
                "type": "command_ack",
                "command": "AUTO_EXECUTED",
                "order": sanitised_order,
                "result": result,
            })
        else:
            logger.error("AUTO-EXECUTE FAILED: %s — %s", status, result)
            gui_push("primary_user", {
                "type": "error",
                "message": f"Auto-execute failed: {status}",
                "detail": result,
            })

    def _handle_command(self, data: dict):
        """Route inbound command from GUI to appropriate subsystem."""
        # Only handle commands that originate from GUI (have user_id)
        # Skip commands that we published ourselves (from route_command)
        source = data.get("_source")
        if source == "orchestrator":
            return

        route_command(data, gui_push_fn=gui_push)

    def _handle_alert(self, data: dict):
        """Route alert notification to users via GUI + Telegram."""
        notify_route(data, gui_push, telegram_bot=self.telegram_bot)

    def _handle_status(self, data: dict):
        """Update process health from heartbeat."""
        handle_status_message(data, self.process_health)
        role = data.get("role", "UNKNOWN")
        update_process_health(role, self.process_health.get(role, {}))

    # ------------------------------------------------------------------
    # Scheduler (main thread)
    # ------------------------------------------------------------------

    def _run_scheduler(self):
        """Periodic task scheduler — runs every 1 second."""
        logger.info("Scheduler started")

        while self.running:
            now = time.time()

            try:
                # Live market push — every 1 second
                if now - self._last_market_push >= 1:
                    self._push_live_market()
                    self._last_market_push = now

                # Dashboard refresh — every 60 seconds
                if now - self._last_dashboard_refresh >= 60:
                    self._refresh_dashboards()
                    self._last_dashboard_refresh = now

                # API health checks — every 30 seconds
                if now - self._last_health_check >= 30:
                    self._run_health_checks()
                    self._last_health_check = now

                # Own heartbeat — every 30 seconds
                if now - self._last_heartbeat >= 30:
                    self._publish_heartbeat()
                    self._last_heartbeat = now

                # Quiet hours queue flush — every 60 seconds (Phase 6)
                if now - self._last_quiet_flush >= 60:
                    self._flush_quiet_queues()
                    self._last_quiet_flush = now

                # Daily reconciliation — 19:00 EST
                self._check_reconciliation_trigger()

            except Exception as exc:
                logger.error("Scheduler tick error: %s", exc, exc_info=True)

            time.sleep(1)

    def _push_live_market(self):
        """Push live market quote to all connected WebSocket users (~1 Hz)."""
        from captain_command.api import _ws_sessions

        if not _ws_sessions:
            return
        try:
            update = build_live_market_update()
            for user_id in list(_ws_sessions.keys()):
                gui_push(user_id, update)
        except Exception as exc:
            logger.debug("Market push error: %s", exc)

    def _refresh_dashboards(self):
        """Push fresh dashboard data to all connected WebSocket users.

        Excludes live_market from the WS push — it has its own 1Hz channel
        via _push_live_market.  Prevents the 60s snapshot from overwriting
        continuously-merged market data on the frontend.
        """
        from captain_command.api import _ws_sessions

        for user_id in list(_ws_sessions.keys()):
            try:
                snapshot = build_dashboard_snapshot(user_id)
                snapshot.pop("live_market", None)
                gui_push(user_id, snapshot)
            except Exception as exc:
                logger.error("Dashboard refresh failed for %s: %s", user_id, exc)

    def _flush_quiet_queues(self):
        """Flush quiet hours queues for users whose quiet hours have ended."""
        try:
            for uid in _get_all_active_user_ids():
                prefs = _get_user_preferences(uid)
                if not _is_in_quiet_hours(prefs):
                    def _tg_send(chat_id, message, priority):
                        if self.telegram_bot:
                            prefix = {
                                "CRITICAL": "\U0001f6a8",
                                "HIGH": "\u26a0\ufe0f",
                                "MEDIUM": "\u2139\ufe0f",
                                "LOW": "\U0001f4dd",
                            }.get(priority, "")
                            self.telegram_bot.send_message(
                                chat_id, f"{prefix} {message}", priority,
                            )

                    flush_quiet_queue(uid, telegram_send_fn=_tg_send)
        except Exception as exc:
            logger.error("Quiet queue flush error: %s", exc, exc_info=True)

    def _run_health_checks(self):
        """Run API connection health checks and update shared state."""
        def _notify(msg, priority):
            notify_route({
                "priority": priority,
                "message": msg,
                "source": "API_HEALTH",
            }, gui_push, telegram_bot=self.telegram_bot)

        summary = run_health_checks(notify_fn=_notify)
        update_api_connections(summary.get("details", {}))

    def _publish_heartbeat(self):
        """Publish Command process heartbeat to Redis."""
        try:
            client = get_redis_client()
            client.publish(CH_STATUS, json.dumps({
                "role": "COMMAND",
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "details": {
                    "api_connections": get_connection_summary(),
                },
            }))
            self.process_health["COMMAND"]["timestamp"] = datetime.now().isoformat()
        except Exception as exc:
            logger.error("Heartbeat publish failed: %s", exc)

    def _check_reconciliation_trigger(self):
        """Check if it's 19:00 EST and run daily reconciliation."""
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(SYSTEM_TIMEZONE)
            now = datetime.now(tz)
        except Exception:
            now = datetime.now()

        if now.hour == SOD_RESET_HOUR and now.minute == SOD_RESET_MINUTE:
            today = now.strftime("%Y-%m-%d")
            if self._last_reconciliation_date != today:
                self._last_reconciliation_date = today
                logger.info("Triggering daily reconciliation")

                def _notify(notif):
                    notify_route(notif, gui_push, telegram_bot=self.telegram_bot)

                run_daily_reconciliation(
                    gui_push_fn=gui_push,
                    get_broker_status_fn=None,  # V1: manual only
                    notify_fn=_notify,
                )
