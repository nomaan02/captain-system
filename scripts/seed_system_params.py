# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
Task 1.7: Seed P3-D17 system_params with default values.

All parameters from Architecture §9 + V3 amendments.
Run after QuestDB schema is initialized.

Usage: python scripts/seed_system_params.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor


# System parameters with defaults from spec
SYSTEM_PARAMS = {
    # --- Capacity ---
    "max_users": {"value": 20, "category": "capacity"},
    "max_accounts_per_user": {"value": 10, "category": "capacity"},
    "max_assets": {"value": 50, "category": "capacity"},

    # --- Quality Thresholds (CALIBRATE from P1/P2 data before first live session) ---
    "quality_hard_floor": {"value": 0.003, "category": "quality"},
    "quality_ceiling": {"value": 0.010, "category": "quality"},
    "minimum_quality_threshold": {"value": 0.003, "category": "quality"},

    # --- Risk ---
    "max_silo_drawdown_pct": {"value": 0.30, "category": "risk"},
    "circuit_breaker_vix_threshold": {"value": 50, "category": "risk"},
    "circuit_breaker_data_hold_count": {"value": 3, "category": "risk"},
    "network_concentration_threshold": {"value": 0.80, "category": "risk"},

    # --- Execution ---
    "execution_mode": {"value": "MANUAL", "category": "execution"},
    "manual_halt_all": {"value": False, "category": "execution"},

    # --- Sizing ---
    "tsm_budget_divisor_default": {"value": 20, "category": "sizing"},
    "kelly_shrinkage_start": {"value": 0.5, "category": "sizing"},

    # --- AIM ---
    "aim_modifier_floor": {"value": 0.5, "category": "aim"},
    "aim_modifier_ceiling": {"value": 1.5, "category": "aim"},
    "aim_minimum_evaluation_period": {"value": 50, "category": "aim"},
    "aim_inclusion_threshold": {"value": 0.02, "category": "aim"},
    "aim_dormancy_threshold": {"value": 0.05, "category": "aim"},
    "aim_dormancy_days": {"value": 30, "category": "aim"},
    "aim_dominance_threshold": {"value": 0.30, "category": "aim"},

    # --- Offline ---
    "dma_forgetting_factor": {"value": 0.99, "category": "offline"},
    "bocpd_level2_threshold": {"value": 0.8, "category": "offline"},
    "bocpd_level3_threshold": {"value": 0.9, "category": "offline"},
    "bocpd_level3_consecutive_days": {"value": 5, "category": "offline"},
    "ewma_adaptive_span_min": {"value": 8, "category": "offline"},
    "ewma_adaptive_span_max": {"value": 30, "category": "offline"},
    "parallel_tracking_period_days": {"value": 20, "category": "offline"},
    "transition_phasing_window_days": {"value": 10, "category": "offline"},
    "tsm_simulation_iterations": {"value": 10000, "category": "offline"},
    "sensitivity_perturbation_range": {"value": 0.15, "category": "offline"},
    "pbo_rejection_threshold": {"value": 0.5, "category": "offline"},

    # --- Diagnostics ---
    "strategy_staleness_threshold_days": {"value": 180, "category": "diagnostics"},
    "oo_score_weakness_threshold": {"value": 0.55, "category": "diagnostics"},
    "edge_decline_alert_threshold": {"value": 0.15, "category": "diagnostics"},
    "action_item_stale_threshold_days": {"value": 90, "category": "diagnostics"},
    "pipeline_staleness_medium_days": {"value": 90, "category": "diagnostics"},
    "pipeline_staleness_high_days": {"value": 180, "category": "diagnostics"},
    "minimum_test_suite_size": {"value": 20, "category": "diagnostics"},

    # --- Infrastructure ---
    "system_timezone": {"value": "America/New_York", "category": "infrastructure"},
    "key_rotation_interval_days": {"value": 90, "category": "infrastructure"},
    "sod_reset_time": {"value": "19:00", "category": "infrastructure"},
}


def seed_system_params():
    """Insert all system parameters into P3-D17."""
    with get_cursor() as cur:
        count = 0
        for key, spec in SYSTEM_PARAMS.items():
            value = json.dumps(spec["value"]) if not isinstance(spec["value"], str) else spec["value"]
            try:
                cur.execute(
                    """INSERT INTO p3_d17_system_monitor_state
                       (param_key, param_value, category, last_updated)
                       VALUES (%s, %s, %s, now())""",
                    (key, value, spec["category"]),
                )
                count += 1
            except Exception as e:
                print(f"  [ERR] {key}: {e}")
        print(f"  [OK] Seeded {count}/{len(SYSTEM_PARAMS)} system parameters.")
    return count == len(SYSTEM_PARAMS)


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — System Parameters Seed (P3-D17)")
    print("=" * 60)
    success = seed_system_params()
    sys.exit(0 if success else 1)
