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
import contextlib
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta, date, timezone
from unittest.mock import patch
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

# Session asset groups
NY_ASSETS = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM"]
LON_ASSETS = ["MGC"]

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
    logger.info(
        f"User: {user_silo['user_id']}, accounts: {accounts}, "
        f"capital: ${user_silo['total_capital']:,.0f}"
    )

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
        locked_strategies=b1.get("locked_strategies"),
        assets_detail=b1.get("assets_detail"),
        open_positions=[],  # No live positions in replay
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


def _replay_compute_or_range(asset_id: str, bars: list[dict],
                              session_type: str) -> float | None:
    """Compute OR price range (high-low) from replay bars within the OR window.

    Mirrors `_replay_compute_or_volume` for the new D29 `or_range_first_m_min`
    column added in Phase 2 (F-04 — Kelly SL distance unification). Used so the
    replay harness backfills the same column the live `b8_or_tracker` writes
    via `store_opening_volume(or_range=...)`.
    """
    cfg = SESSION_CONFIG.get(session_type)
    if not cfg:
        return None
    or_start_str = cfg.get("or_start", "09:30")
    or_end_str = cfg.get("or_end", "09:35")
    or_start_t = datetime.strptime(or_start_str, "%H:%M").time()
    or_end_t = datetime.strptime(or_end_str, "%H:%M").time()

    highs: list[float] = []
    lows: list[float] = []
    for bar in bars:
        t = parse_bar_time(bar)
        if t is None:
            continue
        t_et = t.astimezone(ET).time()
        if or_start_t <= t_et < or_end_t:
            h = bar.get("h") or bar.get("high")
            lo = bar.get("l") or bar.get("low")
            if h is None or lo is None:
                continue
            try:
                highs.append(float(h))
                lows.append(float(lo))
            except (TypeError, ValueError):
                continue
    if not highs or not lows:
        return None
    rng = max(highs) - min(lows)
    return rng if rng > 0 else None


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

        # Store today's volume + OR range in D29 for future reference.
        # `or_range` powers Phase 2 Kelly SL distance derivation (F-04).
        sess_type = get_asset_session_type(asset_id)
        or_range_now = _replay_compute_or_range(asset_id, bars, session_type)
        store_opening_volume(asset_id, sess_type, or_min, vol_now,
                             or_range=or_range_now)

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

    # Filter recommended_trades to JUST this asset. Without the filter, every
    # Phase B call publishes signals for every previously-resolved asset too,
    # because `features` is mutated in place each call (or_direction stays set
    # for prior assets). The live orchestrator does the same filtering via
    # `assets=newly_resolved` in `_run_b6_for_user`; the replay must mirror it
    # to avoid emitting cumulative batches that flood the GUI signal panel.
    all_recommended = b5c.get("recommended_trades", [])
    recommended_for_asset = [asset_id] if asset_id in all_recommended else []

    result = run_signal_output(
        recommended_trades=recommended_for_asset,
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
        tp = sig.get("tp_level")
        sl = sig.get("sl_level")
        per_acc = sig.get("per_account") or {}
        contracts = next(iter(per_acc.values()), {}).get("contracts", "?") if per_acc else "?"
        logger.info(
            "  SIGNAL: %s %s x%s — TP=%s SL=%s confidence=%s",
            sig.get("direction"), sig.get("asset"), contracts,
            f"{tp:.2f}" if isinstance(tp, (int, float)) else "None",
            f"{sl:.2f}" if isinstance(sl, (int, float)) else "None",
            sig.get("confidence_tier", "?"),
        )

    return result


# ---------------------------------------------------------------------------
# Replay harness helpers (not live code)
# ---------------------------------------------------------------------------

def _seed_quote_cache(all_bars: dict[str, list[dict]]) -> int:
    """Populate shared.topstep_stream.quote_cache so B1's Data Moderator sees
    a fresh quote per asset (live MarketStream would do this)."""
    from shared.topstep_stream import quote_cache
    now_iso = datetime.now(timezone.utc).isoformat()
    seeded = 0
    for asset, bars in all_bars.items():
        cid = CONTRACT_MAP.get(asset)
        if not cid or not bars:
            continue
        px = bars[0].get("c") or bars[0].get("close")
        if not px:
            continue
        quote_cache.update(cid, {"lastPrice": float(px), "timestamp": now_iso})
        seeded += 1
    logger.info("Seeded quote_cache for %d/%d assets", seeded, len(all_bars))
    return seeded


class _FrozenDatetime:
    """Shim for `datetime` inside b8_or_tracker. `.now()` returns a harness-set
    time; everything else delegates to the real stdlib datetime."""
    _current: datetime | None = None

    @classmethod
    def set(cls, t: datetime) -> None:
        cls._current = t

    @classmethod
    def now(cls, tz=None):
        if cls._current is None:
            return datetime.now(tz)
        return cls._current.astimezone(tz) if tz else cls._current

    @classmethod
    def combine(cls, *a, **kw):
        return datetime.combine(*a, **kw)

    @classmethod
    def fromisoformat(cls, s):
        return datetime.fromisoformat(s)

    @classmethod
    def fromtimestamp(cls, *a, **kw):
        return datetime.fromtimestamp(*a, **kw)

    @classmethod
    def strptime(cls, *a, **kw):
        return datetime.strptime(*a, **kw)


@contextlib.contextmanager
def _replay_clock():
    """Scope-limited monkey-patch of b8_or_tracker.datetime. Only affects the
    OR tracker module's namespace; production containers are untouched."""
    from captain_online.blocks import b8_or_tracker
    with patch.object(b8_or_tracker, "datetime", _FrozenDatetime):
        yield _FrozenDatetime


def _fmt(v, nd=2):
    if isinstance(v, (int, float)):
        return f"{v:.{nd}f}"
    return "None"


def _print_replay_summary(tracker, signals_by_asset: dict, cb_blocks: dict) -> None:
    """One compact table: OR + signal + CB flags per asset. Loud markers if
    or_range==0 (harness clock regression) or TP/SL missing (latent B6 bug)."""
    logger.info("")
    logger.info("=" * 88)
    logger.info("REPLAY DIAGNOSTIC TABLE")
    logger.info("=" * 88)
    logger.info("%-5s %-6s %6s %4s %9s %9s %9s %-20s",
                "asset", "or_rng", "ticks", "dir", "entry", "tp", "sl", "flags")
    logger.info("-" * 88)
    issue3 = issue4 = 0
    for asset in sorted(signals_by_asset.keys() | {a for a in tracker.get_all_states()}):
        st = tracker.get_state(asset)
        sig = signals_by_asset.get(asset) or {}
        or_rng = st.or_range if st else None
        ticks = st.tick_count if st else 0
        direction = sig.get("direction") or (st.direction if st else 0)
        entry = sig.get("entry_price") or (st.entry_price if st else None)
        tp = sig.get("tp_level")
        sl = sig.get("sl_level")
        flags = []
        if or_rng == 0 or or_rng is None:
            flags.append("OR=0")
            issue3 += 1
        if sig and (tp is None or sl is None):
            flags.append("TP/SL=None")
            issue4 += 1
        cb_reason = cb_blocks.get(asset)
        if cb_reason:
            flags.append(f"CB:{cb_reason[:14]}")
        logger.info("%-5s %6s %6d %4s %9s %9s %9s %-20s",
                    asset, _fmt(or_rng, 4), ticks, str(direction),
                    _fmt(entry), _fmt(tp), _fmt(sl), ",".join(flags) or "OK")
    logger.info("-" * 88)
    if issue3:
        logger.warning("!! ISSUE 3: %d assets with or_range=0 (harness clock failure)", issue3)
    if issue4:
        logger.warning("!! ISSUE 4: %d signals with None TP/SL (latent B6 bug)", issue4)
    if not issue3 and not issue4:
        logger.info("No harness-side regressions detected.")
    logger.info("=" * 88)


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
    assets = NY_ASSETS if session_type == "NY" else LON_ASSETS if session_type == "LON" else ["NKD"]
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

    # Seed quote_cache so B1 Data Moderator sees a fresh quote per asset
    # (substitute for live MarketStream; see docs2/e2e-script-issues/claude-analysis.)
    _seed_quote_cache(all_bars)

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

    with _replay_clock() as clk:
        for ts, asset, cid, bar in merged_bars:
            clk.set(ts)  # advance OR-tracker clock to bar time

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
                                state.entry_price or 0,  # decimal-boundary: ok (price for log display only, not arithmetic)
                                state.or_range or 0,  # decimal-boundary: ok (or_range is a price range, not money)
                                t_et.strftime("%H:%M:%S ET"))
                else:
                    logger.info("*** OR EXPIRED: %s — no breakout within cutoff ***", asset)

    # Step 5: Run Phase B for all resolved assets
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE B: Generating signals for %d resolved assets", len(resolved_assets))
    logger.info("=" * 60)

    signals_by_asset: dict[str, dict] = {}
    for asset in resolved_assets:
        state = tracker.get_state(asset)
        if state and state.direction != 0:
            # Convert to dict for Phase B
            state_dict = {
                "direction": state.direction,
                "entry_price": state.entry_price or 0,  # decimal-boundary: ok (price for downstream simulation; OR tracker uses native floats)
                "or_range": state.or_range or 0,  # decimal-boundary: ok (or_range is a price range, not money)
                "state": state.state.value,
            }
            result = run_phase_b(asset, state_dict, phase_a,
                                 bars=all_bars.get(asset, []), session_type=session_type)
            for sig in (result or {}).get("signals", []):
                signals_by_asset[sig.get("asset", asset)] = sig

    # CB block reasons per asset (from Phase A B5C output, if available)
    cb_blocks: dict[str, str] = {}
    b5c = (phase_a or {}).get("b5c") or {}
    for asset_map in (b5c.get("account_skip_reason") or {}).values() if isinstance(b5c.get("account_skip_reason"), dict) else []:
        pass  # shape varies — covered by per-asset scan below
    for a, per_acc in (b5c.get("account_skip_reason") or {}).items():
        if isinstance(per_acc, dict):
            for reason in per_acc.values():
                if reason and "L" in str(reason):
                    cb_blocks[a] = str(reason)
                    break

    _print_replay_summary(tracker, signals_by_asset, cb_blocks)

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
