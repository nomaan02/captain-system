# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — FastAPI application.

Block 1.0: Health endpoint (GET /health).
WebSocket hub for GUI real-time updates.
REST endpoints for commands and validation.

Spec: Program3_Command.md Block 1.0 (lines 34-53), Block 1 (lines 55-161),
      Block 10 (lines 781-877).
"""

import asyncio
import hmac
import json
import logging
import math
import os
import secrets
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from captain_command.blocks.b1_core_routing import (
    route_command,
    route_notification,
    sanitise_for_api,
)
from captain_command.blocks.b10_data_validation import (
    validate_user_input,
    validate_asset_config,
)
from captain_command.blocks.b2_gui_data_server import (
    build_dashboard_snapshot,
    build_system_overview,
    build_processes_status,
    get_aim_detail,
)
from captain_command.blocks.b6_reports import generate_report, REPORT_TYPES
from captain_command.blocks.b7_notifications import (
    save_user_preferences,
    mark_gui_read,
    DEFAULT_PREFERENCES,
    route_notification as notify_route,
)

logger = logging.getLogger(__name__)

# Orchestrator instance — set by main.py before uvicorn.run()
_orchestrator = None


def set_orchestrator(orch):
    """Store the orchestrator so the lifespan shutdown hook can stop it."""
    global _orchestrator
    _orchestrator = orch


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """FastAPI lifespan: captures event loop on startup, stops orchestrator + bot on shutdown."""
    set_event_loop(asyncio.get_running_loop())
    yield
    # Shutdown — runs when uvicorn receives SIGTERM/SIGINT
    logger.info("Lifespan shutdown: stopping orchestrator and telegram bot")
    if _orchestrator:
        _orchestrator.stop()
    if _telegram_bot:
        _telegram_bot.stop()


app = FastAPI(title="Captain Command API", version="1.0.0", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# JWT Authentication (G-002 / DEC-01)
# ---------------------------------------------------------------------------

_JWT_SECRET: str = os.environ.get("JWT_SECRET_KEY", "")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))
_API_SECRET_KEY: str = os.environ.get("API_SECRET_KEY", "")

if not _JWT_SECRET:
    _JWT_SECRET = secrets.token_hex(32)
    logger.warning("JWT_SECRET_KEY not set — using ephemeral key (tokens won't survive restarts)")
if not _API_SECRET_KEY:
    logger.warning("API_SECRET_KEY not set — /auth/token login will be unavailable")

_AUTH_EXEMPT_PATHS = frozenset({
    "/api/health",
    "/api/status",
    "/auth/token",
    "/docs",
    "/openapi.json",
    "/redoc",
})


class _JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer JWT on all HTTP endpoints except exempt paths."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Health, status, login, and docs are public
        if path in _AUTH_EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        # WebSocket auth handled inside the endpoint (query-param token)
        if path.startswith("/ws/"):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid authorization header"},
            )

        token = auth[7:]
        try:
            payload = pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
            request.state.user_id = payload.get("sub", "")
            request.state.token_payload = payload
        except pyjwt.ExpiredSignatureError:
            return JSONResponse(status_code=401, content={"error": "Token expired"})
        except pyjwt.InvalidTokenError:
            return JSONResponse(status_code=401, content={"error": "Invalid token"})

        return await call_next(request)


app.add_middleware(_JWTAuthMiddleware)


# Event-loop capture moved into _lifespan() startup phase.


# ---------------------------------------------------------------------------
# Shared state (set by orchestrator at startup)
# ---------------------------------------------------------------------------

# Process health — updated by status heartbeats
_process_health: dict[str, dict] = {
    "OFFLINE": {"status": "unknown", "timestamp": None},
    "ONLINE": {"status": "unknown", "timestamp": None},
    "COMMAND": {"status": "ok", "timestamp": datetime.now().isoformat()},
}

# API adapter connection status — updated by B3 health monitor
_api_connections: dict[str, dict] = {}

# Start time for uptime calculation
_start_time: float = time.time()

# Last signal time — updated by signal routing
_last_signal_time: str | None = None

# Active WebSocket sessions — user_id → set of WebSocket objects
_ws_sessions: dict[str, set[WebSocket]] = defaultdict(set)
_ws_lock = threading.Lock()

# Max concurrent WebSocket sessions per user. Oldest evicted with code 4001
# (client knows not to reconnect on 4001). Allows for brief overlap during reconnects.
MAX_SESSIONS_PER_USER = 3


# ---------------------------------------------------------------------------
# Block 1.0: Health Endpoint
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    """External health endpoint — monitored every 30 seconds.

    If 3 consecutive failures: external service sends Telegram alert
    to ADMIN directly.  This is the ONLY monitoring path that survives
    a complete Captain system failure.

    Spec: CMD Block 1.0 lines 34-53.
    """
    # Determine aggregate status
    connected_apis = sum(
        1 for ac in _api_connections.values()
        if ac.get("connected", False)
    )
    total_apis = len(_api_connections)

    # Check if any circuit breaker is HALTED
    cb_status = "ACTIVE"
    offline_status = _process_health.get("OFFLINE", {}).get("status", "unknown")
    online_status = _process_health.get("ONLINE", {}).get("status", "unknown")

    if offline_status == "halted" or online_status == "halted":
        cb_status = "HALTED"

    # Aggregate status
    if offline_status == "unknown" and online_status == "unknown":
        overall = "DEGRADED"
    elif offline_status == "error" or online_status == "error":
        overall = "DEGRADED"
    else:
        overall = "OK"

    active_users = len(_ws_sessions)
    uptime = int(time.time() - _start_time)

    return JSONResponse({
        "status": overall,
        "uptime_seconds": uptime,
        "last_signal_time": _last_signal_time,
        "active_users": active_users,
        "circuit_breaker": cb_status,
        "api_connections": {
            "connected": connected_apis,
            "total": total_apis,
        },
        "last_heartbeat": _process_health.get("COMMAND", {}).get("timestamp"),
    })


@app.get("/api/accounts")
async def get_accounts():
    """Return the account list derived from environment variables.

    Each instance reads TOPSTEP_ACCOUNT_NAME from its own .env,
    so this endpoint returns the correct account per deployment.
    """
    account_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")
    trading_env = os.environ.get("TRADING_ENVIRONMENT", "PAPER").upper()
    account_type = "live" if trading_env == "LIVE" else "practice"

    accounts = []
    if account_name:
        accounts.append({
            "id": account_name,
            "label": f"{'Live' if account_type == 'live' else 'Practice'} Account",
            "type": account_type,
        })

    return JSONResponse({"accounts": accounts})


@app.get("/api/status")
async def status():
    """Detailed system status for internal use."""
    return JSONResponse({
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "processes": {
            role: info.get("status", "unknown")
            for role, info in _process_health.items()
        },
        "active_ws_sessions": {
            uid: len(sockets) for uid, sockets in _ws_sessions.items()
        },
        "api_connections": _api_connections,
    })


# ---------------------------------------------------------------------------
# Authentication: Token Issuer
# ---------------------------------------------------------------------------


class _AuthTokenRequest(BaseModel):
    api_key: str
    user_id: str = "primary_user"


@app.post("/auth/token")
def auth_token(req: _AuthTokenRequest):
    """Issue a JWT in exchange for a valid API secret key."""
    if not _API_SECRET_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "Authentication not configured (API_SECRET_KEY not set)"},
        )
    if not hmac.compare_digest(req.api_key, _API_SECRET_KEY):
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid API key"},
        )

    now = datetime.now(timezone.utc)
    payload = {
        "sub": req.user_id,
        "iat": now,
        "exp": now + timedelta(hours=_JWT_EXPIRY_HOURS),
    }
    token = pyjwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)
    return JSONResponse({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": _JWT_EXPIRY_HOURS * 3600,
    })


# ---------------------------------------------------------------------------
# WebSocket hub — GUI real-time updates
# ---------------------------------------------------------------------------


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(default=""),
):
    """WebSocket endpoint for GUI real-time updates.

    Authentication: token query param must be a valid JWT whose ``sub``
    claim matches the ``user_id`` path parameter.

    Session management: new connections are added to the set, and stale
    sessions beyond MAX_SESSIONS_PER_USER are closed immediately.
    Cleanup on disconnect happens in the finally block.
    """
    # Verify JWT token before accepting connection
    if not token:
        await websocket.close(code=4003, reason="Missing authentication token")
        return
    try:
        payload = pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        token_user = payload.get("sub", "")
        if token_user != user_id:
            await websocket.close(code=4003, reason="User ID mismatch")
            return
    except pyjwt.ExpiredSignatureError:
        await websocket.close(code=4003, reason="Token expired")
        return
    except pyjwt.InvalidTokenError:
        await websocket.close(code=4003, reason="Invalid token")
        return

    await websocket.accept()

    # Mutate _ws_sessions under lock — gui_push reads from background threads.
    with _ws_lock:
        sessions = _ws_sessions[user_id]

        # Evict oldest sessions over the limit. Use code 4001 so the client
        # knows NOT to reconnect (normal close codes trigger reconnect).
        stale = []
        while len(sessions) >= MAX_SESSIONS_PER_USER:
            try:
                oldest = next(iter(sessions))
                sessions.discard(oldest)
                stale.append(oldest)
            except StopIteration:
                break

        sessions.add(websocket)
        session_count = len(sessions)

    logger.info("WebSocket connected: user=%s (sessions=%d, evicted=%d)",
                user_id, session_count, len(stale))

    # Close evicted sessions AFTER adding the new one (so the new one is safe)
    for old_ws in stale:
        try:
            await old_ws.close(code=4001)
        except Exception:
            pass

    try:
        await websocket.send_json({"type": "connected", "user_id": user_id})
    except (RuntimeError, WebSocketDisconnect):
        # Client disconnected between accept() and first send — clean up and exit
        with _ws_lock:
            _ws_sessions[user_id].discard(websocket)
            if not _ws_sessions[user_id]:
                _ws_sessions.pop(user_id, None)
        return

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "command":
                data["user_id"] = user_id
                # Remap: GUI sends {type:"command", command:"ACTIVATE_AIM"}
                # but route_command expects {type:"ACTIVATE_AIM"}
                if "command" in data:
                    data["type"] = data["command"]
                route_command(data, gui_push_fn=gui_push)

            elif msg_type == "validate_input":
                result = validate_user_input(
                    data.get("input_type", ""),
                    data.get("value"),
                    data.get("context", {}),
                )
                await websocket.send_json({"type": "validation_result", **result})

            else:
                await websocket.send_json({"type": "echo", "data": data})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket error for user %s: %s", user_id, exc, exc_info=True)
    finally:
        with _ws_lock:
            _ws_sessions[user_id].discard(websocket)
            remaining = len(_ws_sessions[user_id])
            if remaining == 0:
                _ws_sessions.pop(user_id, None)
        logger.info("WebSocket disconnected: user=%s (remaining=%d)",
                    user_id, remaining)


# ---------------------------------------------------------------------------
# GUI push function (used by core routing)
# ---------------------------------------------------------------------------


# Reference to the main asyncio event loop — set by the orchestrator at startup
# so that background threads can schedule coroutines safely.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop):
    """Store the main event loop reference. Called once at startup."""
    global _main_loop
    _main_loop = loop


def _make_json_safe(obj):
    """Recursively sanitise values for JSON serialization.

    Handles datetime → ISO string and NaN/Infinity → null (both are
    invalid in standard JSON and cause browser JSON.parse to fail).
    """
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def gui_push(user_id: str, message: dict):
    """Push a message to all connected WebSocket sessions for a user.

    Non-blocking: schedules sends on the event loop and returns immediately.
    Dead sessions are cleaned up asynchronously when send fails.

    Safe to call from background threads (orchestrator, Redis listener).
    """
    # Snapshot sessions under lock — background threads call gui_push while
    # the event loop mutates _ws_sessions on connect/disconnect.
    with _ws_lock:
        sessions = list(_ws_sessions.get(user_id, set()))
    if not sessions:
        return

    loop = _main_loop
    if loop is None or loop.is_closed():
        return

    message = _make_json_safe(message)

    # Schedule each send as a fire-and-forget coroutine on the event loop.
    # No blocking — the scheduler thread returns immediately.
    for ws in sessions:
        asyncio.run_coroutine_threadsafe(_safe_ws_send(ws, user_id, message), loop)


async def _safe_ws_send(ws: WebSocket, user_id: str, message: dict):
    """Send a message to one WebSocket session. Clean up on failure."""
    try:
        await asyncio.wait_for(ws.send_json(message), timeout=10.0)
    except Exception:
        # Send failed — connection is dead. Remove from set AND close properly
        # so the endpoint coroutine's finally block fires and the coroutine exits.
        with _ws_lock:
            _ws_sessions[user_id].discard(ws)
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# REST: Validation endpoints
# ---------------------------------------------------------------------------


class ValidateInputRequest(BaseModel):
    input_type: str
    value: float
    context: dict[str, Any] = {}


class AssetConfigRequest(BaseModel):
    asset_config: dict[str, Any]


@app.post("/api/validate/input")
def api_validate_input(req: ValidateInputRequest):
    """Validate a user-provided input value (REST alternative to WebSocket)."""
    result = validate_user_input(req.input_type, req.value, req.context)
    return JSONResponse(result)


@app.post("/api/validate/asset-config")
def api_validate_asset_config(req: AssetConfigRequest):
    """Validate an asset configuration for onboarding."""
    result = validate_asset_config(req.asset_config)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# REST: Dashboard & System Overview
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/{user_id}")
def api_dashboard(user_id: str):
    """Full dashboard snapshot for a user (REST fallback for WebSocket).

    Sync def — FastAPI runs this in a thread pool so the blocking
    QuestDB queries inside build_dashboard_snapshot() do NOT freeze
    the uvicorn event loop (which would stall all WebSocket sends).
    """
    return JSONResponse(_make_json_safe(build_dashboard_snapshot(user_id)))


@app.get("/api/aim/{aim_id}/detail")
def api_aim_detail(aim_id: int):
    """AIM detail for the registry modal — per-asset breakdown + validation."""
    return JSONResponse(_make_json_safe(get_aim_detail(aim_id)))


@app.post("/api/aim/{aim_id}/activate")
def api_aim_activate(aim_id: int):
    """Activate an AIM — routes ACTIVATE_AIM command to Offline via Redis."""
    route_command(
        {"type": "ACTIVATE_AIM", "aim_id": aim_id, "user_id": "primary_user"},
        gui_push_fn=lambda *_a, **_kw: None,
    )
    return JSONResponse({"ok": True, "aim_id": aim_id, "action": "ACTIVATE_AIM"})


@app.post("/api/aim/{aim_id}/deactivate")
def api_aim_deactivate(aim_id: int):
    """Deactivate (suppress) an AIM — routes DEACTIVATE_AIM command to Offline."""
    route_command(
        {"type": "DEACTIVATE_AIM", "aim_id": aim_id, "user_id": "primary_user"},
        gui_push_fn=lambda *_a, **_kw: None,
    )
    return JSONResponse({"ok": True, "aim_id": aim_id, "action": "DEACTIVATE_AIM"})


@app.get("/api/system-overview")
def api_system_overview():
    """System Overview — ADMIN only."""
    return JSONResponse(_make_json_safe(build_system_overview()))


# ---------------------------------------------------------------------------
# REST: Process Monitoring
# ---------------------------------------------------------------------------


@app.get("/api/processes/status")
def api_processes_status():
    """Process monitoring for the Processes tab — aggregates block registry,
    process health, locked strategies, and API connections."""
    return JSONResponse(_make_json_safe(
        build_processes_status(_process_health, _api_connections)
    ))


# ---------------------------------------------------------------------------
# REST: Reports
# ---------------------------------------------------------------------------


class ReportRequest(BaseModel):
    report_type: str
    user_id: str
    params: dict[str, Any] = {}


@app.get("/api/reports/types")
async def api_report_types():
    """List available report types."""
    return JSONResponse(REPORT_TYPES)


@app.post("/api/reports/generate")
def api_generate_report(req: ReportRequest):
    """Generate a report."""
    result = generate_report(req.report_type, req.user_id, req.params)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Helpers for orchestrator to update shared state
# ---------------------------------------------------------------------------


def update_process_health(role: str, info: dict):
    """Called by orchestrator when a status heartbeat arrives."""
    _process_health[role] = info


def update_api_connections(connections: dict):
    """Called by B3 health monitor."""
    global _api_connections
    _api_connections = connections


def update_last_signal_time(ts: str):
    """Called by signal router when a new signal batch arrives."""
    global _last_signal_time
    _last_signal_time = ts


# Telegram bot instance — set by main.py after bot creation
_telegram_bot = None


def set_telegram_bot(bot):
    """Store the Telegram bot so API endpoints can use it."""
    global _telegram_bot
    _telegram_bot = bot


# ---------------------------------------------------------------------------
# REST: Notification Preferences (Phase 6)
# ---------------------------------------------------------------------------


class NotificationPrefsRequest(BaseModel):
    user_id: str
    preferences: dict[str, Any]


class NotificationReadRequest(BaseModel):
    notif_id: str
    user_id: str


class TestNotificationRequest(BaseModel):
    user_id: str
    event_type: str = "SYSTEM_STATUS"
    priority: str = "HIGH"
    message: str = "Test notification from Captain."


@app.get("/api/notifications/preferences/{user_id}")
def api_get_notification_prefs(user_id: str):
    """Get notification preferences for a user."""
    from captain_command.blocks.b7_notifications import _get_user_preferences
    prefs = _get_user_preferences(user_id)
    return JSONResponse(prefs)


@app.post("/api/notifications/preferences")
def api_save_notification_prefs(req: NotificationPrefsRequest):
    """Save notification preferences for a user."""
    save_user_preferences(req.user_id, req.preferences)
    return JSONResponse({"status": "ok", "user_id": req.user_id})


@app.post("/api/notifications/read")
def api_mark_notification_read(req: NotificationReadRequest):
    """Mark a GUI notification as read."""
    mark_gui_read(req.notif_id, req.user_id)
    return JSONResponse({"status": "ok"})


@app.post("/api/notifications/test")
def api_test_notification(req: TestNotificationRequest):
    """Send a test notification to all channels (ADMIN only, spec §8.5)."""
    notify_route({
        "event_type": req.event_type,
        "priority": req.priority,
        "message": req.message,
        "user_id": req.user_id,
    }, gui_push, telegram_bot=_telegram_bot)
    return JSONResponse({"status": "sent", "user_id": req.user_id})


@app.get("/api/notifications/telegram-history")
def api_telegram_history(limit: int = 50):
    """Fetch recent Telegram-delivered notifications from D10."""
    from shared.questdb_client import get_cursor

    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT notification_id, user_id, priority, event_type,
                          asset, message, ts
                   FROM p3_d10_notification_log
                   WHERE telegram_delivered = true
                   ORDER BY ts DESC
                   LIMIT %s""",
                (min(limit, 200),),
            )
            rows = cur.fetchall()
            items = []
            for r in rows:
                items.append({
                    "notif_id": r[0],
                    "user_id": r[1],
                    "priority": r[2],
                    "event_type": r[3],
                    "asset": r[4],
                    "message": r[5],
                    "timestamp": r[6].isoformat() if r[6] else None,
                })
            return JSONResponse({"items": items, "count": len(items)})
    except Exception as exc:
        logger.error("Telegram history query failed: %s", exc)
        return JSONResponse({"items": [], "count": 0, "error": "Failed to fetch notification history"})


# ---------------------------------------------------------------------------
# REST: Session Replay (Block 11)
# ---------------------------------------------------------------------------


class ReplayStartRequest(BaseModel):
    date: str
    sessions: list[str] | None = None
    session: str | None = None  # Backward compat -- use sessions instead
    config_overrides: dict = {}
    speed: float = 1.0

    @property
    def resolved_sessions(self) -> list[str]:
        if self.sessions is not None:
            return self.sessions
        if self.session is not None:
            return [self.session]
        return ["NY"]


class ReplayControlRequest(BaseModel):
    action: str  # pause, resume, speed, skip_to_next, stop
    value: float | None = None


class ReplaySaveRequest(BaseModel):
    replay_id: str
    user_id: str = "primary_user"


class ReplayPresetRequest(BaseModel):
    name: str
    config: dict
    user_id: str = "primary_user"


@app.post("/api/replay/start")
def api_replay_start(req: ReplayStartRequest):
    """Start a session replay. Returns replay_id.

    Sync def -- FastAPI runs this in a thread pool so the blocking
    replay_engine calls do NOT freeze the uvicorn event loop.
    """
    try:
        from captain_command.blocks.b11_replay_runner import start_replay
        replay_id = start_replay(
            user_id="primary_user",
            date_str=req.date,
            sessions=req.resolved_sessions,
            config_overrides=req.config_overrides,
            speed=req.speed,
            gui_push_fn=gui_push,
        )
        return JSONResponse({"replay_id": replay_id})
    except Exception as exc:
        logger.error("Replay start failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


class BatchReplayStartRequest(BaseModel):
    date_from: str
    date_to: str
    sessions: list[str] = ["NY"]
    config_overrides: dict = {}
    speed: float = 1.0


@app.post("/api/replay/batch/start")
def api_batch_replay_start(req: BatchReplayStartRequest):
    """Start a batch (period) replay over a date range. Returns replay_id."""
    try:
        from captain_command.blocks.b11_replay_runner import start_batch_replay
        replay_id = start_batch_replay(
            user_id="primary_user",
            date_from=req.date_from,
            date_to=req.date_to,
            sessions=req.sessions,
            config_overrides=req.config_overrides,
            speed=req.speed,
            gui_push_fn=gui_push,
        )
        return JSONResponse({"replay_id": replay_id, "mode": "batch"})
    except Exception as exc:
        logger.error("Batch replay start failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.post("/api/replay/control")
def api_replay_control(req: ReplayControlRequest):
    """Control an active replay: pause, resume, speed, skip_to_next, stop."""
    try:
        from captain_command.blocks.b11_replay_runner import control_replay
        result = control_replay("primary_user", req.action, req.value)
        return JSONResponse(result)
    except Exception as exc:
        logger.error("Replay control failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.post("/api/replay/save")
def api_replay_save(req: ReplaySaveRequest):
    """Save replay results to p3_replay_results."""
    try:
        from captain_command.blocks.b11_replay_runner import save_replay
        result = save_replay(req.replay_id, req.user_id)
        return JSONResponse(result)
    except Exception as exc:
        logger.error("Replay save failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.get("/api/replay/status")
def api_replay_status():
    """Get the status of the active replay for primary_user."""
    try:
        from captain_command.blocks.b11_replay_runner import get_active_replay
        result = get_active_replay("primary_user")
        if result is None:
            return JSONResponse({"status": "no_active_replay"})
        return JSONResponse(result)
    except Exception as exc:
        logger.error("Replay status failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.get("/api/replay/history")
def api_replay_history():
    """List saved replay results (most recent first, limit 50)."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """SELECT replay_id, user_id, replay_date, session_type,
                          summary, created
                   FROM p3_replay_results
                   ORDER BY ts DESC LIMIT 50"""
            )
            rows = cur.fetchall()
        results = []
        for r in rows:
            summary = {}
            if r[4]:
                try:
                    summary = json.loads(r[4]) if isinstance(r[4], str) else r[4]
                except (json.JSONDecodeError, TypeError):
                    summary = {}
            results.append({
                "replay_id": r[0],
                "user_id": r[1],
                "replay_date": r[2],
                "session_type": r[3],
                "summary": summary,
                "created": r[5],
            })
        return JSONResponse({"replays": results})
    except Exception as exc:
        logger.error("Replay history failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.get("/api/replay/presets")
def api_replay_presets():
    """List saved replay presets for primary_user."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """SELECT preset_id, name, config, ts
                   FROM p3_replay_presets
                   WHERE user_id = 'primary_user'
                   ORDER BY ts DESC"""
            )
            rows = cur.fetchall()
        presets = []
        for r in rows:
            config = {}
            if r[2]:
                try:
                    config = json.loads(r[2]) if isinstance(r[2], str) else r[2]
                except (json.JSONDecodeError, TypeError):
                    config = {}
            presets.append({
                "preset_id": r[0],
                "name": r[1],
                "config": config,
                "created": r[3],
            })
        return JSONResponse({"presets": presets})
    except Exception as exc:
        logger.error("Replay presets fetch failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.post("/api/replay/presets")
def api_replay_preset_save(req: ReplayPresetRequest):
    """Save a replay configuration preset."""
    try:
        import uuid as _uuid
        from shared.questdb_client import get_cursor
        preset_id = f"PRESET-{_uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_replay_presets(
                       preset_id, user_id, name, config, ts
                   ) VALUES(%s, %s, %s, %s, %s)""",
                (preset_id, req.user_id, req.name, json.dumps(req.config), now),
            )
        return JSONResponse({
            "status": "saved",
            "preset_id": preset_id,
            "name": req.name,
        })
    except Exception as exc:
        logger.error("Replay preset save failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})


@app.post("/api/replay/whatif")
def api_replay_whatif(req: ReplayStartRequest):
    """Rerun sizing with different config using cached bars from last replay.

    No API calls needed -- uses bars cached during the last replay run.
    """
    try:
        from captain_command.blocks.b11_replay_runner import run_whatif as do_whatif
        result = do_whatif("primary_user", req.config_overrides)
        return JSONResponse(_make_json_safe(result))
    except Exception as exc:
        logger.error("Replay what-if failed: %s", exc, exc_info=True)
        return JSONResponse({"error": "Internal server error"})
