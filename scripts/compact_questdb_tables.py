#!/usr/bin/env python3
"""Compact bloated QuestDB append-only state tables.

QuestDB is append-only — every "update" appends a new row. State tables
like D01, D02, D05, D08, D12, D16, D25 grow unbounded. This script
keeps only the latest row per logical key and drops the rest.

Usage (run inside captain-command container):
    docker exec captain-system-captain-command-1 python3 /app/scripts/compact_questdb_tables.py

Or with --dry-run to see counts without making changes:
    docker exec captain-system-captain-command-1 python3 /app/scripts/compact_questdb_tables.py --dry-run
"""

import os
import sys
import psycopg2

QUESTDB_HOST = os.environ.get("QUESTDB_HOST", "questdb")
QUESTDB_PORT = int(os.environ.get("QUESTDB_PORT", "8812"))
QUESTDB_USER = os.environ.get("QUESTDB_USER", "captain")
QUESTDB_PASSWORD = os.environ.get("QUESTDB_PASSWORD", "")

# Each entry: (table_name, key_columns, timestamp_col, create_ddl)
TABLES = [
    (
        "p3_d01_aim_model_states",
        ["aim_id", "asset_id"],
        "last_updated",
        """CREATE TABLE IF NOT EXISTS p3_d01_aim_model_states (
            aim_id INT,
            asset_id SYMBOL,
            status STRING,
            model_object STRING,
            warmup_progress DOUBLE,
            current_modifier STRING,
            last_retrained TIMESTAMP,
            missing_data_rate_30d DOUBLE,
            last_updated TIMESTAMP
        ) timestamp(last_updated);""",
    ),
    (
        "p3_d02_aim_meta_weights",
        ["aim_id", "asset_id"],
        "last_updated",
        """CREATE TABLE IF NOT EXISTS p3_d02_aim_meta_weights (
            aim_id INT,
            asset_id SYMBOL,
            weight DOUBLE,
            dma_score DOUBLE,
            trend STRING,
            anomaly_flag BOOLEAN,
            override_reason STRING,
            last_updated TIMESTAMP
        ) timestamp(last_updated);""",
    ),
    (
        "p3_d05_ewma_states",
        ["asset_id", "regime", "session"],
        "last_updated",
        """CREATE TABLE IF NOT EXISTS p3_d05_ewma_states (
            asset_id SYMBOL,
            regime STRING,
            session INT,
            win_rate DOUBLE,
            avg_win DOUBLE,
            avg_loss DOUBLE,
            n_trades INT,
            last_updated TIMESTAMP
        ) timestamp(last_updated);""",
    ),
    (
        "p3_d12_kelly_parameters",
        ["asset_id", "regime", "session"],
        "last_updated",
        """CREATE TABLE IF NOT EXISTS p3_d12_kelly_parameters (
            asset_id SYMBOL,
            regime STRING,
            session INT,
            kelly_full DOUBLE,
            shrinkage_factor DOUBLE,
            sizing_override STRING,
            last_updated TIMESTAMP
        ) timestamp(last_updated);""",
    ),
    (
        "p3_d25_circuit_breaker_params",
        ["account_id"],
        "last_updated",
        """CREATE TABLE IF NOT EXISTS p3_d25_circuit_breaker_params (
            account_id SYMBOL,
            model_m INT,
            r_bar DOUBLE,
            beta_b DOUBLE,
            sigma DOUBLE,
            rho_bar DOUBLE,
            n_observations INT,
            p_value DOUBLE,
            l_star DOUBLE,
            cold_start BOOLEAN,
            last_updated TIMESTAMP
        ) timestamp(last_updated);""",
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

    # Step 1: Count current rows
    cur.execute(f"SELECT count() FROM {table}")
    total = cur.fetchone()[0]

    # Step 2: Get latest timestamp per key group
    cur.execute(f"SELECT {key_str}, max({ts_col}) as latest FROM {table} GROUP BY {key_str}")
    groups = cur.fetchall()
    print(f"\n--- Compacting {table}: {total:,} rows -> {len(groups)} rows ---")

    if dry_run:
        print("  [DRY RUN] No changes made.")
        return

    # Step 3: Fetch the latest full row for each key group
    latest_rows = []
    for group in groups:
        where_parts = []
        params = []
        for i, key in enumerate(keys):
            where_parts.append(f"{key} = ${i + 1}")
            params.append(group[i])
        # The last element in group is max(ts_col)
        where_parts.append(f"{ts_col} = ${len(keys) + 1}")
        params.append(group[-1])

        where_clause = " AND ".join(where_parts)

        # QuestDB uses $1, $2 style params but psycopg2 uses %s
        where_parts_psy = []
        for i, key in enumerate(keys):
            where_parts_psy.append(f"{key} = %s")
        where_parts_psy.append(f"{ts_col} = %s")
        where_clause = " AND ".join(where_parts_psy)

        cur.execute(f"SELECT * FROM {table} WHERE {where_clause} LIMIT 1", params)
        row = cur.fetchone()
        if row:
            latest_rows.append(row)

    print(f"  Retrieved {len(latest_rows)} latest rows")

    # Step 4: Get column count for placeholders
    cur.execute(f"SELECT * FROM {table} LIMIT 0")
    col_count = len(cur.description)
    col_names = [desc[0] for desc in cur.description]
    print(f"  Columns: {col_names}")

    # Step 5: Drop old table
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    print(f"  Dropped old table")

    # Step 6: Recreate table
    cur.execute(create_ddl)
    print(f"  Recreated table")

    # Step 7: Insert latest rows
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
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=== DRY RUN MODE — no changes will be made ===")

    conn = get_connection()
    cur = conn.cursor()
    print("Connected to QuestDB")

    # Always audit first
    audit_tables(cur)

    if dry_run:
        print("\nRe-run without --dry-run to compact bloated tables.")
        cur.close()
        conn.close()
        return

    # Compact each table
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
