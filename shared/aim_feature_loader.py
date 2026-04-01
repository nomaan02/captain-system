"""Historical AIM feature loader for session replay.

Builds the features dict, aim_states, and aim_weights needed by
shared.aim_compute.run_aim_aggregation() using historical data from
QuestDB tables and VIX CSVs.

Data sources:
  - VIX/VXV: shared/vix_provider.py (CSV-backed, 9155+ rows)
  - OHLCV:   p3_d30_daily_ohlcv (283 days × 10 assets)
  - IV/RV:   p3_d31_implied_vol (ES only, 122 days)
  - Skew:    p3_d32_options_skew (ES only, 81 days)
  - Vol:     p3_d33_opening_volatility (240 rows)
  - Volumes: p3_d29_opening_volumes (24 days)
  - States:  p3_d01_aim_model_states
  - Weights: p3_d02_aim_meta_weights
"""

import json
import logging
from datetime import date, timedelta

from shared.aim_compute import z_score
from shared.questdb_client import get_cursor
from shared import vix_provider

logger = logging.getLogger(__name__)


def load_replay_features(target_date: date, assets: list[str]):
    """Load historical features, AIM states, and weights for a replay date.

    Returns:
        (features, aim_states, aim_weights) tuple ready for run_aim_aggregation().
    """
    with get_cursor() as cur:
        # Shared VIX features (same for all assets)
        vix_features = _load_vix_features(target_date)

        # Per-asset features
        features = {}
        for asset_id in assets:
            f = {}
            f.update(vix_features)
            f.update(_load_ohlcv_features(target_date, asset_id, cur))
            f.update(_load_iv_rv_features(target_date, asset_id, cur))
            f.update(_load_skew_features(target_date, asset_id, cur))
            f.update(_load_volume_features(target_date, asset_id, cur))
            f.update(_load_calendar_features(target_date, asset_id))
            features[asset_id] = f

        aim_states, aim_weights = _load_aim_states_and_weights(assets, cur)

    return features, aim_states, aim_weights


# ---------------------------------------------------------------------------
# VIX / VXV / IVTS features (shared across all assets)
# ---------------------------------------------------------------------------

def _load_vix_features(target_date: date) -> dict:
    """Compute VIX-derived features from CSV data.

    Returns features used by AIM-04 (ivts), AIM-11 (vix_z, vix_daily_change_z),
    and AIM-12 (vix_z overlay).
    """
    # Get VIX data up to target_date
    vix_data = vix_provider._vix_data  # (date, close) sorted ascending
    vix_provider._ensure_loaded()
    vix_data = vix_provider._vix_data

    vxv_data = vix_provider._vxv_data

    # Filter to <= target_date
    vix_up_to = [(d, c) for d, c in vix_data if d <= target_date]
    vxv_up_to = [(d, c) for d, c in vxv_data if d <= target_date]

    f = {}

    if not vix_up_to:
        return f

    latest_vix = vix_up_to[-1][1]

    # vix_z: 252-day trailing z-score
    trailing_252 = [c for _, c in vix_up_to[-252:]]
    f["vix_z"] = z_score(latest_vix, trailing_252)

    # vix_daily_change_z: z-score of latest abs daily change over 60-day changes
    if len(vix_up_to) >= 2:
        latest_change = abs(vix_up_to[-1][1] - vix_up_to[-2][1])
        closes_61 = [c for _, c in vix_up_to[-61:]]
        changes = [abs(closes_61[i] - closes_61[i - 1]) for i in range(1, len(closes_61))]
        f["vix_daily_change_z"] = z_score(latest_change, changes)

    # ivts: VIX / VXV ratio (used by AIM-04)
    if vxv_up_to:
        latest_vxv = vxv_up_to[-1][1]
        if latest_vxv > 0:
            f["ivts"] = latest_vix / latest_vxv

    return f


# ---------------------------------------------------------------------------
# OHLCV features (per asset)
# ---------------------------------------------------------------------------

def _load_ohlcv_features(target_date: date, asset_id: str, cur) -> dict:
    """Compute OHLCV-derived features from p3_d30_daily_ohlcv.

    Returns features used by AIM-01 (day_of_week overlay), AIM-04 (overnight_return_z),
    AIM-08 (correlation_z), AIM-09 (cross_momentum).
    """
    f = {}
    target_str = target_date.isoformat()

    # Get trailing 30 rows for this asset
    cur.execute(
        "SELECT trade_date, open, high, low, close FROM p3_d30_daily_ohlcv "
        "WHERE asset_id = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 30",
        (asset_id, target_str),
    )
    rows = cur.fetchall()
    if not rows or len(rows) < 2:
        return f

    # Rows are descending — reverse for chronological order
    rows = list(reversed(rows))
    # Each row: (trade_date, open, high, low, close)

    closes = [r[4] for r in rows]
    opens = [r[1] for r in rows]

    # overnight_return_z: (today_open - yesterday_close) / yesterday_close, z-scored
    overnight_returns = []
    for i in range(1, len(rows)):
        prev_close = rows[i - 1][4]
        curr_open = rows[i][1]
        if prev_close and prev_close != 0:
            overnight_returns.append((curr_open - prev_close) / prev_close)

    if overnight_returns:
        f["overnight_return_z"] = z_score(overnight_returns[-1], overnight_returns)

    # cross_momentum: sign alignment of 5-day vs 20-day returns
    if len(closes) >= 20:
        ret_5 = (closes[-1] - closes[-5]) / closes[-5] if closes[-5] != 0 else 0
        ret_20 = (closes[-1] - closes[-20]) / closes[-20] if closes[-20] != 0 else 0
        # +1 if aligned, -1 if opposed, 0 if one is flat
        if ret_5 > 0 and ret_20 > 0:
            f["cross_momentum"] = 1.0
        elif ret_5 < 0 and ret_20 < 0:
            f["cross_momentum"] = 1.0
        elif (ret_5 > 0 and ret_20 < 0) or (ret_5 < 0 and ret_20 > 0):
            f["cross_momentum"] = -1.0
        else:
            f["cross_momentum"] = 0.0

    # correlation_z: 20-day rolling correlation with ES (requires ES data too)
    if asset_id != "ES":
        cur.execute(
            "SELECT trade_date, close FROM p3_d30_daily_ohlcv "
            "WHERE asset_id = 'ES' AND trade_date <= %s ORDER BY trade_date DESC LIMIT 30",
            (target_str,),
        )
        es_rows = cur.fetchall()
        if es_rows and len(es_rows) >= 20:
            es_rows = list(reversed(es_rows))
            es_closes = [r[1] for r in es_rows]

            # Align by trade_date
            es_by_date = {r[0]: r[1] for r in es_rows}
            asset_by_date = {r[0]: r[4] for r in rows}
            common_dates = sorted(set(es_by_date.keys()) & set(asset_by_date.keys()))

            if len(common_dates) >= 20:
                es_rets = []
                asset_rets = []
                for i in range(1, len(common_dates)):
                    d, d_prev = common_dates[i], common_dates[i - 1]
                    es_prev, es_cur = es_by_date[d_prev], es_by_date[d]
                    a_prev, a_cur = asset_by_date[d_prev], asset_by_date[d]
                    if es_prev and a_prev and es_prev != 0 and a_prev != 0:
                        es_rets.append((es_cur - es_prev) / es_prev)
                        asset_rets.append((a_cur - a_prev) / a_prev)

                if len(es_rets) >= 10:
                    corr = _pearson(es_rets[-20:], asset_rets[-20:])
                    if corr is not None:
                        # z-score the correlation (use trailing correlations as baseline)
                        # Simplified: use the correlation value directly as proxy z-score
                        # since we don't have a long history of rolling correlations
                        f["correlation_z"] = corr
    else:
        # ES correlation with itself is 1.0 — always normal
        f["correlation_z"] = 0.0

    return f


# ---------------------------------------------------------------------------
# IV/RV features (AIM-01 VRP) — ES only
# ---------------------------------------------------------------------------

def _load_iv_rv_features(target_date: date, asset_id: str, cur) -> dict:
    """Compute VRP from p3_d31_implied_vol. Currently only ES has data."""
    f = {}

    cur.execute(
        "SELECT trade_date, atm_iv_30d, realized_vol_20d FROM p3_d31_implied_vol "
        "WHERE asset_id = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 30",
        (asset_id, target_date.isoformat()),
    )
    rows = cur.fetchall()
    if not rows or len(rows) < 10:
        return f

    # VRP = IV - RV (positive means implied > realized, uncertainty premium)
    vrps = []
    for _, iv, rv in reversed(rows):
        if iv is not None and rv is not None:
            vrps.append(iv - rv)

    if vrps:
        f["vrp_overnight_z"] = z_score(vrps[-1], vrps)

    return f


# ---------------------------------------------------------------------------
# Skew features (AIM-02) — ES only
# ---------------------------------------------------------------------------

def _load_skew_features(target_date: date, asset_id: str, cur) -> dict:
    """Compute skew_z from p3_d32_options_skew. Currently only ES has data."""
    f = {}

    cur.execute(
        "SELECT trade_date, cboe_skew FROM p3_d32_options_skew "
        "WHERE asset_id = %s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 30",
        (asset_id, target_date.isoformat()),
    )
    rows = cur.fetchall()
    if not rows or len(rows) < 10:
        return f

    skews = [r[1] for r in reversed(rows) if r[1] is not None]
    if skews:
        f["skew_z"] = z_score(skews[-1], skews)

    # pcr_z not available — no PCR data source
    return f


# ---------------------------------------------------------------------------
# Volume / volatility features (AIM-12 vol_z, AIM-15 opening_volume_ratio)
# ---------------------------------------------------------------------------

def _load_volume_features(target_date: date, asset_id: str, cur) -> dict:
    """Compute vol_z and opening_volume_ratio from QuestDB tables."""
    f = {}

    # vol_z from p3_d33_opening_volatility
    cur.execute(
        "SELECT session_date, vol_5min FROM p3_d33_opening_volatility "
        "WHERE asset_id = %s AND session_date <= %s ORDER BY session_date DESC LIMIT 30",
        (asset_id, target_date.isoformat()),
    )
    vol_rows = cur.fetchall()
    if vol_rows and len(vol_rows) >= 10:
        vols = [r[1] for r in reversed(vol_rows) if r[1] is not None]
        if vols:
            f["vol_z"] = z_score(vols[-1], vols)

    # opening_volume_ratio from p3_d29_opening_volumes
    cur.execute(
        "SELECT session_date, volume_first_m_min FROM p3_d29_opening_volumes "
        "WHERE asset_id = %s AND session_date <= %s ORDER BY ts DESC LIMIT 30",
        (asset_id, target_date.isoformat()),
    )
    vol_count_rows = cur.fetchall()
    if vol_count_rows and len(vol_count_rows) >= 2:
        volumes = [r[1] for r in reversed(vol_count_rows) if r[1] is not None and r[1] > 0]
        if volumes and len(volumes) >= 2:
            avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
            if avg_vol > 0:
                f["opening_volume_ratio"] = volumes[-1] / avg_vol

    return f


# ---------------------------------------------------------------------------
# Calendar features (pure date computation)
# ---------------------------------------------------------------------------

def _load_calendar_features(target_date: date, asset_id: str) -> dict:
    """Compute calendar-derived features from the target date alone."""
    f = {}

    f["day_of_week"] = target_date.weekday()  # 0=Monday

    # is_opex_window: True if within ±2 trading days of 3rd Friday
    third_friday = _third_friday(target_date.year, target_date.month)
    delta = abs((target_date - third_friday).days)
    f["is_opex_window"] = delta <= 3  # ±3 calendar days ≈ ±2 trading days

    # is_eia_wednesday: only matters for CL (crude oil) — not in our universe
    f["is_eia_wednesday"] = target_date.weekday() == 2 and asset_id == "CL"

    # event_proximity / events_today: no calendar feed in replay
    # Handlers will get None → return neutral modifier

    return f


# ---------------------------------------------------------------------------
# AIM states and weights from QuestDB
# ---------------------------------------------------------------------------

def _load_aim_states_and_weights(assets: list[str], cur):
    """Load aim_states and aim_weights for run_aim_aggregation().

    Returns:
        (aim_states, aim_weights) matching the expected dict structures.
    """
    # Load D01 states
    by_asset_aim = {}
    cur.execute(
        "SELECT aim_id, asset_id, status, current_modifier, warmup_progress "
        "FROM p3_d01_aim_model_states"
    )
    for row in cur.fetchall():
        aim_id, asset_id, status, current_modifier_str, warmup_progress = row
        if asset_id not in assets:
            continue
        state = {
            "status": status or "INSTALLED",
            "warmup_progress": warmup_progress or 0.0,
        }
        # Parse current_modifier JSON if present (used by AIM-13, AIM-16)
        if current_modifier_str:
            try:
                state["current_modifier"] = json.loads(current_modifier_str)
            except (json.JSONDecodeError, TypeError):
                pass
        by_asset_aim[(asset_id, aim_id)] = state

    aim_states = {"by_asset_aim": by_asset_aim, "global": {}}

    # Load D02 weights
    aim_weights = {}
    cur.execute(
        "SELECT aim_id, asset_id, inclusion_probability, inclusion_flag, "
        "recent_effectiveness, days_below_threshold "
        "FROM p3_d02_aim_meta_weights"
    )
    for row in cur.fetchall():
        aim_id, asset_id, inc_prob, inc_flag, effectiveness, days_below = row
        if asset_id not in assets:
            continue
        aim_weights[(asset_id, aim_id)] = {
            "inclusion_probability": inc_prob if inc_prob is not None else 1.0,
            "inclusion_flag": inc_flag if inc_flag is not None else True,
            "recent_effectiveness": effectiveness or 0.0,
            "days_below_threshold": days_below or 0,
        }

    return aim_states, aim_weights


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of the given month."""
    # 1st day of month
    d = date(year, month, 1)
    # Find first Friday (weekday 4)
    offset = (4 - d.weekday()) % 7
    first_friday = d + timedelta(days=offset)
    # 3rd Friday = first Friday + 14 days
    return first_friday + timedelta(days=14)


def _pearson(x: list[float], y: list[float]):
    """Simple Pearson correlation. Returns None if degenerate."""
    n = min(len(x), len(y))
    if n < 5:
        return None
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    sx = sum((xi - mx) ** 2 for xi in x)
    sy = sum((yi - my) ** 2 for yi in y)
    if sx == 0 or sy == 0:
        return None
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    return sxy / (sx ** 0.5 * sy ** 0.5)
