# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Opening Range (OR) tracker for live ORB direction resolution.

Tracks OR high/low per (asset, session_date) from live MarketStream quotes,
detects breakouts after the OR window closes, and provides or_range,
entry_price, and direction to downstream blocks (B6).

Architecture: C+B hybrid — this module owns OR state (fed by on_quote);
the orchestrator gates when B6 runs based on breakout/expiry.

Price source: lastPrice from each GatewayQuote tick (running min/max during
OR window).  Aligned to local backtester bar-based OR semantics — first
N-minute high/low from session open.
"""

import json
import logging
import threading
from datetime import datetime, date, time as dtime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pytz import timezone

logger = logging.getLogger(__name__)

_ET = timezone("America/New_York")

# Breakout expiry: minutes after OR close with no breakout → EXPIRED
DEFAULT_BREAKOUT_CUTOFF_MINUTES = 30


class ORState(str, Enum):
    """OR tracking state machine."""
    WAITING = "WAITING"          # Before or_start
    FORMING = "FORMING"          # During OR window (tracking high/low)
    COMPLETE = "COMPLETE"        # OR window closed, awaiting breakout
    BREAKOUT_LONG = "BREAKOUT_LONG"    # Price broke above OR high
    BREAKOUT_SHORT = "BREAKOUT_SHORT"  # Price broke below OR low
    EXPIRED = "EXPIRED"          # No breakout by cutoff


class AssetORSession:
    """OR state for a single (asset, session_date) pair.

    Thread-safe: all mutations go through the tracker's lock.
    """

    __slots__ = (
        "asset_id", "session_date", "session_type",
        "or_start", "or_end", "cutoff",
        "or_high", "or_low", "tick_count",
        "entry_price", "direction", "state",
        "breakout_time",
    )

    def __init__(self, asset_id: str, session_date: date,
                 session_type: str, or_start: dtime, or_end: dtime,
                 cutoff_minutes: int = DEFAULT_BREAKOUT_CUTOFF_MINUTES):
        self.asset_id = asset_id
        self.session_date = session_date
        self.session_type = session_type
        self.or_start = or_start
        self.or_end = or_end
        # Cutoff: or_end + cutoff_minutes
        or_end_dt = datetime.combine(session_date, or_end, tzinfo=_ET)
        cutoff_dt = or_end_dt + timedelta(minutes=cutoff_minutes)
        self.cutoff = cutoff_dt.timetz()

        self.or_high: float | None = None
        self.or_low: float | None = None
        self.tick_count: int = 0
        self.entry_price: float | None = None
        self.direction: int = 0  # 0=pending, +1=long, -1=short
        self.state = ORState.WAITING
        self.breakout_time: datetime | None = None

    @property
    def or_range(self) -> float | None:
        if self.or_high is not None and self.or_low is not None:
            return self.or_high - self.or_low
        return None

    @property
    def is_resolved(self) -> bool:
        return self.state in (
            ORState.BREAKOUT_LONG, ORState.BREAKOUT_SHORT, ORState.EXPIRED
        )

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "session_date": str(self.session_date),
            "session_type": self.session_type,
            "state": self.state.value,
            "or_high": self.or_high,
            "or_low": self.or_low,
            "or_range": self.or_range,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "tick_count": self.tick_count,
            "breakout_time": self.breakout_time.isoformat() if self.breakout_time else None,
        }


# ---------------------------------------------------------------------------
# Session registry loader
# ---------------------------------------------------------------------------

_registry_cache: dict | None = None


def _load_session_registry() -> dict:
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

    logger.warning("session_registry.json not found — using NY defaults")
    _registry_cache = {
        "sessions": {
            "NY": {"or_start": "09:30", "or_end": "09:35", "or_window_minutes": 5},
        },
        "asset_session_map": {},
    }
    return _registry_cache


def get_asset_session_type(asset_id: str) -> str:
    """Return the session type for an asset (e.g. 'NY', 'APAC')."""
    reg = _load_session_registry()
    return reg.get("asset_session_map", {}).get(asset_id, "NY")


def get_or_times(session_type: str) -> tuple[dtime, dtime]:
    """Return (or_start, or_end) as time objects for a session type."""
    reg = _load_session_registry()
    sess = reg.get("sessions", {}).get(session_type, {})
    or_start_str = sess.get("or_start", "09:30")
    or_end_str = sess.get("or_end", "09:35")
    or_start = datetime.strptime(or_start_str, "%H:%M").time()
    or_end = datetime.strptime(or_end_str, "%H:%M").time()
    return or_start, or_end


# ---------------------------------------------------------------------------
# Contract ID → asset_id mapping
# ---------------------------------------------------------------------------

_contract_to_asset: dict[str, str] | None = None


def _load_contract_to_asset() -> dict[str, str]:
    """Build reverse map: contract_id → asset_id from contract_ids.json."""
    global _contract_to_asset
    if _contract_to_asset is not None:
        return _contract_to_asset

    _contract_to_asset = {}
    paths = [
        Path(__file__).resolve().parent.parent.parent.parent / "config" / "contract_ids.json",
        Path("/captain/config/contract_ids.json"),
    ]
    for p in paths:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            for asset_id, info in data.get("contracts", {}).items():
                cid = info.get("contract_id")
                if cid:
                    _contract_to_asset[cid] = asset_id
                    # Also map exchange root (e.g. "F.US.EP")
                    parts = cid.split(".")
                    if len(parts) >= 4 and parts[0] == "CON":
                        _contract_to_asset[".".join(parts[1:-1])] = asset_id
                    name = info.get("name")
                    if name:
                        _contract_to_asset[name] = asset_id
            break

    return _contract_to_asset


# ---------------------------------------------------------------------------
# ORTracker — the main tracker
# ---------------------------------------------------------------------------

class ORTracker:
    """Thread-safe OR tracker for all active assets.

    Usage:
        tracker = ORTracker()
        tracker.register_asset("ES")   # call at session start for each asset
        tracker.on_quote(quote_data)   # called from MarketStream on_quote

        state = tracker.get_state("ES")
        if state and state.is_resolved:
            # direction, or_range, entry_price are available
    """

    def __init__(self, cutoff_minutes: int = DEFAULT_BREAKOUT_CUTOFF_MINUTES):
        self._sessions: dict[str, AssetORSession] = {}  # asset_id → session
        self._lock = threading.Lock()
        self._cutoff_minutes = cutoff_minutes

    def register_asset(self, asset_id: str,
                       session_date: date | None = None) -> None:
        """Start OR tracking for an asset on a given date."""
        if session_date is None:
            session_date = datetime.now(_ET).date()

        session_type = get_asset_session_type(asset_id)
        or_start, or_end = get_or_times(session_type)

        with self._lock:
            session = AssetORSession(
                asset_id=asset_id,
                session_date=session_date,
                session_type=session_type,
                or_start=or_start,
                or_end=or_end,
                cutoff_minutes=self._cutoff_minutes,
            )
            self._sessions[asset_id] = session
            logger.info("OR tracker registered: %s (%s) OR %s–%s on %s",
                        asset_id, session_type, or_start, or_end, session_date)

    def get_state(self, asset_id: str) -> AssetORSession | None:
        """Get current OR state for an asset (snapshot — not a live reference)."""
        with self._lock:
            return self._sessions.get(asset_id)

    def get_all_states(self) -> dict[str, dict]:
        """Get all OR states as dicts (for logging/GUI)."""
        with self._lock:
            return {k: v.to_dict() for k, v in self._sessions.items()}

    def on_quote(self, data: Any) -> None:
        """Process a GatewayQuote tick — called from MarketStream thread.

        Resolves contract_id → asset_id, then updates OR state.
        """
        if not isinstance(data, dict):
            return

        last_price = data.get("lastPrice")
        if last_price is None:
            return

        # Resolve which asset this quote belongs to
        contract_map = _load_contract_to_asset()
        asset_id = None
        for key in ("contractId", "contract_id", "symbol", "symbolId"):
            val = data.get(key)
            if val and val in contract_map:
                asset_id = contract_map[val]
                break

        if asset_id is None:
            return

        now = datetime.now(_ET)
        now_time = now.timetz()

        with self._lock:
            session = self._sessions.get(asset_id)
            if session is None or session.is_resolved:
                return

            self._update_state(session, last_price, now, now_time)

    def check_expirations(self) -> list[str]:
        """Check for expired OR sessions (call from orchestrator loop).

        Returns list of asset_ids that just expired.
        """
        now_time = datetime.now(_ET).timetz()
        expired = []

        with self._lock:
            for asset_id, session in self._sessions.items():
                if session.state == ORState.COMPLETE and now_time >= session.cutoff:
                    session.state = ORState.EXPIRED
                    logger.warning("OR EXPIRED: %s — no breakout by %s",
                                   asset_id, session.cutoff)
                    expired.append(asset_id)

        return expired

    def clear(self) -> None:
        """Clear all tracked sessions (call at end of day)."""
        with self._lock:
            self._sessions.clear()

    # -- Internal state machine ---------------------------------------------

    def _update_state(self, session: AssetORSession,
                      price: float, now: datetime, now_time: dtime) -> None:
        """Advance the OR state machine for a single tick. Caller holds lock."""

        if session.state == ORState.WAITING:
            if now_time >= session.or_start:
                session.state = ORState.FORMING
                session.or_high = price
                session.or_low = price
                session.tick_count = 1
                logger.info("OR FORMING: %s — first tick %.4f at %s",
                            session.asset_id, price, now_time)

        elif session.state == ORState.FORMING:
            if now_time >= session.or_end:
                # OR window closed — transition to COMPLETE
                session.state = ORState.COMPLETE
                logger.info(
                    "OR COMPLETE: %s — high=%.4f low=%.4f range=%.4f (%d ticks)",
                    session.asset_id, session.or_high, session.or_low,
                    session.or_range or 0, session.tick_count,
                )
                # Still check this tick for immediate breakout
                self._check_breakout(session, price, now)
            else:
                # Update running high/low
                if price > session.or_high:
                    session.or_high = price
                if price < session.or_low:
                    session.or_low = price
                session.tick_count += 1

        elif session.state == ORState.COMPLETE:
            self._check_breakout(session, price, now)

    def _check_breakout(self, session: AssetORSession,
                        price: float, now: datetime) -> None:
        """Check if price has broken through OR bounds. Caller holds lock."""
        if session.or_high is None or session.or_low is None:
            return

        broke_high = price > session.or_high
        broke_low = price < session.or_low

        if broke_high and broke_low:
            # Gap through both (extremely rare) — larger penetration wins
            high_pen = price - session.or_high
            low_pen = session.or_low - price
            if high_pen >= low_pen:
                broke_low = False
            else:
                broke_high = False

        if broke_high:
            session.state = ORState.BREAKOUT_LONG
            session.direction = 1
            session.entry_price = price
            session.breakout_time = now
            logger.info("OR BREAKOUT LONG: %s — price=%.4f > OR high=%.4f, "
                        "or_range=%.4f", session.asset_id, price,
                        session.or_high, session.or_range or 0)

        elif broke_low:
            session.state = ORState.BREAKOUT_SHORT
            session.direction = -1
            session.entry_price = price
            session.breakout_time = now
            logger.info("OR BREAKOUT SHORT: %s — price=%.4f < OR low=%.4f, "
                        "or_range=%.4f", session.asset_id, price,
                        session.or_low, session.or_range or 0)
