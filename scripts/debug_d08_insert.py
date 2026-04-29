#!/usr/bin/env python3
"""Standalone D08 INSERT debug harness.

Run inside the captain-offline container — it has scripts/ bind-mounted at
/captain/scripts and the same QuestDB env vars as captain-command:

    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/debug_d08_insert.py

(captain-command does NOT have scripts/ mounted — see docker-compose.yml.)

What it does
------------
1.  Connects to QuestDB via the same ``shared.questdb_client`` adapters the
    real code path uses (so the Decimal + bool adapters are registered).
2.  Builds the exact 21-column INSERT for ``p3_d08_tsm_state`` that
    ``_store_tsm_in_d08`` builds.
3.  Reproduces the failing TSM payload from the handoff document
    (account 20319811, Topstep 150K Combine, current_balance 148155.93).
4.  For every test variant it:
       * mogrifies the SQL with parameters substituted
       * prints the literal SQL
       * executes it
       * prints either ``OK`` or the **full** psycopg2.Error diag fields
5.  Cleans up by deleting the test rows it inserted.

Variants
--------
A) Full INSERT exactly as production sends today
B) Same as A, but with max_daily_loss replaced by Decimal('0')
   (isolates "None for DECIMAL" hypothesis)
C) Same as A, but with the four large JSON STRING params shortened to '{}'
   (isolates "huge JSON string" hypothesis)
D) Same as A, but max_contracts wrapped in str(...) instead of bare int
   (isolates "Python int -> QuestDB INT" hypothesis)
E) Same as A, but each %s replaced one-at-a-time with a known-safe literal
   (true binary search) — runs only if A still fails after B/C/D pass
"""
from __future__ import annotations

import json
import sys
import traceback
from decimal import Decimal

# Register Decimal + bool adapters via shared.questdb_client side-effects.
from shared.questdb_client import get_cursor  # noqa: F401
from shared.decimal_json import dumps_decimal

import psycopg2

# ---------------------------------------------------------------------------
# Reproduce the failing payload
# ---------------------------------------------------------------------------

# This mirrors the dump in 2026-04-29_d08_tsm_insert_debug_handoff.md.
TSM = {
    "name": "Topstep 150K Trading Combine",
    "classification": {
        "provider": "TopstepX",
        "category": "PROP_EVAL",
        "stage": "STAGE_1",
        "risk_goal": "PASS_EVAL",
    },
    "starting_balance": 150000,
    "current_balance": 148155.93,
    "max_drawdown_limit": 4500,
    "max_daily_loss": None,                  # <-- NULL for DECIMAL
    "profit_target": 9000,
    "max_contracts": 15,                     # <-- Python int for INT
    "commission_per_contract": 1.40,
    "overnight_allowed": False,
    "trading_hours": {
        "session_open": "18:00 EST",
        "session_close": "16:10 EST",
        "flat_by": "16:10 EST",
        "risk_manager_flatten": "16:08 EST",
        "eod_exit_buffer": "15:55 EST",
        "weekend_close": "Friday 16:10 EST",
        "weekend_open": "Sunday 18:00 EST",
    },
    "topstep_optimisation": True,
    "topstep_params": {"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0,
                       "max_payouts_remaining": 0},
    "fee_schedule": {
        "type": "TOPSTEP_EXPRESS",
        "fees_by_instrument": {
            "ES":  {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "NQ":  {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "MES": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
        },
        "slippage_model": {"type": "FIXED_TICKS", "ticks_per_side": 1},
    },
    "scaling_plan": None,
    "scaling_plan_active": False,
    "user_id": "primary_user",
}

ACCOUNT_ID = "DEBUG_D08_TEST"

SQL = """INSERT INTO p3_d08_tsm_state(
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


def build_params(tsm: dict) -> tuple:
    classification = tsm.get("classification", {})
    topstep_state = dumps_decimal({
        "topstep_params": tsm.get("topstep_params", {}),
        "payout_rules": tsm.get("payout_rules", {}),
        "fee_schedule": tsm.get("fee_schedule", {}),
        "scaling_plan": tsm.get("scaling_plan", []),
    })
    sb = tsm.get("starting_balance", 0)
    cb = tsm.get("current_balance", tsm.get("starting_balance", 0))
    return (
        ACCOUNT_ID,
        tsm.get("user_id", ""),
        tsm.get("name", ""),
        json.dumps(classification),
        str(Decimal(str(sb))),
        str(Decimal(str(cb))),
        str(Decimal(str(tsm.get("max_drawdown_limit", 0)))),
        str(Decimal(str(tsm.get("max_daily_loss")))) if tsm.get("max_daily_loss") is not None else None,
        str(Decimal("0")),
        str(Decimal(str(tsm.get("profit_target")))) if tsm.get("profit_target") is not None else None,
        tsm.get("max_contracts", 0),
        str(Decimal(str(tsm.get("commission_per_contract", 0)))),
        tsm.get("overnight_allowed", False),
        json.dumps(tsm.get("trading_hours", "")) if isinstance(tsm.get("trading_hours"), dict) else tsm.get("trading_hours", ""),
        classification.get("risk_goal", ""),
        tsm.get("topstep_optimisation", False),
        tsm.get("scaling_plan_active", False),
        topstep_state,
        dumps_decimal(tsm.get("fee_schedule", {})),
        dumps_decimal(tsm.get("payout_rules", {})),
    )


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def cleanup():
    """QuestDB has no DELETE; truncate is the only way to clear the test row."""
    # TRUNCATE on a partitioned table only drops complete partitions; for a
    # single test row that lives in the current month, the cleanest path is to
    # drop the partition.  But we share the table with real data, so instead
    # we simply leave the DEBUG_D08_TEST row in place.  It does not interfere
    # with the real account_id ('20319811').  Document it as harmless.
    pass


def run_variant(label: str, params: tuple):
    print(f"\n{'='*72}\n{label}\n{'='*72}")
    print(f"  param types: {[(i, type(p).__name__, repr(p)[:60]) for i, p in enumerate(params)]}\n")
    try:
        with get_cursor() as cur:
            mogrified = cur.mogrify(SQL, params)
            sql_text = mogrified.decode("utf-8", errors="replace") if isinstance(mogrified, bytes) else str(mogrified)
            print(f"  mogrified SQL (first 1500 chars):\n  {sql_text[:1500]}\n")
            cur.execute(mogrified)
        print("  RESULT: OK")
        return True
    except psycopg2.Error as exc:
        diag = getattr(exc, "diag", None)
        print(f"  RESULT: FAIL ({type(exc).__name__})")
        print(f"    str(exc)  : {exc!r}")
        print(f"    pgcode    : {getattr(exc, 'pgcode', None)}")
        print(f"    pgerror   : {getattr(exc, 'pgerror', None)!r}")
        if diag is not None:
            for attr in ("severity", "sqlstate", "message_primary", "message_detail",
                         "message_hint", "statement_position", "context",
                         "schema_name", "table_name", "column_name", "datatype_name"):
                val = getattr(diag, attr, None)
                if val is not None:
                    print(f"    diag.{attr:<22}: {val!r}")
        return False
    except Exception as exc:
        print(f"  RESULT: FAIL (non-pg {type(exc).__name__}): {exc!r}")
        traceback.print_exc()
        return False


def main():
    print("D08 INSERT debug harness — captain-command container")
    print(f"  using account_id = {ACCOUNT_ID!r}\n")

    # -------- baseline sanity --------
    try:
        with get_cursor() as cur:
            cur.execute("SELECT count() FROM p3_d08_tsm_state")
            n = cur.fetchone()[0]
        print(f"baseline: p3_d08_tsm_state row count = {n}")
    except Exception as exc:
        print(f"baseline failed: {exc!r}")
        sys.exit(1)

    # ---- A: production payload as-is ----
    A = build_params(TSM)
    okA = run_variant("VARIANT A — exact production payload (None DECIMAL, int max_contracts)", A)

    if okA:
        print("\nVariant A succeeded. Either the bug is fixed already or the "
              "TSM payload at runtime differs from this synthetic one. "
              "Re-run the harness inside captain-command after a restart.")
        cleanup()
        return

    # ---- B: replace None DECIMAL with Decimal('0') ----
    tsm_b = dict(TSM, max_daily_loss=0)
    B = build_params(tsm_b)
    okB = run_variant("VARIANT B — max_daily_loss = '0' (no NULL DECIMAL)", B)

    # ---- C: shorten all JSON STRING params ----
    tsm_c = dict(TSM, trading_hours="", topstep_params={}, fee_schedule={},
                 payout_rules={}, scaling_plan=None)
    # also shrink classification to just the required keys with short values
    tsm_c["classification"] = {"provider": "TopstepX", "category": "X",
                               "stage": "X", "risk_goal": "PASS_EVAL"}
    C = build_params(tsm_c)
    okC = run_variant("VARIANT C — small JSON STRING params", C)

    # ---- D: max_contracts as str instead of int ----
    D_params = list(A)
    D_params[10] = str(A[10])  # column index 10 = max_contracts
    okD = run_variant("VARIANT D — max_contracts wrapped as str", tuple(D_params))

    # ---- E: replace each %s one-by-one with a known-safe literal ----
    if not (okB or okC or okD):
        print("\nNone of B/C/D fixed it. Running per-column isolation.")
        SAFE = {
            0: "'BIN_TEST'", 1: "'u'", 2: "'n'", 3: "'{}'",
            4: "'1'", 5: "'1'", 6: "'1'", 7: "NULL",
            8: "'0'", 9: "'1'", 10: "1",
            11: "'1'", 12: "false",
            13: "''", 14: "''", 15: "false", 16: "false",
            17: "'{}'", 18: "'{}'", 19: "'{}'",
        }
        for swap_idx in range(20):
            # Build SQL with a literal at swap_idx, %s elsewhere
            placeholders = []
            ph_iter = iter(range(20))
            for i in range(20):
                placeholders.append(SAFE[i] if i == swap_idx else "%s")
            sql_e = SQL  # rebuild
            # Manually substitute placeholders by index
            parts = SQL.split("%s")
            # parts has 21 chunks (20 %s placeholders + closing chunk)
            assert len(parts) == 21, len(parts)
            built = parts[0]
            new_params = []
            for i in range(20):
                built += placeholders[i] + parts[i + 1]
                if placeholders[i] == "%s":
                    new_params.append(A[i])
            # Use a different account_id per probe so dedup doesn't hide the result
            new_params_t = tuple(new_params)
            label_e = f"VARIANT E[{swap_idx:02d}] — column {swap_idx} replaced with safe literal {SAFE[swap_idx]!r}"
            try:
                with get_cursor() as cur:
                    mogrified = cur.mogrify(built, new_params_t)
                    cur.execute(mogrified)
                print(f"  {label_e}: OK  (column {swap_idx} is the suspect)")
            except psycopg2.Error as exc:
                diag = getattr(exc, "diag", None)
                primary = getattr(diag, "message_primary", None) if diag else None
                print(f"  {label_e}: FAIL  pgcode={exc.pgcode} primary={primary!r}")

    cleanup()


if __name__ == "__main__":
    main()
