# Captain System — P3-D Dataset Schemas (Consolidated)

**Date:** 2026-03-01
**Purpose:** Single-source field list for all 23 Captain persistent datasets (P3-D00 through P3-D22). Nomaan: use this when creating QuestDB table schemas. Each dataset shows: every field, its type, and which spec file defines it.
**Master catalogue:** `Program3_Architecture.md` Section 3.2

---

## P3-D00 — asset_universe_register

**Owner:** Command | **Source:** `Program3_Architecture.md` Section 3.2, `Program3_Online.md` Block 1, `Program3_Offline.md` asset_bootstrap

| Field | Type | Description |
|-------|------|-------------|
| asset_id | string | Asset identifier (e.g., "ES", "NQ", "CL") |
| p1_status | string | "VALIDATED" / "PENDING" / "NOT_RUN" |
| p2_status | string | "VALIDATED" / "PENDING" / "NOT_RUN" |
| captain_status | string | "WARM_UP" / "ACTIVE" / "DECAYED" / "DATA_HOLD" / "ROLL_PENDING" / "PAUSED" |
| warm_up_progress | float | 0.0–1.0 (fraction of warm-up conditions met) |
| aim_warmup_progress | dict | {aim_id: float} — per-AIM warm-up progress for this asset |
| locked_strategy | reference | FK to P2-D06 entry for this asset |
| roll_calendar | object | {current_contract, next_contract, next_roll_date, roll_confirmed} |
| exchange_timezone | string | IANA timezone (e.g., "America/New_York"). Used to derive session membership and session-from-time for bootstrapping |
| point_value | float | Dollar value per point for the instrument (e.g., $50/pt for ES, $20/pt for NQ). Used by Kelly sizing and P&L computation |
| tick_size | float | Minimum price increment (e.g., 0.25 for ES). Used for OR minimum size validation |
| margin_per_contract | float | Default margin requirement per contract. Broker accounts use this for sizing cap |
| session_hours | object | {NY: {open: "09:30", close: "16:00"}, LON: {open: "08:00", close: "16:30"}, APAC: {open: "09:00", close: "15:00"}} — which sessions this asset participates in (null = does not trade that session) |
| p1_data_path | string | Container path to P1 output files for this asset (e.g., "/captain/data/p1_outputs/ES/"). Validated by Command Block 10 (P3-PG-42) at onboarding |
| p2_data_path | string | Container path to P2 output files for this asset (e.g., "/captain/data/p2_outputs/ES/"). Validated by Command Block 10 (P3-PG-42) at onboarding |
| data_sources | object | Per-AIM and per-feature data source configuration (see Data Source Registry below) |
| data_quality_flag | string | "CLEAN" / "PRICE_SUSPECT" / "ZERO_VOLUME" / "VOLUME_EXTREME" / "STALE_FEATURE" |
| created | datetime | When asset was added to universe |
| last_updated | datetime | Last status change |

### P3-D00.data_sources — Data Source Registry (per asset)

Each asset carries its own data source configuration, mapping every AIM and feature input to a specific adapter and endpoint. This is the single source of truth for "where does this asset's data come from?"

```
data_sources: {
    price_feed: {
        adapter:    "REST" | "WEBSOCKET" | "FILE" | "BROKER_API",
        endpoint:   string (URL, file path, or broker identifier),
        frequency:  "STREAMING" | "POLL_10S" | "POLL_1MIN" | "DAILY_FILE",
        auth_ref:   string (key vault reference, null if public)
    },
    options_chain: {
        adapter:    "REST" | "FILE",
        endpoint:   string,
        frequency:  "DAILY_PRE_SESSION" | "POLL_1MIN",
        auth_ref:   string,
        provides:   ["IV_ATM", "PUT_CALL_RATIO", "GEX", "SKEW"]
    },
    vix_feed: {
        adapter:    "REST" | "FILE",
        endpoint:   string,
        frequency:  "DAILY_PRE_SESSION",
        auth_ref:   string,
        provides:   ["VIX_CLOSE", "VXV_CLOSE", "VIX_INTRADAY"]
    },
    cot_data: {
        adapter:    "FILE" | "REST",
        endpoint:   string,
        frequency:  "WEEKLY",
        auth_ref:   string,
        provides:   ["SMI_POLARITY", "SPECULATOR_NET", "SPECULATOR_Z"]
    },
    economic_calendar: {
        adapter:    "REST" | "FILE",
        endpoint:   string,
        frequency:  "DAILY_PRE_SESSION",
        auth_ref:   string
    },
    macro_data: {
        adapter:    "REST" | "FILE",
        endpoint:   string,
        frequency:  "DAILY",
        auth_ref:   string,
        provides:   ["TERM_SPREAD", "CREDIT_SPREAD", "DXY"]
    },
    cross_asset_prices: {
        adapter:    "REST" | "WEBSOCKET",
        endpoint:   string,
        frequency:  "DAILY_PRE_SESSION",
        assets:     [string] (list of correlated assets for AIM-08/09)
    }
}
```

**Adapter types:**
- `REST` — HTTP GET at scheduled intervals (pre-session or polling). Nomaan implements per-provider adapter.
- `WEBSOCKET` — Streaming connection for real-time data (price feed, intraday VIX).
- `FILE` — Local file updated on schedule (COT weekly dump, economic calendar).
- `BROKER_API` — Uses the account's broker connection (TopstepX, IBKR) for price data.

**Health checking:** Online Block 1 validates each data source at session open. If `data_sources[source].endpoint` returns null/error, the asset is flagged `DATA_HOLD` and the corresponding AIM receives null input (graceful degradation per AIM's edge-case handling in `AIMRegistry.md` Part J).

**Adding a new asset:** When a new asset is added to P3-D00, ALL `data_sources` entries must be populated. Command Block 10 (`data_input_validator`) validates the config before accepting it. Any source with `adapter = null` means that AIM's data is unavailable for this asset — the AIM outputs 1.0 (neutral) for that asset.

---

## P3-D01 — aim_model_states

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 1, `AIMRegistry.md` Part A3/J

| Field | Type | Description |
|-------|------|-------------|
| aim_id | int | 1–15 |
| status | string | "INSTALLED" / "COLLECTING" / "WARM_UP" / "BOOTSTRAPPED" / "ELIGIBLE" / "ACTIVE" / "SUPPRESSED" |
| model_object | serialised | Trained model state (AIM-specific) |
| warmup_progress | float | 0.0–1.0 |
| current_modifier | dict | {asset_id: float} — latest modifier per asset |
| last_retrained | datetime | Last training timestamp |
| missing_data_rate_30d | float | Fraction of missing data in last 30 days |

---

## P3-D02 — aim_meta_weights

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 1.4

| Field | Type | Description |
|-------|------|-------------|
| aim_id | int | 1–15 |
| inclusion_probability | float | DMA-learned probability (normalised across all active AIMs) |
| inclusion_flag | bool | True if inclusion_probability > inclusion_threshold |
| recent_effectiveness | float | EWMA of reward signal (for diversity recovery) |
| days_below_threshold | int | Consecutive days with weight below dormancy threshold |

---

## P3-D03 — trade_outcome_log

**Owner:** Online→Offline | **Source:** `Program3_Online.md` Block 7 (resolve_position)

| Field | Type | Description |
|-------|------|-------------|
| trade_id | UUID | Auto-generated |
| user_id | string | Trade owner |
| asset | string | Asset identifier |
| direction | int | +1 (LONG) / -1 (SHORT) |
| entry_price | float | Actual entry price (from fill or user input) |
| signal_entry_price | float | Price from signal generation |
| exit_price | float | Price at resolution |
| contracts | int | Number of contracts traded |
| gross_pnl | float | PnL before commission |
| commission | float | Round-trip commission |
| pnl | float | Net PnL (gross - commission) — feeds learning loop |
| slippage | float | (actual_entry - signal_entry) * direction * contracts * point_value |
| outcome | string | "TP_HIT" / "SL_HIT" / "MANUAL_CLOSE" / "TIME_EXIT" |
| entry_time | datetime | Position open time |
| exit_time | datetime | Position close time |
| regime_at_entry | string | "LOW_VOL" / "HIGH_VOL" |
| aim_modifier_at_entry | float | Combined AIM modifier at signal time |
| aim_breakdown_at_entry | dict | {aim_id: {modifier, weight, reason_tag}} |
| session | int | 1=NY, 2=LON, 3=APAC |
| account | string | Account ID |
| tsm_used | string | TSM file name active at trade time |

---

## P3-D04 — decay_detector_states

**Owner:** Offline | **Source:** `Program3_Offline.md` Blocks 2.3, 2.4, 2.5, 1.6

| Field | Type | Description |
|-------|------|-------------|
| asset_id | string | Per-asset detector state |
| bocpd.run_length_posterior | array | Posterior distribution over run lengths |
| bocpd.cp_probability | float | Current changepoint probability (mass at r=0) |
| bocpd.cp_history | array | Historical cp_probability values |
| cusum.C_up_prev | float | Upper CUSUM statistic |
| cusum.C_down_prev | float | Lower CUSUM statistic |
| cusum.sprint_length | int | Current sprint length T_n |
| cusum.allowance | float | CUSUM allowance parameter k |
| cusum.sequential_limits | dict | {sprint_length: control_limit} — bootstrap-calibrated |
| adwin_states | dict | {aim_id: ADWIN_state} — per-AIM drift detection |
| decay_events | array | Timestamped log of all Level 2/3 triggers |
| current_changepoint_probability | float | Alias for bocpd.cp_probability (used by Offline Block 8) |

---

## P3-D05 — ewma_states

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 8, `Program3_Architecture.md` Section 3.2

| Field | Type | Description |
|-------|------|-------------|
| [asset][regime][session].win_rate | float | EWMA of win indicator (0 or 1) |
| [asset][regime][session].avg_win | float | EWMA of $/contract on winning trades |
| [asset][regime][session].avg_loss | float | EWMA of $/contract on losing trades (positive value) |

Indexed by: asset_id × regime (LOW_VOL, HIGH_VOL) × session (1=NY, 2=LON, 3=APAC). All values normalised to per-contract dollar terms.

---

## P3-D06 — injection_history

**Owner:** Command | **Source:** `Program3_Offline.md` Block 4

| Field | Type | Description |
|-------|------|-------------|
| injection_id | UUID | Auto-generated |
| asset | string | Target asset |
| candidate | object | New strategy candidate (from P2-D06) |
| current | object | Current locked strategy |
| expected_new | float | AIM-adjusted expected edge for candidate |
| expected_current | float | AIM-adjusted expected edge for current |
| pseudo_results | object | Pseudotrader comparison results |
| recommendation | string | "ADOPT" / "PARALLEL_TRACK" / "REJECT" |
| status | string | "RERUN_REQUESTED" / "COMPARISON_COMPLETE" / "ADOPTED" / "REJECTED" |
| timestamp | datetime | Event time |
| type | string | "INJECTION" / "AUTO_EXPANSION" / "LEVEL3_RERUN" |
| outcome | string | Final outcome after user decision |

---

## P3-D07 — correlation_model_states

**Owner:** Offline | **Source:** `Program3_Architecture.md` Section 3.2, AIM-08

| Field | Type | Description |
|-------|------|-------------|
| correlation_matrix | matrix | Rolling pairwise correlations across all universe assets |
| last_updated | datetime | Last recomputation |
| dcc_parameters | object | DCC-GARCH model parameters (if fitted) |

---

## P3-D08 — tsm_files (runtime state)

**Owner:** Command | **Source:** `Program3_Command.md` Block 4

| Field | Type | Description |
|-------|------|-------------|
| account_id | string | FK to Account |
| name | string | TSM display name |
| classification | object | {provider, category, stage, risk_goal} |
| starting_balance | float | Initial account balance |
| current_balance | float | Live balance (updated from API or manual) |
| current_drawdown | float | Current drawdown from peak |
| daily_loss_used | float | Today's realised loss (reset daily) |
| profit_target | float | Evaluation target (null for brokers) |
| max_drawdown_limit | float | MDD limit (null for brokers) |
| max_daily_loss | float | MLL limit (null for brokers) |
| max_contracts | int | Contract cap (null for brokers) |
| scaling_plan | array | [{balance_threshold, max_contracts}] |
| commission_per_contract | float | Per-contract round-trip commission |
| instrument_permissions | list | Assets this account is permitted to trade (e.g., ["ES", "NQ"]). Online Block 4 checks this before sizing. |
| overnight_allowed | bool | Can hold overnight? |
| trading_hours | string | e.g., "09:30-16:00 America/New_York" |
| margin_per_contract | float | Broker margin (null for prop) |
| margin_buffer_pct | float | Margin buffer multiplier (null for prop) |
| pass_probability | float | From Offline Block 7 simulation (null for brokers without MDD) |
| simulation_date | datetime | Last simulation run |
| risk_goal | string | Alias for classification.risk_goal |
| evaluation_end_date | date | Deadline (null if no time limit) |
| evaluation_stages | array | [{stage, target, mdd, mll, days}] |

---

## P3-D09 — report_archive

**Owner:** Command | **Source:** `Program3_Command.md` Block 6

| Field | Type | Description |
|-------|------|-------------|
| report_id | UUID | Auto-generated |
| report_type | string | "RPT-01" through "RPT-11" |
| generated_at | datetime | Generation timestamp |
| content | JSON/HTML | Report content |
| user_id | string | Target user (or "SYSTEM" for broadcast) |

---

## P3-D10 — notification_log

**Owner:** Command | **Source:** `NotificationSpec.md` Section 6

| Field | Type | Description |
|-------|------|-------------|
| notification_id | UUID | Auto-generated |
| user_id | string | Target user ("SYSTEM" for broadcast) |
| timestamp | datetime | Creation time |
| priority | string | "CRITICAL" / "HIGH" / "MEDIUM" / "LOW" |
| event_type | string | Event category |
| asset | string | Related asset (optional) |
| message | string | Notification text |
| action_required | bool | User action needed? |
| gui_delivered | bool | Delivered to GUI? |
| gui_read | bool | Read in GUI? |
| gui_read_at | datetime | When read |
| telegram_delivered | bool | Sent via Telegram? |
| telegram_read | bool | Receipt confirmed? |
| email_delivered | bool | Sent via email? |
| user_response | string | User's response (if action_required) |
| response_at | datetime | When user responded |

---

## P3-D11 — pseudotrader_results

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 3

| Field | Type | Description |
|-------|------|-------------|
| result_id | UUID | Auto-generated |
| update_type | string | "AIM_WEIGHT_CHANGE" / "MODEL_RETRAIN" / "STRATEGY_INJECTION" |
| sharpe_improvement | float | Updated Sharpe - baseline Sharpe |
| drawdown_change | float | Updated max DD - baseline max DD |
| winrate_delta | float | Updated win rate - baseline win rate |
| pbo | float | Probability of backtest overfitting |
| dsr | float | Deflated Sharpe ratio |
| recommendation | string | "ADOPT" / "REJECT" |
| timestamp | datetime | Test time |

---

## P3-D12 — kelly_parameters

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 8

| Field | Type | Description |
|-------|------|-------------|
| [asset][regime][session].kelly_full | float | Full Kelly fraction (dimensionless) |
| [asset].shrinkage_factor | float | Parameter uncertainty shrinkage (0.3–1.0) |
| [asset].last_updated | datetime | Last Kelly update |
| sizing_override | dict | {asset: reduction_factor} — Level 2 decay overrides |

Indexed by: asset_id × regime (LOW_VOL, HIGH_VOL) × session (1=NY, 2=LON, 3=APAC).

---

## P3-D13 — sensitivity_scan_results

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 5

| Field | Type | Description |
|-------|------|-------------|
| asset_id | string | Scanned asset |
| sharpe_stability | float | CV of Sharpe across perturbation grid |
| pbo | float | PBO from perturbation grid |
| dsr | float | DSR from perturbation grid |
| adjusted_sharpe | float | max(Sharpe) - complexity_penalty |
| robustness_status | string | "ROBUST" / "FRAGILE" |
| flags | array | List of flag strings |
| perturbation_grid_results | array | Full grid results |
| scan_date | datetime | When scan ran |

---

## P3-D14 — api_connection_states

**Owner:** Command | **Source:** `Program3_Command.md` Block 3.2

| Field | Type | Description |
|-------|------|-------------|
| account_id | string | Account identifier |
| adapter_type | string | "TopstepX" / "InteractiveBrokers" / "Manual" |
| connection_status | string | "CONNECTED" / "DISCONNECTED" / "RECONNECTING" |
| last_heartbeat | datetime | Last successful ping |
| latency_ms | float | Last measured latency |
| error_log | array | Recent connection errors |

---

## P3-D15 — user_session_data

**Owner:** Command | **Source:** `UserManagementSetup.md` Section 1

| Field | Type | Description |
|-------|------|-------------|
| user_id | string | User identifier |
| display_name | string | Display name |
| auth_token | string | Session token |
| role | string | "ADMIN" (V1) |
| tags | array | ["ADMIN", "DEV", ...] |
| device_sessions | array | [{session_id, device_type, ip_address, connected_at, last_ping, websocket_id}] |
| preferences | object | See UserManagementSetup Section 1.3 (display_timezone, notification channels, quiet hours, theme) |
| created | datetime | Account creation |
| last_active | datetime | Last activity |

---

## P3-D16 — user_capital_silos

**Owner:** Command | **Source:** `UserManagementSetup.md` Section 10.2

| Field | Type | Description |
|-------|------|-------------|
| user_id | string | FK to User |
| starting_capital | float | Auto-computed: SUM(account.starting_balance). Immutable after set. |
| total_capital | float | Current total across all accounts |
| accounts | array | [account_id] references |
| risk_allocation.max_simultaneous_positions | int | Max concurrent trades (default: no limit) |
| risk_allocation.max_portfolio_risk_pct | float | Max % capital at risk (default: 0.10) |
| risk_allocation.correlation_threshold | float | Covariance reduction threshold (default: 0.7) |
| risk_allocation.user_kelly_ceiling | float | User-specific Kelly cap (default: 1.0) |
| capital_history | array | [{date, total_capital, per_account: {ac: balance}, daily_pnl, cumulative_pnl}] |
| created | datetime | Silo creation |
| last_updated | datetime | Last capital update |

---

## P3-D17 — system_monitor_state

**Owner:** Online/Command | **Source:** `Program3_Online.md` Blocks 8, 9, `Program3_Architecture.md` Section 9

| Field | Type | Description |
|-------|------|-------------|
| system_params | object | All configurable system parameters (max_users, max_accounts_per_user, max_assets, quality_hard_floor, quality_ceiling, minimum_quality_threshold, network_concentration_threshold, max_silo_drawdown_pct, circuit_breaker_vix_threshold, circuit_breaker_data_hold_count, execution_mode, tsm_budget_divisor_default, manual_halt_all) |
| capacity_state | object | Latest capacity evaluation (active_users, active_accounts, active_assets, signal_supply_ratio, quality_pass_rate, constraints[], max capacities) |
| concentration_history | array | Network concentration events with admin responses |
| capacity_recommendations | array | Proactive recommendations for universe expansion |
| session_log | array | Per-session quality gate statistics (total_selected, total_recommended, total_below_threshold, quality_scores) |
| data_quality_log | array | Per-session data moderator results |
| latency_metrics | object | Per-block latency measurements. Written by Online orchestrator after each session evaluation: {block_1_ms, block_2_ms, ..., total_ms, per_user_ms[]}. Read by Command Block 2.3 (System Overview Network Performance panel). |
| taken_modification_rate | float | Rolling 100-trade unmodified rate |

---

## P3-D18 — version_history_store

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 1.4b

| Field | Type | Description |
|-------|------|-------------|
| version_id | UUID | Auto-generated |
| component | string | "P3-D01" / "P3-D02" / "P3-D05" / "P3-D12" / "P3-D17.system_params" |
| timestamp | datetime | Snapshot time |
| trigger | string | "DMA_UPDATE" / "AIM_RETRAIN" / "KELLY_UPDATE" / "EWMA_UPDATE" / "PARAM_CHANGE" / "INJECTION_ADOPT" / "ROLLBACK" |
| state | object | Deep copy of component state at snapshot time |
| model_hash | string | Hash of state for integrity verification |

---

## P3-D19 — reconciliation_log

**Owner:** Command | **Source:** `Program3_Command.md` Block 8

| Field | Type | Description |
|-------|------|-------------|
| recon_id | UUID | Auto-generated |
| account | string | Account identifier |
| user_id | string | Account owner |
| timestamp | datetime | Reconciliation time |
| source | string | "API" / "MANUAL" |
| mismatches | array | [{field, system_value, api_value}] |
| corrected | bool | Whether system auto-corrected |
| status | string | "CLEAN" / "AUTO_CORRECTED" / "AWAITING_USER_CONFIRMATION" |

---

## P3-D20 — system_journal

**Owner:** All (per-process) | **Source:** `Program3_Architecture.md` Section 11.1

| Field | Type | Description |
|-------|------|-------------|
| entry_id | UUID | Auto-generated |
| timestamp | datetime | Checkpoint time |
| component | string | "ONLINE" / "OFFLINE" / "COMMAND" |
| checkpoint | string | "SESSION_START" / "SHARED_INTEL_COMPLETE" / "USER_LOOP_COMPLETE" / "SIGNALS_DELIVERED" / "TRADE_RESOLVED" / "MODEL_UPDATED" / etc. |
| state_hash | string | Hash of relevant system state |
| last_action | string | What just completed |
| next_action | string | What should happen next |
| metadata | JSON | Component-specific context |

Storage: SQLite WAL (one file per Captain process). NOT in QuestDB.

---

## P3-D21 — incident_log

**Owner:** Command | **Source:** `Program3_Command.md` Block 9

| Field | Type | Description |
|-------|------|-------------|
| incident_id | UUID | Auto-generated |
| timestamp | datetime | Detection time |
| type | string | "CRASH" / "DATA_QUALITY" / "RECONCILIATION" / "PERFORMANCE" / "SECURITY" / "OPERATIONAL" / "STRESS_TEST" |
| severity | string | "P1_CRITICAL" / "P2_HIGH" / "P3_MEDIUM" / "P4_LOW" |
| component | string | "ONLINE" / "OFFLINE" / "COMMAND" / "DATA_FEED" / "API" |
| details | string | Description |
| affected_users | array | [user_id] |
| system_snapshot | object | System state at incident time |
| status | string | "OPEN" / "RESOLVED" |
| resolution | string | How it was resolved |
| root_cause | string | Root cause (if determined) |
| resolved_by | string | Admin who resolved |
| resolved_at | datetime | Resolution time |

---

## P3-D22 — system_health_diagnostic

**Owner:** Offline | **Source:** `Program3_Offline.md` Block 9

| Field | Type | Description |
|-------|------|-------------|
| diagnostic_results | array | [{timestamp, mode, scores: {d1..d8}, overall_health, action_items_generated, critical_count, high_count, queue_total, open_count, stale_count}] |
| action_queue | array | See action item schema below |

### Action Item Schema (within P3-D22.action_queue)

| Field | Type | Description |
|-------|------|-------------|
| action_id | string | e.g., "ACT-2026-03-07-001" |
| created | datetime | When generated |
| priority | string | "CRITICAL" / "HIGH" / "MEDIUM" / "LOW" |
| category | string | "MODEL_DEV" / "RESEARCH" / "FEATURE_DEV" / "AIM_IMPROVEMENT" / "DATA_ACQUISITION" |
| dimension | string | "D1"–"D8" (which diagnostic dimension) |
| constraint_type | string | e.g., "STRATEGY_HOMOGENEITY", "FEATURE_CONCENTRATION", "EDGE_DECLINING" |
| title | string | Human-readable summary |
| detail | string | Full description with current data |
| impact_estimate | string | What fixing this would improve |
| recommendation | string | Suggested action |
| status | string | "OPEN" / "ACKNOWLEDGED" / "IN_PROGRESS" / "RESOLVED" / "VERIFIED" / "STALE" |
| acknowledged_by | string | Admin user_id |
| acknowledged_at | datetime | When acknowledged |
| resolved_at | datetime | When resolved |
| verified_at | datetime | When verification ran |
| verification_result | string | "IMPROVED" / "INCONCLUSIVE" / "NOT_IMPROVED" |
| notes | string | Admin notes (appended) |
| metric_snapshot_at_creation | float | Metric value when item was created (for D8 verification) |
| last_seen | datetime | Last time diagnostic confirmed this issue still exists |

### Diagnostic Score Dimensions

| Dimension | Name | Weight Components |
|-----------|------|-------------------|
| D1 | Strategy Portfolio Health | type diversity, freshness, weakest OO, consistency |
| D2 | Feature Portfolio Health | distinct features, reuse concentration, decay flags |
| D3 | Model Staleness Tracker | days since P1/P2, regime model ages, AIM retrain ages |
| D4 | AIM Effectiveness Portfolio | active count, dormant AIMs, dominant AIMs, warm-up backlog |
| D5 | Edge Trajectory | 30d/60d/90d edge, trend, per-regime breakdown (monthly only) |
| D6 | Data Coverage Gaps | AIM missing data rates, asset data quality, data hold frequency |
| D7 | Research Pipeline Throughput | days since injection, unresolved Level 3, expansion success rate |
| D8 | Resolution Verification | resolved items verified, stale items detected |

---

## Account Entity (implicit — no P3-D number)

**Source:** `UserManagementSetup.md` Section 2

| Field | Type | Description |
|-------|------|-------------|
| account_id | UUID | Auto-generated |
| user_id | string | FK to User |
| name | string | Display name |
| classification | object | {provider, category, stage, risk_goal} |
| tsm_file | string | Path to TSM config file |
| api_adapter | string | "TopstepX" / "InteractiveBrokers" / "Manual" |
| api_key_ref | string | Reference to vault entry |
| status | string | "ACTIVE" / "PAUSED" / "CLOSED" |
| api_validated | bool | TSM confirmed against live API? |
| last_api_sync | datetime | Last API state sync |
| created | datetime | Account creation |

Note: This entity needs a QuestDB table but is not formally numbered in the P3-D scheme. It is referenced by P3-D08 (TSM state per account), P3-D14 (API state per account), and P3-D16 (account list per silo).

---

*This document consolidates field lists from `Program3_Architecture.md`, `Program3_Offline.md`, `Program3_Online.md`, `Program3_Command.md`, `UserManagementSetup.md`, and `NotificationSpec.md`. It is the authoritative schema reference for QuestDB table creation.*
