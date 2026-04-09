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

    def __init__(self, replay_id, user_id, config, target_date, speed, gui_push_fn, sessions=None):
        self.replay_id = replay_id
        self.user_id = user_id
        self.config = config
        self.target_date = target_date
        self.speed = speed
        self.gui_push_fn = gui_push_fn
        self.sessions = sessions

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
                sessions=self.sessions,
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


def start_replay(user_id, date_str, sessions, config_overrides, speed, gui_push_fn) -> str:
    """Start a new replay. Returns replay_id. Stops any existing replay for this user."""
    from shared.replay_engine import load_replay_config

    # Stop existing replay for this user and clean up completed sessions
    with _lock:
        for rid, rs in list(_active_sessions.items()):
            if rs.user_id == user_id:
                if rs._status in ("running", "paused", "pending"):
                    rs.stop()
                if rs._status in ("complete", "error", "stopped"):
                    del _active_sessions[rid]

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
        sessions=sessions,
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
                    ",".join(rs.sessions) if rs.sessions else "ALL",
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
            sessions=rs.sessions,
        )
        return result
    except Exception as exc:
        logger.error("What-if failed: %s", exc, exc_info=True)
        return {"error": f"What-if failed: {exc}"}


# ---------------------------------------------------------------------------
# Batch (period) replay
# ---------------------------------------------------------------------------


class BatchReplaySession:
    """Manages a multi-day batch replay in a background thread."""

    def __init__(self, replay_id, user_id, config, dates, sessions, speed, gui_push_fn):
        self.replay_id = replay_id
        self.user_id = user_id
        self.config = config
        self.dates = dates                # list[date] -- weekdays only
        self.sessions = sessions          # list[str]
        self.speed = speed
        self.gui_push_fn = gui_push_fn

        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_flag = False
        self._thread = None
        self._status = "pending"
        self._error = None
        self._started_at = None
        self._finished_at = None

        self.day_results = []
        self._current_day_idx = 0
        self._cached_bars = None
        self._results = None
        # target_date is the last date in the range (for compat with _get_user_session)
        self.target_date = dates[-1] if dates else None

    def start(self):
        self._status = "running"
        self._started_at = datetime.now().isoformat()
        self._thread = threading.Thread(
            target=self._run, name=f"batch-{self.replay_id}", daemon=True
        )
        self._thread.start()

    def pause(self):
        self._pause_event.clear()
        self._status = "paused"
        logger.info("Batch %s paused", self.replay_id)

    def resume(self):
        self._pause_event.set()
        self._status = "running"
        logger.info("Batch %s resumed", self.replay_id)

    def set_speed(self, speed):
        self.speed = max(0.1, min(speed, 100.0))
        logger.info("Batch %s speed set to %.1fx", self.replay_id, self.speed)

    def skip_to_next(self):
        self._pause_event.set()

    def stop(self):
        self._stop_flag = True
        self._pause_event.set()
        self._status = "stopped"
        logger.info("Batch %s stopped", self.replay_id)

    def get_status(self) -> dict:
        return {
            "replay_id": self.replay_id,
            "user_id": self.user_id,
            "status": self._status,
            "speed": self.speed,
            "total_days": len(self.dates),
            "completed_days": len(self.day_results),
            "current_day": self.dates[self._current_day_idx].isoformat()
                if self._current_day_idx < len(self.dates) else None,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "error": self._error,
            "has_results": len(self.day_results) > 0,
        }

    def _run(self):
        from shared.replay_engine import run_replay

        write_checkpoint(
            "COMMAND", "BATCH_REPLAY_START", "starting", "batch_replay",
            {"replay_id": self.replay_id, "total_days": len(self.dates)},
        )

        self.gui_push_fn(self.user_id, {
            "type": "batch_started",
            "replay_id": self.replay_id,
            "total_days": len(self.dates),
            "dates": [d.isoformat() for d in self.dates],
            "sessions": self.sessions,
        })

        for idx, target_date in enumerate(self.dates):
            if self._stop_flag:
                break

            self._pause_event.wait()
            if self._stop_flag:
                break

            self._current_day_idx = idx
            date_str = target_date.isoformat()

            self.gui_push_fn(self.user_id, {
                "type": "batch_day_started",
                "replay_id": self.replay_id,
                "date": date_str,
                "day_index": idx,
                "total_days": len(self.dates),
            })

            def on_event(event, _date=date_str):
                if self._stop_flag:
                    return
                event_data = event.get("data", {})
                self.gui_push_fn(self.user_id, {
                    "type": "replay_tick",
                    "replay_id": self.replay_id,
                    "event": event.get("event", ""),
                    "batch_date": _date,
                    **event_data,
                })
                # Minimal speed delay for batch mode
                evt = event.get("event", "")
                if evt not in ("breakout", "exit", "error", "replay_complete",
                               "config_loaded", "auth_complete"):
                    time.sleep(0.1 / max(self.speed, 1))

            try:
                result = run_replay(
                    config=self.config,
                    target_date=target_date,
                    on_event=on_event,
                    sessions=self.sessions,
                )

                summary = result.get("summary", {})
                if isinstance(summary, str):
                    summary = {}

                day_record = {
                    "date": date_str,
                    "sessions": self.sessions,
                    "trades": summary.get("trades_taken", 0) if isinstance(summary, dict) else 0,
                    "wins": summary.get("wins", 0) if isinstance(summary, dict) else 0,
                    "losses": summary.get("losses", 0) if isinstance(summary, dict) else 0,
                    "pnl": result.get("total_pnl", 0),
                    "errors": len(result.get("errors", [])),
                }

            except Exception as exc:
                day_record = {
                    "date": date_str,
                    "sessions": self.sessions,
                    "trades": 0, "wins": 0, "losses": 0, "pnl": 0,
                    "errors": 1, "error": str(exc),
                }
                logger.error("Batch day %s failed: %s", date_str, exc, exc_info=True)

            self.day_results.append(day_record)
            cum_pnl = sum(d["pnl"] for d in self.day_results)
            day_record["cumulative_pnl"] = round(cum_pnl, 2)

            self.gui_push_fn(self.user_id, {
                "type": "batch_day_completed",
                "replay_id": self.replay_id,
                "date": date_str,
                "day_index": idx,
                "total_days": len(self.dates),
                "day_pnl": round(day_record["pnl"], 2),
                "cumulative_pnl": day_record["cumulative_pnl"],
                "day_trades": day_record["trades"],
                "day_wins": day_record["wins"],
                "day_losses": day_record["losses"],
            })

        # Compute and send overall summary
        batch_summary = self._compute_batch_summary()
        self._status = "complete"
        self._finished_at = datetime.now().isoformat()
        self._results = {"day_results": self.day_results, "summary": batch_summary}

        self.gui_push_fn(self.user_id, {
            "type": "batch_complete",
            "replay_id": self.replay_id,
            "summary": batch_summary,
            "day_results": [
                {k: v for k, v in d.items() if k != "results"}
                for d in self.day_results
            ],
        })

        write_checkpoint(
            "COMMAND", "BATCH_REPLAY_COMPLETE", "batch_replay", "idle",
            {"replay_id": self.replay_id, "total_pnl": batch_summary.get("total_pnl", 0),
             "total_days": len(self.day_results)},
        )

    def _compute_batch_summary(self) -> dict:
        days = self.day_results
        if not days:
            return {}
        total_pnl = sum(d["pnl"] for d in days)
        total_trades = sum(d["trades"] for d in days)
        total_wins = sum(d["wins"] for d in days)
        total_losses = sum(d["losses"] for d in days)
        pnls = [d["pnl"] for d in days]

        peak = 0
        max_dd = 0
        cum = 0
        for p in pnls:
            cum += p
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        return {
            "total_pnl": round(total_pnl, 2),
            "total_trades": total_trades,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "win_rate": round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,
            "best_day": round(max(pnls), 2) if pnls else 0,
            "worst_day": round(min(pnls), 2) if pnls else 0,
            "avg_daily_pnl": round(total_pnl / len(days), 2) if days else 0,
            "max_drawdown": round(max_dd, 2),
            "total_days": len(days),
            "profitable_days": sum(1 for p in pnls if p > 0),
            "losing_days": sum(1 for p in pnls if p < 0),
        }


def start_batch_replay(user_id, date_from, date_to, sessions, config_overrides, speed, gui_push_fn) -> str:
    """Start a batch (period) replay. Returns replay_id."""
    from datetime import timedelta
    from shared.replay_engine import load_replay_config

    # Stop existing replay for this user and clean up completed sessions
    with _lock:
        for rid, rs in list(_active_sessions.items()):
            if rs.user_id == user_id:
                if rs._status in ("running", "paused", "pending"):
                    rs.stop()
                if rs._status in ("complete", "error", "stopped"):
                    del _active_sessions[rid]

    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format: {e}")

    if d_from > d_to:
        raise ValueError(f"date_from ({date_from}) must be <= date_to ({date_to})")

    # Generate weekday dates
    dates = []
    current = d_from
    while current <= d_to:
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current)
        current += timedelta(days=1)

    if not dates:
        raise ValueError(f"No weekdays in range {date_from} to {date_to}")

    if len(dates) > 60:
        raise ValueError(f"Too many days ({len(dates)}). Max 60 weekdays per batch.")

    # Load config once
    config = load_replay_config(config_overrides or {})

    if "tp_multiple" in (config_overrides or {}):
        for asset_strat in config.get("strategies", {}).values():
            asset_strat["tp_multiple"] = config_overrides["tp_multiple"]
    if "sl_multiple" in (config_overrides or {}):
        for asset_strat in config.get("strategies", {}).values():
            asset_strat["sl_multiple"] = config_overrides["sl_multiple"]

    replay_id = uuid.uuid4().hex[:12]

    batch = BatchReplaySession(
        replay_id=replay_id,
        user_id=user_id,
        config=config,
        dates=dates,
        sessions=sessions,
        speed=speed,
        gui_push_fn=gui_push_fn,
    )

    with _lock:
        _active_sessions[replay_id] = batch

    batch.start()

    logger.info(
        "Batch replay started: id=%s user=%s dates=%s..%s days=%d speed=%.1f",
        replay_id, user_id, date_from, date_to, len(dates), speed,
    )

    return replay_id


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
