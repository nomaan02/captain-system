# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B5B: Signal Quality Gate — P3-PG-25B (Task 3.6 / ON lines 972-1072).

Filters selected trades by minimum quality threshold before signal generation.
Signals below quality_hard_floor are excluded. Between floor and ceiling,
graduated sizing via quality_multiplier.

Quality score = expected_edge × combined_modifier × data_maturity

Reads: P3-D03 (trade count), P3-D05 (EWMA), P3-D17 (system params)
Writes: P3-D17 (session_log)
"""

import json
import logging
from datetime import datetime

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)


def run_quality_gate(
    selected_trades: list[str],
    expected_edge: dict,
    combined_modifier: dict,
    regime_probs: dict,
    user_silo: dict,
    session_id: int,
) -> dict:
    """P3-PG-25B: Signal quality gate for one user.

    Returns:
        dict with recommended_trades, available_not_recommended, quality_results
    """
    user_id = user_silo.get("user_id", "unknown")

    # Load quality thresholds from P3-D17
    hard_floor = _load_system_param("quality_hard_floor", 0.003)
    quality_ceiling = _load_system_param("quality_ceiling", 0.010)

    quality_results = {}

    for u in selected_trades:
        # Trade count for data maturity
        # Cold-start: set floor at 0.5 so quality gate doesn't block all trades
        # on fresh systems. Full maturity requires 50 trades.
        trade_count = _get_trade_count(u)
        data_maturity = min(1.0, max(0.5, trade_count / 50.0))

        # Quality score
        edge = expected_edge.get(u, 0.0)
        modifier = combined_modifier.get(u, 1.0)
        quality_score = edge * modifier * data_maturity

        # Gate logic
        if quality_score < hard_floor:
            quality_multiplier = 0.0
            passes_gate = False
        else:
            quality_multiplier = min(1.0, quality_score / quality_ceiling) if quality_ceiling > 0 else 1.0
            passes_gate = True

        quality_results[u] = {
            "quality_score": quality_score,
            "quality_multiplier": quality_multiplier,
            "passes_gate": passes_gate,
            "edge": edge,
            "modifier": modifier,
            "data_maturity": data_maturity,
            "trade_count": trade_count,
        }

        if not passes_gate:
            logger.info("ON-B5B: Asset %s quality_score %.6f below floor %.6f — AVAILABLE_NOT_RECOMMENDED",
                        u, quality_score, hard_floor)

    # Split
    recommended_trades = [u for u in selected_trades if quality_results.get(u, {}).get("passes_gate", False)]
    available_not_recommended = [u for u in selected_trades if not quality_results.get(u, {}).get("passes_gate", True)]

    # Log session results to P3-D17
    _log_quality_results(session_id, user_id, selected_trades, recommended_trades,
                         available_not_recommended, quality_results)

    logger.info("ON-B5B: Quality gate for user %s: %d recommended, %d below threshold",
                user_id, len(recommended_trades), len(available_not_recommended))

    return {
        "recommended_trades": recommended_trades,
        "available_not_recommended": available_not_recommended,
        "quality_results": quality_results,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_trade_count(asset_id: str) -> int:
    """Count trades for an asset in P3-D03."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT count() FROM p3_d03_trade_outcome_log WHERE asset = %s",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else 0


def _load_system_param(key: str, default):
    """Load a system parameter from P3-D17."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT param_value FROM p3_d17_system_monitor_state
               LATEST ON last_updated PARTITION BY param_key
               WHERE param_key = %s""",
            (key,),
        )
        row = cur.fetchone()
    if row and row[0]:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            return default
    return default


def _log_quality_results(session_id, user_id, selected, recommended, below_threshold, quality_results):
    """Log quality gate results to P3-D17."""
    summary = json.dumps({
        "session": session_id,
        "user_id": user_id,
        "total_selected": len(selected),
        "total_recommended": len(recommended),
        "total_below_threshold": len(below_threshold),
        "quality_scores": {
            u: {
                "quality_score": qr["quality_score"],
                "passes_gate": qr["passes_gate"],
                "data_maturity": qr["data_maturity"],
            }
            for u, qr in quality_results.items()
        },
    })
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d17_system_monitor_state
               (param_key, param_value, category, last_updated)
               VALUES (%s, %s, %s, now())""",
            (f"session_log_{session_id}_{user_id}", summary, "session_log"),
        )
