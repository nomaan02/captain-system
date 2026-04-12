# Spec Manifest -- Canvas Cross-Validation Audit

> **Generated:** 2026-04-12 Phase 0
> **Source:** 8 Backend (.md) canvas mirrors + SPEC_INDEX.md from `~/obsidian-spec/`
> **Purpose:** Complete catalogue of everything the specs define. Subsequent audit sessions reference this instead of re-reading the vault.

---

## 1. Blocks Per Component

### Captain Offline (9 blocks, event-driven + scheduled)

| Block | Name | PG Refs | Service |
|-------|------|---------|---------|
| B1 | AIM Model Training & Management | PG-01, PG-01C, PG-02, PG-03, PG-04 | offline_worker |
| B2 | Strategy Decay Detection | PG-05, PG-06, PG-07, PG-08 | offline_worker |
| B3 | Pseudotrader | PG-09, PG-09B, PG-09C | offline_worker |
| B4 | Injection Comparison | PG-10, PG-11 | offline_worker |
| B5 | Sensitivity (AIM-13) | PG-12 | offline_worker (monthly cron) |
| B6 | Auto-Expansion (AIM-14) | PG-13 | offline_worker (L3 decay trigger) |
| B7 | TSM Simulation | PG-14 | offline_worker (monthly cron) |
| B8 | Kelly Updates | PG-15, PG-16C | offline_worker (trade outcome trigger) |
| B9 | System Health | PG-17 | offline_worker (weekly/monthly cron) |

### Captain Online (9 blocks + B5B + Circuit Breaker, session-driven)

| Block | Name | PG Refs | Service | Scope |
|-------|------|---------|---------|-------|
| B1 | Data Ingestion | PG-21 | online_engine | SHARED |
| B2 | Regime Probability | PG-22 | online_engine | SHARED |
| B3 | AIM Aggregation | PG-23 | online_engine | SHARED |
| B4 | Kelly 7-Layer Sizing | PG-24 | online_engine (per-user worker) | PER-USER |
| B5 | Trade Selection | PG-25 | online_engine | PER-USER |
| B5B | Quality Gate | PG-25B | online_engine | PER-USER |
| CB | Circuit Breaker (L0-L4) | PG-27B | online_engine (between B5B and B6) | PER-USER |
| B6 | Signal Output | PG-26 | online_engine | PER-USER |
| B7 | Position Monitor | PG-27 | online_engine (continuous) | PER-USER |
| B8 | Net Concentration | PG-28 | online_engine | PER-USER |
| B9 | Capacity Evaluation | PG-29 | online_engine (session-end) | PER-USER |

### Captain Command (10 blocks, always-on)

| Block | Name | PG Refs | Service |
|-------|------|---------|---------|
| B1 | Core Routing | PG-30 | command_server (FastAPI + WebSocket) |
| B2 | GUI Interface | PG-31 | command_server (WebSocket push) |
| B3 | API + Execution | PG-32 | command_server (REST) |
| B4 | TSM Management | PG-33 | command_server |
| B5 | Injection Flow | PG-34 | command_server (GUI workflow) |
| B6 | Reports | PG-35 | command_server (cron per RPT schedule) |
| B7 | Notifications | PG-36 | command_server + Telegram bot |
| B8 | Daily Reconciliation | PG-39 | command_server (cron 19:00 EST daily) |
| B9 | Incident Response | PG-40 | command_server |
| B10 | Data Validation | PG-41 | online_engine + command_server |

---

## 2. Programs (PG-XX)

### Offline Programs

| PG | Name | Block | Spec Docs |
|----|------|-------|-----------|
| PG-01 | AIM Lifecycle | Off B1 | 31, 32 |
| PG-01C | HMM Training | Off B1 | 31, 32 |
| PG-02 | DMA Update | Off B1 | 21, 32 |
| PG-03 | HDWM Diversity Check | Off B1 | 21, 32 |
| PG-04 | Drift Detection (ADWIN) | Off B1 | 32 |
| PG-05 | BOCPD | Off B2 | 21, 32 |
| PG-06 | CUSUM | Off B2 | 21, 32 |
| PG-07 | CUSUM Limits Recalibration | Off B2 | 32 |
| PG-08 | Decay Response | Off B2 | 32 |
| PG-09 | Pseudotrader (PBO, CSCV S=16) | Off B3 | 28, 32 |
| PG-09B | Pseudotrader CB Replay | Off B3 | 28, 32 |
| PG-09C | Pseudotrader CB Grid | Off B3 | 28, 32 |
| PG-10 | Injection Compare | Off B4 | 32 |
| PG-11 | Injection Transition | Off B4 | 32 |
| PG-12 | Sensitivity Grid | Off B5 | 32 |
| PG-13 | Auto-Expansion | Off B6 | 32 |
| PG-14 | TSM Monte Carlo | Off B7 | 32 |
| PG-15 | Kelly EWMA Update | Off B8 | 21, 32 |
| PG-16C | Beta_b Estimator | Off B8 | 32 |
| PG-17 | System Health | Off B9 | 32 |

### Online Programs

| PG | Name | Block | Spec Docs |
|----|------|-------|-----------|
| PG-21 | Data Ingestion | On B1 | 33 |
| PG-22 | Regime Probability | On B2 | 23, 33 |
| PG-23 | AIM Aggregation / MoE Gating | On B3 | 22, 31, 33 |
| PG-24 | Kelly 7-Layer Sizing | On B4 | 21, 33 |
| PG-25 | Trade Selection | On B5 | 33 |
| PG-25B | Quality Gate | On B5B | 33 |
| PG-25D | Signal Distribution (multi-user) | -- | 20 |
| PG-26 | Signal Output | On B6 | 33 |
| PG-27 | Position Monitor | On B7 | 33 |
| PG-27B | Circuit Breaker (L0-L4) | On CB | 33 |
| PG-28 | Net Concentration | On B8 | 33 |
| PG-29 | Capacity Evaluation | On B9 | 33 |

### Command Programs

| PG | Name | Block | Spec Docs |
|----|------|-------|-----------|
| PG-30 | Core Routing | Cmd B1 | 34 |
| PG-31 | GUI Data Server | Cmd B2 | 18, 34 |
| PG-32 | Broker Adapters / API Execution | Cmd B3 | 34 |
| PG-33 | TSM Management | Cmd B4 | 25, 34 |
| PG-34 | Injection Flow | Cmd B5 | 34 |
| PG-35 | Report Generation | Cmd B6 | 26, 29, 34 |
| PG-36 | Notifications | Cmd B7 | 26, 34 |
| PG-39 | Daily Reconciliation (SOD Reset) | Cmd B8 | 25, 34 |
| PG-40 | Incident Response | Cmd B9 | 29, 34 |
| PG-41 | Data Validation | Cmd B10 | 34 |

---

## 3. Data Stores

### P3 Data Stores (Captain)

| Store | Name | QuestDB Table (spec name) | Written By | Read By | Feedback Loop |
|-------|------|---------------------------|-----------|---------|---------------|
| P3-D00 | Asset universe / system config | asset_universe | Off B4 (injection), Loop 2 (decay) | Online, Offline | Loop 2 |
| P3-D01 | AIM model states / modifiers | aim_model_states (QuestDB) + aim_modifiers:{asset} (Redis hash) | Off B1, AIM modules | Online B3, DMA engine | -- |
| P3-D02 | AIM meta-weights / DMA inclusion probs | meta_weights | Off B1 (dma_update, HDWM, drift) | Online B3 (MoE) | **Loop 1** |
| P3-D03 | Trade outcome log | trade_outcomes | On B7 (on_close) | Off B1, B2, B8 | Trigger for Loops 1,2,3,4 |
| P3-D04 | BOCPD/CUSUM decay probs | bocpd + cusum subtables | Off B2 | Off B8 (alpha for Kelly) | **Loop 2** |
| P3-D05 | EWMA states (win rate, avg win/loss) | ewma_states | Off B8 | Online B4 (Kelly L1,L4) | **Loop 3** |
| P3-D06 | Locked strategy reference | (injection comparison) | Off B4 | Online | -- |
| P3-D07 | Correlation model states | correlation_model_states | AIM-08 | AIM-08 | -- |
| P3-D08 | TSM state / configs | tsm_configs | Cmd B8 (sod_reset), Cmd B4 | Online B4 (L6,L7), CB (L0,L1,L2) | **Loop 6** |
| P3-D09 | Report archive | report_archive | Cmd B6 | -- | -- |
| P3-D10 | Notification log | notification_log | Cmd B7 | -- | -- |
| P3-D11 | Pseudotrader + TSM sim results | pseudotrader_results | Off B3, Off B7 | -- | -- |
| P3-D12 | Kelly params (f*, overrides, shrinkage) | kelly_params | Off B8, Loop 2 (sizing_override) | Online B4 (Kelly L1-L3) | **Loop 2, 3** |
| P3-D13 | Sensitivity scan results | sensitivity_scan_results | Off B5 | AIM-13 | -- |
| P3-D14 | API connection states | api_connection_states | Cmd B3 | Cmd B3 | -- |
| P3-D16 | User profiles / capital silos | user_profiles / capital_silos | -- | Online B4 (L6), Cmd B2 | -- |
| P3-D17 | Data quality log | data_quality_log | On B1, On B9 | Cmd B10 | -- |
| P3-D18 | Snapshots (version manager) | snapshots | Off B1 (before every write) | -- | -- |
| P3-D19 | Reconciliation log | reconciliation_log | Cmd B8 | -- | -- |
| P3-D20 | SQLite WAL checkpoint | *SQLite, not QuestDB* | Off B8 | -- | -- |
| P3-D21 | Incident log | incident_log | Cmd B9 | -- | -- |
| P3-D22 | System health scores | system_health | Off B9 | -- | -- |
| P3-D23 | Intraday CB state (L_t, n_t) | intraday_state (QuestDB + Redis) | On B7 (on_close) | CB L1/L2 | **Loop 5** |
| P3-D25 | Circuit breaker beta_b params | circuit_breaker / beta_b_params | Off B8 (PG-16C) | CB L3 | **Loop 4** |
| P3-D26 | HMM states | hmm_states | Off B1 (PG-01C) | Online B3 (HMM inference) | -- |
| P3-D27 | Signal distribution state/log | distribution_state (Redis) + distribution_audit (QuestDB) | Cmd B1, signal distributor | Signal distributor | -- |

### P2 Data Stores (Regime Selection)

| Store | Name | Written By | Read By (P3) |
|-------|------|-----------|--------------|
| P2-D01 | Realized volatility (RV_t, sigma_t) | P2 Block 1 | -- |
| P2-D02 | Regime labels (HIGH_VOL / LOW_VOL) | P2 Block 1 | -- |
| P2-D03 | Tau per strategy x regime | P2 Block 2 | -- |
| P2-D04 | Bootstrap p-values | P2 Block 2 | -- |
| P2-D05 | Complexity tier (C1-C4) | P2 Pre-Block 3 | -- |
| P2-D06 | **Locked strategy register** | P2 Block 3a | Off B4 (injection), Online |
| P2-D07 | **Trained regime classifier** (joblib) | P2 Block 3b | Online B2 (PG-22) |
| P2-D08 | Classifier validation metrics | P2 Block 3b | -- |
| P2-D09 | Classifier features (f1..f14) | P2 Pre-Pipeline | -- |

### P1 Data Stores (Strategy Validation)

| Store | Name | Written By | Read By (P2/P3) |
|-------|------|-----------|-----------------|
| D-00 | Model definitions (~9,200 JSON) | Model Generator | P1 Pre-Pipeline |
| D-01 | Market data (1-min OHLCV) | Model Generator / QC | P1, P2 Block 1 |
| D-02 | Input variable definitions (IX-1) | Model Generator | P1 Pre-Pipeline |
| D-03 | Transformation definitions (IX-2) | Model Generator | P1 Pre-Pipeline |
| D-04 | Sample periods | Model Generator | P1 Pre-Pipeline |
| D-05 | Indexed variables V(n) | Pre-Pipeline (IX-1) | P1 Block 1 |
| D-06 | Indexed transformations T(n) | Pre-Pipeline (IX-2) | P1 Block 1 |
| D-07 | Indexed samples S(s) w/ DISCOVERY/OOS | Pre-Pipeline (IX-3/3a) | P1 B2a-B5, P2 |
| D-08 | Feature index F(k), N_F ~144 | P1 Block 1 (IX-4) | P1 B2B+ |
| D-09 | Control model index m=1..N_M | Pre-Pipeline (IX-5) | P1 Block 2a |
| D-10 | Trade results per model (m) | P1 Block 2a (IX-6) | P1 B2B, B3, B4, B5 |
| D-11 | Multi-test results | P1 Block 5 | -- |
| D-13 | Raw feature time series | P1 Block 1 | P1 B2B, B3, B4, B5 |
| D-14..D-19 | Feature experiment results | P1 Block 2B | -- |
| D-20 | Threshold, direction, shape per (m,k) | P1 Block 3 | P1 Block 4, P2 |
| D-21 | QC metrics (control + model) | P1 Block 4 | -- |
| D-22 | Trade log (NET of fees) | P1 Block 4 | P1 Block 5, P2 Block 2 |
| D-23 | Test weights | P1 Block 5 (PG-07) | -- |
| D-24 | **OO scores** (P1 final output) | P1 Block 5 | P2 Block 3a |

---

## 4. AIM Modules (16)

| AIM | Name | Seed Type | Module Filename | Data Source | Notes |
|-----|------|-----------|-----------------|-------------|-------|
| AIM-01 | VRP (Volatility Risk Premium) | Options | aim_01_vrp.py | Redis: iv_atm:{asset}, QuestDB: P2-D01 (rv) | -- |
| AIM-02 | Skew | Options | aim_02_skew.py | Redis: pcr:{asset}, put_skew:{asset} | -- |
| AIM-03 | GEX (Gamma Exposure) | Options | aim_03_gex.py | Redis: option_chain:{asset} | DEPS: scipy (BSM) |
| AIM-04 | Pre-Market | Microstructure | aim_04_premarket.py | Redis: vix_close, vxv_close, overnight_return | -- |
| AIM-05 | Orderbook (LOB) | Microstructure | aim_05_orderbook.py | N/A | **DEFERRED** stub, returns 1.0 |
| AIM-06 | Calendar | Macro/Event | aim_06_calendar.py | disk: economic_calendar.json | -- |
| AIM-07 | COT (Commitment of Traders) | Macro/Event | aim_07_cot.py | disk: cot_weekly/ (3d lag) | -- |
| AIM-08 | Correlation (DCC-GARCH) | Cross-Asset | aim_08_correlation.py | Redis: prices:{ES,NQ,CL,DXY,10Y,USDCAD} | DEPS: arch, R/W P3-D07 |
| AIM-09 | Momentum | Cross-Asset | aim_09_momentum.py | Redis: cross_asset_prices | -- |
| AIM-10 | Calendar Effect | Temporal | aim_10_calendar_effect.py | system calendar, Redis: price_feed, QuestDB: P3-D00 (OPEX dates) | -- |
| AIM-11 | Regime Warning | Temporal | aim_11_regime_warning.py | Redis: vix_feed, macro_data (credit_spreads), P2 regime state | -- |
| AIM-12 | Cost Estimator | Internal | aim_12_cost_estimator.py | QuestDB: P3-D03 (execution history), Redis: live_spread | -- |
| AIM-13 | Sensitivity | Internal | aim_13_sensitivity.py | QuestDB: P3-D13 (sensitivity_scan_results) | -- |
| AIM-14 | Auto-Expansion | Internal | aim_14_auto_expansion.py | QuestDB: P3-D04 (decay_events) | Not a modifier (returns 1.0), triggers Off B6 on L3 decay |
| AIM-15 | Volume Quality | Microstructure | aim_15_volume_quality.py | Redis: volume_or:{asset}, QuestDB: avg_volume_20d | -- |
| AIM-16 | HMM (Opportunity) | Opportunity | aim_16_hmm.py | Train: P3-D03 -> P3-D26. Infer: P3-D26 -> session_budget_weights | Session-level, not per-asset. DEPS: hmmlearn |

### AIM Aggregation Path

```
16 AIMs -> Redis hash aim_modifiers:{asset} (fields aim_01..aim_16)
  -> DMA Update (Offline PG-02): P3-D01 snapshot -> P3-D02 meta_weights
  -> MoE Gating (Online PG-23): P3-D01 + P3-D02 -> combined_modifier:{asset}
  -> Kelly L5 (Online PG-24): f *= combined_mod
```

---

## 5. Python Module Filenames Referenced in Specs

### Offline Modules

| Module | PG | Purpose |
|--------|-----|---------|
| aim_lifecycle.py | PG-01 | AIM state transitions |
| hmm_trainer.py | PG-01C | HMM 60-day Baum-Welch training |
| dma_engine.py | PG-02, PG-03 | DMA update + HDWM diversity check + mag_weighted_likelihood() |
| drift_det.py / drift_detector.py | PG-04 | ADWIN drift detection with AutoEncoder models |
| version_manager.py | B1 | P3-D18 snapshot before every write |
| bocpd.py | PG-05 | Bayesian Online Changepoint Detection |
| cusum.py | PG-06 | CUSUM monitoring |
| decay_response.py | PG-08 | L2 reduce / L3 halt response |
| pseudotrader.py | PG-09 | PBO (CSCV S=16) pseudotrading |
| pbo_engine.py | B3 | PBO computation engine |
| cb_replay.py | PG-09B | Circuit breaker replay |
| cb_grid.py | PG-09C | Circuit breaker parameter grid search |
| injection.py | PG-10 | E_new vs 1.2xE comparison (ADOPT/PARALLEL/REJECT) |
| transition.py | PG-11 | Injection transition blending |
| sensitivity.py | PG-12 | Grid +/-20%, PBO+DSR scoring |
| auto_expand.py | PG-13 | L3 decay -> scan candidates |
| tsm_simulator.py | PG-14 | Monte Carlo 10k paths |
| kelly_ewma.py | PG-15 | EWMA update, alpha=f(cp), f*=(pW-(1-p)L)/W |
| beta_b_estimator.py | PG-16C | beta_b serial correlation fit |
| system_health.py | PG-17 | 8-dimension health scoring |

### Online Modules

| Module | PG | Purpose |
|--------|-----|---------|
| data_ingestion.py | PG-21 | Feed validation, 14 features, roll calendar check |
| data_moderator.py | B1 | Data quality moderation |
| aim_feature_compute.py | B1 | AIM feature computation |
| regime_classifier.py | PG-22 | XGBoost/sklearn classifier inference |
| aim_aggregator.py | PG-23 | compute_combined_modifier(), MoE gating |
| moe_gating.py | PG-23 | Mixture of Experts softmax(g/tau) gating |
| hmm_inference.py | PG-23 | HMM-16 state inference |
| aim_01_vrp.py .. aim_16_hmm.py | B3 | 16 individual AIM modules |
| kelly_pipeline.py | PG-24 | L2 blend, L3 shrink, L4 robust, L5 aim, L6 account, L7 caps |
| fee_resolver.py | PG-24, B7 | get_round_trip_fee() |
| trade_selector.py | PG-25 | hmm_opp_wt x daily_budget ranking |
| quality_gate.py | PG-25B | $/contract floor + ceiling |
| circuit_breaker.py | PG-27B | L0 scaling, L1 preemptive, L2 budget, L3 beta_b, L4 sharpe |
| signal_emitter.py | PG-26 | jitter(time, size), Redis publish |
| anti_copy_jitter.py | PG-26 | Anti-copy-trading time/size jitter (multi-user) |
| signal_distributor.py | PG-25D/PG-30 | 6-step distribution: pool -> merge -> conflict -> rotation -> bypass -> output |
| position_monitor.py | PG-27 | Track open positions, on_close -> P3-D03 |
| concentration.py | PG-28 | IF same_dir > 80%: ALERT |
| capacity_eval.py | PG-29 | fill_quality, slippage metrics |
| session_evaluator.py | -- | Inline session orchestration (runs B1-B9 sequence) |

### Command Modules

| Module | PG | Purpose |
|--------|-----|---------|
| command_router.py | PG-30 | Core routing, sanitise_for_api() -> 6 fields only |
| gui_data_server.py | PG-31 | WebSocket push to GUI clients |
| admin_overview.py | PG-31 | System Overview (ADMIN-only) |
| broker_adapter_topstep.py | PG-32 | TopstepX REST adapter (mTLS) |
| broker_adapter_ibkr.py | PG-32 | IBKR adapter (mTLS) |
| compliance_gate.py | PG-32 | Verify signal within TSM constraints |
| tsm_manager.py | PG-33 | onboard_account(), validate_fee_schedule() |
| injection_flow.py | PG-34 | GUI workflow for injection |
| report_generator.py | PG-35 | RPT-01 through RPT-12 generation |
| notification_router.py | PG-36 | Route to gui, telegram, push |
| telegram_bot.py | PG-36 | Telegram Bot API (long-polling) |
| reconciliation.py | PG-39 | SOD reset: A=balance, mdd_pct, R_eff, N, E, L_halt |
| payout_rules.py | PG-39 | XFA + Live payout logic |
| incident_handler.py | PG-40 | Incident creation and response |
| data_validator.py | PG-41 | Freshness/completeness/schema checks |

### P1/P2 Modules (upstream, not in captain-system repo)

| Module | Program | Purpose |
|--------|---------|---------|
| model_generator.py | Upstream | Generate ~9,200 model variants |
| feature_generate_program.py | P1 B1 | V x T cross-product feature gen |
| input_compute.py | P1 B1 | Variable computation |
| transform_compute.py | P1 B1 | Transformation application |
| bootstrap_engine.py | P1 B2B, P2 B2 | Shared bootstrap iteration engine |
| state_functions.py | P1 B5 | 12 per-test relevance weight functions |

---

## 6. Redis Key Patterns

### Pub/Sub Channels

| Channel | Publisher | Subscriber | Payload |
|---------|----------|------------|---------|
| `captain:signals:{user_id}` | Online B6 (PG-26) | Command B1 (PG-30) | Signal batch (direction, size, TP, SL, per-account) |
| `captain:trade_outcomes` / `trades` | Online B7 (PG-27) | Offline orchestrator | Trade outcome (trade_id, pnl, regime, AIM context) |
| `captain:commands` | Command B1 (PG-30) | Online, Offline | TAKEN/SKIPPED, strategy decisions, TSM, AIM control |
| `captain:alerts` | Any process | Command B7 (PG-36) | Alert with priority (CRITICAL/HIGH/MEDIUM/LOW) |
| `captain:status` | All processes | Command B1 | Heartbeat + health |
| `market:{asset}` | Data feed | AIM compute workers | Market data pub/sub |

### Hashes and Keys

| Key Pattern | Purpose | Data Store | Written By | Read By |
|-------------|---------|------------|-----------|---------|
| `aim_modifiers:{asset}` | AIM modifier values (fields aim_01..aim_16) | P3-D01 | AIM modules | Online B3 (MoE), DMA engine |
| `regime_probs:{asset}` | P(LOW_VOL), P(HIGH_VOL) | -- | Online B2 (PG-22) | Online B4 (Kelly L2), Cmd B2 |
| `combined_modifier:{asset}` | Combined AIM modifier after MoE | -- | Online B3 (PG-23) | Online B4 (Kelly L5) |
| `session_budget_weights` | HMM-16 budget allocation | -- | Online B3 | Online B5 |
| `aim_breakdown` | Individual AIM breakdown | -- | Online B3 | Cmd B2 (GUI) |
| `intraday:{account_id}` | Intraday CB state (L_t, n_t) | P3-D23 | Online B7 | CB L1/L2 |
| `fees:{asset}` | Fee schedule per asset | -- | Cmd B4 | Online B4 (L7), CB L1 |
| `adwin:{aim_id}` | ADWIN drift detector state | -- | Off B1 (PG-04) | Off B1 (PG-04) |
| `bocpd:{asset}` | BOCPD changepoint probability | P3-D04 | Off B2 (PG-05) | Off B8 (Kelly alpha) |
| `distribution_state` | Priority queue + rolling_30d_ev | P3-D27 | Signal distributor | Signal distributor |

### AIM Data Source Keys

| Key Pattern | AIM | Source |
|-------------|-----|--------|
| `iv_atm:{asset}` | AIM-01 | options_chain adapter |
| `pcr:{asset}` | AIM-02 | options_chain adapter |
| `put_skew:{asset}` | AIM-02 | options_chain adapter |
| `option_chain:{asset}` | AIM-03 | options_chain adapter |
| `vix_close` | AIM-04 | vix_feed |
| `vxv_close` | AIM-04 | vix_feed |
| `overnight_return` | AIM-04 | price_feed |
| `volume_or:{asset}` | AIM-15 | price_feed |
| `prices:{ES,NQ,CL,DXY,10Y,USDCAD}` | AIM-08 | cross_asset_prices |
| `live_spread` | AIM-12 | price_feed |
| `credit_spreads` | AIM-11 | macro_data |

### Queues (Redis Lists)

| Queue | Purpose | Publisher | Consumer |
|-------|---------|----------|----------|
| `signal_queue` | Signal routing | Online B6 | Command B1 |
| `command_queue` | Command routing | Command B1 | Online, Offline |
| `notification_queue` | Notification routing | Any (PG-08, PG-28, PG-40) | Command B7 |

---

## 7. QuestDB Tables

Per doc 24 (P3 Dataset Schemas): 18 tables for D00-D27.

| Table Name (spec) | Data Store | Component | Read/Write Pattern |
|--------------------|-----------|-----------|-------------------|
| asset_universe | P3-D00 | Off B4, Loop 2 W / Online R | Mostly-read, write on injection or decay |
| aim_model_states | P3-D01 | Off B1 W / Online B3 R | Write after training, read per session |
| meta_weights | P3-D02 | Off B1 W / Online B3 R | Write after DMA/HDWM/drift, read per session |
| trade_outcomes | P3-D03 | On B7 W / Off B1,B2,B8 R | Append per trade, read for learning |
| bocpd (decay subtable) | P3-D04 | Off B2 W / Off B8 R | Write per outcome, read for Kelly alpha |
| cusum (decay subtable) | P3-D04 | Off B2 W | Write per outcome |
| ewma_states | P3-D05 | Off B8 W / Online B4 R | Write per outcome batch, read per session |
| (injection comparison) | P3-D06 | Off B4 W / Online R | Write on injection |
| correlation_model_states | P3-D07 | AIM-08 R/W | Periodic update |
| tsm_configs / tsm_state | P3-D08 | Cmd B8 W, Cmd B4 W / Online B4,CB R | Daily SOD update, read per session |
| report_archive | P3-D09 | Cmd B6 W | Append per report |
| notification_log | P3-D10 | Cmd B7 W | Append per notification |
| pseudotrader_results | P3-D11 | Off B3,B7 W | Write after pseudotrader/TSM sim |
| kelly_params | P3-D12 | Off B8 W, Loop 2 W / Online B4 R | Write per outcome, read per session |
| sensitivity_scan_results | P3-D13 | Off B5 W / AIM-13 R | Monthly update |
| api_connection_states | P3-D14 | Cmd B3 R/W | Per API connection |
| user_profiles / capital_silos | P3-D16 | -- / Online B4, Cmd B2 R | Mostly-read |
| data_quality_log | P3-D17 | On B1, On B9 W | Append per validation |
| snapshots | P3-D18 | Off B1 W | Pre-write snapshot |
| reconciliation_log | P3-D19 | Cmd B8 W | Daily append |
| incident_log | P3-D21 | Cmd B9 W | Append per incident |
| system_health | P3-D22 | Off B9 W | Weekly/monthly scoring |
| intraday_state | P3-D23 | On B7 W / CB L1/L2 R | Per-trade update, daily ZERO by Cmd B8 |
| circuit_breaker / beta_b_params | P3-D25 | Off B8 (PG-16C) W / CB L3 R | Write per outcome batch, read per session |
| hmm_states | P3-D26 | Off B1 (PG-01C) W / Online B3 R | Write after HMM training, read per session |
| distribution_audit | P3-D27 | Signal distributor W | Per-session append |
| aim_features_{N} | -- | AIM compute | Per-AIM feature stores |

---

## 8. Feedback Loops (6 total)

| Loop | Name | Trigger | Path | Destination |
|------|------|---------|------|-------------|
| **1** | AIM Meta-Learning | On B7 on_close | P3-D03 -> Off B1 dma_update -> **P3-D02** | On B3 -> combined_mod -> On B4 |
| **2** | Decay Detection | On B7 on_close | P3-D03 -> Off B2 bocpd -> **P3-D04** -> sizing_override -> **P3-D12** or DECAYED -> **P3-D00** | On B4 (Kelly reduced) or halt |
| **3** | Kelly EWMA | On B7 on_close | P3-D03 -> Off B8 ewma -> alpha=f(cp) -> **P3-D05** -> f* -> **P3-D12** | On B4 Kelly sizing |
| **4** | beta_b Learning | On B7 on_close | P3-D03 -> Off B8 beta_b_fit -> **P3-D25** | CB L3: IF mu_b <= 0: BLOCK |
| **5** | Intraday CB State | On B7 on_close | P3-D23 (L_t += pnl, n_t++) | CB L1/L2. RESET: 19:00 EST by Cmd B8 |
| **6** | SOD Compounding | Cmd B8 daily 19:00 EST | A=balance -> mdd_pct=4500/A -> R,N,E,L_halt -> **P3-D08** | On B4 next day |

---

## 9. Circuit Breaker Layers (PG-27B)

| Layer | Name | Reads | Condition | Action |
|-------|------|-------|-----------|--------|
| L0 | Scaling Cap | P3-D08 (tier_limit) | (XFA only) IF micros > tier | BLOCK |
| L1 | Preemptive Halt | P3-D23 (L_t), fee_schedule | IF \|L_t\| + rho_j >= L_halt | BLOCK |
| L2 | Budget Check | P3-D08 (E, L_halt), P3-D23 (L_t) | IF E - \|L_t\| < needed | BLOCK |
| L3 | beta_b Expectancy | P3-D25 (beta_b) | mu_b = r_bar + b_b * L_b; IF mu_b <= 0 | BLOCK |
| L4 | Correlation Sharpe | Redis (basket_hist) | Rolling Basket Sharpe check | BLOCK |

---

## 10. Kelly 7-Layer Pipeline (PG-24)

| Layer | Name | Location | Reads | Module Function |
|-------|------|----------|-------|-----------------|
| L1 | Regime-Conditional Kelly | Offline B8 (PG-15) | P3-D05, P3-D03, bocpd cp | kelly_pipeline.py -> update_regime_kelly() |
| L2 | Blended Kelly | Online B4 (PG-24) | P3-D12, regime_probs | kelly_pipeline.py -> compute_blended_kelly() |
| L3 | Parameter Uncertainty Shrinkage | Online B4 | P3-D12 (shrinkage_factor) | kelly_pipeline.py -> apply_shrinkage() |
| L4 | Robust Kelly Fallback | Online B4 | P3-D05 (EWMA moments) | kelly_pipeline.py -> robust_kelly_check() |
| L5 | AIM Modifier | Online B4 | P3-D01 (aim_modifiers), P3-D02 (meta_weights) | aim_aggregator.py -> compute_combined_modifier() |
| L6 | Account-Type Adjustment | Online B4 | P3-D08 (tsm_configs), P3-D16 (user_profiles) | kelly_pipeline.py -> account_kelly_adjustment() |
| L7 | TSM Hard Constraints | Online B4 | P3-D08 (MDD/MLL), P3-D23 (intraday), fees | kelly_pipeline.py -> compute_final_contracts() + fee_resolver.py |

---

## 11. Signal Distribution Pipeline (PG-25D / PG-30)

| Step | Name | Module Function | Key I/O |
|------|------|-----------------|---------|
| 1 | Pool Classification | signal_distributor.py -> classify_pool() | R: P3-D08, P3-D16 |
| 2 | Merge & Deduplicate | signal_distributor.py -> merge_and_dedup() | R: P3-D08 (instrument_permissions) |
| 3 | Conflict Key Check | signal_distributor.py (inline) | in-memory: assigned_conflicts |
| 4 | Priority Rotation & EV Balancing | signal_distributor.py -> distribute_signals() | R/W: P3-D27 (priority_queue, rolling_30d_ev) |
| 5 | Broker-Only Bypass | signal_distributor.py -> append_broker_only() | in-memory |
| 6 | Assignment Output | signal_distributor.py -> finalise_distribution() | W: P3-D27, distribution_audit |

---

## 12. External Dependencies Referenced in Specs

| Dependency | Used By | Purpose |
|------------|---------|---------|
| hmmlearn | AIM-16 (PG-01C, Online B3) | GaussianHMM (static, V1) |
| scipy | Off B2 (bocpd.py), AIM-03 | Student-t distribution, BSM gamma |
| xgboost | Online B2 (PG-22) | Regime classifier inference |
| sklearn | Online B2, P1 B3 | LogisticRegression fallback, isotonic regression |
| arch | AIM-08 | DCC-GARCH correlation |
| deap | Off B6 (auto_expand.py) | Genetic algorithm |
| kneed | P1 B3, Off B5 | Kneedle algorithm for thresholds |
| python-telegram-bot | Cmd B7 | Telegram notifications (long-polling) |
| pysignalr | shared/topstep_stream.py | SignalR WebSocket streaming |
| joblib | Online B2 | Regime model deserialization |
