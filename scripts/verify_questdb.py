# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""QuestDB Schema Verification — run after init_questdb.py to confirm all tables exist.

Usage:
  1. Ensure QuestDB is running: docker compose up -d questdb
  2. Run init:   python scripts/init_questdb.py
  3. Run verify: python scripts/verify_questdb.py

Checks:
  - All expected tables exist
  - Each table has the expected columns
  - Reports any missing tables or column mismatches
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor

# Expected tables and their required columns (subset — key columns only)
EXPECTED_TABLES = {
    "p3_d00_asset_universe": [
        "asset_id", "captain_status", "locked_strategy", "point_value",
        "tick_size", "session_hours", "last_updated",
    ],
    "p3_d01_aim_model_states": [
        "aim_id", "asset_id", "status", "warmup_progress", "last_updated",
    ],
    "p3_d02_aim_meta_weights": [
        "aim_id", "asset_id", "inclusion_probability", "inclusion_flag", "last_updated",
    ],
    "p3_d03_trade_outcome_log": [
        "trade_id", "user_id", "account_id", "asset", "direction",
        "entry_price", "exit_price", "pnl", "commission", "outcome", "ts",
    ],
    "p3_d04_decay_detector_states": [
        "asset_id", "bocpd_cp_probability", "cusum_c_up_prev", "last_updated",
    ],
    "p3_d05_ewma_states": [
        "asset_id", "regime", "session", "win_rate", "avg_win", "avg_loss", "last_updated",
    ],
    "p3_d06_injection_history": [
        "injection_id", "asset", "recommendation", "ts",
    ],
    "p3_d06b_active_transitions": [
        "asset_id", "mode", "current_day", "total_days", "completed", "last_updated",
    ],
    "p3_d07_correlation_model_states": [
        "correlation_matrix", "last_updated",
    ],
    "p3_d08_tsm_state": [
        "account_id", "user_id", "starting_balance", "current_balance",
        "max_drawdown_limit", "max_daily_loss", "max_contracts",
        "topstep_optimisation", "topstep_params", "fee_schedule",
        "payout_rules", "scaling_plan_active", "last_updated",
    ],
    "p3_d09_report_archive": [
        "report_id", "report_type", "content", "user_id", "ts",
    ],
    "p3_d10_notification_log": [
        "notification_id", "user_id", "priority", "event_type",
        "gui_delivered", "telegram_delivered", "ts",
    ],
    "p3_d11_pseudotrader_results": [
        "result_id", "pbo", "dsr", "recommendation", "ts",
    ],
    "p3_d12_kelly_parameters": [
        "asset_id", "regime", "session", "kelly_full", "shrinkage_factor", "last_updated",
    ],
    "p3_d13_sensitivity_scan_results": [
        "asset_id", "robustness_status", "flags", "scan_date",
    ],
    "p3_d14_api_connection_states": [
        "account_id", "connection_status", "latency_ms", "last_updated",
    ],
    "p3_d15_user_session_data": [
        "user_id", "display_name", "role", "tags", "last_active",
    ],
    "p3_d16_user_capital_silos": [
        "user_id", "status", "starting_capital", "total_capital",
        "accounts", "telegram_chat_id", "last_updated",
    ],
    "p3_d17_system_monitor_state": [
        "param_key", "param_value", "category", "last_updated",
    ],
    "p3_d18_version_history": [
        "version_id", "component", "trigger", "state", "ts",
    ],
    "p3_offline_job_queue": [
        "job_id", "job_type", "asset_id", "status", "last_updated",
    ],
    "p3_d19_reconciliation_log": [
        "recon_id", "account_id", "user_id", "ts",
    ],
    # P3-D20 = SQLite WAL, not in QuestDB
    "p3_d21_incident_log": [
        "incident_id", "incident_type", "severity", "status", "ts",
    ],
    "p3_d22_system_health_diagnostic": [
        "mode", "scores", "overall_health", "action_queue", "ts",
    ],
    # V3 tables
    "p3_d23_circuit_breaker_intraday": [
        "account_id", "l_t", "n_t", "last_updated",
    ],
    "p3_d25_circuit_breaker_params": [
        "account_id", "model_m", "r_bar", "beta_b", "sigma", "rho_bar", "last_updated",
    ],
    "p3_d26_hmm_opportunity_state": [
        "hmm_params", "current_state_probs", "opportunity_weights",
        "cold_start", "last_updated",
    ],
    # Auxiliary tables
    "p3_session_event_log": [
        "user_id", "event_type", "event_id", "ts",
    ],
    "p3_d28_account_lifecycle": [
        "event_id", "account_id", "event_type", "from_stage", "to_stage", "ts",
    ],
}


def verify_questdb():
    """Verify all expected tables exist with correct columns."""
    print("=" * 60)
    print("CAPTAIN FUNCTION — QuestDB Schema Verification")
    print(f"Checking {len(EXPECTED_TABLES)} expected tables")
    print("=" * 60)

    passed = 0
    failed = 0
    warnings = 0

    with get_cursor() as cur:
        # Get all tables in QuestDB
        cur.execute("SELECT table_name FROM tables();")
        existing_tables = {row[0] for row in cur.fetchall()}

        print(f"\nFound {len(existing_tables)} tables in QuestDB\n")

        for table_name, expected_cols in sorted(EXPECTED_TABLES.items()):
            if table_name not in existing_tables:
                print(f"  [FAIL] {table_name} — TABLE MISSING")
                failed += 1
                continue

            # Check columns
            cur.execute(f"SELECT \"column\" FROM table_columns('{table_name}');")
            actual_cols = {row[0] for row in cur.fetchall()}

            missing_cols = [c for c in expected_cols if c not in actual_cols]

            if missing_cols:
                print(f"  [WARN] {table_name} — missing columns: {missing_cols}")
                warnings += 1
            else:
                print(f"  [ OK ] {table_name} ({len(actual_cols)} columns)")
                passed += 1

        # Check for unexpected tables (not in our expected list)
        expected_names = set(EXPECTED_TABLES.keys())
        extra_tables = existing_tables - expected_names
        if extra_tables:
            print(f"\n  Extra tables (not in spec): {sorted(extra_tables)}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} OK, {warnings} WARN, {failed} FAIL")
    print(f"Total expected: {len(EXPECTED_TABLES)}")
    print("=" * 60)

    if failed > 0:
        print("\nACTION: Run 'python scripts/init_questdb.py' to create missing tables")
        return False
    if warnings > 0:
        print("\nWARNING: Some tables have missing columns — may need schema update")
        return False

    print("\nAll tables verified successfully.")
    return True


if __name__ == "__main__":
    try:
        success = verify_questdb()
    except Exception as e:
        print(f"\nFATAL: Cannot connect to QuestDB — {e}")
        print("Make sure QuestDB is running: docker compose up -d questdb")
        sys.exit(1)

    sys.exit(0 if success else 1)
