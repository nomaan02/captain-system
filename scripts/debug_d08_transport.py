#!/usr/bin/env python3
"""D08 transport-layer probe.

Goal: variant E in debug_d08_insert.py proved that *no individual parameter*
causes the failure — every column-replacement still produces the same empty
``DatabaseError`` at statement_position 1.  That isolates the failure to the
SQL transport, not the data.

This script tests four orthogonal hypotheses in one shot:

    1. PG wire, exact mogrified bytes (current production path)
    2. PG wire, mogrified bytes decoded to str
    3. PG wire, single-line version of the SQL (no embedded newlines)
    4. HTTP REST API (/exec) with the *same* literal SQL — QuestDB
       returns a real, non-empty error message via HTTP

It uses ``account_id = 'PROBE_D08_TEST'`` to avoid colliding with whatever
already lives in the table.

Run:

    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/debug_d08_transport.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from decimal import Decimal
from urllib.parse import quote

# Side-effect: registers Decimal + bool adapters
from shared.questdb_client import get_cursor  # noqa: F401
from shared.decimal_json import dumps_decimal

import psycopg2
import urllib.request
import urllib.error

ACCOUNT_ID = "PROBE_D08_TEST"
QUESTDB_HTTP = f"http://{os.environ.get('QUESTDB_HOST', 'questdb')}:9000"

TSM = {
    "name": "Topstep 150K Trading Combine",
    "classification": {"provider": "TopstepX", "category": "PROP_EVAL",
                       "stage": "STAGE_1", "risk_goal": "PASS_EVAL"},
    "starting_balance": 150000,
    "current_balance": 148155.93,
    "max_drawdown_limit": 4500,
    "max_daily_loss": None,
    "profit_target": 9000,
    "max_contracts": 15,
    "commission_per_contract": 1.40,
    "overnight_allowed": False,
    "trading_hours": {"session_open": "18:00 EST", "session_close": "16:10 EST"},
    "topstep_optimisation": True,
    "topstep_params": {"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0,
                       "max_payouts_remaining": 0},
    "fee_schedule": {"type": "TOPSTEP_EXPRESS",
                     "fees_by_instrument": {"ES": {"round_turn": 2.80}}},
    "scaling_plan": None,
    "scaling_plan_active": False,
    "user_id": "primary_user",
}

SQL_MULTILINE = """INSERT INTO p3_d08_tsm_state(
             account_id, user_id, name, classification,
             starting_balance, current_balance,
             max_drawdown_limit, max_daily_loss,
             daily_loss_used, profit_target, max_contracts,
             commission_per_contract, overnight_allowed,
             trading_hours, risk_goal,
             topstep_optimisation, scaling_plan_active,
             topstep_state, fee_schedule, payout_rules,
             last_updated
         ) VALUES(
             %s, %s, %s, %s,
             %s, %s,
             %s, %s,
             %s, %s, %s,
             %s, %s,
             %s, %s,
             %s, %s,
             %s, %s, %s,
             now()
         )"""


def build_params() -> tuple:
    cls = TSM["classification"]
    topstep_state = dumps_decimal({
        "topstep_params": TSM.get("topstep_params", {}),
        "payout_rules": TSM.get("payout_rules", {}),
        "fee_schedule": TSM.get("fee_schedule", {}),
        "scaling_plan": TSM.get("scaling_plan", []),
    })
    return (
        ACCOUNT_ID, TSM["user_id"], TSM["name"], json.dumps(cls),
        str(Decimal(str(TSM["starting_balance"]))),
        str(Decimal(str(TSM["current_balance"]))),
        str(Decimal(str(TSM["max_drawdown_limit"]))),
        None,
        str(Decimal("0")),
        str(Decimal(str(TSM["profit_target"]))),
        TSM["max_contracts"],
        str(Decimal(str(TSM["commission_per_contract"]))),
        TSM["overnight_allowed"],
        json.dumps(TSM["trading_hours"]),
        cls["risk_goal"],
        TSM["topstep_optimisation"],
        TSM["scaling_plan_active"],
        topstep_state,
        dumps_decimal(TSM["fee_schedule"]),
        dumps_decimal({}),
    )


def report_pg_error(label: str, exc: psycopg2.Error):
    diag = getattr(exc, "diag", None)
    print(f"  {label}: FAIL ({type(exc).__name__})")
    print(f"    str(exc)            : {exc!r}")
    print(f"    pgcode              : {getattr(exc, 'pgcode', None)}")
    if diag is not None:
        for attr in ("severity", "sqlstate", "message_primary",
                     "message_detail", "message_hint",
                     "statement_position", "context",
                     "schema_name", "table_name", "column_name",
                     "datatype_name"):
            v = getattr(diag, attr, None)
            if v is not None:
                print(f"    diag.{attr:<19}: {v!r}")


# ---------------------------------------------------------------------------
# Probe 1: bytes (current production path)
# ---------------------------------------------------------------------------
def probe_bytes():
    print("\n=== Probe 1: PG wire, mogrified bytes (current code path) ===")
    params = build_params()
    try:
        with get_cursor() as cur:
            mogrified = cur.mogrify(SQL_MULTILINE, params)
            print(f"  type(mogrified) = {type(mogrified).__name__}, len = {len(mogrified)}")
            cur.execute(mogrified)  # qexecute: ok — debug-only utility, intentional bypass
        print("  RESULT: OK")
    except psycopg2.Error as exc:
        report_pg_error("bytes-execute", exc)


# ---------------------------------------------------------------------------
# Probe 2: str
# ---------------------------------------------------------------------------
def probe_str():
    print("\n=== Probe 2: PG wire, mogrified-then-decoded str ===")
    params = build_params()
    try:
        with get_cursor() as cur:
            mogrified = cur.mogrify(SQL_MULTILINE, params)
            mogrified_str = mogrified.decode("utf-8") if isinstance(mogrified, bytes) else mogrified
            print(f"  type(query) = {type(mogrified_str).__name__}, len = {len(mogrified_str)}")
            cur.execute(mogrified_str)  # qexecute: ok — debug-only utility, intentional bypass
        print("  RESULT: OK")
    except psycopg2.Error as exc:
        report_pg_error("str-execute", exc)


# ---------------------------------------------------------------------------
# Probe 3: single-line SQL
# ---------------------------------------------------------------------------
def probe_singleline():
    print("\n=== Probe 3: PG wire, single-line SQL (newlines collapsed) ===")
    sql_one_line = re.sub(r"\s+", " ", SQL_MULTILINE).strip()
    params = build_params()
    try:
        with get_cursor() as cur:
            mogrified = cur.mogrify(sql_one_line, params)
            mogrified_str = mogrified.decode("utf-8") if isinstance(mogrified, bytes) else mogrified
            print(f"  len = {len(mogrified_str)}")
            cur.execute(mogrified_str)  # qexecute: ok — debug-only utility, intentional bypass
        print("  RESULT: OK")
    except psycopg2.Error as exc:
        report_pg_error("singleline-execute", exc)


# ---------------------------------------------------------------------------
# Probe 4: HTTP REST API (real error messages)
# ---------------------------------------------------------------------------
def probe_http():
    print("\n=== Probe 4: HTTP REST API /exec — should give a real error ===")
    # Build the literal SQL by mogrifying once outside any cursor execute call.
    params = build_params()
    with get_cursor() as cur:
        mogrified = cur.mogrify(SQL_MULTILINE, params)
    sql_str = mogrified.decode("utf-8") if isinstance(mogrified, bytes) else mogrified

    url = f"{QUESTDB_HTTP}/exec?query={quote(sql_str, safe='')}"
    print(f"  GET {QUESTDB_HTTP}/exec  (sql len={len(sql_str)})")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode("utf-8")
        print(f"  HTTP {resp.status}: {body[:600]}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code}: {body[:1000]}")
    except Exception as exc:
        print(f"  FAIL ({type(exc).__name__}): {exc}")


# ---------------------------------------------------------------------------
# Probe 5: simplest possible 21-col INSERT (literals everywhere)
# ---------------------------------------------------------------------------
def probe_literal_only():
    print("\n=== Probe 5: PG wire, ALL columns as inline SQL literals (no params) ===")
    sql = (
        "INSERT INTO p3_d08_tsm_state("
        "account_id, user_id, name, classification, "
        "starting_balance, current_balance, max_drawdown_limit, max_daily_loss, "
        "daily_loss_used, profit_target, max_contracts, commission_per_contract, "
        "overnight_allowed, trading_hours, risk_goal, topstep_optimisation, "
        "scaling_plan_active, topstep_state, fee_schedule, payout_rules, last_updated"
        ") VALUES("
        "'PROBE_LITERAL', 'u', 'n', '{}', "
        "'1', '1', '1', NULL, "
        "'0', '1', 1, '1', "
        "false, '', '', false, "
        "false, '{}', '{}', '{}', now())"
    )
    print(f"  len = {len(sql)}")
    try:
        with get_cursor() as cur:
            cur.execute(sql)  # qexecute: ok — debug-only utility, intentional bypass
        print("  RESULT: OK")
    except psycopg2.Error as exc:
        report_pg_error("literal-only", exc)


def main():
    print(f"D08 transport probe — account_id={ACCOUNT_ID!r}")
    print(f"QuestDB HTTP endpoint: {QUESTDB_HTTP}")
    try:
        with get_cursor() as cur:
            cur.execute("SELECT count() FROM p3_d08_tsm_state")
            n = cur.fetchone()[0]
        print(f"baseline rows in p3_d08_tsm_state: {n}")
    except Exception as exc:
        print(f"baseline failed: {exc!r}")
        sys.exit(1)

    probe_bytes()
    probe_str()
    probe_singleline()
    probe_literal_only()
    probe_http()


if __name__ == "__main__":
    main()
