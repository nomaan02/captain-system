# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command -- Block 11: Session Replay Runner.

Manages replay sessions as background threads, streaming events to the
GUI via WebSocket (gui_push).  Supports pause/resume, speed control,
skip-to-next-event, and what-if reruns.

Depends on: shared/replay_engine.py (load_replay_config, run_replay, run_whatif)
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime, date

from shared.journal import write_checkpoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Replay session class
# ---------------------------------------------------------------------------

class ReplaySession:
    """Manages a single replay execution in a background thread."""

    def __init__(self, replay_id, user_id, config, target_date, speed, gui_push_fn):
        self.replay_id = replay_id
        self.user_id = user_id
        self.config = config
        self.target_date = target_date
        self.speed = speed
        self.gui_push_fn = gui_push_fn

        self._pause_event = threading.Event()
        self._pause_event.set()  # Start unpaused
        self._stop_flag = False
        self._skip_flag = False
        self._thread = None
        self._results = None
        self._cached_bars = None
        self._status = "pending"
        self._error = None
        self._started_at = None
        self._finished_at = None

    def start(self):
        """Start replay in background thread."""
        self._status = "running"
        self._started_at = datetime.now().isoformat()
        self._thread = threading.Thread(
            target=self._run,
            name=f"replay-{self.replay_id}",
            daemon=True,
        )
        self._thread.start()

    def pause(self):
        """Pause tick streaming."""
        self._pause_event.clear()
        self._status = "paused"
        logger.info("Replay %s paused", self.replay_id)

    def resume(self):
        """Resume tick streaming."""
        self._pause_event.set()
        self._status = "running"
        logger.info("Replay %s resumed", self.replay_id)

    def set_speed(self, speed: float):
        """Change playback speed."""
        self.speed = max(0.1, min(speed, 100.0))
        logger.info("Replay %s speed set to %.1fx", self.replay_id, self.speed)

    def skip_to_next(self):
        """Skip to next breakout/exit/error event."""
        self._skip_flag = True
        # Also resume if paused so we don't get stuck
        self._pause_event.set()

    def stop(self):
        """Stop and clean up."""
        self._stop_flag = True
        self._pause_event.set()  # Unblock if paused so thread can exit
        self._status = "stopped"
        logger.info("Replay %s stopped", self.replay_id)

    def get_status(self) -> dict:
        """Return current status of this replay."""
        return {
            "replay_id": self.replay_id,
            "user_id": self.user_id,
            "status": self._status,
            "speed": self.speed,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "error": self._error,
            "has_results": self._results is not None,
        }

    def _run(self):
        """Main thread function -- calls replay_engine.run_replay with on_event callback."""
        from shared.replay_engine import run_replay

        write_checkpoint(
            "COMMAND", "REPLAY_START", "starting", "run_replay",
            {"replay_id": self.replay_id, "user_id": self.user_id},
        )

        # Event types that are "significant" -- skip_to_next skips tick-level
        # sleeps until one of these arrives.
        _significant_events = {"breakout", "exit", "error", "replay_complete"}

        def on_event(event):
            """Callback invoked by replay_engine at each step."""
            if self._stop_flag:
                return

            event_type = event.get("event", "")
            event_data = event.get("data", {})

            # Push to GUI via WebSocket
            self.gui_push_fn(self.user_id, {
                "type": "replay_tick",
                "replay_id": self.replay_id,
                "event": event_type,
                **event_data,
            })

            # Clear skip flag when we hit a significant event
            if event_type in _significant_events:
                self._skip_flag = False

            # For non-significant events (bar-level ticks, config_loaded, etc.),
            # add a sleep between events to simulate real-time playback.
            # Skip the sleep if skip_to_next is active.
            if event_type not in _significant_events and not self._skip_flag:
                sleep_duration = 0.5 / max(self.speed, 0.1)
                # Sleep in small increments to allow pause/stop to interrupt
                elapsed = 0.0
                while elapsed < sleep_duration:
                    if self._stop_flag:
                        return
                    # Check pause -- blocks until resumed
                    self._pause_event.wait(timeout=0.1)
                    if not self._pause_event.is_set():
                        continue  # Still paused, keep waiting
                    elapsed += 0.1

        try:
            result = run_replay(
                config=self.config,
                target_date=self.target_date,
                on_event=on_event,
            )

            self._results = result
            self._cached_bars = result.get("cached_bars", {})
            self._status = "complete"
            self._finished_at = datetime.now().isoformat()

            write_checkpoint(
                "COMMAND", "REPLAY_COMPLETE", "run_replay", "idle",
                {
                    "replay_id": self.replay_id,
                    "total_pnl": result.get("total_pnl", 0),
                    "trades": len(result.get("trades_taken", [])),
                },
            )

        except Exception as exc:
            self._status = "error"
            self._error = str(exc)
            self._finished_at = datetime.now().isoformat()
            logger.error("Replay %s failed: %s", self.replay_id, exc, exc_info=True)

            # Push error to GUI
            self.gui_push_fn(self.user_id, {
                "type": "replay_tick",
                "replay_id": self.replay_id,
                "event": "error",
                "error": str(exc),
            })

            write_checkpoint(
                "COMMAND", "REPLAY_ERROR", "run_replay", "idle",
                {"replay_id": self.replay_id, "error": str(exc)},
            )


# ---------------------------------------------------------------------------
# Module-level session manager
# ---------------------------------------------------------------------------

_active_sessions: dict[str, ReplaySession] = {}
_lock = threading.Lock()


def start_replay(user_id, date_str, session, config_overrides, speed, gui_push_fn) -> str:
    """Start a new replay. Returns replay_id. Stops any existing replay for this user."""
    from shared.replay_engine import load_replay_config

    # Stop existing replay for this user
    with _lock:
        for rid, rs in list(_active_sessions.items()):
            if rs.user_id == user_id and rs._status in ("running", "paused", "pending"):
                rs.stop()

    # Parse target date
    try:
        target_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.")

    # Load config with overrides
    config = load_replay_config(config_overrides or {})

    # Override TP/SL multiples if provided at top level
    if "tp_multiple" in (config_overrides or {}):
        for asset_strat in config.get("strategies", {}).values():
            asset_strat["tp_multiple"] = config_overrides["tp_multiple"]
    if "sl_multiple" in (config_overrides or {}):
        for asset_strat in config.get("strategies", {}).values():
            asset_strat["sl_multiple"] = config_overrides["sl_multiple"]

    replay_id = uuid.uuid4().hex[:12]

    rs = ReplaySession(
        replay_id=replay_id,
        user_id=user_id,
        config=config,
        target_date=target_date,
        speed=speed,
        gui_push_fn=gui_push_fn,
    )

    with _lock:
        _active_sessions[replay_id] = rs

    rs.start()

    logger.info(
        "Replay started: id=%s user=%s date=%s speed=%.1f",
        replay_id, user_id, date_str, speed,
    )

    return replay_id


def control_replay(user_id, action, value=None) -> dict:
    """Control active replay: pause, resume, speed, skip_to_next, stop."""
    rs = _get_user_session(user_id)
    if rs is None:
        return {"error": f"No active replay for user {user_id}"}

    if action == "pause":
        rs.pause()
    elif action == "resume":
        rs.resume()
    elif action == "speed":
        if value is None:
            return {"error": "Speed value required"}
        rs.set_speed(float(value))
    elif action == "skip_to_next":
        rs.skip_to_next()
    elif action == "stop":
        rs.stop()
    else:
        return {"error": f"Unknown action: {action}"}

    return {"status": "ok", "action": action, **rs.get_status()}


def get_active_replay(user_id) -> dict | None:
    """Get status of active replay."""
    rs = _get_user_session(user_id)
    if rs is None:
        return None
    return rs.get_status()


def save_replay(replay_id, user_id) -> dict:
    """Save replay results to p3_replay_results."""
    from shared.questdb_client import get_cursor

    with _lock:
        rs = _active_sessions.get(replay_id)

    if rs is None:
        return {"error": f"Replay {replay_id} not found"}

    if rs._results is None:
        return {"error": f"Replay {replay_id} has no results (status: {rs._status})"}

    results = rs._results
    now = datetime.now().isoformat()

    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_replay_results(
                       replay_id, user_id, replay_date, session_type,
                       config, results, summary, comparison,
                       created, ts
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    replay_id,
                    user_id,
                    rs.target_date.isoformat() if rs.target_date else "",
                    "NY",  # Primary session
                    json.dumps(_safe_config(rs.config)),
                    json.dumps(results.get("results", []), default=str),
                    json.dumps(results.get("summary", {}), default=str),
                    "",  # comparison filled by what-if
                    now,
                    now,
                ),
            )
        logger.info("Replay %s saved to p3_replay_results", replay_id)
        return {"status": "saved", "replay_id": replay_id}
    except Exception as exc:
        logger.error("Failed to save replay %s: %s", replay_id, exc, exc_info=True)
        return {"error": f"Save failed: {exc}"}


def run_whatif(user_id, config_overrides) -> dict:
    """Rerun sizing with different config using cached bars from last replay."""
    from shared.replay_engine import load_replay_config
    from shared.replay_engine import run_whatif as engine_whatif

    # Find the most recent completed replay for this user
    rs = _get_user_session(user_id, include_complete=True)

    if rs is None:
        return {"error": "No replay found. Run a replay first."}

    if rs._cached_bars is None or rs._results is None:
        return {"error": f"Replay {rs.replay_id} has no cached data (status: {rs._status})"}

    # Load fresh config with overrides
    config = load_replay_config(config_overrides or {})

    # Override TP/SL multiples if provided at top level
    if "tp_multiple" in (config_overrides or {}):
        for asset_strat in config.get("strategies", {}).values():
            asset_strat["tp_multiple"] = config_overrides["tp_multiple"]
    if "sl_multiple" in (config_overrides or {}):
        for asset_strat in config.get("strategies", {}).values():
            asset_strat["sl_multiple"] = config_overrides["sl_multiple"]

    try:
        result = engine_whatif(
            config=config,
            cached_bars=rs._cached_bars,
            original_results=rs._results,
            target_date=rs.target_date,
        )
        return result
    except Exception as exc:
        logger.error("What-if failed: %s", exc, exc_info=True)
        return {"error": f"What-if failed: {exc}"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_user_session(user_id, include_complete=False) -> ReplaySession | None:
    """Find the most recent replay session for a user."""
    with _lock:
        # Prefer running/paused sessions
        for rs in reversed(list(_active_sessions.values())):
            if rs.user_id == user_id and rs._status in ("running", "paused"):
                return rs
        # Fall back to complete sessions if requested
        if include_complete:
            for rs in reversed(list(_active_sessions.values())):
                if rs.user_id == user_id and rs._status == "complete":
                    return rs
    return None


def _safe_config(config: dict) -> dict:
    """Strip non-serializable or bulky internals from config for storage."""
    safe = {}
    for key, value in config.items():
        if key.startswith("_"):
            continue
        if key in ("session_config", "asset_session_map"):
            continue  # Static, no need to store
        if isinstance(value, dict) and len(str(value)) > 5000:
            safe[key] = f"<{len(value)} entries>"
        else:
            safe[key] = value
    return safe
