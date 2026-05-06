#!/usr/bin/env python3
"""Reset capital state to broker truth — Bug A unpause prerequisite (2026-04-29).

CONTEXT
-------
b7_position_monitor inflated D03 gross_pnl by `50 / true_point_value` for every
non-ES asset (Bug A). This propagated into D16 (capital silo) via
`_update_capital_and_cb`, producing a phantom 39.2 % silo drawdown that tripped
the kill switch even though the actual TopstepX cumulative PnL was ~−$2.7K.

PURPOSE
-------
After deploying the b7 Tier-1 fix, this script resets the **state tables** that
are downstream of D03 corruption so trading can resume from accurate state:

    1. D16 user_capital_silos.total_capital → broker truth
       (clears the silo drawdown alarm)
    2. D23 circuit_breaker_intraday          → fresh intraday baseline
       (clears L1/L2 phantom rho_j accumulation)
    3. (optional) D08 tsm_state.current_balance → broker truth
       (Cmd B8 SOD reconciliation rewrites this anyway at 19:00 ET; touching
        it manually is only needed if you need accurate TSM checks before SOD)

The script does NOT touch p3_d03_trade_outcome_log itself — historical PnL
inflation is corrected by `scripts/backfill_d03_pnl_inflation.py` (separate
script, requires reader-audit before live use).

Audit trail is preserved via `capital_history` JSON in D16 (append-only event
log) and via the natural append-only nature of D23 / D08 (LATEST-ON reads).

USAGE
-----
    # 1. Dry-run (default) — prints proposed changes without writing
    python3 scripts/reset_capital_state_to_broker_truth.py \\
        --user primary_user --account 20319811

    # 2. Apply (requires explicit flag — destructive op)
    python3 scripts/reset_capital_state_to_broker_truth.py \\
        --user primary_user --account 20319811 --apply

    # 3. Skip the optional D08 touch (recommended unless you need TSM checks
    #    accurate immediately, before next SOD reconciliation)
    python3 scripts/reset_capital_state_to_broker_truth.py \\
        --user primary_user --account 20319811 --apply --skip-d08

EXIT CODES
----------
    0  Success
    2  Configuration / argument error
    3  Broker reconciliation failed (cannot proceed)
    4  D16 / D08 / D23 write failed (partial state — see logs)
    5  Refusing to apply: broker balance and current D16 differ by less than
       the inflation threshold (suggests problem already resolved)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any

# Make sibling imports work when run via `python scripts/...` from repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.questdb_client import get_cursor  # noqa: E402
from shared.decimal_json import dumps_decimal, loads_decimal  # noqa: E402
from shared.constants import now_et  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reset_capital")


def _money(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _fmt(x: Any) -> str:
    return f"${_money(x):,.2f}"


# ---------------------------------------------------------------------------
# Broker truth fetch
# ---------------------------------------------------------------------------

def fetch_broker_balance(account_id: str) -> Decimal:
    """Pull the LIVE balance for the given TopstepX account.

    Raises RuntimeError if the account cannot be located.
    """
    from shared.topstep_client import get_topstep_client  # lazy: avoid in dry-run

    client = get_topstep_client()
    accounts = client.get_accounts(only_active=True)
    for acc in accounts:
        if str(acc.get("id")) == str(account_id):
            balance = acc.get("balance")
            if balance is None:
                raise RuntimeError(
                    f"Broker returned no balance for account {account_id}: {acc}"
                )
            return _money(balance)
    raise RuntimeError(
        f"Account {account_id} not found in broker active accounts; "
        f"saw {[a.get('id') for a in accounts]}"
    )


# ---------------------------------------------------------------------------
# D16 (user_capital_silos) reset
# ---------------------------------------------------------------------------

D16_FIELDS = [
    "user_id", "status", "role", "starting_capital", "total_capital",
    "accounts", "max_simultaneous_positions", "max_portfolio_risk_pct",
    "correlation_threshold", "user_kelly_ceiling",
    "capital_history", "telegram_chat_id", "created",
]


def read_d16_row(user_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT {", ".join(D16_FIELDS)}
                FROM p3_d16_user_capital_silos
                WHERE user_id = %s
                LATEST ON last_updated PARTITION BY user_id""",
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return dict(zip(D16_FIELDS, row))


def write_d16_row(d16: dict, new_total_capital: Decimal,
                  new_capital_history: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d16_user_capital_silos (
                   user_id, status, role, starting_capital, total_capital, accounts,
                   max_simultaneous_positions, max_portfolio_risk_pct,
                   correlation_threshold, user_kelly_ceiling,
                   capital_history, telegram_chat_id, created, last_updated
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (
                d16["user_id"], d16["status"], d16["role"],
                d16["starting_capital"], new_total_capital, d16["accounts"],
                d16["max_simultaneous_positions"], d16["max_portfolio_risk_pct"],
                d16["correlation_threshold"], d16["user_kelly_ceiling"],
                new_capital_history, d16["telegram_chat_id"], d16["created"],
            ),
        )


def build_capital_history_correction(
    existing_history_json: str | None,
    old_total: Decimal,
    new_total: Decimal,
    broker_balance: Decimal,
) -> str:
    try:
        history = loads_decimal(existing_history_json) if existing_history_json else []
    except (json.JSONDecodeError, ValueError):
        history = []
    if not isinstance(history, list):
        history = []
    history.append({
        "date": now_et().isoformat(),
        "event": "bug_a_capital_correction",
        "reason": (
            "Bug A multiplier inflation in b7_position_monitor wrote inflated "
            "gross_pnl into D03 → propagated into D16 total_capital. Reset to "
            "broker truth following b7 Tier-1 fix deployment."
        ),
        "old_total_capital": old_total,
        "new_total_capital": new_total,
        "broker_balance_used": broker_balance,
    })
    return dumps_decimal(history)


# ---------------------------------------------------------------------------
# D08 (tsm_state) reset — OPTIONAL
# ---------------------------------------------------------------------------

D08_FIELDS = [
    "account_id", "user_id", "name", "classification",
    "starting_balance", "current_balance", "current_drawdown",
    "daily_loss_used", "profit_target", "max_drawdown_limit",
    "max_daily_loss", "max_contracts", "scaling_plan",
    "commission_per_contract", "instrument_permissions",
    "overnight_allowed", "trading_hours", "margin_per_contract",
    "margin_buffer_pct", "pass_probability", "simulation_date",
    "risk_goal", "evaluation_end_date", "evaluation_stages",
    "topstep_optimisation", "topstep_params", "topstep_state",
    "fee_schedule", "payout_rules",
    "scaling_plan_active", "scaling_tier_micros",
]


def read_d08_row(account_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT {", ".join(D08_FIELDS)}
                FROM p3_d08_tsm_state
                WHERE account_id = %s
                LATEST ON last_updated PARTITION BY account_id""",
            (account_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return dict(zip(D08_FIELDS, row))


def write_d08_row(d08: dict, new_current_balance: Decimal,
                  new_current_drawdown: Decimal) -> None:
    fields_str = ", ".join(D08_FIELDS) + ", last_updated"
    placeholders = ", ".join(["%s"] * len(D08_FIELDS)) + ", now()"
    d08["current_balance"] = new_current_balance
    d08["current_drawdown"] = new_current_drawdown
    d08["daily_loss_used"] = Decimal("0")  # fresh day — Bug A daily_loss_used was inflated
    with get_cursor() as cur:
        cur.execute(
            f"INSERT INTO p3_d08_tsm_state ({fields_str}) "
            f"VALUES ({placeholders})",
            tuple(d08[f] for f in D08_FIELDS),
        )


# ---------------------------------------------------------------------------
# D23 (intraday CB state) reset
# ---------------------------------------------------------------------------

def reset_d23_intraday(account_id: str) -> None:
    """Zero today's per-session L_t, n_t and clear per-basket l_b/n_b.

    Per-session-budget update (2026-05-06): D23 is now keyed by
    (account_id, session_id). Insert one zero row for EVERY session in
    TRADING_DAY_SESSION_ORDER so the next session-open hook starts clean.
    effective_l_halt / effective_e_exposure / session_opened_at left NULL —
    will be populated by the orchestrator's _initialize_session_budget hook
    when each session actually opens.
    """
    from shared.sod_session_budget import (
        TRADING_DAY_SESSION_ORDER as _ORDER,
    )
    with get_cursor() as cur:
        for sid in _ORDER:
            cur.execute(
                """INSERT INTO p3_d23_circuit_breaker_intraday
                   (account_id, session_id, l_t, n_t, l_b, n_b,
                    effective_l_halt, effective_e_exposure, session_opened_at,
                    last_updated)
                   VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, now())""",
                (
                    account_id, int(sid), Decimal("0"), 0,
                    dumps_decimal({}), json.dumps({}),
                ),
            )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Reset D16/D23 (and optionally D08) to broker truth after "
                    "Bug A unpause.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--user", required=True, help="User ID (e.g. primary_user)")
    p.add_argument("--account", required=True,
                   help="TopstepX account ID (e.g. 20319811)")
    p.add_argument("--apply", action="store_true",
                   help="Actually write changes. Without this, runs as dry-run.")
    p.add_argument("--skip-d08", action="store_true",
                   help="Skip the optional D08 current_balance reset (Cmd B8 "
                        "SOD reconciliation will fix it at 19:00 ET anyway).")
    p.add_argument("--skip-d23", action="store_true",
                   help="Skip the D23 intraday reset (only do this if intraday "
                        "is already clean).")
    p.add_argument("--inflation-threshold", type=float, default=1000.0,
                   help="Refuse to apply if |broker_balance - current_total| < "
                        "this dollar amount (default $1000). Sanity guard.")
    args = p.parse_args(argv)

    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=" * 72)
    logger.info(" reset_capital_state_to_broker_truth — %s", mode)
    logger.info(" user=%s  account=%s", args.user, args.account)
    logger.info("=" * 72)

    # 1. Fetch broker truth
    try:
        broker_balance = fetch_broker_balance(args.account)
    except Exception as exc:
        logger.error("FAILED to fetch broker balance: %s", exc)
        return 3
    logger.info("Broker truth balance for %s: %s", args.account, _fmt(broker_balance))

    # 2. Read current state
    d16 = read_d16_row(args.user)
    if d16 is None:
        logger.error("D16 row not found for user_id=%s", args.user)
        return 3
    old_total = _money(d16["total_capital"])
    starting = _money(d16["starting_capital"])
    delta_d16 = old_total - broker_balance
    logger.info("D16  starting_capital = %s", _fmt(starting))
    logger.info("D16  current  total_capital = %s", _fmt(old_total))
    logger.info("D16  proposed total_capital = %s   (delta from current: %s)",
                _fmt(broker_balance), _fmt(-delta_d16))

    if abs(delta_d16) < Decimal(str(args.inflation_threshold)):
        logger.warning(
            "Refusing to apply: |delta| %s < threshold %s. "
            "If you really want to do this, lower --inflation-threshold.",
            _fmt(delta_d16), _fmt(args.inflation_threshold),
        )
        if args.apply:
            return 5
        logger.info("Continuing in DRY-RUN for visibility.")

    d08 = read_d08_row(args.account) if not args.skip_d08 else None
    if d08 is not None:
        old_d08_balance = _money(d08["current_balance"])
        old_d08_drawdown = _money(d08["current_drawdown"])
        logger.info("D08  current  current_balance = %s", _fmt(old_d08_balance))
        logger.info("D08  proposed current_balance = %s", _fmt(broker_balance))
        # peak = max(starting, prior_peak); we approximate peak as
        # max(starting_balance, broker_balance) since starting balance is the
        # known floor and any prior drawdown was measured against starting.
        new_drawdown = max(Decimal("0"), starting - broker_balance)
        logger.info("D08  current  current_drawdown = %s", _fmt(old_d08_drawdown))
        logger.info("D08  proposed current_drawdown = %s   (= max(0, start-bal))",
                    _fmt(new_drawdown))

    if not args.skip_d23:
        logger.info("D23  proposed: reset l_t=0, n_t=0, l_b={}, n_b={}")

    if not args.apply:
        logger.info("=" * 72)
        logger.info(" DRY-RUN complete. Re-run with --apply to write.")
        logger.info("=" * 72)
        return 0

    # 3. Apply
    try:
        new_history = build_capital_history_correction(
            d16.get("capital_history"), old_total, broker_balance, broker_balance,
        )
        write_d16_row(d16, broker_balance, new_history)
        logger.info("D16 row written.")

        if d08 is not None:
            new_drawdown = max(Decimal("0"), starting - broker_balance)
            write_d08_row(d08, broker_balance, new_drawdown)
            logger.info("D08 row written.")

        if not args.skip_d23:
            reset_d23_intraday(args.account)
            logger.info("D23 row written (zeroed intraday).")
    except Exception as exc:
        logger.exception("Write failed: %s", exc)
        return 4

    logger.info("=" * 72)
    logger.info(" APPLY complete. Verify via QuestDB web console:")
    logger.info("   SELECT total_capital FROM p3_d16_user_capital_silos "
                "WHERE user_id='%s' LATEST ON last_updated PARTITION BY user_id;",
                args.user)
    logger.info("   SELECT current_balance, current_drawdown FROM p3_d08_tsm_state "
                "WHERE account_id='%s' LATEST ON last_updated PARTITION BY account_id;",
                args.account)
    logger.info("   SELECT l_t, n_t FROM p3_d23_circuit_breaker_intraday "
                "WHERE account_id='%s' LATEST ON last_updated PARTITION BY account_id;",
                args.account)
    logger.info("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
