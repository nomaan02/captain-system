#!/usr/bin/env python3
"""D08 column-bisection probe — find which column makes the INSERT fail.

Probes:
    1. Show the actual table schema as QuestDB sees it (HTTP /exec).
    2. Show the FULL HTTP error response for the failing 21-column INSERT
       (debug_d08_transport.py truncated this — we need the "error" field,
       not just the "query" field).
    3. Bisect by growing column count from 3 -> 21 to find the exact
       transition point where the INSERT goes from OK to FAIL.

Run:

    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/debug_d08_bisect.py
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import quote

from shared.questdb_client import get_cursor  # noqa: F401  (registers adapters)

import urllib.request
import urllib.error

QUESTDB_HTTP = f"http://{os.environ.get('QUESTDB_HOST', 'questdb')}:9000"

# Same column order as in b4_tsm_manager._store_tsm_in_d08, plus the trailing
# now() for last_updated.  All 21 names, paired with a known-safe literal.
COLUMNS = [
    ("account_id",              "'BISECT_PROBE'"),
    ("user_id",                 "'u'"),
    ("name",                    "'n'"),
    ("classification",          "'{}'"),
    ("starting_balance",        "'1'"),
    ("current_balance",         "'1'"),
    ("max_drawdown_limit",      "'1'"),
    ("max_daily_loss",          "'1'"),
    ("daily_loss_used",         "'0'"),
    ("profit_target",           "'1'"),
    ("max_contracts",           "1"),
    ("commission_per_contract", "'1'"),
    ("overnight_allowed",       "false"),
    ("trading_hours",           "''"),
    ("risk_goal",               "''"),
    ("topstep_optimisation",    "false"),
    ("scaling_plan_active",     "false"),
    ("topstep_state",           "'{}'"),
    ("fee_schedule",            "'{}'"),
    ("payout_rules",            "'{}'"),
]
LAST_COL = ("last_updated", "now()")


def http_exec(sql: str) -> tuple[int, str]:
    url = f"{QUESTDB_HTTP}/exec?query={quote(sql, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# 1. Show the table schema as QuestDB has it
# ---------------------------------------------------------------------------
def show_schema():
    print("=" * 72)
    print("1. Live schema of p3_d08_tsm_state (HTTP /exec):")
    print("=" * 72)
    status, body = http_exec("SHOW COLUMNS FROM p3_d08_tsm_state")
    print(f"  HTTP {status}")
    if status == 200:
        try:
            data = json.loads(body)
            cols = data.get("dataset", [])
            print(f"  {len(cols)} columns:")
            for r in cols:
                # SHOW COLUMNS columns: column, type, indexed, indexBlockCapacity, ...
                print(f"    {r[0]:<28} {r[1]}")
        except Exception:
            print(body[:2000])
    else:
        print(body[:2000])
    print()

    # Also dump WAL / suspended state — can cause silent INSERT rejection
    print("-" * 72)
    print("WAL state for p3_d08_tsm_state:")
    status, body = http_exec("SELECT name, suspended, writerTxn, sequencerTxn "
                             "FROM wal_tables() WHERE name = 'p3_d08_tsm_state'")
    print(f"  HTTP {status}: {body[:500]}")
    print()


# ---------------------------------------------------------------------------
# 2. Full HTTP error for the failing 21-column INSERT
# ---------------------------------------------------------------------------
def full_http_error_for_21cols():
    print("=" * 72)
    print("2. FULL HTTP response for failing 21-column INSERT")
    print("=" * 72)
    cols = COLUMNS + [LAST_COL]
    sql = (
        "INSERT INTO p3_d08_tsm_state("
        + ", ".join(c for c, _ in cols)
        + ") VALUES("
        + ", ".join(v for _, v in cols)
        + ")"
    )
    print(f"  SQL ({len(sql)} chars): {sql[:200]}...")
    status, body = http_exec(sql)
    print(f"  HTTP {status}")
    print(f"  FULL BODY:\n{body}\n")


# ---------------------------------------------------------------------------
# 3. Bisect: grow N from 3 -> 21
# ---------------------------------------------------------------------------
def bisect_by_growth():
    print("=" * 72)
    print("3. Bisection — grow column count, find the failure point")
    print("=" * 72)
    print("  (uses HTTP API so we get a real error message)")
    print()

    last_ok_n = 0
    first_fail_n = None

    for n in range(3, len(COLUMNS) + 1):
        cols = COLUMNS[:n] + [LAST_COL]
        sql = (
            "INSERT INTO p3_d08_tsm_state("
            + ", ".join(c for c, _ in cols)
            + ") VALUES("
            + ", ".join(v for _, v in cols)
            + ")"
        )
        status, body = http_exec(sql)
        ok = status == 200
        # Extract just the "error" field if present
        err = ""
        try:
            j = json.loads(body)
            err = j.get("error") or ""
            pos = j.get("position")
            if pos is not None:
                err = f"{err}  (position={pos})"
        except Exception:
            err = body[:200]
        first_col = COLUMNS[n - 1][0]  # the column we just added
        print(f"  N={n:2d}  added={first_col:<28}  HTTP={status}  {'OK' if ok else 'FAIL'}  {err[:160]}")
        if ok:
            last_ok_n = n
        elif first_fail_n is None:
            first_fail_n = n

    print()
    print(f"  Last OK at N={last_ok_n}, first FAIL at N={first_fail_n}")
    if first_fail_n:
        offending = COLUMNS[first_fail_n - 1][0]
        print(f"  >>> Adding column {offending!r} flips the INSERT from OK to FAIL.")


# ---------------------------------------------------------------------------
# 4. Same bisection in REVERSE: drop columns from full set one at a time
# ---------------------------------------------------------------------------
def bisect_by_dropping():
    print()
    print("=" * 72)
    print("4. Reverse bisection — drop one column from the full INSERT at a time")
    print("=" * 72)
    print("  (if dropping column X makes a previously-failing 21-col INSERT pass,")
    print("   then X is the trigger)")
    print()
    for drop_idx in range(len(COLUMNS)):
        cols = [c for i, c in enumerate(COLUMNS) if i != drop_idx] + [LAST_COL]
        sql = (
            "INSERT INTO p3_d08_tsm_state("
            + ", ".join(c for c, _ in cols)
            + ") VALUES("
            + ", ".join(v for _, v in cols)
            + ")"
        )
        status, body = http_exec(sql)
        try:
            err = json.loads(body).get("error", "")
        except Exception:
            err = body[:120]
        dropped = COLUMNS[drop_idx][0]
        marker = "OK <<<" if status == 200 else "fail"
        print(f"  drop={dropped:<28}  HTTP={status}  {marker}  {err[:120]}")


def main():
    show_schema()
    full_http_error_for_21cols()
    bisect_by_growth()
    bisect_by_dropping()


if __name__ == "__main__":
    main()
