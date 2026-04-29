#!/usr/bin/env python3
"""D08 minimal-repro probe.

The growth bisection in debug_d08_bisect.py showed the INSERT flips from OK
to FAIL the moment ``starting_balance`` (the first DECIMAL column) is added.
HTTP returns 500 with error="" and position=0 — that's an unhandled
server exception in QuestDB, not a normal parse error.

But D16 ``user_capital_silos`` INSERTs with the same '150000' quoted-string
pattern work fine in production (bootstrap_production.py succeeds). So the
trigger is more nuanced than "quoted-string DECIMAL".

This probe pins down two questions:

  Q1: Does the value FORMAT matter?  '1' (quoted) vs 1 vs 1.0 vs cast.
  Q2: Does the column SHAPE matter?  3-col vs 4-col vs 5-col combos.
  Q3: Cross-check D16 baseline — same value format, see what works there.

Outcome will be one of:
  - A specific value format works → fix is to wrap Decimal differently
  - A specific column adjacency triggers it → may need an INSERT rewrite
  - All formats fail → likely a real QuestDB bug; we file a workaround
    (e.g. drop and recreate the table, or use ILP for D08)

Run:

    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/debug_d08_minimal_repro.py
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote

from shared.questdb_client import get_cursor  # noqa: F401  (registers adapters)

import urllib.request
import urllib.error

QUESTDB_HTTP = f"http://{os.environ.get('QUESTDB_HOST', 'questdb')}:9000"


def http_exec(sql: str) -> tuple[int, str, str]:
    """Returns (status, error_text, full_body)."""
    url = f"{QUESTDB_HTTP}/exec?query={quote(sql, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, "", body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body).get("error", "")
            pos = json.loads(body).get("position")
            err = f"{err} (pos={pos})"
        except Exception:
            err = body[:200]
        return exc.code, err, body
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}", ""


def run(label: str, sql: str):
    status, err, body = http_exec(sql)
    marker = "OK  " if status == 200 else "FAIL"
    print(f"  {marker} HTTP={status:<4}  {label}")
    print(f"        sql: {sql[:160]}{'...' if len(sql) > 160 else ''}")
    if status != 200:
        print(f"        err: {err[:200]}")
    print()


def section(title: str):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    section("Q1 — Value format for starting_balance in a known-failing 5-col INSERT")
    base = ("INSERT INTO p3_d08_tsm_state(account_id, user_id, name, "
            "classification, starting_balance, last_updated) "
            "VALUES('FMT_PROBE_{n}', 'u', 'n', '{{}}', {val}, now())")
    for i, val in enumerate([
        "'1'",                              # current production format (Decimal adapter)
        "1",                                # bare integer
        "1.0",                              # bare double
        "1.00",                             # bare double with scale
        "cast('1' as DECIMAL(18,2))",       # explicit cast
        "cast('1.00' as DECIMAL(18,2))",
        "1.0::DECIMAL(18,2)",               # PG-style cast
        "NULL",                             # NULL literal
    ]):
        sql = base.format(n=i, val=val)
        run(f"starting_balance = {val}", sql)

    section("Q2 — Column shape: which combo flips OK -> FAIL?")
    combos = [
        ("3-col (account_id, starting_balance, last_updated)",
         "INSERT INTO p3_d08_tsm_state(account_id, starting_balance, last_updated) "
         "VALUES('SHAPE_3a', '100', now())"),
        ("4-col + user_id BEFORE starting_balance",
         "INSERT INTO p3_d08_tsm_state(account_id, user_id, starting_balance, last_updated) "
         "VALUES('SHAPE_4a', 'u', '100', now())"),
        ("4-col + name (STRING) BEFORE starting_balance",
         "INSERT INTO p3_d08_tsm_state(account_id, name, starting_balance, last_updated) "
         "VALUES('SHAPE_4b', 'n', '100', now())"),
        ("4-col + classification (STRING) BEFORE starting_balance",
         "INSERT INTO p3_d08_tsm_state(account_id, classification, starting_balance, last_updated) "
         "VALUES('SHAPE_4c', '{}', '100', now())"),
        ("5-col: account_id, user_id, name, starting_balance, last_updated (no classification)",
         "INSERT INTO p3_d08_tsm_state(account_id, user_id, name, starting_balance, last_updated) "
         "VALUES('SHAPE_5a', 'u', 'n', '100', now())"),
        ("5-col: account_id, user_id, classification, starting_balance, last_updated (no name)",
         "INSERT INTO p3_d08_tsm_state(account_id, user_id, classification, starting_balance, last_updated) "
         "VALUES('SHAPE_5b', 'u', '{}', '100', now())"),
        ("Reorder: starting_balance LAST, last_updated separate",
         "INSERT INTO p3_d08_tsm_state(account_id, user_id, name, classification, last_updated, starting_balance) "
         "VALUES('SHAPE_5c', 'u', 'n', '{}', now(), '100')"),
        ("starting_balance moved to position 1 (before account_id) — invalid because account_id is the symbol but try anyway",
         "INSERT INTO p3_d08_tsm_state(starting_balance, account_id, user_id, name, classification, last_updated) "
         "VALUES('100', 'SHAPE_5d', 'u', 'n', '{}', now())"),
    ]
    for label, sql in combos:
        run(label, sql)

    section("Q3 — D16 baseline (DECIMAL inside a multi-column INSERT — known to work)")
    run("D16 7-col with quoted DECIMAL",
        "INSERT INTO p3_d16_user_capital_silos("
        "user_id, status, role, starting_capital, total_capital, accounts, last_updated) "
        "VALUES('REPRO_TEST', 'ACTIVE', 'ADMIN', '100', '100', '[]', now())")

    section("Q4 — D08 with EVERY column listed, in EXACT schema order")
    # Every one of D08's 32 columns, in declared order, with safe values.
    # If THIS works, the bug is column-subset-related, not data-related.
    full = (
        "INSERT INTO p3_d08_tsm_state("
        "account_id, user_id, name, classification, "
        "starting_balance, current_balance, current_drawdown, daily_loss_used, "
        "profit_target, max_drawdown_limit, max_daily_loss, max_contracts, "
        "scaling_plan, commission_per_contract, instrument_permissions, "
        "overnight_allowed, trading_hours, margin_per_contract, "
        "margin_buffer_pct, pass_probability, simulation_date, risk_goal, "
        "evaluation_end_date, evaluation_stages, topstep_optimisation, "
        "topstep_params, topstep_state, fee_schedule, payout_rules, "
        "scaling_plan_active, scaling_tier_micros, last_updated"
        ") VALUES("
        "'FULL_PROBE', 'u', 'n', '{}', "
        "'1', '1', '1', '0', "
        "'1', '1', NULL, 1, "
        "'', '1', '', "
        "false, '', '1', "
        "0.0, 0.0, NULL, '', "
        "NULL, '', false, "
        "'{}', '{}', '{}', '{}', "
        "false, 1, now())"
    )
    run("ALL 32 cols in schema order", full)

    section("Q5 — repeat the failing 21-col INSERT but with EVERY DECIMAL value bare-numeric (no quotes)")
    bare = (
        "INSERT INTO p3_d08_tsm_state("
        "account_id, user_id, name, classification, "
        "starting_balance, current_balance, max_drawdown_limit, max_daily_loss, "
        "daily_loss_used, profit_target, max_contracts, commission_per_contract, "
        "overnight_allowed, trading_hours, risk_goal, topstep_optimisation, "
        "scaling_plan_active, topstep_state, fee_schedule, payout_rules, last_updated"
        ") VALUES("
        "'BARE_PROBE', 'u', 'n', '{}', "
        "1.0, 1.0, 1.0, NULL, "
        "0.0, 1.0, 1, 1.0, "
        "false, '', '', false, "
        "false, '{}', '{}', '{}', now())"
    )
    run("21-col, DECIMAL values bare-numeric", bare)

    section("Q6 — same 21-col INSERT but with cast('x' AS DECIMAL(18,2)) for every DECIMAL")
    cast_form = (
        "INSERT INTO p3_d08_tsm_state("
        "account_id, user_id, name, classification, "
        "starting_balance, current_balance, max_drawdown_limit, max_daily_loss, "
        "daily_loss_used, profit_target, max_contracts, commission_per_contract, "
        "overnight_allowed, trading_hours, risk_goal, topstep_optimisation, "
        "scaling_plan_active, topstep_state, fee_schedule, payout_rules, last_updated"
        ") VALUES("
        "'CAST_PROBE', 'u', 'n', '{}', "
        "cast('1' as DECIMAL(18,2)), cast('1' as DECIMAL(18,2)), "
        "cast('1' as DECIMAL(18,2)), NULL, "
        "cast('0' as DECIMAL(18,2)), cast('1' as DECIMAL(18,2)), 1, "
        "cast('1' as DECIMAL(18,2)), "
        "false, '', '', false, "
        "false, '{}', '{}', '{}', now())"
    )
    run("21-col, DECIMAL values via explicit cast", cast_form)


if __name__ == "__main__":
    main()
