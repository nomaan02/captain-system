# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B9: Capacity Evaluation (Session-End) — P3-PG-29 (Task 3.10 / ON lines 1537-1645).

Runs at session end to update capacity metrics.
Tracks signal supply vs. trader demand, identifies constraints,
generates actionable recommendations for System Overview GUI.

Reads: P3-D00, P3-D07, P3-D16, P3-D17, P2-D06
Writes: P3-D17 (capacity_state)
"""

import json
import logging
from datetime import datetime

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)


def run_capacity_evaluation(
    session_id: int,
    active_users: list[dict],
    active_assets: list[str],
) -> dict:
    """P3-PG-29: Capacity evaluation at session end."""

    # Load session log data from P3-D17
    session_data = _load_session_log(session_id)

    total_recommended = sum(d.get("total_recommended", 0) for d in session_data)
    total_below_threshold = sum(d.get("total_below_threshold", 0) for d in session_data)
    total_users = len(active_users)

    # Utilization metrics
    signal_supply_ratio = total_recommended / max(total_users, 1)
    quality_pass_rate = total_recommended / max(total_recommended + total_below_threshold, 1)

    # Asset diversity
    active_asset_count = len(active_assets)
    assets_producing = _count_assets_producing_signals(session_id, session_data)
    effective_diversity = assets_producing / max(active_asset_count, 1)

    # Correlation-adjusted diversity
    corr_matrix = _load_correlation_matrix(active_assets)
    high_corr_pairs = _find_high_corr_pairs(active_assets, corr_matrix, threshold=0.7)
    effective_independent = active_asset_count - len(high_corr_pairs)

    # System params
    max_users = _load_param("max_users", 20)
    max_accounts = _load_param("max_accounts_per_user", 10)
    max_assets = _load_param("max_assets", 50)
    quality_floor = _load_param("quality_hard_floor", 0.003)

    # Build constraints list
    constraints = []

    if signal_supply_ratio < 1.0:
        constraints.append({
            "type": "SIGNAL_SHORTAGE",
            "severity": "HIGH",
            "message": f"Not enough quality signals for all users ({signal_supply_ratio:.1f} per user)",
            "recommendation": f"Test additional assets via P1/P2, or lower quality threshold (current: {quality_floor})",
        })

    if effective_independent < total_users:
        constraints.append({
            "type": "ASSET_CONCENTRATION",
            "severity": "HIGH",
            "message": f"Only {effective_independent} independent assets for {total_users} users",
            "recommendation": f"Add uncorrelated assets. High-correlation pairs: {high_corr_pairs}",
        })

    if quality_pass_rate < 0.3:
        constraints.append({
            "type": "LOW_QUALITY_RATE",
            "severity": "MEDIUM",
            "message": f"Only {quality_pass_rate * 100:.0f}% of signals pass quality gate",
            "recommendation": "Review strategy quality via P1/P2 re-run",
        })

    if total_users > max_users * 0.8:
        constraints.append({
            "type": "USER_CAPACITY",
            "severity": "HIGH",
            "message": f"At {total_users}/{max_users} user capacity",
            "recommendation": "Consider infrastructure scaling",
        })

    # Strategy homogeneity check
    strategy_models = _get_strategy_models(active_assets)
    if len(strategy_models) == 1:
        constraints.append({
            "type": "STRATEGY_HOMOGENEITY",
            "severity": "MEDIUM",
            "message": "All assets use the same (model, feature) pair — no strategy diversification",
            "recommendation": "Develop alternative strategy types via P1/P2",
        })

    # Asset class homogeneity check (P3-PG-29 lines 1647-1655)
    asset_classes = set()
    for asset_id in active_assets:
        with get_cursor() as cur:
            cur.execute(
                "SELECT locked_strategy FROM p3_d00_asset_universe "
                "LATEST ON last_updated PARTITION BY asset_id WHERE asset_id = %s",
                (asset_id,),
            )
            row = cur.fetchone()
        if row and row[0]:
            strategy = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
            asset_classes.add(strategy.get("asset_class", "EQUITY"))

    if len(asset_classes) <= 1 and len(active_assets) > 1:
        constraints.append({
            "type": "ASSET_CLASS_HOMOGENEITY",
            "severity": "MEDIUM",
            "detail": f"All {len(active_assets)} assets are in class: {asset_classes}",
            "recommendation": "Add assets from different classes (bonds, commodities, FX) for diversification",
        })

    # Save capacity state
    capacity_state = {
        "timestamp": datetime.now().isoformat(),
        "session": session_id,
        "active_users": total_users,
        "active_accounts": _count_accounts(active_users),
        "active_assets": active_asset_count,
        "assets_producing_signals": assets_producing,
        "effective_independent_assets": effective_independent,
        "signal_supply_ratio": signal_supply_ratio,
        "quality_pass_rate": quality_pass_rate,
        "total_recommended": total_recommended,
        "total_below_threshold": total_below_threshold,
        "max_users": max_users,
        "max_accounts_per_user": max_accounts,
        "max_assets": max_assets,
        "max_simultaneous_sessions": 3,
        "max_aims": 16,
        "constraints": constraints,
    }

    _save_capacity_state(session_id, capacity_state)

    logger.info("ON-B9: Capacity eval — supply ratio=%.1f, quality rate=%.0f%%, %d constraints",
                signal_supply_ratio, quality_pass_rate * 100, len(constraints))

    return capacity_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_session_log(session_id: int) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT param_value FROM p3_d17_system_monitor_state
               WHERE category = 'session_log'
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    results = []
    for r in rows:
        try:
            data = json.loads(r[0])
            if data.get("session_id") == session_id:
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def _count_assets_producing_signals(session_id: int, session_data: list[dict]) -> int:
    assets = set()
    for entry in session_data:
        quality_scores = entry.get("quality_scores", {})
        for asset_id, qs in quality_scores.items():
            if qs.get("passes_gate", False):
                assets.add(asset_id)
    return len(assets)


def _load_correlation_matrix(active_assets: list[str]) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT correlation_matrix FROM p3_d07_correlation_model_states
               ORDER BY last_updated DESC LIMIT 1"""
        )
        row = cur.fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _find_high_corr_pairs(assets: list[str], matrix: dict, threshold: float = 0.7) -> list[tuple]:
    pairs = []
    for i, a1 in enumerate(assets):
        for j, a2 in enumerate(assets):
            if i >= j:
                continue
            key = f"{a1}_{a2}"
            alt_key = f"{a2}_{a1}"
            corr = matrix.get(key) or matrix.get(alt_key)
            if corr is not None:
                try:
                    if float(corr) > threshold:
                        pairs.append((a1, a2))
                except (ValueError, TypeError):
                    pass
    return pairs


def _get_strategy_models(active_assets: list[str]) -> set:
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, locked_strategy FROM p3_d00_asset_universe
               ORDER BY last_updated DESC"""
        )
        rows = cur.fetchall()

    seen = set()
    models = set()
    for r in rows:
        if r[0] in seen or r[0] not in active_assets:
            continue
        seen.add(r[0])
        try:
            strategy = json.loads(r[1]) if isinstance(r[1], str) else (r[1] or {})
            m = strategy.get("m")
            k = strategy.get("k")
            if m is not None and k is not None:
                models.add((m, k))
        except (json.JSONDecodeError, TypeError):
            pass
    return models


def _count_accounts(active_users: list[dict]) -> int:
    total = 0
    for user in active_users:
        accounts = user.get("accounts", [])
        if isinstance(accounts, str):
            try:
                accounts = json.loads(accounts)
            except (json.JSONDecodeError, TypeError):
                accounts = []
        total += len(accounts) if isinstance(accounts, list) else 0
    return total


def _load_param(key: str, default):
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
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _save_capacity_state(session_id: int, state: dict):
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d17_system_monitor_state
               (param_key, param_value, category, last_updated)
               VALUES (%s, %s, %s, now())""",
            (f"capacity_state_{session_id}", json.dumps(state, default=str), "capacity"),
        )
