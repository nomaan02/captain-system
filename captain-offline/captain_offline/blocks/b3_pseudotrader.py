# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Pseudotrader Counterfactual Replay — P3-PG-09 + V3 CB Extension (Tasks 2.3, 2.3b).

P3-PG-09: Replays historical trades with CURRENT vs PROPOSED parameters.
  Computes: sharpe_improvement, drawdown_change, winrate_delta, PBO, DSR.
  ADOPT if sharpe > 0 AND pbo < 0.5 AND dsr > 0.5, else REJECT.

P3-PG-09B (V3): Circuit breaker pseudotrader at intraday resolution.
  Replays with/without CB, tracks blocked trades, per-layer breakdown.

P3-PG-09C (V3): Grid search over CB parameters (c, lambda).

Reads: P3-D03 (trade outcomes), P3-D25 (CB params)
Writes: P3-D11 (pseudotrader results)
"""

import json
import math
import logging
import uuid
from collections import defaultdict

import numpy as np

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# Anti-overfitting thresholds
PBO_THRESHOLD = 0.5
DSR_THRESHOLD = 0.5
CSCV_SPLITS = 16


def _compute_sharpe(returns: list[float]) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    mean = arr.mean()
    std = arr.std()
    if std < 1e-10:
        return 0.0
    return float(mean / std * math.sqrt(252))


def _compute_max_drawdown(equity_curve: list[float]) -> float:
    """Maximum drawdown from equity curve."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return float(max_dd)


def _compute_win_rate(pnl_list: list[float]) -> float:
    """Win rate from list of P&L values."""
    if not pnl_list:
        return 0.0
    wins = sum(1 for p in pnl_list if p > 0)
    return wins / len(pnl_list)


def _compute_pbo(returns: list[float], S: int = CSCV_SPLITS) -> float:
    """PBO via full CSCV (Paper 152). Delegates to shared.statistics."""
    from shared.statistics import compute_pbo
    return compute_pbo(returns, S)


def _compute_dsr(sharpe: float, n_trials: int, skew: float,
                  kurtosis: float, T: int) -> float:
    """DSR (Paper 150). Delegates to shared.statistics."""
    from shared.statistics import compute_dsr
    return compute_dsr(sharpe, n_trials, skew, kurtosis, T)


# ---------------------------------------------------------------------------
# Account-type constraint helpers (C1 gap resolution)
# ---------------------------------------------------------------------------

def _enforce_trading_hours(trade_ts: str, trading_hours: dict) -> str | None:
    """Check if a trade timestamp falls within allowed trading hours.

    Args:
        trade_ts: ISO timestamp string of the trade
        trading_hours: Dict with session_open, flat_by, eod_exit_buffer

    Returns:
        None if trade is allowed, otherwise a reason string.
    """
    if not trading_hours or not isinstance(trading_hours, dict):
        return None  # no trading hours constraint

    from datetime import datetime as _dt
    try:
        ts = _dt.fromisoformat(trade_ts) if isinstance(trade_ts, str) else trade_ts
    except (ValueError, TypeError):
        return None  # can't parse, allow

    hour, minute = ts.hour, ts.minute
    ts_minutes = hour * 60 + minute

    # eod_exit_buffer: no new entries after this time (e.g. 15:55 EST = 955 min)
    eod_buffer = trading_hours.get("eod_exit_buffer", "")
    if eod_buffer and ":" in str(eod_buffer):
        parts = str(eod_buffer).replace(" EST", "").split(":")
        buf_minutes = int(parts[0]) * 60 + int(parts[1])
        if buf_minutes < 18 * 60:  # before 18:00 means next-day portion
            if ts_minutes >= buf_minutes and ts_minutes < 16 * 60 + 10:
                return "AFTER_EOD_BUFFER"

    # flat_by: hard close (e.g. 16:10 EST = 970 min)
    flat_by = trading_hours.get("flat_by", "")
    if flat_by and ":" in str(flat_by):
        parts = str(flat_by).replace(" EST", "").split(":")
        flat_minutes = int(parts[0]) * 60 + int(parts[1])
        if flat_minutes < 18 * 60:  # next-day portion
            if ts_minutes >= flat_minutes and ts_minutes < 18 * 60:
                return "AFTER_FLAT_BY"

    return None


def _lookup_scaling_tier(balance: float, starting_balance: float,
                         scaling_plan: list[dict]) -> int:
    """Look up max contracts (micros) for current balance under XFA scaling.

    Args:
        balance: Current account balance
        starting_balance: Account starting balance
        scaling_plan: List of tier dicts with balance_threshold and max_micros

    Returns:
        Maximum micros allowed under current tier.
    """
    if not scaling_plan:
        return 999  # no scaling constraint

    sorted_plan = sorted(scaling_plan,
                         key=lambda t: t.get("balance_threshold", 0))
    max_micros = sorted_plan[0].get("max_micros", 30)  # default first tier

    for tier in sorted_plan:
        if balance >= tier.get("balance_threshold", 0):
            max_micros = tier.get("max_micros", max_micros)

    return max_micros


def _check_dll(daily_pnl: float, max_daily_loss: float | None) -> bool:
    """Check if daily loss limit is breached.

    Returns True if breached (trading should stop).
    """
    if max_daily_loss is None or max_daily_loss <= 0:
        return False
    return daily_pnl <= -max_daily_loss


def run_account_aware_replay(asset_id: str, update_type: str,
                              trades: list[dict],
                              account_config: dict | None = None) -> dict:
    """Execute P3-PG-09 with account-type constraint enforcement.

    Replays trade-level data while enforcing DLL, MDD, contract scaling,
    trading hours, and consistency rules per the account's TSM config.
    When account_config is None, replays with only a basic $4,500 MDD check.

    Spec: Pseudotrader_Account_Awareness_Amendment.md sections 1-4.

    Args:
        asset_id: Asset being evaluated
        update_type: "AIM_WEIGHT_CHANGE" | "MODEL_RETRAIN" | "STRATEGY_INJECTION"
        trades: List of trade dicts with keys: day, pnl, contracts, ts, model
        account_config: TSM config dict (or None for legacy behavior)

    Returns:
        Replay result dict with metrics and constraint breach counts.
    """
    # Extract constraints from account_config
    if account_config:
        mdd_limit = account_config.get("max_drawdown_limit", 4500)
        max_daily_loss = account_config.get("max_daily_loss")
        trading_hours = account_config.get("trading_hours")
        scaling_plan = account_config.get("scaling_plan")
        scaling_active = account_config.get("scaling_plan_active", False)
        consistency_rule = account_config.get("consistency_rule")
        starting_balance = account_config.get("starting_balance", 150000)
        max_contracts_micros = account_config.get("max_contracts", 15) * 10
        # Live accounts: no trailing MLL, use daily drawdown instead
        max_daily_drawdown = account_config.get("max_daily_drawdown")
        low_balance_threshold = account_config.get("low_balance_threshold", 10000)
        low_balance_daily_dd = account_config.get("low_balance_daily_drawdown", 2000)
        # Capital unlock (Live only): profit-target based reserve release
        capital_unlock = account_config.get("capital_unlock")
    else:
        mdd_limit = 4500
        max_daily_loss = None
        trading_hours = None
        scaling_plan = None
        scaling_active = False
        consistency_rule = None
        starting_balance = 150000
        max_contracts_micros = 150
        max_daily_drawdown = None
        low_balance_threshold = 10000
        low_balance_daily_dd = 2000
        capital_unlock = None

    # Capital unlock state (Live accounts)
    if capital_unlock:
        tradable_cap = capital_unlock.get("tradable_cap", 30000)
        unlock_levels = capital_unlock.get("unlock_levels", 4)
        unlock_profit = capital_unlock.get("unlock_profit", 9000)
        tradable_balance = min(starting_balance, tradable_cap)
        reserve_balance = max(starting_balance - tradable_cap, 0.0)
        reserve_per_block = (reserve_balance / unlock_levels
                             if reserve_balance > 0 else 0.0)
        unlocks_remaining = unlock_levels if reserve_balance > 0 else 0
        cumulative_live_profit = 0.0
        capital_unlock_events = 0
    else:
        tradable_balance = 0.0
        reserve_balance = 0.0
        reserve_per_block = 0.0
        unlocks_remaining = 0
        cumulative_live_profit = 0.0
        capital_unlock_events = 0

    # Group trades by day
    by_day = defaultdict(list)
    for t in trades:
        by_day[t.get("day", "unknown")].append(t)

    running_balance = starting_balance
    max_balance = starting_balance
    daily_pnl_list = []
    breach_counts = {
        "dll_breaches": 0,
        "daily_dd_breaches": 0,
        "mdd_breach": False,
        "mdd_breach_day": None,
        "scaling_cap_hits": 0,
        "trading_hours_blocks": 0,
        "consistency_violations": 0,
        "capital_unlock_events": 0,
        "total_trades_taken": 0,
        "total_trades_blocked": 0,
    }

    mdd_breached = False

    for day in sorted(by_day.keys()):
        if mdd_breached:
            daily_pnl_list.append(0.0)
            continue

        day_trades = sorted(by_day[day], key=lambda t: t.get("ts", ""))
        daily_pnl = 0.0
        daily_profit = 0.0
        dll_hit = False

        for trade in day_trades:
            # Check MDD (skip for Live accounts with no trailing MLL)
            if mdd_limit is not None:
                current_mdd = max_balance - running_balance
                if current_mdd >= mdd_limit:
                    mdd_breached = True
                    breach_counts["mdd_breach"] = True
                    breach_counts["mdd_breach_day"] = day
                    breach_counts["total_trades_blocked"] += 1
                    break

            # Check DLL
            if _check_dll(daily_pnl, max_daily_loss):
                if not dll_hit:
                    breach_counts["dll_breaches"] += 1
                    dll_hit = True
                breach_counts["total_trades_blocked"] += 1
                continue

            # Check daily drawdown (Live accounts)
            if max_daily_drawdown is not None:
                effective_dd = (low_balance_daily_dd
                                if running_balance <= low_balance_threshold
                                else max_daily_drawdown)
                if daily_pnl <= -effective_dd:
                    if not dll_hit:
                        breach_counts["daily_dd_breaches"] = breach_counts.get("daily_dd_breaches", 0) + 1
                        dll_hit = True  # reuse flag to halt remaining trades
                    breach_counts["total_trades_blocked"] += 1
                    continue

            # Check trading hours
            hours_block = _enforce_trading_hours(
                trade.get("ts", ""), trading_hours)
            if hours_block:
                breach_counts["trading_hours_blocks"] += 1
                breach_counts["total_trades_blocked"] += 1
                continue

            # Check scaling (XFA only)
            if scaling_active and scaling_plan:
                tier_micros = _lookup_scaling_tier(
                    running_balance, starting_balance, scaling_plan)
                trade_micros = trade.get("contracts", 1) * 10
                if trade_micros > tier_micros:
                    breach_counts["scaling_cap_hits"] += 1
                    # Scale down to tier limit instead of blocking
                    scale_factor = tier_micros / trade_micros
                    trade_pnl = trade["pnl"] * scale_factor
                else:
                    trade_pnl = trade["pnl"]
            else:
                trade_pnl = trade["pnl"]

            # Trade taken
            daily_pnl += trade_pnl
            running_balance += trade_pnl
            max_balance = max(max_balance, running_balance)
            breach_counts["total_trades_taken"] += 1

            # Post-trade MDD check (skip for Live accounts with no trailing MLL)
            if mdd_limit is not None:
                post_mdd = max_balance - running_balance
                if post_mdd >= mdd_limit:
                    mdd_breached = True
                    breach_counts["mdd_breach"] = True
                    if breach_counts["mdd_breach_day"] is None:
                        breach_counts["mdd_breach_day"] = day
                    break

            # Track daily profit for consistency check
            if trade_pnl > 0:
                daily_profit += trade_pnl

        daily_pnl_list.append(daily_pnl)

        # Consistency check (end of day)
        if consistency_rule and isinstance(consistency_rule, dict):
            max_daily_profit = consistency_rule.get("max_daily_profit")
            if max_daily_profit and daily_profit > max_daily_profit:
                breach_counts["consistency_violations"] += 1

        # Capital unlock check (Live only — profit-target based)
        if capital_unlock and unlocks_remaining > 0 and reserve_per_block > 0:
            cumulative_live_profit = running_balance - starting_balance
            unlocks_earned = int(max(cumulative_live_profit, 0) // unlock_profit)
            unlocks_already = unlock_levels - unlocks_remaining
            new_unlocks = max(unlocks_earned - unlocks_already, 0)
            if new_unlocks > 0:
                actual_unlocks = min(new_unlocks, unlocks_remaining)
                unlock_amount = actual_unlocks * reserve_per_block
                tradable_balance += unlock_amount
                reserve_balance -= unlock_amount
                unlocks_remaining -= actual_unlocks
                capital_unlock_events += actual_unlocks
                breach_counts["capital_unlock_events"] += actual_unlocks

    # Compute metrics
    sharpe = _compute_sharpe(daily_pnl_list)
    eq_curve = list(np.cumsum(daily_pnl_list))
    max_dd = _compute_max_drawdown(eq_curve) if eq_curve else 0.0
    all_trades_pnl = [t["pnl"] for t in trades]
    win_rate = _compute_win_rate(all_trades_pnl)
    pbo = _compute_pbo(daily_pnl_list)
    net_pnl = sum(daily_pnl_list)

    # Eval pass/fail check (PROP_EVAL only)
    eval_result = None
    if account_config:
        classification = account_config.get("classification", {})
        if classification.get("category") == "PROP_EVAL":
            profit_target = account_config.get("profit_target", 0)
            if running_balance >= starting_balance + profit_target:
                eval_result = "PASS"
            elif mdd_breached:
                eval_result = "FAIL_MDD"
            else:
                eval_result = "IN_PROGRESS"

    result = {
        "asset_id": asset_id,
        "update_type": update_type,
        "account_type": (account_config or {}).get("classification", {}).get("category", "UNKNOWN"),
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "pbo": pbo,
        "net_pnl": net_pnl,
        "final_balance": running_balance,
        "trading_days": len(daily_pnl_list),
        "eval_result": eval_result,
        # Capital unlock state (Live only)
        "tradable_balance": tradable_balance,
        "reserve_balance": reserve_balance,
        "unlocks_remaining": unlocks_remaining,
        **breach_counts,
    }

    # Store in P3-D11
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d11_pseudotrader_results
                   (result_id, update_type, sharpe_improvement, drawdown_change,
                    winrate_delta, pbo, dsr, recommendation, ts)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (
                    f"AAR-{asset_id}-{update_type[:3]}",
                    update_type, sharpe, -max_dd,
                    win_rate, pbo, 0.0,
                    "ACCOUNT_AWARE_REPLAY",
                ),
            )
    except Exception as exc:
        logger.warning("Failed to store account-aware replay result: %s", exc)

    logger.info("Account-aware replay %s [%s]: sharpe=%.4f, net_pnl=%.2f, "
                "dll=%d, scaling=%d, hours=%d, consistency=%d, "
                "capital_unlocks=%d, mdd_breach=%s",
                asset_id, update_type, sharpe, net_pnl,
                breach_counts["dll_breaches"], breach_counts["scaling_cap_hits"],
                breach_counts["trading_hours_blocks"],
                breach_counts["consistency_violations"],
                breach_counts["capital_unlock_events"],
                breach_counts["mdd_breach"])

    return result


# ---------------------------------------------------------------------------
# D03 data source + full pipeline replay (G-OFF-016, G-OFF-024)
# ---------------------------------------------------------------------------

def fetch_d03_trade_outcomes(user_id: str, asset_id: str,
                              limit: int = 60) -> list[dict]:
    """Fetch historical trade outcomes from P3-D03 (trade_outcome_log).

    Spec: Doc 32 PG-09 — actual_trade_outcome(d) data source.

    Args:
        user_id: User identifier (e.g. "primary_user")
        asset_id: Asset symbol (e.g. "ES")
        limit: Maximum rows to return

    Returns:
        List of trade outcome dicts ordered by timestamp descending.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT trade_id, user_id, account_id, asset, direction,
                      entry_price, exit_price, contracts, pnl, slippage,
                      outcome, entry_time, exit_time, regime_at_entry,
                      aim_modifier_at_entry, session, ts
               FROM p3_d03_trade_outcome_log
               WHERE user_id = %s AND asset = %s
               ORDER BY ts DESC
               LIMIT %s""",
            (user_id, asset_id, limit),
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def captain_online_replay(target_date, asset_id: str,
                           params: dict | None = None,
                           cached_bars: dict | None = None,
                           baseline_result: dict | None = None) -> dict:
    """Replay B1-B6 online pipeline for a single day with optional param overrides.

    Spec: Doc 32 PG-09 §1-2 — captain_online_replay(d, using=params).
    Uses shared/replay_engine for full pipeline replay. When cached_bars
    and baseline_result are provided, uses run_whatif() for zero API calls.

    Args:
        target_date: date object for the day to replay
        asset_id: Asset to extract results for
        params: Optional config overrides for load_replay_config()
        cached_bars: Pre-fetched bars from a prior run_replay() call
        baseline_result: Full result dict from a prior run_replay() call

    Returns:
        Dict with signal details and theoretical P&L for the target asset,
        plus cached_bars and _full_result for efficient whatif chaining.
    """
    from shared.replay_engine import load_replay_config, run_replay, run_whatif

    config = load_replay_config(overrides=params)

    if cached_bars is not None and baseline_result is not None:
        full = run_whatif(config, cached_bars, baseline_result,
                          target_date=target_date)
        results_list = full.get("whatif_results", [])
    else:
        full = run_replay(config, target_date=target_date)
        results_list = full.get("results", [])

    for r in results_list:
        if r.get("asset") == asset_id:
            return {
                "asset": asset_id,
                "date": str(target_date),
                "direction": r.get("direction", 0),
                "contracts": r.get("contracts", 0),
                "pnl": r.get("total_pnl", 0.0),
                "pnl_per_contract": r.get("pnl_per_contract", 0.0),
                "exit_reason": r.get("exit_reason", ""),
                "aim_modifier": r.get("aim_modifier"),
                "quality_score": r.get("quality_score"),
                "sizing": r.get("sizing"),
                "cached_bars": full.get("cached_bars"),
                "_full_result": full,
            }

    return {
        "asset": asset_id,
        "date": str(target_date),
        "direction": 0,
        "contracts": 0,
        "pnl": 0.0,
        "exit_reason": "NO_BREAKOUT",
        "cached_bars": full.get("cached_bars"),
        "_full_result": full,
    }


def run_pseudotrader(asset_id: str, update_type: str,
                      baseline_pnl: list[float] | None = None,
                      proposed_pnl: list[float] | None = None,
                      *,
                      current_params: dict | None = None,
                      proposed_params: dict | None = None,
                      user_id: str = "primary_user",
                      lookback_days: int = 30) -> dict:
    """Execute P3-PG-09: counterfactual replay comparison.

    PRIMARY PATH (spec Doc 32 PG-09 §1-2): When baseline_pnl/proposed_pnl
    are not provided, replays B1-B6 via captain_online_replay() for each
    day in the historical window from D03, then compares outcomes.

    FAST FALLBACK: When baseline_pnl/proposed_pnl are provided directly,
    skips replay and computes comparison metrics from pre-computed P&L.

    Args:
        asset_id: Asset being evaluated
        update_type: "AIM_WEIGHT_CHANGE" | "MODEL_RETRAIN" | "STRATEGY_INJECTION"
        baseline_pnl: [FALLBACK] Daily P&L under current parameters
        proposed_pnl: [FALLBACK] Daily P&L under proposed parameters
        current_params: [PRIMARY] Config overrides for baseline replay
        proposed_params: [PRIMARY] Config overrides for proposed replay
        user_id: User ID for D03 queries (default: "primary_user")
        lookback_days: Number of trading days to replay (default: 30)

    Returns:
        Comparison dict with recommendation
    """
    # ── PRIMARY PATH: Full B1-B6 pipeline replay (G-OFF-016) ─────────
    if baseline_pnl is None and proposed_pnl is None:
        from datetime import date as _date_cls

        d03_outcomes = fetch_d03_trade_outcomes(user_id, asset_id, lookback_days)

        if not d03_outcomes:
            logger.warning("No D03 outcomes for %s/%s; cannot run replay path",
                          asset_id, user_id)
            return {
                "update_type": update_type,
                "sharpe_improvement": 0.0,
                "drawdown_change": 0.0,
                "winrate_delta": 0.0,
                "pbo": 1.0,
                "dsr": 0.0,
                "recommendation": "REJECT",
                "reason": "NO_HISTORICAL_DATA",
            }

        # Determine unique trading days from D03 timestamps
        trading_days = sorted({
            outcome["ts"].date() if hasattr(outcome["ts"], "date")
            else _date_cls.fromisoformat(str(outcome["ts"])[:10])
            for outcome in d03_outcomes
        })

        logger.info("Pseudotrader replay %s [%s]: %d trading days from D03",
                    asset_id, update_type, len(trading_days))

        # Phase 1: Baseline replay (CURRENT parameters) — fetches bars
        baseline_pnl = []
        cached_bars_by_day = {}
        baseline_results_by_day = {}

        for day in trading_days:
            result = captain_online_replay(day, asset_id, params=current_params)
            baseline_pnl.append(result["pnl"])
            cached_bars_by_day[str(day)] = result.get("cached_bars")
            baseline_results_by_day[str(day)] = result.get("_full_result")

        # Phase 2: Proposed replay (reuses cached bars — zero API calls)
        proposed_pnl = []
        for day in trading_days:
            day_key = str(day)
            result = captain_online_replay(
                day, asset_id,
                params=proposed_params,
                cached_bars=cached_bars_by_day.get(day_key),
                baseline_result=baseline_results_by_day.get(day_key),
            )
            proposed_pnl.append(result["pnl"])

        logger.info("Replay complete %s: baseline_total=%.2f, proposed_total=%.2f",
                    asset_id, sum(baseline_pnl), sum(proposed_pnl))
    else:
        # ── FAST FALLBACK: Pre-computed P&L (not the default path) ───
        logger.debug("Pseudotrader %s: using pre-computed P&L fallback", asset_id)

    # ── Phase 3-5: Comparison metrics (shared by both paths) ─────────
    sharpe_base = _compute_sharpe(baseline_pnl)
    sharpe_prop = _compute_sharpe(proposed_pnl)
    sharpe_improvement = sharpe_prop - sharpe_base

    eq_base = list(np.cumsum(baseline_pnl))
    eq_prop = list(np.cumsum(proposed_pnl))
    dd_base = _compute_max_drawdown(eq_base)
    dd_prop = _compute_max_drawdown(eq_prop)
    drawdown_change = dd_prop - dd_base

    wr_base = _compute_win_rate(baseline_pnl)
    wr_prop = _compute_win_rate(proposed_pnl)
    winrate_delta = wr_prop - wr_base

    # Anti-overfitting
    pbo = _compute_pbo(proposed_pnl)
    arr = np.array(proposed_pnl)
    skew = float(np.mean((arr - arr.mean()) ** 3) / max(arr.std() ** 3, 1e-10)) if len(arr) > 2 else 0.0
    kurt = float(np.mean((arr - arr.mean()) ** 4) / max(arr.std() ** 4, 1e-10)) if len(arr) > 2 else 3.0
    dsr = _compute_dsr(sharpe_prop, 1, skew, kurt, len(proposed_pnl))

    # Decision
    if sharpe_improvement > 0 and pbo < PBO_THRESHOLD and dsr > DSR_THRESHOLD:
        recommendation = "ADOPT"
    else:
        recommendation = "REJECT"

    result = {
        "update_type": update_type,
        "sharpe_improvement": sharpe_improvement,
        "drawdown_change": drawdown_change,
        "winrate_delta": winrate_delta,
        "pbo": pbo,
        "dsr": dsr,
        "recommendation": recommendation,
    }

    # Store in P3-D11
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d11_pseudotrader_results
               (result_id, update_type, sharpe_improvement, drawdown_change,
                winrate_delta, pbo, dsr, recommendation, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (
                f"PT-{asset_id}-{update_type[:3]}",
                update_type, sharpe_improvement, drawdown_change,
                winrate_delta, pbo, dsr, recommendation,
            ),
        )

    logger.info("Pseudotrader %s [%s]: sharpe_delta=%.4f, dd_delta=%.4f, "
                "pbo=%.3f, dsr=%.3f -> %s",
                asset_id, update_type, sharpe_improvement, drawdown_change,
                pbo, dsr, recommendation)

    return result


def run_signal_replay_comparison(asset_id: str, proposed_update: dict) -> dict:
    """P3-PG-09 with full signal replay instead of pre-computed P&L.

    Loads replay context, runs baseline and proposed replays via
    SignalReplayEngine, extracts daily P&L, then delegates to
    run_pseudotrader() for the counterfactual comparison.

    Args:
        asset_id: Asset to evaluate
        proposed_update: Dict with keys:
            update_type: "AIM_WEIGHT_CHANGE" | "KELLY_UPDATE" | "STRATEGY_PARAM_CHANGE"
            For AIM/Kelly changes (sizing replay):
                proposed_aim_weights: {aim_id: inclusion_probability}
                proposed_kelly_params: {"LOW_VOL": {"kelly_full": f}, "HIGH_VOL": {...}}
            For strategy changes (strategy replay):
                proposed_strategy_params: {"sl_multiplier": x, "tp_multiplier": y, ...}

    Returns:
        Comparison dict from run_pseudotrader() with recommendation.
    """
    from shared.signal_replay import SignalReplayEngine

    update_type = proposed_update.get("update_type", "AIM_WEIGHT_CHANGE")

    # Load replay context (trades, regime labels, locked strategy, defaults)
    ctx = SignalReplayEngine.load_replay_context(asset_id)
    trades = ctx["trades"]
    regime_labels = ctx["regime_labels"]
    locked_strategy = ctx["locked_strategy"]
    kelly_params = ctx["kelly_params"]
    aim_weights = ctx["aim_weights"]

    engine = SignalReplayEngine(asset=asset_id)

    if update_type in ("AIM_WEIGHT_CHANGE", "KELLY_UPDATE"):
        # ------- Sizing replay: same trades, different AIM/Kelly -------
        # Baseline: current parameters
        baseline_trades = engine.sizing_replay(
            trades=trades,
            regime_labels=regime_labels,
            aim_weights=aim_weights,
            kelly_params=kelly_params,
        )

        # Proposed: new AIM weights and/or Kelly params
        proposed_aim = proposed_update.get("proposed_aim_weights", aim_weights)
        proposed_kelly = proposed_update.get("proposed_kelly_params", kelly_params)
        proposed_trades = engine.sizing_replay(
            trades=trades,
            regime_labels=regime_labels,
            aim_weights=proposed_aim,
            kelly_params=proposed_kelly,
        )

    else:
        # ------- Strategy replay: different SL/TP/threshold -------
        proposed_params = proposed_update.get("proposed_strategy_params", {})

        # Baseline: current locked strategy params
        baseline_strategy = {
            "sl_multiplier": locked_strategy.get("sl_multiplier",
                             locked_strategy.get("sl_multiple", 1.0)),
            "tp_multiplier": locked_strategy.get("tp_multiplier",
                             locked_strategy.get("tp_multiple", 2.0)),
        }
        baseline_trades = engine.strategy_replay(
            trades=trades,
            regime_labels=regime_labels,
            aim_weights=aim_weights,
            kelly_params=kelly_params,
            strategy_params=baseline_strategy,
        )

        # Proposed: caller-supplied strategy params
        proposed_trades = engine.strategy_replay(
            trades=trades,
            regime_labels=regime_labels,
            aim_weights=aim_weights,
            kelly_params=kelly_params,
            strategy_params=proposed_params,
        )

    # Extract daily P&L from trade lists
    def _daily_pnl(trade_list: list[dict]) -> list[float]:
        by_day: dict[str, float] = {}
        for t in trade_list:
            day = t.get("day", "unknown")
            by_day[day] = by_day.get(day, 0.0) + t.get("pnl", 0.0)
        return [by_day[d] for d in sorted(by_day)]

    baseline_pnl = _daily_pnl(baseline_trades)
    proposed_pnl = _daily_pnl(proposed_trades)

    # Delegate to existing pseudotrader comparison
    result = run_pseudotrader(asset_id, update_type, baseline_pnl, proposed_pnl)

    logger.info("Signal replay comparison %s [%s]: %d baseline trades, "
                "%d proposed trades -> %s",
                asset_id, update_type, len(baseline_trades),
                len(proposed_trades), result.get("recommendation"))

    return result


def run_cb_pseudotrader(account_id: str, historical_trades: list[dict],
                         cb_params: dict, basket_params: dict) -> dict:
    """Execute P3-PG-09B: circuit breaker pseudotrader at intraday resolution.

    Args:
        account_id: Account to evaluate
        historical_trades: List of trade dicts with: day, pnl, contracts, model, ts
        cb_params: {p, e, c, lambda_threshold}
        basket_params: {model_m: {r_bar, beta_b, sigma, rho_bar}}

    Returns:
        Comparison dict with per-layer breakdown
    """
    p = cb_params.get("p", 0.02)
    e = cb_params.get("e", 0.05)
    c = cb_params.get("c", 0.5)
    lambda_threshold = cb_params.get("lambda_threshold", 0.0)

    # Group trades by day
    by_day = defaultdict(list)
    for t in historical_trades:
        by_day[t.get("day", "unknown")].append(t)

    baseline_daily_pnl = []
    cb_daily_pnl = []
    total_blocked = 0
    total_taken = 0
    blocks_by_reason = defaultdict(int)

    for day in sorted(by_day.keys()):
        trades = sorted(by_day[day], key=lambda t: t.get("ts", ""))

        # Baseline: all trades taken
        baseline_day_pnl = sum(t["pnl"] for t in trades)
        baseline_daily_pnl.append(baseline_day_pnl)

        # CB replay
        account_balance = cb_params.get("account_balance", 150000)
        mdd = cb_params.get("mdd", cb_params.get("max_drawdown_limit", 4500))
        n_max = int(e * account_balance / max(mdd * p, 1))
        l_halt = c * e * account_balance

        l_t = 0.0
        n_t = 0
        l_b = defaultdict(float)
        n_b = defaultdict(int)
        cb_day_pnl = 0.0

        for trade in trades:
            model_m = trade.get("model", 0)
            pnl = trade["pnl"]
            bp = basket_params.get(str(model_m), basket_params.get(model_m, {}))

            # Layer 1: Hard halt
            if abs(l_t) >= l_halt:
                blocks_by_reason["HARD_HALT"] += 1
                total_blocked += 1
                continue

            # Layer 2: Budget
            if n_t >= n_max:
                blocks_by_reason["BUDGET_EXHAUSTED"] += 1
                total_blocked += 1
                continue

            # Layer 3: Conditional expectancy
            r_bar = bp.get("r_bar", 0.0)
            beta_b = bp.get("beta_b", 0.0)
            mu_b = r_bar + beta_b * l_b[model_m]
            if beta_b != 0 and mu_b <= 0:
                blocks_by_reason["BASKET_NEGATIVE_EXPECTANCY"] += 1
                total_blocked += 1
                continue

            # Layer 4: Correlation-adjusted Sharpe
            sigma = bp.get("sigma", 1.0)
            rho_bar = bp.get("rho_bar", 0.0)
            denom = sigma * math.sqrt(max(1 + 2 * n_t * rho_bar, 0.01))
            cond_sharpe = mu_b / denom if denom > 0 else 0.0
            if cond_sharpe <= lambda_threshold and lambda_threshold > 0:
                blocks_by_reason["SHARPE_BELOW_THRESHOLD"] += 1
                total_blocked += 1
                continue

            # Trade taken
            cb_day_pnl += pnl
            l_t += pnl
            n_t += 1
            l_b[model_m] += pnl
            n_b[model_m] += 1
            total_taken += 1

        cb_daily_pnl.append(cb_day_pnl)

    # Compare
    sharpe_base = _compute_sharpe(baseline_daily_pnl)
    sharpe_cb = _compute_sharpe(cb_daily_pnl)
    dd_base = _compute_max_drawdown(list(np.cumsum(baseline_daily_pnl)))
    dd_cb = _compute_max_drawdown(list(np.cumsum(cb_daily_pnl)))

    pbo = _compute_pbo(cb_daily_pnl)

    result = {
        "update_type": "CIRCUIT_BREAKER",
        "account_id": account_id,
        "params_tested": cb_params,
        "sharpe_delta": sharpe_cb - sharpe_base,
        "dd_improvement": dd_base - dd_cb,
        "pnl_delta": sum(cb_daily_pnl) - sum(baseline_daily_pnl),
        "total_blocked": total_blocked,
        "total_taken": total_taken,
        "block_rate": total_blocked / max(total_taken + total_blocked, 1),
        "blocks_by_reason": dict(blocks_by_reason),
        "pbo": pbo,
        "recommendation": "ADOPT" if (sharpe_cb - sharpe_base > 0 and dd_base - dd_cb > 0 and pbo < PBO_THRESHOLD) else "REVIEW",
    }

    # Store in P3-D11
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d11_pseudotrader_results
               (result_id, update_type, sharpe_improvement, drawdown_change,
                winrate_delta, pbo, dsr, recommendation, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (
                f"CB-{account_id}",
                "CIRCUIT_BREAKER", result["sharpe_delta"], -result["dd_improvement"],
                0.0, pbo, 0.0, result["recommendation"],
            ),
        )

    logger.info("CB Pseudotrader %s: sharpe_delta=%.4f, dd_improvement=%.4f, "
                "blocked=%d/%d, pbo=%.3f -> %s",
                account_id, result["sharpe_delta"], result["dd_improvement"],
                total_blocked, total_taken + total_blocked, pbo, result["recommendation"])

    return result


def run_cb_grid_search(account_id: str, historical_trades: list[dict],
                        basket_params: dict, base_params: dict,
                        c_values: list[float] | None = None,
                        lambda_values: list[float] | None = None) -> dict:
    """Execute P3-PG-09C: grid search over circuit breaker parameters.

    Tests all combinations of (c, lambda), selects the best set with pbo < 0.5.

    Args:
        account_id: Account to evaluate
        historical_trades: Trade history for replay
        basket_params: Per-model {r_bar, beta_b, sigma, rho_bar}
        base_params: Base CB params (p, e, account_balance)
        c_values: Grid values for c (hard halt fraction). Default [0.3,0.4,0.5,0.6,0.7]
        lambda_values: Grid values for lambda threshold. Default [0,0.1,0.2,0.5]

    Returns:
        Dict with best_params, all_results (ranked by sharpe_delta)
    """
    if c_values is None:
        c_values = [0.3, 0.4, 0.5, 0.6, 0.7]
    if lambda_values is None:
        lambda_values = [0.0, 0.1, 0.2, 0.5]

    results = []

    for c in c_values:
        for lam in lambda_values:
            params = {**base_params, "c": c, "lambda_threshold": lam}
            result = run_cb_pseudotrader(account_id, historical_trades, params, basket_params)
            result["params"] = {"c": c, "lambda_threshold": lam}
            results.append(result)

    # Filter by PBO < 0.5, rank by sharpe_delta descending
    valid = [r for r in results if r["pbo"] < PBO_THRESHOLD]
    valid.sort(key=lambda r: r["sharpe_delta"], reverse=True)

    best = valid[0] if valid else None

    if best:
        logger.info("CB grid search %s: best c=%.2f, lambda=%.2f, sharpe_delta=%.4f",
                    account_id, best["params"]["c"], best["params"]["lambda_threshold"],
                    best["sharpe_delta"])
    else:
        logger.warning("CB grid search %s: no valid parameter set found (all pbo >= 0.5)",
                       account_id)

    return {
        "account_id": account_id,
        "best_params": best["params"] if best else None,
        "best_result": best,
        "all_results": results,
        "valid_count": len(valid),
        "total_tested": len(results),
    }


def run_multistage_replay(trades: list[dict],
                           starting_balance: float = 150000) -> dict:
    """Replay trades through full EVAL -> XFA -> LIVE lifecycle.

    Uses MultiStageTopstepAccount to track stage transitions, failures,
    fee charges ($226.60 per failure), and balance carryover.

    Args:
        trades: List of trade dicts with keys: day, pnl, contracts, ts, model
        starting_balance: Initial EVAL balance (default $150K)

    Returns:
        Dict with lifecycle results including stage progression, failures,
        fees, and per-stage performance metrics.
    """
    from shared.account_lifecycle import MultiStageTopstepAccount, TopstepStage

    account = MultiStageTopstepAccount(starting_balance=starting_balance)

    # Group trades by day
    by_day = defaultdict(list)
    for t in trades:
        by_day[t.get("day", "unknown")].append(t)

    per_stage_pnl = defaultdict(list)  # stage -> daily pnl list
    stage_at_day = {}
    total_trades_taken = 0
    total_trades_blocked = 0

    for day in sorted(by_day.keys()):
        day_trades = sorted(by_day[day], key=lambda t: t.get("ts", ""))
        stage_at_day[day] = account.current_stage.value
        day_pnl = 0.0

        for trade in day_trades:
            result = account.process_trade(trade)
            if result["allowed"]:
                day_pnl += result["adjusted_pnl"]
                total_trades_taken += 1
            else:
                total_trades_blocked += 1

            # Handle post-trade breach
            if result.get("breach_type") == "MLL":
                break  # stop processing this day

        per_stage_pnl[account.current_stage.value].append(day_pnl)

        # End of day processing (checks transitions, failures)
        eod = account.end_of_day(day)
        if eod["failure"]:
            # After failure + reset, future days start fresh EVAL
            pass
        if eod["stage_changed"] and not eod["failure"]:
            # Successful transition -- log it
            pass

    # Compute per-stage metrics
    stage_metrics = {}
    for stage_name, pnl_list in per_stage_pnl.items():
        if pnl_list:
            stage_metrics[stage_name] = {
                "trading_days": len(pnl_list),
                "net_pnl": sum(pnl_list),
                "sharpe": _compute_sharpe(pnl_list),
                "max_drawdown": _compute_max_drawdown(
                    list(np.cumsum(pnl_list))),
                "win_rate": _compute_win_rate(pnl_list),
                "pbo": _compute_pbo(pnl_list),
            }

    # Flatten all daily P&L in order
    all_daily_pnl = []
    for stage_pnl in per_stage_pnl.values():
        all_daily_pnl.extend(stage_pnl)

    snapshot = account.get_state_snapshot()

    result = {
        "stages_reached": list(per_stage_pnl.keys()),
        "stage_metrics": stage_metrics,
        "final_stage": snapshot["current_stage"],
        "final_balance": snapshot["balance"],
        "tradable_balance": snapshot["tradable_balance"],
        "reserve_balance": snapshot["reserve_balance"],
        "total_fees": snapshot["total_fees"],
        "total_resets": snapshot["total_resets"],
        "total_trades_taken": total_trades_taken,
        "total_trades_blocked": total_trades_blocked,
        "net_pnl": sum(all_daily_pnl),
        "sharpe": _compute_sharpe(all_daily_pnl),
        "max_drawdown": _compute_max_drawdown(
            list(np.cumsum(all_daily_pnl))) if all_daily_pnl else 0.0,
        "events": [
            {
                "event_type": e.event_type,
                "from_stage": e.from_stage,
                "to_stage": e.to_stage,
                "trigger": e.trigger,
                "balance": e.balance_at_event,
                "fee": e.fee_charged,
                "ts": e.ts,
            }
            for e in account.events
        ],
    }

    # Store summary in P3-D11
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d11_pseudotrader_results
                   (result_id, update_type, sharpe_improvement, drawdown_change,
                    winrate_delta, pbo, dsr, recommendation, ts)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (
                    f"MSR-{uuid.uuid4().hex[:8]}",
                    "MULTISTAGE_REPLAY",
                    result["sharpe"], -result["max_drawdown"],
                    0.0, 0.0, 0.0,
                    f"STAGES:{','.join(result['stages_reached'])}",
                ),
            )
    except Exception as exc:
        logger.warning("Failed to store multistage replay result: %s", exc)

    logger.info("Multistage replay: stages=%s, resets=%d, fees=$%.2f, "
                "final_stage=%s, final_balance=$%.2f",
                result["stages_reached"], result["total_resets"],
                result["total_fees"], result["final_stage"],
                result["final_balance"])

    return result


# ---------------------------------------------------------------------------
# Two-Forecast Structure — P3-D27 (Spec Sec 5)
# ---------------------------------------------------------------------------

def _compute_sortino(returns: list[float]) -> float:
    """Annualized Sortino ratio from daily returns."""
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    mean = arr.mean()
    downside = arr[arr < 0]
    down_std = downside.std() if len(downside) > 1 else 1e-10
    if down_std < 1e-10:
        return 0.0
    return float(mean / down_std * math.sqrt(252))


def _compute_calmar(returns: list[float], max_dd: float) -> float:
    """Calmar ratio: annualised return / max drawdown."""
    if max_dd < 1e-10 or len(returns) < 2:
        return 0.0
    annual_return = sum(returns) / (len(returns) / 252)
    return float(annual_return / max_dd)


def _compute_profit_factor(returns: list[float]) -> float:
    """Gross profit / gross loss."""
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    if gross_loss < 1e-10:
        return float("inf") if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def _max_dd_duration(equity_curve: list[float]) -> int:
    """Max drawdown duration in trading days."""
    if not equity_curve:
        return 0
    peak = equity_curve[0]
    peak_idx = 0
    max_duration = 0
    for i, v in enumerate(equity_curve):
        if v >= peak:
            peak = v
            peak_idx = i
        else:
            max_duration = max(max_duration, i - peak_idx)
    return max_duration


def _monthly_equity_curve(daily_pnl: list[float],
                          day_labels: list[str]) -> list[dict]:
    """Aggregate daily P&L into monthly equity curve points."""
    monthly = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
    cumulative = 0.0
    for pnl, day in zip(daily_pnl, day_labels):
        month = day[:7]  # "YYYY-MM"
        monthly[month]["pnl"] += pnl
        monthly[month]["trades"] += 1

    curve = []
    cumulative = 0.0
    peak = 0.0
    for month in sorted(monthly.keys()):
        cumulative += monthly[month]["pnl"]
        peak = max(peak, cumulative)
        dd_pct = (peak - cumulative) / peak if peak > 0 else 0.0
        curve.append({
            "date": month,
            "cumulative_pnl": round(cumulative, 2),
            "drawdown_pct": round(dd_pct, 4),
            "trade_count": monthly[month]["trades"],
        })
    return curve


def _build_system_state_snapshot() -> dict:
    """Build system state snapshot for forecast versioning.

    Captures current pipeline parameters, AIM weights, and active models.
    Falls back gracefully if config files are unavailable.
    """
    import hashlib
    from datetime import datetime as _dt
    from pathlib import Path

    state = {
        "version": "v1.0.0",
        "run_date": _dt.now().isoformat(),
        "pipeline_parameters": {},
        "aim_weights": {},
        "active_models": [],
        "state_hash": "",
    }

    # Try to load pipeline config
    config_dir = Path(__file__).parent.parent.parent / "config"
    try:
        config_path = config_dir / "pipeline_config.json"
        if config_path.exists():
            with open(config_path) as f:
                state["pipeline_parameters"] = json.load(f)
    except Exception:
        pass

    # Try to load AIM weights from QuestDB
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT aim_id, inclusion_probability FROM p3_d02_aim_meta_weights "
                "ORDER BY ts DESC LIMIT 20")
            rows = cur.fetchall()
            state["aim_weights"] = {str(r[0]): float(r[1]) for r in rows}
    except Exception:
        pass

    # Hash the entire state for comparison
    state_str = json.dumps(state, sort_keys=True, default=str)
    state["state_hash"] = f"sha256:{hashlib.sha256(state_str.encode()).hexdigest()[:16]}"

    return state


def generate_forecast(trades: list[dict],
                      account_config: dict | None = None,
                      forecast_type: str = "FULL_HISTORY",
                      account_id: str = "default",
                      system_state: dict | None = None) -> dict:
    """Generate a standardized backtest forecast per spec Sec 5.

    Produces either Forecast A (full history) or Forecast B (rolling 252-day)
    with comprehensive performance metrics, constraint breach counts,
    equity curves, and system state snapshots.

    Args:
        trades: List of trade dicts with keys: day, pnl, contracts, ts, model
        account_config: TSM config dict (or None for unconstrained)
        forecast_type: "FULL_HISTORY" or "ROLLING_252D"
        account_id: Account identifier
        system_state: Pre-built system state snapshot (or None to generate)

    Returns:
        Forecast dict matching P3-D27 schema.
    """
    if not trades:
        logger.warning("No trades for forecast generation")
        return {}

    # For rolling 252-day, filter to last 252 trading days
    if forecast_type == "ROLLING_252D":
        unique_days = sorted(set(t["day"] for t in trades))
        if len(unique_days) > 252:
            cutoff_day = unique_days[-252]
            trades = [t for t in trades if t["day"] >= cutoff_day]

    # Run account-aware replay to get constraint-enforced results
    replay_result = run_account_aware_replay(
        asset_id=trades[0].get("asset", "UNKNOWN"),
        update_type="FORECAST",
        trades=trades,
        account_config=account_config,
    )

    # Reconstruct daily P&L and day labels from trades (post-constraint)
    by_day = defaultdict(float)
    trade_counts_by_day = defaultdict(int)
    for t in trades:
        by_day[t["day"]] += t["pnl"]
        trade_counts_by_day[t["day"]] += 1

    sorted_days = sorted(by_day.keys())
    daily_pnl = [by_day[d] for d in sorted_days]

    # Core metrics
    eq_curve = list(np.cumsum(daily_pnl))
    sharpe = _compute_sharpe(daily_pnl)
    sortino = _compute_sortino(daily_pnl)
    max_dd_pct = _compute_max_drawdown(eq_curve)
    max_dd_abs = max(eq_curve) - min(eq_curve) if eq_curve else 0.0
    max_dd_dur = _max_dd_duration(eq_curve)
    calmar = _compute_calmar(daily_pnl, max_dd_abs)
    profit_factor = _compute_profit_factor(daily_pnl)
    net_pnl = sum(daily_pnl)
    total_trades = sum(trade_counts_by_day.values())

    # Per-trade P&L for win/loss averages
    all_trade_pnl = [t["pnl"] for t in trades]
    wins = [p for p in all_trade_pnl if p > 0]
    losses = [p for p in all_trade_pnl if p < 0]
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = net_pnl / total_trades if total_trades > 0 else 0.0

    # Annualised return
    years = len(sorted_days) / 252 if sorted_days else 1.0
    annualised_return = net_pnl / years if years > 0 else 0.0

    # Regime breakdown (if available in trade data)
    pnl_by_regime = defaultdict(float)
    trades_by_regime = defaultdict(int)
    regime_daily_pnl = defaultdict(list)
    for t in trades:
        regime = str(t.get("regime", "UNKNOWN"))
        pnl_by_regime[regime] += t["pnl"]
        trades_by_regime[regime] += 1
        regime_daily_pnl[regime].append(t["pnl"])
    sharpe_by_regime = {
        r: _compute_sharpe(pnls) for r, pnls in regime_daily_pnl.items()
    }

    # Monthly equity curve
    monthly_curve = _monthly_equity_curve(daily_pnl, sorted_days)

    # Eval-specific metrics (PROP_EVAL only)
    eval_metrics = None
    if account_config:
        classification = account_config.get("classification", {})
        if classification.get("category") == "PROP_EVAL":
            profit_target = account_config.get("profit_target", 9000)
            mdd_limit = account_config.get("max_drawdown_limit", 4500)
            starting_bal = account_config.get("starting_balance", 150000)

            # Simulate pass/fail over the full history
            pass_count = 0
            fail_mdd_count = 0
            fail_dll_count = 0
            days_to_pass_list = []
            running = starting_bal
            peak = starting_bal
            attempt_start_idx = 0

            for i, dpnl in enumerate(daily_pnl):
                running += dpnl
                peak = max(peak, running)
                if running >= starting_bal + profit_target:
                    pass_count += 1
                    days_to_pass_list.append(i - attempt_start_idx + 1)
                    running = starting_bal
                    peak = starting_bal
                    attempt_start_idx = i + 1
                elif (peak - running) >= mdd_limit:
                    fail_mdd_count += 1
                    running = starting_bal
                    peak = starting_bal
                    attempt_start_idx = i + 1

            total_attempts = pass_count + fail_mdd_count + fail_dll_count
            eval_metrics = {
                "pass_simulations": pass_count,
                "avg_days_to_pass": (sum(days_to_pass_list) / len(days_to_pass_list)
                                     if days_to_pass_list else 0.0),
                "fail_rate_mdd": (fail_mdd_count / total_attempts
                                  if total_attempts > 0 else 0.0),
                "fail_rate_dll": (fail_dll_count / total_attempts
                                  if total_attempts > 0 else 0.0),
                "total_attempts": total_attempts,
            }

    # Rolling-252D specific fields
    rolling_extras = {}
    if forecast_type == "ROLLING_252D":
        # Regime distribution
        total_regime_trades = sum(trades_by_regime.values())
        rolling_extras["regime_distribution"] = {
            r: round(c / total_regime_trades, 4) if total_regime_trades > 0 else 0.0
            for r, c in trades_by_regime.items()
        }
        # Current regime (last trade's regime)
        rolling_extras["current_regime"] = str(trades[-1].get("regime", "UNKNOWN"))
        # Momentum: slope of 60-day rolling Sharpe
        if len(daily_pnl) >= 60:
            rolling_sharpes = []
            for i in range(60, len(daily_pnl) + 1):
                window = daily_pnl[i - 60:i]
                rolling_sharpes.append(_compute_sharpe(window))
            if len(rolling_sharpes) >= 2:
                x = np.arange(len(rolling_sharpes))
                slope = float(np.polyfit(x, rolling_sharpes, 1)[0])
                rolling_extras["momentum_indicator"] = round(slope, 6)
            else:
                rolling_extras["momentum_indicator"] = 0.0
        else:
            rolling_extras["momentum_indicator"] = 0.0
        # Streak
        streak = 0
        for dpnl in reversed(daily_pnl):
            if streak == 0:
                streak = 1 if dpnl > 0 else -1
            elif (streak > 0 and dpnl > 0) or (streak < 0 and dpnl < 0):
                streak += 1 if streak > 0 else -1
            else:
                break
        rolling_extras["streak"] = streak

    # Build system state snapshot
    if system_state is None:
        try:
            system_state = _build_system_state_snapshot()
        except Exception:
            system_state = {"version": "v1.0.0", "run_date": "", "state_hash": ""}

    forecast_id = f"FCT-{uuid.uuid4().hex[:12].upper()}"

    forecast = {
        "forecast_id": forecast_id,
        "forecast_type": forecast_type,
        "account_id": account_id,
        "version": system_state.get("version", "v1.0.0"),
        "run_date": system_state.get("run_date", ""),
        "window_start": sorted_days[0] if sorted_days else "",
        "window_end": sorted_days[-1] if sorted_days else "",
        "trading_days": len(sorted_days),

        # Performance metrics
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 2),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "max_drawdown_duration": max_dd_dur,
        "calmar": round(calmar, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "net_pnl": round(net_pnl, 2),
        "annualised_return": round(annualised_return, 2),

        # Account constraint metrics (from replay)
        "dll_breaches_total": replay_result.get("dll_breaches", 0),
        "scaling_cap_hits": replay_result.get("scaling_cap_hits", 0),
        "consistency_violations": replay_result.get("consistency_violations", 0),
        "trading_hours_closes": replay_result.get("trading_hours_blocks", 0),
        "capital_unlock_events": replay_result.get("capital_unlock_events", 0),
        "mdd_breach": replay_result.get("mdd_breach", False),
        "mdd_breach_date": replay_result.get("mdd_breach_day"),

        # Regime breakdown
        "pnl_by_regime": dict(pnl_by_regime),
        "trades_by_regime": dict(trades_by_regime),
        "sharpe_by_regime": sharpe_by_regime,

        # Equity curve (monthly)
        "equity_curve_monthly": monthly_curve,

        # Eval-specific
        "eval_metrics": eval_metrics,

        # Rolling-252D extras
        **rolling_extras,

        # System state snapshot
        "system_state": system_state,

        # Caveats
        "caveats": _forecast_caveats(forecast_type, sorted_days, trades_by_regime),
    }

    logger.info("Generated %s forecast %s: %d days, %d trades, "
                "Sharpe=%.3f, net_pnl=$%.2f",
                forecast_type, forecast_id, len(sorted_days),
                total_trades, sharpe, net_pnl)

    return forecast


def _forecast_caveats(forecast_type: str, sorted_days: list[str],
                      trades_by_regime: dict) -> list[str]:
    """Generate warning caveats per spec Sec 5.6."""
    caveats = []

    if forecast_type == "FULL_HISTORY":
        caveats.append(
            "HYPOTHETICAL — uses current parameters retroactively across "
            "full history. Performance is not achievable in real time.")
        caveats.append(
            "Account constraints applied retroactively. Topstep XFA/Live "
            "rules did not exist before ~2022.")

    # Check regime concentration
    total = sum(trades_by_regime.values())
    if total > 0:
        for regime, count in trades_by_regime.items():
            pct = count / total
            if pct > 0.80:
                caveats.append(
                    f"WARNING: window dominated by regime '{regime}' "
                    f"({pct:.0%} of trades). Performance may not generalise.")

    # Check if window is short
    if len(sorted_days) < 100:
        caveats.append(
            f"Short window ({len(sorted_days)} days). Metrics may have "
            "high variance.")

    return caveats


def generate_dual_forecasts(trades: list[dict],
                             account_config: dict | None = None,
                             account_id: str = "default") -> dict:
    """Generate both Forecast A (full history) and Forecast B (rolling 252-day).

    Per spec Sec 5: every pseudotrader run produces two standardized forecasts.

    Args:
        trades: Full history trade list
        account_config: TSM config dict
        account_id: Account identifier

    Returns:
        Dict with forecast_a, forecast_b, and system_state.
    """
    system_state = _build_system_state_snapshot()

    forecast_a = generate_forecast(
        trades=trades,
        account_config=account_config,
        forecast_type="FULL_HISTORY",
        account_id=account_id,
        system_state=system_state,
    )

    forecast_b = generate_forecast(
        trades=trades,
        account_config=account_config,
        forecast_type="ROLLING_252D",
        account_id=account_id,
        system_state=system_state,
    )

    result = {
        "account_id": account_id,
        "system_state": system_state,
        "forecast_a": forecast_a,
        "forecast_b": forecast_b,
    }

    # Store both in P3-D27
    for fc in [forecast_a, forecast_b]:
        if not fc:
            continue
        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d27_pseudotrader_forecasts
                       (forecast_id, forecast_type, account_id, version,
                        run_date, window_start, window_end,
                        metrics, equity_curve, system_state, ts)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                    (
                        fc["forecast_id"],
                        fc["forecast_type"],
                        account_id,
                        fc["version"],
                        fc["run_date"],
                        fc["window_start"],
                        fc["window_end"],
                        json.dumps({k: v for k, v in fc.items()
                                    if k not in ("equity_curve_monthly",
                                                 "system_state", "forecast_id",
                                                 "forecast_type", "account_id",
                                                 "version", "run_date",
                                                 "window_start", "window_end")}),
                        json.dumps(fc.get("equity_curve_monthly", [])),
                        json.dumps(system_state),
                    ),
                )
        except Exception as exc:
            logger.warning("Failed to store forecast %s: %s",
                           fc.get("forecast_id"), exc)

    logger.info("Dual forecasts generated for account %s: "
                "A=%s (%d days), B=%s (%d days)",
                account_id,
                forecast_a.get("forecast_id", "N/A"),
                forecast_a.get("trading_days", 0),
                forecast_b.get("forecast_id", "N/A"),
                forecast_b.get("trading_days", 0))

    return result
