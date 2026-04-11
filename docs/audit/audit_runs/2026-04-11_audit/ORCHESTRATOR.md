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
| 2 | Spec Extraction | Obsidian vault tag search, wikilink traversal, spec-to-code mapping | PENDING |
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

## Session 2 — Spec Extraction

**Status:** PENDING

_(To be populated by Session 2)_

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
