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
    publish_to_stream,
    CH_COMMANDS,
    CH_ALERTS,
    CH_STATUS,
    CH_PROCESS_LOGS,
    signals_channel,
    ensure_consumer_group,
    read_stream,
    read_pending_stream,
    ack_message,
    STREAM_SIGNALS,
    STREAM_COMMANDS,
    STREAM_TRADE_OUTCOMES,
    GROUP_COMMAND_SIGNALS,
    GROUP_COMMAND_COMMANDS,
    GROUP_COMMAND_GUI_OUTCOMES,
)
from shared.process_logger import ProcessLogger
from shared.journal import write_checkpoint
from shared.constants import SOD_RESET_HOUR, SOD_RESET_MINUTE, SYSTEM_TIMEZONE, now_et

from captain_command.blocks.b1_core_routing import (
    route_signal_batch,
    route_command,
    route_notification as core_route_notification,
    handle_status_message,
    _log_trade_confirmation,
)
from captain_command.blocks.b2_gui_data_server import (
    build_dashboard_snapshot,
    build_system_overview,
    build_live_market_update,
    set_pipeline_stage,
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
from captain_command.blocks.trade_gui_bridge import build_trade_closed_ws_payload
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
        self.plog = ProcessLogger("COMMAND", get_redis_client())
        self.process_health: dict = {
            "OFFLINE": {"status": "unknown", "timestamp": None},
            "ONLINE": {"status": "unknown", "timestamp": None},
            "COMMAND": {"status": "ok", "timestamp": now_et().isoformat()},
        }
        self._last_reconciliation_date: str | None = None
        self._last_dashboard_refresh: float = 0
        self._last_market_push: float = 0
        self._last_health_check: float = 0
        self._last_heartbeat: float = 0
        self._last_quiet_flush: float = 0
        self._last_health_log: float = 0

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

        # Background thread 2: Command stream reader (durable delivery)
        self._command_thread = threading.Thread(
            target=self._command_stream_reader, daemon=True, name="cmd-commands"
        )
        self._command_thread.start()

        # Background thread 3: Pub/sub for alerts + status (non-critical)
        self._redis_thread = threading.Thread(
            target=self._redis_listener, daemon=True, name="cmd-redis"
        )
        self._redis_thread.start()

        # Background thread 4: Process log forwarder (Live Terminal GUI)
        self._plog_thread = threading.Thread(
            target=self._process_log_forwarder, daemon=True, name="cmd-plog"
        )
        self._plog_thread.start()

        # Background thread 5: Trade outcomes → GUI WebSocket (stream:trade_outcomes)
        self._trade_gui_thread = threading.Thread(
            target=self._trade_outcomes_gui_forwarder, daemon=True, name="cmd-trade-gui"
        )
        self._trade_gui_thread.start()

        # Signal API health gate — orchestrator threads are up
        from captain_command.api import set_orchestrator_ready
        set_orchestrator_ready()
        logger.info("CommandOrchestrator ready — API health gate opened")

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

                # --- PEL recovery: drain pending messages from previous crash ---
                pending = read_pending_stream(
                    STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, "command_1",
                )
                for msg_id, data in pending:
                    logger.info("Recovering pending signal: %s", msg_id)
                    # NOTE: _handle_signal is not fully idempotent today.
                    # Duplicate execution risk is low — the compliance gate
                    # and brokerage API reject duplicate order attempts — and
                    # far preferable to silently losing a signal.
                    self._handle_signal(data)
                    ack_message(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, msg_id)
                if pending:
                    logger.info("Recovered %d pending signal(s) from PEL", len(pending))
                # --- end PEL recovery ---

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

    def _command_stream_reader(self):
        """Read commands from Redis Stream with durable delivery guarantee.

        Mirrors _signal_stream_reader() pattern.  Commands published to
        STREAM_COMMANDS by b1_core_routing and b5_injection_flow are now
        consumed here instead of relying solely on the non-durable pub/sub
        listener.
        """
        backoff = 1
        while self.running:
            try:
                ensure_consumer_group(STREAM_COMMANDS, GROUP_COMMAND_COMMANDS)
                logger.info("Command stream consumer group ready")
                backoff = 1

                # --- PEL recovery: drain pending messages from previous crash ---
                pending = read_pending_stream(
                    STREAM_COMMANDS, GROUP_COMMAND_COMMANDS, "command_1",
                )
                for msg_id, data in pending:
                    logger.info("Recovering pending command: %s", msg_id)
                    self._handle_command(data)
                    ack_message(STREAM_COMMANDS, GROUP_COMMAND_COMMANDS, msg_id)
                if pending:
                    logger.info("Recovered %d pending command(s) from PEL", len(pending))
                # --- end PEL recovery ---

                while self.running:
                    for msg_id, data in read_stream(
                        STREAM_COMMANDS, GROUP_COMMAND_COMMANDS,
                        "command_1", block=2000,
                    ):
                        self._handle_command(data)
                        ack_message(STREAM_COMMANDS, GROUP_COMMAND_COMMANDS, msg_id)

            except Exception as exc:
                if not self.running:
                    return
                logger.error("Command stream error: %s — reconnecting in %ds", exc, backoff)
                if self.running:
                    try:
                        create_incident(
                            "RECONNECT", "P2_HIGH", "COMMAND",
                            f"Command stream reconnecting after: {exc}",
                            notify_fn=lambda n: notify_route(n, gui_push, telegram_bot=self.telegram_bot),
                        )
                    except Exception:
                        pass
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)

    def _redis_listener(self):
        """Subscribe to non-critical pub/sub channels (alerts, status).

        Commands are now primarily read from Redis Streams in
        _command_stream_reader().  CH_COMMANDS remains subscribed here
        for backward compatibility during the transition period.
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

    def _process_log_forwarder(self):
        """Subscribe to process logs from all processes and forward to GUI.

        Runs in a dedicated thread. Each log entry is pushed to all
        connected WebSocket sessions as a ``process_log`` message.
        """
        logger.info("Process log forwarder started")
        backoff = 1

        while self.running:
            try:
                pubsub = get_redis_pubsub()
                pubsub.subscribe(CH_PROCESS_LOGS)
                backoff = 1

                for message in pubsub.listen():
                    if not self.running:
                        return
                    if message["type"] != "message":
                        continue

                    try:
                        entry = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # Forward to all connected GUI users
                    from captain_command.api import _ws_sessions
                    for user_id in list(_ws_sessions.keys()):
                        gui_push(user_id, {"type": "process_log", **entry})

            except Exception as exc:
                logger.error("Process log forwarder error: %s — reconnecting in %ds",
                             exc, backoff)
                if self.running:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)

    def _trade_outcomes_gui_forwarder(self):
        """Consume Redis Stream trade outcomes (separate group from Offline).

        Mirrors ``offline_outcomes`` — publishes ``trade_closed`` to GUI WebSockets.
        """
        logger.info("Trade outcomes GUI forwarder started")
        backoff = 1

        while self.running:
            try:
                ensure_consumer_group(STREAM_TRADE_OUTCOMES, GROUP_COMMAND_GUI_OUTCOMES)
                backoff = 1

                pending = read_pending_stream(
                    STREAM_TRADE_OUTCOMES, GROUP_COMMAND_GUI_OUTCOMES, "command_gui_1",
                )
                for msg_id, data in pending:
                    self._forward_trade_closed_ws(data)
                    ack_message(STREAM_TRADE_OUTCOMES, GROUP_COMMAND_GUI_OUTCOMES, msg_id)
                if pending:
                    logger.info(
                        "Recovered %d pending trade outcome(s) for GUI forwarder",
                        len(pending),
                    )

                while self.running:
                    for msg_id, data in read_stream(
                        STREAM_TRADE_OUTCOMES, GROUP_COMMAND_GUI_OUTCOMES,
                        "command_gui_1", block=2000,
                    ):
                        self._forward_trade_closed_ws(data)
                        ack_message(STREAM_TRADE_OUTCOMES, GROUP_COMMAND_GUI_OUTCOMES, msg_id)

            except Exception as exc:
                if not self.running:
                    return
                logger.error(
                    "Trade outcomes GUI forwarder error: %s — reconnecting in %ds",
                    exc, backoff,
                )
                if self.running:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)

    def _forward_trade_closed_ws(self, data: dict):
        """Push a normalized ``trade_closed`` message to the user's dashboard WS."""
        pair = build_trade_closed_ws_payload(data)
        if pair is None:
            return
        uid, body = pair
        gui_push(uid, body)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def _handle_signal(self, data: dict):
        """Route signal batch from Online B6 to GUI + API (if auto-execute).

        When INSTANCE_PARITY is set (multi-instance mode), each signal
        increments a daily Redis counter. Only signals matching this
        instance's parity are executed; others are shown in GUI as
        PARITY_SKIPPED but still tracked by the shadow monitor for
        theoretical outcome learning.
        """
        user_id = data.get("user_id", "")
        ts = data.get("timestamp", now_et().isoformat())

        update_last_signal_time(ts)

        signals = data.get("signals", [])
        assets = [s.get("asset", "?") for s in signals]
        self.plog.info(
            f"Signal batch received \u2014 {len(signals)} signal(s) for {user_id}: {', '.join(assets)}",
            source="b1_routing",
        )

        # --- Parity filter (multi-instance trade alternation) ---
        instance_parity = os.environ.get("INSTANCE_PARITY", "").strip()
        parity_active = instance_parity in ("0", "1")
        parity_skip = False

        if parity_active:
            parity_skip = self._check_parity_skip(int(instance_parity), data)

        # Auto-execute: route signals directly to TopstepX API adapter
        auto_execute = os.environ.get("AUTO_EXECUTE", "").lower() in ("1", "true", "yes")

        if parity_skip:
            # Parity mismatch — show in GUI but do NOT execute
            api_fn = None
            route_signal_batch(
                payload=data,
                gui_push_fn=gui_push,
                api_route_fn=None,
            )
            # Notify GUI that this signal was parity-skipped
            for signal in data.get("signals", []):
                gui_push(user_id, {
                    "type": "parity_skipped",
                    "signal_id": signal.get("signal_id"),
                    "asset": signal.get("asset"),
                    "message": f"Signal for {signal.get('asset')} assigned to other instance (parity filter)",
                })
        else:
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
                    "auto_executed": auto_execute and not parity_skip,
                    "parity_skipped": parity_skip,
                },
            }, gui_push, telegram_bot=self.telegram_bot)

        logger.debug("Signal routed for user %s at %s (auto_execute=%s, parity_skip=%s)",
                      user_id, ts, auto_execute, parity_skip)

    def _check_parity_skip(self, my_parity: int, data: dict) -> bool:
        """Check if this signal batch should be skipped based on instance parity.

        Uses a daily Redis counter (reset at midnight ET) to deterministically
        assign each signal batch to parity 0 or 1. Both instances see the same
        signals in the same order, so the counter stays synchronized without
        any network connection between them.

        Returns True if this batch should be skipped (parity mismatch).
        """
        today = now_et().strftime("%Y-%m-%d")

        counter_key = f"captain:signal_counter:{today}"
        try:
            client = get_redis_client()
            trade_number = client.incr(counter_key)
            client.expire(counter_key, 86400 * 2)  # TTL: 2 days
        except Exception as exc:
            logger.error("Parity counter failed: %s — defaulting to TAKE", exc)
            return False

        # trade_number starts at 1. Parity 0 takes odd (1,3,5), parity 1 takes even (2,4,6)
        signal_parity = (trade_number - 1) % 2  # 0 for odd, 1 for even
        skip = signal_parity != my_parity

        signals = data.get("signals", [])
        assets = [s.get("asset", "?") for s in signals]
        logger.info("PARITY CHECK: trade_number=%d, signal_parity=%d, my_parity=%d, skip=%s, assets=%s",
                     trade_number, signal_parity, my_parity, skip, assets)

        return skip

    def _auto_execute_signal(self, account_id: str, sanitised_order: dict):
        """Execute a signal immediately via the TopstepX API adapter."""
        from captain_command.blocks.b3_api_adapter import _active_connections

        direction = sanitised_order.get("direction")
        # Translate integer direction from B6 to TopstepX side string
        if direction == 1 or direction == "BUY":
            direction = "BUY"
        elif direction == -1 or direction == "SELL":
            direction = "SELL"
        else:
            logger.info("AUTO-EXECUTE SKIP: direction=%s for %s (no valid direction)",
                        direction, sanitised_order.get("asset"))
            gui_push(sanitised_order.get("user_id", "unknown"), {
                "type": "signal_pending",
                "message": f"Signal for {sanitised_order.get('asset')} awaiting OR breakout direction",
                "order": sanitised_order,
            })
            return
        sanitised_order["direction"] = direction

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

        self.plog.info(
            f"Bracket order: {sanitised_order.get('asset')} {direction} "
            f"x{sanitised_order.get('size')} @ MKT, "
            f"TP={sanitised_order.get('tp')}, SL={sanitised_order.get('sl')}",
            source="b3_api",
        )

        result = adapter.send_signal(sanitised_order)
        status = result.get("status", "UNKNOWN")

        if status == "PLACED":
            logger.info("AUTO-EXECUTE SUCCESS: order_id=%s fill_price=%s",
                        result.get("order_id"), result.get("fill_price"))
            self.plog.info(
                f"Order PLACED: {sanitised_order.get('asset')} {direction} "
                f"x{sanitised_order.get('size')} (order_id={result.get('order_id')}, "
                f"fill={result.get('fill_price')})",
                source="b3_api",
            )
            # Phase 5: log TRADE_TAKEN to p3_session_event_log so the
            # backend `_get_pending_signals` query correctly excludes
            # auto-executed signals on subsequent dashboard refreshes.
            # Without this, only the manual /api/commands route logs the
            # event; auto-execute used to leave the signal floating in
            # the "pending but already taken" limbo state.
            try:
                _log_trade_confirmation(
                    sanitised_order.get("signal_id"),
                    sanitised_order.get("user_id", "unknown"),
                    "TAKEN",
                    {
                        "asset": sanitised_order.get("asset"),
                        "account_id": account_id,
                        "contracts": sanitised_order.get("size"),
                        "actual_entry_price": result.get("fill_price"),
                    },
                )
            except Exception as log_exc:
                logger.error(
                    "Auto-execute TRADE_TAKEN log failed for %s: %s",
                    sanitised_order.get("signal_id"), log_exc,
                )
            gui_push(sanitised_order.get("user_id", "unknown"), {
                "type": "command_ack",
                "command": "AUTO_EXECUTED",
                "order": sanitised_order,
                "result": result,
            })
            publish_to_stream(STREAM_COMMANDS, {
                "type": "TAKEN_SKIPPED",
                "_source": "orchestrator",
                "action": "TAKEN",
                "signal_id": sanitised_order.get("signal_id"),
                "user_id": sanitised_order.get("user_id"),
                "asset": sanitised_order.get("asset"),
                "direction": direction,
                "actual_entry_price": result.get("fill_price"),
                "entry_price": sanitised_order.get("entry_price"),
                "contracts": sanitised_order.get("size", 0),
                "tp_level": sanitised_order.get("tp"),
                "sl_level": sanitised_order.get("sl"),
                "point_value": sanitised_order.get("point_value", 50.0),
                "risk_amount": sanitised_order.get("risk_amount", 0),
                "account_id": account_id,
                "session": sanitised_order.get("session"),
                "regime_state": sanitised_order.get("regime_state"),
                "combined_modifier": sanitised_order.get("combined_modifier"),
                "aim_breakdown": sanitised_order.get("aim_breakdown"),
                "tsm_id": sanitised_order.get("tsm_id"),
                # Phase 3a: forward atomic-bracket flag and entry order id so
                # B7 can later query the exchange for the actual SL/TP fill
                # price (rather than relying on the polled lastPrice as exit).
                "bracket": bool(result.get("bracket", False)),
                "entry_order_id": result.get("entry_order_id") or result.get("order_id"),
            })
        else:
            logger.error("AUTO-EXECUTE FAILED: %s — %s", status, result)
            self.plog.error(
                f"Order FAILED: {sanitised_order.get('asset')} \u2014 {status}",
                source="b3_api",
            )
            gui_push(sanitised_order.get("user_id", "unknown"), {
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
        """Route alert from Redis captain:alerts to GUI + Telegram.

        IMPORTANT: Do NOT call notify_route() here — it publishes back to
        captain:alerts, which would create an infinite feedback loop.
        Instead, push directly to GUI and Telegram.
        """
        priority = data.get("priority", "LOW")
        message = data.get("message", "")
        notif_id = data.get("notif_id", "")
        event_type = data.get("event_type", "")
        asset = data.get("asset", "")
        ts = data.get("timestamp", now_et().isoformat())
        source = data.get("source", "SYSTEM")

        # Push to all connected GUI users
        from captain_command.api import _ws_sessions
        for user_id in list(_ws_sessions.keys()):
            gui_push(user_id, {
                "type": "notification",
                "notif_id": notif_id,
                "priority": priority,
                "event_type": event_type,
                "message": message,
                "source": source,
                "timestamp": ts,
                "asset": asset,
            })

        # Send to Telegram for CRITICAL/HIGH (skip re-publishing to Redis)
        if self.telegram_bot and priority in ("CRITICAL", "HIGH"):
            from captain_command.blocks.b7_notifications import (
                _get_all_active_user_ids,
                _get_telegram_chat_id,
            )
            prefix = {
                "CRITICAL": "\U0001f6a8",
                "HIGH": "\u26a0\ufe0f",
            }.get(priority, "")
            for uid in _get_all_active_user_ids():
                chat_id = _get_telegram_chat_id(uid)
                if chat_id:
                    self.telegram_bot.send_message(
                        chat_id, f"{prefix} {message}", priority,
                    )

    def _handle_status(self, data: dict):
        """Update process health from heartbeat."""
        handle_status_message(data, self.process_health)
        role = data.get("role", "UNKNOWN")
        update_process_health(role, self.process_health.get(role, {}))

        # Relay pipeline stage from Online to GUI
        if data.get("type") == "pipeline_stage" and data.get("stage"):
            stage = data["stage"]
            set_pipeline_stage(stage)
            from captain_command.api import _ws_sessions
            for user_id in list(_ws_sessions.keys()):
                gui_push(user_id, {
                    "type": "pipeline_status",
                    "stage": stage,
                    "timestamp": data.get("timestamp"),
                })

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

        # Log to terminal every 5 minutes (avoids spam)
        now = time.time()
        if now - self._last_health_log >= 300:
            self._last_health_log = now
            statuses = {
                role: info.get("status", "unknown")
                for role, info in self.process_health.items()
            }
            parts = ", ".join(f"{r}={s}" for r, s in statuses.items())
            self.plog.info(f"Health check: {parts}", source="scheduler")

    def _publish_heartbeat(self):
        """Publish Command process heartbeat to Redis."""
        try:
            client = get_redis_client()
            client.publish(CH_STATUS, json.dumps({
                "role": "COMMAND",
                "status": "ok",
                "timestamp": now_et().isoformat(),
                "details": {
                    "api_connections": get_connection_summary(),
                },
            }))
            self.process_health["COMMAND"]["timestamp"] = now_et().isoformat()
        except Exception as exc:
            logger.error("Heartbeat publish failed: %s", exc)

    def _check_reconciliation_trigger(self):
        """Check if it's 19:00 EST and run daily reconciliation."""
        now = now_et()

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
