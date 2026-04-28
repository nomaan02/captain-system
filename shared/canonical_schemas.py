"""Canonical QuestDB schemas for Captain Function — fresh-start bootstrap.

Single source of truth for every QuestDB table used by captain-offline,
captain-online, and captain-command. Produced 2026-04-20 from a
read-only audit of init_questdb.py, compact_questdb_tables.py, and every
INSERT / SELECT / LATEST ON site across the three services + shared/ + scripts/.

See `.schema-audit.md` at repo root for the full inventory, the
discrepancies this file resolves, and the ones it flags as breaks-codebase.

## Design rules applied

1. Columns, types, and nullability match what application code actually
   writes today. Partial-INSERT call sites still work because QuestDB
   fills omitted columns with NULL.
2. Every table has PARTITION BY — state tables with few rows use MONTH
   to avoid empty-partition overhead; hot tick/heartbeat tables use DAY
   so old partitions can be dropped cheaply.
3. Every table has WAL except `p3_audit_log` (see inline note).
4. Every table has DEDUP UPSERT KEYS(<designated_ts>, <natural_key...>)
   except `p3_audit_log` (append-only journal) and `p3_offline_job_queue`
   (rows are state-transition history, not dedupable).
5. DDL is compatible with QuestDB 9.3.3 (IF NOT EXISTS, WAL, DEDUP UPSERT KEYS).
6. This module defines DDL strings only — no connection logic. Consumers
   (init_questdb.py, fresh-start bootstrap) import CANONICAL_DDLS and run
   each string through their own cursor.

## Discrepancies resolved here (see audit doc for full reasoning)

- D02: uses inclusion_probability/inclusion_flag/recent_effectiveness/
  days_below_threshold per every INSERT site. The 7-col schema in
  compact_questdb_tables.py (weight/dma_score/trend/...) is abandoned —
  no live writer or reader uses it.
- D01, D02, D04..D08, D12..D17, D23, D25, D26, p3_offline_job_queue:
  add PARTITION BY MONTH (init_questdb.py left these unpartitioned,
  causing the 4.3M-row D01 bloat observed 2026-04-15).
- D14: PARTITION BY DAY (heartbeat writes every tick).
- D23: PARTITION BY DAY (resets at 19:00 EST).
- All tables get WAL (init had none — required for concurrent INSERT from
  three processes) and DEDUP UPSERT KEYS (init had none — every UPSERT
  appended a duplicate row).

## Discrepancies flagged, NOT fixed here

These need an application-code change before the canonical DDL matches
what the codebase emits. Each is called out in `.schema-audit.md` with
the exact file:line and a one-line suggested patch. Left for a follow-up
session.

- D21 `p3_d21_incident_log` column name: canonical uses `timestamp` (4
  sites write/read `timestamp`: b9_incident_response.py:186, :360 and
  SELECTs at :230,:255 + b2_gui_data_server.py:963). ONE site writes
  `ts` — captain-online/.../b1_data_ingestion.py:692. That INSERT will
  fail under canonical DDL until the column name is flipped to
  `timestamp`. Deliberately chosen: majority-usage wins.

- D33 `p3_d33_opening_volatility.session_date` type: canonical keeps
  TIMESTAMP (matches init_questdb + the qc bootstrap script which passes
  a real timestamp). captain-online/.../b1_features.py:1278 writes
  today's date as a *string* ("YYYY-MM-DD"), which falls on QuestDB's
  implicit STRING→TIMESTAMP cast. Flagged: swap to `now()` or a parsed
  TIMESTAMP at the call site.

- D30, D29 session_date / trade_date: left as STRING (matches every
  INSERT site today). Upgrading to TIMESTAMP would require rewriting the
  qc bootstrap scripts and every downstream SELECT that string-compares
  dates. Out of scope for this session.
"""

from __future__ import annotations


# --------------------------------------------------------------------- #
# Reference / slow-moving state tables (PARTITION BY MONTH)
# --------------------------------------------------------------------- #

D00_ASSET_UNIVERSE = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset_id);
"""

D01_AIM_MODEL_STATES = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, aim_id, asset_id);
"""

D02_AIM_META_WEIGHTS = """
CREATE TABLE IF NOT EXISTS p3_d02_aim_meta_weights (
    aim_id INT,
    asset_id SYMBOL,
    inclusion_probability DOUBLE,
    inclusion_flag BOOLEAN,
    recent_effectiveness DOUBLE,
    days_below_threshold INT,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, aim_id, asset_id);
"""

D04_DECAY_DETECTOR_STATES = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset_id);
"""

D05_EWMA_STATES = """
CREATE TABLE IF NOT EXISTS p3_d05_ewma_states (
    asset_id SYMBOL,
    regime STRING,
    session INT,
    win_rate DOUBLE,
    avg_win DOUBLE,
    avg_loss DOUBLE,
    n_trades INT,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset_id, regime, session);
"""

D06B_ACTIVE_TRANSITIONS = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset_id);
"""

D07_CORRELATION_MODEL_STATES = """
CREATE TABLE IF NOT EXISTS p3_d07_correlation_model_states (
    correlation_matrix STRING,
    dcc_parameters STRING,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated);
"""

# --------------------------------------------------------------------- #
# P2 research output tables (read-only at runtime; populated by P1/P2   #
# pipeline reruns or the offline seed scripts)                           #
# --------------------------------------------------------------------- #
#
# Phase 1: table created empty. Online B1 still synthesises regime model
# params from p3_d00_asset_universe.locked_strategy (deferred to Phase 7).
# When Phase 7 ships, _load_regime_models() switches to SELECT FROM this table.
P2_D07_REGIME_MODELS = """
CREATE TABLE IF NOT EXISTS p2_d07_regime_models (
    asset                SYMBOL,
    model_type           STRING,
    feature_list         STRING,
    pettersson_threshold DOUBLE,
    regime_label         STRING,
    training_period      STRING,
    n_training_obs       INT,
    best_hyperparams     STRING,
    cv_score             DOUBLE,
    trained_at           TIMESTAMP,
    last_updated         TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset);
"""

D08_TSM_STATE = """
CREATE TABLE IF NOT EXISTS p3_d08_tsm_state (
    account_id SYMBOL,
    user_id SYMBOL,
    name STRING,
    classification STRING,
    starting_balance DECIMAL(18, 2),
    current_balance DECIMAL(18, 2),
    current_drawdown DECIMAL(18, 2),
    daily_loss_used DECIMAL(18, 2),
    profit_target DECIMAL(18, 2),
    max_drawdown_limit DECIMAL(18, 2),
    max_daily_loss DECIMAL(18, 2),
    max_contracts INT,
    scaling_plan STRING,
    commission_per_contract DECIMAL(18, 2),
    instrument_permissions STRING,
    overnight_allowed BOOLEAN,
    trading_hours STRING,
    margin_per_contract DECIMAL(18, 2),
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, account_id);
"""

D12_KELLY_PARAMETERS = """
CREATE TABLE IF NOT EXISTS p3_d12_kelly_parameters (
    asset_id SYMBOL,
    regime STRING,
    session INT,
    kelly_full DOUBLE,
    shrinkage_factor DOUBLE,
    sizing_override STRING,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset_id, regime, session);
"""

D13_SENSITIVITY_SCAN_RESULTS = """
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
) TIMESTAMP(scan_date) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(scan_date, asset_id);
"""

D15_USER_SESSION_DATA = """
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
) TIMESTAMP(last_active) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_active, user_id);
"""

D16_USER_CAPITAL_SILOS = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, user_id);
"""

D17_SYSTEM_MONITOR_STATE = """
CREATE TABLE IF NOT EXISTS p3_d17_system_monitor_state (
    param_key STRING,
    param_value STRING,
    category STRING,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, param_key);
"""

D25_CIRCUIT_BREAKER_PARAMS = """
CREATE TABLE IF NOT EXISTS p3_d25_circuit_breaker_params (
    account_id SYMBOL,
    model_m INT,
    r_bar DOUBLE,
    beta_b DOUBLE,
    sigma DOUBLE,
    rho_bar DOUBLE,
    n_observations INT,
    p_value DOUBLE,
    l_star DECIMAL(18, 2),
    cold_start BOOLEAN,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, account_id);
"""

# Q-27 RATIFIED 2026-04-27 — column set matches decisions log §4.3 exactly.
# Canonical name: p3_d26_hmm_opportunity_state (decisions doc uses shorthand
# "p3_d26_hmm_states" — per Q-02 code name is authoritative).
# Writer split (Q-11): confirmed Phase 10 plan — merge implemented in Batch 10.4+
# (`save_hmm_state` offline merges inference columns from prior LATEST row):
#   offline PG-01C → hmm_params, training_window, n_observations, last_trained,
#                    cold_start (training-derived)
#   online PG-23/PG-25B → current_state_probs, opportunity_weights,
#                          prior_alpha ([CONFIRM] smoothing carry), last_updated (inference)
D26_HMM_OPPORTUNITY_STATE = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated);
"""


# --------------------------------------------------------------------- #
# Hot heartbeat / per-session state (PARTITION BY DAY)
# --------------------------------------------------------------------- #

D14_API_CONNECTION_STATES = """
CREATE TABLE IF NOT EXISTS p3_d14_api_connection_states (
    account_id SYMBOL,
    adapter_type STRING,
    connection_status STRING,
    last_heartbeat TIMESTAMP,
    latency_ms DOUBLE,
    error_log STRING,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(last_updated, account_id);
"""

D23_CIRCUIT_BREAKER_INTRADAY = """
CREATE TABLE IF NOT EXISTS p3_d23_circuit_breaker_intraday (
    account_id SYMBOL,
    l_t DECIMAL(18, 2),
    n_t INT,
    l_b STRING,
    n_b STRING,
    last_updated TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(last_updated, account_id);
"""


# --------------------------------------------------------------------- #
# Event / log tables (PARTITION BY DAY or MONTH depending on volume)
# --------------------------------------------------------------------- #

D03_TRADE_OUTCOME_LOG = """
CREATE TABLE IF NOT EXISTS p3_d03_trade_outcome_log (
    trade_id STRING,
    signal_id STRING,
    user_id SYMBOL,
    account_id SYMBOL,
    asset SYMBOL,
    direction INT,
    entry_price DECIMAL(14, 4),
    signal_entry_price DECIMAL(14, 4),
    exit_price DECIMAL(14, 4),
    contracts INT,
    gross_pnl DECIMAL(18, 4),
    commission DECIMAL(18, 4),
    pnl DECIMAL(18, 4),
    slippage DECIMAL(18, 4),
    outcome STRING,
    entry_time TIMESTAMP,
    exit_time TIMESTAMP,
    regime_at_entry STRING,
    aim_modifier_at_entry DOUBLE,
    aim_breakdown_at_entry STRING,
    session INT,
    tsm_used STRING,
    model_m INT,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, trade_id);
"""

D06_INJECTION_HISTORY = """
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
    pbo DOUBLE,
    dsr DOUBLE,
    transition_days INT,
    tracking_days INT,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, injection_id);
"""

D09_REPORT_ARCHIVE = """
CREATE TABLE IF NOT EXISTS p3_d09_report_archive (
    report_id STRING,
    report_type STRING,
    generated_at TIMESTAMP,
    content STRING,
    user_id SYMBOL,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, report_id);
"""

D10_NOTIFICATION_LOG = """
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
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, notification_id);
"""

D11_PSEUDOTRADER_RESULTS = """
CREATE TABLE IF NOT EXISTS p3_d11_pseudotrader_results (
    result_id STRING,
    update_type STRING,
    sharpe_baseline DOUBLE,
    sharpe_updated DOUBLE,
    sharpe_improvement DOUBLE,
    drawdown_change DOUBLE,
    winrate_delta DOUBLE,
    pbo DOUBLE,
    dsr DOUBLE,
    recommendation STRING,
    pair_series STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, result_id);
"""

D18_VERSION_HISTORY = """
CREATE TABLE IF NOT EXISTS p3_d18_version_history (
    version_id STRING,
    component STRING,
    trigger STRING,
    state STRING,
    model_hash STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, version_id);
"""

D19_RECONCILIATION_LOG = """
CREATE TABLE IF NOT EXISTS p3_d19_reconciliation_log (
    recon_id STRING,
    account_id SYMBOL,
    user_id SYMBOL,
    source STRING,
    mismatches STRING,
    corrected BOOLEAN,
    status STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, recon_id);
"""

# D21: column is `timestamp` (matches 4 of 5 codebase sites). The lone
# outlier — captain-online/.../b1_data_ingestion.py:692 — writes `ts`
# and will fail until patched. Flagged in .schema-audit.md.
D21_INCIDENT_LOG = """
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
    timestamp TIMESTAMP
) TIMESTAMP(timestamp) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(timestamp, incident_id);
"""

D22_SYSTEM_HEALTH_DIAGNOSTIC = """
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
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts);
"""

D22B_ASSET_RERUN_STATUS = """
CREATE TABLE IF NOT EXISTS p3_d22b_asset_rerun_status (
    asset                SYMBOL,
    last_p1p2_rerun_ts   TIMESTAMP,
    rerun_trigger        STRING,
    last_updated         TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(asset, last_updated);
"""

D27_PSEUDOTRADER_FORECASTS = """
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
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, forecast_id);
"""

# D28: table is defined but no live code path references it today. Kept
# in canonical because bootstrap + compaction scripts both create it, and
# account_lifecycle.py integration is planned. DEDUP on (ts, event_id).
D28_ACCOUNT_LIFECYCLE = """
CREATE TABLE IF NOT EXISTS p3_d28_account_lifecycle (
    event_id STRING,
    account_id SYMBOL,
    user_id SYMBOL,
    event_type STRING,
    from_stage STRING,
    to_stage STRING,
    trigger STRING,
    balance_at_event DECIMAL(18, 2),
    fee_charged DECIMAL(18, 2),
    payout_amount DECIMAL(18, 2),
    payout_net DECIMAL(18, 2),
    payouts_taken INT,
    tradable_balance DECIMAL(18, 2),
    reserve_balance DECIMAL(18, 2),
    details STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, event_id);
"""


# --------------------------------------------------------------------- #
# Market-data / bootstrap tables
# --------------------------------------------------------------------- #

D29_OPENING_VOLUMES = """
CREATE TABLE IF NOT EXISTS p3_d29_opening_volumes (
    asset_id SYMBOL,
    session_date STRING,
    session_type STRING,
    or_minutes INT,
    volume_first_m_min LONG,
    or_range_first_m_min DOUBLE,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, asset_id, session_date);
"""

D30_DAILY_OHLCV = """
CREATE TABLE IF NOT EXISTS p3_d30_daily_ohlcv (
    asset_id SYMBOL,
    trade_date STRING,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume LONG,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(ts, asset_id, trade_date);
"""

D31_IMPLIED_VOL = """
CREATE TABLE IF NOT EXISTS p3_d31_implied_vol (
    asset_id SYMBOL,
    trade_date TIMESTAMP,
    atm_iv_30d DOUBLE,
    realized_vol_20d DOUBLE,
    vrp DOUBLE,
    ts TIMESTAMP
) TIMESTAMP(trade_date) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(trade_date, asset_id);
"""

D32_OPTIONS_SKEW = """
CREATE TABLE IF NOT EXISTS p3_d32_options_skew (
    asset_id SYMBOL,
    trade_date TIMESTAMP,
    cboe_skew DOUBLE,
    skew_spread_proxy DOUBLE,
    ts TIMESTAMP
) TIMESTAMP(trade_date) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(trade_date, asset_id);
"""

# D33: canonical keeps session_date TIMESTAMP per init DDL + the qc
# bootstrap. captain-online/.../b1_features.py:1278 writes a STRING
# today — flagged in .schema-audit.md, not fixed here.
D33_OPENING_VOLATILITY = """
CREATE TABLE IF NOT EXISTS p3_d33_opening_volatility (
    asset_id SYMBOL,
    session_date TIMESTAMP,
    session_type SYMBOL,
    or_minutes INT,
    opening_range_pct DOUBLE,
    opening_vol_z DOUBLE,
    ts TIMESTAMP
) TIMESTAMP(session_date) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(session_date, asset_id);
"""

SPREAD_HISTORY = """
CREATE TABLE IF NOT EXISTS p3_spread_history (
    asset_id SYMBOL,
    session_id INT,
    spread DOUBLE,
    timestamp TIMESTAMP
) TIMESTAMP(timestamp) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(timestamp, asset_id, session_id);
"""


# --------------------------------------------------------------------- #
# Auxiliary: replay, session log, job queue, audit
# --------------------------------------------------------------------- #

SESSION_EVENT_LOG = """
CREATE TABLE IF NOT EXISTS p3_session_event_log (
    user_id SYMBOL,
    event_type STRING,
    event_id STRING,
    asset SYMBOL,
    details STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, event_id);
"""

REPLAY_RESULTS = """
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
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, replay_id);
"""

REPLAY_PRESETS = """
CREATE TABLE IF NOT EXISTS p3_replay_presets (
    preset_id STRING,
    user_id SYMBOL,
    name STRING,
    config STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(ts, preset_id);
"""

# p3_offline_job_queue: each row is a state transition (PENDING → RUNNING
# → COMPLETED/FAILED). job_id alone is unique but the table captures the
# *history* of transitions, so DEDUP would collapse the history. Left as
# plain append-only with WAL for concurrent enqueue from multiple blocks.
OFFLINE_JOB_QUEUE = """
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
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL;
"""

# p3_audit_log: write-once security audit trail (Doc 19 §10). WAL is
# deliberately omitted — this log is written from one Command API process
# only, so concurrent writes aren't needed, and its non-WAL append
# semantics make tampering more obvious during a forensic review.
# DEDUP omitted because each audited user action is a unique event even
# if (user_id, action, ts) coincide.
AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS p3_audit_log (
    user_id SYMBOL,
    action STRING,
    detail STRING,
    old_value STRING,
    new_value STRING,
    ts TIMESTAMP
) TIMESTAMP(ts) PARTITION BY MONTH;
"""


# --------------------------------------------------------------------- #
# Registry — order matters only for readability, not dependencies
# --------------------------------------------------------------------- #

CANONICAL_DDLS: list[str] = [
    # Reference / state (MONTH)
    D00_ASSET_UNIVERSE,
    D01_AIM_MODEL_STATES,
    D02_AIM_META_WEIGHTS,
    D04_DECAY_DETECTOR_STATES,
    D05_EWMA_STATES,
    D06B_ACTIVE_TRANSITIONS,
    D07_CORRELATION_MODEL_STATES,
    D08_TSM_STATE,
    D12_KELLY_PARAMETERS,
    D13_SENSITIVITY_SCAN_RESULTS,
    D15_USER_SESSION_DATA,
    D16_USER_CAPITAL_SILOS,
    D17_SYSTEM_MONITOR_STATE,
    D25_CIRCUIT_BREAKER_PARAMS,
    D26_HMM_OPPORTUNITY_STATE,
    # Hot heartbeat (DAY)
    D14_API_CONNECTION_STATES,
    D23_CIRCUIT_BREAKER_INTRADAY,
    # Event / log
    D03_TRADE_OUTCOME_LOG,
    D06_INJECTION_HISTORY,
    D09_REPORT_ARCHIVE,
    D10_NOTIFICATION_LOG,
    D11_PSEUDOTRADER_RESULTS,
    D18_VERSION_HISTORY,
    D19_RECONCILIATION_LOG,
    D21_INCIDENT_LOG,
    D22_SYSTEM_HEALTH_DIAGNOSTIC,
    D22B_ASSET_RERUN_STATUS,
    D27_PSEUDOTRADER_FORECASTS,
    D28_ACCOUNT_LIFECYCLE,
    # Market-data / bootstrap
    D29_OPENING_VOLUMES,
    D30_DAILY_OHLCV,
    D31_IMPLIED_VOL,
    D32_OPTIONS_SKEW,
    D33_OPENING_VOLATILITY,
    SPREAD_HISTORY,
    # Auxiliary
    SESSION_EVENT_LOG,
    REPLAY_RESULTS,
    REPLAY_PRESETS,
    OFFLINE_JOB_QUEUE,
    # P2 research output (empty at install; populated by pipeline reruns)
    P2_D07_REGIME_MODELS,
    AUDIT_LOG,
]


# ---------------------------------------------------------------------------
# Additive column migrations (idempotent ALTER TABLE runs).
# Format: (migration_id, alter_sql)
# init_questdb.py applies these after the CREATE TABLE loop.
# ---------------------------------------------------------------------------
CANONICAL_MIGRATIONS: list[tuple[str, str]] = [
    # Batch 2 — Q-06 / F-06
    (
        "M001_d03_add_model_m",
        "ALTER TABLE p3_d03_trade_outcome_log ADD COLUMN model_m INT",
    ),
    # Phase 7 — F-23 / Q-15: link D03 rows to originating signal (PG-09 pair)
    (
        "M002_d03_add_signal_id",
        "ALTER TABLE p3_d03_trade_outcome_log ADD COLUMN signal_id STRING",
    ),
    # Phase 7 — PG-09 metric persistence (Stage 1B Appendix B)
    (
        "M003_d11_add_sharpe_baseline",
        "ALTER TABLE p3_d11_pseudotrader_results ADD COLUMN sharpe_baseline DOUBLE",
    ),
    (
        "M004_d11_add_sharpe_updated",
        "ALTER TABLE p3_d11_pseudotrader_results ADD COLUMN sharpe_updated DOUBLE",
    ),
    (
        "M005_d11_add_pair_series",
        "ALTER TABLE p3_d11_pseudotrader_results ADD COLUMN pair_series STRING",
    ),
    # Phase 7 — PG-10 injection persistence (Stage 1B Appendix B)
    (
        "M006_d06_add_pbo",
        "ALTER TABLE p3_d06_injection_history ADD COLUMN pbo DOUBLE",
    ),
    (
        "M007_d06_add_dsr",
        "ALTER TABLE p3_d06_injection_history ADD COLUMN dsr DOUBLE",
    ),
    (
        "M008_d06_add_transition_days",
        "ALTER TABLE p3_d06_injection_history ADD COLUMN transition_days INT",
    ),
    (
        "M009_d06_add_tracking_days",
        "ALTER TABLE p3_d06_injection_history ADD COLUMN tracking_days INT",
    ),
    # --- Phase A (monetary DECIMAL): D08 TSM state ---
    (
        "M010_d08_starting_balance_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN starting_balance TYPE DECIMAL(18, 2)",
    ),
    (
        "M011_d08_current_balance_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN current_balance TYPE DECIMAL(18, 2)",
    ),
    (
        "M012_d08_current_drawdown_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN current_drawdown TYPE DECIMAL(18, 2)",
    ),
    (
        "M013_d08_daily_loss_used_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN daily_loss_used TYPE DECIMAL(18, 2)",
    ),
    (
        "M014_d08_profit_target_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN profit_target TYPE DECIMAL(18, 2)",
    ),
    (
        "M015_d08_max_drawdown_limit_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN max_drawdown_limit TYPE DECIMAL(18, 2)",
    ),
    (
        "M016_d08_max_daily_loss_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN max_daily_loss TYPE DECIMAL(18, 2)",
    ),
    (
        "M017_d08_commission_per_contract_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN commission_per_contract TYPE DECIMAL(18, 2)",
    ),
    (
        "M018_d08_margin_per_contract_to_decimal",
        "ALTER TABLE p3_d08_tsm_state ALTER COLUMN margin_per_contract TYPE DECIMAL(18, 2)",
    ),
    # --- Phase A: D23 / D25 ---
    (
        "M019_d23_l_t_to_decimal",
        "ALTER TABLE p3_d23_circuit_breaker_intraday ALTER COLUMN l_t TYPE DECIMAL(18, 2)",
    ),
    (
        "M020_d25_l_star_to_decimal",
        "ALTER TABLE p3_d25_circuit_breaker_params ALTER COLUMN l_star TYPE DECIMAL(18, 2)",
    ),
    # --- Phase A: D28 account lifecycle ---
    (
        "M021_d28_balance_at_event_to_decimal",
        "ALTER TABLE p3_d28_account_lifecycle ALTER COLUMN balance_at_event TYPE DECIMAL(18, 2)",
    ),
    (
        "M022_d28_fee_charged_to_decimal",
        "ALTER TABLE p3_d28_account_lifecycle ALTER COLUMN fee_charged TYPE DECIMAL(18, 2)",
    ),
    (
        "M023_d28_payout_amount_to_decimal",
        "ALTER TABLE p3_d28_account_lifecycle ALTER COLUMN payout_amount TYPE DECIMAL(18, 2)",
    ),
    (
        "M024_d28_payout_net_to_decimal",
        "ALTER TABLE p3_d28_account_lifecycle ALTER COLUMN payout_net TYPE DECIMAL(18, 2)",
    ),
    (
        "M025_d28_tradable_balance_to_decimal",
        "ALTER TABLE p3_d28_account_lifecycle ALTER COLUMN tradable_balance TYPE DECIMAL(18, 2)",
    ),
    (
        "M026_d28_reserve_balance_to_decimal",
        "ALTER TABLE p3_d28_account_lifecycle ALTER COLUMN reserve_balance TYPE DECIMAL(18, 2)",
    ),
    # --- Phase B (monetary DECIMAL): D03 trade outcome ---
    (
        "M027_d03_entry_price_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN entry_price TYPE DECIMAL(14, 4)",
    ),
    (
        "M028_d03_signal_entry_price_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN signal_entry_price TYPE DECIMAL(14, 4)",
    ),
    (
        "M029_d03_exit_price_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN exit_price TYPE DECIMAL(14, 4)",
    ),
    (
        "M030_d03_gross_pnl_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN gross_pnl TYPE DECIMAL(18, 4)",
    ),
    (
        "M031_d03_commission_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN commission TYPE DECIMAL(18, 4)",
    ),
    (
        "M032_d03_pnl_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN pnl TYPE DECIMAL(18, 4)",
    ),
    (
        "M033_d03_slippage_to_decimal",
        "ALTER TABLE p3_d03_trade_outcome_log ALTER COLUMN slippage TYPE DECIMAL(18, 4)",
    ),
]


def table_name_of(ddl: str) -> str:
    """Extract the table name from a CREATE TABLE IF NOT EXISTS statement."""
    head = ddl.strip().split("(", 1)[0]
    return head.strip().split()[-1]
