#!/usr/bin/env python3
"""Compact bloated QuestDB append-only state tables.

QuestDB is append-only — every "update" appends a new row. State tables
like D01, D02, D05, D12, D25 grow unbounded. This script keeps only the
latest row per logical key and drops the rest.

Belt-and-braces: with canonical WAL+DEDUP DDLs, DEDUP fires on same-
microsecond writes; compaction handles the long tail of rows where writers
use now() (unique timestamps). Run every 48h via captain-offline orchestrator.

Usage (run inside captain-command container):
    docker exec captain-system-captain-command-1 python3 /app/scripts/compact_questdb_tables.py

Or with --dry-run to see counts without making changes:
    docker exec captain-system-captain-command-1 python3 /app/scripts/compact_questdb_tables.py --dry-run

Feature flag: set CAPTAIN_COMPACTION_ENABLED=false in .env to disable.
"""

import os
import sys
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.canonical_schemas import (
    D01_AIM_MODEL_STATES,
    D02_AIM_META_WEIGHTS,
    D05_EWMA_STATES,
    D12_KELLY_PARAMETERS,
    D25_CIRCUIT_BREAKER_PARAMS,
)

QUESTDB_HOST = os.environ.get("QUESTDB_HOST", "questdb")
QUESTDB_PORT = int(os.environ.get("QUESTDB_PORT", "8812"))
QUESTDB_USER = os.environ.get("QUESTDB_USER", "captain")
QUESTDB_PASSWORD = os.environ.get("QUESTDB_PASSWORD", "")

# Each entry: (table_name, key_columns, timestamp_col, create_ddl)
# DDLs imported from canonical_schemas — guaranteed consistent with init_all.py
TABLES = [
    (
        "p3_d01_aim_model_states",
        ["aim_id", "asset_id"],
        "last_updated",
        D01_AIM_MODEL_STATES,
    ),
    (
        "p3_d02_aim_meta_weights",
        ["aim_id", "asset_id"],
        "last_updated",
        D02_AIM_META_WEIGHTS,
    ),
    (
        "p3_d05_ewma_states",
        ["asset_id", "regime", "session"],
        "last_updated",
        D05_EWMA_STATES,
    ),
    (
        "p3_d12_kelly_parameters",
        ["asset_id", "regime", "session"],
        "last_updated",
        D12_KELLY_PARAMETERS,
    ),
    (
        "p3_d25_circuit_breaker_params",
        ["account_id"],
        "last_updated",
        D25_CIRCUIT_BREAKER_PARAMS,
    ),
]


def get_connection():
    conn = psycopg2.connect(
        host=QUESTDB_HOST,
        port=QUESTDB_PORT,
        user=QUESTDB_USER,
        password=QUESTDB_PASSWORD,
        database="qdb",
    )
    conn.autocommit = True
    return conn


def audit_tables(cur):
    """Print row counts for all state tables."""
    print("\n=== Table Row Counts ===")
    for table, keys, ts_col, _ in TABLES:
        try:
            cur.execute(f"SELECT count() FROM {table}")
            total = cur.fetchone()[0]

            key_str = ", ".join(keys)
            cur.execute(f"SELECT count() FROM (SELECT {key_str} FROM {table} GROUP BY {key_str})")
            unique = cur.fetchone()[0]

            ratio = total / unique if unique > 0 else 0
            status = "BLOATED" if ratio > 10 else "OK" if ratio < 3 else "GROWING"
            print(f"  {table}: {total:,} rows, {unique} unique keys, {ratio:.0f}x bloat [{status}]")
        except Exception as e:
            print(f"  {table}: ERROR — {e}")


def compact_table(cur, table, keys, ts_col, create_ddl, dry_run=False):
    """Compact a table by keeping only the latest row per logical key."""
    key_str = ", ".join(keys)

    cur.execute(f"SELECT count() FROM {table}")
    total = cur.fetchone()[0]

    cur.execute(f"SELECT {key_str}, max({ts_col}) as latest FROM {table} GROUP BY {key_str}")
    groups = cur.fetchall()
    print(f"\n--- Compacting {table}: {total:,} rows -> {len(groups)} rows ---")

    if dry_run:
        print("  [DRY RUN] No changes made.")
        return

    # Fetch the latest full row for each key group
    latest_rows = []
    for group in groups:
        where_parts_psy = []
        params = []
        for i, key in enumerate(keys):
            where_parts_psy.append(f"{key} = %s")
            params.append(group[i])
        where_parts_psy.append(f"{ts_col} = %s")
        params.append(group[-1])
        where_clause = " AND ".join(where_parts_psy)

        cur.execute(f"SELECT * FROM {table} WHERE {where_clause} LIMIT 1", params)
        row = cur.fetchone()
        if row:
            latest_rows.append(row)

    print(f"  Retrieved {len(latest_rows)} latest rows")

    cur.execute(f"SELECT * FROM {table} LIMIT 0")
    col_count = len(cur.description)
    col_names = [desc[0] for desc in cur.description]
    print(f"  Columns: {col_names}")

    cur.execute(f"DROP TABLE IF EXISTS {table}")
    print("  Dropped old table")

    cur.execute(create_ddl)
    print("  Recreated table (canonical DDL)")

    placeholders = ", ".join(["%s"] * col_count)
    inserted = 0
    for row in latest_rows:
        try:
            cur.execute(f"INSERT INTO {table} VALUES ({placeholders})", row)
            inserted += 1
        except Exception as e:
            print(f"  WARNING: Failed to insert row: {e}")
            print(f"  Row: {row}")

    print(f"  Inserted {inserted}/{len(latest_rows)} rows")
    print(f"  Compaction complete: {total:,} -> {inserted}")


def main():
    compaction_enabled = os.environ.get("CAPTAIN_COMPACTION_ENABLED", "true").lower() == "true"
    if not compaction_enabled:
        print("CAPTAIN_COMPACTION_ENABLED=false — compaction skipped by feature flag.")
        return

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== DRY RUN MODE — no changes will be made ===")

    conn = get_connection()
    cur = conn.cursor()
    print("Connected to QuestDB")

    audit_tables(cur)

    if dry_run:
        print("\nRe-run without --dry-run to compact bloated tables.")
        cur.close()
        conn.close()
        return

    for table, keys, ts_col, ddl in TABLES:
        try:
            cur.execute(f"SELECT count() FROM {table}")
            total = cur.fetchone()[0]
            cur.execute(f"SELECT count() FROM (SELECT {', '.join(keys)} FROM {table} GROUP BY {', '.join(keys)})")
            unique = cur.fetchone()[0]
            ratio = total / unique if unique > 0 else 0

            if ratio > 3:
                compact_table(cur, table, keys, ts_col, ddl)
            else:
                print(f"\n--- Skipping {table}: only {ratio:.1f}x bloat ---")
        except Exception as e:
            print(f"\n--- ERROR on {table}: {e} ---")

    cur.close()
    conn.close()
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
