# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
Session Replay — Simulates yesterday's ORB session using live TopstepX bars.

READ-ONLY: No trades placed, no QuestDB writes, no Redis publishes.

Pulls 1-min bars from TopstepX, computes Opening Range, detects breakouts,
sizes via Kelly, and computes hypothetical PnL for all 10 active assets.

Usage (inside captain-command container):
    python /app/replay_session.py [--date 2026-03-26]
"""

import argparse
import json
import math
import sys
import os
from datetime import datetime, timedelta, date, time as dtime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/app")


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


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_bars(client, contract_id: str, target_date: date, session_type: str) -> list[dict]:
    """Fetch 1-minute bars for a full session from TopstepX.

    Uses /History/retrieveBars endpoint with flat payload format.
    TopstepX returns bars in REVERSE chronological order (newest first).
    Timestamps are UTC.
    """
    import requests

    cfg = SESSION_CONFIG[session_type]

    # For APAC, the session starts the evening BEFORE target_date
    if session_type == "APAC":
        start_day = target_date - timedelta(days=1)
    else:
        start_day = target_date

    or_start = datetime.strptime(cfg["or_start"], "%H:%M").time()
    eod = datetime.strptime(cfg["eod"], "%H:%M").time()

    # Convert ET times to UTC for API (ET = UTC-4 during EDT)
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")

    fetch_start = datetime.combine(start_day, or_start, tzinfo=et) - timedelta(minutes=5)
    fetch_end = datetime.combine(target_date if session_type != "APAC" else target_date, eod, tzinfo=et) + timedelta(minutes=30)

    start_utc = fetch_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S")
    end_utc = fetch_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S")

    # Use retrieveBars (the correct TopstepX endpoint)
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
        return []
    data = resp.json()
    bars = data.get("bars", [])
    # Reverse to chronological order (oldest first)
    bars.reverse()
    return bars


def parse_bar_time(bar: dict) -> datetime | None:
    """Extract timestamp from a bar dict.

    TopstepX retrieveBars returns: {"t": "2026-03-26T13:30:00+00:00", "o", "h", "l", "c", "v"}
    """
    for key in ("t", "timestamp", "time", "dateTime", "barTime"):
        val = bar.get(key)
        if val:
            try:
                if isinstance(val, str):
                    val = val.replace("Z", "+00:00")
                    return datetime.fromisoformat(val)
                elif isinstance(val, (int, float)):
                    return datetime.fromtimestamp(val / 1000 if val > 1e12 else val, tz=timezone.utc)
            except (ValueError, OSError):
                continue
    return None


def get_bar_field(bar: dict, field: str) -> float | None:
    """Get a numeric field from a bar.

    TopstepX uses single-letter keys: o, h, l, c, v.
    """
    # Map full names to single-letter keys
    _field_map = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}
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
# ORB Simulation
# ---------------------------------------------------------------------------

def simulate_orb(bars: list[dict], asset_id: str, session_type: str,
                 target_date: date, strategy: dict, spec: dict) -> dict | None:
    """Simulate ORB for one asset on one date.

    Returns dict with or_high, or_low, direction, entry_price, exit_price, pnl_per_contract, etc.
    Returns None if no valid OR or no breakout.
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
        # Convert to naive ET for comparison (TopstepX returns UTC or ET)
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
            parsed.append({"time": t_et, "open": o, "high": h, "low": l, "close": c})

    if not parsed:
        return {"asset": asset_id, "error": f"No parseable bars (raw count: {len(bars)})"}

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
        # Debug: show what times we have
        times = [b["time"].strftime("%H:%M") for b in parsed[:10]]
        return {"asset": asset_id, "error": f"No bars in OR window {or_start}-{or_end} "
                f"(have {len(parsed)} bars, times: {times}...)"}

    or_high = max(b["high"] for b in or_bars)
    or_low = min(b["low"] for b in or_bars)
    or_range = or_high - or_low

    if or_range <= 0:
        return {"asset": asset_id, "error": f"OR range is zero ({or_high}={or_low})"}

    # Post-OR bars (after OR closes, until EOD)
    eod_date = target_date if session_type != "APAC" else target_date
    eod_dt = datetime.combine(eod_date, eod)
    post_or = [b for b in parsed if b["time"] >= or_end_dt and b["time"] <= eod_dt]

    if not post_or:
        return {"asset": asset_id, "error": f"No post-OR bars (OR ends {or_end}, "
                f"last bar: {parsed[-1]['time'].strftime('%H:%M')})"}

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
            "or_high": or_high, "or_low": or_low, "or_range": round(or_range, 4),
            "or_bars": len(or_bars), "post_or_bars": len(post_or),
            "direction": 0, "result": "NO_BREAKOUT",
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

def compute_contracts(asset_id: str, pnl_per_contract: float, spec: dict,
                      kelly_params: dict, ewma_states: dict,
                      user_capital: float, max_contracts: int,
                      strategy: dict, tsm: dict, session_id: int = 1) -> dict:
    """Compute contract count matching real B4 Kelly pipeline.

    Returns dict with contracts, kelly_raw, tsm_cap, risk_per_contract, etc.
    """
    point_value = spec.get("point_value", 50.0)
    sl_dist = strategy.get("threshold", 4.0)
    fallback_risk = sl_dist * point_value

    # Step 1: Regime-blended Kelly (REGIME_NEUTRAL → equal 0.5/0.5 probs)
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

    # Step 3: AIM modifier (1.0 = neutral since AIMs just activated)
    aim_mod = 1.0
    kelly_with_aim = adjusted * aim_mod

    # Step 4: Risk goal (PASS_EVAL)
    classification = tsm.get("classification") or {}
    risk_goal = classification.get("risk_goal") or tsm.get("risk_goal") or "GROW_CAPITAL"
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
    max_dd = tsm.get("max_drawdown_limit") or 999999
    current_dd = tsm.get("current_drawdown") or 0
    remaining_mdd = max_dd - current_dd
    budget_divisor = 20  # default
    daily_budget = remaining_mdd / budget_divisor
    mdd_cap = math.floor(daily_budget / fallback_risk) if fallback_risk > 0 else 999

    # Step 8: Daily loss cap (MLL)
    max_daily = tsm.get("max_daily_loss")
    daily_used = tsm.get("daily_loss_used") or 0
    if max_daily and max_daily > 0:
        remaining_daily = max_daily - daily_used
        daily_cap = math.floor(remaining_daily / fallback_risk) if fallback_risk > 0 else 999
    else:
        daily_cap = 999

    # Step 9: 4-way min
    final = min(math.floor(raw), mdd_cap, daily_cap, max_contracts)
    final = max(final, 0)

    # Step 10: Circuit breaker L1 preemptive halt — abs(L_t) + rho_j >= c * e * A
    topstep_params = tsm.get("topstep_params", {})
    if isinstance(topstep_params, str):
        topstep_params = json.loads(topstep_params) if topstep_params else {}
    c = topstep_params.get("c", 0.5)
    e = topstep_params.get("e", 0.01)
    l_halt = c * e * user_capital
    rho_j = final * fallback_risk
    cb_blocked = False
    if rho_j >= l_halt and final > 0:
        cb_blocked = True
        while final > 0 and (final * fallback_risk) >= l_halt:
            final -= 1
        final = max(final, 0)

    return {
        "contracts": final,
        "kelly_blended": round(blended, 6),
        "kelly_adjusted": round(kelly_with_aim, 6),
        "risk_per_contract": round(risk_per_contract, 2),
        "raw_contracts": math.floor(raw),
        "mdd_cap": mdd_cap,
        "daily_cap": daily_cap,
        "max_contracts": max_contracts,
        "cb_l1_halt": round(l_halt, 2),
        "cb_rho_j": round(rho_j, 2),
        "cb_blocked": cb_blocked,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Replay yesterday's ORB session (read-only)")
    parser.add_argument("--date", type=str, default=None,
                        help="Session date YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
        target_date = (now_et - timedelta(days=1)).date()

    print("=" * 70)
    print(f"CAPTAIN FUNCTION — Session Replay (READ-ONLY, NO TRADES)")
    print(f"Date: {target_date} ({target_date.strftime('%A')})")
    print("=" * 70)

    # Load locked strategies and Kelly params from QuestDB
    print("\nLoading data from QuestDB...")
    from shared.questdb_client import get_cursor
    import psycopg2

    # Locked strategies
    strategies = {}
    specs = {}
    with get_cursor() as cur:
        cur.execute("SELECT asset_id, locked_strategy, point_value, tick_size, margin_per_contract FROM p3_d00_asset_universe ORDER BY last_updated DESC")
        seen = set()
        for r in cur.fetchall():
            if r[0] in seen:
                continue
            seen.add(r[0])
            if r[0] in ACTIVE_ASSETS and r[1]:
                try:
                    strategies[r[0]] = json.loads(r[1]) if isinstance(r[1], str) else r[1]
                except (json.JSONDecodeError, TypeError):
                    strategies[r[0]] = {}
                specs[r[0]] = {"point_value": r[2] or 50.0, "tick_size": r[3] or 0.25, "margin": r[4] or 0.0}

    # Kelly params
    kelly_params = {}
    with get_cursor() as cur:
        cur.execute("SELECT asset_id, regime, session, kelly_full, shrinkage_factor FROM p3_d12_kelly_parameters ORDER BY last_updated DESC")
        seen = set()
        for r in cur.fetchall():
            key = (r[0], r[1], r[2])
            if key in seen:
                continue
            seen.add(key)
            kelly_params[key] = {"kelly_full": r[3] or 0.0, "shrinkage_factor": r[4] or 1.0}

    # EWMA states
    ewma_states = {}
    with get_cursor() as cur:
        cur.execute("SELECT asset_id, regime, session, win_rate, avg_win, avg_loss FROM p3_d05_ewma_states ORDER BY last_updated DESC")
        seen = set()
        for r in cur.fetchall():
            key = (r[0], r[1], r[2])
            if key in seen:
                continue
            seen.add(key)
            ewma_states[key] = {"win_rate": r[3] or 0.5, "avg_win": r[4] or 0.0, "avg_loss": r[5] or 0.0}

    # Capital silo
    with get_cursor() as cur:
        cur.execute("SELECT total_capital, accounts, max_simultaneous_positions FROM p3_d16_user_capital_silos WHERE user_id = 'primary_user' ORDER BY last_updated DESC LIMIT 1")
        row = cur.fetchone()
    user_capital = row[0] if row else 150000.0
    max_positions = row[2] if row else 5
    print(f"  Capital: ${user_capital:,.0f}, max positions: {max_positions}")

    # TSM config (full)
    tsm = {}
    with get_cursor() as cur:
        cur.execute("""SELECT account_id, classification, starting_balance, current_balance,
                       current_drawdown, daily_loss_used, max_drawdown_limit, max_daily_loss,
                       max_contracts, topstep_optimisation, risk_goal
                       FROM p3_d08_tsm_state WHERE account_id = '20319811'
                       ORDER BY last_updated DESC LIMIT 1""")
        row = cur.fetchone()
    if row:
        classification = row[1]
        if isinstance(classification, str):
            try:
                classification = json.loads(classification)
            except (json.JSONDecodeError, TypeError):
                classification = {}
        tsm = {
            "account_id": row[0],
            "classification": classification,
            "starting_balance": row[2] or 150000,
            "current_balance": row[3] or 150000,
            "current_drawdown": row[4] or 0,
            "daily_loss_used": row[5] or 0,
            "max_drawdown_limit": row[6],
            "max_daily_loss": row[7],
            "max_contracts": row[8] or 15,
            "risk_goal": row[10] or (classification.get("risk_goal", "GROW_CAPITAL") if classification else "GROW_CAPITAL"),
        }
    max_contracts = tsm.get("max_contracts", 15)
    print(f"  TSM: max_cts={max_contracts}, max_dd=${tsm.get('max_drawdown_limit')}, "
          f"max_daily=${tsm.get('max_daily_loss')}, risk_goal={tsm.get('risk_goal')}")

    print(f"  Strategies: {len(strategies)}, Kelly: {len(kelly_params)}, EWMA: {len(ewma_states)}")

    # Authenticate TopstepX
    print("\nAuthenticating TopstepX...")
    from shared.topstep_client import get_topstep_client

    client = get_topstep_client()
    client.authenticate()

    # Load contract IDs directly from config file (container may not have /captain/config mounted)
    contracts = {}
    for config_path in ["/app/contract_ids.json", "/captain/config/contract_ids.json",
                        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "contract_ids.json")]:
        if os.path.exists(config_path):
            with open(config_path) as f:
                cdata = json.load(f)
            for asset_id, info in cdata.get("contracts", {}).items():
                cid = info.get("contract_id")
                if cid:
                    contracts[asset_id] = cid
            print(f"  Contracts loaded from {config_path}")
            break

    if not contracts:
        print("  ERROR: No contract config found")
        return 1

    print(f"  Authenticated. {len(contracts)} contracts resolved.")

    # Process each asset
    print(f"\n{'='*70}")
    print(f"SIMULATING ORB FOR {len(ACTIVE_ASSETS)} ASSETS ON {target_date}")
    print(f"{'='*70}")

    results = []
    errors = []
    total_pnl = 0.0

    for asset_id in ACTIVE_ASSETS:
        session_type = ASSET_SESSION_MAP[asset_id]
        contract_id = contracts.get(asset_id)

        if not contract_id:
            errors.append({"asset": asset_id, "error": "No contract ID"})
            continue

        strategy = strategies.get(asset_id, {})
        spec = specs.get(asset_id, {"point_value": 50.0})

        print(f"\n  {asset_id} ({session_type}, {contract_id})")
        print(f"  {'─'*50}")

        # Fetch bars
        try:
            bars = fetch_bars(client, contract_id, target_date, session_type)
            print(f"    Bars: {len(bars)}")
        except Exception as e:
            err = {"asset": asset_id, "error": f"API error: {e}"}
            errors.append(err)
            print(f"    ERROR: {e}")
            continue

        if not bars:
            err = {"asset": asset_id, "error": "No bars returned"}
            errors.append(err)
            print(f"    No bars returned")
            continue

        # Debug: show first bar to understand format
        if bars:
            print(f"    First bar keys: {list(bars[0].keys())}")

        # Simulate ORB
        result = simulate_orb(bars, asset_id, session_type, target_date, strategy, spec)

        if result and "error" in result:
            errors.append(result)
            print(f"    ERROR: {result['error']}")
            continue

        if result and result.get("direction", 0) == 0:
            print(f"    OR: {result['or_high']}-{result['or_low']} (range={result['or_range']})")
            print(f"    Result: NO BREAKOUT")
            results.append(result)
            continue

        # Compute contracts (full B4 Kelly)
        session_id = {"NY": 1, "LONDON": 2, "APAC": 3, "NY_PRE": 1}.get(session_type, 1)
        sizing = compute_contracts(
            asset_id, result["pnl_per_contract"], spec,
            kelly_params, ewma_states, user_capital, max_contracts,
            strategy, tsm, session_id
        )

        result["contracts"] = sizing["contracts"]
        result["sizing"] = sizing
        result["total_pnl"] = round(result["pnl_per_contract"] * sizing["contracts"], 2)
        results.append(result)

        dir_str = result["direction_str"]
        print(f"    OR: {result['or_high']}-{result['or_low']} (range={result['or_range']})")
        print(f"    Breakout: {dir_str} at {result['breakout_time']}, entry={result['entry_price']}")
        print(f"    TP={result['tp_level']} (x{result['tp_mult']}), SL={result['sl_level']} (x{result['sl_mult']})")
        print(f"    Exit: {result['exit_reason']} at {result['exit_time']}, price={result['exit_price']}")
        print(f"    PnL/contract: ${result['pnl_per_contract']:+.2f} ({result['pnl_points']:+.4f} pts)")
        cb_tag = " ** CB L1 REDUCED **" if sizing.get('cb_blocked') else ""
        print(f"    Sizing: kelly={sizing['kelly_adjusted']:.4f}, risk/ct=${sizing['risk_per_contract']:.2f}, "
              f"raw={sizing['raw_contracts']}, mdd_cap={sizing['mdd_cap']}, daily_cap={sizing['daily_cap']}")
        print(f"    CB L1: rho_j=${sizing.get('cb_rho_j',0):.0f} vs L_halt=${sizing.get('cb_l1_halt',0):.0f}"
              f"{cb_tag}")
        print(f"    Contracts: {sizing['contracts']} -> Total PnL: ${result['total_pnl']:+.2f}")

    # Apply position limit (max_simultaneous_positions from D16)
    trades_with_contracts = [r for r in results if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0]
    no_breakout = [r for r in results if r.get("result") == "NO_BREAKOUT"]
    zero_sized = [r for r in results if r.get("direction", 0) != 0 and r.get("contracts", 0) == 0]

    # Sort by absolute PnL per contract (proxy for expected edge) — take top N
    trades_with_contracts.sort(key=lambda x: abs(x.get("pnl_per_contract", 0)), reverse=True)
    if len(trades_with_contracts) > max_positions:
        excluded = trades_with_contracts[max_positions:]
        trades_with_contracts = trades_with_contracts[:max_positions]
        for ex in excluded:
            ex["excluded_reason"] = f"Position limit ({max_positions})"
            ex["contracts"] = 0
            ex["total_pnl"] = 0

    total_pnl = sum(r.get("total_pnl", 0) for r in trades_with_contracts)

    # Summary
    print(f"\n{'='*70}")
    print(f"SESSION REPLAY SUMMARY — {target_date}")
    print(f"{'='*70}")

    trades_taken = trades_with_contracts

    print(f"\n  Trades taken:    {len(trades_taken)}/{len(ACTIVE_ASSETS)}")
    print(f"  No breakout:     {len(no_breakout)}")
    print(f"  Errors:          {len(errors)}")

    if trades_taken:
        print(f"\n  {'Asset':<6} {'Dir':<6} {'Entry':>10} {'Exit':>10} {'Reason':<8} {'Cts':>4} {'PnL':>12}")
        print(f"  {'─'*60}")
        for r in sorted(trades_taken, key=lambda x: x.get("total_pnl", 0), reverse=True):
            print(f"  {r['asset']:<6} {r['direction_str']:<6} {r['entry_price']:>10.2f} "
                  f"{r['exit_price']:>10.2f} {r['exit_reason']:<8} {r.get('contracts',0):>4} "
                  f"${r.get('total_pnl',0):>+10.2f}")

        print(f"  {'─'*60}")
        print(f"  {'TOTAL':>46} ${total_pnl:>+10.2f}")

        wins = [r for r in trades_taken if r.get("total_pnl", 0) > 0]
        losses = [r for r in trades_taken if r.get("total_pnl", 0) < 0]
        print(f"\n  Wins: {len(wins)}, Losses: {len(losses)}, "
              f"Win rate: {len(wins)/len(trades_taken)*100:.0f}%")

    if errors:
        print(f"\n  ERRORS:")
        for e in errors:
            print(f"    {e['asset']}: {e['error']}")

    print(f"\n  ** This is a SIMULATION. No real trades were placed. **")
    print(f"{'='*70}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
