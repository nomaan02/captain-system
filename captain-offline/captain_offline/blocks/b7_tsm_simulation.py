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
import random
import logging

from shared.constants import now_et
from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS

logger = logging.getLogger(__name__)

# Simulation parameters
N_PATHS = 10_000
BLOCK_SIZES = [3, 5, 7]

_RPT07_KEY_TEMPLATE = "captain:reports:rpt07:{account_id}"
_RPT07_TTL = 86400  # 24 hours


def _simulate_one_path(
    trade_returns: list[float],
    remaining_days: int,
    starting_balance: float,
    max_drawdown_limit: float | None,
    max_daily_loss: float | None,
    profit_target: float | None,
) -> dict:
    """One MC path: outer day loop with inner block of 3-7 trades per spec PG-14.

    MDD is checked per-trade (inner loop).
    MLL is checked on daily_pnl aggregate (after inner loop).
    """
    n = len(trade_returns)
    sim_balance = starting_balance
    sim_max_balance = starting_balance
    passed = True

    for _ in range(remaining_days):
        block_size = random.choice(BLOCK_SIZES)
        start_idx = random.randint(0, max(n - block_size, 0))
        daily_returns = trade_returns[start_idx:start_idx + block_size]

        daily_pnl = 0.0
        for ret in daily_returns:
            sim_balance += ret
            daily_pnl += ret
            sim_max_balance = max(sim_max_balance, sim_balance)
            sim_drawdown = sim_max_balance - sim_balance

            if max_drawdown_limit is not None and sim_drawdown > max_drawdown_limit:
                passed = False
                break

        if not passed:
            break

        if max_daily_loss is not None and daily_pnl < 0 and abs(daily_pnl) > max_daily_loss:
            passed = False
            break

    target_reached = True
    if profit_target is not None:
        target_reached = (sim_balance - starting_balance) >= profit_target

    return {
        "passed": passed and target_reached,
        "final_balance": sim_balance,
        "max_drawdown": sim_max_balance - sim_balance,
    }


def _write_pass_probability(
    account_id: str,
    existing_row: tuple | None,
    pass_probability: float | None,
    risk_goal: str,
) -> None:
    """Persist pass_probability to P3-D08; no-op if row missing (silent when pass_probability is None)."""
    with get_cursor() as cur:
        row = existing_row
        if row is None:
            cur.execute(
                """SELECT account_id, user_id, name, classification,
                          starting_balance, current_balance, current_drawdown,
                          daily_loss_used, profit_target,
                          max_drawdown_limit, max_daily_loss, max_contracts,
                          scaling_plan, commission_per_contract,
                          instrument_permissions, overnight_allowed,
                          trading_hours, margin_per_contract, margin_buffer_pct,
                          evaluation_end_date, evaluation_stages,
                          topstep_optimisation, topstep_params, topstep_state,
                          fee_schedule, payout_rules, scaling_plan_active,
                          scaling_tier_micros
                   FROM p3_d08_tsm_state
                   WHERE account_id = %s
                   ORDER BY last_updated DESC LIMIT 1""",
                (account_id,),
            )
            row = cur.fetchone()
        if row is None:
            if pass_probability is not None:
                logger.warning(
                    "No D08 row for %s — skipping simulation persist until TSM config is loaded",
                    account_id,
                )
            return
        p = list(row)
        cur.execute(
            """INSERT INTO p3_d08_tsm_state(
                   account_id, user_id, name, classification,
                   starting_balance, current_balance, current_drawdown,
                   daily_loss_used, profit_target,
                   max_drawdown_limit, max_daily_loss, max_contracts,
                   scaling_plan, commission_per_contract,
                   instrument_permissions, overnight_allowed,
                   trading_hours, margin_per_contract, margin_buffer_pct,
                   pass_probability, simulation_date, risk_goal,
                   evaluation_end_date, evaluation_stages,
                   topstep_optimisation, topstep_params, topstep_state,
                   fee_schedule, payout_rules, scaling_plan_active,
                   scaling_tier_micros, last_updated
               ) VALUES(
                   %s, %s, %s, %s,
                   %s, %s, %s,
                   %s, %s,
                   %s, %s, %s,
                   %s, %s,
                   %s, %s,
                   %s, %s, %s,
                   %s, now(), %s,
                   %s, %s,
                   %s, %s, %s,
                   %s, %s, %s,
                   %s, now()
               )""",
            (
                p[0], p[1], p[2], p[3],
                p[4], p[5], p[6],
                p[7], p[8],
                p[9], p[10], p[11],
                p[12], p[13],
                p[14], p[15],
                p[16], p[17], p[18],
                pass_probability, risk_goal,
                p[19], p[20],
                p[21], p[22], p[23],
                p[24], p[25], p[26],
                p[27],
            ),
        )


def _generate_rpt07(
    account_id: str,
    pass_probability: float | None,
    ruin_probability: float | None,
    risk_goal: str,
    remaining_days: int,
    n_paths: int,
    alert: dict | None,
):
    """PG-14 GENERATE RPT-07: store MC summary to Redis for Command renderer.

    Key: captain:reports:rpt07:{account_id}
    TTL: 24 hours (refreshed on each simulation run)
    """
    try:
        client = get_redis_client()
        report = {
            "account_id": account_id,
            "pass_probability": pass_probability,
            "ruin_probability": ruin_probability,
            "risk_goal": risk_goal,
            "remaining_days": remaining_days,
            "n_paths": n_paths,
            "alert_priority": alert["priority"] if alert else None,
            "generated_at": now_et().isoformat(),
        }
        key = _RPT07_KEY_TEMPLATE.format(account_id=account_id)
        client.setex(key, _RPT07_TTL, json.dumps(report))
    except Exception as e:
        logger.error("RPT-07 generation failed for %s: %s", account_id, e)


def run_tsm_simulation(
    account_id: str,
    trade_returns: list[float],
    tsm_config: dict,
    sizing_override: float = 1.0,
) -> dict:
    """Execute P3-PG-14: Monte Carlo TSM simulation.

    Args:
        account_id: Account to simulate
        trade_returns: Historical per-trade returns (P3-D03)
        tsm_config: TSM configuration from P3-D08 with keys:
            starting_balance, current_balance, max_drawdown_limit,
            max_daily_loss, profit_target, evaluation_end_date, risk_goal
        sizing_override: Q-31 decay sizing factor in [0, 1] applied to returns before MC

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

    # Spec PG-14: accounts with no constraints get NULL pass_probability
    if mdd_limit is None and mll_limit is None:
        _write_pass_probability(account_id, None, None, risk_goal)
        _generate_rpt07(account_id, None, None, risk_goal, remaining_days, 0, None)
        logger.info("TSM simulation %s: unconstrained account — pass_probability=None", account_id)
        return {
            "account_id": account_id,
            "pass_probability": None,
            "ruin_probability": None,
            "n_paths": 0,
            "remaining_days": remaining_days,
            "risk_goal": risk_goal,
            "alert": None,
        }

    # Q-31: scale historical returns to reflect current decay-adjusted sizing
    if sizing_override != 1.0:
        trade_returns = [r * sizing_override for r in trade_returns]

    # Run Monte Carlo
    pass_count = 0
    results = []

    for _ in range(N_PATHS):
        sim = _simulate_one_path(
            trade_returns, remaining_days, current_balance,
            mdd_limit, mll_limit, remaining_target,
        )
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

    _write_pass_probability(account_id, None, pass_probability, risk_goal)

    # PG-14: GENERATE RPT-07(P3-D08)
    _generate_rpt07(account_id, pass_probability, ruin_probability,
                    risk_goal, remaining_days, N_PATHS, alert)

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
                "timestamp": now_et().isoformat(),
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
