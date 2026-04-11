# Gap Analysis Orchestrator — Captain System vs Obsidian Spec

**Audit Date:** 2026-04-11
**Auditor:** Claude (automated, Nomaan-directed)
**Source of Truth:** Obsidian vault at `~/obsidian-spec/` (symlink to `/mnt/c/Users/nomaa/Documents/Quant_Project/`)
**Scope:** All P3 programs (Offline, Online, Command) + shared modules + GUI integration points
**Constraint:** Read-only audit — no source code modifications

---

## Session Plan

| Session | Title | Scope | Status |
|---------|-------|-------|--------|
| 1 | Index & Scaffold | Directory structure, git history, mem-search context, file index | COMPLETE |
| 2 | Spec Extraction | Obsidian vault tag search, wikilink traversal, spec-to-code mapping | COMPLETE |
| 3 | P3-Offline Audit | All 17 offline blocks vs spec (AIM lifecycle, decay, Kelly, diagnostic) | PENDING |
| 4 | P3-Online Audit | All 14 online blocks vs spec (data ingestion, regime, AIM, signal output) | PENDING |
| 5 | P3-Command Audit | All 12 command blocks vs spec (routing, GUI, API, reconciliation) | PENDING |
| 6 | Cross-Verification & Verdict | Regression check, unaudited file scan, final rollup, READY/NOT READY | PENDING |

---

## Session 1 — Index & Scaffold

**Completed:** 2026-04-11 03:33 GMT+1
**Objective:** Build the file index, capture prior audit context, create scaffold

### 1.1 Prior Audit Context (from mem-search)

A comprehensive 100-gap audit was completed on 2026-04-09 across 12 implementation sessions:

| Metric | Value |
|--------|-------|
| Total gaps identified | 100 |
| Fully resolved | 62 |
| Partially resolved | 4 (G-030, G-031, G-038, G-039) |
| Deferred LOW | 33 |
| Deferred HIGH | 1 (G-025 pseudotrader) |
| CRITICAL gaps resolved | 7/7 |
| HIGH gaps resolved | 21/22 |

**Key decisions from April 9 audit:**
- DEC-01: JWT HS256 for API auth
- DEC-02: Removed git-pull endpoint (RCE fix)
- DEC-03: 7-layer circuit breaker
- DEC-04: Defer pseudotrader refactor until post-live
- DEC-05: hmmlearn for AIM-16
- DEC-06: AIM-16 dispatch pattern
- DEC-07: ZN/ZB session mapping
- DEC-08: Disable AIM-07
- DEC-09: Session controller extraction
- DEC-10: Compliance gate block

**Post-audit changes invalidating baseline:**
- 26 commits since April 9 audit completion
- 12-batch UX audit overhaul (batches 0-11) covering entire GUI
- 60 files changed on `ux-audit-overhaul` branch: +4036 / -943 lines
- 28 files currently uncommitted: +953 / -349 lines
- Existing `master_gap_analysis.md` (661 lines) and `spec_reference.md` (4102 lines) are stale baselines

**Why a fresh audit is needed:** The April 9 audit predates the UX overhaul and additional backend changes. Code has diverged significantly — the previous gap analysis cannot be trusted as current state.

### 1.2 Git History — April 9-10 Reconciliation Commits

#### Session 05 (6321342) — Timezone & Session Infrastructure
```
captain-command/Dockerfile                          +16/-1
captain-command/captain_command/api.py              +262 (major rework)
captain-command/captain_command/blocks/b6_reports.py +4/-4
captain-command/captain_command/blocks/b7_notifications.py +7/-7
captain-command/requirements.txt                    +1
captain-gui/Dockerfile                              +5/-5
captain-offline/Dockerfile                          +6
captain-offline/captain_offline/blocks/b2_level_escalation.py +5/-5
captain-offline/captain_offline/blocks/b4_injection.py +3/-3
captain-offline/captain_offline/blocks/b5_sensitivity.py +3/-3
captain-offline/captain_offline/blocks/b7_tsm_simulation.py +3/-3
captain-offline/captain_offline/blocks/b9_diagnostic.py +23/-23
captain-offline/captain_offline/blocks/orchestrator.py +3/-3
captain-online/Dockerfile                           +6
captain-online/captain_online/blocks/b1_data_ingestion.py +6/-6
captain-online/captain_online/blocks/b1_features.py +48/-48
docker-compose.yml                                  -2
shared/constants.py                                 +6
```

#### Session 06 (072fa82) — Online Reliability
```
captain-online/captain_online/blocks/b1_data_ingestion.py +50/-50
captain-online/captain_online/blocks/b7_position_monitor.py +159/-159
captain-online/captain_online/blocks/b7_shadow_monitor.py +32/-32
captain-online/captain_online/blocks/orchestrator.py +4
shared/topstep_client.py                            +44/-44
```

#### Session 07 (bda610f) — AIM Implementation
```
captain-offline/captain_offline/blocks/b5_sensitivity.py +2/-2
captain-online/captain_online/blocks/b1_features.py +60/-60
shared/aim_compute.py                               +4/-4
shared/aim_feature_loader.py                        +88/-88
```

#### Session 08 (3c2d2f7) — Offline Pipeline Alignment
```
captain-offline/captain_offline/blocks/b1_aim16_hmm.py +210 (major reduction)
captain-offline/captain_offline/blocks/b8_kelly_update.py +16
captain-offline/captain_offline/blocks/b9_diagnostic.py +6
captain-offline/captain_offline/blocks/bootstrap.py +4/-4
captain-online/captain_online/blocks/b3_aim_aggregation.py -27 (removed)
captain-online/captain_online/blocks/orchestrator.py +2/-2
```

#### Session 09 (8e91f65) — Command Pipeline + QuestDB
```
captain-command/captain_command/blocks/b11_replay_runner.py +18/-18
captain-command/captain_command/blocks/b7_notifications.py +16
captain-command/captain_command/blocks/b8_reconciliation.py +91/-91
captain-command/captain_command/blocks/b9_incident_response.py +3/-3
captain-command/captain_command/blocks/telegram_bot.py +3/-3
scripts/seed_system_params.py                       +1
```

#### Session 10 (60df394) — Concurrency + CB + Feedback
```
captain-command/captain_command/api.py              +58/-58
captain-command/captain_command/blocks/b2_gui_data_server.py +47/-47
captain-online/captain_online/blocks/b4_kelly_sizing.py +18/-18
captain-online/captain_online/blocks/b5_trade_selection.py +13/-13
captain-online/captain_online/blocks/b5c_circuit_breaker.py +7/-7
captain-online/captain_online/blocks/b6_signal_output.py +12/-12
shared/aim_compute.py                               +3/-3
shared/aim_feature_loader.py                        +16
shared/statistics.py                                +20/-20
```

#### Session 12 (0b5db6e) — Session Controller, OR Tracker, Compliance Gate
```
captain-command/captain_command/blocks/b12_compliance_gate.py +103 (NEW)
captain-command/captain_command/blocks/b2_gui_data_server.py +12/-12
captain-command/captain_command/blocks/b3_api_adapter.py +43/-43
captain-online/captain_online/blocks/b8_or_tracker.py (renamed from or_tracker.py)
captain-online/captain_online/blocks/b9_session_controller.py +150 (NEW)
captain-online/captain_online/blocks/orchestrator.py +23/-23
captain-online/captain_online/main.py               +2/-2
```

#### Final Validation v1.0 (d6c96b0)
```
captain-command/captain_command/blocks/b2_gui_data_server.py +8/-8
captain-command/captain_command/blocks/b7_notifications.py +8/-8
captain-command/captain_command/main.py              +8/-8
captain-gui/src/App.jsx                             +48/-48
captain-gui/src/api/client.js                       +15/-15
captain-gui/src/auth/AuthContext.jsx                +62 (NEW)
captain-gui/src/components/signals/SignalCards.jsx   +22/-22
captain-gui/src/index.jsx                           +5/-5
captain-gui/src/pages/* (multiple)
captain-gui/src/stores/dashboardStore.js            +11
captain-gui/src/ws/useWebSocket.js                  +12/-12
captain-offline/captain_offline/blocks/* (8 files)
captain-online/captain_online/blocks/* (8 files)
docker-compose.yml                                  +3
nginx/nginx-local.conf                              +10
shared/contract_resolver.py                         +2/-2
shared/questdb_client.py                            +2/-2
shared/replay_engine.py                             +8/-8
```

#### UX Audit Batches 0-11 (14398c7..20469c8)
```
Batch 0 — Foundation: shared components (CollapsiblePanel, DataTable, StatusBadge, StatusDot), global.css
Batch 1 — App Shell: App.jsx, TopBar.jsx, AuthContext.jsx, api/client.js
Batch 2 — Market + Chart: ChartPanel.jsx, MarketTicker.jsx (deleted CandlestickChart, ChartOverlayToggles, TimeframeSelector)
Batch 3 — Risk + Trade: RiskPanel.jsx, TradeLog.jsx
Batch 4 — Position + AIM: AimRegistryPanel.jsx, ActivePosition.jsx
Batch 5 — Modal + Syslog: AimDetailModal.jsx, SystemLog.jsx
Batch 6 — Signals + Dashboard: SignalCards.jsx, SignalExecutionBar.jsx, DashboardPage.jsx
Batch 7 — Replay Controls: PlaybackControls.jsx, ReplayConfigPanel.jsx
Batch 8 — Replay Panels: AssetCard.jsx, BatchPnlReport.jsx, BlockDetail.jsx, PipelineStepper.jsx, ReplaySummary.jsx
Batch 9 — Pages A: WhatIfComparison.jsx, HistoryPage.jsx, LoginPage.jsx, ModelsPage.jsx, ReplayPage.jsx
Batch 10 — Pages B: ConfigPage.jsx, ProcessesPage.jsx, ReportsPage.jsx, SettingsPage.jsx, SystemOverviewPage.jsx
Batch 11 — Cleanup: TradingViewWidget.jsx, dashboardStore.js, useWebSocket.js
```

### 1.3 Current Codebase File Index

#### P3-Offline — Captain Offline (17 blocks + orchestrator)

| File | Block | Area |
|------|-------|------|
| `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py` | B1 | AIM lifecycle management |
| `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` | B1 | AIM-16 HMM (Hidden Markov Model) |
| `captain-offline/captain_offline/blocks/b1_dma_update.py` | B1 | DMA (Decayed Moving Average) meta-weight update |
| `captain-offline/captain_offline/blocks/b1_drift_detection.py` | B1 | Regime drift detection |
| `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py` | B1 | HDWM diversity scoring |
| `captain-offline/captain_offline/blocks/b2_bocpd.py` | B2 | BOCPD changepoint detection |
| `captain-offline/captain_offline/blocks/b2_cusum.py` | B2 | CUSUM changepoint detection |
| `captain-offline/captain_offline/blocks/b2_level_escalation.py` | B2 | Decay level escalation |
| `captain-offline/captain_offline/blocks/b3_pseudotrader.py` | B3 | Pseudotrader simulation |
| `captain-offline/captain_offline/blocks/b4_injection.py` | B4 | Parameter injection |
| `captain-offline/captain_offline/blocks/b5_sensitivity.py` | B5 | Sensitivity analysis |
| `captain-offline/captain_offline/blocks/b6_auto_expansion.py` | B6 | Auto-expansion logic |
| `captain-offline/captain_offline/blocks/b7_tsm_simulation.py` | B7 | TSM (Trade State Machine) simulation |
| `captain-offline/captain_offline/blocks/b8_cb_params.py` | B8 | Circuit breaker parameter update |
| `captain-offline/captain_offline/blocks/b8_kelly_update.py` | B8 | Kelly criterion update |
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | B9 | Diagnostic reporting |
| `captain-offline/captain_offline/blocks/bootstrap.py` | — | Bootstrap/initialization |
| `captain-offline/captain_offline/blocks/orchestrator.py` | — | Block orchestration |
| `captain-offline/captain_offline/blocks/version_snapshot.py` | — | Version snapshot |
| `captain-offline/captain_offline/main.py` | — | Process entry point |

#### P3-Online — Captain Online (14 blocks + orchestrator)

| File | Block | Area |
|------|-------|------|
| `captain-online/captain_online/blocks/b1_data_ingestion.py` | B1 | Market data ingestion |
| `captain-online/captain_online/blocks/b1_features.py` | B1 | Feature computation |
| `captain-online/captain_online/blocks/b2_regime_probability.py` | B2 | Regime probability estimation |
| `captain-online/captain_online/blocks/b4_kelly_sizing.py` | B4 | Kelly position sizing |
| `captain-online/captain_online/blocks/b5_trade_selection.py` | B5 | Trade selection logic |
| `captain-online/captain_online/blocks/b5b_quality_gate.py` | B5b | Quality gate filter |
| `captain-online/captain_online/blocks/b5c_circuit_breaker.py` | B5c | Circuit breaker check |
| `captain-online/captain_online/blocks/b6_signal_output.py` | B6 | Signal output to Redis |
| `captain-online/captain_online/blocks/b7_position_monitor.py` | B7 | Active position monitoring |
| `captain-online/captain_online/blocks/b7_shadow_monitor.py` | B7 | Shadow (theoretical) monitoring |
| `captain-online/captain_online/blocks/b8_concentration_monitor.py` | B8 | Concentration risk monitor |
| `captain-online/captain_online/blocks/b8_or_tracker.py` | B8 | Opening Range tracker |
| `captain-online/captain_online/blocks/b9_capacity_evaluation.py` | B9 | Capacity evaluation |
| `captain-online/captain_online/blocks/b9_session_controller.py` | B9 | Session lifecycle controller |
| `captain-online/captain_online/blocks/orchestrator.py` | — | Block orchestration |
| `captain-online/captain_online/main.py` | — | Process entry point |

#### P3-Command — Captain Command (12 blocks + orchestrator)

| File | Block | Area |
|------|-------|------|
| `captain-command/captain_command/blocks/b1_core_routing.py` | B1 | Signal routing + parity filter |
| `captain-command/captain_command/blocks/b2_gui_data_server.py` | B2 | WebSocket GUI data server |
| `captain-command/captain_command/blocks/b3_api_adapter.py` | B3 | API adapter layer |
| `captain-command/captain_command/blocks/b4_tsm_manager.py` | B4 | Trade State Machine manager |
| `captain-command/captain_command/blocks/b5_injection_flow.py` | B5 | Injection flow handler |
| `captain-command/captain_command/blocks/b6_reports.py` | B6 | Report generation |
| `captain-command/captain_command/blocks/b7_notifications.py` | B7 | Telegram + notification dispatch |
| `captain-command/captain_command/blocks/b8_reconciliation.py` | B8 | Position/trade reconciliation |
| `captain-command/captain_command/blocks/b9_incident_response.py` | B9 | Incident response automation |
| `captain-command/captain_command/blocks/b10_data_validation.py` | B10 | Data validation checks |
| `captain-command/captain_command/blocks/b11_replay_runner.py` | B11 | Replay execution |
| `captain-command/captain_command/blocks/b12_compliance_gate.py` | B12 | Compliance gate enforcement |
| `captain-command/captain_command/blocks/orchestrator.py` | — | Block orchestration |
| `captain-command/captain_command/blocks/telegram_bot.py` | — | Telegram bot handler |
| `captain-command/captain_command/api.py` | — | FastAPI application |
| `captain-command/captain_command/main.py` | — | Process entry point |

#### Shared Modules

| File | Purpose |
|------|---------|
| `shared/topstep_client.py` | REST client (18 endpoints) |
| `shared/topstep_stream.py` | WebSocket streaming (pysignalr) |
| `shared/contract_resolver.py` | Futures contract ID resolution |
| `shared/account_lifecycle.py` | Account progression logic |
| `shared/questdb_client.py` | QuestDB connection helper |
| `shared/redis_client.py` | Redis connection + pub/sub |
| `shared/vault.py` | AES-256-GCM key vault |
| `shared/journal.py` | SQLite WAL crash recovery |
| `shared/constants.py` | Shared constants |
| `shared/statistics.py` | Statistical utilities |
| `shared/signal_replay.py` | Signal replay for debugging |
| `shared/trade_source.py` | Trade data source abstraction |
| `shared/vix_provider.py` | VIX/VXV data provider |
| `shared/aim_compute.py` | AIM aggregation logic |
| `shared/aim_feature_loader.py` | AIM feature loading |
| `shared/bar_cache.py` | Bar data caching |
| `shared/json_helpers.py` | JSON serialization |
| `shared/process_logger.py` | Centralized log forwarder |
| `shared/replay_engine.py` | Session replay engine |

#### Uncommitted Changes (28 files, +953/-349)

**Backend (6 files):**
- `captain-command/captain_command/api.py` — API route changes
- `captain-command/captain_command/blocks/b1_core_routing.py` — Routing logic
- `captain-command/captain_command/blocks/b2_gui_data_server.py` — GUI data server
- `captain-command/captain_command/blocks/orchestrator.py` — Command orchestrator
- `captain-command/captain_command/main.py` — Command entry point
- `captain-offline/captain_offline/blocks/orchestrator.py` — Offline orchestrator
- `captain-offline/captain_offline/main.py` — Offline entry point
- `captain-online/captain_online/blocks/b6_signal_output.py` — Signal output
- `captain-online/captain_online/blocks/orchestrator.py` — Online orchestrator
- `captain-online/captain_online/main.py` — Online entry point
- `shared/contract_resolver.py` — Contract resolution
- `shared/redis_client.py` — Redis client

**GUI (12 files):**
- `captain-gui/src/api/client.js` — API client
- `captain-gui/src/components/aim/AimDetailModal.jsx`
- `captain-gui/src/components/aim/AimRegistryPanel.jsx`
- `captain-gui/src/components/chart/ChartPanel.jsx`
- `captain-gui/src/components/layout/MarketTicker.jsx`
- `captain-gui/src/components/layout/TopBar.jsx`
- `captain-gui/src/components/risk/RiskPanel.jsx`
- `captain-gui/src/components/signals/SignalCards.jsx`
- `captain-gui/src/components/signals/SignalExecutionBar.jsx`
- `captain-gui/src/components/trading/ActivePosition.jsx`
- `captain-gui/src/pages/DashboardPage.jsx`
- `captain-gui/src/stores/dashboardStore.js`
- `captain-gui/src/ws/useWebSocket.js`
- `captain-gui/vite.config.mjs`

**New untracked files:**
- `.mcp.json` — MCP server configuration
- `captain-gui/src/components/terminal/` — LiveTerminal component
- `captain-gui/src/stores/terminalStore.js` — Terminal state store
- `shared/process_logger.py` — Process log forwarder
- `logs/vix_update.log` — VIX update log

### 1.4 Existing Audit Artifacts

| File | Lines | Date | Status |
|------|-------|------|--------|
| `docs/audit/FINAL_VALIDATION_REPORT.md` | 576 | 2026-04-09 | Stale — predates UX overhaul |
| `docs/audit/master_gap_analysis.md` | 661 | 2026-04-09 | Stale — 100 gaps, many now resolved |
| `docs/audit/spec_reference.md` | 4102 | 2026-04-09 | Stale — consolidated spec from vault |
| `docs/audit/VALIDATION_ROADMAP.md` | 820 | 2026-04-09 | Stale — original roadmap |
| `docs/audit/ln-621--global.md` | — | 2026-04-09 | Security audit findings |
| `docs/audit/ln-628--global.md` | — | 2026-04-09 | Concurrency audit findings |
| `docs/audit/ln-629--global.md` | — | 2026-04-09 | Lifecycle audit findings |
| `plans/CAPTAIN_RECONCILIATION_MATRIX.md` | — | 2026-04-09 | Reconciliation tracking (81 items) |

### 1.5 Scope for This Audit

This audit will compare **current code state** (HEAD of `ux-audit-overhaul` + uncommitted changes) against **current Obsidian vault specs** (the single source of truth). Prior audit artifacts are reference only — every finding must be re-verified against current code.

**Total files to audit:**
- P3-Offline: 20 files (17 blocks + orchestrator + bootstrap + version_snapshot + main)
- P3-Online: 16 files (14 blocks + orchestrator + main)
- P3-Command: 16 files (12 blocks + orchestrator + telegram_bot + api.py + main)
- Shared: 19 files
- GUI integration points: WebSocket, API client, stores (spec compliance only)

**Total: 71 source files**

---

## Session 2 — Spec Map

**Status:** COMPLETE
**Completed:** 2026-04-11 03:50 GMT+1
**Objective:** Extract all spec requirements from Obsidian vault and map to code files

### 2.1 Spec Documents Read

| Doc # | Title | Spec ID | Relevance | Key Content |
|-------|-------|---------|-----------|-------------|
| 18 | GUI Dashboard | Transfer-P2-18 | P3-Command | 2 layers, 3 autonomy tiers, 9 panels, AIM sub-panel, 6-field outbound limit |
| 19 | User Management | Transfer-P2-19 | P3-Online/Command | User entity, 5 account classes, 6 RBAC roles, JWT, P3-D16 silos, V1/V2 split |
| 20 | Signal Distribution | Transfer-P2-20 | P3-Online/Command | Anti-copy PG-30, priority rotation, EV-balancing, P3-D27 |
| 21 | Implementation Guides | Transfer-P2-21 | P3-Offline/Online | DMA/MoE meta-learning, BOCPD/CUSUM, Kelly 7-layer, 16-AIM register |
| 22 | HMM Opportunity Regime | Transfer-P2-22 | P3-Offline/Online | AIM-16: K=3 Gaussian HMM, TVTP, 7-element obs vector, 60-day Baum-Welch |
| 23 | XGBoost Classifier | Transfer-P2-23 | P3-Online | P2 Block 3b training, Online B2 inference, 4 complexity tiers (C1-C4) |
| 24 | P3 Dataset Schemas | Transfer-P2-24 | All P3 | QuestDB field-level schemas for D00-D27, 9-source data registry |
| 25 | Fee & Payout System | Transfer-P2-25 | P3-Command | TSM fees, commission resolution, XFA scaling tiers, payout rules |
| 26 | Notification System | Transfer-P2-26 | P3-Command | Telegram bot, 4 priority levels, quiet hours, P3-D10 delivery log |
| 27 | Contract Rollover | Transfer-P2-27 | P3-Online | Roll timing, QuantConnect BackwardsRatio, pseudotrader alignment |
| 28 | Pseudotrader System | Transfer-P2-28 | P3-Offline | Account-aware replay (PG-09/09B/09C), LEGACY vs IDEAL modes, SHA256 tick stream |
| 29 | Operational Policies | Transfer-P2-29 | All P3 | Change management, governance, 12 reports (RPT-01 to RPT-12), 3-level validation |
| 31 | AIM Individual Specs | Transfer-P2-31 | P3-Offline/Online | Per-AIM pseudocode (AIM-01 to AIM-15), output interface, lifecycle, z-score modifiers |
| 32 | P3 Offline Pseudocode | Transfer-P2-32 | P3-Offline | Full pseudocode: 9 blocks, 17 PG programs (PG-01 to PG-17) |
| 33 | P3 Online Pseudocode | Transfer-P2-33 | P3-Online | Full pseudocode: B1-B9 + B5B + 5-layer CB |
| 34 | P3 Command Pseudocode | Transfer-P2-34 | P3-Command | Full pseudocode: 10 blocks (PG-30 to PG-41) |

**Total: 16 spec documents read from Obsidian vault.**

---

### 2.2 Captain Offline — Block-to-Spec-to-Code Map

#### Block 1 — AIM Model Training and Management

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-01 | `aim_lifecycle_manager_A` | 31, 32 | `captain-offline/.../b1_aim_lifecycle.py` | 7-state lifecycle (INSTALLED→COLLECTING→WARM_UP→ELIGIBLE→ACTIVE→SUPPRESSED→BOOTSTRAPPED), 50-trade min eval |
| PG-01C | `aim16_hmm_train_A` | 22, 32 | `captain-offline/.../b1_aim16_hmm.py` | K=3 Gaussian HMM, TVTP, Baum-Welch on 60-day rolling window, 240 obs, α=0.3 smoothing |
| PG-02 | `aim_dma_update_A` | 21, 32 | `captain-offline/.../b1_dma_update.py` | DMA forgetting λ=0.99, magnitude-weighted likelihood (SPEC-A9), z-score normalised, shared intelligence |
| PG-03 | `aim_diversity_check_A` | 21, 32 | `captain-offline/.../b1_hdwm_diversity.py` | HDWM weekly check, 6 seed types, force-reactivate if all AIMs of a type suppressed |
| PG-04 | `aim_drift_detector_A` | 32 | `captain-offline/.../b1_drift_detection.py` | Daily, autoencoder + ADWIN per AIM, on drift: weight *= 0.5, flag retrain |

**Data stores R/W:** Reads P3-D02, P3-D03, P3-D05. Writes P3-D01, P3-D02, P3-D04, P3-D26.

#### Block 2 — Strategy Decay Detection

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-05 | `bocpd_decay_monitor_A` | 21, 32 | `captain-offline/.../b2_bocpd.py` | Adams & MacKay 2007, NIG→Student-t, hazard=1/200, cp>0.8→L2, cp>0.9 sustained 5d→L3 |
| PG-06 | `cusum_decay_monitor_A` | 21, 32 | `captain-offline/.../b2_cusum.py` | Two-sided CUSUM, sequential control limits, sprint length tracking |
| PG-07 | `cusum_bootstrap_calibrate_A` | 21, 32 | `captain-offline/.../b2_cusum.py` | B=2000 bootstrap, ARL₀=200, run at init + quarterly |
| PG-08 | `decay_response_handler_A` | 32 | `captain-offline/.../b2_level_escalation.py` | L2: sizing reduction (50%-100%), L3: DECAYED status, schedule P1/P2 rerun |

**Data stores R/W:** Reads P3-D03. Writes P3-D04, P3-D12 (sizing_override), P3-D00 (captain_status).

#### Block 3 — Post-Update Retest (Pseudotrader)

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-09 | `pseudotrader_retest_A` | 28, 32 | `captain-offline/.../b3_pseudotrader.py` | 5-phase replay (baseline, updated, compare, validate PBO/DSR, store), CSCV S=16 |
| PG-09B | CB replay | 28, 32 | `captain-offline/.../b3_pseudotrader.py` | Account-aware replay with per-account constraints (XFA/Eval/Live) |
| PG-09C | CB grid | 28, 32 | `captain-offline/.../b3_pseudotrader.py` | LEGACY vs IDEAL modes, SHA256 deterministic tick stream |

**Data stores R/W:** Reads P3-D03, P3-D08. Writes P3-D11, P3-D27.

#### Block 4 — Strategy Injection Comparison

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-10 | `injection_comparison_A` | 32 | `captain-offline/.../b4_injection.py` | Retroactive AIM analysis, E_new > 1.2×E_current→ADOPT (10d transition), 0.9-1.2→PARALLEL (20d), <0.9→REJECT |
| PG-11 | `strategy_transition_A` | 32 | `captain-offline/.../b4_injection.py` | Linear blending over transition_days, parallel tracking with dual logging |

**Data stores R/W:** Reads P3-D00, P3-D02, P3-D03, P2-D06. Writes P3-D00, P3-D06.

#### Block 5 — AIM-13 Sensitivity Scanner

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-12 | `sensitivity_scanner_A` | 31, 32 | `captain-offline/.../b5_sensitivity.py` | Monthly, ±5/10/20% perturbation grid, PBO CSCV S=8, DSR, ROBUST/FRAGILE classification |

**Data stores R/W:** Reads P3-D00 (locked strategy). Writes P3-D13.

#### Block 6 — AIM-14 Auto-Expansion

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-13 | `auto_expansion_search_A` | 31, 32 | `captain-offline/.../b6_auto_expansion.py` | L3 trigger only, GA search (pop=100, gen=50), top 5 candidates, OOS test, PBO<0.5 AND DSR>0.5 |

**Data stores R/W:** Reads P3-D00 (decayed asset), P1 feature library. Writes candidates to injection flow.

#### Block 7 — TSM Simulation

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-14 | `tsm_simulation_A` | 32 | `captain-offline/.../b7_tsm_simulation.py` | Monte Carlo 10k paths, block bootstrap (size 3/5/7), pass_probability, PASS_EVAL vs GROW_CAPITAL |

**Data stores R/W:** Reads P3-D03, P3-D08, P3-D12. Writes P3-D08 (pass_probability).

#### Block 8 — Kelly Parameter Updates + beta_b

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-15 | `kelly_parameter_update_A` | 21, 32 | `captain-offline/.../b8_kelly_update.py` | Adaptive EWMA α from BOCPD cp, per [asset][regime][session], Kelly f*=p-(1-p)/b, shrinkage max(0.3, 1-est_var) |
| PG-16C | `beta_b_estimator_A` | 32 | `captain-offline/.../b8_cb_params.py` | Per-basket OLS regression, cold_start n<100, L* breakeven computation |

**Data stores R/W:** Reads P3-D03, P3-D04. Writes P3-D05, P3-D12, P3-D25.

#### Block 9 — System Health Diagnostic

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-17 / PG-16B | `system_health_diagnostic_A` | 21, 32 | `captain-offline/.../b9_diagnostic.py` | 8 dimensions (D1-D8), scored ∈[0,1], weekly+monthly, action item queue for ADMIN |

**Data stores R/W:** Reads P3-D00, P3-D01, P3-D02, P3-D03, P3-D04, P3-D13, P2-D06. Writes P3-D22.

#### Offline Support Files

| File | Spec Reference | Purpose |
|------|---------------|---------|
| `bootstrap.py` | Implicit (system init) | Asset/AIM/Kelly data seeding |
| `version_snapshot.py` | Doc 32 (Version Snapshot Policy) | Pre-update snapshots of D01, D02, D05, D12, D17; rollback support |
| `orchestrator.py` | Doc 32 (execution modes) | Scheduled + event-triggered dispatch, parity-aware signal outcome handling |
| `main.py` | — | Process entry point |

---

### 2.3 Captain Online — Block-to-Spec-to-Code Map

#### Block 1 — Pre-Session Data Ingestion

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-21 | `data_ingestion_A` | 33 | `captain-online/.../b1_data_ingestion.py` | Session-match filter, data moderator (price 5% bounds, volume, staleness, TZ), roll calendar check |
| PG-21 | Feature computation | 31, 33 | `captain-online/.../b1_features.py` + `shared/aim_feature_loader.py` | 14+ features per asset: VRP, IVTS, GEX, PCR, COT, correlation, momentum, spread, volume ratio, calendar, VIX |

**Data stores READ:** P3-D00, P3-D01, P3-D02, P3-D05, P3-D08, P3-D12, P2-D06, P2-D07.
**SHARED:** Computed once per session, same result for all users.

#### Block 2 — Regime Probability

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-22 | `regime_probability_A` | 23, 33 | `captain-online/.../b2_regime_probability.py` | P2 classifier (XGBoost/LogReg/Binary per tier C1-C4), P(LOW_VOL), P(HIGH_VOL), regime_uncertain flag at <0.6 |

**Data stores READ:** P2-D07 (trained classifier).
**SHARED:** Computed once per session.

#### Block 3 — AIM Aggregation

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-23 | `aim_aggregation_A` | 21, 22, 31, 33 | `shared/aim_compute.py` + `shared/aim_feature_loader.py` | Per-AIM modifier dispatch (16 AIMs), MoE weighted aggregation via DMA probs, combined_modifier ∈[0.5,1.5], AIM-16 session budget weights |

**Note:** Original `b3_aim_aggregation.py` was removed in Session 08 reconciliation; logic extracted to `shared/aim_compute.py`.
**Data stores READ:** P3-D01, P3-D02, P3-D26 (HMM states).
**SHARED:** Computed once per session.

#### Block 4 — Kelly 7-Layer Sizing

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-24 | `kelly_sizing_A` | 21, 33 | `captain-online/.../b4_kelly_sizing.py` | L2: regime blend, L3: shrinkage, L4: robust fallback (if regime_uncertain), L5: AIM modifier, L6: risk_goal (PASS_EVAL/PRESERVE/GROW), L7: TSM caps + XFA scaling + fee R_eff |

**Data stores READ:** P3-D05, P3-D08, P3-D12, regime_probs, combined_modifier.
**PER-USER:** Runs per active user's accounts.

#### Block 5 — Trade Selection + Block 5B Quality Gate

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-25 | `trade_selection_A` | 33 | `captain-online/.../b5_trade_selection.py` | Daily budget from HMM session weights, rank by edge×contracts, top-down allocation |
| PG-25B | Quality gate | 33 | `captain-online/.../b5b_quality_gate.py` | $/contract floor + ceiling filter |

**PER-USER.**

#### Circuit Breaker (between B5B and B6)

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-27B | `circuit_breaker_screen_A` | 33 | `captain-online/.../b5c_circuit_breaker.py` | 5 layers: L0 scaling cap (XFA), L1 preemptive halt (L_t+ρ_j≥L_halt), L2 budget check, L3 β_b expectancy (μ_b≤0→BLOCK), L4 correlated Sharpe |

**Data stores READ:** P3-D08, P3-D23, P3-D25.
**PER-USER.**

#### Block 6 — Signal Output

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-26 | `signal_output_A` | 33 | `captain-online/.../b6_signal_output.py` | Anti-copy jitter (±30s time, ±1 micro size), Redis pub/sub `signals:{user_id}`, sanitised 6 fields only |

**Data stores WRITE:** Redis channel `captain:signals:{user_id}`.

#### Block 7 — Position Monitoring

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-27 | `position_monitor_A` | 33 | `captain-online/.../b7_position_monitor.py` | on_close→P3-D03 outcome, P3-D23 L_t+pnl, resolve commission, trigger Offline learning loops via Redis |

**Shadow monitor:** `captain-online/.../b7_shadow_monitor.py` — tracks theoretical TP/SL outcomes for multi-instance parity-skipped signals (implementation addition for multi-instance).

**Data stores WRITE:** P3-D03, P3-D23. Redis channel `captain:trade_outcomes`.

#### Block 8 — Net Concentration + OR Tracker

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-28 | `net_concentration_A` | 33 | `captain-online/.../b8_concentration_monitor.py` | If same_dir > 80%: ALERT (advisory only, does NOT block) |
| — | OR tracker | — | `captain-online/.../b8_or_tracker.py` | Opening Range tracking (implementation addition, supports B1 feature computation) |

#### Block 9 — Capacity Evaluation + Session Controller

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-29 | `capacity_eval_A` | 33 | `captain-online/.../b9_capacity_evaluation.py` | Session-end fill quality, slippage_bps, volume participation |
| — | Session controller | — | `captain-online/.../b9_session_controller.py` | Session lifecycle management (implementation addition, DEC-09) |

#### Online Support Files

| File | Spec Reference | Purpose |
|------|---------------|---------|
| `orchestrator.py` | Doc 33 (session-driven) | Session-driven dispatch, shared vs per-user split |
| `main.py` | — | Process entry point |

---

### 2.4 Captain Command — Block-to-Spec-to-Code Map

#### Block 1 — Core Routing

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-30 | `command_router_A` | 34 | `captain-command/.../b1_core_routing.py` | 3 message queues (signal/command/notification), per-user signal delivery, 6-field sanitisation, PROHIBITED_FIELDS enforcement |

**Command types:** TAKEN, SKIPPED, ADOPT_STRATEGY, REJECT_STRATEGY, PARALLEL_TRACK, SELECT_TSM, ACTIVATE_AIM, DEACTIVATE_AIM, CONFIRM_ROLL, UPDATE_ACTION_ITEM, TRIGGER_DIAGNOSTIC, MANUAL_PAUSE, MANUAL_RESUME.

#### Block 2 — GUI Interface

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-31 | `gui_data_server_A` | 18, 34 | `captain-command/.../b2_gui_data_server.py` | `get_dashboard_data(user_id)`: signals, regime, decay_alerts, warmup_gauges, aim_panel, positions, tsm_status, capital, notifications, payout_panel. ADMIN-only System Overview |

**GUI spec requirements (doc 18):**
- 9 dashboard panels (signal, regime, AIM, notification, positions, TSM, capital, decay, warmup)
- AIM sub-panel: status, modifier, confidence, DMA weight, warmup bar, 30-day hit rate, last retrained
- 3 autonomy tiers: FULL_AUTO, SEMI_AUTO (default), MANUAL
- Payout panel: per-account recommended, net after commission, tier impact
- 6-field outbound limit strictly enforced

#### Block 3 — API + Execution

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-32 | `api_plugin_A` | 34 | `captain-command/.../b3_api_adapter.py` + `captain-command/.../api.py` | Broker adapter management, mTLS connect, compliance_gate(signal), auto-reconnect 3 retries |
| PG-34 | Injection flow | 34 | `captain-command/.../b5_injection_flow.py` | GUI workflow for strategy adoption (separate from B3/PG-32) |

#### Block 4 — TSM Management

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-33 | `tsm_manager_A` | 25, 34 | `captain-command/.../b4_tsm_manager.py` | Validate TSM structure, classify account (5 categories), load fee_schedule, provider-agnostic onboarding |

**Fee resolution (doc 25):** `resolve_commission(tsm, asset, contracts)`, `get_expected_fee(tsm, asset)`, fallback if no fee_schedule.

#### Block 5 — Injection Flow

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-34 | Injection flow | 34 | `captain-command/.../b5_injection_flow.py` | Receive RPT-05 from Offline B4, present to ADMIN, capture ADOPT/PARALLEL/REJECT, forward to Offline PG-11 |

#### Block 6 — Reports

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-35 | `report_generator_A` | 29, 34 | `captain-command/.../b6_reports.py` | 12 reports (RPT-01 to RPT-12): daily signal, weekly perf, monthly health, AIM effectiveness, injection comparison, regime transition, TSM compliance, probability accuracy, decision impact, annual review, financial summary, alpha decomposition |

**Data stores WRITE:** P3-D09 (report_archive).

#### Block 7 — Notifications

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-36 | Notification routing | 26, 34 | `captain-command/.../b7_notifications.py` + `captain-command/.../telegram_bot.py` | 4 priority levels, Telegram bot (7 commands + inline buttons), quiet hours 22:00-06:00, per-user preferences, 60msg/hr rate limit |

**Telegram commands (doc 26):** /status, /signals, /positions, /reports, /tsm, /mute, /help.
**Data stores WRITE:** P3-D10 (notification_log).

#### Block 8 — Daily Reconciliation

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-39 | `daily_reconciliation_A` | 25, 34 | `captain-command/.../b8_reconciliation.py` | 19:00 EST SOD boundary, broker balance = source of truth, recalculate mdd_pct=4500/A, R_eff, N, E, L_halt, ZERO P3-D23, XFA scaling tier update, payout recommendation |

**Data stores R/W:** Reads/writes P3-D08, P3-D23. Writes P3-D19.

#### Block 9 — Incident Response

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-40 | `incident_handler_A` | 29, 34 | `captain-command/.../b9_incident_response.py` | create_incident(): 4 severity levels (P1-P4), system state snapshot, routing per severity (P1→ALL channels override quiet hours) |

**Data stores WRITE:** P3-D21 (incident_logs).

#### Block 10 — Data Validation

| PG Ref | Procedure | Spec Doc | Code File | Key Requirements |
|--------|-----------|----------|-----------|------------------|
| PG-41 | `data_validation_A` | 34 | `captain-command/.../b10_data_validation.py` | Continuous validation: freshness (max_staleness), completeness (required_fields), format (schema validation) |

#### Command — Implementation Additions (No Spec PG)

| File | Purpose | Origin |
|------|---------|--------|
| `b11_replay_runner.py` | Session replay execution | Implementation feature (supports debugging/testing) |
| `b12_compliance_gate.py` | Pre-trade compliance checks | DEC-10 from April 9 audit |
| `telegram_bot.py` | Telegram bot handler | Separated from B7 for modularity |
| `api.py` | FastAPI application | Routes, auth, WebSocket server |
| `orchestrator.py` | Block orchestration | Always-on dispatch |
| `main.py` | Process entry point | — |

---

### 2.5 Shared Modules — Spec Mapping

| File | Spec Docs | Purpose | Key Requirements |
|------|-----------|---------|------------------|
| `shared/topstep_client.py` | (API ref) | REST client — 18 endpoints | Auth, orders, positions, accounts. TOPSTEP_ env prefix. OrderType 1=Limit, 2=Market |
| `shared/topstep_stream.py` | (API ref) | WebSocket streaming | pysignalr, MarketStream + UserStream |
| `shared/contract_resolver.py` | 27 | Contract ID resolution | 10 assets, rollover calendar alignment |
| `shared/account_lifecycle.py` | 19, 25 | Account progression | EVAL→XFA→LIVE, 5 account classes |
| `shared/questdb_client.py` | 24 | QuestDB connection | PostgreSQL wire protocol helper |
| `shared/redis_client.py` | — | Redis pub/sub | 5 channels: signals, trade_outcomes, commands, alerts, status |
| `shared/vault.py` | 19 | AES-256-GCM vault | Per-user key encryption, quarterly rotation |
| `shared/journal.py` | — | SQLite WAL crash recovery | 1 journal per process |
| `shared/constants.py` | — | Shared constants | FROZEN — do not modify |
| `shared/statistics.py` | 21 | Statistical utilities | EWMA, shrinkage, z-scores |
| `shared/signal_replay.py` | — | Signal replay debugging | — |
| `shared/trade_source.py` | — | Trade data abstraction | — |
| `shared/vix_provider.py` | 31 (AIM-04, AIM-11) | VIX/VXV data | IVTS = VIX/VXV term structure ratio |
| `shared/aim_compute.py` | 21, 31, 33 (PG-23) | AIM aggregation | MoE weighted aggregation, combined_modifier ∈[0.5,1.5], dispatch to per-AIM modifiers |
| `shared/aim_feature_loader.py` | 31, 33 (PG-21) | AIM feature loading | 14+ features per asset, per-AIM data source mapping |
| `shared/bar_cache.py` | — | Bar data caching | Replay support |
| `shared/json_helpers.py` | — | JSON serialization | — |
| `shared/process_logger.py` | — | Log forwarder | NEW (uncommitted) — centralized process logging |
| `shared/replay_engine.py` | 28 | Session replay engine | Pseudotrader support |

---

### 2.6 Data Store Map — P3 Datasets

| ID | Table Name | Schema Doc | Written By (Spec) | Written By (Code) | Read By (Spec) | Read By (Code) |
|----|-----------|-----------|-------------------|-------------------|----------------|----------------|
| P3-D00 | `asset_universe_register` | 24 | Off B4 (injection), Off B2 (decay L3) | `b4_injection.py`, `b2_level_escalation.py` | Online all, Offline all | `b1_data_ingestion.py`, `orchestrator.py` (all) |
| P3-D01 | `aim_model_states` | 24 | Off B1 (lifecycle) | `b1_aim_lifecycle.py`, `b1_aim16_hmm.py` | Online B3, GUI | `aim_compute.py`, `b2_gui_data_server.py` |
| P3-D02 | `aim_meta_weights` | 24 | Off B1 (DMA update) | `b1_dma_update.py`, `b1_hdwm_diversity.py`, `b1_drift_detection.py` | Online B3 | `aim_compute.py` |
| P3-D03 | `trade_outcome_log` | 24 | On B7 (position monitor) | `b7_position_monitor.py` | Off B1/B2/B8, reports | `b1_dma_update.py`, `b2_bocpd.py`, `b8_kelly_update.py`, `b6_reports.py` |
| P3-D04 | `decay_detector_states` | 24 | Off B2 (BOCPD/CUSUM) | `b2_bocpd.py`, `b2_cusum.py` | Off B8 (Kelly α), Off B2 | `b8_kelly_update.py` |
| P3-D05 | `ewma_states` | 24 | Off B8 (Kelly update) | `b8_kelly_update.py` | Online B4 (Kelly sizing) | `b4_kelly_sizing.py` |
| P3-D06 | `injection_history` | 24 | Off B4 (injection) | `b4_injection.py` | Reports | `b6_reports.py` |
| P3-D08 | `topstep_state` | 24 | Cmd B8 (SOD reset), Off B7 (TSM sim) | `b8_reconciliation.py`, `b7_tsm_simulation.py` | Online B4, CB, GUI | `b4_kelly_sizing.py`, `b5c_circuit_breaker.py`, `b2_gui_data_server.py` |
| P3-D09 | `report_archive` | 24 | Cmd B6 (reports) | `b6_reports.py` | — | — |
| P3-D10 | `notification_log` | 24, 26 | Cmd B7 (notifications) | `b7_notifications.py` | — | — |
| P3-D11 | `pseudotrader_results` | 24 | Off B3 (pseudotrader), Off B7 (TSM sim) | `b3_pseudotrader.py`, `b7_tsm_simulation.py` | Reports | `b6_reports.py` |
| P3-D12 | `sizing_parameters` | 24 | Off B8 (Kelly), Off B2 (sizing_override) | `b8_kelly_update.py`, `b2_level_escalation.py` | Online B4 | `b4_kelly_sizing.py` |
| P3-D13 | `sensitivity_register` | 24 | Off B5 (sensitivity) | `b5_sensitivity.py` | Online (AIM-13 reads cached result) | `aim_compute.py` |
| P3-D21 | `incident_logs` | 24 | Cmd B9 (incidents) | `b9_incident_response.py` | System Overview | `b2_gui_data_server.py` |
| P3-D22 | `system_health` | 24 | Off B9 (diagnostic) | `b9_diagnostic.py` | GUI (System Overview) | `b2_gui_data_server.py` |
| P3-D23 | `intraday_state` | 24 | On B7 (L_t, n_t), Cmd B8 (ZERO reset) | `b7_position_monitor.py`, `b8_reconciliation.py` | Online CB L1/L2 | `b5c_circuit_breaker.py` |
| P3-D25 | `beta_b_params` | 24 | Off B8 (beta_b fit) | `b8_cb_params.py` | Online CB L3 | `b5c_circuit_breaker.py` |
| P3-D26 | `hmm_states` | 24 | Off B1 (HMM train) | `b1_aim16_hmm.py` | Online B3 (AIM-16 inference) | `aim_compute.py` |
| P3-D27 | `signal_distribution` | 24 | Cmd B1 (routing) | `b1_core_routing.py` | — | — |

**Data stores referenced in spec but NOT in P3-D00..D27 numbering:**
| Store | Purpose | Written By | Code Location |
|-------|---------|-----------|---------------|
| P3-D16 | `capital_silos` | User management / bootstrap | `bootstrap_production.py`, `b8_reconciliation.py` |
| P3-D17 | `system_params` | Seed scripts | `seed_system_params.py` |
| P3-D18 | `version_snapshots` | Off B1 (version snapshot policy) | `version_snapshot.py` |
| P3-D19 | `reconciliation_log` | Cmd B8 (reconciliation) | `b8_reconciliation.py` |

---

### 2.7 Feedback Loop Map

| Loop # | Name | Trigger | Spec Citation | Participating Code Files |
|--------|------|---------|---------------|--------------------------|
| **1** | AIM Meta-Learning | on_close (On B7) | SPEC_INDEX, doc 21 (DMA), doc 32 (PG-02) | `b7_position_monitor.py` → Redis → `orchestrator.py` (offline) → `b1_dma_update.py` → P3-D02 → `aim_compute.py` → `b4_kelly_sizing.py` |
| **2** | Decay Detection | on_close (On B7) | SPEC_INDEX, doc 21 (BOCPD), doc 32 (PG-05/08) | `b7_position_monitor.py` → Redis → `b2_bocpd.py` / `b2_cusum.py` → `b2_level_escalation.py` → P3-D04/D12/D00 → `b4_kelly_sizing.py` |
| **3** | Kelly EWMA | on_close (On B7) | SPEC_INDEX, doc 21 (Kelly), doc 32 (PG-15) | `b7_position_monitor.py` → Redis → `b8_kelly_update.py` → P3-D05/D12 → `b4_kelly_sizing.py` |
| **4** | beta_b Learning | on_close (On B7) | SPEC_INDEX, doc 32 (PG-16C) | `b7_position_monitor.py` → Redis → `b8_cb_params.py` → P3-D25 → `b5c_circuit_breaker.py` (CB L3) |
| **5** | Intraday CB State | on_close (On B7) | SPEC_INDEX, doc 33 (PG-27) | `b7_position_monitor.py` → P3-D23 (L_t += pnl, n_t++) → `b5c_circuit_breaker.py` (CB L1/L2). RESET: `b8_reconciliation.py` at 19:00 EST |
| **6** | SOD Compounding | Cmd B8 sod_reset (19:00 EST) | SPEC_INDEX, doc 25 (fees), doc 34 (PG-39) | `b8_reconciliation.py` → P3-D08 (A, mdd_pct, R_eff, N, E, L_halt) → `b4_kelly_sizing.py` next day |

---

### 2.8 Implementation Additions (Code Without Spec PG)

These code files exist in the codebase but have no direct PG reference in the spec. They are implementation decisions made during development.

| File | Block | Origin | Rationale |
|------|-------|--------|-----------|
| `captain-online/.../b7_shadow_monitor.py` | On B7 | Multi-instance design | Shadow-tracks theoretical outcomes for parity-skipped signals (Category A learning) |
| `captain-online/.../b8_or_tracker.py` | On B8 | Implementation | Opening Range tracking to support B1 feature computation |
| `captain-online/.../b9_session_controller.py` | On B9 | DEC-09 (April 9 audit) | Session lifecycle management extracted from orchestrator |
| `captain-command/.../b11_replay_runner.py` | Cmd B11 | Implementation | Session replay execution for debugging/testing |
| `captain-command/.../b12_compliance_gate.py` | Cmd B12 | DEC-10 (April 9 audit) | Pre-trade compliance check layer |
| `captain-command/.../telegram_bot.py` | Cmd — | Modular separation | Telegram bot handler extracted from B7 |
| `captain-command/.../api.py` | Cmd — | Implementation | FastAPI routes, auth (JWT HS256 per DEC-01), WebSocket server |
| `shared/process_logger.py` | — | NEW (uncommitted) | Centralized process log forwarder |
| `shared/bar_cache.py` | — | Implementation | Bar data caching for replay |
| `shared/json_helpers.py` | — | Implementation | JSON serialization utilities |

---

### 2.9 Spec Requirements — Potential Gaps to Investigate (Sessions 3-5)

These are spec requirements that may not have full code coverage. **Each must be verified against actual code in Sessions 3-5.**

#### HIGH — Likely Missing or Incomplete

| # | Spec Requirement | Spec Doc | Expected Code | Risk |
|---|-----------------|----------|---------------|------|
| S2-01 | Version Snapshot Policy (pre-update snapshots, rollback, regression tests) | 32 | `version_snapshot.py` | Verify full implementation vs spec (deep_copy, max_versions, cold_storage migration, admin approval rollback) |
| S2-02 | PG-09/09B/09C pseudotrader account-aware replay (LEGACY vs IDEAL modes) | 28, 32 | `b3_pseudotrader.py` | G-025 was deferred HIGH in prior audit. Verify current state |
| S2-03 | AIM-16 HMM: 7-element observation vector, TVTP, supervised seeding | 22 | `b1_aim16_hmm.py` | Verify all 7 obs elements, TVTP transitions, quartile P&L seeding |
| S2-04 | Signal Distribution PG-25D: anti-copy priority rotation, EV-balancing | 20 | `b1_core_routing.py` | May be V1 no-op passthrough — verify |
| S2-05 | AIM-05 (Order Book) should return neutral/deferred | 31 | `aim_compute.py` | Verify deferred status handled correctly |
| S2-06 | RPT-12 Alpha Decomposition report | 29 | `b6_reports.py` | Not in doc 34 pseudocode, only in doc 29 governance. Verify existence |
| S2-07 | P3-D16 capital_silos per-user isolation | 19 | `bootstrap_production.py` | Verify multi-user capital isolation |
| S2-08 | P3-D18 version_snapshots table | 32 | `version_snapshot.py`, `init_questdb.py` | Verify QuestDB table exists |

#### MEDIUM — Partial or Deferred

| # | Spec Requirement | Spec Doc | Expected Code | Risk |
|---|-----------------|----------|---------------|------|
| S2-09 | RBAC 6 roles (ADMIN/ANALYST/DEV/TRADER/VIEWER/AUDITOR/SYSTEM) | 19 | `api.py` | May be V1-simplified |
| S2-10 | Quiet hours 22:00-06:00 local user TZ with CRITICAL override | 26 | `b7_notifications.py` | Verify implementation |
| S2-11 | Per-user notification preferences (channel toggles, priority threshold, asset filters) | 26 | `b7_notifications.py` | Verify granularity |
| S2-12 | Compliance gate: instrument_permitted + max_contracts check | 34 | `b12_compliance_gate.py` | Verify completeness vs spec |
| S2-13 | XFA scaling tiers end-of-day evaluation (5 profit tiers) | 25 | `b8_reconciliation.py` | Verify tier lookup table |
| S2-14 | Payout recommendation logic (XFA: $5k/50% cap, 10% commission, 5 winning days) | 25 | `b8_reconciliation.py` | Verify rules |
| S2-15 | AIM cascading dependencies (e.g., AIM-06+AIM-10→AIM-01→sizing) | 31 | `aim_compute.py`, `aim_feature_loader.py` | Verify cascade order |
| S2-16 | Health endpoint (GET /health) with 30s external monitoring, 3 consecutive failures→alert | 34 | `api.py` | Verify implementation |

#### LOW — Operational/Governance (Verify Existence)

| # | Spec Requirement | Spec Doc | Expected Code | Risk |
|---|-----------------|----------|---------------|------|
| S2-17 | 12 report specs (RPT-01 to RPT-12) all implemented | 29, 34 | `b6_reports.py` | Some may be stubs |
| S2-18 | Audit trail logging (user_id, timestamp, action, old_value, new_value) | 19 | `api.py`, various | Verify logging granularity |
| S2-19 | CUSUM bootstrap calibration (PG-07) at init + quarterly | 32 | `b2_cusum.py` | Verify calibration schedule |
| S2-20 | System Health 8 dimensions fully scored | 32 | `b9_diagnostic.py` | Verify all D1-D8 implemented |
| S2-21 | Incident escalation matrix (P1: 5min, P2: 30min, P3: 4hr, P4: next day) | 29 | `b9_incident_response.py` | Verify routing |
| S2-22 | Contract rollover: roll_confirmed flag, ROLL_PENDING status | 27, 33 | `b1_data_ingestion.py` | Verify roll calendar handling |

---

### 2.10 Summary Statistics

| Metric | Count |
|--------|-------|
| Spec documents read | 16 |
| PG programs mapped | 32 (PG-01 to PG-41, with gaps) |
| Offline blocks mapped | 9 (17 code files) |
| Online blocks mapped | 9 + CB (14 code files) |
| Command blocks mapped | 10 (12+ code files) |
| Shared modules mapped | 19 |
| Data stores mapped | 22 (P3-D00 to P3-D27 + D16/D17/D18/D19) |
| Feedback loops mapped | 6 |
| Implementation additions | 10 files (no spec PG) |
| Potential gaps flagged | 22 (8 HIGH, 8 MEDIUM, 6 LOW) |
| AIM modules specified | 16 (AIM-01 to AIM-16, AIM-05 deferred) |
| Reports specified | 12 (RPT-01 to RPT-12) |

**All 71 source files from Session 1 index have been mapped to spec requirements or flagged as implementation additions.**

---

## Session 3 — P3-Offline Audit

**Status:** PENDING

_(To be populated by Session 3)_

---

## Session 4 — P3-Online Audit

**Status:** PENDING

_(To be populated by Session 4)_

---

## Session 5 — P3-Command Audit

**Status:** PENDING

_(To be populated by Session 5)_

---

## Session 6 — Cross-Verification & Verdict

**Status:** PENDING

_(To be populated by Session 6)_
