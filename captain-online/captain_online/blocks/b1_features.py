# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B1A: Feature Computation Functions — Appendix A + B (Task 3.1b+3.1c / ON lines 225-601).

17 feature computation functions (Appendix A) + 11 data access utilities (Appendix B).
All functions are pure where possible; data access goes through adapter stubs.

Features computed per asset at session open:
  AIM-01: vrp, vrp_overnight
  AIM-02: pcr, put_skew
  AIM-03: gex
  AIM-04: ivts (CRITICAL regime filter)
  AIM-06: events_today, event_proximity
  AIM-07: cot_smi, cot_speculator_z
  AIM-08: correlation_20d, correlation_z
  AIM-09: cross_momentum
  AIM-10: is_opex_window, day_of_week
  AIM-11: vix_z, vix_daily_change_z, cl_basis (CL only)
  AIM-12: current_spread, spread_z
  AIM-15: opening_volume_ratio
  Common: overnight_return
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from shared.contract_resolver import resolve_contract_id
from shared.topstep_client import get_topstep_client, TopstepXClientError
from shared.topstep_stream import quote_cache

logger = logging.getLogger(__name__)


# ===========================================================================
# AIM-01: Volatility Risk Premium
# ===========================================================================

def compute_vrp(asset_id: str) -> Optional[float]:
    """VRP = Expected Realised Vol - Implied Vol.

    Positive = IV cheap (markets underpricing vol).
    Negative = IV expensive (markets overpricing vol).
    """
    iv = _get_atm_implied_vol(asset_id, maturity="30d")
    rv = _get_realised_vol(asset_id)

    if iv is None or rv is None:
        return None

    return rv - iv


def compute_overnight_vrp(asset_id: str) -> Optional[float]:
    """Overnight VRP: gap-implied vol vs realised overnight range."""
    overnight_range = _get_overnight_range(asset_id)
    iv_overnight = _get_atm_implied_vol(asset_id, maturity="1d")

    if iv_overnight is None or overnight_range is None:
        return None

    return overnight_range - iv_overnight


# ===========================================================================
# AIM-02: Options Skew
# ===========================================================================

def compute_put_call_ratio(asset_id: str) -> Optional[float]:
    """Put-Call Ratio: total put volume / total call volume (prior session)."""
    put_vol = _get_options_volume(asset_id, option_type="PUT")
    call_vol = _get_options_volume(asset_id, option_type="CALL")

    if call_vol is None or call_vol == 0:
        return None

    return put_vol / call_vol


def compute_dotm_otm_put_spread(asset_id: str) -> Optional[float]:
    """DOTM-OTM Put IV Spread: deep OTM put IV - slightly OTM put IV.

    Measures tail risk pricing. Positive = steep skew (crash risk elevated).
    """
    dotm_put_iv = _get_put_iv(asset_id, delta=0.10, maturity="30d")
    otm_put_iv = _get_put_iv(asset_id, delta=0.25, maturity="30d")

    if dotm_put_iv is None or otm_put_iv is None:
        return None

    return dotm_put_iv - otm_put_iv


# ===========================================================================
# AIM-03: Gamma Exposure
# ===========================================================================

def compute_dealer_net_gamma(asset_id: str) -> Optional[float]:
    """Dealer Net Gamma Exposure from open interest.

    GEX = SUM(dealer_net_OI * gamma * multiplier * spot^2) across strikes.
    Positive = positive gamma (dampening); negative = negative gamma (amplification).
    """
    spot = _get_latest_price(asset_id)
    option_chain = _get_option_chain(asset_id, max_maturity_days=30)

    if spot is None or spot <= 0 or option_chain is None or len(option_chain) == 0:
        return None

    gex = 0.0
    multiplier = _get_contract_multiplier(asset_id)
    risk_free_rate = _get_risk_free_rate()

    for opt in option_chain:
        gamma = _compute_bsm_gamma(
            spot, opt["strike"], opt["maturity_years"], opt["iv"], risk_free_rate
        )
        # Assume dealers are net short options
        dealer_net_oi = -opt["open_interest"]
        if opt["type"] == "PUT":
            dealer_net_oi = -dealer_net_oi  # put-call parity adjustment
        gex += dealer_net_oi * gamma * multiplier * spot * spot

    return gex


# ===========================================================================
# AIM-06: Economic Calendar
# ===========================================================================

def check_economic_calendar(date, asset_id: str) -> list[dict]:
    """Returns list of economic events on the given date relevant to the asset.

    Each event: {name, time, tier, expected}.
    Tier: 1=NFP/FOMC, 2=CPI/GDP, 3=EIA/ISM, 4=Housing/PPI.
    """
    all_events = _load_economic_calendar(date)
    relevant = []
    for event in all_events:
        affected = event.get("affected_assets", [])
        if asset_id in affected or event.get("scope") == "ALL":
            relevant.append({
                "name": event["name"],
                "time": event.get("time"),
                "tier": event.get("tier", 4),
                "expected": event.get("consensus"),
            })
    return relevant


def min_distance_to_event(events: list[dict], reference_time: datetime) -> Optional[float]:
    """Minutes between reference_time and nearest event.

    Negative = event before reference; positive = event after.
    """
    if not events:
        return None

    distances = []
    for event in events:
        event_time = event.get("time")
        if event_time is None:
            continue
        if isinstance(event_time, str):
            try:
                event_time = datetime.fromisoformat(event_time)
            except ValueError:
                continue
        delta = (event_time - reference_time).total_seconds() / 60.0
        distances.append(delta)

    if not distances:
        return None

    closest_idx = min(range(len(distances)), key=lambda i: abs(distances[i]))
    return distances[closest_idx]


# ===========================================================================
# AIM-07: COT Positioning
# ===========================================================================

def latest_smi_polarity(asset_id: str) -> Optional[int]:
    """Smart Money Index polarity from COT data.

    Returns: 1 (institutional net long), -1 (net short), 0 (neutral), None (no data).
    """
    cot = _load_latest_cot(asset_id)
    if cot is None:
        return None

    institutional = (
        cot.get("dealer_long", 0) - cot.get("dealer_short", 0)
        + cot.get("asset_mgr_long", 0) - cot.get("asset_mgr_short", 0)
    )
    retail = cot.get("nonreportable_long", 0) - cot.get("nonreportable_short", 0)

    if institutional > retail:
        return 1
    elif institutional < retail:
        return -1
    return 0


def speculator_z_score(asset_id: str) -> Optional[float]:
    """Large speculator net positioning as z-score vs 52-week history."""
    cot = _load_latest_cot(asset_id)
    cot_history = _load_cot_history(asset_id, weeks=52)

    if cot is None or len(cot_history) < 26:
        return None

    spec_net = cot.get("noncommercial_long", 0) - cot.get("noncommercial_short", 0)
    spec_history = [
        c.get("noncommercial_long", 0) - c.get("noncommercial_short", 0)
        for c in cot_history
    ]

    return z_score(spec_net, spec_history)


# ===========================================================================
# AIM-08: Cross-Asset Correlation
# ===========================================================================

def rolling_20d_correlation(asset1: str, asset2: str) -> Optional[float]:
    """20-trading-day rolling Pearson correlation of daily returns."""
    returns1 = _get_daily_returns(asset1, lookback=20)
    returns2 = _get_daily_returns(asset2, lookback=20)

    if returns1 is None or returns2 is None or len(returns1) < 20 or len(returns2) < 20:
        return None

    return float(np.corrcoef(returns1, returns2)[0, 1])


# ===========================================================================
# AIM-09: Cross-Asset Momentum
# ===========================================================================

def compute_cross_asset_momentum(asset_id: str, lookback: int = 21) -> Optional[float]:
    """Aggregate momentum signal from all traded assets using MACD.

    Returns: net direction -1 to +1.
    """
    all_assets = _get_all_universe_assets()
    signals = []

    for a in all_assets:
        closes = _get_daily_closes(a, lookback=max(26, lookback) + 9)
        if closes is None or len(closes) < 35:
            continue
        ema_12 = ema(closes, 12)
        ema_26 = ema(closes, 26)
        macd_line = [e12 - e26 for e12, e26 in zip(ema_12, ema_26)]
        signal_line_vals = ema(macd_line, 9)
        if macd_line[-1] > signal_line_vals[-1]:
            signals.append(1)
        else:
            signals.append(-1)

    if not signals:
        return None

    return sum(signals) / len(signals)


# ===========================================================================
# AIM-10: Calendar Effects
# ===========================================================================

def is_within_opex_window(date) -> bool:
    """True if date is within +/- 2 trading days of monthly options expiration.

    Monthly OPEX = 3rd Friday of each month.
    """
    third_friday = _get_third_friday(date.year, date.month)
    distance = _trading_days_between(date, third_friday)
    return abs(distance) <= 2


def _get_third_friday(year: int, month: int):
    """Get the 3rd Friday of a given month."""
    from datetime import date as dt_date
    # First day of month
    first_day = dt_date(year, month, 1)
    # Day of week: Monday=0 ... Friday=4
    first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
    third_friday = first_friday + timedelta(weeks=2)
    return third_friday


def _trading_days_between(date1, date2) -> int:
    """Count trading days between two dates (excludes weekends).

    Returns negative if date1 > date2.
    """
    if date1 == date2:
        return 0
    sign = 1 if date2 >= date1 else -1
    start, end = (date1, date2) if sign > 0 else (date2, date1)
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:  # Mon-Fri
            count += 1
        current += timedelta(days=1)
    return count * sign


# ===========================================================================
# AIM-12: Dynamic Costs
# ===========================================================================

def get_live_spread(asset_id: str) -> Optional[float]:
    """Current bid-ask spread in price units."""
    bid = _get_best_bid(asset_id)
    ask = _get_best_ask(asset_id)

    if bid is None or ask is None or bid <= 0:
        return None

    return ask - bid


# ===========================================================================
# AIM-15: Opening Volume
# ===========================================================================

def volume_first_N_min(asset_id: str, minutes: int) -> Optional[int]:
    """Total volume during the first N minutes of OR formation."""
    bars = _get_intraday_bars(asset_id, minutes)
    if bars is None or len(bars) == 0:
        return None
    return sum(b.get("volume", 0) for b in bars)


def avg_volume_first_N_min(asset_id: str, minutes: int, lookback: int = 20) -> Optional[float]:
    """Average volume during first N minutes across last `lookback` sessions."""
    historical = _get_historical_volume_first_N_min(asset_id, minutes, lookback)
    if historical is None or len(historical) < 5:
        return None
    return sum(historical) / len(historical)


# ===========================================================================
# General Utility Functions
# ===========================================================================

def z_score(value, trailing_series) -> Optional[float]:
    """Standard z-score: (value - mean) / std. None if insufficient data."""
    if trailing_series is None or len(trailing_series) < 10:
        return None

    arr = np.array(trailing_series, dtype=float)
    mu = float(np.mean(arr))
    sigma = float(np.std(arr))

    if sigma == 0:
        return 0.0

    return (value - mu) / sigma


def ema(series, span: int) -> list[float]:
    """Exponential moving average with given span."""
    if not series or len(series) == 0:
        return []
    alpha = 2.0 / (span + 1)
    result = [float(series[0])]
    for i in range(1, len(series)):
        result.append(alpha * float(series[i]) + (1 - alpha) * result[-1])
    return result


# ===========================================================================
# Appendix B — Data Access Utility Functions
# ===========================================================================

def close_price(asset_id: str, date) -> Optional[float]:
    """Yesterday's closing price from price_feed adapter."""
    return _get_prior_close_for_date(asset_id, date)


def get_current_session_volume(asset_id: str) -> int:
    """Current session's cumulative volume."""
    return _get_session_volume(asset_id) or 0


def avg_session_volume_20d(asset_id: str) -> Optional[float]:
    """20-day average session volume."""
    volumes = _get_historical_session_volumes(asset_id, lookback=20)
    if volumes is None or len(volumes) == 0:
        return None
    return sum(volumes) / len(volumes)


def get_required_features(asset_id: str, aim_states: dict) -> list[str]:
    """Return list of feature keys based on which AIMs are ACTIVE/BOOTSTRAPPED."""
    required = []
    for aim_id in range(1, 17):
        key = (asset_id, aim_id)
        state = aim_states.get("by_asset_aim", {}).get(key)
        if state and state["status"] in ("ACTIVE", "BOOTSTRAPPED", "ELIGIBLE"):
            required.extend(AIM_FEATURE_MAP.get(aim_id, []))
    return required


def feature_value(features: dict, asset_id: str, feature_name: str):
    """Current value of a computed feature."""
    return features.get(asset_id, {}).get(feature_name)


def get_last_known_value(asset_id: str, feature_name: str) -> Optional[float]:
    """Fallback: last known value from P3-D17 session history."""
    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute(
            """SELECT param_value FROM p3_d17_system_monitor_state
               WHERE param_key = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (f"feature_{asset_id}_{feature_name}",),
        )
        row = cur.fetchone()
    if row and row[0]:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            return None
    return None


def extract_classifier_features(asset_id: str, features: dict, regime_model: dict) -> list:
    """Maps features dict to the feature vector expected by P2-D07 classifier."""
    feature_list = regime_model.get("feature_list", [])
    feature_vector = []
    asset_features = features.get(asset_id, {})
    for fname in feature_list:
        feature_vector.append(asset_features.get(fname))
    return feature_vector


def get_return_bounds(ewma_state: dict) -> tuple[float, float]:
    """Distributional robust Kelly: return bounds from EWMA statistics.

    Paper 218: uncertainty set based on mean +/- k*sigma.
    Returns (lower_bound, upper_bound).
    """
    wr = ewma_state.get("win_rate", 0.5)
    avg_win = ewma_state.get("avg_win", 0.0)
    avg_loss = ewma_state.get("avg_loss", 0.0)

    mu = avg_win * wr - avg_loss * (1 - wr)
    variance = avg_win ** 2 * wr + avg_loss ** 2 * (1 - wr) - mu ** 2
    sigma = math.sqrt(max(0, variance))

    return (mu - 1.5 * sigma, mu + 1.5 * sigma)


def compute_robust_kelly(return_bounds: tuple[float, float], standard_kelly: float = 0.0) -> float:
    """Distributional robust Kelly: min-max approach (Paper 218).

    Maximises minimum growth over uncertainty set.
    """
    lower, upper = return_bounds
    if lower <= 0:
        return 0.3 * standard_kelly  # conservative fallback

    if upper * lower == 0:
        return 0.0

    robust_f = lower / (upper * lower)
    return max(0.0, min(robust_f, 0.5))  # cap at half-Kelly


def get_or_window_minutes(locked_strategy: dict) -> int:
    """OR formation window in minutes from strategy params."""
    strategy_params = locked_strategy.get("strategy_params", {})
    return strategy_params.get("OR_window_minutes", 15)


# ===========================================================================
# AIM → Feature mapping
# ===========================================================================

AIM_FEATURE_MAP = {
    1: ["vrp", "vrp_overnight"],
    2: ["pcr", "put_skew"],
    3: ["gex"],
    4: ["ivts"],
    5: [],  # AIM-05 is DEFERRED
    6: ["events_today", "event_proximity"],
    7: ["cot_smi", "cot_speculator_z"],
    8: ["correlation_20d", "correlation_z"],
    9: ["cross_momentum"],
    10: ["is_opex_window", "day_of_week"],
    11: ["vix_z", "vix_daily_change_z"],
    12: ["current_spread", "spread_z"],
    13: [],  # AIM-13 sensitivity — no features
    14: [],  # AIM-14 auto-expansion — outputs 1.0
    15: ["opening_volume_ratio"],
    16: [],  # AIM-16 HMM — trained offline, read from D26
}


# ===========================================================================
# Cross-asset correlation pairs (per asset)
# ===========================================================================

_CORRELATION_PAIRS = {
    "ES": ("ES", "CL"),   "MES": ("ES", "CL"),
    "NQ": ("NQ", "ES"),   "MNQ": ("NQ", "ES"),
    "M2K": ("M2K", "ES"), "MYM": ("MYM", "ES"),
    "NKD": ("NKD", "ES"),
    "MGC": ("MGC", "ES"),
    "ZB": ("ZB", "ES"),   "ZN": ("ZN", "ES"),
    "CL": ("CL", "ES"),
}


def _get_correlation_pair(asset_id: str) -> tuple[str, str] | None:
    """Return the correlation pair for a given asset, or None if unmapped."""
    return _CORRELATION_PAIRS.get(asset_id)


# ===========================================================================
# Master feature computation entry point
# ===========================================================================

def compute_all_features(
    assets: list[dict],
    aim_states: dict,
    locked_strategies: dict,
) -> dict[str, dict]:
    """Compute all features for all assets.

    Returns: {asset_id: {feature_name: value, ...}, ...}
    """
    today = datetime.now()
    features = {}

    for asset in assets:
        asset_id = asset["asset_id"]
        f = {}

        # Overnight return (always computed)
        open_price = _get_open_price(asset_id, today)
        prior_close = _get_prior_close_for_date(asset_id, today - timedelta(days=1))
        if open_price and prior_close and prior_close > 0:
            f["overnight_return"] = (open_price / prior_close) - 1
        else:
            f["overnight_return"] = None

        # AIM-01: VRP (if active)
        aim01_state = aim_states.get("by_asset_aim", {}).get((asset_id, 1))
        if aim01_state and aim01_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["vrp"] = compute_vrp(asset_id)
            f["vrp_overnight"] = compute_overnight_vrp(asset_id)

        # AIM-04: IVTS (CRITICAL regime filter — always compute if available)
        vix_close = _get_vix_close_yesterday()
        vxv_close = _get_vxv_close_yesterday()
        if vix_close and vxv_close and vxv_close > 0:
            f["ivts"] = vix_close / vxv_close
        else:
            f["ivts"] = None

        # AIM-15: Opening volume ratio
        aim15_state = aim_states.get("by_asset_aim", {}).get((asset_id, 15))
        if aim15_state and aim15_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            strategy = locked_strategies.get(asset_id, {})
            or_minutes = get_or_window_minutes(strategy)
            vol_now = volume_first_N_min(asset_id, or_minutes)
            vol_avg = avg_volume_first_N_min(asset_id, or_minutes)
            if vol_now is not None and vol_avg is not None and vol_avg > 0:
                f["opening_volume_ratio"] = vol_now / vol_avg
            else:
                f["opening_volume_ratio"] = None

        # AIM-06: Economic calendar
        aim06_state = aim_states.get("by_asset_aim", {}).get((asset_id, 6))
        if aim06_state and aim06_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["events_today"] = check_economic_calendar(today.date(), asset_id)
            session_open = _get_session_open_time(asset_id)
            f["event_proximity"] = min_distance_to_event(f["events_today"], session_open or today)

        # AIM-07: COT positioning
        aim07_state = aim_states.get("by_asset_aim", {}).get((asset_id, 7))
        if aim07_state and aim07_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["cot_smi"] = latest_smi_polarity(asset_id)
            f["cot_speculator_z"] = speculator_z_score(asset_id)

        # AIM-08: Cross-asset correlation (dynamic per-asset pairs)
        aim08_state = aim_states.get("by_asset_aim", {}).get((asset_id, 8))
        if aim08_state and aim08_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            correlation_pair = _get_correlation_pair(asset_id)
            if correlation_pair:
                f["correlation_pair"] = correlation_pair
                f["correlation_20d"] = rolling_20d_correlation(correlation_pair[0], correlation_pair[1])
                trailing_252d = _get_trailing_correlations(correlation_pair[0], correlation_pair[1], lookback=252)
                corr_val = f["correlation_20d"]
                if corr_val is not None and trailing_252d is not None:
                    f["correlation_z"] = z_score(corr_val, trailing_252d)
                else:
                    f["correlation_z"] = None
            else:
                f["correlation_20d"] = None
                f["correlation_z"] = None

        # AIM-09: Cross-asset momentum
        aim09_state = aim_states.get("by_asset_aim", {}).get((asset_id, 9))
        if aim09_state and aim09_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["cross_momentum"] = compute_cross_asset_momentum(asset_id, lookback=21)

        # AIM-03: GEX
        aim03_state = aim_states.get("by_asset_aim", {}).get((asset_id, 3))
        if aim03_state and aim03_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["gex"] = compute_dealer_net_gamma(asset_id)

        # AIM-02: Skew
        aim02_state = aim_states.get("by_asset_aim", {}).get((asset_id, 2))
        if aim02_state and aim02_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["pcr"] = compute_put_call_ratio(asset_id)
            f["put_skew"] = compute_dotm_otm_put_spread(asset_id)

        # AIM-10: Calendar
        aim10_state = aim_states.get("by_asset_aim", {}).get((asset_id, 10))
        if aim10_state and aim10_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["is_opex_window"] = is_within_opex_window(today.date())
            f["day_of_week"] = today.weekday()

        # AIM-11: Regime warning (VIX)
        aim11_state = aim_states.get("by_asset_aim", {}).get((asset_id, 11))
        if aim11_state and aim11_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            trailing_252d_vix = _get_trailing_vix(lookback=252)
            if vix_close is not None and trailing_252d_vix is not None:
                f["vix_z"] = z_score(vix_close, trailing_252d_vix)
            else:
                f["vix_z"] = None

            trailing_60d_vix_changes = _get_trailing_vix_daily_changes(lookback=60)
            vix_change = _get_vix_change_today()
            if vix_change is not None and trailing_60d_vix_changes is not None:
                f["vix_daily_change_z"] = z_score(abs(vix_change), trailing_60d_vix_changes)
            else:
                f["vix_daily_change_z"] = None

            # CL-specific: basis
            if asset_id == "CL":
                cl_spot = _get_cl_spot()
                cl_front = _get_cl_front_futures()
                if cl_spot and cl_front and cl_spot > 0:
                    f["cl_basis"] = (cl_spot - cl_front) / cl_spot
                else:
                    f["cl_basis"] = None

        # AIM-12: Dynamic costs
        aim12_state = aim_states.get("by_asset_aim", {}).get((asset_id, 12))
        if aim12_state and aim12_state["status"] in ("ACTIVE", "BOOTSTRAPPED"):
            f["current_spread"] = get_live_spread(asset_id)
            trailing_60d_spreads = _get_trailing_spreads(asset_id, lookback=60)
            if f["current_spread"] is not None and trailing_60d_spreads is not None:
                f["spread_z"] = z_score(f["current_spread"], trailing_60d_spreads)
            else:
                f["spread_z"] = None

        features[asset_id] = f
        logger.debug("ON-B1A: %s — %d features computed", asset_id,
                      len([v for v in f.values() if v is not None]))

    return features


# ===========================================================================
# Market data adapter stubs — replaced by real feeds in integration
# ===========================================================================
# These functions return None/empty to allow the system to run without
# live data feeds. In production, each will connect to the appropriate
# data source (broker API, CBOE, CFTC, etc.).

def _get_latest_price(asset_id: str) -> Optional[float]:
    """Latest price from TopstepX stream cache or REST fallback."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    quote = quote_cache.get(contract_id)
    if quote and quote.get("lastPrice"):
        return float(quote["lastPrice"])
    try:
        client = get_topstep_client()
        now = datetime.now(timezone.utc)
        bars = client.get_bars(
            contract_id, 2, 1,
            (now - timedelta(minutes=5)).isoformat(), now.isoformat(),
        )
        if bars:
            return float(bars[-1]["close"])
    except TopstepXClientError:
        pass
    return None

def _get_open_price(asset_id: str, date) -> Optional[float]:
    """Today's open from TopstepX stream cache or daily bar."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    quote = quote_cache.get(contract_id)
    if quote and quote.get("open"):
        return float(quote["open"])
    try:
        client = get_topstep_client()
        d = date if hasattr(date, 'isoformat') else datetime.now(timezone.utc).date()
        bars = client.get_bars(
            contract_id, 4, 1, d.isoformat(), d.isoformat(),
        )
        if bars:
            return float(bars[0]["open"])
    except TopstepXClientError:
        pass
    return None

def _get_prior_close_for_date(asset_id: str, date) -> Optional[float]:
    """Previous close from TopstepX daily bars."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    try:
        client = get_topstep_client()
        d = date if hasattr(date, 'isoformat') else datetime.now(timezone.utc).date()
        start = (d - timedelta(days=5)).isoformat()
        end = (d - timedelta(days=1)).isoformat()
        bars = client.get_bars(contract_id, 4, 1, start, end)
        if bars:
            return float(bars[-1]["close"])
    except TopstepXClientError:
        pass
    return None

def _get_session_volume(asset_id: str) -> Optional[int]:
    """Current session volume from stream cache."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    quote = quote_cache.get(contract_id)
    if quote and quote.get("volume") is not None:
        return int(quote["volume"])
    return None

def _get_historical_session_volumes(asset_id: str, lookback: int = 20) -> Optional[list[int]]:
    """Historical daily volumes from TopstepX."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    try:
        client = get_topstep_client()
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=lookback + 10)).isoformat()
        end = (today - timedelta(days=1)).isoformat()
        bars = client.get_bars(contract_id, 4, 1, start, end)
        if bars:
            return [int(b.get("volume", 0)) for b in bars[-lookback:]]
    except TopstepXClientError:
        pass
    return None

def _get_atm_implied_vol(asset_id: str, maturity: str = "30d") -> Optional[float]:
    return None

def _get_realised_vol(asset_id: str) -> Optional[float]:
    return None

def _get_overnight_range(asset_id: str) -> Optional[float]:
    return None

def _get_options_volume(asset_id: str, option_type: str = "PUT") -> Optional[int]:
    return None

def _get_put_iv(asset_id: str, delta: float = 0.10, maturity: str = "30d") -> Optional[float]:
    return None

def _get_option_chain(asset_id: str, max_maturity_days: int = 30) -> Optional[list[dict]]:
    return None

def _get_contract_multiplier(asset_id: str) -> float:
    return 50.0  # ES default

def _get_risk_free_rate() -> float:
    return 0.05  # approximate

def _compute_bsm_gamma(spot, strike, maturity_years, iv, risk_free_rate) -> float:
    """Black-Scholes-Merton gamma computation."""
    if iv is None or iv <= 0 or maturity_years is None or maturity_years <= 0:
        return 0.0
    try:
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv ** 2) * maturity_years) / (
            iv * math.sqrt(maturity_years)
        )
        gamma = math.exp(-0.5 * d1 ** 2) / (
            spot * iv * math.sqrt(2 * math.pi * maturity_years)
        )
        return gamma
    except (ValueError, ZeroDivisionError):
        return 0.0

def _load_economic_calendar(date) -> list[dict]:
    return []

def _load_latest_cot(asset_id: str) -> Optional[dict]:
    return None

def _load_cot_history(asset_id: str, weeks: int = 52) -> list[dict]:
    return []

def _get_daily_returns(asset_id: str, lookback: int = 20) -> Optional[list[float]]:
    """Compute daily returns from TopstepX daily bars."""
    closes = _get_daily_closes(asset_id, lookback + 1)
    if closes and len(closes) >= 2:
        return [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes))]
    return None

def _get_daily_closes(asset_id: str, lookback: int = 35) -> Optional[list[float]]:
    """Daily close prices from TopstepX."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    try:
        client = get_topstep_client()
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=lookback + 10)).isoformat()
        end = (today - timedelta(days=1)).isoformat()
        bars = client.get_bars(contract_id, 4, 1, start, end)
        if bars:
            return [float(b["close"]) for b in bars[-lookback:]]
    except TopstepXClientError:
        pass
    return None

def _get_all_universe_assets() -> list[str]:
    """Get all asset IDs in the universe from P3-D00."""
    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute(
            "SELECT DISTINCT asset_id FROM p3_d00_asset_universe"
        )
        rows = cur.fetchall()
    return [r[0] for r in rows] if rows else []

def _get_session_open_time(asset_id: str) -> Optional[datetime]:
    """Session open time — ES regular trading hours 9:30 ET."""
    try:
        import pytz
        et = pytz.timezone("America/New_York")
        now_et = datetime.now(et)
        return now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    except ImportError:
        now = datetime.now(timezone.utc)
        return now.replace(hour=14, minute=30, second=0, microsecond=0)  # 9:30 ET = 14:30 UTC

def _get_best_bid(asset_id: str) -> Optional[float]:
    """Best bid from TopstepX stream cache."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    quote = quote_cache.get(contract_id)
    if quote and quote.get("bestBid") is not None:
        return float(quote["bestBid"])
    return None

def _get_best_ask(asset_id: str) -> Optional[float]:
    """Best ask from TopstepX stream cache."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    quote = quote_cache.get(contract_id)
    if quote and quote.get("bestAsk") is not None:
        return float(quote["bestAsk"])
    return None

def _get_intraday_bars(asset_id: str, minutes: int) -> Optional[list[dict]]:
    """Intraday minute bars from TopstepX REST."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    try:
        client = get_topstep_client()
        now = datetime.now(timezone.utc)
        # Fetch today's bars at the requested minute resolution
        start = now.replace(hour=0, minute=0, second=0).isoformat()
        bars = client.get_bars(
            contract_id, 2, minutes,  # barUnit=2 (Minute)
            start, now.isoformat(),
        )
        return bars if bars else None
    except TopstepXClientError:
        pass
    return None

def _get_historical_volume_first_N_min(asset_id: str, minutes: int, lookback: int = 20) -> Optional[list[int]]:
    """Historical opening N-minute volumes from TopstepX.

    Fetches daily bars and uses them as a proxy — exact first-N-min
    volumes would require intraday bars for each historical day.
    """
    # Not directly available from TopstepX without per-day intraday queries.
    # Leave as None — AIM-15 will gracefully degrade.
    return None

def _get_vix_close_yesterday() -> Optional[float]:
    """Most recent VIX daily close from CSV provider."""
    from shared.vix_provider import get_latest_vix_close
    return get_latest_vix_close()

def _get_vxv_close_yesterday() -> Optional[float]:
    """Most recent VXV (Cboe 3-month vol) close from CSV provider."""
    from shared.vix_provider import get_latest_vxv_close
    return get_latest_vxv_close()

def _get_trailing_vix(lookback: int = 252) -> Optional[list[float]]:
    """Trailing VIX daily closes for z-score computation."""
    from shared.vix_provider import get_trailing_vix_closes
    return get_trailing_vix_closes(lookback)

def _get_trailing_vix_daily_changes(lookback: int = 60) -> Optional[list[float]]:
    """Trailing absolute VIX daily changes for z-score computation."""
    from shared.vix_provider import get_trailing_vix_daily_changes
    return get_trailing_vix_daily_changes(lookback)

def _get_vix_change_today() -> Optional[float]:
    """Most recent VIX daily change (close[t] - close[t-1])."""
    from shared.vix_provider import get_vix_change_latest
    return get_vix_change_latest()

def _get_cl_spot() -> Optional[float]:
    return None

def _get_cl_front_futures() -> Optional[float]:
    return None

def _get_trailing_spreads(asset_id: str, lookback: int = 60) -> Optional[list[float]]:
    return None

def _get_trailing_correlations(asset1: str, asset2: str, lookback: int = 252) -> Optional[list[float]]:
    return None
