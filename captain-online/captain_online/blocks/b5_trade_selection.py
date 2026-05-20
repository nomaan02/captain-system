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
from shared.json_helpers import parse_json

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
    accounts = parse_json(user_silo.get("accounts", "[]"), [])

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

    # Q2-B-strict NKD bypass (audit 2026-05-20 §2 Q2). NKD is always selected
    # regardless of expected_edge, correlation filter, or max_simultaneous_positions.
    # Restore NKD contracts to 1 if upstream logic zeroed them, and ensure NKD is
    # in selected_trades so B5B/B5C/B6 pick it up.
    if "NKD" in active_assets:
        for ac in accounts:
            if final_contracts.get("NKD", {}).get(ac, 0) == 0:
                final_contracts.setdefault("NKD", {})[ac] = 1
                account_recommendation.setdefault("NKD", {})[ac] = "TRADE"
                account_skip_reason.setdefault("NKD", {})[ac] = None
        if "NKD" not in selected_trades:
            selected_trades.append("NKD")
        logger.info(
            "ON-B5: NKD bypass — auto-selecting NKD regardless of "
            "edge/correlation/max_pos for user=%s", user_id,
        )

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
    """OBSERVABILITY-ONLY (2026-05-06): logs the HMM session weight but does
    NOT mutate ``final_contracts``.

    PRE-2026-05-06: scaled contracts by ``session_weight = 1/3`` (cold start)
    or HMM-weighted shares, with a floor that always kept at least 1 contract
    if Kelly recommended any. This was a soft allocation layer.

    POST-2026-05-06: the per-session budget is enforced END-TO-END as a dollar
    pool (L_halt and E_daily_exposure SCOPED to the session) at three points:

        - B4 ``_compute_topstep_daily_cap`` reads per-session E (Phase 5).
        - B5C L1 reads per-session ``effective_l_halt`` (Phase 4).
        - B5C L2 reads per-session ``effective_e_exposure`` (Phase 4).

    Multiplying contracts here by 1/3 ON TOP of those caps would double-count
    the session budget — Kelly already produced a contract count that fits
    within the day-total; the per-session caps then trim further if the
    session-share is smaller. Multiplying by 1/3 again would shrink contracts
    well below what the session budget can actually support.

    This function is kept as an observability hook so log lines about the
    HMM session weight remain in production logs (useful for tuning).

    Returns ``final_contracts`` unchanged.
    """
    hmm_state = _load_hmm_opportunity_state()
    session_key = {1: "NY", 2: "LON", 3: "APAC"}.get(session_id, "NY")

    if hmm_state is None:
        logger.info(
            "ON-B5 HMM: session=%s no D26 state — equal-weight fallback "
            "(observability-only; per-session enforcement at B4/B5C)",
            session_key,
        )
        return final_contracts

    opp_weights = parse_json(hmm_state.get("opportunity_weights"), {})
    n_obs = hmm_state.get("n_observations", 0)
    cold_start = hmm_state.get("cold_start", True)

    if cold_start or n_obs < 20:
        session_weight = 1.0 / 3.0
        regime = "EQUAL_COLD_START"
    elif n_obs < 60:
        hmm_weight = opp_weights.get(session_key, 1.0 / 3.0)
        session_weight = 0.5 * (1.0 / 3.0) + 0.5 * hmm_weight
        regime = "BLENDED"
    else:
        session_weight = opp_weights.get(session_key, 1.0 / 3.0)
        regime = "HMM_FULL"
    session_weight = max(session_weight, 0.05)

    logger.info(
        "ON-B5 HMM: session=%s weight=%.3f regime=%s n_obs=%d "
        "(observability-only; budget enforcement at B4/B5C)",
        session_key, session_weight, regime, n_obs,
    )
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
        return parse_json(row[0], {})
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


