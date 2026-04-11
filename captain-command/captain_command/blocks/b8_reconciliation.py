# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 8: Daily Reconciliation (P3-PG-39).

Runs at 19:00 EST.  Three responsibilities:

1. **Reconciliation** — Sync system state with broker truth (API-connected)
   or manual user confirmation.  Mismatch > $1 auto-corrects from broker.
2. **SOD Topstep Parameter Computation (V3)** — For accounts with
   ``topstep_optimisation == true``, compute f(A), N(A), E(A), L_halt,
   scaling_tier, W(A), g(A), and store in P3-D08.
3. **Payout Recommendation (V3)** — Check if payout is recommended,
   send GUI notification with amount, net, tier impact, MDD% impact.
4. **Daily Reset** — Reset daily counters: daily_loss_used, D23 intraday
   state (L_t, n_t, L_b, n_b).

Spec: Program3_Command.md lines 661-718 + V3 Amendments
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Callable

from shared.questdb_client import get_cursor
from shared.journal import write_checkpoint
from shared.constants import SOD_RESET_HOUR, SOD_RESET_MINUTE, now_et

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Main reconciliation entry point
# ---------------------------------------------------------------------------


def run_daily_reconciliation(gui_push_fn: Callable,
                             get_broker_status_fn: Callable | None = None,
                             notify_fn: Callable | None = None):
    """Run the full 19:00 EST reconciliation cycle.

    Parameters
    ----------
    gui_push_fn : callable
        ``gui_push_fn(user_id, message_dict)``
    get_broker_status_fn : callable or None
        ``get_broker_status_fn(account_id) → {balance, drawdown, ...}``
        None for manual-only accounts.
    notify_fn : callable or None
        ``notify_fn(notif_dict)``
    """
    write_checkpoint("COMMAND", "RECONCILIATION", "starting", "process_accounts")
    logger.info("Daily reconciliation started at %s", now_et().isoformat())

    try:
        accounts = _get_all_accounts()

        for ac in accounts:
            ac_id = ac["account_id"]
            user_id = ac["user_id"]

            # Step 1: Reconcile with broker or request manual input
            if get_broker_status_fn and ac.get("api_connected"):
                _reconcile_api_account(ac_id, user_id, ac, get_broker_status_fn, gui_push_fn)
            else:
                _request_manual_reconciliation(ac_id, user_id, gui_push_fn)

            # Step 2: SOD Topstep parameter computation (V3)
            if ac.get("scaling_plan_active"):
                _compute_sod_topstep_params(ac_id, user_id, ac, gui_push_fn, notify_fn)

        # Step 3: Daily counter resets (all accounts)
        _reset_daily_counters()

        write_checkpoint("COMMAND", "RECONCILIATION_COMPLETE", "all_accounts", "waiting")
        logger.info("Daily reconciliation complete")

    except Exception as exc:
        logger.error("Reconciliation failed: %s", exc, exc_info=True)
        write_checkpoint("COMMAND", "RECONCILIATION_ERROR", "failed", "retry",
                         {"error": str(exc)})


# ---------------------------------------------------------------------------
# API-connected reconciliation
# ---------------------------------------------------------------------------


def _reconcile_api_account(ac_id: str, user_id: str, ac: dict,
                           get_broker_status_fn: Callable,
                           gui_push_fn: Callable):
    """Reconcile an API-connected account with broker truth."""
    try:
        broker_status = get_broker_status_fn(ac_id)
        if not broker_status:
            logger.warning("No broker status for account %s", ac_id)
            return

        broker_balance = broker_status.get("balance")
        system_balance = ac.get("current_balance")

        if broker_balance is None or system_balance is None:
            return

        mismatch = abs(broker_balance - system_balance)

        if mismatch > 1.0:
            # Auto-correct from broker (trusted source)
            _update_account_balance(ac_id, broker_balance)

            gui_push_fn(user_id, {
                "type": "notification",
                "priority": "MEDIUM",
                "message": (
                    f"Account {ac_id} balance reconciled: "
                    f"system ${system_balance:,.2f} → broker ${broker_balance:,.2f} "
                    f"(diff: ${mismatch:,.2f})"
                ),
                "source": "RECONCILIATION",
                "timestamp": now_et().isoformat(),
            })

            logger.info("Balance corrected for %s: %.2f → %.2f (diff: %.2f)",
                        ac_id, system_balance, broker_balance, mismatch)

        _log_reconciliation(ac_id, user_id, "API", system_balance,
                           broker_balance, mismatch)

    except Exception as exc:
        logger.error("API reconciliation failed for %s: %s", ac_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Manual reconciliation request
# ---------------------------------------------------------------------------


def _request_manual_reconciliation(ac_id: str, user_id: str,
                                    gui_push_fn: Callable):
    """Send a notification requesting manual balance confirmation."""
    gui_push_fn(user_id, {
        "type": "notification",
        "priority": "MEDIUM",
        "message": f"Please confirm current balance for account {ac_id} via GUI.",
        "source": "RECONCILIATION",
        "timestamp": now_et().isoformat(),
        "data": {
            "action": "CONFIRM_BALANCE",
            "account_id": ac_id,
        },
    })

    _log_reconciliation(ac_id, user_id, "MANUAL_REQUESTED", None, None, None)


def process_manual_balance(ac_id: str, user_id: str, reported_balance: float):
    """Process a manually reported balance from the user.

    Called from the GUI/API when the user responds to the reconciliation
    request.
    """
    _update_account_balance(ac_id, reported_balance)
    _log_reconciliation(ac_id, user_id, "MANUAL_CONFIRMED",
                       None, reported_balance, 0)
    logger.info("Manual balance confirmed for %s: %.2f", ac_id, reported_balance)


# ---------------------------------------------------------------------------
# V3: SOD Topstep Parameter Computation
# ---------------------------------------------------------------------------


def _compute_sod_topstep_params(ac_id: str, user_id: str, ac: dict,
                                 gui_push_fn: Callable,
                                 notify_fn: Callable | None):
    """Compute start-of-day Topstep-specific parameters.

    From Topstep_Optimisation_Functions.md Part 6:
        f(A) = MDD / A                           (MDD%)
        R_eff(A, p, φ) = p·f(A) + φ/A           (effective risk per trade)
        N(A, p, e, φ) = floor((e·A) / (MDD·p + φ))  (max trades/day)
        E(A, e) = e·A                            (daily exposure budget $)
        W(A) = min(5000, 0.5·(A - starting))     (max payout)
        g(A) = MDD / (A - W(A))                  (post-payout MDD%)
    Where MDD is read from account config (not hardcoded).
        L_halt = c·e·A                           (hard halt threshold $)
        scaling_tier = lookup(profit)
    """
    try:
        ts_state = json.loads(ac.get("topstep_state", "{}"))
        ts_params = ts_state.get("topstep_params", {})
        payout_rules = ts_state.get("payout_rules", {})
        fee_schedule = ts_state.get("fee_schedule", {})

        A = ac.get("current_balance", 0)
        starting = ac.get("starting_balance", 150000)
        profit = A - starting

        if A <= 0:
            logger.warning("Account %s has non-positive balance: %.2f", ac_id, A)
            return

        p = ts_params.get("p", 0.005)
        e = ts_params.get("e", 0.01)
        c = ts_params.get("c", 0.5)
        lam = ts_params.get("lambda", 0)

        # Default fee for primary instrument
        fees_by_inst = fee_schedule.get("fees_by_instrument", {})
        phi = 0.0
        if fees_by_inst:
            # Use ES as default
            es_fees = fees_by_inst.get("ES", {})
            phi = es_fees.get("round_turn", 0)

        # f(A) — MDD as fraction of balance
        mdd_limit = ac.get("max_drawdown_limit", 4500)
        f_A = mdd_limit / A

        # R_eff — effective risk per trade
        R_eff = p * f_A + phi / A

        # N — max trades per day
        denom = mdd_limit * p + phi
        N = math.floor((e * A) / denom) if denom > 0 else 0

        # E — daily exposure budget
        E = e * A

        # L_halt — hard halt threshold
        L_halt = c * e * A

        # W(A) — max payout
        max_per = payout_rules.get("max_per_payout", 5000)
        max_pct = 0.50
        commission_rate = payout_rules.get("commission_rate", 0.10)
        tier_floor = payout_rules.get("scaling_tier_floor", 4500)

        W = min(max_per, max_pct * max(A - starting, 0))

        # g(A) — post-payout MDD%
        balance_after_payout = A - W
        g_A = mdd_limit / balance_after_payout if balance_after_payout > 0 else 0

        # Scaling tier
        from captain_command.blocks.b4_tsm_manager import get_scaling_tier
        scaling = get_scaling_tier(ac, profit)

        # Store computed params in P3-D08 topstep_state
        computed = {
            "topstep_params": ts_params,
            "payout_rules": payout_rules,
            "fee_schedule": fee_schedule,
            "scaling_plan": ts_state.get("scaling_plan", []),
            "computed_sod": {
                "f_A": round(f_A, 6),
                "R_eff": round(R_eff, 6),
                "N_max_trades": N,
                "E_daily_exposure": round(E, 2),
                "L_halt": round(L_halt, 2),
                "W_max_payout": round(W, 2),
                "g_A_post_payout_mdd": round(g_A, 6),
                "computed_at": now_et().isoformat(),
            },
            "scaling_tier": scaling.get("tier_label", ""),
            "current_tier_label": scaling.get("tier_label", ""),
            "current_max_micros": scaling.get("max_micros", 0),
            "profit_to_next_tier": scaling.get("profit_to_next_tier", 0),
            "next_tier_label": scaling.get("next_tier_label", ""),
            "payouts_remaining": payout_rules.get("max_total_payouts", 5),
            "tier_after_payout": scaling.get("tier_label", ""),
        }

        _update_topstep_state(ac_id, json.dumps(computed))

        logger.info("SOD Topstep params computed for %s: f(A)=%.4f N=%d E=%.2f L_halt=%.2f",
                    ac_id, f_A, N, E, L_halt)

        # V3: Payout recommendation notification
        _check_payout_recommendation(
            ac_id, user_id, ac, profit, W, commission_rate,
            tier_floor, scaling, gui_push_fn, notify_fn,
        )

    except Exception as exc:
        logger.error("SOD Topstep computation failed for %s: %s", ac_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# V3: Payout Recommendation
# ---------------------------------------------------------------------------


def _check_payout_recommendation(ac_id: str, user_id: str, ac: dict,
                                  profit: float, W: float,
                                  commission_rate: float, tier_floor: float,
                                  scaling: dict, gui_push_fn: Callable,
                                  notify_fn: Callable | None):
    """Check if a payout is recommended using 4-step spec decision.

    Per Payout_Rules.md:
    Step 1: Tier-preserving max
    Step 2: Cap withdrawal to tier-preserving max
    Step 3: Net after commission check (>= $500)
    Step 4: MDD% impact check
    """
    # E7: Account-type-aware payout rules
    account_type = ac.get("account_type", "PROP_XFA")
    if account_type == "BROKER_LIVE":
        commission_rate = 0.0  # Live accounts: 0% commission
        # Live requires 30 winning days before payouts
        winning_days = ac.get("winning_days", 0)
        if winning_days < 30:
            return  # Not enough winning days for live payout

    # Step 1: Tier-preserving max — ensure profit stays above tier floor
    tier_preserving_max = profit - tier_floor
    if tier_preserving_max <= 0:
        return  # PROFIT_BELOW_TIER_FLOOR

    # Step 2: Cap withdrawal to tier-preserving max
    withdraw_amount = min(W, tier_preserving_max)

    # Step 3: Net after commission check (not gross)
    net_after_commission = withdraw_amount * (1 - commission_rate)
    if net_after_commission < 500:
        return  # NET_BELOW_MINIMUM

    # Step 4: MDD% impact check
    A = ac.get("current_balance", 0)
    mdd_limit = ac.get("max_drawdown_limit", 4500)
    f_target_max = _get_d17_param("f_target_max", 0.03)

    A_post = A - withdraw_amount
    if A_post > 0:
        f_post = mdd_limit / A_post
        if f_post > f_target_max:
            # Reduce withdrawal to keep f_post within target
            # f_target_max = mdd_limit / (A - W_adj) => W_adj = A - mdd_limit / f_target_max
            withdraw_amount = A - (mdd_limit / f_target_max)
            withdraw_amount = min(withdraw_amount, tier_preserving_max, W)
            withdraw_amount = max(withdraw_amount, 0)
            # Recheck net after adjustment
            net_after_commission = withdraw_amount * (1 - commission_rate)
            if net_after_commission < 500:
                return  # Adjusted amount too small
            f_post = mdd_limit / (A - withdraw_amount) if (A - withdraw_amount) > 0 else 0
    else:
        return  # Balance too low

    # Build notification
    profit_after = profit - withdraw_amount
    tsm_name = ac.get("tsm_name", ac_id)
    payouts_remaining = scaling.get("payouts_remaining", "N/A")

    message = (
        f"PAYOUT RECOMMENDED: {tsm_name}. "
        f"Withdraw ${withdraw_amount:,.0f} "
        f"(receive ${net_after_commission:,.0f} after {commission_rate * 100:.0f}% commission). "
        f"Profit stays at ${profit_after:,.0f} → tier {scaling.get('tier_label', 'maintained')}. "
        f"Post-payout MDD%: {f_post:.4f}. Payouts remaining: {payouts_remaining}."
    )

    notif = {
        "type": "notification",
        "priority": "MEDIUM",
        "message": message,
        "source": "PAYOUT_RECOMMENDATION",
        "user_id": user_id,
        "timestamp": now_et().isoformat(),
        "data": {
            "account_id": ac_id,
            "payout_amount": round(withdraw_amount, 2),
            "net_amount": round(net_after_commission, 2),
            "profit_after": round(profit_after, 2),
            "tier_after": scaling.get("tier_label", ""),
            "f_post": round(f_post, 6),
            "payouts_remaining": payouts_remaining,
        },
    }

    gui_push_fn(user_id, notif)

    if notify_fn:
        notify_fn(notif)

    logger.info("Payout recommendation sent: %s $%.0f for user %s", ac_id, withdraw_amount, user_id)


# ---------------------------------------------------------------------------
# Daily counter resets
# ---------------------------------------------------------------------------


def _reset_daily_counters():
    """Reset daily loss counters and D23 intraday state for all accounts.

    Called at 19:00 EST as part of reconciliation.
    """
    try:
        with get_cursor() as cur:
            # Reset daily_loss_used in P3-D08
            # QuestDB doesn't support UPDATE, so we track the reset via session log
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), "SYSTEM",
                    "DAILY_RESET", "RESET-" + now_et().strftime("%Y%m%d"),
                    "", json.dumps({"reset_type": "daily_counters"}),
                ),
            )

            # Reset P3-D23 intraday circuit breaker state
            # Insert fresh zero rows for each account
            cur.execute(
                "SELECT DISTINCT account_id FROM p3_d08_tsm_state"
            )
            accounts = cur.fetchall()
            for (ac_id,) in accounts:
                cur.execute(
                    """INSERT INTO p3_d23_circuit_breaker_intraday(
                           timestamp, account_id, L_t, n_t,
                           L_b, n_b, reset_flag
                       ) VALUES(%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        now_et().isoformat(), ac_id,
                        0.0, 0,
                        json.dumps({}), json.dumps({}),
                        True,
                    ),
                )

        logger.info("Daily counters reset for %d accounts", len(accounts) if accounts else 0)

    except Exception as exc:
        logger.error("Daily counter reset failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_d17_param(key: str, default: float) -> float:
    """Read a single parameter from P3-D17 system_monitor_state."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT param_value FROM p3_d17_system_monitor_state
                   WHERE param_key = %s
                   ORDER BY last_updated DESC LIMIT 1""",
                (key,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(json.loads(row[0]))
    except Exception as exc:
        logger.warning("D17 param %s lookup failed, using default %.4f: %s",
                       key, default, exc)
    return default


def _get_all_accounts() -> list[dict]:
    """Fetch all active accounts from P3-D08."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT account_id, user_id, tsm_name,
                          current_balance, starting_balance,
                          max_drawdown_limit, max_daily_loss,
                          topstep_optimisation, topstep_state,
                          scaling_plan_active
                   FROM p3_d08_tsm_state
                   ORDER BY account_id"""
            )
            results = []
            for r in cur.fetchall():
                results.append({
                    "account_id": r[0],
                    "user_id": r[1],
                    "tsm_name": r[2],
                    "current_balance": r[3],
                    "starting_balance": r[4],
                    "max_drawdown_limit": r[5],
                    "max_daily_loss": r[6],
                    "topstep_optimisation": r[7],
                    "topstep_state": r[8] or "{}",
                    "scaling_plan_active": r[9],
                })
            return results
    except Exception as exc:
        logger.error("Failed to fetch accounts: %s", exc, exc_info=True)
    return []


def _update_account_balance(ac_id: str, new_balance: float):
    """Update account balance in P3-D08 (via insert — QuestDB append-only).

    Reads the latest D08 snapshot for the account, replaces current_balance
    with *new_balance*, and appends a corrected row.  Also writes an audit
    entry to the session event log.
    """
    try:
        with get_cursor() as cur:
            # 1. Read latest D08 snapshot to carry forward all fields
            cur.execute(
                """SELECT account_id, user_id, name, classification,
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
                          scaling_tier_micros
                   FROM p3_d08_tsm_state
                   WHERE account_id = %s
                   ORDER BY last_updated DESC
                   LIMIT 1""",
                (ac_id,),
            )
            row = cur.fetchone()
            if not row:
                logger.warning("No D08 row for account %s — cannot correct balance", ac_id)
                return

            # 2. Insert corrected D08 row with updated current_balance
            params = list(row)
            params[5] = new_balance  # current_balance is column index 5
            params.append(now_et().isoformat())  # last_updated

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
                       %s, %s, %s,
                       %s, %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s
                   )""",
                params,
            )

            # 3. Audit trail in session event log
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), "SYSTEM",
                    "BALANCE_UPDATE", ac_id, "",
                    json.dumps({"new_balance": new_balance}),
                ),
            )
            logger.info("D08 balance corrected for %s: %.2f", ac_id, new_balance)
    except Exception as exc:
        logger.error("Balance update failed for %s: %s", ac_id, exc, exc_info=True)


def _update_topstep_state(ac_id: str, topstep_state_json: str):
    """Update topstep_state in P3-D08 for an account."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), "SYSTEM",
                    "TOPSTEP_SOD_UPDATE", ac_id, "",
                    topstep_state_json,
                ),
            )
    except Exception as exc:
        logger.error("Topstep state update failed for %s: %s", ac_id, exc, exc_info=True)


def _log_reconciliation(ac_id: str, user_id: str, method: str,
                        system_balance: float | None, broker_balance: float | None,
                        mismatch: float | None):
    """Insert reconciliation result into P3-D19."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d19_reconciliation_log(
                       timestamp, account_id, user_id, method,
                       system_balance, broker_balance, mismatch,
                       auto_corrected
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(),
                    ac_id, user_id, method,
                    system_balance, broker_balance, mismatch,
                    mismatch is not None and mismatch > 1.0,
                ),
            )
    except Exception as exc:
        logger.error("Reconciliation log failed: %s", exc, exc_info=True)
