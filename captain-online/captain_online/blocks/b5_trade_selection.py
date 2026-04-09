# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B5: Universe-Level Trade Selection — P3-PG-25 (Task 3.5 / ON lines 896-968).

Selects which assets the CURRENT USER should trade this session.
Considers: expected edge, contract sizing (user-specific), cross-asset correlation,
max simultaneous positions.

V3: HMM session-partitioned budget allocation from P3-D26 replaces FCFS.
Cold start: <20 days → equal weights; 20-59 → blended 50/50; 60+ → full HMM.

Reads: P3-D05 (EWMA), P3-D07 (correlation), P3-D16 (user silo), P3-D26 (HMM)
Writes: nothing (pure computation)
"""

import json
import logging
from typing import Optional

from shared.questdb_client import get_cursor
from shared.statistics import get_ewma_for_regime

logger = logging.getLogger(__name__)


def run_trade_selection(
    active_assets: list[str],
    final_contracts: dict,
    account_recommendation: dict,
    account_skip_reason: dict,
    ewma_states: dict,
    regime_probs: dict,
    user_silo: dict,
    session_id: int,
) -> dict:
    """P3-PG-25: Universe-level trade selection for one user.

    Returns:
        dict with selected_trades, score, expected_edge, updated final_contracts/recommendations
    """
    user_id = user_silo.get("user_id", "unknown")
    accounts = _parse_json(user_silo.get("accounts", "[]"), [])

    # Compute expected edge per asset (shared intelligence)
    expected_edge = {}
    score = {}

    for u in active_assets:
        r_probs = regime_probs.get(u, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5})
        regime = max(r_probs, key=r_probs.get)
        ewma = get_ewma_for_regime(u, regime, ewma_states, session_id)

        if ewma:
            edge = ewma["win_rate"] * ewma["avg_win"] - (1 - ewma["win_rate"]) * ewma["avg_loss"]
        else:
            edge = 0.0

        expected_edge[u] = edge

        # Score = edge × max contracts across this user's accounts
        max_contracts = max(
            (final_contracts.get(u, {}).get(ac, 0) for ac in accounts), default=0
        )
        score[u] = edge * max_contracts

    # Cross-asset correlation filter
    corr_threshold = user_silo.get("correlation_threshold", 0.7)

    if len(active_assets) > 1:
        corr_matrix = _load_correlation_matrix(active_assets)

        for i, u1 in enumerate(active_assets):
            for j, u2 in enumerate(active_assets):
                if i >= j:
                    continue
                corr = _get_correlation(corr_matrix, u1, u2)
                if corr is not None and corr > corr_threshold:
                    # Reduce contracts for lower-scoring asset
                    if score.get(u1, 0) > score.get(u2, 0):
                        for ac in accounts:
                            fc = final_contracts.get(u2, {}).get(ac, 0)
                            final_contracts.setdefault(u2, {})[ac] = fc // 2
                    else:
                        for ac in accounts:
                            fc = final_contracts.get(u1, {}).get(ac, 0)
                            final_contracts.setdefault(u1, {})[ac] = fc // 2

    # Max simultaneous positions
    ranked_assets = sorted(active_assets, key=lambda u: score.get(u, 0), reverse=True)
    max_pos = user_silo.get("max_simultaneous_positions")

    if max_pos is not None and len(ranked_assets) > max_pos:
        for u in ranked_assets[max_pos:]:
            for ac in accounts:
                final_contracts.setdefault(u, {})[ac] = 0

    # Reconcile recommendations after B5 modifications
    for u in active_assets:
        for ac in accounts:
            if final_contracts.get(u, {}).get(ac, 0) == 0:
                if account_recommendation.get(u, {}).get(ac) == "TRADE":
                    account_recommendation.setdefault(u, {})[ac] = "SKIP"
                    account_skip_reason.setdefault(u, {})[ac] = \
                        "Removed by portfolio-level constraint (correlation or position limit)"

    # Select trades
    selected_trades = []
    for u in ranked_assets:
        max_contracts = max(
            (final_contracts.get(u, {}).get(ac, 0) for ac in accounts), default=0
        )
        if max_contracts > 0 and expected_edge.get(u, 0) > 0:
            selected_trades.append(u)

    logger.info("ON-B5: Trade selection for user %s: %d/%d assets selected",
                user_id, len(selected_trades), len(active_assets))

    return {
        "selected_trades": selected_trades,
        "score": score,
        "expected_edge": expected_edge,
        "final_contracts": final_contracts,
        "account_recommendation": account_recommendation,
        "account_skip_reason": account_skip_reason,
    }


# ---------------------------------------------------------------------------
# V3: HMM Session Budget Allocation
# ---------------------------------------------------------------------------

def apply_hmm_session_allocation(
    selected_trades: list[str],
    final_contracts: dict,
    accounts: list[str],
    session_id: int,
) -> dict:
    """V3: HMM session-partitioned budget allocation from P3-D26.

    Replaces FCFS with OO-ranked allocation within HMM session windows.
    Cold start: <20 days → equal weights; 20-59 → blended 50/50; 60+ → full HMM.
    Floor = 0.05 per session.
    """
    hmm_state = _load_hmm_opportunity_state()
    if hmm_state is None:
        return final_contracts  # No HMM data — keep as-is

    opp_weights = _parse_json(hmm_state.get("opportunity_weights"), {})
    n_obs = hmm_state.get("n_observations", 0)
    cold_start = hmm_state.get("cold_start", True)

    session_key = {1: "NY", 2: "LON", 3: "APAC"}.get(session_id, "NY")

    # Determine weight for this session
    if cold_start or n_obs < 20:
        # Equal weights across sessions
        session_weight = 1.0 / 3.0
    elif n_obs < 60:
        # Blended 50/50: equal + HMM
        hmm_weight = opp_weights.get(session_key, 1.0 / 3.0)
        equal_weight = 1.0 / 3.0
        session_weight = 0.5 * equal_weight + 0.5 * hmm_weight
    else:
        # Full HMM weights
        session_weight = opp_weights.get(session_key, 1.0 / 3.0)

    # Floor at 0.05
    session_weight = max(session_weight, 0.05)

    # Apply session weight as a multiplier on contracts
    # (contracts were computed without session budgeting; now scale by session share)
    import math
    for u in selected_trades:
        for ac in accounts:
            current = final_contracts.get(u, {}).get(ac, 0)
            final_contracts.setdefault(u, {})[ac] = max(1, math.floor(current * session_weight)) \
                if current > 0 else 0

    logger.info("ON-B5 HMM: Session %s weight=%.3f (n_obs=%d, cold=%s)",
                session_key, session_weight, n_obs, cold_start)

    return final_contracts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_correlation_matrix(active_assets: list[str]) -> dict:
    """Load correlation matrix from P3-D07."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT correlation_matrix FROM p3_d07_correlation_model_states
               ORDER BY last_updated DESC LIMIT 1"""
        )
        row = cur.fetchone()
    if row and row[0]:
        return _parse_json(row[0], {})
    return {}


def _get_correlation(matrix: dict, a1: str, a2: str) -> float | None:
    """Get pairwise correlation from matrix."""
    if isinstance(matrix, dict):
        pair = matrix.get(f"{a1}_{a2}") or matrix.get(f"{a2}_{a1}")
        if pair is not None:
            return float(pair) if not isinstance(pair, float) else pair
    return None


def _load_hmm_opportunity_state() -> dict | None:
    """Load HMM opportunity state from P3-D26."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT opportunity_weights, n_observations, cold_start
               FROM p3_d26_hmm_opportunity_state
               ORDER BY last_updated DESC LIMIT 1"""
        )
        row = cur.fetchone()
    if row:
        return {
            "opportunity_weights": row[0],
            "n_observations": row[1] or 0,
            "cold_start": row[2] if row[2] is not None else True,
        }
    return None


def _parse_json(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
