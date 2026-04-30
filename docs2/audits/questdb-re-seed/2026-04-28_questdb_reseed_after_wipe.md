# QuestDB Re-Seed Audit After Full Wipe

**Date:** 2026-04-28  
**Scope:** What happens when `questdb/db/` is emptied, containers restarted, and the normal init/seed path runs.  
**Trigger paths audited:** `scripts/captain-update.sh`, `scripts/captain-setup.sh`, `scripts/init_all.py`

---

## Section A — Auto-Reseed Inventory

### A.1 What `captain-update.sh` Does (the primary post-wipe path)

The update script executes these steps in order:

| Step | Script | What It Does |
|------|--------|-------------|
| 6 | `scripts/init_questdb.py` | Creates all 38 tables from `shared/canonical_schemas.py` `CANONICAL_DDLS` list + applies `CANONICAL_MIGRATIONS` (42 ALTER TABLE migrations). Schema only — no data. |
| 6a-1 | `scripts/seed_all_assets.py` | Full 17-asset registration + bootstrap for 10 active assets. See A.2 below. |
| 6a-2 | `scripts/seed_iv_rv_from_extract.py` | Seeds `p3_d31_implied_vol` from CSV. |
| 6a-3 | `scripts/seed_skew_from_extract.py` | Seeds `p3_d32_options_skew` from CSV. |
| 6a-4 | `scripts/seed_ohlcv_from_qc.py` | Seeds `p3_d30_daily_ohlcv` from CSV. |
| 6a-5 | `scripts/seed_or_volumes_from_qc.py` | Seeds `p3_d29_opening_volumes` from CSV. |
| 6a-6 | `scripts/seed_opening_vol_from_qc.py` | Seeds `p3_d33_opening_volatility` from CSV. |
| 6b | inline Python | Integrity check: verifies D00 ≥ 10 rows, D01 ≥ 50, D02 ≥ 50, D12 ≥ 10, D16 ≥ 1. |

### A.2 Detailed Table-by-Table Inventory

#### Tables populated by `seed_all_assets.py`

This script reads committed P1/P2 JSON files under `data/`, calls `captain_offline.blocks.bootstrap.asset_bootstrap()` for the 10 active assets, and registers all 17 assets.

| Table | Domain | Rows After Seed | Data Source on Disk | Recency Rule |
|-------|--------|-----------------|---------------------|--------------|
| `p3_d00_asset_universe` | D00 — Asset registry | 17 (10 ACTIVE + 1 P2_ELIM + 6 P1_ELIM) | `data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json`, `data/p2_outputs/{ASSET}/p2_d08_classifier_validation.json`, hardcoded `ASSET_SPECS` dict in script | **Frozen to committed data.** Strategy (m,k), OO, contract specs are from P2 outputs committed to git. Point values/margins are hardcoded. |
| `p3_d01_aim_model_states` | D01 — AIM states | ~60 (10 assets × 6 Tier 1 AIMs) | Hardcoded `TIER1_AIMS = [4, 6, 8, 11, 12, 15]`. Status set to INSTALLED, then promoted to BOOTSTRAPPED by `asset_bootstrap()`. | **Frozen.** No `model_object` is populated — just status + warmup_progress. Live AIM training fills `model_object` at runtime. |
| `p3_d04_decay_detector_states` | D04 — BOCPD/CUSUM | 10 (one per active asset) | Computed from P1 D-22 trade returns: `data/p1_outputs/{ASSET}/d22_trade_log_{asset}.json` | **Frozen to P1 research.** ES trades span 2009-12-23 → 2025-12-19. CUSUM allowance = `std(returns) * 0.5`, `bocpd_cp_probability = 0.01`. No live changepoints. |
| `p3_d05_ewma_states` | D05 — EWMA win rate / avg win / avg loss | 60 (10 assets × 2 regimes × 3 sessions) | Computed from P1 D-22 trades + P2 D-02 regime labels: `data/p1_outputs/{ASSET}/d22_trade_log_{asset}.json`, `data/p2_outputs/{ASSET}/p2_d02_regime_labels.json` | **Frozen to P1/P2 research.** Historical unconditional stats. No live trade outcomes incorporated. |
| `p3_d12_kelly_parameters` | D12 — Kelly fractions | 60 (10 assets × 2 regimes × 3 sessions) | Derived from D05 EWMA stats in same bootstrap call. `kelly_full = max(0, p - (1-p)/b)`, shrinkage from sqrt(n_trades). | **Frozen to P1/P2 research.** Same vintage as D05. |

#### Tables populated by AIM data seed scripts (CSV-based)

| Table | Domain | Script | CSV Source | Assets Covered | Committed Date Range | How to Find Max Date |
|-------|--------|--------|------------|----------------|---------------------|---------------------|
| `p3_d30_daily_ohlcv` | D30 — Daily bars | `seed_ohlcv_from_qc.py` | `data/seed/aim_data/ohlcv_{ASSET}.csv` + `ohlcv_combined.csv` | All 10 active | ~2025-02-25 → 2026-03-30 (ES per-asset); combined has all 10 up to ~2026-03-30 | `tail -1 data/seed/aim_data/ohlcv_ES.csv` or inspect `ohlcv_combined.csv` |
| `p3_d31_implied_vol` | D31 — IV/RV | `seed_iv_rv_from_extract.py` | `data/seed/aim_data/es_iv_rv.csv` | **ES only** | 2025-08-22 → 2026-03-27 (122 rows) | `tail -1 data/seed/aim_data/es_iv_rv.csv` |
| `p3_d32_options_skew` | D32 — CBOE skew | `seed_skew_from_extract.py` | `data/seed/aim_data/es_skew.csv` | **ES only** | 2025-12-03 → 2026-03-31 (81 rows) | `tail -1 data/seed/aim_data/es_skew.csv` |
| `p3_d29_opening_volumes` | D29 — OR volume | `seed_or_volumes_from_qc.py` | `data/seed/or_volume_data/{ASSET}_or_volume.csv` | All 10 active | ~2026-02-25 → 2026-03-30 (ES: 480 1-min bar rows → daily aggregates) | `tail -1 data/seed/or_volume_data/ES_or_volume.csv` |
| `p3_d33_opening_volatility` | D33 — Opening vol | `seed_opening_vol_from_qc.py` | Same OR volume CSVs as D29 | All 10 active | Same as D29 per asset | Same inspection as D29 |

### A.3 What `captain-setup.sh` Adds Beyond `captain-update.sh`

The fresh-install setup script calls **everything captain-update.sh does** plus:

| Script | Tables | What It Adds |
|--------|--------|-------------|
| `scripts/bootstrap_production.py` | D00 (overlay), D02, D16, D25 | **Phase 1:** Overlays D00 with full `locked_strategy` JSON (includes `feature_threshold`, `regime_method`, TP/SL multiples, `sl_distance`), `point_value`, `tick_size`, `margin_per_contract`, `session_hours`, sets `captain_status=ACTIVE`. **Phase 2:** Creates `p3_d16_user_capital_silos` row linking account to user with starting capital. **Phase 3:** Seeds `p3_d02_aim_meta_weights` (60 rows, equal 1/6 probability). **Phase 4:** Seeds `p3_d25_circuit_breaker_params` (cold-start, `beta_b=0`). |

### A.4 What `init_all.py` Adds (not called by either shell script)

| Script | Tables | What It Adds |
|--------|--------|-------------|
| `scripts/seed_system_params.py` | D17 | 36 system parameter rows (quality thresholds, risk limits, AIM config, execution mode, etc.) |
| `scripts/seed_test_asset.py` | D00, D15, D16 | Test ES asset + `primary_user` session + test capital silo. Overlaps with `seed_all_assets.py` and `bootstrap_production.py`. |

### A.5 Implicit Runtime Seeding (no explicit seed script)

| Table | Domain | How It Gets Populated | Trigger |
|-------|--------|----------------------|---------|
| `p3_d08_tsm_state` | D08 — TSM | `captain-command/main.py` → `_link_tsm_to_account()` → `b4_tsm_manager._store_tsm_in_d08()`. Reads TSM JSON from `config/tsm/` directory, merges with live account balance from TopstepX API. | captain-command container startup, **requires TopstepX authentication**. |
| `p3_d14_api_connection_states` | D14 — API heartbeat | Written by `captain-command/blocks/b3_api_adapter.py` at runtime. | Continuous during WebSocket connection. |
| `p3_d23_circuit_breaker_intraday` | D23 — Intraday CB | Written by Command at session start. | Each trading session. |

### A.6 VIX/VXV Data (Not in QuestDB)

VIX/VXV data lives as **flat CSV files** read at runtime by `shared/vix_provider.py`:

| File | Path | Date Range | Rows |
|------|------|-----------|------|
| VIX daily close | `data/vix/vix_daily_close.csv` | 1990-01-02 → 2026-04-09 | 9161 |
| VXV daily close | `data/vix/vxv_daily_close.csv` | Similar range | Similar |

These are **not QuestDB tables** — they survive a QuestDB wipe. To update: `python scripts/update_vix_daily.py` (fetches from Yahoo Finance, no API key needed).

---

## Section B — Staleness / API Assessment

### B.1 Always Stale After Wipe (Committed CSV-Bounded)

These tables are re-seeded from committed files only. Their data ends at the CSV file's max date, which is frozen at the last git commit that refreshed them.

| Domain | Committed Frontier (approximate) | Gap After Wipe |
|--------|----------------------------------|----------------|
| D30 OHLCV (all 10 assets) | ~2026-03-30 | Every trading day after 2026-03-30 is missing. Online `b1_features.py` writes new D30 rows at runtime, but only going forward. |
| D31 IV/RV (**ES only**) | 2026-03-27 | All other 9 assets have **zero** IV/RV data. ES is missing everything after 2026-03-27. |
| D32 Options Skew (**ES only**) | 2026-03-31 | Same: 9 assets completely empty. ES missing after 2026-03-31. |
| D29 OR Volumes (all 10) | ~2026-03-30 | Missing after frontier. `or_range_first_m_min` column is NULL in CSV seeds (backfill requires `bootstrap_opening_volumes.py` + TopstepX API). |
| D33 Opening Vol (all 10) | ~2026-03-30 | Missing after frontier. |
| D04 BOCPD/CUSUM | Frozen to P1 research (trades ending ~2025-12-19) | No live changepoint history. Cold-start values only. |
| D05 EWMA | Frozen to P1 research | No live trade outcomes reflected. |
| D12 Kelly | Frozen to P1 research | Derived from frozen D05 stats. |
| D01 AIM model_object | Always NULL after seed | AIM model objects (trained parameters) are lost. Requires live training iterations to rebuild. |

### B.2 Refreshable via Live API or Specific Scripts

| Domain | How to Refresh | Script / Command | Needs API? |
|--------|---------------|-----------------|-----------|
| D08 TSM state | Auto-linked at captain-command startup | `captain-command/main.py` → `_link_tsm_to_account()` | **Yes** — TopstepX API for live account balance. Also reads `config/tsm/*.json` files. |
| D29 `or_range_first_m_min` backfill | Manual script | `python scripts/bootstrap_opening_volumes.py` | **Yes** — TopstepX historical minute bars API. Fetches last 35 days. |
| D30-D33 going forward | Automatic at runtime | Online `b1_features.py` / `b1_data_ingestion.py` writes new rows each session. | **Yes** — TopstepX WebSocket market data. |
| VIX/VXV CSVs | Manual script | `python scripts/update_vix_daily.py` | No (Yahoo Finance, no key). |
| Delta restore (D29/D30/D33/spread) | Manual script with pre-wipe backup | `python scripts/restore_live_delta.py --backup-dir <path>` | No — reads from backup CSVs produced by `scripts/backup_live_tables.py`. |

### B.3 Never Re-Seeded (Runtime-Only or Lost)

These tables start **empty** after wipe and only accumulate data through live system operation:

| Table | Domain | How Populated |
|-------|--------|--------------|
| `p3_d03_trade_outcome_log` | D03 — Trade history | Online B7 `b7_position_monitor.py` writes on trade close. **All historical trade records are lost.** |
| `p3_d06_injection_history` | D06 — Strategy injection | Offline `b5_strategy_injection.py`. |
| `p3_d06b_active_transitions` | D06b — Strategy transitions | Offline `b5_strategy_injection.py`. |
| `p3_d07_correlation_model_states` | D07 — Correlation | Offline correlation block. |
| `p3_d09_report_archive` | D09 — Reports | Offline report generation. |
| `p3_d10_notification_log` | D10 — Notifications | Command notification system. |
| `p3_d11_pseudotrader_results` | D11 — Pseudotrader | Offline `b3_pseudotrader.py`. |
| `p3_d13_sensitivity_scan_results` | D13 — Sensitivity | Offline sensitivity scanner. |
| `p3_d18_version_history` | D18 — Versions | Runtime version tracking. |
| `p3_d19_reconciliation_log` | D19 — Reconciliation | Command `b8_reconciliation.py`. |
| `p3_d21_incident_log` | D21 — Incidents | Runtime incident response. |
| `p3_d22_system_health_diagnostic` | D22 — Health | Offline system health. |
| `p3_d22b_asset_rerun_status` | D22b — Rerun status | Offline rerun tracking. |
| `p3_d26_hmm_opportunity_state` | D26 — HMM | Offline training + Online inference. Cold-start. |
| `p3_d27_pseudotrader_forecasts` | D27 — Forecasts | Offline pseudotrader. |
| `p3_d28_account_lifecycle` | D28 — Account events | Command account lifecycle tracking. |
| `p2_d07_regime_models` | P2 regime models | Empty. Only populated by P1/P2 pipeline reruns (external repo). |
| `p3_spread_history` | Spread samples | Online `b1_data_ingestion.py`. |
| `p3_session_event_log` | Session events | Runtime. |
| `p3_replay_results` | Replay results | Manual replay tools. |
| `p3_replay_presets` | Replay presets | User-created. |
| `p3_offline_job_queue` | Job queue | Runtime Offline orchestrator. |
| `p3_audit_log` | Audit trail | Command API. |

---

## Section C — Post-Wipe Manual Checklist

### C.1 MUST-DO (ordered)

1. **Pre-wipe backup (if possible).** Before wiping, run:
   ```bash
   docker compose exec -T captain-offline python scripts/backup_live_tables.py --backup-root ~/captain-backups
   ```
   This captures D30/D29/D33/spread_history + monetary migration tables (D08/D23/D25/D28/D03/D16/D00) to CSV. File: `scripts/backup_live_tables.py`.

2. **Wipe and restart:**
   ```bash
   docker compose down
   rm -rf questdb/db/*
   docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
   ```

3. **Run `captain-update.sh` (handles Steps 4-6 automatically):**
   ```bash
   bash scripts/captain-update.sh --skip-pull
   ```
   This runs: `init_questdb.py` → `seed_all_assets.py` → 5 AIM data seed scripts → integrity check.
   
   **Covers:** D00, D01, D04, D05, D12 (from P1/P2 data), D29, D30, D31, D32, D33 (from committed CSVs).
   
   **Does NOT cover:** D02, D08, D16, D17, D25, D26 — see steps below.

4. **Run `bootstrap_production.py` (CRITICAL — not in captain-update.sh):**
   ```bash
   docker compose exec -T -e PYTHONPATH=/app \
     -e BOOTSTRAP_ACCOUNT_ID=<your_account_id> \
     -e BOOTSTRAP_USER_ID=primary_user \
     -e BOOTSTRAP_STARTING_CAPITAL=<your_capital> \
     captain-offline python /captain/scripts/bootstrap_production.py
   ```
   **Covers:** D00 locked_strategy overlay (TP/SL multiples, feature_threshold), D02 AIM meta-weights, D16 capital silo, D25 circuit breaker cold-start, D00 captain_status → ACTIVE.
   
   **Without this:** D02 is empty (AIM scoring breaks), D16 is empty (position sizing breaks), D25 is empty (circuit breaker breaks), D00 lacks full strategy JSON (Online B4/B6 signal generation may fail).

5. **Run `seed_system_params.py` (not in captain-update.sh):**
   ```bash
   docker compose exec -T -e PYTHONPATH=/app captain-offline \
     python /captain/scripts/seed_system_params.py
   ```
   **Covers:** D17 system parameters (36 rows — quality thresholds, risk limits, AIM config, execution mode). Required by Online and Offline blocks that read D17.

6. **Verify D08 TSM auto-link (requires TopstepX credentials):**
   
   The captain-command container auto-links TSM at startup via `_link_tsm_to_account()` in `captain-command/captain_command/main.py` (lines 73-133). This requires:
   - TopstepX API credentials in `.env` (TOPSTEP_USERNAME, TOPSTEP_API_KEY, TOPSTEP_ACCOUNT_NAME)
   - TSM config files in `config/tsm/`
   - The container must authenticate successfully against TopstepX API
   
   **Verify:**
   ```sql
   SELECT account_id, name, starting_balance, current_balance FROM p3_d08_tsm_state;
   ```
   If empty and TopstepX auth fails, run `scripts/fix_bootstrap_data.py` manually (it has a D08 seed function with hardcoded defaults).

7. **Restore live delta (if backup exists):**
   ```bash
   docker compose exec -T -e PYTHONPATH=/app captain-offline \
     python /captain/scripts/restore_live_delta.py \
     --backup-dir /path/to/captain-backups/live-tables-YYYYMMDD-HHMMSS
   ```
   Restores D30/D29/D33/spread_history rows **beyond the committed seed frontier** from the pre-wipe backup. File: `scripts/restore_live_delta.py`. The script computes per-asset seed frontiers from the committed CSVs and only inserts rows with dates strictly after that frontier.

### C.2 RECOMMENDED (optional but valuable)

8. **Update VIX/VXV data:**
   ```bash
   python scripts/update_vix_daily.py
   ```
   Appends recent VIX/VXV closes to `data/vix/vix_daily_close.csv` and `vxv_daily_close.csv` from Yahoo Finance. Not a QuestDB table — read as CSV by `shared/vix_provider.py`.

9. **Backfill D29 `or_range_first_m_min` (requires TopstepX API):**
   ```bash
   docker compose exec -T -e PYTHONPATH=/app captain-command \
     python /captain/scripts/bootstrap_opening_volumes.py
   ```
   Fetches last 35 days of 1-minute bars from TopstepX for all 10 assets and computes OR range. The CSV seed leaves `or_range_first_m_min = NULL`; this script fills it. File: `scripts/bootstrap_opening_volumes.py`, uses `shared/topstep_client.get_topstep_client()`.

10. **Accept that AIM model_object training is lost:**
    
    D01 `model_object` is NULL after re-seed. AIM models must re-train through live observation (Offline `b1_aim_lifecycle.py`). The system operates in cold-start / BOOTSTRAPPED status until enough sessions accumulate. No manual intervention possible — this is by design.

11. **Accept that D03 trade history is lost unless backed up:**
    
    `p3_d03_trade_outcome_log` is **never re-seeded** by any script. If the pre-wipe backup included D03 via `backup_live_tables.py`, you can manually restore it, but `restore_live_delta.py` does not handle D03 — it only handles D29/D30/D33/spread_history. Custom SQL import would be needed.

---

## Section D — Open Questions

These items cannot be definitively resolved from code inspection alone.

| # | Question | What to Inspect |
|---|----------|----------------|
| 1 | **Exact max dates in committed seed CSVs.** The audit found ES OHLCV through ~2026-03-30, IV/RV through 2026-03-27, skew through 2026-03-31, OR volume through ~2026-03-30. Other assets may differ. | Run: `tail -3 data/seed/aim_data/ohlcv_{ASSET}.csv` for each of the 10 assets. Also `tail -3 data/seed/or_volume_data/{ASSET}_or_volume.csv`. |
| 2 | **D31/D32 only cover ES.** The IV/RV and skew seed scripts hardcode `asset_id='ES'` and read only `es_iv_rv.csv` / `es_skew.csv`. Other assets have zero historical IV/RV/skew after wipe. | Verify: `ls data/seed/aim_data/*iv*.csv data/seed/aim_data/*skew*.csv`. If only `es_*` files exist, AIM features 4 (IV) and 6 (skew) for non-ES assets start from scratch at runtime. |
| 3 | **Does `captain-update.sh` integrity check still pass without `bootstrap_production.py`?** The check requires D02 ≥ 50 and D16 ≥ 1. After `seed_all_assets.py` alone, D02 has 0 rows and D16 has 0 rows → integrity check FAILS, script prints scary error, but containers keep running. | Verify by reading the inline integrity check at `captain-update.sh` lines 166-195. Confirmed: it checks D02 ≥ 50 and D16 ≥ 1 — both will fail without `bootstrap_production.py`. |
| 4 | **Are `config/tsm/` files committed?** D08 auto-link depends on TSM JSON config files existing. If these are gitignored, a fresh clone won't have them. | Run: `ls config/tsm/` and check `.gitignore` for `config/tsm/`. |
| 5 | **Redis state after wipe.** QuestDB wipe does not affect Redis. The Redis AOF (`redis/`) persists parity counters (`captain:parity_counter`), recent quotes cache, and pub/sub state. If Redis is also wiped, parity counters reset to 0 (affects multi-instance determinism). | Check: `docker compose exec redis redis-cli KEYS '*'` |
| 6 | **D26 HMM cold-start.** No seed script populates `p3_d26_hmm_opportunity_state`. After wipe, HMM is in cold-start (`cold_start=true` flag). Online PG-23/PG-25B reads this and falls back to uniform opportunity weights. Verify HMM training kicks in automatically via Offline PG-01C. | Check: `SELECT * FROM p3_d26_hmm_opportunity_state;` after a few sessions. |
| 7 | **D03 restorability.** `backup_live_tables.py` exports D03, but `restore_live_delta.py` only handles D29/D30/D33/spread. A custom restore script for D03 would need to be written, or manual `INSERT` from the backup CSV. | If D03 trade history matters, write a restore function or use QuestDB's CSV import: `COPY p3_d03_trade_outcome_log FROM '/path/to/backup.csv'`. |

---

## Appendix: Script → Table Matrix

| Script      | D00 | D01 | D02 | D04 | D05 | D08 | D12 | D16 | D17 | D25 | D29 | D30 | D31 | D32 | D33 |
|--------------------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| `seed_all_assets.py` | W | W | | W | W | | W | | | | | | | | |
| `bootstrap_production.py` | W | | W | | | | | W | | W | | | | | |
| `seed_system_params.py` | | | | | | | | | W | | | | | | |
| `seed_ohlcv_from_qc.py` | | | | | | | | | | | | W | | | |
| `seed_iv_rv_from_extract.py` | | | | | | | | | | | | | W | | |
| `seed_skew_from_extract.py` | | | | | | | | | | | | | | W | |
| `seed_or_volumes_from_qc.py` | | | | | | | | | | | W | | | | |
| `seed_opening_vol_from_qc.py` | | | | | | | | | | | | | | | W |
| `captain-command/main.py` (runtime) | | | | | | W | | | | | | | | | |
| `restore_live_delta.py` (manual) | | | | | | | | | | | W | W | | | W |
| `bootstrap_opening_volumes.py` (manual, API) | | | | | | | | | | | W | | | | |

**Legend:** W = writes to this table. Empty = no effect.

### Invocation Chain Summary

```
captain-setup.sh (fresh install)
├── init_questdb.py           ← schema only (38 tables + 42 migrations)
├── bootstrap_production.py   ← D00 overlay, D02, D16, D25
├── seed_all_assets.py        ← D00, D01, D04, D05, D12
├── seed_iv_rv_from_extract.py    ← D31
├── seed_skew_from_extract.py     ← D32
├── seed_ohlcv_from_qc.py        ← D30
├── seed_or_volumes_from_qc.py   ← D29
└── seed_opening_vol_from_qc.py  ← D33

captain-update.sh (subsequent updates / post-wipe recovery)
├── init_questdb.py           ← schema only
├── seed_all_assets.py        ← D00, D01, D04, D05, D12
├── seed_iv_rv_from_extract.py    ← D31
├── seed_skew_from_extract.py     ← D32
├── seed_ohlcv_from_qc.py        ← D30
├── seed_or_volumes_from_qc.py   ← D29
├── seed_opening_vol_from_qc.py  ← D33
└── [MISSING] bootstrap_production.py  ← D02, D16, D25 NOT POPULATED
    [MISSING] seed_system_params.py    ← D17 NOT POPULATED

init_all.py (standalone, not called by either shell script)
├── init_questdb.py (inline)
├── init_sqlite.py
├── seed_system_params.py     ← D17
└── seed_test_asset.py        ← D00 (test ES), D15, D16 (test silo)
```
