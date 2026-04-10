# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B6: Signal Output — P3-PG-26 (Task 3.7 / ON lines 1076-1177).

Generates fully specified trading signals for the CURRENT USER.
Publishes to Redis captain:signals:{user_id} for Command routing.

Signal includes: direction, TP, SL, per-account breakdown, AIM context,
regime state, quality score, confidence tier.

Below-threshold signals included as available_not_recommended for transparency.

Reads: All shared intelligence + user-specific outputs from B4/B5/B5B
Writes: Redis signals channel, P3-D17 (session_log)
"""

import json
import logging
import uuid
from datetime import datetime

from shared.redis_client import publish_to_stream, STREAM_SIGNALS
from shared.questdb_client import get_cursor
from shared.statistics import get_ewma_for_regime
from shared.json_helpers import parse_json

logger = logging.getLogger(__name__)


def run_signal_output(
    recommended_trades: list[str],
    available_not_recommended: list[str],
    quality_results: dict,
    final_contracts: dict,
    account_recommendation: dict,
    account_skip_reason: dict,
    features: dict,
    ewma_states: dict,
    aim_breakdown: dict,
    combined_modifier: dict,
    regime_probs: dict,
    expected_edge: dict,
    locked_strategies: dict,
    tsm_configs: dict,
    user_silo: dict,
    assets_detail: dict,
    session_id: int,
) -> dict:
    """P3-PG-26: Signal output for one user.

    Publishes signals to Redis and returns signal list.
    """
    user_id = user_silo.get("user_id", "unknown")
    accounts = parse_json(user_silo.get("accounts", "[]"), [])
    total_capital = user_silo.get("total_capital", 0)

    # Load quality thresholds for confidence classification
    quality_ceiling = _load_system_param("quality_ceiling", 0.010)
    hard_floor = _load_system_param("quality_hard_floor", 0.003)

    signals = []

    for u in recommended_trades:
        strategy = locked_strategies.get(u, {})
        asset_detail = assets_detail.get(u, {})
        asset_features = features.get(u, {})

        r_probs = regime_probs.get(u, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5})
        regime = max(r_probs, key=r_probs.get)

        ewma = get_ewma_for_regime(u, regime, ewma_states, session_id)
        win_rate = ewma["win_rate"] if ewma else 0.5
        avg_win = ewma["avg_win"] if ewma else 0.0
        avg_loss = ewma["avg_loss"] if ewma else 0.0
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        qr = quality_results.get(u, {})

        # Direction and levels from locked strategy
        direction = _determine_direction(strategy, asset_features)
        if direction == 0:
            logger.warning("ON-B6: Skipping %s — no breakout direction resolved "
                           "(or_direction=%s, default_direction=%s)",
                           u, asset_features.get("or_direction"),
                           strategy.get("default_direction"))
            continue
        tp_level = _compute_tp(strategy, asset_features, direction)
        sl_level = _compute_sl(strategy, asset_features, direction)

        signal = {
            "signal_id": f"SIG-{uuid.uuid4().hex[:12].upper()}",
            "user_id": user_id,
            "asset": u,
            "session": session_id,
            "timestamp": datetime.now().isoformat(),
            "direction": direction,
            "tp_level": tp_level,
            "sl_level": sl_level,
            "sl_method": strategy.get("sl_method", "OR_RANGE"),
            "entry_conditions": strategy.get("entry_conditions", {}),

            # Per-account breakdown
            "per_account": _build_per_account(u, accounts, final_contracts, account_recommendation,
                                               account_skip_reason, tsm_configs),

            # Context for GUI
            "aim_breakdown": aim_breakdown.get(u, {}),
            "combined_modifier": combined_modifier.get(u, 1.0),
            "regime_state": regime,
            "regime_probs": r_probs,
            "expected_edge": expected_edge.get(u, 0.0),
            "win_rate": win_rate,
            "payoff_ratio": payoff_ratio,

            # User capital context
            "user_total_capital": total_capital,
            "user_daily_pnl": _get_daily_pnl(user_id),

            # Signal quality
            "quality_score": qr.get("quality_score", 0.0),
            "quality_multiplier": qr.get("quality_multiplier", 1.0),
            "data_maturity": qr.get("data_maturity", 0.0),

            # Confidence tier
            "confidence_tier": _classify_confidence(
                expected_edge.get(u, 0.0), combined_modifier.get(u, 1.0),
                quality_ceiling, hard_floor
            ),
        }

        signals.append(signal)

    # Below-threshold signals for transparency
    below_threshold = [
        {
            "asset": u,
            "quality_score": quality_results.get(u, {}).get("quality_score", 0.0),
            "expected_edge": expected_edge.get(u, 0.0),
            "reason": f"Below minimum quality threshold ({hard_floor})",
        }
        for u in available_not_recommended
    ]

    # Publish to Redis
    if signals or below_threshold:
        _publish_signals(user_id, signals, below_threshold, session_id)

    # Log to P3-D17
    _log_signal_output(user_id, session_id, signals, below_threshold)

    logger.info("ON-B6: %d signals published for user %s (session %d), %d below threshold",
                len(signals), user_id, session_id, len(below_threshold))

    return {
        "signals": signals,
        "below_threshold": below_threshold,
    }


# ---------------------------------------------------------------------------
# Signal construction helpers
# ---------------------------------------------------------------------------

def _determine_direction(strategy: dict, features: dict) -> int:
    """Determine trade direction from strategy and features.

    For ORB strategies with live OR tracker: the orchestrator injects
    ``or_direction`` into features after breakout detection.  Falls back
    to ``default_direction`` from the locked strategy (0 = pending).
    """
    # Live OR breakout direction (injected by orchestrator Phase B)
    or_direction = features.get("or_direction")
    if or_direction is not None and or_direction != 0:
        return int(or_direction)

    return strategy.get("default_direction", 0)


def _compute_tp(strategy: dict, features: dict, direction: int) -> float | None:
    """Compute take-profit level from strategy params."""
    tp_multiple = strategy.get("tp_multiple", 0.70)
    or_range = features.get("or_range")
    entry = features.get("entry_price")

    if or_range and entry:
        tp_dist = tp_multiple * or_range
        return entry + (tp_dist * direction) if direction != 0 else None

    return strategy.get("tp_level")


def _compute_sl(strategy: dict, features: dict, direction: int) -> float | None:
    """Compute stop-loss level from strategy params."""
    sl_multiple = strategy.get("sl_multiple", 0.35)
    or_range = features.get("or_range")
    entry = features.get("entry_price")

    if or_range and entry:
        sl_dist = sl_multiple * or_range
        return entry - (sl_dist * direction) if direction != 0 else None

    return strategy.get("sl_level")


def _build_per_account(
    asset_id: str,
    accounts: list[str],
    final_contracts: dict,
    account_recommendation: dict,
    account_skip_reason: dict,
    tsm_configs: dict,
) -> dict:
    """Build per-account trade breakdown."""
    result = {}
    for ac_id in accounts:
        tsm = tsm_configs.get(ac_id, {})
        classification = tsm.get("classification", {})

        contracts = final_contracts.get(asset_id, {}).get(ac_id, 0)
        rec = account_recommendation.get(asset_id, {}).get(ac_id, "SKIP")
        reason = account_skip_reason.get(asset_id, {}).get(ac_id)

        mdd_limit = tsm.get("max_drawdown_limit")
        current_dd = tsm.get("current_drawdown", 0)
        mll = tsm.get("max_daily_loss")
        daily_used = tsm.get("daily_loss_used", 0)

        result[ac_id] = {
            "contracts": contracts,
            "recommendation": rec,
            "skip_reason": reason,
            "account_name": tsm.get("name", ac_id),
            "category": classification.get("category"),
            "risk_goal": tsm.get("risk_goal"),
            "remaining_mdd": (mdd_limit - current_dd) if mdd_limit is not None else None,
            "remaining_mll": (mll - daily_used) if mll is not None else None,
            "pass_probability": tsm.get("pass_probability"),
            "risk_budget_pct": (daily_used / mll * 100) if mll and mll > 0 else None,
            "api_validated": tsm.get("api_validated", False),
        }

    return result


def _classify_confidence(edge: float, modifier: float, high_threshold: float, low_threshold: float) -> str:
    """Classify signal confidence tier for GUI display."""
    if edge > high_threshold and modifier > 1.0:
        return "HIGH"
    elif edge > low_threshold:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Publishers / Writers
# ---------------------------------------------------------------------------

def _publish_signals(user_id: str, signals: list, below_threshold: list, session_id: int):
    """Publish signals to Redis stream:signals (durable delivery)."""
    try:
        publish_to_stream(STREAM_SIGNALS, {
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "signals": signals,
            "below_threshold": below_threshold,
        })
        logger.debug("ON-B6: Published %d signals to %s", len(signals), STREAM_SIGNALS)
    except Exception as e:
        logger.error("ON-B6: Failed to publish signals: %s", e)


def _log_signal_output(user_id: str, session_id: int, signals: list, below_threshold: list):
    """Log signal output to P3-D17 session_log."""
    summary = json.dumps({
        "user_id": user_id,
        "session_id": session_id,
        "signal_count": len(signals),
        "below_threshold_count": len(below_threshold),
        "assets": [s["asset"] for s in signals],
    })
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d17_system_monitor_state
               (param_key, param_value, category, last_updated)
               VALUES (%s, %s, %s, now())""",
            (f"signal_output_{session_id}_{user_id}", summary, "signal_output"),
        )


def _get_daily_pnl(user_id: str) -> float:
    """Get today's cumulative P&L for user from P3-D03."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """SELECT sum(pnl) FROM p3_d03_trade_outcome_log
                   WHERE user_id = %s
                   AND exit_time >= cast(today() as timestamp)""",
                (user_id,),
            )
            row = cur.fetchone()
        return float(row[0]) if row and row[0] else 0.0
    except Exception:
        return 0.0




def _load_system_param(key: str, default):
    with get_cursor() as cur:
        cur.execute(
            """SELECT param_value FROM p3_d17_system_monitor_state
               WHERE param_key = %s
               LATEST ON last_updated PARTITION BY param_key""",
            (key,),
        )
        row = cur.fetchone()
    if row and row[0]:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            return default
    return default


