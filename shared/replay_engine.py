# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Reusable replay engine — extracted from scripts/replay_session.py.

READ-ONLY: No trades placed, no QuestDB writes, no Redis publishes.

Provides structured, importable functions for:
  - Loading replay configuration from QuestDB (strategies, kelly, ewma, TSM, capital)
  - Fetching session bars from TopstepX (with SQLite WAL bar_cache)
  - Simulating ORB breakouts with TP/SL/EOD exit logic
  - Computing contract sizing via full B4 Kelly pipeline
  - Applying position limits by edge ranking
  - Running a full replay with optional streaming callbacks
  - Running what-if reruns with parameter overrides (no API calls)
"""

import json
import logging
import math
import os
from datetime import datetime, timedelta, date, time as dtime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session config (from session_registry.json)
# ---------------------------------------------------------------------------

SESSION_CONFIG = {
    "NY":     {"or_start": "09:30", "or_end": "09:35", "eod": "15:55"},
    "NY_PRE": {"or_start": "06:00", "or_end": "06:05", "eod": "13:25"},
    "LONDON": {"or_start": "03:00", "or_end": "03:05", "eod": "11:25"},
    "APAC":   {"or_start": "18:00", "or_end": "18:05", "eod": "02:55"},
}

ASSET_SESSION_MAP = {
    "ES": "NY", "MES": "NY", "NQ": "NY", "MNQ": "NY",
    "M2K": "NY", "MYM": "NY",
    "NKD": "APAC",
    "MGC": "LONDON",
    "ZB": "NY_PRE", "ZN": "NY_PRE",
}

ACTIVE_ASSETS = list(ASSET_SESSION_MAP.keys())

SESSION_ID_MAP = {"NY": 1, "LONDON": 2, "APAC": 3, "NY_PRE": 1}


# ---------------------------------------------------------------------------
# Config loading (READ-ONLY on QuestDB)
# ---------------------------------------------------------------------------

def load_replay_config(overrides: dict | None = None) -> dict:
    """Load all config from QuestDB (strategies, kelly, ewma, capital, tsm).

    Apply overrides dict on top WITHOUT writing to QuestDB.
    Returns full config dict with all parameters needed for replay.

    Overrides can contain any top-level key (e.g. ``user_capital``,
    ``max_contracts``, ``tp_multiple``, ``sl_multiple``, ``budget_divisor``,
    ``cb_enabled``) plus nested dicts like ``strategies`` or ``kelly_params``
    that are merged into the loaded values.
    """
    from shared.questdb_client import get_cursor

    # --- Locked strategies + asset specs from D00 ---
    strategies = {}
    specs = {}
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, locked_strategy, point_value, tick_size, "
            "margin_per_contract "
            "FROM p3_d00_asset_universe ORDER BY last_updated DESC"
        )
        seen = set()
        for r in cur.fetchall():
            if r[0] in seen:
                continue
            seen.add(r[0])
            if r[0] in ACTIVE_ASSETS and r[1]:
                try:
                    strategies[r[0]] = (
                        json.loads(r[1]) if isinstance(r[1], str) else r[1]
                    )
                except (json.JSONDecodeError, TypeError):
                    strategies[r[0]] = {}
                specs[r[0]] = {
                    "point_value": r[2] or 50.0,
                    "tick_size": r[3] or 0.25,
                    "margin": r[4] or 0.0,
                }

    # --- Kelly params from D12 ---
    kelly_params = {}
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, regime, session, kelly_full, shrinkage_factor "
            "FROM p3_d12_kelly_parameters ORDER BY last_updated DESC"
        )
        seen = set()
        for r in cur.fetchall():
            key = (r[0], r[1], r[2])
            if key in seen:
                continue
            seen.add(key)
            kelly_params[key] = {
                "kelly_full": r[3] or 0.0,
                "shrinkage_factor": r[4] or 1.0,
            }

    # --- EWMA states from D05 ---
    ewma_states = {}
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, regime, session, win_rate, avg_win, avg_loss "
            "FROM p3_d05_ewma_states ORDER BY last_updated DESC"
        )
        seen = set()
        for r in cur.fetchall():
            key = (r[0], r[1], r[2])
            if key in seen:
                continue
            seen.add(key)
            ewma_states[key] = {
                "win_rate": r[3] or 0.5,
                "avg_win": r[4] or 0.0,
                "avg_loss": r[5] or 0.0,
            }

    # --- Capital silo from D16 ---
    with get_cursor() as cur:
        cur.execute(
            "SELECT total_capital, accounts, max_simultaneous_positions "
            "FROM p3_d16_user_capital_silos "
            "WHERE user_id = 'primary_user' "
            "ORDER BY last_updated DESC LIMIT 1"
        )
        row = cur.fetchone()
    user_capital = row[0] if row else 150000.0
    max_positions = row[2] if row else 5

    # Extract dynamic account_id from D16 accounts list
    _accounts_raw = row[1] if row else None
    if isinstance(_accounts_raw, str):
        try:
            _accounts_raw = json.loads(_accounts_raw)
        except (json.JSONDecodeError, TypeError):
            _accounts_raw = None
    if isinstance(_accounts_raw, list) and _accounts_raw:
        _dynamic_account_id = str(_accounts_raw[0])
    else:
        _dynamic_account_id = "20319811"  # fallback

    # --- TSM state from D08 ---
    tsm = {}
    topstep_params = {}
    risk_goal = "GROW_CAPITAL"
    max_contracts = 15
    mdd_limit = 4500.0
    mll_limit = 2250.0
    current_drawdown = 0.0
    daily_loss_used = 0.0

    with get_cursor() as cur:
        cur.execute(
            "SELECT account_id, classification, starting_balance, "
            "current_balance, current_drawdown, daily_loss_used, "
            "max_drawdown_limit, max_daily_loss, max_contracts, "
            "topstep_optimisation, risk_goal "
            "FROM p3_d08_tsm_state WHERE account_id = %s "
            "ORDER BY last_updated DESC LIMIT 1",
            (_dynamic_account_id,)
        )
        row = cur.fetchone()
    if row:
        classification = row[1]
        if isinstance(classification, str):
            try:
                classification = json.loads(classification)
            except (json.JSONDecodeError, TypeError):
                classification = {}
        topstep_opt = row[9]
        if isinstance(topstep_opt, str):
            try:
                topstep_params = json.loads(topstep_opt)
            except (json.JSONDecodeError, TypeError):
                topstep_params = {}
        elif isinstance(topstep_opt, dict):
            topstep_params = topstep_opt
        risk_goal = (
            row[10]
            or (classification.get("risk_goal", "GROW_CAPITAL")
                if classification else "GROW_CAPITAL")
        )
        max_contracts = row[8] or 15
        mdd_limit = row[6] or 4500.0
        mll_limit = row[7] or 2250.0
        current_drawdown = row[4] or 0.0
        daily_loss_used = row[5] or 0.0
        tsm = {
            "account_id": row[0],
            "classification": classification,
            "starting_balance": row[2] or 150000,
            "current_balance": row[3] or 150000,
            "current_drawdown": current_drawdown,
            "daily_loss_used": daily_loss_used,
            "max_drawdown_limit": mdd_limit,
            "max_daily_loss": mll_limit,
            "max_contracts": max_contracts,
            "topstep_params": topstep_params,
            "risk_goal": risk_goal,
            "pass_probability": (
                classification.get("pass_probability", 0.6)
                if isinstance(classification, dict) else 0.6
            ),
            "evaluation_end_date": (
                classification.get("evaluation_end_date")
                if isinstance(classification, dict) else None
            ),
            "fee_per_trade": (
                topstep_params.get("round_turn_fee",
                                   topstep_params.get("fee_per_trade", 2.80))
                if topstep_params else 2.80
            ),
        }

    # --- Contract IDs from config file ---
    contracts = {}
    for config_path in [
        "/app/contract_ids.json",
        "/captain/config/contract_ids.json",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config",
            "contract_ids.json",
        ),
    ]:
        if os.path.exists(config_path):
            with open(config_path) as f:
                cdata = json.load(f)
            for asset_id, info in cdata.get("contracts", {}).items():
                cid = info.get("contract_id")
                if cid:
                    contracts[asset_id] = cid
            break

    # --- Trade counts from D03 (for quality gate data maturity) ---
    trade_counts = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT asset, count() as cnt FROM p3_d03_trade_outcome_log "
                "GROUP BY asset"
            )
            for r in cur.fetchall():
                trade_counts[r[0]] = r[1]
    except Exception:
        pass  # D03 may be empty on fresh systems

    # --- Correlation matrix from D07 (for cross-asset filter) ---
    correlation_matrix = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT correlation_matrix FROM p3_d07_correlation_model_states "
                "ORDER BY last_updated DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row and row[0]:
                correlation_matrix = (
                    json.loads(row[0]) if isinstance(row[0], str) else row[0]
                )
    except Exception:
        pass  # D07 may not be populated yet

    # --- CB basket parameters from D25 (for L2/L3 circuit breaker) ---
    cb_params = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT account_id, model_m, r_bar, beta_b, sigma, rho_bar, "
                "n_observations, p_value "
                "FROM p3_d25_circuit_breaker ORDER BY last_updated DESC"
            )
            seen_cb = set()
            for r in cur.fetchall():
                key = (r[0], str(r[1]) if r[1] is not None else "0")
                if key in seen_cb:
                    continue
                seen_cb.add(key)
                cb_params[key] = {
                    "r_bar": r[2] or 0.0,
                    "beta_b": r[3] or 0.0,
                    "sigma": r[4] or 0.0,
                    "rho_bar": r[5] or 0.0,
                    "n_observations": r[6] or 0,
                    "p_value": r[7] or 1.0,
                }
    except Exception:
        pass  # D25 may not be populated yet

    # --- HMM opportunity state from D26 (for session allocation) ---
    hmm_state = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT hmm_params "
                "FROM p3_d26_hmm_opportunity_state "
                "ORDER BY last_updated DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row and row[0]:
                _hmm_raw = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                if isinstance(_hmm_raw, dict):
                    hmm_state = _hmm_raw
    except Exception:
        pass  # D26 may not be populated yet

    # Compute budget_divisor from evaluation_end_date (b4_kelly_sizing.py:332-341)
    _budget_divisor = 20
    _eval_end = tsm.get("evaluation_end_date")
    if _eval_end:
        try:
            if isinstance(_eval_end, str):
                _eval_end_dt = date.fromisoformat(_eval_end)
            elif isinstance(_eval_end, date):
                _eval_end_dt = _eval_end
            else:
                _eval_end_dt = None
            if _eval_end_dt:
                _remaining = (_eval_end_dt - date.today()).days
                _budget_divisor = max(_remaining, 1)
        except (ValueError, TypeError):
            pass

    # --- Assemble config dict ---
    config = {
        "user_capital": user_capital,
        "max_contracts": max_contracts,
        "max_positions": max_positions,
        "budget_divisor": _budget_divisor,
        "risk_goal": risk_goal,
        "cb_enabled": True,
        "tp_multiple": 0.70,
        "sl_multiple": 0.35,
        "mdd_limit": mdd_limit,
        "mll_limit": mll_limit,
        "current_drawdown": current_drawdown,
        "daily_loss_used": daily_loss_used,
        "strategies": strategies,
        "specs": specs,
        "kelly_params": kelly_params,
        "ewma_states": ewma_states,
        "contracts": contracts,
        "trade_counts": trade_counts,
        "correlation_matrix": correlation_matrix,
        "topstep_params": topstep_params if topstep_params else {"c": 0.5, "e": 0.01},
        "cb_params": cb_params,
        "hmm_state": hmm_state,
        "session_config": SESSION_CONFIG,
        "asset_session_map": ASSET_SESSION_MAP,
        # Keep full TSM for compute_contracts
        "_tsm": tsm,
    }

    # --- Apply overrides WITHOUT writing to QuestDB ---
    if overrides:
        for key, value in overrides.items():
            if key in ("strategies", "specs", "kelly_params", "ewma_states"):
                # Merge nested dicts rather than replacing wholesale
                if isinstance(value, dict):
                    config[key].update(value)
            else:
                config[key] = value

    return config


# ---------------------------------------------------------------------------
# Bar parsing helpers
# ---------------------------------------------------------------------------

def parse_bar_time(bar: dict) -> datetime | None:
    """Extract timestamp from a bar dict.

    TopstepX retrieveBars returns:
        {"t": "2026-03-26T13:30:00+00:00", "o", "h", "l", "c", "v"}
    """
    for key in ("t", "timestamp", "time", "dateTime", "barTime"):
        val = bar.get(key)
        if val:
            try:
                if isinstance(val, str):
                    val = val.replace("Z", "+00:00")
                    return datetime.fromisoformat(val)
                elif isinstance(val, (int, float)):
                    return datetime.fromtimestamp(
                        val / 1000 if val > 1e12 else val,
                        tz=timezone.utc,
                    )
            except (ValueError, OSError):
                continue
    return None


def get_bar_field(bar: dict, field: str) -> float | None:
    """Get a numeric field from a bar.

    TopstepX uses single-letter keys: o, h, l, c, v.
    """
    _field_map = {
        "open": "o", "high": "h", "low": "l", "close": "c", "volume": "v",
    }
    short = _field_map.get(field.lower(), field.lower())
    for key in (short, field, field.lower(), field.upper(), field.capitalize()):
        val = bar.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


# ---------------------------------------------------------------------------
# Bar fetching (with cache)
# ---------------------------------------------------------------------------

def _fetch_bars_from_api(
    client,
    contract_id: str,
    target_date: date,
    session_type: str,
) -> list[dict]:
    """Fetch 1-minute bars for a full session from TopstepX.

    Uses /History/retrieveBars endpoint with flat payload format.
    TopstepX returns bars in REVERSE chronological order (newest first).
    Timestamps are UTC.
    """
    import requests
    from zoneinfo import ZoneInfo

    cfg = SESSION_CONFIG[session_type]

    # For APAC, the session starts the evening BEFORE target_date
    if session_type == "APAC":
        start_day = target_date - timedelta(days=1)
    else:
        start_day = target_date

    or_start = datetime.strptime(cfg["or_start"], "%H:%M").time()
    eod = datetime.strptime(cfg["eod"], "%H:%M").time()

    # Convert ET times to UTC for API (ET = UTC-4 during EDT)
    et = ZoneInfo("America/New_York")

    fetch_start = (
        datetime.combine(start_day, or_start, tzinfo=et)
        - timedelta(minutes=5)
    )
    fetch_end = (
        datetime.combine(
            target_date if session_type != "APAC" else target_date,
            eod,
            tzinfo=et,
        )
        + timedelta(minutes=30)
    )

    start_utc = fetch_start.astimezone(ZoneInfo("UTC")).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    end_utc = fetch_end.astimezone(ZoneInfo("UTC")).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    url = "https://api.topstepx.com/api/History/retrieveBars"
    headers = client._auth_headers()
    payload = {
        "contractId": contract_id,
        "live": False,
        "startTime": start_utc,
        "endTime": end_utc,
        "unit": 2,        # Minute
        "unitNumber": 1,  # 1-minute bars
        "limit": 1000,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code != 200:
        logger.warning(
            "retrieveBars HTTP %d for contract %s", resp.status_code, contract_id,
        )
        return []
    data = resp.json()
    bars = data.get("bars", [])
    # Reverse to chronological order (oldest first)
    bars.reverse()
    return bars


def fetch_session_bars(
    client,
    asset_id: str,
    contract_id: str,
    target_date: date,
    session_type: str,
    use_cache: bool = True,
) -> list[dict]:
    """Fetch bars from TopstepX, using bar_cache if available.

    On cache miss, fetches from API and caches result.
    """
    bar_date_str = target_date.isoformat()

    # Try cache first
    if use_cache:
        try:
            from shared.bar_cache import get_cached_bars, cache_bars

            cached = get_cached_bars(asset_id, bar_date_str, session_type)
            if cached is not None:
                logger.info(
                    "bar_cache HIT: %s %s %s (%d bars)",
                    asset_id, bar_date_str, session_type, len(cached),
                )
                return cached
        except Exception as exc:
            logger.debug("bar_cache unavailable: %s", exc)

    # Fetch from API
    bars = _fetch_bars_from_api(client, contract_id, target_date, session_type)

    # Cache the result
    if use_cache and bars:
        try:
            from shared.bar_cache import cache_bars

            cache_bars(asset_id, bar_date_str, session_type, bars)
        except Exception as exc:
            logger.debug("bar_cache store failed: %s", exc)

    return bars


# ---------------------------------------------------------------------------
# ORB Simulation
# ---------------------------------------------------------------------------

def simulate_orb(
    bars: list[dict],
    asset_id: str,
    session_type: str,
    target_date: date,
    strategy: dict,
    spec: dict,
) -> dict:
    """Simulate ORB for one asset on one date.

    Returns dict with or_high, or_low, direction, entry_price, exit_price,
    pnl_per_contract, etc.  On error or no-breakout the dict includes an
    ``error`` key or ``result`` == ``"NO_BREAKOUT"``.
    """
    cfg = SESSION_CONFIG[session_type]
    or_start = datetime.strptime(cfg["or_start"], "%H:%M").time()
    or_end = datetime.strptime(cfg["or_end"], "%H:%M").time()
    eod = datetime.strptime(cfg["eod"], "%H:%M").time()

    if not bars:
        return {"asset": asset_id, "error": "No bars returned from API"}

    # Parse bars and filter by time
    parsed = []
    for bar in bars:
        t = parse_bar_time(bar)
        if t is None:
            continue
        # Convert to naive ET for comparison
        if t.tzinfo:
            from zoneinfo import ZoneInfo

            t_et = t.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
        else:
            t_et = t
        h = get_bar_field(bar, "high")
        l = get_bar_field(bar, "low")
        c = get_bar_field(bar, "close")
        o = get_bar_field(bar, "open")
        if h is not None and l is not None and c is not None:
            parsed.append({
                "time": t_et,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
            })

    if not parsed:
        return {
            "asset": asset_id,
            "error": f"No parseable bars (raw count: {len(bars)})",
        }

    # For APAC, the OR date is the evening before
    if session_type == "APAC":
        or_date = target_date - timedelta(days=1)
    else:
        or_date = target_date

    # Filter to OR window
    or_start_dt = datetime.combine(or_date, or_start)
    or_end_dt = datetime.combine(or_date, or_end)

    or_bars = [b for b in parsed if or_start_dt <= b["time"] < or_end_dt]

    if not or_bars:
        times = [b["time"].strftime("%H:%M") for b in parsed[:10]]
        return {
            "asset": asset_id,
            "error": (
                f"No bars in OR window {or_start}-{or_end} "
                f"(have {len(parsed)} bars, times: {times}...)"
            ),
        }

    or_high = max(b["high"] for b in or_bars)
    or_low = min(b["low"] for b in or_bars)
    or_range = or_high - or_low

    if or_range <= 0:
        return {
            "asset": asset_id,
            "error": f"OR range is zero ({or_high}={or_low})",
        }

    # Post-OR bars (after OR closes, until EOD)
    eod_date = target_date if session_type != "APAC" else target_date
    eod_dt = datetime.combine(eod_date, eod)
    post_or = [b for b in parsed if b["time"] >= or_end_dt and b["time"] <= eod_dt]

    if not post_or:
        return {
            "asset": asset_id,
            "error": (
                f"No post-OR bars (OR ends {or_end}, "
                f"last bar: {parsed[-1]['time'].strftime('%H:%M')})"
            ),
        }

    # Detect breakout
    direction = 0
    entry_price = None
    breakout_time = None

    for bar in post_or:
        high_breach = bar["high"] > or_high
        low_breach = bar["low"] < or_low
        if high_breach and low_breach:
            # Simultaneous breach: pick by penetration depth (matching live ORTracker)
            high_pen = bar["high"] - or_high
            low_pen = or_low - bar["low"]
            if high_pen >= low_pen:
                direction = 1  # LONG
                entry_price = or_high
            else:
                direction = -1  # SHORT
                entry_price = or_low
            breakout_time = bar["time"]
            break
        elif high_breach:
            direction = 1  # LONG breakout
            entry_price = or_high
            breakout_time = bar["time"]
            break
        elif low_breach:
            direction = -1  # SHORT breakout
            entry_price = or_low
            breakout_time = bar["time"]
            break

    if direction == 0:
        return {
            "asset": asset_id,
            "or_high": or_high,
            "or_low": or_low,
            "or_range": round(or_range, 4),
            "or_bars": len(or_bars),
            "or_bars_data": or_bars,
            "post_or_bars": len(post_or),
            "direction": 0,
            "result": "NO_BREAKOUT",
            "pnl_per_contract": 0.0,
        }

    # Simulate TP/SL exit
    tp_mult = strategy.get("tp_multiple", 2.0)
    sl_mult = strategy.get("sl_multiple", 1.0)

    tp_level = entry_price + (tp_mult * or_range * direction)
    sl_level = entry_price - (sl_mult * or_range * direction)

    exit_price = None
    exit_reason = "EOD"
    exit_time = None

    for bar in post_or:
        if bar["time"] <= breakout_time:
            continue

        if direction == 1:  # LONG
            if bar["low"] <= sl_level:
                exit_price = sl_level
                exit_reason = "SL_HIT"
                exit_time = bar["time"]
                break
            if bar["high"] >= tp_level:
                exit_price = tp_level
                exit_reason = "TP_HIT"
                exit_time = bar["time"]
                break
        else:  # SHORT
            if bar["high"] >= sl_level:
                exit_price = sl_level
                exit_reason = "SL_HIT"
                exit_time = bar["time"]
                break
            if bar["low"] <= tp_level:
                exit_price = tp_level
                exit_reason = "TP_HIT"
                exit_time = bar["time"]
                break

    # EOD exit: use last bar's close
    if exit_price is None:
        exit_price = post_or[-1]["close"]
        exit_time = post_or[-1]["time"]

    pnl_per_contract = (exit_price - entry_price) * direction
    point_value = spec.get("point_value", 50.0)
    pnl_dollars = pnl_per_contract * point_value

    return {
        "asset": asset_id,
        "session": session_type,
        "or_high": round(or_high, 4),
        "or_low": round(or_low, 4),
        "or_range": round(or_range, 4),
        "or_bars": len(or_bars),
        "or_bars_data": or_bars,
        "direction": direction,
        "direction_str": "LONG" if direction == 1 else "SHORT",
        "entry_price": round(entry_price, 4),
        "tp_level": round(tp_level, 4),
        "sl_level": round(sl_level, 4),
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "exit_time": exit_time.strftime("%H:%M") if exit_time else None,
        "breakout_time": breakout_time.strftime("%H:%M") if breakout_time else None,
        "pnl_points": round(pnl_per_contract, 4),
        "pnl_per_contract": round(pnl_dollars, 2),
        "point_value": point_value,
        "tp_mult": tp_mult,
        "sl_mult": sl_mult,
    }


# ---------------------------------------------------------------------------
# Regime probability (ports live B2 — b2_regime_probability.py)
# ---------------------------------------------------------------------------

def _compute_regime_probs(
    asset_id: str,
    strategy: dict,
    bars: list | None = None,
) -> tuple[dict, bool]:
    """Compute regime probabilities for one asset, porting from live B2.

    Logic mirrors ``b2_regime_probability.py``:
      - REGIME_NEUTRAL → equal 0.5/0.5 (line 153-154)
      - BINARY_ONLY with pettersson_threshold → realised vol vs phi (line 95-116)
      - Fallback on locked regime_label

    Returns:
        (probs, uncertain) where probs = {HIGH_VOL: float, LOW_VOL: float}
        and uncertain = True if max(probs) < 0.6 (spec PG-22).
    """
    regime_label = strategy.get("regime_label", "REGIME_NEUTRAL")

    # REGIME_NEUTRAL → equal probs (matches live B2 _classifier_regime)
    if regime_label == "REGIME_NEUTRAL":
        return {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}, True

    # BINARY_ONLY with pettersson_threshold (live B2 _binary_regime)
    phi = strategy.get("pettersson_threshold")
    if phi is not None and bars:
        sigma = _estimate_realised_vol(bars)
        if sigma is not None:
            if sigma > phi:
                probs = {"HIGH_VOL": 1.0, "LOW_VOL": 0.0}
            else:
                probs = {"HIGH_VOL": 0.0, "LOW_VOL": 1.0}
            return probs, (max(probs.values()) < 0.6)

    # Fallback: use locked regime label directly
    if regime_label == "HIGH_VOL":
        return {"HIGH_VOL": 1.0, "LOW_VOL": 0.0}, False
    if regime_label == "LOW_VOL":
        return {"HIGH_VOL": 0.0, "LOW_VOL": 1.0}, False

    return {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}, True


def _estimate_realised_vol(bars: list) -> float | None:
    """Estimate annualised realised volatility from intraday 1-min bars.

    Uses close-to-close log returns, annualised assuming ~390 bars/day
    and 252 trading days/year.  Minimum 10 bars required.
    """
    if not bars or len(bars) < 10:
        return None

    closes = []
    for bar in bars:
        c = get_bar_field(bar, "close")
        if c and c > 0:
            closes.append(c)

    if len(closes) < 10:
        return None

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if not log_returns:
        return None

    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / max(len(log_returns) - 1, 1)
    std = math.sqrt(variance)

    # Annualize: ~390 1-min bars per day, 252 trading days
    return std * math.sqrt(390 * 252)


# ---------------------------------------------------------------------------
# Robust Kelly (Paper 218 distributional robust Kelly)
# ---------------------------------------------------------------------------

def _get_return_bounds(ewma_state: dict) -> tuple[float, float]:
    """Paper 218: uncertainty set bounds from EWMA statistics.

    Port of ``b1_features.py:450-464``.
    """
    wr = ewma_state.get("win_rate", 0.5)
    avg_win = ewma_state.get("avg_win", 0.0)
    avg_loss = ewma_state.get("avg_loss", 0.0)
    mu = avg_win * wr - avg_loss * (1 - wr)
    variance = avg_win ** 2 * wr + avg_loss ** 2 * (1 - wr) - mu ** 2
    sigma = math.sqrt(max(0, variance))
    return (mu - 1.5 * sigma, mu + 1.5 * sigma)


def _compute_robust_kelly(
    return_bounds: tuple[float, float],
    standard_kelly: float = 0.0,
) -> float:
    """Paper 218: min-max robust Kelly fraction.

    Port of ``b1_features.py:467-480``.
    """
    lower, upper = return_bounds
    if lower <= 0:
        return 0.3 * standard_kelly
    product = upper * lower
    if product == 0:
        return 0.0
    robust_f = lower / product
    return max(0.0, min(robust_f, 0.5))


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------

def compute_contracts(
    asset_id: str,
    pnl_per_contract: float,
    spec: dict,
    kelly_params: dict,
    ewma_states: dict,
    config: dict,
    strategy: dict,
    session_id: int = 1,
    aim_modifier: float = 1.0,
) -> dict:
    """Compute contract count matching real B4 Kelly pipeline.

    ``config`` must contain: ``user_capital``, ``max_contracts``,
    ``budget_divisor``, ``risk_goal``, ``cb_enabled``, ``current_drawdown``,
    ``daily_loss_used``, ``mdd_limit``, ``mll_limit``, ``topstep_params``,
    and the full ``_tsm`` sub-dict.

    Returns dict with contracts, kelly_raw, tsm_cap, risk_per_contract, etc.
    """
    user_capital = config.get("user_capital", 150000.0)
    max_contracts = config.get("max_contracts", 15)

    point_value = spec.get("point_value", 50.0)
    sl_dist = strategy.get("threshold", 4.0)
    fallback_risk = sl_dist * point_value

    # Step 1: Regime-blended Kelly (weighted by actual regime probabilities from B2)
    low_kelly = 0.0
    high_kelly = 0.0
    shrinkage = 1.0
    for key, kp in kelly_params.items():
        if key[0] == asset_id and key[2] == session_id:
            if key[1] == "LOW_VOL":
                low_kelly = kp.get("kelly_full", 0)
            elif key[1] == "HIGH_VOL":
                high_kelly = kp.get("kelly_full", 0)
            shrinkage = kp.get("shrinkage_factor", 1.0)

    regime_probs = config.get("regime_probs", {}).get(
        asset_id, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5},
    )
    blended = (
        regime_probs.get("LOW_VOL", 0.5) * low_kelly
        + regime_probs.get("HIGH_VOL", 0.5) * high_kelly
    )

    # Step 2: Shrinkage
    adjusted = blended * shrinkage

    # Step 3: Robust Kelly fallback (b4_kelly_sizing.py:129-138, Paper 218)
    regime_uncertain = config.get("regime_uncertain", {}).get(asset_id, False)
    robust_kelly_applied = False
    if regime_uncertain:
        dominant_regime = max(regime_probs.items(), key=lambda x: x[1])[0]
        ewma_key = (asset_id, dominant_regime, session_id)
        ewma_for_robust = ewma_states.get(ewma_key, {})
        if ewma_for_robust:
            bounds = _get_return_bounds(ewma_for_robust)
            robust = _compute_robust_kelly(bounds, adjusted)
            if robust < adjusted:
                adjusted = robust
                robust_kelly_applied = True

    # Step 4: AIM modifier
    aim_mod = aim_modifier
    kelly_with_aim = adjusted * aim_mod

    # Step 5: User Kelly ceiling (b4_kelly_sizing.py:144-145)
    user_kelly_ceiling = config.get("user_kelly_ceiling", 0.25)
    kelly_with_aim = min(kelly_with_aim, user_kelly_ceiling)

    # Step 6: Risk goal — graduated by pass_probability (b4_kelly_sizing.py:305-317)
    risk_goal = config.get("risk_goal", "GROW_CAPITAL")
    if risk_goal == "PASS_EVAL":
        pass_prob = config.get("_tsm", {}).get("pass_probability", 0.6)
        if pass_prob < 0.5:
            kelly_with_aim *= 0.5
        elif pass_prob < 0.7:
            kelly_with_aim *= 0.7
        else:
            kelly_with_aim *= 0.85
    elif risk_goal == "PRESERVE_CAPITAL":
        kelly_with_aim *= 0.5

    # Step 7: Risk per contract from EWMA
    risk_per_contract = None
    for key, ewma in ewma_states.items():
        if key[0] == asset_id and key[2] == session_id:
            avg_loss = ewma.get("avg_loss", 0)
            if avg_loss > 0:
                risk_per_contract = avg_loss
                break
    # Fallback to any session
    if risk_per_contract is None:
        for key, ewma in ewma_states.items():
            if key[0] == asset_id:
                avg_loss = ewma.get("avg_loss", 0)
                if avg_loss > 0:
                    risk_per_contract = avg_loss
                    break
    if risk_per_contract is None or risk_per_contract <= 0:
        risk_per_contract = fallback_risk

    # Step 7b: Add expected fee to risk_per_contract (b4_kelly_sizing.py:422-440)
    expected_fee = config.get("_tsm", {}).get("fee_per_trade", 2.80)
    risk_per_contract += expected_fee

    # Step 8: Raw contracts
    if risk_per_contract > 0 and kelly_with_aim > 0:
        raw = kelly_with_aim * user_capital / risk_per_contract
    else:
        raw = 0

    # Step 9: MDD budget cap (remaining MDD / budget_divisor)
    tsm = config.get("_tsm", {})
    max_dd = tsm.get("max_drawdown_limit") or config.get("mdd_limit", 999999)
    current_dd = tsm.get("current_drawdown") or config.get("current_drawdown", 0)
    remaining_mdd = max_dd - current_dd
    budget_divisor = config.get("budget_divisor", 20)
    daily_budget = remaining_mdd / budget_divisor
    mdd_cap = (
        math.floor(daily_budget / fallback_risk) if fallback_risk > 0 else 999
    )

    # Step 10: Daily loss cap (MLL)
    max_daily = tsm.get("max_daily_loss") or config.get("mll_limit")
    daily_used = tsm.get("daily_loss_used") or config.get("daily_loss_used", 0)
    if max_daily and max_daily > 0:
        remaining_daily = max_daily - daily_used
        daily_cap = (
            math.floor(remaining_daily / fallback_risk)
            if fallback_risk > 0
            else 999
        )
    else:
        daily_cap = 999

    # Step 11: 4-way min
    raw_floor = math.floor(raw)
    final = min(raw_floor, mdd_cap, daily_cap, max_contracts)
    final = max(final, 0)

    # Log which constraint is binding
    binding = "kelly"
    if final < raw_floor:
        if final == mdd_cap:
            binding = "mdd_cap"
        elif final == daily_cap:
            binding = "daily_cap"
        elif final == max_contracts:
            binding = "max_contracts"
    logger.info("SIZING %s: kelly=%.4f aim_mod=%.3f → raw=%d, mdd_cap=%d, daily_cap=%d, "
                "max=%d → final=%d (binding: %s)",
                asset_id, adjusted, aim_mod, raw_floor, mdd_cap, daily_cap,
                max_contracts, final, binding)

    # --- Circuit breaker layers (b5c_circuit_breaker.py) ---
    topstep_params_cb = config.get("topstep_params", {})
    if isinstance(topstep_params_cb, str):
        topstep_params_cb = (
            json.loads(topstep_params_cb) if topstep_params_cb else {}
        )
    c_param = topstep_params_cb.get("c", 0.5)
    e_param = topstep_params_cb.get("e", 0.01)
    fee_per_trade = config.get("_tsm", {}).get("fee_per_trade", 2.80)
    cb_enabled = config.get("cb_enabled", True)

    # Step 11b: CB L0 — Scaling cap for XFA accounts (b5c_circuit_breaker.py:232-256)
    cb_l0_blocked = False
    scaling_plan_active = config.get("_tsm", {}).get("scaling_plan_active", False)
    if cb_enabled and scaling_plan_active and final > 0:
        scaling_tier_micros = config.get("_tsm", {}).get("scaling_tier_micros", 150)
        current_open_micros = config.get("_current_open_micros", 0)
        if current_open_micros + final > scaling_tier_micros:
            final = max(0, scaling_tier_micros - current_open_micros)
            cb_l0_blocked = (final == 0)

    # Step 12: CB L1 — Preemptive halt: abs(L_t) + rho_j >= c * e * A
    l_t = abs(config.get("_intraday_cumulative_pnl", 0.0))
    l_halt = c_param * e_param * user_capital
    rho_j = final * (fallback_risk + fee_per_trade)
    cb_blocked = False
    if cb_enabled and final > 0 and (l_t + rho_j) >= l_halt:
        cb_blocked = True
        while final > 0 and (l_t + final * (fallback_risk + fee_per_trade)) >= l_halt:
            final -= 1
        final = max(final, 0)

    # Step 13: CB L2 — Budget exhaustion: n_t < N (b5c_circuit_breaker.py:292-321)
    n_t = config.get("_intraday_trade_count", 0)
    p_param = topstep_params_cb.get("p", 0.005)
    mdd_val = config.get("mdd_limit", 4500.0)
    l2_denom = mdd_val * p_param + fee_per_trade
    cb_l2_N = int((e_param * user_capital) / l2_denom) if l2_denom > 0 else 999
    cb_l2_blocked = False
    if cb_enabled and final > 0 and n_t >= cb_l2_N:
        cb_l2_blocked = True
        final = 0

    # Step 14: CB L3 — Basket expectancy: mu_b = r_bar + beta_b * L_b
    #   (b5c_circuit_breaker.py:324-368)
    cb_l3_blocked = False
    mu_b = None
    n_obs = 0
    bp = {}
    if cb_enabled and final > 0:
        _account_id = config.get("_tsm", {}).get("account_id", "20319811")
        _model_m = str(strategy.get("m", 0))
        bp = config.get("cb_params", {}).get((_account_id, _model_m), {})
        n_obs = bp.get("n_observations", 0)
        if n_obs > 0:
            r_bar = bp.get("r_bar", 0.0)
            beta_b = bp.get("beta_b", 0.0)
            p_val = bp.get("p_value", 1.0)
            # Significance gate: require p<0.05 AND n>=100
            if p_val > 0.05 or n_obs < 100:
                beta_b = 0.0
            l_b = config.get("_intraday_basket_pnl", {}).get(_model_m, 0.0)
            mu_b = r_bar + beta_b * l_b
            if mu_b <= 0 and beta_b > 0:
                cb_l3_blocked = True
                final = 0

    # Step 15: CB L4 — Correlation-adjusted Sharpe (b5c_circuit_breaker.py:371-433)
    #   Reuses bp, n_obs, mu_b from L3 scope above.
    cb_l4_blocked = False
    if cb_enabled and final > 0 and n_obs >= 100 and mu_b is not None:
        sigma_cb = bp.get("sigma", 0.0)
        rho_bar = bp.get("rho_bar", 0.0)
        lambda_threshold = topstep_params_cb.get("lambda", 0.0)
        if sigma_cb > 0:
            denom = sigma_cb * math.sqrt(1.0 + 2.0 * n_t * max(rho_bar, 0.0))
            S = mu_b / denom if denom > 0 else 0.0
            if S <= lambda_threshold:
                cb_l4_blocked = True
                final = 0

    return {
        "asset": asset_id,
        "contracts": final,
        "kelly_blended": round(blended, 6),
        "kelly_shrunk": round(adjusted, 6),
        "kelly_adjusted": round(kelly_with_aim, 6),
        "robust_kelly_applied": robust_kelly_applied,
        "user_kelly_ceiling": user_kelly_ceiling,
        "risk_per_contract": round(risk_per_contract, 2),
        "raw_contracts": math.floor(raw),
        "mdd_cap": mdd_cap,
        "daily_cap": daily_cap,
        "max_contracts": max_contracts,
        "budget_divisor": budget_divisor,
        "remaining_mdd": round(remaining_mdd, 2),
        "daily_budget": round(daily_budget, 2),
        "fallback_risk": round(fallback_risk, 2),
        "risk_goal": risk_goal,
        "cb_l1_halt": round(l_halt, 2),
        "cb_l1_l_t": round(l_t, 2),
        "cb_rho_j": round(rho_j, 2),
        "cb_blocked": cb_blocked,
        "cb_l2_blocked": cb_l2_blocked,
        "cb_l2_N": cb_l2_N,
        "cb_l2_n_t": n_t,
        "cb_l3_blocked": cb_l3_blocked,
        "cb_l3_mu_b": round(mu_b, 4) if mu_b is not None else None,
        "cb_l0_blocked": cb_l0_blocked,
        "cb_l4_blocked": cb_l4_blocked,
        "cb_enabled": cb_enabled,
        "binding_constraint": binding,
        "aim_modifier": round(aim_mod, 4),
        "regime_probs": regime_probs,
        "regime_uncertain": regime_uncertain,
    }


# ---------------------------------------------------------------------------
# Position limit
# ---------------------------------------------------------------------------

def _expected_edge(result: dict, config: dict) -> float:
    """Compute forward-looking expected edge for one trade result.

    Ports from live B5 (``b5_trade_selection.py:51-61``):
      edge = wr * avg_win - (1 - wr) * avg_loss
    using the dominant regime's EWMA stats.
    """
    asset_id = result.get("asset")
    regime_probs = config.get("regime_probs", {}).get(
        asset_id, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5},
    )
    dominant_regime = max(regime_probs, key=regime_probs.get)

    ewma_states = config.get("ewma_states", {})
    session_type = ASSET_SESSION_MAP.get(asset_id, "NY")
    session_id = SESSION_ID_MAP.get(session_type, 1)

    # Look up EWMA for (asset, dominant_regime, session_id)
    ewma = ewma_states.get((asset_id, dominant_regime, session_id))
    if not ewma:
        # Fallback: try any session for this asset + regime
        for key, val in ewma_states.items():
            if key[0] == asset_id and key[1] == dominant_regime:
                ewma = val
                break
    if not ewma:
        return 0.0

    wr = ewma.get("win_rate", 0.5)
    avg_win = ewma.get("avg_win", 0.0)
    avg_loss = ewma.get("avg_loss", 0.0)
    return wr * avg_win - (1 - wr) * avg_loss


def apply_position_limit(
    results: list[dict],
    max_positions: int,
    config: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Rank trades by expected edge (B5 spec), take top N.

    When ``config`` is provided, ranks by forward-looking expected edge
    (wr*avg_win - (1-wr)*avg_loss) matching live B5.  Falls back to
    abs(pnl_per_contract) if config is missing.

    Returns (selected, excluded).
    """
    if config is None:
        config = {}

    # Only trades with a breakout AND non-zero contracts qualify
    eligible = [
        r
        for r in results
        if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0
    ]

    # Compute and attach expected edge to each result
    for r in eligible:
        r["expected_edge"] = round(_expected_edge(r, config), 4)

    # Rank by expected edge (forward-looking, matching live B5)
    eligible.sort(key=lambda x: x.get("expected_edge", 0), reverse=True)

    if len(eligible) <= max_positions:
        return eligible, []

    selected = eligible[:max_positions]
    excluded = eligible[max_positions:]
    for ex in excluded:
        ex["excluded_reason"] = f"Position limit ({max_positions})"
        ex["original_contracts"] = ex.get("contracts", 0)
        ex["contracts"] = 0
        ex["total_pnl"] = 0
    return selected, excluded


# ---------------------------------------------------------------------------
# Quality gate (ports live B5B — b5b_quality_gate.py)
# ---------------------------------------------------------------------------

def _apply_quality_gate(results: list[dict], config: dict) -> list[dict]:
    """B5B quality gate: filter/scale trades by quality_score.

    Port of ``b5b_quality_gate.py:49-67``.

    ``quality_score = expected_edge × aim_modifier × data_maturity``

    - Below ``hard_floor`` (default 0.003): contracts zeroed.
    - Between floor and ceiling: graduated sizing multiplier
      ``min(1.0, quality_score / quality_ceiling)``.
    - ``data_maturity = min(1.0, max(0.5, trade_count / 50))``
      (cold-start floor of 0.5 so fresh systems aren't fully blocked).
    """
    hard_floor = config.get("quality_hard_floor", 0.003)
    quality_ceiling = config.get("quality_ceiling", 0.010)
    trade_counts = config.get("trade_counts", {})

    for result in results:
        if result.get("direction", 0) == 0:
            continue

        asset_id = result.get("asset")
        edge = result.get("expected_edge", 0.0)
        aim_mod = result.get("aim_modifier", 1.0)
        trade_count = trade_counts.get(asset_id, 0)

        # Data maturity ramp (b5b_quality_gate.py:54)
        data_maturity = min(1.0, max(0.5, trade_count / 50.0))

        quality_score = abs(edge) * aim_mod * data_maturity
        result["quality_score"] = round(quality_score, 6)
        result["data_maturity"] = round(data_maturity, 4)

        if quality_score < hard_floor:
            result["quality_gate_passed"] = False
            result["original_contracts"] = result.get("contracts", 0)
            result["contracts"] = 0
            result["total_pnl"] = 0.0
            result["quality_gate_reason"] = (
                f"score {quality_score:.6f} < floor {hard_floor}"
            )
        else:
            result["quality_gate_passed"] = True
            # Graduated sizing multiplier (b5b_quality_gate.py:66)
            quality_mult = (
                min(1.0, quality_score / quality_ceiling)
                if quality_ceiling > 0
                else 1.0
            )
            new_contracts = max(0, int(result.get("contracts", 0) * quality_mult))
            result["contracts"] = new_contracts
            result["total_pnl"] = round(
                result.get("pnl_per_contract", 0) * new_contracts, 2,
            )
            result["quality_multiplier"] = round(quality_mult, 4)

    return results


# ---------------------------------------------------------------------------
# Cross-asset correlation filter (ports live B5 — b5_trade_selection.py)
# ---------------------------------------------------------------------------

# Known high-correlation pairs (fallback when D07 is not populated)
_DEFAULT_CORR_PAIRS = {
    ("ES", "MES"): 0.99,  ("MES", "ES"): 0.99,
    ("NQ", "MNQ"): 0.99,  ("MNQ", "NQ"): 0.99,
    ("ZB", "ZN"):  0.85,  ("ZN", "ZB"):  0.85,
}


def _apply_correlation_filter(
    selected: list[dict],
    config: dict,
) -> list[dict]:
    """Reduce contracts for highly correlated pairs.

    Port of ``b5_trade_selection.py:70-89``.

    For pairs with correlation above *threshold* (default 0.7), the asset
    with the lower expected edge gets its contracts halved.
    """
    corr_threshold = config.get("correlation_threshold", 0.7)
    corr_matrix = config.get("correlation_matrix", {})

    if not corr_matrix:
        corr_matrix = _DEFAULT_CORR_PAIRS

    # Only process eligible trades (direction != 0, contracts > 0)
    eligible = [
        r for r in selected
        if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0
    ]

    for i, r1 in enumerate(eligible):
        for r2 in eligible[i + 1:]:
            a1, a2 = r1["asset"], r2["asset"]

            # Try both key formats: tuple keys and string keys
            corr = corr_matrix.get(
                (a1, a2),
                corr_matrix.get(
                    (a2, a1),
                    corr_matrix.get(
                        f"{a1}_{a2}",
                        corr_matrix.get(f"{a2}_{a1}", 0.0),
                    ),
                ),
            )
            if isinstance(corr, str):
                try:
                    corr = float(corr)
                except (ValueError, TypeError):
                    corr = 0.0

            if corr > corr_threshold:
                # Halve the lower-edge asset (b5_trade_selection.py:83-86)
                e1 = r1.get("expected_edge", 0)
                e2 = r2.get("expected_edge", 0)
                if e1 < e2:
                    orig = r1["contracts"]
                    r1["contracts"] = max(0, orig // 2)
                    r1["correlation_reduced"] = True
                    r1["correlated_with"] = a2
                    r1["pre_correlation_contracts"] = orig
                    r1["total_pnl"] = round(
                        r1.get("pnl_per_contract", 0) * r1["contracts"], 2,
                    )
                else:
                    orig = r2["contracts"]
                    r2["contracts"] = max(0, orig // 2)
                    r2["correlation_reduced"] = True
                    r2["correlated_with"] = a1
                    r2["pre_correlation_contracts"] = orig
                    r2["total_pnl"] = round(
                        r2.get("pnl_per_contract", 0) * r2["contracts"], 2,
                    )

    return selected


# ---------------------------------------------------------------------------
# Portfolio risk cap (B4 Step 7 — b4_kelly_sizing.py:236-247)
# ---------------------------------------------------------------------------

def _apply_portfolio_risk_cap(
    results: list[dict],
    config: dict,
) -> list[dict]:
    """Scale down all contracts if total risk exceeds portfolio cap.

    ``total_risk = Σ(contracts × SL_distance × point_value)``
    If ``total_risk > max_portfolio_risk_pct × capital``, scale proportionally.
    """
    max_pct = config.get("max_portfolio_risk_pct", 0.10)
    user_capital = config.get("user_capital", 150000.0)
    max_risk = max_pct * user_capital
    strategies = config.get("strategies", {})
    specs = config.get("specs", {})

    total_risk = 0.0
    active = []
    for r in results:
        if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0:
            asset_id = r.get("asset")
            sl_dist = strategies.get(asset_id, {}).get("threshold", 4)
            pv = specs.get(asset_id, {}).get("point_value", 50.0)
            risk = r["contracts"] * sl_dist * pv
            total_risk += risk
            active.append(r)

    if total_risk > max_risk and total_risk > 0:
        scale = max_risk / total_risk
        for r in active:
            original = r["contracts"]
            r["contracts"] = max(0, int(original * scale))
            if r["contracts"] < original:
                r["portfolio_risk_scaled"] = True
                r["portfolio_scale_factor"] = round(scale, 4)
                r["total_pnl"] = round(
                    r.get("pnl_per_contract", 0) * r["contracts"], 2,
                )

    return results


def _apply_hmm_session_weight(
    results: list[dict],
    config: dict,
) -> list[dict]:
    """Apply HMM session allocation weights (b5_trade_selection.py:135-185).

    During cold start (n_observations < 20), uses equal 1/3 weights per session
    which is a no-op for single-session replays.  When warm, applies learned
    session weights from D26.
    """
    hmm_state = config.get("hmm_state", {})
    n_obs = hmm_state.get("n_observations", 0)

    if n_obs < 20:
        return results  # Cold start: equal weights, no change

    session_weights = hmm_state.get("session_weights", {})
    for r in results:
        session = r.get("session_type", "NY")
        weight = session_weights.get(session, 1.0 / 3.0)
        weight = max(weight, 0.05)  # Floor at 5%
        if r.get("contracts", 0) > 0:
            original = r["contracts"]
            r["contracts"] = max(1, int(original * weight))
            if r["contracts"] < original:
                r["hmm_session_weighted"] = True
                r["hmm_session_weight"] = round(weight, 4)

    return results


# ---------------------------------------------------------------------------
# Full replay orchestrator
# ---------------------------------------------------------------------------

def _emit(on_event, event_type: str, data: dict) -> None:
    """Fire an event callback if provided."""
    if on_event is not None:
        try:
            on_event({"event": event_type, "data": data})
        except Exception as exc:
            logger.warning("on_event callback error (%s): %s", event_type, exc)


def run_replay(
    config: dict,
    target_date: date | None = None,
    on_event: callable = None,
    sessions: list[str] | None = None,
) -> dict:
    """Run a full replay for *target_date* using *config*.

    If ``on_event`` is provided, call it at each step boundary with event
    dicts.  When called without ``on_event``, runs silently and returns
    results.

    Returns a dict with keys: ``results``, ``errors``, ``trades_taken``,
    ``excluded``, ``no_breakout``, ``zero_sized``, ``total_pnl``,
    ``summary``, ``cached_bars``.
    """
    from shared.topstep_client import get_topstep_client

    if target_date is None:
        from zoneinfo import ZoneInfo

        now_et = datetime.now(ZoneInfo("America/New_York"))
        target_date = (now_et - timedelta(days=1)).date()

    aim_enabled = config.get("aim_enabled", False)

    # Emit config loaded
    _emit(on_event, "config_loaded", {
        "user_capital": config.get("user_capital"),
        "max_contracts": config.get("max_contracts"),
        "max_positions": config.get("max_positions"),
        "budget_divisor": config.get("budget_divisor"),
        "risk_goal": config.get("risk_goal"),
        "mdd_limit": config.get("mdd_limit"),
        "mll_limit": config.get("mll_limit"),
        "cb_enabled": config.get("cb_enabled"),
        "aim_enabled": aim_enabled,
        "strategies_count": len(config.get("strategies", {})),
        "kelly_count": len(config.get("kelly_params", {})),
        "ewma_count": len(config.get("ewma_states", {})),
        "target_date": target_date.isoformat(),
    })

    # Authenticate TopstepX
    client = get_topstep_client()
    client.authenticate()

    contracts = config.get("contracts", {})
    _emit(on_event, "auth_complete", {
        "contracts_resolved": len(contracts),
    })

    if not contracts:
        return {
            "results": [],
            "errors": [{"asset": "ALL", "error": "No contract IDs loaded"}],
            "trades_taken": [],
            "excluded": [],
            "no_breakout": [],
            "zero_sized": [],
            "total_pnl": 0.0,
            "summary": "No contract IDs loaded",
            "cached_bars": {},
        }

    strategies = config.get("strategies", {})
    specs = config.get("specs", {})
    kelly_params = config.get("kelly_params", {})
    ewma_states = config.get("ewma_states", {})
    max_positions = config.get("max_positions", 5)

    results = []
    errors = []
    cached_bars = {}  # {asset_id: bars} for what-if reruns

    # Filter assets by selected sessions
    active_assets = ACTIVE_ASSETS
    if sessions:
        active_assets = [a for a in ACTIVE_ASSETS if ASSET_SESSION_MAP[a] in sessions]

    # --- Intraday state accumulators for CB L1/L2/L3 ---
    config["_intraday_cumulative_pnl"] = 0.0
    config["_intraday_trade_count"] = 0
    config["_intraday_basket_pnl"] = {}

    # --- Regime probability (B2) — initial pass from strategy data ---
    config["regime_probs"] = {}
    config["regime_uncertain"] = {}
    for _asset in active_assets:
        _strat = strategies.get(_asset, {})
        _probs, _unc = _compute_regime_probs(_asset, _strat)
        config["regime_probs"][_asset] = _probs
        config["regime_uncertain"][_asset] = _unc

    _emit(on_event, "regime_computed", {
        "regime_probs": config["regime_probs"],
        "regime_uncertain": config["regime_uncertain"],
    })

    # --- AIM scoring ---
    aim_combined_modifier = {}
    aim_breakdown = {}
    if aim_enabled:
        try:
            from shared.aim_compute import run_aim_aggregation
            from shared.aim_feature_loader import load_replay_features

            replay_features, aim_states, aim_weights = load_replay_features(
                target_date, active_assets,
            )
            aim_output = run_aim_aggregation(
                active_assets=active_assets,
                features=replay_features,
                aim_states=aim_states,
                aim_weights=aim_weights,
            )
            aim_combined_modifier = aim_output.get("combined_modifier", {})
            aim_breakdown = aim_output.get("aim_breakdown", {})

            # Emit detailed debug info for each AIM
            aim_debug = {}
            for asset_id_dbg, breakdown in aim_breakdown.items():
                asset_debug = {}
                for aid, info in breakdown.items():
                    asset_debug[aid] = {
                        "modifier": info.get("modifier", 1.0),
                        "weight": info.get("dma_weight", 0),
                        "tag": info.get("reason_tag", ""),
                    }
                aim_debug[asset_id_dbg] = asset_debug

            _emit(on_event, "aim_scored", {
                "combined_modifier": aim_combined_modifier,
                "aim_breakdown": aim_breakdown,
                "aim_debug": aim_debug,
            })
        except Exception as exc:
            logger.warning("AIM scoring failed, falling back to neutral: %s", exc)
            _emit(on_event, "aim_scored", {
                "combined_modifier": {},
                "aim_breakdown": {},
                "error": str(exc),
            })

    for asset_id in active_assets:
        session_type = ASSET_SESSION_MAP[asset_id]
        contract_id = contracts.get(asset_id)
        asset_aim_mod = aim_combined_modifier.get(asset_id, 1.0)

        if not contract_id:
            errors.append({"asset": asset_id, "error": "No contract ID"})
            continue

        strategy = strategies.get(asset_id, {})
        spec = specs.get(asset_id, {"point_value": 50.0})

        # --- Fetch bars ---
        try:
            bars = fetch_session_bars(
                client, asset_id, contract_id, target_date, session_type,
                use_cache=True,
            )
            cached_bars[asset_id] = bars
            _emit(on_event, "asset_bars_fetched", {
                "asset": asset_id,
                "bar_count": len(bars),
                "session": session_type,
            })

            # Refine regime probs with bars if pettersson_threshold available
            if strategy.get("pettersson_threshold") is not None:
                _probs, _unc = _compute_regime_probs(asset_id, strategy, bars)
                config["regime_probs"][asset_id] = _probs
                config["regime_uncertain"][asset_id] = _unc

        except Exception as exc:
            err = {"asset": asset_id, "error": f"API error: {exc}"}
            errors.append(err)
            logger.warning("Fetch failed for %s: %s", asset_id, exc)
            continue

        if not bars:
            errors.append({"asset": asset_id, "error": "No bars returned"})
            continue

        # --- Simulate ORB ---
        try:
            result = simulate_orb(
                bars, asset_id, session_type, target_date, strategy, spec,
            )
        except Exception as exc:
            err = {"asset": asset_id, "error": f"simulate_orb error: {exc}"}
            errors.append(err)
            logger.warning("simulate_orb failed for %s: %s", asset_id, exc)
            continue

        if result and "error" in result:
            errors.append(result)
            continue

        # Emit OR computed for all breakout and no-breakout results
        _emit(on_event, "or_computed", {
            "asset": asset_id,
            "or_high": result.get("or_high"),
            "or_low": result.get("or_low"),
            "or_range": result.get("or_range"),
            "or_bars": result.get("or_bars"),
        })

        if result.get("direction", 0) == 0:
            results.append(result)
            continue

        # Emit breakout
        _emit(on_event, "breakout", {
            "asset": asset_id,
            "direction": result["direction"],
            "direction_str": result["direction_str"],
            "entry_price": result["entry_price"],
            "breakout_time": result.get("breakout_time"),
            "tp_level": result.get("tp_level"),
            "sl_level": result.get("sl_level"),
        })

        # Emit exit
        _emit(on_event, "exit", {
            "asset": asset_id,
            "exit_price": result["exit_price"],
            "exit_reason": result["exit_reason"],
            "exit_time": result.get("exit_time"),
            "pnl_per_contract": result["pnl_per_contract"],
            "pnl_points": result["pnl_points"],
        })

        # --- Compute contracts ---
        session_id = SESSION_ID_MAP.get(session_type, 1)
        try:
            sizing = compute_contracts(
                asset_id,
                result["pnl_per_contract"],
                spec,
                kelly_params,
                ewma_states,
                config,
                strategy,
                session_id,
                aim_modifier=asset_aim_mod,
            )
        except Exception as exc:
            logger.warning("compute_contracts failed for %s: %s", asset_id, exc)
            sizing = {"contracts": 0, "error": str(exc)}

        result["contracts"] = sizing.get("contracts", 0)
        result["sizing"] = sizing
        result["total_pnl"] = round(
            result["pnl_per_contract"] * sizing.get("contracts", 0), 2,
        )
        # Pre-compute expected edge & AIM modifier for quality gate / position limit
        result["expected_edge"] = round(_expected_edge(result, config), 4)
        result["aim_modifier"] = asset_aim_mod

        # Update intraday state for subsequent CB checks
        if result.get("direction", 0) != 0 and sizing.get("contracts", 0) > 0:
            config["_intraday_trade_count"] = (
                config.get("_intraday_trade_count", 0) + 1
            )
            config["_intraday_cumulative_pnl"] = (
                config.get("_intraday_cumulative_pnl", 0.0)
                + result["total_pnl"]
            )
            _m = str(strategy.get("m", 0))
            _bpnl = config.get("_intraday_basket_pnl", {})
            _bpnl[_m] = _bpnl.get(_m, 0.0) + result["total_pnl"]
            config["_intraday_basket_pnl"] = _bpnl

        results.append(result)

        _emit(on_event, "sizing_complete", {
            "asset": asset_id,
            "aim_modifier": asset_aim_mod,
            **sizing,
        })

    # --- Apply quality gate (B5B) ---
    if config.get("quality_gate_enabled", True):
        results = _apply_quality_gate(results, config)
        _emit(on_event, "quality_gate_applied", {
            "results": [
                {
                    "asset": r.get("asset"),
                    "quality_score": r.get("quality_score"),
                    "quality_gate_passed": r.get("quality_gate_passed"),
                    "data_maturity": r.get("data_maturity"),
                    "quality_multiplier": r.get("quality_multiplier"),
                }
                for r in results
                if r.get("direction", 0) != 0
            ],
        })

    # --- Apply position limit ---
    selected, excluded = apply_position_limit(results, max_positions, config)

    _emit(on_event, "position_limit_applied", {
        "selected": [
            {"asset": r["asset"], "expected_edge": r.get("expected_edge", 0)}
            for r in selected
        ],
        "excluded": [
            {"asset": r["asset"], "expected_edge": r.get("expected_edge", 0)}
            for r in excluded
        ],
        "max_positions": max_positions,
    })

    # --- Apply cross-asset correlation filter ---
    if config.get("correlation_filter_enabled", True):
        selected = _apply_correlation_filter(selected, config)
        corr_adjustments = [
            {
                "asset": r["asset"],
                "correlated_with": r.get("correlated_with"),
                "contracts": r.get("contracts"),
                "pre_correlation_contracts": r.get("pre_correlation_contracts"),
            }
            for r in selected
            if r.get("correlation_reduced")
        ]
        if corr_adjustments:
            _emit(on_event, "correlation_filter_applied", {
                "adjustments": corr_adjustments,
            })

    # --- Apply portfolio risk cap (B4 Step 7) ---
    if config.get("portfolio_risk_cap_enabled", True):
        selected = _apply_portfolio_risk_cap(selected, config)
        scaled = [
            r for r in selected if r.get("portfolio_risk_scaled")
        ]
        if scaled:
            _emit(on_event, "portfolio_risk_cap_applied", {
                "scale_factor": scaled[0].get("portfolio_scale_factor"),
                "assets_scaled": [r["asset"] for r in scaled],
            })

    # --- Apply HMM session allocation (B5 warmup/blend) ---
    if config.get("hmm_enabled", True):
        selected = _apply_hmm_session_weight(selected, config)

    # Classify non-trade results
    no_breakout = [r for r in results if r.get("result") == "NO_BREAKOUT"]
    zero_sized = [
        r
        for r in results
        if r.get("direction", 0) != 0 and r.get("contracts", 0) == 0
        and r not in excluded
    ]

    total_pnl = sum(r.get("total_pnl", 0) for r in selected)

    wins = [r for r in selected if r.get("total_pnl", 0) > 0]
    losses = [r for r in selected if r.get("total_pnl", 0) < 0]

    summary = {
        "target_date": target_date.isoformat(),
        "assets_total": len(ACTIVE_ASSETS),
        "trades_taken": len(selected),
        "no_breakout": len(no_breakout),
        "errors": len(errors),
        "zero_sized": len(zero_sized),
        "excluded": len(excluded),
        "total_pnl": round(total_pnl, 2),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (
            round(len(wins) / len(selected) * 100, 1) if selected else 0.0
        ),
    }

    _emit(on_event, "replay_complete", {
        "summary": summary,
        "all_results": results,
    })

    return {
        "results": results,
        "errors": errors,
        "trades_taken": selected,
        "excluded": excluded,
        "no_breakout": no_breakout,
        "zero_sized": zero_sized,
        "total_pnl": total_pnl,
        "summary": summary,
        "cached_bars": cached_bars,
    }


# ---------------------------------------------------------------------------
# What-if reruns (no API calls)
# ---------------------------------------------------------------------------

def run_whatif(
    config: dict,
    cached_bars: dict,
    original_results: dict,
    target_date: date | None = None,
    sessions: list[str] | None = None,
) -> dict:
    """Rerun sizing with different config using already-fetched bars.

    No API calls needed.  Re-simulates ORB from cached bars and recomputes
    Kelly sizing with the (potentially overridden) config.

    Returns comparison dict with ``original`` and ``whatif`` sub-dicts.
    """
    if target_date is None:
        from zoneinfo import ZoneInfo

        now_et = datetime.now(ZoneInfo("America/New_York"))
        target_date = (now_et - timedelta(days=1)).date()

    strategies = config.get("strategies", {})
    specs = config.get("specs", {})
    kelly_params = config.get("kelly_params", {})
    ewma_states = config.get("ewma_states", {})
    max_positions = config.get("max_positions", 5)

    whatif_results = []
    errors = []

    # Filter assets by selected sessions
    active_assets = ACTIVE_ASSETS
    if sessions:
        active_assets = [a for a in ACTIVE_ASSETS if ASSET_SESSION_MAP[a] in sessions]

    # Ensure regime_probs exist in config (may be overridden or missing)
    if "regime_probs" not in config:
        config["regime_probs"] = {}
        config["regime_uncertain"] = {}
        for _asset in active_assets:
            _strat = strategies.get(_asset, {})
            _bars = cached_bars.get(_asset)
            _probs, _unc = _compute_regime_probs(_asset, _strat, _bars)
            config["regime_probs"][_asset] = _probs
            config["regime_uncertain"][_asset] = _unc

    # Initialize intraday state accumulators for CB L1/L2/L3
    config["_intraday_cumulative_pnl"] = 0.0
    config["_intraday_trade_count"] = 0
    config["_intraday_basket_pnl"] = {}

    # Extract AIM modifiers from original results for what-if (#11)
    aim_modifiers = {}
    if config.get("aim_enabled", False):
        for r in original_results.get("results", []):
            _a = r.get("asset")
            if _a:
                aim_modifiers[_a] = r.get("aim_modifier", 1.0)

    for asset_id in active_assets:
        session_type = ASSET_SESSION_MAP[asset_id]
        bars = cached_bars.get(asset_id)

        if not bars:
            errors.append({"asset": asset_id, "error": "No cached bars"})
            continue

        strategy = strategies.get(asset_id, {})
        spec = specs.get(asset_id, {"point_value": 50.0})

        # Re-simulate ORB (tp_multiple / sl_multiple may have changed)
        try:
            result = simulate_orb(
                bars, asset_id, session_type, target_date, strategy, spec,
            )
        except Exception as exc:
            errors.append({
                "asset": asset_id,
                "error": f"simulate_orb error: {exc}",
            })
            continue

        if result and "error" in result:
            errors.append(result)
            continue

        if result.get("direction", 0) == 0:
            whatif_results.append(result)
            continue

        # Recompute sizing with (potentially overridden) config
        session_id = SESSION_ID_MAP.get(session_type, 1)
        _aim_mod = aim_modifiers.get(asset_id, 1.0)
        try:
            sizing = compute_contracts(
                asset_id,
                result["pnl_per_contract"],
                spec,
                kelly_params,
                ewma_states,
                config,
                strategy,
                session_id,
                aim_modifier=_aim_mod,
            )
        except Exception as exc:
            sizing = {"contracts": 0, "error": str(exc)}

        result["contracts"] = sizing.get("contracts", 0)
        result["sizing"] = sizing
        result["total_pnl"] = round(
            result["pnl_per_contract"] * sizing.get("contracts", 0), 2,
        )
        # Pre-compute expected edge & AIM modifier for quality gate / position limit
        result["expected_edge"] = round(_expected_edge(result, config), 4)
        result["aim_modifier"] = _aim_mod

        # Update intraday state for subsequent CB checks
        if result.get("direction", 0) != 0 and sizing.get("contracts", 0) > 0:
            config["_intraday_trade_count"] = (
                config.get("_intraday_trade_count", 0) + 1
            )
            config["_intraday_cumulative_pnl"] = (
                config.get("_intraday_cumulative_pnl", 0.0)
                + result["total_pnl"]
            )
            _m = str(strategy.get("m", 0))
            _bpnl = config.get("_intraday_basket_pnl", {})
            _bpnl[_m] = _bpnl.get(_m, 0.0) + result["total_pnl"]
            config["_intraday_basket_pnl"] = _bpnl

        whatif_results.append(result)

    # Apply quality gate (B5B)
    if config.get("quality_gate_enabled", True):
        whatif_results = _apply_quality_gate(whatif_results, config)

    # Apply position limit
    selected, excluded = apply_position_limit(whatif_results, max_positions, config)

    # Apply cross-asset correlation filter
    if config.get("correlation_filter_enabled", True):
        selected = _apply_correlation_filter(selected, config)

    # Apply portfolio risk cap (B4 Step 7)
    if config.get("portfolio_risk_cap_enabled", True):
        selected = _apply_portfolio_risk_cap(selected, config)

    # Apply HMM session allocation (B5 warmup/blend)
    if config.get("hmm_enabled", True):
        selected = _apply_hmm_session_weight(selected, config)

    whatif_total = sum(r.get("total_pnl", 0) for r in selected)

    # Build comparison
    original_trades = original_results.get("trades_taken", [])
    original_total = original_results.get("total_pnl", 0)

    comparison = []
    for wr in whatif_results:
        asset = wr.get("asset")
        # Find matching original
        orig = next(
            (r for r in original_results.get("results", []) if r.get("asset") == asset),
            None,
        )
        comparison.append({
            "asset": asset,
            "original_contracts": orig.get("contracts", 0) if orig else 0,
            "original_pnl": orig.get("total_pnl", 0) if orig else 0,
            "whatif_contracts": wr.get("contracts", 0),
            "whatif_pnl": wr.get("total_pnl", 0),
            "direction": wr.get("direction", 0),
            "exit_reason": wr.get("exit_reason"),
            "sizing_diff": wr.get("sizing"),
        })

    return {
        "whatif_results": whatif_results,
        "whatif_trades": selected,
        "whatif_excluded": excluded,
        "whatif_total_pnl": round(whatif_total, 2),
        "original_total_pnl": round(original_total, 2),
        "pnl_delta": round(whatif_total - original_total, 2),
        "comparison": comparison,
        "errors": errors,
    }
