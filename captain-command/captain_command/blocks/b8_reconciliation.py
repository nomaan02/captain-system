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

from shared.questdb_client import get_cursor, qexecute
from shared.journal import write_checkpoint
from shared.constants import SOD_RESET_HOUR, SOD_RESET_MINUTE, now_et
from shared.json_helpers import parse_json, parse_json_decimal
from shared.decimal_json import dumps_decimal
from shared.decimal_boundary import as_money, as_money_or_none, to_float
from decimal import Decimal

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
            if ac.get("topstep_optimisation"):
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

        # Phase 2 boundary discipline: broker API returns float, Phase A
        # migration made system_balance Decimal — coerce both at the boundary
        # so the comparison and the GUI/log formatters never touch mixed
        # Decimal/float arithmetic.
        broker_balance = as_money_or_none(broker_status.get("balance"))
        system_balance = as_money_or_none(ac.get("current_balance"))

        if broker_balance is None or system_balance is None:
            return

        mismatch = abs(broker_balance - system_balance)

        if mismatch > Decimal("1.00"):
            # Auto-correct from broker (trusted source)
            _update_account_balance(ac_id, broker_balance)

            gui_push_fn(user_id, {
                "type": "notification",
                "priority": "MEDIUM",
                "message": (
                    f"Account {ac_id} balance reconciled: "
                    f"system ${to_float(system_balance):,.2f} → "
                    f"broker ${to_float(broker_balance):,.2f} "
                    f"(diff: ${to_float(mismatch):,.2f})"
                ),
                "source": "RECONCILIATION",
                "timestamp": now_et().isoformat(),
            })

            logger.info("Balance corrected for %s: %.2f → %.2f (diff: %.2f)",
                        ac_id, to_float(system_balance),
                        to_float(broker_balance), to_float(mismatch))

        _log_reconciliation(ac_id, user_id, "API",
                            to_float(system_balance),
                            to_float(broker_balance),
                            to_float(mismatch))

    except Exception as exc:
        # Phase 2 lockdown: was previously the silent except path that hid
        # the Decimal/float TypeError for weeks. Now logs CRITICAL with full
        # traceback and pushes a GUI alert so reconciliation failures surface
        # immediately instead of silently returning.
        logger.critical(
            "CMD-B8: CRITICAL reconciliation failure for account %s: %s",
            ac_id, exc, exc_info=True,
        )
        try:
            gui_push_fn(user_id, {
                "type": "notification",
                "priority": "CRITICAL",
                "message": (
                    f"Reconciliation FAILED for account {ac_id}: {exc}. "
                    "Manual broker-balance check required before next session."
                ),
                "source": "RECONCILIATION_FAILURE",
                "timestamp": now_et().isoformat(),
            })
        except Exception as alert_exc:
            logger.error(
                "CMD-B8: failed to push reconciliation-failure alert: %s",
                alert_exc,
            )


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
# TSM config disk loader (authoritative source for topstep_params)
# ---------------------------------------------------------------------------

_TSM_PARAMS_CACHE: dict[str, dict] = {}


def _load_topstep_params_from_config(tsm_name: str) -> dict:
    """Read topstep_params from the TSM JSON config file matching *tsm_name*.

    Uses a module-level cache so the disk is only read once per process
    lifetime. Returns empty dict if no match found.
    """
    if not tsm_name:
        return {}

    if not _TSM_PARAMS_CACHE:
        import os as _os
        from captain_command.blocks.b4_tsm_manager import TSM_CONFIG_DIR
        if _os.path.isdir(TSM_CONFIG_DIR):
            for fn in sorted(_os.listdir(TSM_CONFIG_DIR)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(_os.path.join(TSM_CONFIG_DIR, fn)) as _f:
                        disk_tsm = json.load(_f)
                    name = disk_tsm.get("name", "")
                    raw_params = disk_tsm.get("topstep_params", {})
                    if name and raw_params:
                        _TSM_PARAMS_CACHE[name] = {
                            k: Decimal(str(v))
                            for k, v in raw_params.items()
                            if not k.startswith("_") and isinstance(v, (int, float, str))
                        }
                except Exception:
                    continue

    result = _TSM_PARAMS_CACHE.get(tsm_name, {})
    if result:
        logger.debug("topstep_params from config file for '%s': %s", tsm_name, result)
    return result


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
        ts_state = parse_json_decimal(ac.get("topstep_state", "{}") or "{}", {})

        # Authoritative topstep_params: read from TSM config file on disk,
        # matched by TSM name.  D08 rows may hold stale copies from when the
        # account was first linked; the JSON file is always the source of truth.
        ts_params = _load_topstep_params_from_config(ac.get("tsm_name", ""))
        if not ts_params:
            ts_params_nested = ts_state.get("topstep_params", {})
            if isinstance(ts_params_nested, str):
                ts_params_nested = parse_json_decimal(ts_params_nested, {})
            ts_params_col = parse_json_decimal(ac.get("topstep_params", "{}") or "{}", {})
            ts_params = ts_params_nested if ts_params_nested else ts_params_col

        payout_rules = parse_json_decimal(ac.get("payout_rules", "{}") or "{}", {})
        fee_schedule = parse_json_decimal(ac.get("fee_schedule", "{}") or "{}", {})

        A = Decimal(str(ac.get("current_balance", 0)))
        starting = Decimal(str(ac.get("starting_balance", 150000)))
        profit = A - starting

        if A <= 0:
            logger.warning("Account %s has non-positive balance: %s", ac_id, A)
            return

        p = Decimal(str(ts_params.get("p", 0.005)))
        e = Decimal(str(ts_params.get("e", 0.01)))
        c = Decimal(str(ts_params.get("c", 0.5)))
        logger.info("SOD params for %s: c=%s e=%s p=%s (ts_params keys: %s)",
                     ac_id, c, e, p, list(ts_params.keys()))

        fees_by_inst = fee_schedule.get("fees_by_instrument", {})
        phi = Decimal("0")
        if fees_by_inst:
            es_fees = fees_by_inst.get("ES", {})
            if isinstance(es_fees, dict):
                phi = Decimal(str(es_fees.get("round_turn", 0)))

        mdd_limit = Decimal(str(ac.get("max_drawdown_limit", 4500)))
        f_A = mdd_limit / A

        R_eff = p * f_A + phi / A

        denom = mdd_limit * p + phi
        N = math.floor((e * A / denom)) if denom > 0 else 0

        E = e * A
        L_halt = c * e * A

        max_per = payout_rules.get("max_per_payout", Decimal("5000"))
        if not isinstance(max_per, Decimal):
            max_per = Decimal(str(max_per))
        max_pct = Decimal("0.5")
        commission_rate = payout_rules.get("commission_rate", Decimal("0.10"))
        if not isinstance(commission_rate, Decimal):
            commission_rate = Decimal(str(commission_rate))
        tier_floor = payout_rules.get("scaling_tier_floor", Decimal("4500"))
        if not isinstance(tier_floor, Decimal):
            tier_floor = Decimal(str(tier_floor))

        W = min(max_per, max_pct * max(A - starting, Decimal("0")))

        balance_after_payout = A - W
        g_A = (mdd_limit / balance_after_payout) if balance_after_payout > 0 else Decimal("0")

        if ac.get("scaling_plan_active"):
            from captain_command.blocks.b4_tsm_manager import get_scaling_tier
            scaling = get_scaling_tier(ac, float(profit))
            scaling_plan = ts_state.get("scaling_plan", [])
            scaling_tier_label = scaling.get("tier_label", "")
            current_max_micros = scaling.get("max_micros", 0)
            profit_to_next_tier = scaling.get("profit_to_next_tier", 0)
            next_tier_label = scaling.get("next_tier_label", "")
            tier_after_payout = scaling.get("tier_label", "")
        else:
            scaling = {}
            scaling_plan = []
            scaling_tier_label = ""
            current_max_micros = 0
            profit_to_next_tier = 0
            next_tier_label = ""
            tier_after_payout = ""

        q6 = Decimal("0.000001")
        q2 = Decimal("0.01")

        # Per-session budget allocation (2026-05-06): partition L_halt and E
        # across HMM-weighted sessions so a heavy NY day no longer starves
        # APAC's NKD via the abs(L_t) > L_halt cascade. See
        # docs2/audits/2026-05-06_per_session_budget_design.md and Isaac's
        # 15_Topstep_Optimisation_Functions sec 4.4.4.
        from shared.sod_session_budget import (
            session_budget_shares as _session_budget_shares,
        )
        hmm_state = _load_hmm_opportunity_state_for_sod()
        shares = _session_budget_shares(hmm_state)
        # Per-session N_max_trades: floor((alpha_w * E) / (MDD*p + phi))
        per_session: dict[str, dict] = {}
        for sess_key, share in shares.items():
            sess_E = (E * share)
            sess_L_halt = (L_halt * share)
            sess_N = (
                math.floor(sess_E / denom) if denom > 0 else 0
            )
            per_session[sess_key] = {
                "L_halt": sess_L_halt.quantize(q2),
                "E_daily_exposure": sess_E.quantize(q2),
                "N_max_trades": sess_N,
                "share": share.quantize(q6),
            }
        computed = {
            "topstep_params": ts_params,
            "payout_rules": payout_rules,
            "fee_schedule": fee_schedule,
            "scaling_plan": scaling_plan,
            "computed_sod": {
                "f_A": f_A.quantize(q6),
                "R_eff": R_eff.quantize(q6),
                "N_max_trades": N,
                "E_daily_exposure": E.quantize(q2),
                "L_halt": L_halt.quantize(q2),
                # Per-session breakdown (consumed by Online B5C/B4 + replay)
                "session": per_session,
                "session_shares_source": (
                    "HMM_FULL" if (hmm_state and not hmm_state.get("cold_start", True)
                                   and hmm_state.get("n_observations", 0) >= 60)
                    else "HMM_BLENDED" if (hmm_state and not hmm_state.get("cold_start", True)
                                           and hmm_state.get("n_observations", 0) >= 20)
                    else "EQUAL_COLD_START"
                ),
                "W_max_payout": W.quantize(q2),
                "g_A_post_payout_mdd": g_A.quantize(q6),
                "computed_at": now_et().isoformat(),
            },
            "scaling_tier": scaling_tier_label,
            "current_tier_label": scaling_tier_label,
            "current_max_micros": current_max_micros,
            "profit_to_next_tier": profit_to_next_tier,
            "next_tier_label": next_tier_label,
            "payouts_remaining": payout_rules.get("max_total_payouts", 5),
            "tier_after_payout": tier_after_payout,
        }

        _persist_topstep_state_to_d08(ac_id, dumps_decimal(computed))

        logger.info(
            "SOD Topstep params computed for %s: f(A)=%.4f N=%d E=%.2f L_halt=%.2f "
            "per-session L_halt: NY=%.2f LON=%.2f APAC=%.2f",
            ac_id, float(f_A), N, float(E), float(L_halt),
            float(per_session.get("NY", {}).get("L_halt", 0)),
            float(per_session.get("LON", {}).get("L_halt", 0)),
            float(per_session.get("APAC", {}).get("L_halt", 0)),
        )

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
                                  profit: Any, W: Any,
                                  commission_rate: Any, tier_floor: Any,
                                  scaling: dict, gui_push_fn: Callable,
                                  notify_fn: Callable | None):
    """Check if a payout is recommended using 4-step spec decision.

    Per Payout_Rules.md:
    Step 1: Tier-preserving max
    Step 2: Cap withdrawal to tier-preserving max
    Step 3: Net after commission check (>= $500)
    Step 4: MDD% impact check
    """
    profit_d = profit if isinstance(profit, Decimal) else Decimal(str(profit))
    W_d = W if isinstance(W, Decimal) else Decimal(str(W))
    cr = (
        commission_rate if isinstance(commission_rate, Decimal)
        else Decimal(str(commission_rate))
    )
    tf = tier_floor if isinstance(tier_floor, Decimal) else Decimal(str(tier_floor))

    # E7: Account-type-aware payout rules
    account_type = ac.get("account_type", "PROP_XFA")
    if account_type == "BROKER_LIVE":
        cr = Decimal("0")
        winning_days = ac.get("winning_days", 0)
        if winning_days < 30:
            return

    tier_preserving_max = profit_d - tf
    if tier_preserving_max <= 0:
        return

    withdraw_amount = min(W_d, tier_preserving_max)

    net_after_commission = withdraw_amount * (Decimal("1") - cr)
    if net_after_commission < Decimal("500"):
        return

    A = Decimal(str(ac.get("current_balance", 0)))
    mdd_limit = Decimal(str(ac.get("max_drawdown_limit", 4500)))
    f_target_max = Decimal(str(_get_d17_param("f_target_max", 0.03)))

    A_post = A - withdraw_amount
    f_post = Decimal("0")
    if A_post > 0:
        f_post = mdd_limit / A_post
        if f_post > f_target_max:
            withdraw_amount = A - (mdd_limit / f_target_max)
            withdraw_amount = min(withdraw_amount, tier_preserving_max, W_d)
            withdraw_amount = max(withdraw_amount, Decimal("0"))
            net_after_commission = withdraw_amount * (Decimal("1") - cr)
            if net_after_commission < Decimal("500"):
                return
            f_post = (
                mdd_limit / (A - withdraw_amount)
                if (A - withdraw_amount) > 0 else Decimal("0")
            )
    else:
        return

    profit_after = profit_d - withdraw_amount
    tsm_name = ac.get("tsm_name", ac_id)
    payouts_remaining = scaling.get("payouts_remaining", "N/A")

    message = (
        f"PAYOUT RECOMMENDED: {tsm_name}. "
        f"Withdraw ${withdraw_amount:,.0f} "
        f"(receive ${net_after_commission:,.0f} after {float(cr) * 100:.0f}% commission). "
        f"Profit stays at ${profit_after:,.0f} → tier {scaling.get('tier_label', 'maintained')}. "
        f"Post-payout MDD%: {float(f_post):.4f}. Payouts remaining: {payouts_remaining}."
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
            "payout_amount": float(withdraw_amount.quantize(Decimal("0.01"))),
            "net_amount": float(net_after_commission.quantize(Decimal("0.01"))),
            "profit_after": float(profit_after.quantize(Decimal("0.01"))),
            "tier_after": scaling.get("tier_label", ""),
            "f_post": float(f_post.quantize(Decimal("0.000001"))),
            "payouts_remaining": payouts_remaining,
        },
    }

    gui_push_fn(user_id, notif)

    if notify_fn:
        notify_fn(notif)

    logger.info(
        "Payout recommendation sent: %s $%s for user %s",
        ac_id, withdraw_amount, user_id,
    )


# ---------------------------------------------------------------------------
# Daily counter resets
# ---------------------------------------------------------------------------


def _reset_daily_counters():
    """Reset daily loss counters and per-session intraday CB state for all accounts.

    Called at 19:00 EST as part of reconciliation. Two responsibilities:

    1. **D08.daily_loss_used and D08.current_drawdown reset** — historic bug:
       this used to only write a session_event_log row claiming the reset had
       happened, while D08 fields stayed monotonically increasing. Fixed by
       mirroring the read-modify-insert pattern from ``_update_account_balance``
       and writing a fresh D08 row with ``daily_loss_used = 0``. (Per Isaac's
       spec: ``current_drawdown`` is a TRAILING peak-to-current metric, NOT a
       daily counter, so we leave it untouched here. Only ``daily_loss_used``
       resets daily.)

    2. **D23 intraday CB state reset** — per-session zero rows. After the
       per-session-budget refactor (2026-05-06), D23 is keyed by
       ``(account_id, session_id)``. We insert one zero row per (account,
       session) pair so the next session-open hook starts from a clean slate.
       The new row carries ``effective_l_halt = NULL`` and
       ``effective_e_exposure = NULL`` (populated later by the orchestrator's
       ``_initialize_session_budget`` hook at the actual session-open time).

    Failure of either step does not raise — both steps log + alert and continue
    so reconciliation does not block on a single account failing.
    """
    from shared.constants import SESSION_IDS as _SESSION_IDS
    from shared.sod_session_budget import (
        TRADING_DAY_SESSION_ORDER as _TRADING_DAY_SESSION_ORDER,
    )

    accounts: list = []
    try:
        with get_cursor() as cur:
            # Forensic audit trail (kept from prior impl).
            qexecute(cur,
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), "SYSTEM",
                    "DAILY_RESET", "RESET-" + now_et().strftime("%Y%m%d"),
                    "", json.dumps({"reset_type": "daily_counters"}),
                ),
            )

            # Step 1: actually reset daily_loss_used in D08 for every account.
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
                   LATEST ON last_updated PARTITION BY account_id"""
            )
            d08_rows = cur.fetchall()
            for d08 in d08_rows:
                if not d08 or not d08[0]:
                    continue
                params = list(d08)
                # Index 7 = daily_loss_used (per the SELECT order above).
                # Set to Decimal("0") so the column type stays DECIMAL(18,2)
                # and the row is type-pure.
                params[7] = Decimal("0")
                params.append(now_et().isoformat())  # last_updated
                qexecute(cur,
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
                accounts.append(d08[0])

            # Step 2: per-session D23 zero rows. One row per (account, session)
            # for each session in TRADING_DAY_SESSION_ORDER. The session_open
            # hook in the orchestrator will populate effective_l_halt /
            # effective_e_exposure / session_opened_at when each session
            # actually opens.
            for ac_id in accounts:
                for sid in _TRADING_DAY_SESSION_ORDER:
                    qexecute(cur,
                        """INSERT INTO p3_d23_circuit_breaker_intraday(
                               account_id, session_id, l_t, n_t,
                               l_b, n_b,
                               effective_l_halt, effective_e_exposure,
                               session_opened_at, last_updated
                           ) VALUES(%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s)""",
                        (
                            ac_id, int(sid),
                            Decimal("0"), 0,
                            dumps_decimal({}), json.dumps({}),
                            now_et().isoformat(),
                        ),
                    )

        logger.info(
            "Daily counters reset: D08.daily_loss_used=0 for %d accounts; "
            "D23 zero rows written for %d accounts × %d sessions",
            len(accounts), len(accounts), len(_TRADING_DAY_SESSION_ORDER),
        )

    except Exception as exc:
        logger.error("Daily counter reset failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_hmm_opportunity_state_for_sod() -> dict | None:
    """Load HMM opportunity state from P3-D26 for the SOD per-session
    budget allocator. Returns ``None`` if HMM has never been trained, in
    which case ``shared.sod_session_budget.session_budget_shares`` will fall
    back to equal 1/3 weights per session.

    Mirrors ``b5_trade_selection._load_hmm_opportunity_state`` but kept
    local to B8 so the SOD computation does not import from the Online
    process tree.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT opportunity_weights, n_observations, cold_start
                   FROM p3_d26_hmm_opportunity_state
                   ORDER BY last_updated DESC LIMIT 1"""
            )
            row = cur.fetchone()
        if row is None:
            return None
        weights_raw = row[0]
        weights: dict = {}
        if weights_raw:
            try:
                weights = parse_json(weights_raw, {}) or {}
            except Exception:
                weights = {}
        return {
            "opportunity_weights": weights,
            "n_observations": int(row[1] or 0),
            "cold_start": bool(row[2]) if row[2] is not None else True,
        }
    except Exception as exc:
        logger.warning(
            "CMD-B8: failed to load D26 HMM opportunity state for SOD "
            "session-budget allocator (%s) — falling back to equal weights",
            exc,
        )
        return None


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
                """SELECT account_id, user_id, name,
                          current_balance, starting_balance,
                          max_drawdown_limit, max_daily_loss,
                          topstep_optimisation, topstep_state,
                          scaling_plan_active,
                          topstep_params, fee_schedule, payout_rules
                   FROM p3_d08_tsm_state
                   LATEST ON last_updated PARTITION BY account_id
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
                    "topstep_params": r[10] or "{}",
                    "fee_schedule": r[11] or "{}",
                    "payout_rules": r[12] or "{}",
                })
            return results
    except Exception as exc:
        logger.error("Failed to fetch accounts: %s", exc, exc_info=True)
    return []


def _update_account_balance(ac_id: str, new_balance: Any):
    """Update account balance in P3-D08 (via insert — QuestDB append-only).

    Reads the latest D08 snapshot for the account, replaces current_balance
    with *new_balance*, and appends a corrected row.  Also writes an audit
    entry to the session event log.
    """
    new_bal = new_balance if isinstance(new_balance, Decimal) else Decimal(str(new_balance))
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
            params[5] = new_bal  # current_balance is column index 5
            params.append(now_et().isoformat())  # last_updated

            qexecute(cur,
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
            qexecute(cur,
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), "SYSTEM",
                    "BALANCE_UPDATE", ac_id, "",
                    dumps_decimal({"new_balance": new_bal}),
                ),
            )
            logger.info("D08 balance corrected for %s: %s", ac_id, new_bal)
    except Exception as exc:
        logger.error("Balance update failed for %s: %s", ac_id, exc, exc_info=True)


def _persist_topstep_state_to_d08(ac_id: str, topstep_state_json: str):
    """Persist computed topstep_state to P3-D08 (append-only row rewrite).

    QuestDB is append-only, so we mirror the ``_update_account_balance``
    pattern: read the latest D08 snapshot for the account, replace the
    ``topstep_state`` column (index 26 in the canonical 31-column SELECT),
    and INSERT a fresh row with ``last_updated = now_et()``.

    Also writes a forensic audit entry to ``p3_session_event_log`` with
    ``event_type = "TOPSTEP_SOD_UPDATE"``.
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
                logger.warning(
                    "No D08 row for account %s — cannot persist topstep_state", ac_id,
                )
                return

            # 2. Insert corrected D08 row with updated topstep_state (col idx 26)
            params = list(row)
            params[26] = topstep_state_json  # topstep_state
            params.append(now_et().isoformat())  # last_updated

            qexecute(cur,
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

            # 3. Forensic audit trail in session event log (kept from prior impl)
            qexecute(cur,
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    now_et().isoformat(), "SYSTEM",
                    "TOPSTEP_SOD_UPDATE", ac_id, "",
                    topstep_state_json,
                ),
            )
            logger.info("D08 topstep_state persisted for %s", ac_id)
    except Exception as exc:
        logger.error("Topstep state persistence failed for %s: %s", ac_id, exc, exc_info=True)


def _log_reconciliation(ac_id: str, user_id: str, method: str,
                        system_balance: float | None, broker_balance: float | None,
                        mismatch: float | None):
    """Insert reconciliation result into P3-D19."""
    try:
        with get_cursor() as cur:
            qexecute(cur,
                """INSERT INTO p3_d19_reconciliation_log(
                       recon_id, account_id, user_id, source,
                       mismatches, corrected, status, ts
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    f"{ac_id}_{now_et().strftime('%Y%m%d_%H%M%S')}",
                    ac_id, user_id, method,
                    json.dumps({"system_balance": system_balance,
                                "broker_balance": broker_balance,
                                "mismatch": mismatch}),
                    mismatch is not None and mismatch > 1.0,
                    "corrected" if (mismatch is not None and mismatch > 1.0) else "ok",
                    now_et().isoformat(),
                ),
            )
    except Exception as exc:
        logger.error("Reconciliation log failed: %s", exc, exc_info=True)
