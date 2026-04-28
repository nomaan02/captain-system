"""AIM-16 HMM observation panel — doc 22 §4 (shared offline PG-01C + online alignment).

POPULATES ALL 7 FEATURES from QuestDB aggregations best-effort; missing fills use 0.0.

Schema version bumped when observation definitions change."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

import numpy as np

from shared.questdb_client import get_cursor
from shared.vix_provider import get_vix_close_on_or_before

logger = logging.getLogger(__name__)

OBS_SCHEMA_VERSION = 1


def _parse_closed_at_day(closed_at: Optional[str]) -> date:
    """Anchor date for PG-01C training panel (preferred: ``closed_at`` from SESSION_CLOSE)."""
    if closed_at:
        try:
            return datetime.fromisoformat(closed_at.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            pass
    return datetime.now().date()


def _last_n_weekdays(end_d: date, n: int) -> list[date]:
    """``n`` calendar weekdays (Mon–Fri) ending at ``end_d`` inclusive, oldest first."""
    out: list[date] = []
    d = end_d
    guard = 0
    while len(out) < n and guard < 400:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
        guard += 1
    out.reverse()
    return out


def _mean_cross_asset_corr(cor_matrix_json: Any, universe: list[str]) -> float:
    """Mean pairwise corr over active universe from D07 correlation JSON dict."""
    if not universe or cor_matrix_json is None:
        return 0.0
    cm = (
        json.loads(cor_matrix_json)
        if isinstance(cor_matrix_json, str)
        else cor_matrix_json
    )
    if not isinstance(cm, dict):
        return 0.0
    assets = list(universe)[:48]
    pairs: list[float] = []
    for i, a in enumerate(assets):
        for b in assets[i + 1 :]:
            pair = cm.get(f"{a}_{b}")
            if pair is None:
                pair = cm.get(f"{b}_{a}")
            if isinstance(pair, (int, float)):
                pairs.append(float(pair))
    if not pairs:
        return 0.0
    return float(sum(pairs) / len(pairs))


def _slot_features_for_day_sess(
    cur,
    *,
    sess_date: date,
    session_int: int,
    assets_placeholder: list[str],
    cross_corr_mean: float,
    prev_session_pnl: float,
    vix_lvl: float,
) -> tuple[np.ndarray, float]:
    """One row vector (7,) and aggregated session realised PnL for D03 rows."""
    dstr = sess_date.isoformat()

    session_pnl = 0.0
    mean_oo = 0.0
    n_signals = 0

    cur.execute(
        """
        SELECT
          count() as cnt,
          coalesce(sum(pnl), 0) as pnl_sum,
          coalesce(avg(
            CASE
              WHEN entry_price IS NOT NULL AND exit_price IS NOT NULL AND entry_price != 0
              THEN abs(exit_price - signal_entry_price) / abs(entry_price)
              ELSE NULL
            END
          ), 0) as oo
        FROM p3_d03_trade_outcome_log
        WHERE cast(ts as date) = %s AND session = %s
        """,
        (dstr, session_int),
    )
    row = cur.fetchone()
    if row:
        n_signals = int(row[0] or 0)
        session_pnl = float(row[1] or 0)
        oo = row[2]
        mean_oo = float(oo if oo is not None else 0.0)

    # volume_z: pooled volumes for session_date — z vs trailing same-calendar-day pooled volume proxy
    cur.execute(
        """
        SELECT coalesce(sum(volume_first_m_min), 0)::double / greatest(count(), 1)
        FROM p3_d29_opening_volumes
        WHERE session_date = %s
        """,
        (dstr,),
    )
    rvol = cur.fetchone()
    day_vol_avg = float(rvol[0] or 0) if rvol else 0.0

    hist: list[float] = []
    for back in range(1, 21):
        pd = sess_date - timedelta(days=back)
        cur.execute(
            """
            SELECT coalesce(sum(volume_first_m_min), 0)::double / greatest(count(), 1)
            FROM p3_d29_opening_volumes
            WHERE session_date = %s
            """,
            (pd.isoformat(),),
        )
        xr = cur.fetchone()
        if xr and xr[0] is not None:
            hist.append(float(xr[0]))
    if hist:
        m = sum(hist) / len(hist)
        sd = (sum((h - m) ** 2 for h in hist) / len(hist)) ** 0.5
        volume_z = 0.0 if sd <= 1e-9 else (day_vol_avg - m) / sd
    else:
        volume_z = 0.0

    dow = float(sess_date.weekday())  # 0 Mon .. 6 Sun (doc 22: encoded weekday — use raw)

    vec = np.array(
        [
            float(n_signals),
            float(mean_oo),
            float(volume_z),
            float(vix_lvl),
            float(prev_session_pnl),
            float(cross_corr_mean),
            float(dow),
        ],
        dtype=float,
    )
    vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
    return vec, session_pnl


def build_observation_panel(
    asset_universe: list[str],
    closed_at: Optional[str] = None,
    lookback_days: int = 60,
):
    """Build chronological (T,7) observations and session P&amp;L for Baum-Welch.

    T <= 240 = 60 weekdays * 4 sessions (doc 22 §6 uses 4 session slices / day).

    Returns:
        observations: np.ndarray shape (T, 7)
        session_pnl: np.ndarray shape (T,) — per-slot realised PnL from D03
        n_trading_days: int — count of distinct weekdays in the panel
    """
    end_day = _parse_closed_at_day(closed_at)
    weekdays = _last_n_weekdays(end_day, lookback_days)
    n_trading_days = len(weekdays)
    if n_trading_days == 0:
        return np.zeros((0, 7), dtype=float), np.zeros((0,), dtype=float), 0

    rows: list[np.ndarray] = []
    pnls: list[float] = []

    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT correlation_matrix
                FROM p3_d07_correlation_model_states
                ORDER BY last_updated DESC LIMIT 1
                """
            )
            r7 = cur.fetchone()
            cross_mean = _mean_cross_asset_corr(r7[0] if r7 else None, asset_universe)

            prev_pnl = 0.0
            for d in weekdays:
                for session_int in (1, 2, 3, 4):
                    vx = get_vix_close_on_or_before(d) or 0.0
                    vec, spnl = _slot_features_for_day_sess(
                        cur,
                        sess_date=d,
                        session_int=session_int,
                        assets_placeholder=asset_universe,
                        cross_corr_mean=cross_mean,
                        prev_session_pnl=prev_pnl,
                        vix_lvl=vx,
                    )
                    prev_pnl = spnl
                    rows.append(vec)
                    pnls.append(spnl)
    except Exception as exc:
        logger.warning("[aim16] build_observation_panel DB failed (%s)", exc)
        return np.zeros((0, 7), dtype=float), np.zeros((0,), dtype=float), 0

    if not rows:
        return np.zeros((0, 7), dtype=float), np.zeros((0,), dtype=float), 0

    obs = np.vstack(rows)
    sess_pnl_a = np.array(pnls, dtype=float)
    return obs, sess_pnl_a, n_trading_days


def build_single_observation_vector(
    *,
    sess_date: date,
    session_int: int,
    asset_universe: list[str],
    prev_session_pnl: float = 0.0,
) -> np.ndarray:
    """Latest (7,) observation for online inference — same OBS_SCHEMA_VERSION as training."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT correlation_matrix
            FROM p3_d07_correlation_model_states
            ORDER BY last_updated DESC LIMIT 1
            """
        )
        r7 = cur.fetchone()
        cross_mean = _mean_cross_asset_corr(r7[0] if r7 else None, asset_universe)
        vx = get_vix_close_on_or_before(sess_date) or 0.0
        vec, _ = _slot_features_for_day_sess(
            cur,
            sess_date=sess_date,
            session_int=session_int,
            assets_placeholder=asset_universe,
            cross_corr_mean=cross_mean,
            prev_session_pnl=prev_session_pnl,
            vix_lvl=vx,
        )
    return vec
