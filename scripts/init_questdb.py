# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""
QuestDB Schema Initialization — 30 tables for Captain Function (Program 3).

23 original tables (P3-D00 through P3-D22, excluding D20 = SQLite WAL)
+ 3 V3 tables (P3-D23, P3-D25, P3-D26)
+ 2 auxiliary tables (p3_session_event_log, p3_d28_account_lifecycle)
+ 2 replay tables (p3_replay_results, p3_replay_presets)

Run this script after QuestDB container is healthy to create all tables.
Usage: python scripts/init_questdb.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor


# --- Table definitions ---
# QuestDB uses a subset of SQL. Key types:
#   SYMBOL = indexed string (for asset_id, user_id, account_id)
#   STRING = unindexed string (for JSON blobs, free text)
#   TIMESTAMP = microsecond precision timestamp
#   DOUBLE = 64-bit float
#   INT = 32-bit integer
#   LONG = 64-bit integer
#   BOOLEAN = true/false

TABLES = [
    # =====================================================================
    # P3-D00: asset_universe_register
    # Owner: Command | Readers: Online B1, Offline bootstrap
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d00_asset_universe (
        asset_id SYMBOL,
        p1_status STRING,
        p2_status STRING,
        captain_status STRING,
        warm_up_progress DOUBLE,
        aim_warmup_progress STRING,
        locked_strategy STRING,
        roll_calendar STRING,
        exchange_timezone STRING,
        point_value DOUBLE,
        tick_size DOUBLE,
        margin_per_contract DOUBLE,
        session_hours STRING,
        session_schedule STRING,
        p1_data_path STRING,
        p2_data_path STRING,
        data_sources STRING,
        data_quality_flag STRING,
        created TIMESTAMP,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D01: aim_model_states
    # Owner: Offline B1
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d01_aim_model_states (
        aim_id INT,
        asset_id SYMBOL,
        status STRING,
        model_object STRING,
        warmup_progress DOUBLE,
        current_modifier STRING,
        last_retrained TIMESTAMP,
        missing_data_rate_30d DOUBLE,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D02: aim_meta_weights
    # Owner: Offline B1
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d02_aim_meta_weights (
        aim_id INT,
        asset_id SYMBOL,
        inclusion_probability DOUBLE,
        inclusion_flag BOOLEAN,
        recent_effectiveness DOUBLE,
        days_below_threshold INT,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D03: trade_outcome_log
    # Owner: Online B7 -> Offline
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d03_trade_outcome_log (
        trade_id STRING,
        user_id SYMBOL,
        account_id SYMBOL,
        asset SYMBOL,
        direction INT,
        entry_price DOUBLE,
        signal_entry_price DOUBLE,
        exit_price DOUBLE,
        contracts INT,
        gross_pnl DOUBLE,
        commission DOUBLE,
        pnl DOUBLE,
        slippage DOUBLE,
        outcome STRING,
        entry_time TIMESTAMP,
        exit_time TIMESTAMP,
        regime_at_entry STRING,
        aim_modifier_at_entry DOUBLE,
        aim_breakdown_at_entry STRING,
        session INT,
        tsm_used STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY DAY;
    """,

    # =====================================================================
    # P3-D04: decay_detector_states
    # Owner: Offline B2
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d04_decay_detector_states (
        asset_id SYMBOL,
        bocpd_run_length_posterior STRING,
        bocpd_cp_probability DOUBLE,
        bocpd_cp_history STRING,
        cusum_c_up_prev DOUBLE,
        cusum_c_down_prev DOUBLE,
        cusum_sprint_length INT,
        cusum_allowance DOUBLE,
        cusum_sequential_limits STRING,
        adwin_states STRING,
        decay_events STRING,
        current_changepoint_probability DOUBLE,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D05: ewma_states
    # Owner: Offline B8
    # Indexed by: asset_id x regime x session
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d05_ewma_states (
        asset_id SYMBOL,
        regime STRING,
        session INT,
        win_rate DOUBLE,
        avg_win DOUBLE,
        avg_loss DOUBLE,
        n_trades INT,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D06: injection_history
    # Owner: Offline B4 / Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d06_injection_history (
        injection_id STRING,
        asset SYMBOL,
        candidate STRING,
        current_strategy STRING,
        expected_new DOUBLE,
        expected_current DOUBLE,
        pseudo_results STRING,
        recommendation STRING,
        status STRING,
        injection_type STRING,
        outcome STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D06B: active_strategy_transitions
    # Owner: Offline B4 (TransitionPhaser persistence)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d06b_active_transitions (
        asset_id SYMBOL,
        mode STRING,
        new_strategy STRING,
        old_strategy STRING,
        current_day INT,
        total_days INT,
        completed BOOLEAN,
        started_at TIMESTAMP,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D07: correlation_model_states
    # Owner: Offline
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d07_correlation_model_states (
        correlation_matrix STRING,
        dcc_parameters STRING,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D08: tsm_files (runtime state per account)
    # Owner: Command
    # V3: added topstep_optimisation, topstep_params, topstep_state,
    #     fee_schedule, payout_rules, scaling_plan_active, scaling_tier_micros
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d08_tsm_state (
        account_id SYMBOL,
        user_id SYMBOL,
        name STRING,
        classification STRING,
        starting_balance DOUBLE,
        current_balance DOUBLE,
        current_drawdown DOUBLE,
        daily_loss_used DOUBLE,
        profit_target DOUBLE,
        max_drawdown_limit DOUBLE,
        max_daily_loss DOUBLE,
        max_contracts INT,
        scaling_plan STRING,
        commission_per_contract DOUBLE,
        instrument_permissions STRING,
        overnight_allowed BOOLEAN,
        trading_hours STRING,
        margin_per_contract DOUBLE,
        margin_buffer_pct DOUBLE,
        pass_probability DOUBLE,
        simulation_date TIMESTAMP,
        risk_goal STRING,
        evaluation_end_date TIMESTAMP,
        evaluation_stages STRING,
        topstep_optimisation BOOLEAN,
        topstep_params STRING,
        topstep_state STRING,
        fee_schedule STRING,
        payout_rules STRING,
        scaling_plan_active BOOLEAN,
        scaling_tier_micros INT,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D09: report_archive
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d09_report_archive (
        report_id STRING,
        report_type STRING,
        generated_at TIMESTAMP,
        content STRING,
        user_id SYMBOL,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D10: notification_log
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d10_notification_log (
        notification_id STRING,
        user_id SYMBOL,
        priority STRING,
        event_type STRING,
        asset SYMBOL,
        message STRING,
        action_required BOOLEAN,
        gui_delivered BOOLEAN,
        gui_read BOOLEAN,
        gui_read_at TIMESTAMP,
        telegram_delivered BOOLEAN,
        telegram_read BOOLEAN,
        email_delivered BOOLEAN,
        user_response STRING,
        response_at TIMESTAMP,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY DAY;
    """,

    # =====================================================================
    # P3-D11: pseudotrader_results
    # Owner: Offline B3
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d11_pseudotrader_results (
        result_id STRING,
        update_type STRING,
        sharpe_improvement DOUBLE,
        drawdown_change DOUBLE,
        winrate_delta DOUBLE,
        pbo DOUBLE,
        dsr DOUBLE,
        recommendation STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D12: kelly_parameters
    # Owner: Offline B8
    # Indexed by: asset_id x regime x session
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d12_kelly_parameters (
        asset_id SYMBOL,
        regime STRING,
        session INT,
        kelly_full DOUBLE,
        shrinkage_factor DOUBLE,
        sizing_override STRING,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D13: sensitivity_scan_results
    # Owner: Offline B5
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d13_sensitivity_scan_results (
        asset_id SYMBOL,
        sharpe_stability DOUBLE,
        pbo DOUBLE,
        dsr DOUBLE,
        adjusted_sharpe DOUBLE,
        robustness_status STRING,
        flags STRING,
        perturbation_grid_results STRING,
        scan_date TIMESTAMP
    ) timestamp(scan_date);
    """,

    # =====================================================================
    # P3-D14: api_connection_states
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d14_api_connection_states (
        account_id SYMBOL,
        adapter_type STRING,
        connection_status STRING,
        last_heartbeat TIMESTAMP,
        latency_ms DOUBLE,
        error_log STRING,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D15: user_session_data
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d15_user_session_data (
        user_id SYMBOL,
        display_name STRING,
        auth_token STRING,
        role STRING,
        tags STRING,
        device_sessions STRING,
        preferences STRING,
        created TIMESTAMP,
        last_active TIMESTAMP
    ) timestamp(last_active);
    """,

    # =====================================================================
    # P3-D16: user_capital_silos
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d16_user_capital_silos (
        user_id SYMBOL,
        status SYMBOL,
        role SYMBOL,
        starting_capital DOUBLE,
        total_capital DOUBLE,
        accounts STRING,
        max_simultaneous_positions INT,
        max_portfolio_risk_pct DOUBLE,
        correlation_threshold DOUBLE,
        user_kelly_ceiling DOUBLE,
        capital_history STRING,
        telegram_chat_id STRING,
        created TIMESTAMP,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D17: system_monitor_state
    # Owner: Online/Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d17_system_monitor_state (
        param_key STRING,
        param_value STRING,
        category STRING,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D18: version_history_store
    # Owner: Offline
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d18_version_history (
        version_id STRING,
        component STRING,
        trigger STRING,
        state STRING,
        model_hash STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # Offline Job Queue
    # Owner: Offline orchestrator
    # Jobs enqueued by Level 3 decay, scheduled tasks, or manual triggers
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_offline_job_queue (
        job_id STRING,
        job_type STRING,
        asset_id SYMBOL,
        priority STRING,
        status STRING,
        params STRING,
        result STRING,
        error STRING,
        created_at TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D19: reconciliation_log
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d19_reconciliation_log (
        recon_id STRING,
        account_id SYMBOL,
        user_id SYMBOL,
        source STRING,
        mismatches STRING,
        corrected BOOLEAN,
        status STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # P3-D20: SQLite WAL — NOT in QuestDB (see init_sqlite.py)

    # =====================================================================
    # P3-D21: incident_log
    # Owner: Command
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d21_incident_log (
        incident_id STRING,
        incident_type STRING,
        severity STRING,
        component STRING,
        details STRING,
        affected_users STRING,
        system_snapshot STRING,
        status STRING,
        resolution STRING,
        root_cause STRING,
        resolved_by STRING,
        resolved_at TIMESTAMP,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D22: system_health_diagnostic
    # Owner: Offline B9
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d22_system_health_diagnostic (
        mode STRING,
        scores STRING,
        overall_health DOUBLE,
        action_items_generated INT,
        critical_count INT,
        high_count INT,
        queue_total INT,
        open_count INT,
        stale_count INT,
        action_queue STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # V3 TABLES
    # =====================================================================

    # =====================================================================
    # P3-D23: circuit_breaker_intraday_state
    # Owner: Online B7B / Command B8 (reset at 19:00 EST)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d23_circuit_breaker_intraday (
        account_id SYMBOL,
        l_t DOUBLE,
        n_t INT,
        l_b STRING,
        n_b STRING,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D25: circuit_breaker_params
    # Owner: Offline B8 (PG-16C)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d25_circuit_breaker_params (
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
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # P3-D26: hmm_opportunity_state
    # Owner: Offline B1 (PG-01C) / Online B5 (read)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d26_hmm_opportunity_state (
        hmm_params STRING,
        current_state_probs STRING,
        opportunity_weights STRING,
        prior_alpha STRING,
        last_trained TIMESTAMP,
        training_window INT,
        n_observations INT,
        cold_start BOOLEAN,
        last_updated TIMESTAMP
    ) timestamp(last_updated);
    """,

    # =====================================================================
    # p3_session_event_log — Command-side audit trail
    # Used by Command B1, B5, B7, B8 for event logging (signals received,
    # trade confirmations, TSM switches, concentration responses, etc.)
    # Separate from P3-D17 (which is a key-value system parameter store).
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_session_event_log (
        user_id SYMBOL,
        event_type STRING,
        event_id STRING,
        asset SYMBOL,
        details STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY DAY;
    """,

    # =====================================================================
    # P3-D27: pseudotrader_forecasts (Two-forecast structure)
    # Owner: Offline B3 pseudotrader
    # Stores: Forecast A (full history) + Forecast B (rolling 252-day)
    # Spec: Pseudotrader_Account_Awareness_Amendment.md Sec 5
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d27_pseudotrader_forecasts (
        forecast_id STRING,
        forecast_type STRING,
        account_id SYMBOL,
        version STRING,
        run_date STRING,
        window_start STRING,
        window_end STRING,
        metrics STRING,
        equity_curve STRING,
        system_state STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D28: account_lifecycle
    # Owner: Shared (Offline B3 pseudotrader, Command B8 reconciliation)
    # Tracks: stage transitions, failures, fees, payouts, resets
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d28_account_lifecycle (
        event_id STRING,
        account_id SYMBOL,
        user_id SYMBOL,
        event_type STRING,
        from_stage STRING,
        to_stage STRING,
        trigger STRING,
        balance_at_event DOUBLE,
        fee_charged DOUBLE,
        payout_amount DOUBLE,
        payout_net DOUBLE,
        payouts_taken INT,
        tradable_balance DOUBLE,
        reserve_balance DOUBLE,
        details STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # p3_spread_history: AIM-12 trailing spread data for z-score
    # Owner: Online B1 (feature computation)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_spread_history (
        asset_id SYMBOL,
        session_id INT,
        spread DOUBLE,
        timestamp TIMESTAMP
    ) timestamp(timestamp) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D29: opening_volumes
    # Owner: Online (bootstrap + post-OR-close daily write)
    # AIM-15 spec: compare today's first-m-min volume to 20-day avg
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d29_opening_volumes (
        asset_id SYMBOL,
        session_date STRING,
        session_type STRING,
        or_minutes INT,
        volume_first_m_min LONG,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # p3_d30_daily_ohlcv: Historical daily OHLCV for AIM feature baselines
    # Owner: Online (bootstrap from QC + daily write after session close)
    # Powers: AIM-08 correlation z-score, AIM-09 momentum, overnight returns
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d30_daily_ohlcv (
        asset_id SYMBOL,
        trade_date STRING,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        volume LONG,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY YEAR;
    """,

    # =====================================================================
    # p3_replay_results: Signal replay analysis results
    # Owner: Command (replay engine)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_replay_results (
        replay_id STRING,
        user_id SYMBOL,
        replay_date STRING,
        session_type SYMBOL,
        config STRING,
        results STRING,
        summary STRING,
        comparison STRING,
        created TIMESTAMP,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,

    # =====================================================================
    # p3_replay_presets: Saved replay configuration presets
    # Owner: Command (replay engine)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_replay_presets (
        preset_id STRING,
        user_id SYMBOL,
        name STRING,
        config STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY YEAR;
    """,
    # =====================================================================
    # P3-D31: implied_vol — ATM IV + realised vol for AIM-01 VRP
    # Owner: Bootstrap (QC extract) + future daily append
    # Powers: AIM-01 VRP modifier (IV - RV z-score)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d31_implied_vol (
        asset_id SYMBOL,
        trade_date TIMESTAMP,
        atm_iv_30d DOUBLE,
        realized_vol_20d DOUBLE,
        vrp DOUBLE,
        ts TIMESTAMP
    ) timestamp(trade_date) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D32: options_skew — CBOE SKEW for AIM-02
    # Owner: Bootstrap (QC extract) + future daily append
    # Powers: AIM-02 skew half (60d z-score)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d32_options_skew (
        asset_id SYMBOL,
        trade_date TIMESTAMP,
        cboe_skew DOUBLE,
        skew_spread_proxy DOUBLE,
        ts TIMESTAMP
    ) timestamp(trade_date) PARTITION BY MONTH;
    """,

    # =====================================================================
    # P3-D33: opening_volatility — 5-min OR vol for AIM-12 vol_z
    # Owner: Online orchestrator (post-OR-close) + bootstrap from QC
    # Powers: AIM-12 vol_z half (60d z-score)
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_d33_opening_volatility (
        asset_id SYMBOL,
        session_date TIMESTAMP,
        session_type SYMBOL,
        or_minutes INT,
        opening_range_pct DOUBLE,
        opening_vol_z DOUBLE,
        ts TIMESTAMP
    ) timestamp(session_date) PARTITION BY MONTH;
    """,

    # =====================================================================
    # p3_audit_log: User action audit trail (Doc 19 §10)
    # Owner: Command API
    # Fields: user_id, action, old_value, new_value
    # =====================================================================
    """
    CREATE TABLE IF NOT EXISTS p3_audit_log (
        user_id SYMBOL,
        action STRING,
        detail STRING,
        old_value STRING,
        new_value STRING,
        ts TIMESTAMP
    ) timestamp(ts) PARTITION BY MONTH;
    """,
]


def init_questdb():
    """Create all 31 QuestDB tables (D00-D22 excl D20, plus D23, D25, D26, D27, D28, session_event_log, job_queue, spread_history, replay_results, replay_presets)."""
    with get_cursor() as cur:
        created = 0
        for i, ddl in enumerate(TABLES):
            table_name = ddl.strip().split("(")[0].split()[-1]
            try:
                cur.execute(ddl.strip())
                print(f"  [OK] {table_name}")
                created += 1
            except Exception as e:
                print(f"  [ERR] {table_name}: {e}")

        print(f"\nCreated {created}/{len(TABLES)} tables.")
    return created == len(TABLES)


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — QuestDB Schema Initialization")
    print("30 tables (23 original + 3 V3 + 2 auxiliary + 2 replay)")
    print("=" * 60)
    success = init_questdb()
    sys.exit(0 if success else 1)
