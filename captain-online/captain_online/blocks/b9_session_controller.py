# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""B9 Session Controller — P3-PG-20 session scheduling and asset routing.

Centralises session schedule, asset-to-session mapping, and session-open
detection that was previously inline in the orchestrator.

Source of truth: config/session_registry.json (loaded once, cached).
Fallback: hardcoded defaults matching constants.SESSION_IDS.
"""

import json
import logging
import os
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from shared.constants import SESSION_IDS, SYSTEM_TIMEZONE

_ET = ZoneInfo(SYSTEM_TIMEZONE)
logger = logging.getLogger(__name__)

# Tolerance window for session detection (minutes)
SESSION_WINDOW_MINUTES = int(os.environ.get("SESSION_WINDOW_MINUTES", "2"))

# ---------------------------------------------------------------------------
# Registry loading (cached)
# ---------------------------------------------------------------------------

_registry_cache: dict | None = None


def _load_registry() -> dict:
    """Load session_registry.json (cached after first load)."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    paths = [
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "session_registry.json",
        Path("/captain/config/session_registry.json"),
    ]
    for p in paths:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                _registry_cache = json.load(f)
            logger.info("Session registry loaded from %s", p)
            return _registry_cache

    logger.warning("session_registry.json not found — using defaults")
    _registry_cache = {
        "sessions": {
            "NY": {"or_start": "09:30", "or_end": "09:35"},
            "LON": {"or_start": "03:00", "or_end": "03:05"},
            "APAC": {"or_start": "18:00", "or_end": "18:05"},
        },
        "asset_session_map": {},
    }
    return _registry_cache


# ---------------------------------------------------------------------------
# Session schedule
# ---------------------------------------------------------------------------

# Default open times (hour, minute) in ET — used when registry lacks a session
_DEFAULT_OPEN_TIMES: dict[int, tuple[int, int]] = {
    1: (9, 30),   # NY
    2: (3, 0),    # LON (08:00 London ≈ 03:00 ET)
    3: (18, 0),   # APAC (matches session_registry.json)
    4: (6, 0),    # NY_PRE
}


def get_session_open_times() -> dict[int, tuple[int, int]]:
    """Return ``{session_id: (hour, minute)}`` from registry or defaults.

    Reads ``or_start`` from each session in session_registry.json and maps
    it to the session_id via :data:`SESSION_IDS`.
    """
    reg = _load_registry()
    sessions = reg.get("sessions", {})

    # Invert SESSION_IDS: "NY" → 1
    name_to_id = {v: k for k, v in SESSION_IDS.items()}

    result: dict[int, tuple[int, int]] = {}
    for name, cfg in sessions.items():
        sid = name_to_id.get(name)
        if sid is None:
            continue
        or_start = cfg.get("or_start", "")
        if or_start:
            parts = or_start.split(":")
            result[sid] = (int(parts[0]), int(parts[1]))

    # Fill in any missing sessions from defaults
    for sid, default in _DEFAULT_OPEN_TIMES.items():
        if sid not in result:
            result[sid] = default

    return result


def is_session_opening(
    now: datetime, session_id: int, hour: int, minute: int,
    window_minutes: int = SESSION_WINDOW_MINUTES,
) -> bool:
    """Check if *now* falls within *window_minutes* of the session open.

    Does NOT track whether the session was already evaluated today —
    that responsibility stays in the orchestrator's ``_session_evaluated_today``.
    """
    target_minute = hour * 60 + minute
    current_minute = now.hour * 60 + now.minute
    return abs(current_minute - target_minute) <= window_minutes


# ---------------------------------------------------------------------------
# Asset-to-session routing
# ---------------------------------------------------------------------------

def get_assets_for_session(session_id: int) -> list[str]:
    """Return asset IDs that belong to *session_id* per the registry.

    Maps session_id → session name (via :data:`SESSION_IDS`), then filters
    ``asset_session_map`` entries matching that name.
    """
    session_name = SESSION_IDS.get(session_id)
    if session_name is None:
        return []

    reg = _load_registry()
    asset_map = reg.get("asset_session_map", {})
    return [asset for asset, sess in asset_map.items() if sess == session_name]


def get_session_config(session_id: int) -> dict | None:
    """Return full session config dict (or_start, or_end, eod, etc.) for *session_id*."""
    session_name = SESSION_IDS.get(session_id)
    if session_name is None:
        return None

    reg = _load_registry()
    return reg.get("sessions", {}).get(session_name)
