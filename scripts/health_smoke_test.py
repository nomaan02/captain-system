#!/usr/bin/env python3
"""Session C — health_smoke_test.py

Connectivity and schema smoke test.  Exercises the Phase 0 health gate path
via shared/questdb_client.py, reads one row from each critical table, then
runs a write/read/dedup-replace cycle on a scratch table.

Exits 0 on full pass; exits 1 with a one-line reason on any failure.

Usage (locally):
    python scripts/health_smoke_test.py

Usage (inside container):
    python /captain/scripts/health_smoke_test.py
"""
import sys
import os
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, "/app")

from shared.questdb_client import wait_for_questdb, get_cursor

SCRATCH_TABLE = "p3_smoke_scratch"

# Critical tables: (label, table_name) — must be readable after bootstrap
CRITICAL_TABLES = [
    ("D00", "p3_d00_asset_universe"),
    ("D02", "p3_d02_aim_meta_weights"),
    ("D08", "p3_d08_tsm_state"),
    ("D12", "p3_d12_kelly_parameters"),
    ("D16", "p3_d16_user_capital_silos"),
    ("D25", "p3_d25_circuit_breaker_params"),
    ("D30", "p3_d30_daily_ohlcv"),
]

# Fixed timestamp for the dedup test — well in the past, partition safe
_DEDUP_TS = "2026-01-01T00:00:00.000000Z"


def _drop_scratch():
    try:
        with get_cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {SCRATCH_TABLE}")
    except Exception:
        pass


def main():
    # ------------------------------------------------------------------ #
    # 1. Phase 0 health gate — same code path as service startup          #
    # ------------------------------------------------------------------ #
    print("1. QuestDB health gate (wait_for_questdb, max 30s)…")
    if not wait_for_questdb(max_wait_seconds=30):
        print("FAIL: QuestDB unreachable after 30 seconds")
        sys.exit(1)
    print("   reachable.")

    # ------------------------------------------------------------------ #
    # 2. Read one row from each critical table                             #
    # ------------------------------------------------------------------ #
    print("2. Reading one row from each critical table…")
    for label, tname in CRITICAL_TABLES:
        try:
            with get_cursor() as cur:
                cur.execute(f"SELECT count() FROM {tname}")
                count = cur.fetchone()[0]
            print(f"   {label:<4} {tname}: {count} rows")
        except Exception as exc:
            print(f"FAIL: cannot read {label} ({tname}): {exc}")
            sys.exit(1)

    # ------------------------------------------------------------------ #
    # 3. Scratch table: write / read / dedup-replace / drop               #
    # ------------------------------------------------------------------ #
    print("3. Scratch table write/read/dedup-replace…")
    _drop_scratch()  # clean start in case a prior run left debris

    try:
        with get_cursor() as cur:
            cur.execute(
                f"""CREATE TABLE IF NOT EXISTS {SCRATCH_TABLE} (
                    id SYMBOL,
                    val DOUBLE,
                    ts TIMESTAMP
                ) TIMESTAMP(ts) PARTITION BY DAY WAL
                DEDUP UPSERT KEYS(ts, id)"""
            )
        print(f"   created {SCRATCH_TABLE}")

        # First write
        with get_cursor() as cur:
            cur.execute(
                f"INSERT INTO {SCRATCH_TABLE} (id, val, ts) VALUES ('smoke', 1.0, '{_DEDUP_TS}')"
            )
        print("   first write (val=1.0) OK")

        # Read back
        deadline = time.monotonic() + 5.0
        row_found = False
        while time.monotonic() < deadline:
            with get_cursor() as cur:
                cur.execute(
                    f"SELECT val FROM {SCRATCH_TABLE} WHERE id = 'smoke' ORDER BY ts LIMIT 1"
                )
                r = cur.fetchone()
            if r is not None:
                row_found = True
                print(f"   read back: val={r[0]}")
                break
            time.sleep(0.2)

        if not row_found:
            print(f"FAIL: scratch row not readable within 5s")
            _drop_scratch()
            sys.exit(1)

        # Dedup-replace: same (ts, id) key, new val
        with get_cursor() as cur:
            cur.execute(
                f"INSERT INTO {SCRATCH_TABLE} (id, val, ts) VALUES ('smoke', 2.0, '{_DEDUP_TS}')"
            )
        print("   dedup-replace write (val=2.0) OK")

        # Verify the replace landed (poll up to 10s for WAL commit)
        deadline = time.monotonic() + 10.0
        dedup_ok = False
        while time.monotonic() < deadline:
            with get_cursor() as cur:
                cur.execute(
                    f"SELECT count(), max(val) FROM {SCRATCH_TABLE} WHERE id = 'smoke'"
                )
                cnt, max_val = cur.fetchone()
            if cnt == 1 and max_val == 2.0:
                dedup_ok = True
                print(f"   dedup confirmed: count={cnt}, val={max_val}")
                break
            time.sleep(0.3)

        if not dedup_ok:
            print(f"FAIL: dedup did not collapse within 10s (count={cnt}, max_val={max_val})")
            _drop_scratch()
            sys.exit(1)

    except Exception as exc:
        print(f"FAIL: scratch table error: {exc}")
        _drop_scratch()
        sys.exit(1)
    finally:
        _drop_scratch()
        print(f"   dropped {SCRATCH_TABLE}")

    print(
        "\nPASS: QuestDB reachable, 7 critical tables readable, scratch write/read/dedup/drop OK"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
