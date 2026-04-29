#!/usr/bin/env python3
"""D08 fix-pattern probe.

Q1 of debug_d08_minimal_repro.py confirmed the root cause:
QuestDB silently crashes (HTTP 500, error="") when INSERTing certain
short quoted-string values into a DECIMAL column (e.g. '0', '1', '1.4'),
but works for longer ones ('100', '150000', '148155.93').

The adapter fix needs to work for ALL DECIMAL columns across the schema:
    DECIMAL(18,2) — D08 monetary
    DECIMAL(18,4) — D03 pnl
    DECIMAL(14,4) — D30 prices
    DECIMAL(14,6) — wider prices
    DECIMAL(14,8) — bond tick sizes

So we need ONE cast form that works regardless of column scale/precision.

Probes:
    A. cast('<value>' as DECIMAL)             — no precision/scale
    B. cast('<value>' as DECIMAL(38,18))      — max precision scale, narrowed at assignment
    C. '<value>'::DECIMAL                     — pg-style cast, no precision/scale
    D. '<value>'::DECIMAL(38,18)              — pg-style with max precision
    E. cast('<value>' as DECIMAL(18,2))       — exact column match (known to work for D08)

Each pattern is tested with the actual problematic values from the TSM payload:
    '0', '1', '1.4', '4500', '150000', '148155.93'
plus a value with more decimal places than the target column scale (truncation test).

Run:
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/debug_d08_fix_probe.py
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote

from shared.questdb_client import get_cursor  # noqa: F401  (registers adapters)

import urllib.request
import urllib.error

QUESTDB_HTTP = f"http://{os.environ.get('QUESTDB_HOST', 'questdb')}:9000"


def http_exec(sql: str) -> tuple[int, str]:
    url = f"{QUESTDB_HTTP}/exec?query={quote(sql, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def err_field(body: str) -> str:
    try:
        j = json.loads(body)
        e = j.get("error", "")
        p = j.get("position")
        return f"{e} (pos={p})" if e else f"(pos={p})"
    except Exception:
        return body[:140]


# Patterns to test, parametrised by Decimal value string
PATTERNS = [
    ("A_cast_no_scale", lambda v: f"cast('{v}' as DECIMAL)"),
    ("B_cast_38_18",    lambda v: f"cast('{v}' as DECIMAL(38,18))"),
    ("C_pg_no_scale",   lambda v: f"'{v}'::DECIMAL"),
    ("D_pg_38_18",      lambda v: f"'{v}'::DECIMAL(38,18)"),
    ("E_cast_18_2",     lambda v: f"cast('{v}' as DECIMAL(18,2))"),
]

# Values that exercise the bug + edge cases
VALUES = [
    "0",         # single digit zero — daily_loss_used
    "1",         # single digit one  — Q1 confirmed crash
    "1.4",       # short fractional  — commission_per_contract
    "4500",      # multi-digit int   — max_drawdown_limit
    "150000",    # large int         — starting_balance
    "148155.93", # 2-decimal float   — current_balance
    "0.001",     # 3-decimal value   — exceeds DECIMAL(18,2) scale
]

# Two target columns with different precision/scale
TARGETS = [
    ("p3_d08_tsm_state.starting_balance (18,2)",
     "INSERT INTO p3_d08_tsm_state(account_id, starting_balance, last_updated) "
     "VALUES('FIXPROBE_{label}_{vlabel}', {expr}, now())"),
    ("p3_d30_daily_ohlcv.open (14,4)",
     # Use a fake-ish primary key combination that won't collide with seeds
     "INSERT INTO p3_d30_daily_ohlcv(asset_id, ts, open, high, low, close, volume) "
     "VALUES('PROBE_{label}_{vlabel}', cast('1970-01-01T00:00:00.000000Z' as TIMESTAMP), "
     "{expr}, {expr}, {expr}, {expr}, 1)"),
]


def main():
    print("Fix-pattern probe — finds the universal safe form for DECIMAL adapter\n")

    for tgt_label, tgt_sql in TARGETS:
        print("=" * 78)
        print(f"Target: {tgt_label}")
        print("=" * 78)

        # Header row: column = pattern, row = value
        col_w = 22
        header = "value".ljust(12) + "".join(p[0].ljust(col_w) for p in PATTERNS)
        print(header)

        for v in VALUES:
            row = v.ljust(12)
            for label, gen in PATTERNS:
                expr = gen(v)
                vlabel = v.replace(".", "p").replace("-", "m")
                sql = tgt_sql.format(label=label, vlabel=vlabel, expr=expr)
                status, body = http_exec(sql)
                if status == 200:
                    cell = "OK"
                else:
                    err = err_field(body)
                    if "inconvertible" in err:
                        cell = "INCONV"
                    elif status == 500 and "(pos=0)" in err:
                        cell = "CRASH"
                    elif "DEDUP" in err.upper() or "constraint" in err.lower():
                        cell = "DEDUP-OK"
                    else:
                        cell = f"E{status}"
                row += cell.ljust(col_w)
            print(row)
        print()

    print("Legend:")
    print("  OK       — INSERT succeeded")
    print("  CRASH    — HTTP 500 with empty error string (the bug we're working around)")
    print("  INCONV   — 'inconvertible types' (e.g. DOUBLE -> DECIMAL)")
    print("  DEDUP-OK — INSERT was rejected by DEDUP key — counts as success for syntax purposes")
    print("  E<code>  — other HTTP error status")


if __name__ == "__main__":
    main()
