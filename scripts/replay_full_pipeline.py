#!/usr/bin/env python3
"""
Full Pipeline Replay — Replays historical data through the LIVE B1→B6 pipeline.

Fetches real 1-min bars from TopstepX for a past session, feeds them through
the OR tracker as synthetic ticks, runs the full signal pipeline (B1→B6),
and publishes signals to Redis so the GUI displays them.

AUTO_EXECUTE must be disabled on captain-command before running.

Usage (from host, with containers running):
    PYTHONPATH=.:captain-online:captain-command \
        python scripts/replay_full_pipeline.py --date 2026-03-30 --session NY

What happens:
    1. Fetches 1-min bars from TopstepX for the target date
    2. Runs Phase A (B1→B2→B3→B4→B5→B5B→B5C) against LIVE QuestDB data
    3. Feeds historical bars to an OR tracker as ticks (simulating MarketStream)
    4. On OR breakout, runs Phase B (B6) which publishes signals to Redis
    5. Command process picks up signals → pushes to GUI via WebSocket
    6. NO trades are executed (AUTO_EXECUTE must be false)
"""

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

# Ensure project root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "captain-online"))
sys.path.insert(0, os.path.join(_ROOT, "captain-command"))

logging.basicConfig(
    level=logging.INFO,
    format="[REPLAY] %(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("replay")

# Load .env file for credentials
_env_path = os.path.join(_ROOT, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = val

ET = ZoneInfo("America/New_York")

# Session configs
SESSION_CONFIG = {
    "NY":     {"id": 1, "or_start": "09:30", "or_end": "09:35", "eod": "15:55"},
    "APAC":   {"id": 3, "or_start": "18:00", "or_end": "18:05", "eod": "02:55"},
}

# NY session assets (9 assets — NKD is APAC only)
NY_ASSETS = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM", "MGC", "ZB", "ZN"]

# Contract ID mapping
CONTRACT_MAP = {}


def load_contract_map():
    """Load contract IDs from config."""
    global CONTRACT_MAP
    for path in [
        os.path.join(_ROOT, "config", "contract_ids.json"),
        "/captain/config/contract_ids.json",
    ]:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            contracts = data.get("contracts", data.get("assets", {}))
            CONTRACT_MAP = {
                asset: info["contract_id"]
                for asset, info in contracts.items()
                if isinstance(info, dict) and "contract_id" in info
            }
            logger.info("Loaded %d contract IDs from %s", len(CONTRACT_MAP), path)
            return
    logger.warning("No contract_ids.json found — will skip bar fetching")


def fetch_bars(client, contract_id: str, target_date: date, session_type: str) -> list[dict]:
    """Fetch 1-minute bars from TopstepX for a session."""
    import requests

    cfg = SESSION_CONFIG[session_type]
    or_start = datetime.strptime(cfg["or_start"], "%H:%M").time()
    eod = datetime.strptime(cfg["eod"], "%H:%M").time()

    fetch_start = datetime.combine(target_date, or_start, tzinfo=ET) - timedelta(minutes=5)
    fetch_end = datetime.combine(target_date, eod, tzinfo=ET) + timedelta(minutes=30)

    start_utc = fetch_start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S")
    end_utc = fetch_end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S")

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
        logger.error("Failed to fetch bars for %s: HTTP %d", contract_id, resp.status_code)
        return []
    data = resp.json()
    bars = data.get("bars", [])
    bars.reverse()  # Chronological order
    logger.info("Fetched %d bars for %s", len(bars), contract_id)
    return bars


def parse_bar_time(bar: dict) -> datetime | None:
    """Extract timestamp from bar dict."""
    val = bar.get("t") or bar.get("timestamp")
    if val and isinstance(val, str):
        val = val.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    return None


def run_phase_a(session_id: int) -> dict | None:
    """Run Phase A (B1→B5C) for one session using LIVE QuestDB data.

    Returns the full pipeline context or None if blocked.
    """
    from captain_online.blocks.b1_data_ingestion import run_data_ingestion
    from captain_online.blocks.b2_regime_probability import run_regime_probability
    from shared.aim_compute import run_aim_aggregation
    from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
    from captain_online.blocks.b5_trade_selection import run_trade_selection, apply_hmm_session_allocation
    from captain_online.blocks.b5b_quality_gate import run_quality_gate
    from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen

    logger.info("=" * 60)
    logger.info("PHASE A: Running B1→B5C for session %d", session_id)
    logger.info("=" * 60)

    # B1: Data ingestion
    b1 = run_data_ingestion(session_id)
    if b1 is None:
        logger.error("B1 returned None — no active assets")
        return None

    active = b1["active_assets"]
    logger.info("B1: %d active assets: %s", len(active), active)

    # B2: Regime probability
    b2 = run_regime_probability(
        active_assets=active,
        features=b1["features"],
        regime_models=b1["regime_models"],
    )
    logger.info("B2: Regime probs computed for %d assets", len(b2.get("regime_probs", {})))

    # B3: AIM aggregation
    b3 = run_aim_aggregation(
        active_assets=active,
        features=b1["features"],
        aim_states=b1["aim_states"],
        aim_weights=b1["aim_weights"],
    )
    logger.info("B3: Combined modifiers: %s",
                {k: f"{v:.3f}" for k, v in b3.get("combined_modifier", {}).items()})

    # Per-user loop (single user for now)
    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute("""SELECT user_id, status, starting_capital, total_capital,
                              accounts, max_simultaneous_positions, max_portfolio_risk_pct,
                              correlation_threshold, user_kelly_ceiling
                       FROM p3_d16_user_capital_silos
                       ORDER BY last_updated DESC LIMIT 1""")
        row = cur.fetchone()

    if not row:
        logger.error("No user silo found")
        return None

    user_silo = {
        "user_id": row[0], "status": row[1],
        "starting_capital": row[2], "total_capital": row[3],
        "accounts": row[4], "max_simultaneous_positions": row[5],
        "max_portfolio_risk_pct": row[6], "correlation_threshold": row[7],
        "user_kelly_ceiling": row[8] or 1.0,
    }
    accounts = json.loads(user_silo["accounts"]) if isinstance(user_silo["accounts"], str) else user_silo["accounts"]
    logger.info("User: %s, accounts: %s, capital: $%,.0f",
                user_silo["user_id"], accounts, user_silo["total_capital"])

    # B4: Kelly sizing
    b4 = run_kelly_sizing(
        active_assets=active,
        regime_probs=b2["regime_probs"],
        regime_uncertain=b2["regime_uncertain"],
        combined_modifier=b3["combined_modifier"],
        kelly_params=b1["kelly_params"],
        ewma_states=b1["ewma_states"],
        tsm_configs=b1["tsm_configs"],
        sizing_overrides=b1["sizing_overrides"],
        user_silo=user_silo,
        locked_strategies=b1["locked_strategies"],
        assets_detail=b1["assets_detail"],
        session_id=session_id,
    )

    if b4 is None or b4.get("silo_blocked"):
        logger.error("B4: Silo BLOCKED")
        return None

    # B5: Trade selection
    b5 = run_trade_selection(
        active_assets=active,
        final_contracts=b4["final_contracts"],
        account_recommendation=b4["account_recommendation"],
        account_skip_reason=b4["account_skip_reason"],
        ewma_states=b1["ewma_states"],
        regime_probs=b2["regime_probs"],
        user_silo=user_silo,
        session_id=session_id,
    )

    # HMM session allocation
    b5["final_contracts"] = apply_hmm_session_allocation(
        b5["selected_trades"], b5["final_contracts"],
        accounts, session_id,
    )

    logger.info("B5: Selected %d/%d assets: %s",
                len(b5["selected_trades"]), len(active), b5["selected_trades"])

    # B5B: Quality gate
    b5b = run_quality_gate(
        selected_trades=b5["selected_trades"],
        expected_edge=b5["expected_edge"],
        combined_modifier=b3["combined_modifier"],
        regime_probs=b2["regime_probs"],
        user_silo=user_silo,
        session_id=session_id,
    )
    logger.info("B5B: %d recommended, %d below threshold",
                len(b5b.get("recommended_trades", [])),
                len(b5b.get("available_not_recommended", [])))

    # B5C: Circuit breaker screen
    b5c = run_circuit_breaker_screen(
        recommended_trades=b5b.get("recommended_trades", []),
        final_contracts=b5["final_contracts"],
        account_recommendation=b5["account_recommendation"],
        account_skip_reason=b5["account_skip_reason"],
        accounts=accounts,
        tsm_configs=b1["tsm_configs"],
        session_id=session_id,
        proposed_contracts=b5["final_contracts"],
    )

    logger.info("B5C: %d trades pass circuit breaker", len(b5c.get("recommended_trades", [])))

    # Compile Phase A results
    return {
        "session_id": session_id,
        "active_assets": active,
        "b1": b1, "b2": b2, "b3": b3, "b4": b4, "b5": b5, "b5b": b5b, "b5c": b5c,
        "user_silo": user_silo,
        "accounts": accounts,
    }


def _replay_compute_or_volume(asset_id: str, bars: list[dict],
                              session_type: str) -> int | None:
    """Sum volume from replay bars that fall within the OR window.

    Returns total volume during the OR formation period, or None if
    no bars matched.
    """
    cfg = SESSION_CONFIG.get(session_type)
    if not cfg:
        return None
    or_start_str = cfg.get("or_start", "09:30")
    or_end_str = cfg.get("or_end", "09:35")
    or_start_t = datetime.strptime(or_start_str, "%H:%M").time()
    or_end_t = datetime.strptime(or_end_str, "%H:%M").time()

    total_vol = 0
    matched = 0
    for bar in bars:
        t = parse_bar_time(bar)
        if t is None:
            continue
        t_et = t.astimezone(ET).time()
        if or_start_t <= t_et < or_end_t:
            vol = bar.get("v") or bar.get("volume", 0)
            total_vol += int(vol)
            matched += 1

    return total_vol if matched > 0 else None


def _replay_recompute_aim15(asset_id: str, b1: dict, b3: dict,
                            bars: list[dict] | None = None,
                            session_type: str = "NY"):
    """AIM-15 Phase B for replay: recompute volume modifier after OR close.

    Uses replay bars to compute today's OR volume (instead of the live
    TopstepX REST API which isn't available during replay), then compares
    to the 20-day historical average from P3-D29.
    """
    try:
        from captain_online.blocks.b1_features import (
            _get_historical_volume_first_N_min,
            get_or_window_minutes, store_opening_volume,
        )
        from shared.aim_compute import (
            _aim15_volume, MODIFIER_FLOOR, MODIFIER_CEILING, _clamp,
        )
        from captain_online.blocks.b8_or_tracker import get_asset_session_type

        locked = b1.get("locked_strategies", {}).get(asset_id, {})
        or_min = get_or_window_minutes(locked)

        # Compute today's volume from replay bars (not live API)
        if bars is None:
            logger.debug("AIM-15 replay: no bars for %s — skipping", asset_id)
            return
        vol_now = _replay_compute_or_volume(asset_id, bars, session_type)
        if vol_now is None or vol_now <= 0:
            logger.debug("AIM-15 replay: no OR volume for %s", asset_id)
            return

        # Store today's volume in D29 for future reference
        sess_type = get_asset_session_type(asset_id)
        store_opening_volume(asset_id, sess_type, or_min, vol_now)

        # Get 20-day historical average from P3-D29
        hist_vols = _get_historical_volume_first_N_min(asset_id, or_min, lookback=20)
        if not hist_vols or len(hist_vols) < 5:
            logger.debug("AIM-15 replay: insufficient D29 history for %s (%d rows)",
                         asset_id, len(hist_vols) if hist_vols else 0)
            return

        vol_avg = sum(hist_vols) / len(hist_vols)
        if vol_avg <= 0:
            return

        volume_ratio = vol_now / vol_avg

        # Update feature
        features = b1.get("features", {})
        if asset_id in features:
            features[asset_id]["opening_volume_ratio"] = volume_ratio

        # Compute AIM-15 modifier
        result = _aim15_volume({"opening_volume_ratio": volume_ratio}, {})
        new_mod = result["modifier"]

        # Update combined modifier
        combined = b3.get("combined_modifier", {})
        if asset_id in combined:
            old_combined = combined[asset_id]
            updated = _clamp(old_combined * new_mod, MODIFIER_FLOOR, MODIFIER_CEILING)
            combined[asset_id] = updated
            logger.info("AIM-15 Phase B (replay) for %s: or_vol=%d, hist_avg=%.0f, "
                        "ratio=%.2f, mod=%.2f, combined %.3f->%.3f",
                        asset_id, vol_now, vol_avg, volume_ratio, new_mod,
                        old_combined, updated)
    except Exception as e:
        logger.warning("AIM-15 Phase B recompute skipped for %s: %s", asset_id, e)


def run_phase_b(asset_id: str, or_state: dict, phase_a: dict,
                bars: list[dict] | None = None, session_type: str = "NY"):
    """Run Phase B (B6) for one asset after OR breakout.

    Publishes signal to Redis for GUI consumption.
    """
    from captain_online.blocks.b6_signal_output import run_signal_output

    session_id = phase_a["session_id"]
    b1 = phase_a["b1"]
    b2 = phase_a["b2"]
    b3 = phase_a["b3"]
    b5 = phase_a["b5"]
    b5b = phase_a["b5b"]
    b5c = phase_a["b5c"]
    user_silo = phase_a["user_silo"]

    # Inject OR data into features
    features = b1.get("features", {})
    asset_features = features.get(asset_id, {})
    asset_features["or_range"] = or_state.get("or_range", 0)
    asset_features["entry_price"] = or_state.get("entry_price", 0)
    asset_features["or_direction"] = or_state.get("direction", 0)

    # AIM-15 Phase B: recompute volume ratio with actual first-m-min data
    _replay_recompute_aim15(asset_id, b1, b3, bars=bars, session_type=session_type)

    logger.info("PHASE B: Running B6 for %s — direction=%s, entry=%.2f, or_range=%.2f",
                asset_id,
                "LONG" if or_state.get("direction") == 1 else "SHORT",
                or_state.get("entry_price", 0),
                or_state.get("or_range", 0))

    result = run_signal_output(
        recommended_trades=b5c.get("recommended_trades", []),
        available_not_recommended=b5b.get("available_not_recommended", []),
        quality_results=b5b,
        final_contracts=b5c.get("final_contracts", b5["final_contracts"]),
        account_recommendation=b5c.get("account_recommendation", b5["account_recommendation"]),
        account_skip_reason=b5c.get("account_skip_reason", b5["account_skip_reason"]),
        features=features,
        ewma_states=b1["ewma_states"],
        aim_breakdown=b3.get("aim_breakdown", {}),
        combined_modifier=b3["combined_modifier"],
        regime_probs=b2["regime_probs"],
        expected_edge=b5.get("expected_edge", {}),
        locked_strategies=b1["locked_strategies"],
        tsm_configs=b1["tsm_configs"],
        user_silo=user_silo,
        assets_detail=b1["assets_detail"],
        session_id=session_id,
    )

    signals = result.get("signals", [])
    logger.info("B6: Published %d signals to Redis", len(signals))
    for sig in signals:
        logger.info("  SIGNAL: %s %s x%s — TP=%.2f SL=%.2f confidence=%s",
                     sig.get("direction"), sig.get("asset"),
                     sig.get("per_account", {}).get(
                         list(sig.get("per_account", {}).keys())[0] if sig.get("per_account") else "?", {}
                     ).get("contracts", "?"),
                     sig.get("tp_level", 0), sig.get("sl_level", 0),
                     sig.get("confidence_tier", "?"))

    return result


def run_replay(target_date: date, session_type: str = "NY"):
    """Full pipeline replay for a historical session."""
    cfg = SESSION_CONFIG[session_type]
    session_id = cfg["id"]

    logger.info("=" * 60)
    logger.info("FULL PIPELINE REPLAY")
    logger.info("Date: %s, Session: %s (ID=%d)", target_date, session_type, session_id)
    logger.info("=" * 60)

    # Safety check: AUTO_EXECUTE must be disabled
    import redis
    # Check by querying the command container's env (we can't directly, but we warn)
    logger.warning("SAFETY: Ensure AUTO_EXECUTE=false on captain-command before proceeding!")
    logger.warning("If AUTO_EXECUTE is true, replay signals WILL trigger real orders!")

    # Step 1: Authenticate and fetch historical bars
    load_contract_map()
    if not CONTRACT_MAP:
        logger.error("No contract map — cannot fetch bars")
        return

    from shared.topstep_client import get_topstep_client
    client = get_topstep_client()
    client.authenticate()
    logger.info("TopstepX authenticated")

    # Fetch bars for all session assets
    assets = NY_ASSETS if session_type == "NY" else ["NKD"]
    all_bars = {}
    for asset in assets:
        cid = CONTRACT_MAP.get(asset)
        if not cid:
            logger.warning("No contract ID for %s — skipping", asset)
            continue
        bars = fetch_bars(client, cid, target_date, session_type)
        if bars:
            all_bars[asset] = bars

    logger.info("Fetched bars for %d/%d assets", len(all_bars), len(assets))

    if not all_bars:
        logger.error("No bars fetched — cannot replay")
        return

    # Step 2: Run Phase A
    phase_a = run_phase_a(session_id)
    if phase_a is None:
        logger.error("Phase A failed — aborting replay")
        return

    # Step 3: Set up OR tracker and feed historical ticks
    from captain_online.blocks.b8_or_tracker import ORTracker

    tracker = ORTracker(cutoff_minutes=30)

    # Register all assets with bars
    for asset in all_bars:
        tracker.register_asset(asset, session_date=target_date)
        logger.info("OR tracker registered: %s", asset)

    # Merge and sort all bars by timestamp
    merged_bars = []
    for asset, bars in all_bars.items():
        cid = CONTRACT_MAP[asset]
        for bar in bars:
            t = parse_bar_time(bar)
            if t:
                merged_bars.append((t, asset, cid, bar))
    merged_bars.sort(key=lambda x: x[0])

    logger.info("Total bars to replay: %d", len(merged_bars))

    # Step 4: Feed bars as ticks
    resolved_assets = set()
    phase_b_done = False

    logger.info("")
    logger.info("=" * 60)
    logger.info("REPLAYING TICKS — OR detection active")
    logger.info("=" * 60)

    for ts, asset, cid, bar in merged_bars:
        # Construct synthetic quote (what MarketStream would send)
        close = bar.get("c") or bar.get("close", 0)
        high = bar.get("h") or bar.get("high", close)
        low = bar.get("l") or bar.get("low", close)

        # Feed high, low, and close as separate ticks to capture the range
        for price in [high, low, close]:
            if price and price > 0:
                quote = {"contractId": cid, "lastPrice": float(price)}
                tracker.on_quote(quote)

        # Check for breakout
        tracker.check_expirations()
        state = tracker.get_state(asset)
        if state and state.is_resolved and asset not in resolved_assets:
            resolved_assets.add(asset)
            if state.direction != 0:
                t_et = ts.astimezone(ET)
                logger.info("*** OR BREAKOUT: %s %s at %.2f (range=%.4f) at %s ***",
                            asset,
                            "LONG" if state.direction == 1 else "SHORT",
                            state.entry_price or 0,
                            state.or_range or 0,
                            t_et.strftime("%H:%M:%S ET"))
            else:
                logger.info("*** OR EXPIRED: %s — no breakout within cutoff ***", asset)

    # Step 5: Run Phase B for all resolved assets
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE B: Generating signals for %d resolved assets", len(resolved_assets))
    logger.info("=" * 60)

    for asset in resolved_assets:
        state = tracker.get_state(asset)
        if state and state.direction != 0:
            # Convert to dict for Phase B
            state_dict = {
                "direction": state.direction,
                "entry_price": state.entry_price or 0,
                "or_range": state.or_range or 0,
                "state": state.state.value,
            }
            run_phase_b(asset, state_dict, phase_a,
                        bars=all_bars.get(asset, []), session_type=session_type)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("REPLAY COMPLETE")
    logger.info("  Date: %s, Session: %s", target_date, session_type)
    logger.info("  Assets with bars: %d", len(all_bars))
    logger.info("  OR breakouts: %d", sum(1 for a in resolved_assets
                if tracker.get_state(a) and tracker.get_state(a).direction != 0))
    logger.info("  OR expired: %d", sum(1 for a in resolved_assets
                if tracker.get_state(a) and tracker.get_state(a).direction == 0))
    logger.info("  Signals published to Redis → check GUI")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Full pipeline replay")
    parser.add_argument("--date", default=None, help="Target date (YYYY-MM-DD). Default: today")
    parser.add_argument("--session", default="NY", choices=["NY", "APAC"], help="Session to replay")
    args = parser.parse_args()

    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = date.today()

    run_replay(target, args.session)


if __name__ == "__main__":
    main()
