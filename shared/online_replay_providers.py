"""Phase 7 — concrete provider implementations for replay infrastructure.

Split from ``shared.online_replay`` so the live and historical
implementations don't import each other. The protocols themselves live
in ``shared.online_replay``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from shared.online_replay import (  # noqa: F401  re-exported for tests
    MarketDataProvider,
    SignalSink,
    TimeProvider,
)


_ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Market data                                                                 #
# --------------------------------------------------------------------------- #


def _import_topstep():
    """Lazy import bundle — exposed so tests can patch at module scope."""
    from shared.contract_resolver import resolve_contract_id
    from shared.topstep_client import TopstepXClientError, get_topstep_client
    return resolve_contract_id, get_topstep_client, TopstepXClientError


def get_topstep_client():  # pragma: no cover - thin shim, see _import_topstep
    return _import_topstep()[1]()


def resolve_contract_id(asset_id: str):  # pragma: no cover
    return _import_topstep()[0](asset_id)


def get_redis_client():  # pragma: no cover - thin shim
    from shared.redis_client import get_redis_client as _impl
    return _impl()


@dataclass
class LiveMarketDataProvider:
    """Default provider — wraps existing ``shared.topstep_client`` +
    ``topstep_stream.quote_cache``. Methods are thin shims around current
    call sites so the live B1 path is byte-identical when no provider is
    supplied (Phase 7 live-parity invariant)."""

    def get_bars(
        self, asset_id: str, timeframe: str, start: datetime, end: datetime,
    ) -> list[dict]:
        from shared.topstep_client import TopstepXClientError

        contract_id = resolve_contract_id(asset_id)
        if not contract_id:
            return []
        try:
            client = get_topstep_client()
            bar_unit, bar_value = _parse_timeframe(timeframe)
            bars = client.get_bars(
                contract_id, bar_unit, bar_value,
                start.isoformat(), end.isoformat(),
            )
            return list(bars or [])
        except TopstepXClientError:
            return []

    def get_current_quote(self, asset_id: str) -> dict | None:
        try:
            from shared.topstep_stream import quote_cache
        except Exception:
            return None
        return quote_cache.get(asset_id)

    def get_current_session_volume(self, asset_id: str) -> int | None:
        try:
            from shared.topstep_stream import quote_cache
        except Exception:
            return None
        quote = quote_cache.get(asset_id) or {}
        vol = quote.get("session_volume")
        return int(vol) if vol is not None else None

    def get_avg_session_volume_20d(self, asset_id: str) -> float | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT avg(volume_first_m_min) FROM p3_d29_opening_volumes
                       WHERE asset_id = %s
                       ORDER BY ts DESC LIMIT 20""",
                    (asset_id,),
                )
                row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def get_prior_close(self, asset_id: str) -> float | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT close FROM p3_d30_daily_ohlcv
                       WHERE asset_id = %s
                       ORDER BY ts DESC LIMIT 1""",
                    (asset_id,),
                )
                row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def get_intraday_bars(
        self, asset_id: str, lookback_minutes: int,
    ) -> list[dict] | None:
        end = datetime.now(_ET)
        start = end - timedelta(minutes=lookback_minutes)
        bars = self.get_bars(asset_id, "1m", start, end)
        return bars or None

    def get_historical_session_volumes(
        self, asset_id: str, n_sessions: int,
    ) -> list[int] | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT volume_first_m_min FROM p3_d29_opening_volumes
                       WHERE asset_id = %s
                       ORDER BY ts DESC LIMIT %s""",
                    (asset_id, n_sessions),
                )
                rows = cur.fetchall()
            return [int(r[0]) for r in rows if r and r[0] and r[0] > 0] or None
        except Exception:
            return None

    def get_daily_closes(
        self, asset_id: str, n_days: int,
    ) -> list[float] | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT close FROM p3_d30_daily_ohlcv
                       WHERE asset_id = %s
                       ORDER BY ts DESC LIMIT %s""",
                    (asset_id, n_days),
                )
                rows = cur.fetchall()
            return [float(r[0]) for r in rows if r and r[0] is not None] or None
        except Exception:
            return None


@dataclass
class HistoricalMarketDataProvider:
    """Replay provider — reads from QuestDB historical bar storage.

    Bars table caveat (O3): there is no canonical 1-minute bar storage
    table in QuestDB today. ``get_bars`` falls back to the daily OHLCV
    table for ``timeframe='1d'`` and returns an empty list otherwise — the
    Phase 7 build plan flagged this as a gap to address before PG-09 can
    run beyond a daily granularity. Quote synthesis uses ``get_prior_close``
    for the most-recent bar before ``as_of``.
    """

    as_of: datetime

    def get_bars(
        self, asset_id: str, timeframe: str, start: datetime, end: datetime,
    ) -> list[dict]:
        from shared.questdb_client import get_cursor

        if timeframe != "1d":
            # 1-minute bar history — gap surfaced in Phase 7.5 follow-up.
            return []
        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT trade_date, open, high, low, close, volume
                       FROM p3_d30_daily_ohlcv
                       WHERE asset_id = %s
                         AND ts >= %s AND ts < %s
                       ORDER BY ts ASC""",
                    (asset_id, start.isoformat(), end.isoformat()),
                )
                rows = cur.fetchall()
        except Exception:
            return []
        out = []
        for date_s, o, h, l, c, v in rows:
            out.append(
                {
                    "ts": date_s,
                    "open": float(o) if o is not None else None,
                    "high": float(h) if h is not None else None,
                    "low": float(l) if l is not None else None,
                    "close": float(c) if c is not None else None,
                    "volume": int(v) if v is not None else None,
                }
            )
        return out

    def get_current_quote(self, asset_id: str) -> dict | None:
        last_close = self.get_prior_close(asset_id)
        if last_close is None:
            return None
        return {
            "bid": last_close, "ask": last_close,
            "bid_size": 1, "ask_size": 1,
            "ts": self.as_of.isoformat(),
        }

    def get_current_session_volume(self, asset_id: str) -> int | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT volume_first_m_min FROM p3_d29_opening_volumes
                       WHERE asset_id = %s AND ts <= %s
                       ORDER BY ts DESC LIMIT 1""",
                    (asset_id, self.as_of.isoformat()),
                )
                row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def get_avg_session_volume_20d(self, asset_id: str) -> float | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT avg(volume_first_m_min) FROM p3_d29_opening_volumes
                       WHERE asset_id = %s AND ts <= %s
                       ORDER BY ts DESC LIMIT 20""",
                    (asset_id, self.as_of.isoformat()),
                )
                row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def get_prior_close(self, asset_id: str) -> float | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT close FROM p3_d30_daily_ohlcv
                       WHERE asset_id = %s AND ts < %s
                       ORDER BY ts DESC LIMIT 1""",
                    (asset_id, self.as_of.isoformat()),
                )
                row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def get_intraday_bars(
        self, asset_id: str, lookback_minutes: int,
    ) -> list[dict] | None:
        # See get_bars caveat — no 1m history table; surfaced as gap.
        return None

    def get_historical_session_volumes(
        self, asset_id: str, n_sessions: int,
    ) -> list[int] | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT volume_first_m_min FROM p3_d29_opening_volumes
                       WHERE asset_id = %s AND ts < %s
                       ORDER BY ts DESC LIMIT %s""",
                    (asset_id, self.as_of.isoformat(), n_sessions),
                )
                rows = cur.fetchall()
            return [int(r[0]) for r in rows if r and r[0] and r[0] > 0] or None
        except Exception:
            return None

    def get_daily_closes(
        self, asset_id: str, n_days: int,
    ) -> list[float] | None:
        from shared.questdb_client import get_cursor

        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT close FROM p3_d30_daily_ohlcv
                       WHERE asset_id = %s AND ts < %s
                       ORDER BY ts DESC LIMIT %s""",
                    (asset_id, self.as_of.isoformat(), n_days),
                )
                rows = cur.fetchall()
            return [float(r[0]) for r in rows if r and r[0] is not None] or None
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Signal sinks                                                                #
# --------------------------------------------------------------------------- #


@dataclass
class RedisSignalPublisher:
    """Default sink — publishes to live Redis ``STREAM_SIGNALS``."""

    def publish(self, channel: str, payload: dict) -> bool:
        try:
            client = get_redis_client()
        except Exception:
            logger.exception("Redis import failed")
            return False
        try:
            client.publish(channel, payload)  # type: ignore[arg-type]
        except Exception:
            try:
                client.xadd(channel, payload)  # type: ignore[union-attr]
            except Exception:
                logger.exception("Redis publish failed for %s", channel)
                return False
        return True

    def captured(self) -> list[dict]:
        return []


@dataclass
class CapturingSignalSink:
    """Replay sink — captures signals to a list, never publishes."""

    def __post_init__(self) -> None:
        self._captured: list[dict] = []

    def publish(self, channel: str, payload: dict) -> bool:
        self._captured.append({"channel": channel, "payload": payload})
        return True

    def captured(self) -> list[dict]:
        return [c["payload"] for c in self._captured]


# --------------------------------------------------------------------------- #
# Time providers                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class LiveTimeProvider:
    def now_et(self) -> datetime:
        return datetime.now(_ET)


@dataclass
class FixedTimeProvider:
    """Replay time — returns a fixed timestamp; advanceable for Phase B."""

    fixed: datetime

    def __post_init__(self) -> None:
        if self.fixed.tzinfo is None:
            self.fixed = self.fixed.replace(tzinfo=_ET)

    def now_et(self) -> datetime:
        return self.fixed

    def advance(self, seconds: int) -> None:
        self.fixed = self.fixed + timedelta(seconds=seconds)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _parse_timeframe(tf: str) -> tuple[int, int]:
    """Map a TF string to TopstepX ``(barUnit, barValue)`` tuple.

    barUnit codes: 1=Second, 2=Minute, 3=Hour, 4=Day, 5=Week, 6=Month.
    """
    tf = tf.strip().lower()
    if tf.endswith("m") and tf[:-1].isdigit():
        return (2, int(tf[:-1]))
    if tf.endswith("h") and tf[:-1].isdigit():
        return (3, int(tf[:-1]))
    if tf in ("1d", "d", "day"):
        return (4, 1)
    if tf.endswith("s") and tf[:-1].isdigit():
        return (1, int(tf[:-1]))
    return (2, 1)
