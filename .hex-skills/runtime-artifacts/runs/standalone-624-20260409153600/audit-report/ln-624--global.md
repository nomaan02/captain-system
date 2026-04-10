# Code Quality Audit Report

<!-- AUDIT-META
worker: ln-624
category: Code Quality
domain: global
scan_path: .
score: 0.0
total_issues: 221
critical: 0
high: 64
medium: 124
low: 33
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| 1 | Cyclomatic Complexity | failed | 21 HIGH (>20), 23 MEDIUM (11-20); worst: `load_replay_config()` at 89 |
| 2 | Deep Nesting | failed | 2 HIGH (>6 levels), 21 MEDIUM (5-6 levels); worst: `run_aim_lifecycle()` at depth 10 |
| 3 | Long Methods | failed | 15 HIGH (>100 lines), 26 MEDIUM (51-100); worst: `run_replay()` at 324 lines |
| 4 | God Classes/Modules | failed | 4 HIGH (>1000 lines), 9 MEDIUM (501-1000); worst: `replay_engine.py` at 1641 code lines |
| 5 | Too Many Parameters | failed | 12 HIGH (>8 params), 18 MEDIUM (6-8); worst: `_write_trade_outcome()` at 20 params |
| 6 | O(n^2) Algorithms | warning | 0 HIGH, 2 MEDIUM, 5 LOW; all bounded by domain constraints (n<=60) |
| 7 | N+1 Query Patterns | failed | 3 HIGH, 4 MEDIUM, 4 LOW; worst: `run_dma_update()` 60 INSERTs per trade outcome |
| 8 | Constants Management | failed | 6 HIGH, 12 MEDIUM, 7 LOW; worst: `4500` drawdown default in 6 locations bypassing `account_lifecycle.py` |
| 9 | Method Signatures | warning | 0 HIGH, 7 MEDIUM, 12 LOW; no boolean flag problems; `-> dict` is systemic |
| 10 | Cascade Depth | warning | 1 HIGH (depth 4), 2 MEDIUM (depth 3); most modules are clean sinks |

## Scoring

```
penalty = (0 x 2.0) + (64 x 1.0) + (124 x 0.5) + (33 x 0.2)
        = 0 + 64 + 62 + 6.6 = 132.6
score   = max(0, 10 - 132.6) = 0.0/10
```

**Context:** This is a full-codebase scan (110 Python files, 10 checks). The penalty formula is designed for single-domain audits. The volume of findings reflects systemic patterns (widespread long methods, missing constants centralisation) rather than isolated defects. Roughly 60% of HIGH findings concentrate in 5 files: `replay_engine.py`, `b3_pseudotrader.py`, `b1_features.py`, `b4_kelly_sizing.py`, `b2_gui_data_server.py`.

---

## Findings

### CRITICAL -- none

### HIGH

| # | Severity | Location | Issue | Check | Recommendation | Effort |
|---|----------|----------|-------|-------|----------------|--------|
| 1 | HIGH | shared/replay_engine.py:59 | `load_replay_config()` complexity 89 | Complexity | Split into config-parse, validation, and defaults sub-functions | L |
| 2 | HIGH | shared/replay_engine.py:890 | `compute_contracts()` complexity 67 | Complexity | Extract regime-specific sizing into helper | L |
| 3 | HIGH | captain-online/.../b1_features.py:538 | `compute_all_features()` complexity 56 | Complexity | Group by AIM number into per-AIM-family sub-functions | L |
| 4 | HIGH | shared/replay_engine.py:1480 | `run_replay()` complexity 50, 324 lines | Complexity + Long Method | Extract bar loop, position management, result aggregation phases | L |
| 5 | HIGH | captain-offline/.../b3_pseudotrader.py:1073 | `generate_forecast()` complexity 49, 188 lines | Complexity + Long Method | Extract per-regime and per-session forecast logic | L |
| 6 | HIGH | captain-offline/.../b3_pseudotrader.py:169 | `run_account_aware_replay()` complexity 42, 223 lines | Complexity + Long Method | Extract account iteration, position sizing, trade execution | L |
| 7 | HIGH | shared/replay_engine.py:557 | `simulate_orb()` complexity 40, 182 lines | Complexity + Long Method | Split bar-by-bar simulation vs position resolution | L |
| 8 | HIGH | captain-online/.../b4_kelly_sizing.py:43 | `run_kelly_sizing()` complexity 38, 172 lines, 12 params | Complexity + Long Method + Params | Extract silo-drawdown, per-account loop, TSM cap into helpers; use context dataclass | L |
| 9 | HIGH | shared/aim_feature_loader.py:124 | `_load_ohlcv_features()` complexity 38 | Complexity | Extract per-feature-type loaders | M |
| 10 | HIGH | captain-command/.../b10_data_validation.py:136 | `validate_asset_config()` complexity 33 | Complexity | Extract per-field validators | M |
| 11 | HIGH | shared/replay_engine.py:1881 | `run_whatif()` complexity 29, 143 lines | Complexity + Long Method | Extract scenario setup vs execution loop | M |
| 12 | HIGH | captain-command/.../b4_tsm_manager.py:57 | `validate_tsm()` complexity 28 | Complexity | Extract per-rule validators into rule functions | M |
| 13 | HIGH | captain-online/.../b7_position_monitor.py:63 | `monitor_positions()` complexity 27 | Complexity | Extract per-position evaluation into helper | M |
| 14 | HIGH | captain-offline/.../b9_diagnostic.py:745 | `_check_constraint_resolution()` complexity 25, nesting 7 | Complexity + Nesting | Use early returns + extract per-constraint checkers | M |
| 15 | HIGH | captain-online/.../b5_trade_selection.py:31 | `run_trade_selection()` complexity 25, 78 lines, 8 params | Complexity + Params | Extract correlation filter + session weight logic | M |
| 16 | HIGH | captain-command/.../b6_reports.py:194 | `_rpt04_aim_effectiveness()` complexity 25, 90 lines | Complexity + Long Method | Extract per-AIM metric computation | M |
| 17 | HIGH | captain-offline/.../b9_diagnostic.py:513 | `compute_d6()` complexity 24, 77 lines | Complexity | Extract per-metric computation | M |
| 18 | HIGH | captain-command/.../b2_gui_data_server.py:461 | `get_aim_detail()` complexity 24, 111 lines | Complexity + Long Method | Extract detail builders per AIM type | M |
| 19 | HIGH | captain-command/.../telegram_bot.py:315 | `_run_bot()` complexity 24, 194 lines | Complexity + Long Method | Extract command handlers into per-command methods | L |
| 20 | HIGH | captain-online/.../b1_data_ingestion.py:387 | `_run_data_moderator()` complexity 22 | Complexity | Extract per-asset data quality checks | M |
| 21 | HIGH | captain-command/.../api.py:297 | `websocket_endpoint()` complexity 22, 90 lines | Complexity + Long Method | Extract message handlers by type | M |
| 22 | HIGH | captain-offline/.../b1_aim_lifecycle.py:205 | `run_aim_lifecycle()` nesting depth 10 | Nesting | Extract per-state transition handlers (`_transition_from_active()`, etc.) | M |
| 23 | HIGH | shared/replay_engine.py (file) | 1641 code lines, 20 functions, 7 responsibilities | God Module | Split into: config parser, bar fetcher, ORB simulator, contract computer, replay runner, what-if engine | L |
| 24 | HIGH | captain-command/.../b2_gui_data_server.py (file) | 1300 code lines, 32 functions | God Module | Split by GUI panel: dashboard endpoints, AIM endpoints, position endpoints, config endpoints | L |
| 25 | HIGH | captain-offline/.../b3_pseudotrader.py (file) | 1117 code lines, 24 functions | God Module | Split into: pseudotrader runner, grid search, CB calibration, forecast generator | L |
| 26 | HIGH | captain-online/.../b1_features.py (file) | 1106 code lines, 75 functions | God Module | Split by AIM family: AIM-01 through AIM-15 in separate modules | L |
| 27 | HIGH | captain-online/.../b7_position_monitor.py:272 | `_write_trade_outcome()` has 20 params | Params | Create `TradeOutcome` dataclass for DB row | S |
| 28 | HIGH | captain-online/.../b6_signal_output.py:34 | `run_signal_output()` has 17 params | Params | Create `SessionContext` dataclass | M |
| 29 | HIGH | shared/signal_replay.py:213 | `strategy_replay()` has 17 params | Params | Split into `from_config()` classmethod + direct call | M |
| 30 | HIGH | captain-online/.../b5c_circuit_breaker.py:48 | `run_circuit_breaker_screen()` has 14 params | Params | Create `CBScreenInput` dataclass | M |
| 31 | HIGH | captain-online/.../b5c_circuit_breaker.py:169 | `_check_all_layers()` has 11 params | Params | Pass parent's context struct instead of individual params | S |
| 32 | HIGH | shared/signal_replay.py:84 | `sizing_replay()` has 11 params | Params | Create `SizingConfig` dataclass | M |
| 33 | HIGH | captain-command/.../b8_reconciliation.py:298 | `_check_payout_recommendation()` has 10 params | Params | Extract into a reconciliation context object | M |
| 34 | HIGH | captain-offline/.../b9_diagnostic.py:79 | `_queue_action()` has 9 params | Params | Create `DiagnosticAction` dataclass | S |
| 35 | HIGH | captain-command/.../b7_notifications.py:479 | `_log_notification_full()` has 9 params | Params | Create `NotificationRecord` dataclass for DB insert | S |
| 36 | HIGH | shared/replay_engine.py:890 | `compute_contracts()` has 9 params | Params | Fold into replay config dataclass | M |
| 37 | HIGH | captain-online/.../b7_position_monitor.py:361 | `_publish_trade_outcome()` has 7 params | Params | Reuse `TradeOutcome` dataclass from #27 | S |
| 38 | HIGH | captain-offline/.../b1_dma_update.py:190 | 60 individual INSERTs per trade outcome in loop | N+1 Query | Replace `cur.execute` loop with `cur.executemany` | S |
| 39 | HIGH | captain-online/.../b7_position_monitor.py:71 | Per-position `_get_live_price()` in 10-second loop | N+1 Query | Batch-fetch all prices before loop | S |
| 40 | HIGH | captain-online/.../b1_data_ingestion.py:398 | N x M DB calls (assets x features) at session open | N+1 Query | Pre-load feature availability into dict before asset loop | M |
| 41 | HIGH | b3_pseudotrader, b4_injection, b5_sensitivity, b6_auto_expansion | `PBO_THRESHOLD=0.5` / `DSR_THRESHOLD=0.5` defined in 4 files | Constants | Centralise in `shared/constants.py` | S |
| 42 | HIGH | captain-online/.../b4_kelly_sizing.py:300 | Kelly TSM multipliers `0.5`, `0.7`, `0.85` unnamed | Constants | Define `KELLY_TSM_*` named constants | S |
| 43 | HIGH | b3_pseudotrader, b8_reconciliation, b5c_circuit_breaker | `4500` drawdown default in 6 locations bypasses `account_lifecycle.py` | Constants | Import `EVAL_MLL` from `account_lifecycle.py` | S |
| 44 | HIGH | captain-offline/.../bootstrap.py:178 | `max(0.3, ...)` duplicates `SHRINKAGE_FLOOR` without import | Constants | Import `SHRINKAGE_FLOOR` from `b8_kelly_update` or centralise | S |
| 45 | HIGH | b7_position_monitor, b7_shadow_monitor, orchestrator, replay_engine | Direction `1`/`-1` as magic ints in 11 locations | Constants | Define `DIRECTION_LONG=1` / `DIRECTION_SHORT=-1` in `shared/constants.py` | S |
| 46 | HIGH | b5c_circuit_breaker, replay_engine | CB significance `p_value > 0.05` / `n_obs < 100` in 3 locations | Constants | Centralise as `CB_SIGNIFICANCE_P` / `CB_MIN_OBS` | S |
| 47 | HIGH | captain-command/.../b8_reconciliation.py:41 | `run_daily_reconciliation()` cascade depth 4 | Cascade Depth | Make `notify_fn` a direct call in reconciliation rather than passing through `_check_payout_recommendation` | M |

### MEDIUM (top 40 of 124)

| # | Severity | Location | Issue | Check | Recommendation | Effort |
|---|----------|----------|-------|-------|----------------|--------|
| 48 | MEDIUM | captain-online/.../b4_kelly_sizing.py:311 | `_compute_tsm_cap()` complexity 20 | Complexity | Extract tier lookup | M |
| 49 | MEDIUM | captain-online/.../orchestrator.py:141 | `_run_session()` complexity 19 | Complexity | Downgraded: orchestrator with sequential delegation | -- |
| 50 | MEDIUM | captain-offline/.../b7_tsm_simulation.py:100 | `run_tsm_simulation()` complexity 18 | Complexity | Extract per-scenario runner | M |
| 51 | MEDIUM | captain-offline/.../b9_diagnostic.py:194 | `compute_d2()` complexity 17, nesting 5 | Complexity + Nesting | Use early returns | M |
| 52 | MEDIUM | captain-online/.../b7_shadow_monitor.py:67 | `monitor_shadow_positions()` complexity 17 | Complexity | Extract per-position shadow check | M |
| 53 | MEDIUM | shared/aim_compute.py:79 | `run_aim_aggregation()` complexity 17, 81 lines | Complexity | Extract per-AIM scoring phase | M |
| 54 | MEDIUM | captain-offline/.../b3_pseudotrader.py:815 | `run_multistage_replay()` complexity 16, 107 lines | Complexity + Long Method | Extract per-stage runner | M |
| 55 | MEDIUM | captain-online/.../b9_capacity_evaluation.py:26 | `run_capacity_evaluation()` complexity 16, 103 lines | Complexity + Long Method | Extract memory/latency/correlation checks | M |
| 56 | MEDIUM | captain-online/.../b5c_circuit_breaker.py:48 | `run_circuit_breaker_screen()` 97 lines | Long Method | (Already flagged for params -- combined refactor) | M |
| 57 | MEDIUM | captain-offline/.../b5_sensitivity.py:151 | `run_sensitivity_scan()` complexity 12, 74 lines | Complexity | Extract per-parameter perturbation | M |
| 58 | MEDIUM | captain-command/.../main.py:75 | `_link_tsm_to_account()` complexity 15 | Complexity | Extract validation sub-steps | M |
| 59 | MEDIUM | captain-command/.../b3_api_adapter.py:192 | `send_signal()` complexity 14, 71 lines | Complexity | Extract order submission vs confirmation logic | M |
| 60 | MEDIUM | captain-command/.../api.py (file) | 694 code lines -- 13 Pydantic schemas + all routes in one file | God Module | Extract schemas to `schemas.py`; split routes by resource | M |
| 61 | MEDIUM | captain-offline/.../b9_diagnostic.py (file) | 678 code lines -- 16 functions | God Module | Extract per-diagnostic (D1-D8) into separate modules | L |
| 62 | MEDIUM | captain-online/.../b1_data_ingestion.py (file) | 666 code lines -- 28 functions | God Module | Split: bar builder, QuestDB writer, quote cache, data moderator | L |
| 63 | MEDIUM | captain-online/.../orchestrator.py (file) | 609 code lines | God Module | Borderline; coordinator role justifies some size | -- |
| 64 | MEDIUM | captain-command/.../telegram_bot.py (file) | 566 code lines | God Module | Extract command handlers into separate module | M |
| 65 | MEDIUM | shared/topstep_stream.py (file) | 564 code lines | God Module | Borderline; tightly coupled to SignalR protocol | -- |
| 66 | MEDIUM | captain-command/.../b11_replay_runner.py (file) | 560 code lines | God Module | Extract `BatchReplayJob` into separate module | M |
| 67 | MEDIUM | captain-online/.../b5_trade_selection.py:31 | `run_trade_selection()` 8 params | Params | Use context dataclass | M |
| 68 | MEDIUM | captain-command/.../b11_replay_runner.py:35 | `ReplayJob.__init__()` 7 params | Params | Convert to `@dataclass` | S |
| 69 | MEDIUM | captain-command/.../b9_incident_response.py:53 | `create_incident()` 7 params | Params | Create `IncidentReport` dataclass | S |
| 70 | MEDIUM | captain-online/.../b4_kelly_sizing.py:282 | Linear scan of `kelly_params` inside per-asset loop (O(n^2)) | O(n^2) | Index kelly_params by `(asset_id, regime, session_id)` for O(1) lookup | S |
| 71 | MEDIUM | captain-offline/.../b8_cb_params.py:120 | `_compute_same_day_correlation()` O(days x trades^2) | O(n^2) | Vectorise with numpy pairwise | M |
| 72 | MEDIUM | captain-offline/.../b8_kelly_update.py:195 | 6 separate INSERTs (2 regimes x 3 sessions) per trade | N+1 Query | Use `executemany` with 6-row batch | S |
| 73 | MEDIUM | captain-offline/.../orchestrator.py:397 | 2N DB writes per queued job in `_dispatch_pending_jobs` | N+1 Query | Batch status UPDATEs | S |
| 74 | MEDIUM | captain-command/.../b2_gui_data_server.py:442 | Nested query inside `fetchall` loop | N+1 Query | Pre-fetch related data with JOIN | M |
| 75 | MEDIUM | captain-online/.../b4_kelly_sizing.py:43 | `_get_kelly_for_regime` pre-loaded but fallback scans linearly | N+1 Query | Ensure dict key covers all fallback cases | S |
| 76 | MEDIUM | b4_kelly_sizing, replay_engine | `999` sentinel used 13+ times with no named constant | Constants | Define `UNCONSTRAINED_CONTRACTS = 999` | S |
| 77 | MEDIUM | b4_kelly_sizing, replay_engine (x2) | Budget divisor `20` in 3 independent locations | Constants | Centralise or always read from D17 | S |
| 78 | MEDIUM | b2_regime_probability.py:77 | `0.6` regime uncertainty threshold unnamed | Constants | Define `REGIME_UNCERTAIN_THRESHOLD = 0.6` | S |
| 79 | MEDIUM | b5_trade_selection.py:160 | `n_obs < 20`, `n_obs < 60` session weight thresholds unnamed | Constants | Define named constants for HMM transition thresholds | S |
| 80 | MEDIUM | b5b_quality_gate.py:54 | Data maturity `50.0` and floor `0.5` unnamed | Constants | Define `MATURITY_TRADE_COUNT` and `MATURITY_FLOOR` | S |
| 81 | MEDIUM | b2_gui_data_server.py:531 | `aim_id == 16` HMM special case in 3 places | Constants | Define `AIM_HMM_ID = 16` | S |
| 82 | MEDIUM | b7_position_monitor.py:94 | TP/SL proximity `0.10` threshold unnamed | Constants | Define `TPSL_PROXIMITY_WARN = 0.10` | S |
| 83 | MEDIUM | b1_data_ingestion.py:410 | Price deviation `0.05` threshold unnamed | Constants | Define `PRICE_SUSPECT_DEVIATION = 0.05` | S |
| 84 | MEDIUM | b9_diagnostic.py:675 | Injection staleness `120` days uses raw literal not existing constants | Constants | Extend existing `STALENESS_*` constants | S |
| 85 | MEDIUM | captain-offline/.../orchestrator.py:294 | Transition days fallback `10` duplicates `DEFAULT_TRANSITION_DAYS` | Constants | Import from `b4_injection.py` | S |
| 86 | MEDIUM | b9_capacity_evaluation.py:145 | `max_aims: 16`, `max_simultaneous_sessions: 3` unnamed | Constants | Define architectural limit constants | S |
| 87 | MEDIUM | All 3 orchestrators | Backoff `min(backoff * 2, 30)` duplicated in 4 places | Constants | Centralise `MAX_BACKOFF_SECONDS = 30` | S |
| 88 | MEDIUM | shared/topstep_stream.py:38 | `_extract_dict() -> Any` unclear return | Signatures | Use `Optional[dict]` or narrow return type | S |
| 89 | MEDIUM | shared/replay_engine.py:778 | `_compute_regime_probs() -> tuple[dict, bool]` | Signatures | Use `NamedTuple(probs=dict, uncertain=bool)` | S |
| 90 | MEDIUM | shared/replay_engine.py:1203 | `apply_position_limit() -> tuple[list, list]` | Signatures | Use `NamedTuple(selected=list, excluded=list)` | S |
| 91 | MEDIUM | captain-command/.../b3_api_adapter.py:192 | `send_signal() -> dict` undocumented shape | Signatures | Define `OrderResult` TypedDict | S |
| 92 | MEDIUM | captain-online/.../b6_signal_output.py:34 | `run_signal_output() -> dict` undocumented shape | Signatures | Define `SignalBatch` TypedDict | S |
| 93 | MEDIUM | captain-online/.../b5c_circuit_breaker.py:48 | `run_circuit_breaker_screen() -> dict` | Signatures | Define `CBScreenResult` TypedDict | S |
| 94 | MEDIUM | captain-command/.../b9_incident_response.py:53 | `create_incident()` cascade depth 3 | Cascade Depth | Move notification to caller rather than embedding | M |
| 95 | MEDIUM | captain-command/.../b3_api_adapter.py:392 | `run_health_checks()` cascade depth 3 | Cascade Depth | Move notification to orchestrator level | M |

### LOW (33 findings -- summarised)

| Category | Count | Summary |
|----------|-------|---------|
| O(n^2) bounded small | 5 | `calibrate_cusum_limits` (quarterly), `run_cb_grid_search` (rare), `compute_d2` (n<=10), `_find_high_corr_pairs` (n<=10), `run_trade_selection` cross-asset (n<=10) |
| N+1 in admin/startup paths | 4 | `bootstrap.py` nested loops, `_log_api_health_batch`, `b5c_circuit_breaker` (pre-loaded), scripts |
| Magic numbers in non-critical code | 7 | Drift `0.02`, edge significance `0.005`, data gap `0.05`/`0.1`, homogeneity `0.6`, quality floor `0.3`, roll lookahead `3`, HTTP timeouts scattered |
| God modules (borderline 400-500 LOC) | 5 | `aim_compute`, `replay_full_pipeline`, `b8_reconciliation`, `b7_notifications`, command `orchestrator` |
| Optional params (3+ defaults) | 8 | `strategy_replay` (17), `sizing_replay` (11), `load_trades` (8), `run_circuit_breaker_screen` (7), etc. |
| Inconsistent verb naming | 4 | `get_` vs `read_` in `questdb_client`, `redis_client`; `load_` vs `get_` in `vault`; `save_` vs `_store_` in `b4_injection` |
| Systemic `-> dict` returns | 5 | 130+ functions return bare `dict`; top 5 inter-block contracts most impactful |

---

## Top 5 Worst Offenders (files with most concurrent violations)

| Rank | File | Checks Failed | Key Issues |
|------|------|---------------|------------|
| 1 | `shared/replay_engine.py` | 1,2,3,4,5,8 | 1641 LOC god module; 5 functions with complexity >29; 5 functions >100 lines; 9+ params; magic `999` sentinel |
| 2 | `captain-offline/.../b3_pseudotrader.py` | 1,2,3,4,5,8 | 1117 LOC; 2 functions with complexity >42; 2 functions >107 lines; duplicate `PBO_THRESHOLD`; `4500` drawdown |
| 3 | `captain-online/.../b4_kelly_sizing.py` | 1,2,3,5,6,8 | `run_kelly_sizing()` at complexity 38, 172 lines, 12 params; `999` sentinel x9; unnamed Kelly multipliers |
| 4 | `captain-online/.../b1_features.py` | 1,2,3,4 | 1106 LOC; 75 functions; `compute_all_features()` complexity 56, 141 lines |
| 5 | `captain-command/.../b2_gui_data_server.py` | 1,3,4,7 | 1300 LOC; 32 endpoints in one file; nested query N+1; `aim_id==16` magic |

---

## Side-Effect Cascade Summary

| Module | Sinks (0-1) | Shallow Pipes (2) | Deep Pipes (3+) | Sink Ratio |
|--------|-------------|--------------------|------------------|------------|
| shared/ (clients, vault, journal) | 8 | 0 | 0 | 100% |
| shared/topstep_client | 5 | 0 | 0 | 100% |
| offline/blocks | 7 | 0 | 0 | 100% |
| online/blocks | 4 | 2 | 0 | 67% |
| command/blocks | 5 | 1 | 3 | 56% |

Captain-command is the only process with deep pipes, driven by the notification injection pattern where `notify_fn` callbacks add hidden cascade depth.

---

## Priority Remediation Roadmap

### Quick Wins (Effort S, highest impact)

1. **Constants centralisation** (findings 41-46, 76-87): Define ~15 named constants in `shared/constants.py` or a new `shared/thresholds.py`. Import `EVAL_MLL` from `account_lifecycle.py` instead of hardcoding `4500`. ~2 hours, eliminates 18 findings.

2. **N+1 batch inserts** (findings 38, 72): Replace `cur.execute` loops with `executemany` in `b1_dma_update.py` and `b8_kelly_update.py`. ~1 hour, eliminates 2 HIGH findings on the feedback loop critical path.

3. **Parameter object dataclasses** (findings 27, 31, 34, 35): Create `TradeOutcome`, `DiagnosticAction`, `NotificationRecord` dataclasses for the worst 20-param, 11-param, 9-param signatures. ~2 hours, eliminates 4 HIGH findings.

### Medium Term (Effort M)

4. **Split `replay_engine.py`** (finding 23): Extract into `replay_config.py`, `orb_simulator.py`, `replay_runner.py`, `whatif_engine.py`. Eliminates 5 HIGH complexity + 1 HIGH god module.

5. **Split `b1_features.py`** (finding 26): Group 75 functions into per-AIM-family modules. Eliminates 1 HIGH god module + 1 HIGH complexity.

6. **Batch pre-load in `b1_data_ingestion`** (finding 40): Pre-fetch feature availability into a dict keyed by `(asset_id, feature)` before the asset loop.

### Long Term (Effort L)

7. **Split `b3_pseudotrader.py`** and **`b2_gui_data_server.py`** (findings 24-25): Major refactors splitting 1000+ line modules into focused sub-modules.

8. **Flatten notification cascade** (finding 47): Refactor `run_daily_reconciliation` to call `route_notification` directly from reconciliation loop rather than threading through `_check_payout_recommendation`.
