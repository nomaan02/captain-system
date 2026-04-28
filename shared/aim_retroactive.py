"""Phase 7 — AIM retroactive replay (PG-10 Step 1, F-24).

Stand-alone helper that replays a single AIM's modifier computation
against historical features for a given session window. Used by
``b4_injection`` to produce per-AIM modifier series under candidate
strategy thresholds, replacing the prior scalar heuristic.

Per Stage 1B Appendix A. Independent of ``replay_session`` — does not
run B1-B6, only replays the AIM modifier dispatch from ``aim_compute``
against features loaded from QuestDB.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from shared.aim_compute import compute_aim_modifier


_ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def aim_retroactive_replay(
    aim_id: int,
    candidate_strategy: dict,
    historical_window: tuple[date, date],
    *,
    user_id: str,
    asset: str,
) -> list[tuple[date, float]]:
    """Per-day modifier series for ``aim_id`` against ``candidate_strategy``.

    For each session day in ``historical_window`` (inclusive of both
    endpoints), load the asset's feature row from QuestDB feature
    storage (D29/D30/D31/D33), build a state dict that carries the
    candidate strategy thresholds, and call ``compute_aim_modifier``.

    Returns a list of ``(date, modifier)`` tuples sorted by date.
    Days where features are unavailable or the modifier dispatch
    declines (NO_HANDLER / ERROR) are dropped from the series.
    """
    series: list[tuple[date, float]] = []
    for d in _iter_session_days(historical_window[0], historical_window[1]):
        features = _load_historical_features(asset, d)
        if features is None:
            continue
        state = _state_from_candidate(candidate_strategy, asset)
        try:
            result = compute_aim_modifier(
                aim_id, {asset: features}, asset, state,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "AIM-%02d retroactive replay failed for %s on %s",
                aim_id, asset, d,
            )
            continue
        if not result or result.get("reason_tag") in ("NO_HANDLER", "ERROR"):
            continue
        series.append((d, float(result.get("modifier", 1.0))))
    return series


def _iter_session_days(start: date, end: date) -> Iterable[date]:
    """Inclusive range generator skipping weekends.

    Holiday calendar is intentionally excluded — historical D03 timestamps
    drive PG-09's day list; this generator only fills the candidate-side
    feature lookup, and a missing feature row simply drops the day.
    """
    current = start
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            yield current
        current = current + timedelta(days=1)


def _state_from_candidate(candidate_strategy: dict, asset: str) -> dict:
    """Build the ``state`` dict expected by AIM modifier handlers.

    The handlers in ``shared.aim_compute`` accept a ``state`` dict that
    carries asset-scoped thresholds and historical context. Candidate
    strategies override the threshold values; everything else is left
    empty so the handlers fall back to their defaults.
    """
    state: dict = {asset: dict(candidate_strategy)}
    return state


def _load_historical_features(asset: str, d: date) -> dict | None:
    """Load the asset's feature row for session day ``d`` from QuestDB.

    Reads from the feature tables populated by Online B1 (D29 opening
    volumes, D30 daily OHLCV, D31 implied vol, D33 opening volatility).
    Returns ``None`` when no features are available — the caller treats
    that as a skip.
    """
    from shared.questdb_client import get_cursor

    et_start = datetime.combine(d, time.min).replace(tzinfo=_ET)
    et_end = et_start + timedelta(days=1)

    features: dict = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT close, open, high, low, volume
                   FROM p3_d30_daily_ohlcv
                   WHERE asset_id = %s AND ts >= %s AND ts < %s
                   ORDER BY ts DESC LIMIT 1""",
                (asset, et_start.isoformat(), et_end.isoformat()),
            )
            row = cur.fetchone()
        if row:
            features["daily_close"] = _safe(row[0])
            features["daily_open"] = _safe(row[1])
            features["daily_high"] = _safe(row[2])
            features["daily_low"] = _safe(row[3])
            features["daily_volume"] = _safe(row[4])

        with get_cursor() as cur:
            cur.execute(
                """SELECT atm_iv_30d, realized_vol_20d, vrp
                   FROM p3_d31_implied_vol
                   WHERE asset_id = %s AND trade_date < %s
                   ORDER BY trade_date DESC LIMIT 1""",
                (asset, et_end.isoformat()),
            )
            row = cur.fetchone()
        if row:
            features["atm_iv_30d"] = _safe(row[0])
            features["realized_vol_20d"] = _safe(row[1])
            features["vrp"] = _safe(row[2])

        with get_cursor() as cur:
            cur.execute(
                """SELECT volume_first_m_min, or_range_first_m_min
                   FROM p3_d29_opening_volumes
                   WHERE asset_id = %s AND ts < %s
                   ORDER BY ts DESC LIMIT 1""",
                (asset, et_end.isoformat()),
            )
            row = cur.fetchone()
        if row:
            features["opening_volume"] = _safe(row[0])
            features["or_range"] = _safe(row[1])
    except Exception:
        logger.exception(
            "aim_retroactive_replay: feature load failed for %s on %s", asset, d,
        )
        return None

    return features or None


def _safe(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Aggregator used by b4_injection                                             #
# --------------------------------------------------------------------------- #


def aggregate_modifiers(
    retroactive_modifiers: dict[int, list[tuple[date, float]]],
    aim_weights: dict[int, float],
) -> list[tuple[date, float]]:
    """Combine per-AIM modifier series into a daily weighted-average series.

    For each session day present in ``retroactive_modifiers``, returns the
    weight-normalised mean modifier across active AIMs. Days where every
    series is silent are dropped.
    """
    if not retroactive_modifiers:
        return []

    by_day: dict[date, list[tuple[float, float]]] = {}
    for aim_id, series in retroactive_modifiers.items():
        weight = float(aim_weights.get(aim_id, 0.0) or 0.0)
        if weight <= 0.0:
            continue
        for day, modifier in series:
            by_day.setdefault(day, []).append((weight, float(modifier)))

    aggregated: list[tuple[date, float]] = []
    for day in sorted(by_day):
        pairs = by_day[day]
        weight_total = sum(w for w, _ in pairs)
        if weight_total <= 0.0:
            continue
        weighted_mod = sum(w * m for w, m in pairs) / weight_total
        aggregated.append((day, weighted_mod))
    return aggregated
