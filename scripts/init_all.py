# region imports
from AlgorithmImports import *
# endregion
"""
Master initialization script — runs all Phase 1 setup in order.

Prerequisites: docker-compose up -d (QuestDB + Redis must be healthy)

Usage: python scripts/init_all.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def wait_for_questdb(max_wait=60):
    """Wait for QuestDB to accept connections."""
    from shared.questdb_client import get_connection
    print("\nWaiting for QuestDB...")
    for i in range(max_wait):
        try:
            conn = get_connection()
            conn.close()
            print("  [OK] QuestDB is ready.")
            return True
        except Exception:
            time.sleep(1)
    print("  [FAIL] QuestDB not ready after 60s.")
    return False


def wait_for_redis(max_wait=30):
    """Wait for Redis to accept connections."""
    from shared.redis_client import get_redis_client
    print("\nWaiting for Redis...")
    for i in range(max_wait):
        try:
            client = get_redis_client()
            client.ping()
            print("  [OK] Redis is ready.")
            return True
        except Exception:
            time.sleep(1)
    print("  [FAIL] Redis not ready after 30s.")
    return False


def main():
    print("=" * 60)
    print("CAPTAIN FUNCTION — Phase 1 Full Initialization")
    print("=" * 60)

    # Step 1: Wait for infrastructure
    if not wait_for_questdb():
        sys.exit(1)
    if not wait_for_redis():
        sys.exit(1)

    # Step 2: Create QuestDB tables (Task 1.2 + 1.2b)
    print("\n--- Task 1.2/1.2b: QuestDB Schema ---")
    from scripts.init_questdb import init_questdb
    if not init_questdb():
        print("[FAIL] QuestDB schema creation failed.")
        sys.exit(1)

    # Step 3: Initialize SQLite journals (Task 1.5)
    print("\n--- Task 1.5: SQLite WAL Journals ---")
    from scripts.init_sqlite import init_journal
    for process in ["captain-offline", "captain-online", "captain-command"]:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), process, "journal.sqlite")
        init_journal(path)

    # Step 4: Seed system parameters (Task 1.7)
    print("\n--- Task 1.7: System Parameters ---")
    from scripts.seed_system_params import seed_system_params
    seed_system_params()

    # Step 5: Verify compliance gate (Task 1.8)
    print("\n--- Task 1.8: Compliance Gate ---")
    gate_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "compliance_gate.json")
    if os.path.exists(gate_path):
        import json
        with open(gate_path) as f:
            gate = json.load(f)
        all_false = all(v is False for k, v in gate.items() if not k.startswith("_"))
        if all_false:
            print(f"  [OK] Compliance gate: {sum(1 for k in gate if not k.startswith('_'))} requirements, all false")
        else:
            print("  [WARN] Some compliance gate values are true!")
    else:
        print(f"  [FAIL] Missing: {gate_path}")

    # Step 6: Seed test asset + user (Task 1.9)
    print("\n--- Task 1.9: Test Asset + User Seed ---")
    from scripts.seed_test_asset import seed_es_asset, seed_primary_user, seed_capital_silo
    seed_es_asset()
    seed_primary_user()
    seed_capital_silo()

    # Step 7: Verification summary
    print("\n" + "=" * 60)
    print("PHASE 1 INITIALIZATION SUMMARY")
    print("=" * 60)
    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute("SELECT count() FROM tables()")
        table_count = cur.fetchone()[0]
        print(f"  QuestDB tables: {table_count}")

        cur.execute("SELECT count() FROM p3_d17_system_monitor_state")
        param_count = cur.fetchone()[0]
        print(f"  System params seeded: {param_count}")

        cur.execute("SELECT count() FROM p3_d00_asset_universe")
        asset_count = cur.fetchone()[0]
        print(f"  Assets in universe: {asset_count}")

        cur.execute("SELECT count() FROM p3_d15_user_session_data")
        user_count = cur.fetchone()[0]
        print(f"  Users: {user_count}")

    from shared.redis_client import get_redis_client
    client = get_redis_client()
    print(f"  Redis: {'connected' if client.ping() else 'FAILED'}")

    print("\n[DONE] Phase 1 initialization complete.")
    print("Next: docker-compose up -> verify all 6 containers healthy -> Phase 2")


if __name__ == "__main__":
    main()
