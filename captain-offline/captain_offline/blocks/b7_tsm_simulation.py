# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""TSM Monte Carlo Simulation — P3-PG-14 (Task 2.7 / OFF lines 622-631).

Estimates pass_probability for prop firm evaluations via block bootstrap
Monte Carlo simulation (10,000 paths).

Block bootstrap: random block sizes {3, 5, 7}, preserves autocorrelation.
Constraints: MDD breach, MLL breach.
Pass condition: survive constraints AND reach profit target.

Risk goal alerts:
  PASS_EVAL:        pass_prob < 0.3 -> CRITICAL, < 0.5 -> HIGH
  GROW_CAPITAL:     ruin_prob > 0.3 -> HIGH
  PRESERVE_CAPITAL: pass_prob < 0.7 -> HIGH

Reads: P3-D03 (trade outcomes), P3-D08 (TSM config), P3-D12 (Kelly)
Writes: P3-D08 (pass_probability, simulation_date)
"""

import json
import math
import random
import logging
from datetime import datetime

import numpy as np

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS

logger = logging.getLogger(__name__)

# Simulation parameters
N_PATHS = 10_000
BLOCK_SIZES = [3, 5, 7]


def _block_bootstrap_path(trade_returns: list[float], n_days: int) -> list[float]:
    """Generate one bootstrap path using block bootstrap.

    Preserves autocorrelation by sampling contiguous blocks.
    """
    path = []
    n = len(trade_returns)
    while len(path) < n_days:
        block_size = random.choice(BLOCK_SIZES)
        start = random.randint(0, max(n - block_size, 0))
        block = trade_returns[start:start + block_size]
        path.extend(block)
    return path[:n_days]


def _simulate_path(path_returns: list[float], starting_balance: float,
                    max_drawdown_limit: float | None,
                    max_daily_loss: float | None,
                    profit_target: float | None) -> dict:
    """Simulate one MC path and check constraints.

    Returns dict with passed, final_balance, max_drawdown.
    """
    balance = starting_balance
    peak = balance
    max_dd = 0.0
    passed = True

    for daily_pnl in path_returns:
        balance += daily_pnl
        peak = max(peak, balance)
        drawdown = peak - balance
        max_dd = max(max_dd, drawdown)

        # MDD breach
        if max_drawdown_limit is not None and drawdown > max_drawdown_limit:
            passed = False
            break

        # MLL breach (simplified: treat each return as a daily P&L)
        if max_daily_loss is not None and daily_pnl < 0 and abs(daily_pnl) > max_daily_loss:
            passed = False
            break

    # Target achievement
    target_reached = True
    if profit_target is not None:
        target_reached = (balance - starting_balance) >= profit_target

    return {
        "passed": passed and target_reached,
        "final_balance": balance,
        "max_drawdown": max_dd,
    }


def run_tsm_simulation(account_id: str, trade_returns: list[float],
                        tsm_config: dict) -> dict:
    """Execute P3-PG-14: Monte Carlo TSM simulation.

    Args:
        account_id: Account to simulate
        trade_returns: Historical per-trade returns (P3-D03)
        tsm_config: TSM configuration from P3-D08 with keys:
            starting_balance, current_balance, max_drawdown_limit,
            max_daily_loss, profit_target, evaluation_end_date, risk_goal

    Returns:
        Dict with pass_probability, alert info
    """
    if len(trade_returns) < 10:
        logger.warning("TSM simulation %s: insufficient trades (%d < 10)", account_id, len(trade_returns))
        return {"pass_probability": None, "alert": None}

    # No fixed seed — MC simulation must produce different paths each run

    starting_balance = tsm_config.get("starting_balance", 150000)
    current_balance = tsm_config.get("current_balance", starting_balance)
    mdd_limit = tsm_config.get("max_drawdown_limit")
    mll_limit = tsm_config.get("max_daily_loss")
    profit_target = tsm_config.get("profit_target")
    risk_goal = tsm_config.get("risk_goal", "PASS_EVAL")

    # Remaining days (default 60 if no deadline)
    eval_end = tsm_config.get("evaluation_end_date")
    if eval_end:
        from datetime import date
        if isinstance(eval_end, str):
            eval_end = date.fromisoformat(eval_end)
        remaining_days = max((eval_end - date.today()).days, 1)
    else:
        remaining_days = 60

    # Adjust target for current progress
    if profit_target is not None:
        remaining_target = profit_target - (current_balance - starting_balance)
    else:
        remaining_target = None

    # Run Monte Carlo
    pass_count = 0
    results = []

    for _ in range(N_PATHS):
        path = _block_bootstrap_path(trade_returns, remaining_days)
        sim = _simulate_path(path, current_balance, mdd_limit, mll_limit, remaining_target)
        results.append(sim)
        if sim["passed"]:
            pass_count += 1

    pass_probability = pass_count / N_PATHS
    ruin_probability = 1.0 - pass_probability

    # Determine alert
    alert = None
    if risk_goal == "PASS_EVAL":
        if pass_probability < 0.3:
            alert = {"priority": "CRITICAL", "message": f"Pass probability critically low: {pass_probability:.1%}"}
        elif pass_probability < 0.5:
            alert = {"priority": "HIGH", "message": f"Pass probability elevated risk: {pass_probability:.1%}"}
    elif risk_goal == "GROW_CAPITAL":
        if ruin_probability > 0.3:
            alert = {"priority": "HIGH", "message": f"Drawdown risk elevated: ruin probability {ruin_probability:.1%}"}
    elif risk_goal == "PRESERVE_CAPITAL":
        if pass_probability < 0.7:
            alert = {"priority": "HIGH", "message": f"Non-trivial capital risk: {pass_probability:.1%} survival"}

    # Store to P3-D08
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d08_tsm_state
               (account_id, pass_probability, simulation_date, risk_goal, last_updated)
               VALUES (%s, %s, now(), %s, now())""",
            (account_id, pass_probability, risk_goal),
        )

    # Publish alert if needed
    if alert:
        try:
            client = get_redis_client()
            client.publish(CH_ALERTS, json.dumps({
                "type": "TSM_ALERT",
                "account_id": account_id,
                "priority": alert["priority"],
                "message": alert["message"],
                "pass_probability": pass_probability,
                "timestamp": datetime.now().isoformat(),
            }))
        except Exception as e:
            logger.error("Failed to publish TSM alert: %s", e)

    logger.info("TSM simulation %s: pass_prob=%.3f, ruin_prob=%.3f, "
                "risk_goal=%s, alert=%s",
                account_id, pass_probability, ruin_probability,
                risk_goal, alert["priority"] if alert else "none")

    return {
        "account_id": account_id,
        "pass_probability": pass_probability,
        "ruin_probability": ruin_probability,
        "n_paths": N_PATHS,
        "remaining_days": remaining_days,
        "risk_goal": risk_goal,
        "alert": alert,
    }
