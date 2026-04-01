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
            "FROM p3_d08_tsm_state WHERE account_id = '20319811' "
            "ORDER BY last_updated DESC LIMIT 1"
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

    # --- Assemble config dict ---
    config = {
        "user_capital": user_capital,
        "max_contracts": max_contracts,
        "max_positions": max_positions,
        "budget_divisor": 20,
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
        "topstep_params": topstep_params if topstep_params else {"c": 0.5, "e": 0.01},
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
        if bar["high"] > or_high and direction == 0:
            direction = 1  # LONG breakout
            entry_price = or_high
            breakout_time = bar["time"]
            break
        elif bar["low"] < or_low and direction == 0:
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

    # Step 1: Regime-blended Kelly (REGIME_NEUTRAL -> equal 0.5/0.5 probs)
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

    blended = 0.5 * low_kelly + 0.5 * high_kelly

    # Step 2: Shrinkage
    adjusted = blended * shrinkage

    # Step 3: AIM modifier
    aim_mod = aim_modifier
    kelly_with_aim = adjusted * aim_mod

    # Step 4: Risk goal (PASS_EVAL)
    risk_goal = config.get("risk_goal", "GROW_CAPITAL")
    if risk_goal == "PASS_EVAL":
        kelly_with_aim *= 0.7
    elif risk_goal == "PRESERVE_CAPITAL":
        kelly_with_aim *= 0.5

    # Step 5: Risk per contract from EWMA
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

    # Step 6: Raw contracts
    if risk_per_contract > 0 and kelly_with_aim > 0:
        raw = kelly_with_aim * user_capital / risk_per_contract
    else:
        raw = 0

    # Step 7: MDD budget cap (remaining MDD / budget_divisor)
    tsm = config.get("_tsm", {})
    max_dd = tsm.get("max_drawdown_limit") or config.get("mdd_limit", 999999)
    current_dd = tsm.get("current_drawdown") or config.get("current_drawdown", 0)
    remaining_mdd = max_dd - current_dd
    budget_divisor = config.get("budget_divisor", 20)
    daily_budget = remaining_mdd / budget_divisor
    mdd_cap = (
        math.floor(daily_budget / fallback_risk) if fallback_risk > 0 else 999
    )

    # Step 8: Daily loss cap (MLL)
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

    # Step 9: 4-way min
    final = min(math.floor(raw), mdd_cap, daily_cap, max_contracts)
    final = max(final, 0)

    # Step 10: Circuit breaker L1 preemptive halt
    # abs(L_t) + rho_j >= c * e * A
    topstep_params = config.get("topstep_params", {})
    if isinstance(topstep_params, str):
        topstep_params = json.loads(topstep_params) if topstep_params else {}
    c = topstep_params.get("c", 0.5)
    e = topstep_params.get("e", 0.01)
    l_halt = c * e * user_capital
    rho_j = final * fallback_risk
    cb_blocked = False

    cb_enabled = config.get("cb_enabled", True)
    if cb_enabled and rho_j >= l_halt and final > 0:
        cb_blocked = True
        while final > 0 and (final * fallback_risk) >= l_halt:
            final -= 1
        final = max(final, 0)

    return {
        "asset": asset_id,
        "contracts": final,
        "kelly_blended": round(blended, 6),
        "kelly_shrunk": round(adjusted, 6),
        "kelly_adjusted": round(kelly_with_aim, 6),
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
        "cb_rho_j": round(rho_j, 2),
        "cb_blocked": cb_blocked,
        "cb_enabled": cb_enabled,
    }


# ---------------------------------------------------------------------------
# Position limit
# ---------------------------------------------------------------------------

def apply_position_limit(
    results: list[dict],
    max_positions: int,
) -> tuple[list[dict], list[dict]]:
    """Sort by edge (abs pnl per contract), take top N.

    Returns (selected, excluded).
    """
    # Only trades with a breakout AND non-zero contracts qualify
    eligible = [
        r
        for r in results
        if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0
    ]

    # Sort by absolute PnL per contract (proxy for expected edge) -- take top N
    eligible.sort(
        key=lambda x: abs(x.get("pnl_per_contract", 0)), reverse=True,
    )

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

            _emit(on_event, "aim_scored", {
                "combined_modifier": aim_combined_modifier,
                "aim_breakdown": aim_breakdown,
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
        asset_aim_mod = aim_combined_modifier.get(asset_id, 1.0)
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
        results.append(result)

        _emit(on_event, "sizing_complete", {
            "asset": asset_id,
            "aim_modifier": asset_aim_mod,
            **sizing,
        })

    # --- Apply position limit ---
    selected, excluded = apply_position_limit(results, max_positions)

    _emit(on_event, "position_limit_applied", {
        "selected": [r["asset"] for r in selected],
        "excluded": [r["asset"] for r in excluded],
        "max_positions": max_positions,
    })

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
            )
        except Exception as exc:
            sizing = {"contracts": 0, "error": str(exc)}

        result["contracts"] = sizing.get("contracts", 0)
        result["sizing"] = sizing
        result["total_pnl"] = round(
            result["pnl_per_contract"] * sizing.get("contracts", 0), 2,
        )
        whatif_results.append(result)

    # Apply position limit
    selected, excluded = apply_position_limit(whatif_results, max_positions)
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
