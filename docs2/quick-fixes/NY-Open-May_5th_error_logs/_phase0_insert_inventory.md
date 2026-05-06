# Phase 0B — INSERT/UPDATE site inventory

## 1. Summary counts

| Metric | Value |
|--------|------:|
| **Total `cur.execute` INSERT sites** (`INSERT INTO p3_*` / `p3_*` tables in scoped code) | **129** |
| **Total `cur.execute` UPDATE sites** (`UPDATE p3_*` / `UPDATE p2_*`) | **0** |
| **`p2_*` INSERT/UPDATE** | **0** |

### Per bucket

| Bucket | INSERT sites |
|--------|-------------:|
| captain-online | 16 |
| captain-offline | 42 |
| captain-command | 33 |
| shared (`cur.execute` only) | 1 |
| scripts | 37 |

### F-string-built INSERT (needs explicit `columns=` / hand review)

| Location | Cursor | Notes |
|----------|--------|-------|
| `shared/questdb_client.py:243` (inside `update_d00_fields`) | `c.execute` | `D00_COLUMNS + ["last_updated"]` joined into SQL |
| `scripts/bootstrap_production.py:184` | `cur.execute` | Same D00 pattern |
| `scripts/reset_capital_state_to_broker_truth.py:237` | `cur.execute` | `D08_FIELDS + ", last_updated"` joined |

So **3** f-string INSERT constructions affecting production D00/D08 writers (one uses `c`, not `cur`).

---

## 2. Inventory table (one row per opening `*.execute(` line)

| process | file | line | statement | table | columns_static | f_string | needs_explicit_columns |
|---------|------|------|-----------|-------|----------------|----------|------------------------|
| online | captain-online/captain_online/blocks/orchestrator.py | 998 | INSERT | p3_d23_circuit_breaker_intraday | YES (10) | no | no |
| online | captain-online/captain_online/blocks/b7_position_monitor.py | 550 | INSERT | p3_d03_trade_outcome_log | YES (24) | no | no |
| online | captain-online/captain_online/blocks/b7_position_monitor.py | 664 | INSERT | p3_d16_user_capital_silos | YES (14) | no | no |
| online | captain-online/captain_online/blocks/b7_position_monitor.py | 677 | INSERT | p3_d23_circuit_breaker_intraday | YES (10) | no | no |
| online | captain-online/captain_online/blocks/b6_signal_output.py | 443 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| online | captain-online/captain_online/blocks/hmm_inference_block.py | 121 | INSERT | p3_d26_hmm_opportunity_state | YES (9) | no | no |
| online | captain-online/captain_online/blocks/b1_data_ingestion.py | 741 | INSERT | p3_d21_incident_log | YES (7) | no | no |
| online | captain-online/captain_online/blocks/b1_data_ingestion.py | 760 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| online | captain-online/captain_online/blocks/b1_features.py | 738 | INSERT | p3_spread_history | YES (4) | no | no |
| online | captain-online/captain_online/blocks/b1_features.py | 1427 | INSERT | p3_d29_opening_volumes | YES (7) | no | no |
| online | captain-online/captain_online/blocks/b1_features.py | 1459 | INSERT | p3_d33_opening_volatility | YES (3) | no | no |
| online | captain-online/captain_online/blocks/b1_features.py | 1500 | INSERT | p3_d30_daily_ohlcv | YES (8) | no | no |
| online | captain-online/captain_online/blocks/b9_capacity_evaluation.py | 296 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| online | captain-online/captain_online/blocks/b8_concentration_monitor.py | 134 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| online | captain-online/captain_online/blocks/b8_concentration_monitor.py | 158 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| online | captain-online/captain_online/blocks/b5b_quality_gate.py | 166 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| offline | captain-offline/captain_offline/blocks/version_snapshot.py | 210 | INSERT | p3_d18_version_history | YES (6) | no | no |
| offline | captain-offline/captain_offline/blocks/orchestrator.py | 867 | INSERT | p3_offline_job_queue | YES (6) | no | no |
| offline | captain-offline/captain_offline/blocks/orchestrator.py | 892 | INSERT | p3_d22b_asset_rerun_status | YES (4) | no | no |
| offline | captain-offline/captain_offline/blocks/orchestrator.py | 912 | INSERT | p3_offline_job_queue | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b9_diagnostic.py | 872 | INSERT | p3_d22_system_health_diagnostic | YES (11) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_dma_update.py | 253 | INSERT | p3_d02_aim_meta_weights | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b3_pseudotrader.py | 550 | INSERT | p3_d11_pseudotrader_results | YES (9) | no | no |
| offline | captain-offline/captain_offline/blocks/b3_pseudotrader.py | 1031 | INSERT | p3_d11_pseudotrader_results | YES (12) | no | no |
| offline | captain-offline/captain_offline/blocks/b3_pseudotrader.py | 1367 | INSERT | p3_d11_pseudotrader_results | YES (9) | no | no |
| offline | captain-offline/captain_offline/blocks/b3_pseudotrader.py | 1555 | INSERT | p3_d11_pseudotrader_results | YES (9) | no | no |
| offline | captain-offline/captain_offline/blocks/b3_pseudotrader.py | 2025 | INSERT | p3_d27_pseudotrader_forecasts | YES (11) | no | no |
| offline | captain-offline/captain_offline/blocks/b7_tsm_simulation.py | 132 | INSERT | p3_d08_tsm_state | YES (32) | no | no |
| offline | captain-offline/captain_offline/blocks/b8_cb_params.py | 239 | INSERT | p3_d25_circuit_breaker_params | YES (11) | no | no |
| offline | captain-offline/captain_offline/blocks/b8_kelly_update.py | 120 | INSERT | p3_d05_ewma_states | YES (8) | no | no |
| offline | captain-offline/captain_offline/blocks/b8_kelly_update.py | 292 | INSERT | p3_d12_kelly_parameters | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b8_kelly_update.py | 302 | INSERT | p3_d12_kelly_parameters | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b4_injection.py | 125 | INSERT | p3_d06_injection_history | YES (11) | no | no |
| offline | captain-offline/captain_offline/blocks/b4_injection.py | 316 | INSERT | p3_d06b_active_transitions | YES (9) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_aim16_hmm.py | 197 | INSERT | p3_d26_hmm_opportunity_state | YES (9) | no | no |
| offline | captain-offline/captain_offline/blocks/b5_sensitivity.py | 256 | INSERT | p3_d13_sensitivity_scan_results | YES (9) | no | no |
| offline | captain-offline/captain_offline/blocks/b5_sensitivity.py | 268 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/blocks/b5_sensitivity.py | 287 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/blocks/b2_cusum.py | 197 | INSERT | p3_d04_decay_detector_states | YES (4) | no | no |
| offline | captain-offline/captain_offline/blocks/b2_level_escalation.py | 73 | INSERT | p3_d04_decay_detector_states | YES (3) | no | no |
| offline | captain-offline/captain_offline/blocks/b2_level_escalation.py | 85 | INSERT | p3_d12_kelly_parameters | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b2_level_escalation.py | 158 | INSERT | p3_offline_job_queue | YES (8) | no | no |
| offline | captain-offline/captain_offline/blocks/b2_bocpd.py | 250 | INSERT | p3_d04_decay_detector_states | YES (11) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_aim_lifecycle.py | 90 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_aim_lifecycle.py | 104 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_aim_lifecycle.py | 299 | INSERT | p3_d01_aim_model_states | YES (6) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_hdwm_diversity.py | 83 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_hdwm_diversity.py | 92 | INSERT | p3_d02_aim_meta_weights | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_drift_detection.py | 226 | INSERT | p3_d04_decay_detector_states | YES (3) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_drift_detection.py | 277 | INSERT | p3_d02_aim_meta_weights | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_drift_detection.py | 347 | INSERT | p3_d02_aim_meta_weights | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/b1_drift_detection.py | 356 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/main.py | 76 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/main.py | 86 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| offline | captain-offline/captain_offline/blocks/bootstrap.py | 132 | INSERT | p3_d05_ewma_states | YES (8) | no | no |
| offline | captain-offline/captain_offline/blocks/bootstrap.py | 149 | INSERT | p3_d04_decay_detector_states | YES (8) | no | no |
| offline | captain-offline/captain_offline/blocks/bootstrap.py | 181 | INSERT | p3_d12_kelly_parameters | YES (7) | no | no |
| offline | captain-offline/captain_offline/blocks/bootstrap.py | 202 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 524 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 562 | INSERT | p3_d08_tsm_state | YES (32) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 601 | INSERT | p3_d23_circuit_breaker_intraday | YES (10) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 769 | INSERT | p3_d08_tsm_state | YES (32) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 801 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 861 | INSERT | p3_d08_tsm_state | YES (32) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 893 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b8_reconciliation.py | 914 | INSERT | p3_d19_reconciliation_log | YES (8) | no | no |
| command | captain-command/captain_command/blocks/b3_api_adapter.py | 693 | INSERT | p3_d14_api_connection_states | YES (5) | no | no |
| command | captain-command/captain_command/blocks/b3_api_adapter.py | 710 | INSERT | p3_d14_api_connection_states | YES (5) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 414 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 445 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 467 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 494 | INSERT | p3_d10_notification_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 513 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 531 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 550 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 569 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b1_core_routing.py | 594 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/main.py | 306 | INSERT | p3_d16_user_capital_silos | YES (14) | no | no |
| command | captain-command/captain_command/api.py | 376 | INSERT | p3_audit_log | YES (6) | no | no |
| command | captain-command/captain_command/api.py | 1046 | INSERT | p3_replay_presets | YES (5) | no | no |
| command | captain-command/captain_command/blocks/b6_reports.py | 686 | INSERT | p3_d09_report_archive | YES (7) | no | no |
| command | captain-command/captain_command/blocks/b4_tsm_manager.py | 455 | INSERT | p3_d08_tsm_state | YES (21) | no | no |
| command | captain-command/captain_command/blocks/b7_notifications.py | 433 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b7_notifications.py | 532 | INSERT | p3_d10_notification_log | YES (13) | no | no |
| command | captain-command/captain_command/blocks/b7_notifications.py | 566 | INSERT | p3_d10_notification_log | YES (15) | no | no |
| command | captain-command/captain_command/blocks/b7_notifications.py | 591 | INSERT | p3_d10_notification_log | YES (14) | no | no |
| command | captain-command/captain_command/blocks/b5_injection_flow.py | 247 | INSERT | p3_session_event_log | YES (6) | no | no |
| command | captain-command/captain_command/blocks/b11_replay_runner.py | 316 | INSERT | p3_replay_results | YES (10) | no | no |
| command | captain-command/captain_command/blocks/b9_incident_response.py | 185 | INSERT | p3_d21_incident_log | YES (10) | no | no |
| command | captain-command/captain_command/blocks/b9_incident_response.py | 359 | INSERT | p3_d21_incident_log | YES (9) | no | no |
| command | captain-command/captain_command/blocks/telegram_bot.py | 652 | INSERT | p3_session_event_log | YES (6) | no | no |
| shared | shared/trade_source.py | 300 | INSERT | p3_d03_trade_outcome_log | YES (23) | no | no |
| scripts | scripts/bootstrap_production.py | 184 | INSERT | p3_d00_asset_universe | NO (D00_COLUMNS + last_updated) | YES | YES |
| scripts | scripts/bootstrap_production.py | 291 | INSERT | p3_d16_user_capital_silos | YES (14) | no | no |
| scripts | scripts/bootstrap_production.py | 348 | INSERT | p3_d02_aim_meta_weights | YES (7) | no | no |
| scripts | scripts/bootstrap_production.py | 389 | INSERT | p3_d25_circuit_breaker_params | YES (11) | no | no |
| scripts | scripts/reset_capital_state_to_broker_truth.py | 151 | INSERT | p3_d16_user_capital_silos | YES (14) | no | no |
| scripts | scripts/reset_capital_state_to_broker_truth.py | 237 | INSERT | p3_d08_tsm_state | NO (D08_FIELDS + last_updated) | YES | YES |
| scripts | scripts/reset_capital_state_to_broker_truth.py | 263 | INSERT | p3_d23_circuit_breaker_intraday | YES (10) | no | no |
| scripts | scripts/load_p2_multi_asset.py | 281 | INSERT | p3_d00_asset_universe | YES (19) | no | no |
| scripts | scripts/load_p2_multi_asset.py | 320 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| scripts | scripts/backfill_d03_pnl_inflation.py | 229 | INSERT | p3_d03_trade_outcome_log | YES (24) | no | no |
| scripts | scripts/backfill_d03_signal_ids.py | 77 | INSERT | p3_d03_trade_outcome_log | YES (24) | no | no |
| scripts | scripts/debug_d08_transport.py | 147 | INSERT | p3_d08_tsm_state | YES (21) | no | no |
| scripts | scripts/debug_d08_transport.py | 164 | INSERT | p3_d08_tsm_state | YES (21) | no | no |
| scripts | scripts/debug_d08_transport.py | 182 | INSERT | p3_d08_tsm_state | YES (21) | no | no |
| scripts | scripts/debug_d08_transport.py | 234 | INSERT | p3_d08_tsm_state | YES (21) | no | no |
| scripts | scripts/debug_d08_insert.py | 181 | INSERT | p3_d08_tsm_state | YES (21) | partial | no |
| scripts | scripts/debug_d08_insert.py | 282 | INSERT | p3_d08_tsm_state | varies (VARIANT E built SQL) | partial | YES |
| scripts | scripts/seed_test_asset.py | 56 | INSERT | p3_d00_asset_universe | YES (19) | no | no |
| scripts | scripts/seed_test_asset.py | 96 | INSERT | p3_d15_user_session_data | YES (9) | no | no |
| scripts | scripts/seed_test_asset.py | 116 | INSERT | p3_d16_user_capital_silos | YES (14) | no | no |
| scripts | scripts/seed_ohlcv_from_qc.py | 58 | INSERT | p3_d30_daily_ohlcv | YES (8) | no | no |
| scripts | scripts/seed_ohlcv_from_qc.py | 101 | INSERT | p3_d30_daily_ohlcv | YES (8) | no | no |
| scripts | scripts/seed_all_assets.py | 197 | INSERT | p3_d00_asset_universe | YES (19) | no | no |
| scripts | scripts/seed_all_assets.py | 235 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| scripts | scripts/seed_real_asset.py | 311 | INSERT | p3_d00_asset_universe | YES (19) | no | no |
| scripts | scripts/seed_real_asset.py | 344 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| scripts | scripts/fix_bootstrap_data.py | 112 | INSERT | p3_d05_ewma_states | YES (8) | no | no |
| scripts | scripts/fix_bootstrap_data.py | 137 | INSERT | p3_d01_aim_model_states | YES (5) | no | no |
| scripts | scripts/fix_bootstrap_data.py | 167 | INSERT | p3_d08_tsm_state | YES (21) | no | no |
| scripts | scripts/paper_trader.py | 399 | INSERT | p3_d03_trade_outcome_log | YES (13) | no | no |
| scripts | scripts/paper_trader.py | 425 | INSERT | p3_d03_trade_outcome_log | YES (18) | no | no |
| scripts | scripts/bootstrap_opening_volumes.py | 182 | INSERT | p3_d29_opening_volumes | YES (7) | no | no |
| scripts | scripts/seed_or_volumes_from_qc.py | 95 | INSERT | p3_d29_opening_volumes | YES (7) | no | no |
| scripts | scripts/seed_system_params.py | 96 | INSERT | p3_d17_system_monitor_state | YES (4) | no | no |
| scripts | scripts/seed_opening_vol_from_qc.py | 82 | INSERT | p3_d33_opening_volatility | YES (7) | no | no |
| scripts | scripts/seed_skew_from_extract.py | 47 | INSERT | p3_d32_options_skew | YES (5) | no | no |
| scripts | scripts/seed_iv_rv_from_extract.py | 47 | INSERT | p3_d31_implied_vol | YES (5) | no | no |

---

## 3. Per-bucket file list (Phase 3 allocation)

### Bucket 3a — captain-online (9 files)

- `captain-online/captain_online/blocks/b1_data_ingestion.py`
- `captain-online/captain_online/blocks/b1_features.py`
- `captain-online/captain_online/blocks/b5b_quality_gate.py`
- `captain-online/captain_online/blocks/b6_signal_output.py`
- `captain-online/captain_online/blocks/b7_position_monitor.py`
- `captain-online/captain_online/blocks/b8_concentration_monitor.py`
- `captain-online/captain_online/blocks/b9_capacity_evaluation.py`
- `captain-online/captain_online/blocks/hmm_inference_block.py`
- `captain-online/captain_online/blocks/orchestrator.py`

### Bucket 3b — captain-offline (19 files)

- `captain-offline/captain_offline/main.py`
- `captain-offline/captain_offline/blocks/b1_aim16_hmm.py`
- `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py`
- `captain-offline/captain_offline/blocks/b1_dma_update.py`
- `captain-offline/captain_offline/blocks/b1_drift_detection.py`
- `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py`
- `captain-offline/captain_offline/blocks/b2_bocpd.py`
- `captain-offline/captain_offline/blocks/b2_cusum.py`
- `captain-offline/captain_offline/blocks/b2_level_escalation.py`
- `captain-offline/captain_offline/blocks/b3_pseudotrader.py`
- `captain-offline/captain_offline/blocks/b4_injection.py`
- `captain-offline/captain_offline/blocks/b5_sensitivity.py`
- `captain-offline/captain_offline/blocks/b7_tsm_simulation.py`
- `captain-offline/captain_offline/blocks/b8_cb_params.py`
- `captain-offline/captain_offline/blocks/b8_kelly_update.py`
- `captain-offline/captain_offline/blocks/b9_diagnostic.py`
- `captain-offline/captain_offline/blocks/bootstrap.py`
- `captain-offline/captain_offline/blocks/orchestrator.py`
- `captain-offline/captain_offline/blocks/version_snapshot.py`

### Bucket 3c — captain-command (12 files)

- `captain-command/captain_command/api.py`
- `captain-command/captain_command/main.py`
- `captain-command/captain_command/blocks/b1_core_routing.py`
- `captain-command/captain_command/blocks/b3_api_adapter.py`
- `captain-command/captain_command/blocks/b4_tsm_manager.py`
- `captain-command/captain_command/blocks/b5_injection_flow.py`
- `captain-command/captain_command/blocks/b6_reports.py`
- `captain-command/captain_command/blocks/b7_notifications.py`
- `captain-command/captain_command/blocks/b8_reconciliation.py`
- `captain-command/captain_command/blocks/b9_incident_response.py`
- `captain-command/captain_command/blocks/b11_replay_runner.py`
- `captain-command/captain_command/blocks/telegram_bot.py`

### Bucket 3d — shared + scripts (~22 files, but many are debug/seed and lower priority)

- `shared/questdb_client.py` — `c.execute` f-string D00 INSERT (`update_d00_fields`)
- `shared/trade_source.py`
- `scripts/bootstrap_production.py` (production-critical)
- `scripts/reset_capital_state_to_broker_truth.py` (production-critical)
- `scripts/backfill_d03_pnl_inflation.py`
- `scripts/backfill_d03_signal_ids.py`
- `scripts/load_p2_multi_asset.py`
- `scripts/seed_*.py` (10 files, low priority — runbook scripts)
- `scripts/fix_bootstrap_data.py`
- `scripts/paper_trader.py`
- `scripts/bootstrap_opening_volumes.py`
- `scripts/debug_d08_*.py` (3 files, dev debug only — descope)

---

## 4. Special-case sites

- **`_cur` instead of `cur`:** `captain-online/captain_online/blocks/b1_features.py:738` (`p3_spread_history`).
- **`c.execute` instead of `cur`:** `shared/questdb_client.py:243` (`update_d00_fields`).
- **SQL held in a variable:** `captain-command/captain_command/blocks/b4_tsm_manager.py` (`sql = """INSERT..."""` then `cur.execute(sql, params)`).
- **`cur.execute(mogrified)` / dynamic SQL string:** `scripts/debug_d08_insert.py:181`, `scripts/debug_d08_insert.py:282` (VARIANT E builds SQL with substituted literals).
- **Literal-only INSERT (no `%s` params):** `scripts/debug_d08_transport.py:234` — pass-through.
- **Single-line concatenated SQL string:** `captain-offline/captain_offline/blocks/b1_drift_detection.py:227` (`"INSERT INTO p3_d04... " + ...`).
- **`cur.executemany`** for `p3_*` in scoped code: `scripts/restore_live_delta.py` for `p3_d30_daily_ohlcv`, `p3_d29_opening_volumes`, `p3_d33_opening_volatility`, `p3_spread_history` — excluded from the 129 count; migrate separately.
- **Partial / alternate D03 column sets:** `scripts/paper_trader.py:399` (13 cols) and `:425` (18 cols) vs production `b7` / `trade_source` shapes.
- **HTTP-only probes (no `cur.execute` INSERT):** `scripts/debug_d08_bisect.py`, `scripts/debug_d08_minimal_repro.py`, `scripts/debug_d08_fix_probe.py` — not in inventory.

---

## 5. Confidence note

- Every inventory row was tied to a direct file read or multiline grep anchored to the **opening `cur.execute(`** line.
- `tests/` and `docs2/` excluded as requested.
- Inventory targets literal `cur.execute` call sites; `cursor.execute`, `c.execute`, and `executemany` only noted in Special cases.
- **UPDATE:** Repo-wide scoped search found **no** `UPDATE p3_*` / `UPDATE p2_*` SQL in production paths — OLTP style is **append-only INSERT**.

**Total INSERT call sites in scope for Phase 3 migration: 129.**
