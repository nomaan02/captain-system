# Captain System — QuestDB Data Map

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                              QUESTDB — 38 TABLES                                    ║
║                     PostgreSQL wire protocol on port 8812                            ║
║                     Web console on port 9000                                         ║
╚══════════════════════════════════════════════════════════════════════════════════════╝


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   ASSET & STRATEGY LAYER                                                            │
│   The "what we trade and how" foundation. Set during bootstrap, updated by          │
│   Offline when decay/expansion triggers.                                            │
│                                                                                     │
│   ┌─────────────────────────────────┐   ┌──────────────────────────────────────┐    │
│   │ D00  p3_d00_asset_universe      │   │ D07  p3_d07_correlation_model_states │    │
│   │ 2,087 rows                      │   │ 0 rows                              │    │
│   │                                 │   │                                      │    │
│   │ Master registry of all 17       │   │ Cross-asset correlation matrix.      │    │
│   │ assets (10 active, 7 elim).     │   │ Used by B5 trade selection to        │    │
│   │ Each row: asset_id, sessions,   │   │ limit correlated positions and by    │    │
│   │ locked_strategy (m,k pair),     │   │ B9 capacity evaluator for            │    │
│   │ point_value, tick_size,         │   │ effective-independent-asset count.    │    │
│   │ captain_status, contract specs. │   │                                      │    │
│   │                                 │   │ Writers: Offline B7 correlation      │    │
│   │ Writers: Bootstrap, Offline B6  │   │ Readers: Online B5, B9              │    │
│   │ Readers: ALL processes          │   └──────────────────────────────────────┘    │
│   └─────────────────────────────────┘                                               │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   AIM (ADAPTIVE INTELLIGENCE MODULE) LAYER                                          │
│   The learning brain. 6 AIM models per asset, each with lifecycle states,           │
│   meta-weights, drift detection, and diversity tracking.                             │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D01  p3_d01_aim_model_states │   │ D02  p3_d02_aim_meta_weights        │       │
│   │ 18,388 rows                  │   │ 180 rows                            │       │
│   │                              │   │                                      │       │
│   │ State of each AIM instance.  │   │ DMA (Dynamic Model Averaging)        │       │
│   │ Keyed by (aim_id, asset_id). │   │ weights per AIM per asset.           │       │
│   │ Stores: tier, accuracy,      │   │ Updated after every trade outcome.   │       │
│   │ installed date, lifecycle     │   │ Higher weight = more recent success. │       │
│   │ (ACTIVE/DECAYED/RETIRED),    │   │                                      │       │
│   │ feature config, model blob.  │   │ Writers: Offline B1 DMA update       │       │
│   │                              │   │ Readers: Online B3 AIM aggregation   │       │
│   │ Writers: Offline B1 lifecycle│   └──────────────────────────────────────┘       │
│   │ Readers: Online B3, Offline  │                                                  │
│   └──────────────────────────────┘   ┌──────────────────────────────────────┐       │
│                                      │ D04  p3_d04_decay_detector_states    │       │
│   ┌──────────────────────────────┐   │ 1,029 rows                          │       │
│   │ D26  p3_d26_hmm_opportunity  │   │                                      │       │
│   │ 0 rows                       │   │ BOCPD (Bayesian Online Changepoint   │       │
│   │                              │   │ Detection) state per asset.          │       │
│   │ Hidden Markov Model state    │   │ Detects when a strategy's edge       │       │
│   │ for opportunity scoring.     │   │ decays — triggers Level 3 circuit    │       │
│   │ Used by B3 AIM aggregation   │   │ breaker and eventual P1/P2 rerun.   │       │
│   │ to weight regime-specific    │   │                                      │       │
│   │ opportunity signals.         │   │ Writers: Offline B2 BOCPD            │       │
│   │                              │   │ Readers: Offline B1 lifecycle,       │       │
│   │ Writers: Offline B3          │   │          Online B5C circuit breaker  │       │
│   │ Readers: Online B3           │   └──────────────────────────────────────┘       │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   STATISTICAL / SIZING LAYER                                                        │
│   Trade statistics and Kelly criterion parameters that determine position sizes.    │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D05  p3_d05_ewma_states     │   │ D12  p3_d12_kelly_parameters         │       │
│   │ 120 rows                     │   │ 60 rows                             │       │
│   │                              │   │                                      │       │
│   │ EWMA (Exponentially Weighted │   │ Kelly criterion params per AIM per   │       │
│   │ Moving Average) of win rate, │   │ asset. f* (optimal fraction),        │       │
│   │ avg win, avg loss per AIM    │   │ shrinkage factor, robust Kelly,      │       │
│   │ per asset. Updated after     │   │ user ceiling. Determines how many    │       │
│   │ every trade outcome.         │   │ contracts each signal gets.          │       │
│   │                              │   │                                      │       │
│   │ Writers: Offline B5 EWMA     │   │ Writers: Offline B8 Kelly update     │       │
│   │ Readers: Online B4 Kelly,    │   │ Readers: Online B4 Kelly sizing      │       │
│   │          Offline B8 Kelly    │   └──────────────────────────────────────┘       │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   CIRCUIT BREAKER & RISK LAYER                                                      │
│   Multi-layer protection system. 7 layers from intraday stops to strategy decay.    │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D25  p3_d25_circuit_breaker  │   │ D23  p3_d23_circuit_breaker_intraday│       │
│   │ _params  ·  3 rows           │   │ 0 rows                              │       │
│   │                              │   │                                      │       │
│   │ Persistent CB parameters:    │   │ Intraday running totals:             │       │
│   │ beta_b (loss serial corr),   │   │ cumulative loss L(t), trade count    │       │
│   │ layer states, cold-start     │   │ N(t), per-model loss L_b, per-model │       │
│   │ flags. Seeded at bootstrap,  │   │ count N_b. Reset at session end.     │       │
│   │ updated after each trade.    │   │                                      │       │
│   │                              │   │ Writers: Online B7 position monitor  │       │
│   │ Writers: Offline B4, Online  │   │ Readers: Online B5C circuit breaker  │       │
│   │ Readers: Online B5C          │   └──────────────────────────────────────┘       │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   ACCOUNT & CAPITAL LAYER                                                           │
│   User accounts, capital allocation, and account lifecycle progression.              │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D16  p3_d16_user_capital     │   │ D08  p3_d08_tsm_state               │       │
│   │ _silos  ·  5 rows            │   │ 8 rows                              │       │
│   │                              │   │                                      │       │
│   │ Capital allocation per user: │   │ Trade State Machine config per       │       │
│   │ starting capital ($150K),    │   │ account. Position limits, fee        │       │
│   │ total capital, linked        │   │ schedule, max drawdown, trailing     │       │
│   │ accounts, max simultaneous   │   │ drawdown, daily loss limit.          │       │
│   │ positions, portfolio risk    │   │ Loaded from TopstepX at startup.     │       │
│   │ cap, Kelly ceiling, Telegram │   │                                      │       │
│   │ chat_id for notifications.   │   │ Writers: Command main.py (startup)   │       │
│   │                              │   │ Readers: Online B5 trade selection,  │       │
│   │ Writers: Bootstrap, Command  │   │          Online B7 position monitor  │       │
│   │ Readers: Online B5, B7, B9,  │   └──────────────────────────────────────┘       │
│   │          Command, Replay     │                                                  │
│   └──────────────────────────────┘   ┌──────────────────────────────────────┐       │
│                                      │ D28  p3_d28_account_lifecycle        │       │
│   ┌──────────────────────────────┐   │ 0 rows                              │       │
│   │ D15  p3_d15_user_session     │   │                                      │       │
│   │ _data  ·  1 row              │   │ EVAL -> XFA -> LIVE account          │       │
│   │                              │   │ progression tracking. Records        │       │
│   │ Active user sessions.        │   │ account transitions, qualifying      │       │
│   │ user_id, role, last_active.  │   │ trade counts, and activation dates.  │       │
│   │ Used to enumerate users for  │   │                                      │       │
│   │ multi-user signal routing.   │   │ Writers: Command account lifecycle   │       │
│   │                              │   │ Readers: Command orchestrator        │       │
│   │ Writers: Command main.py     │   └──────────────────────────────────────┘       │
│   │ Readers: Online orchestrator │                                                  │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   TRADE & OUTCOME LAYER                                                             │
│   The core feedback loop. Signals become trades, trades produce outcomes,            │
│   outcomes feed back into the learning layer above.                                  │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D03  p3_d03_trade_outcome    │   │ D06  p3_d06_injection_history        │       │
│   │ _log  ·  0 rows              │   │ 0 rows                              │       │
│   │                              │   │                                      │       │
│   │ Every completed trade:       │   │ Manual strategy injections (P1/P2    │       │
│   │ signal_id, asset, direction, │   │ reruns, parameter overrides).        │       │
│   │ entry/exit price, PnL,       │   │ Tracks what was changed, when,       │       │
│   │ regime, AIM scores, Kelly f, │   │ and by whom. Audit trail for         │       │
│   │ commission, duration.        │   │ any non-organic parameter changes.   │       │
│   │                              │   │                                      │       │
│   │ Writers: Online B7 (TP/SL)   │   │ Writers: Offline B6 auto-expansion   │       │
│   │ Readers: Offline (all learn) │   │ Readers: Offline B1 lifecycle        │       │
│   └──────────────────────────────┘   └──────────────────────────────────────┘       │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D06b p3_d06b_active          │   │ D11  p3_d11_pseudotrader_results     │       │
│   │ _transitions  ·  0 rows      │   │ 0 rows                              │       │
│   │                              │   │                                      │       │
│   │ In-flight strategy           │   │ Pseudotrader paper-trade results.    │       │
│   │ transitions (pending         │   │ Virtual execution of signals the     │       │
│   │ injection completions).      │   │ system generated but didn't take     │       │
│   │                              │   │ (circuit breaker blocked, or         │       │
│   │ Writers: Offline B6          │   │ parity-skipped). Used to validate    │       │
│   │ Readers: Offline B6          │   │ strategy without real money.         │       │
│   └──────────────────────────────┘   │                                      │       │
│                                      │ Writers: Offline B3 pseudotrader     │       │
│   ┌──────────────────────────────┐   │ Readers: Offline B8, Command reports │       │
│   │ D27  p3_d27_pseudotrader     │   └──────────────────────────────────────┘       │
│   │ _forecasts  ·  0 rows        │                                                  │
│   │                              │   ┌──────────────────────────────────────┐       │
│   │ Forward-looking pseudotrader │   │ D13  p3_d13_sensitivity_scan_results │       │
│   │ predictions before outcome   │   │ 0 rows                              │       │
│   │ is known. Compared against   │   │                                      │       │
│   │ D11 actuals to measure       │   │ What-if analysis results from        │       │
│   │ forecasting accuracy.        │   │ parameter sensitivity scans.         │       │
│   │                              │   │ Shows how PnL changes if m, k,       │       │
│   │ Writers: Offline B3          │   │ Kelly, or CB params are tweaked.     │       │
│   │ Readers: Offline diagnostics │   │                                      │       │
│   └──────────────────────────────┘   │ Writers: Offline B9 diagnostic       │       │
│                                      │ Readers: Command reports             │       │
│                                      └──────────────────────────────────────┘       │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   MARKET DATA LAYER                                                                 │
│   Historical and real-time market data stored for regime detection, replay,          │
│   and VIX-based alerting.                                                            │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D30  p3_d30_daily_ohlcv     │   │ D29  p3_d29_opening_volumes          │       │
│   │ 2,829 rows                   │   │ 240 rows                            │       │
│   │                              │   │                                      │       │
│   │ Daily OHLCV bars per asset.  │   │ Volume during opening range window   │       │
│   │ Used for regime detection    │   │ per asset per session. Measures      │       │
│   │ (B2), AIM features, and      │   │ market participation at open.        │       │
│   │ replay backtesting.          │   │                                      │       │
│   │                              │   │ Writers: Online B1 data ingestion    │       │
│   │ Writers: Online B1           │   │ Readers: Online B2, Replay           │       │
│   │ Readers: Online B2, Offline, │   └──────────────────────────────────────┘       │
│   │          Replay engine       │                                                  │
│   └──────────────────────────────┘   ┌──────────────────────────────────────┐       │
│                                      │ D33  p3_d33_opening_volatility       │       │
│   ┌──────────────────────────────┐   │ 240 rows                            │       │
│   │ D31  p3_d31_implied_vol     │   │                                      │       │
│   │ 122 rows                     │   │ Realized volatility during the       │       │
│   │                              │   │ opening range window. Combined       │       │
│   │ Implied volatility surface   │   │ with D31 IV for regime classifier    │       │
│   │ data (IV term structure).    │   │ features.                            │       │
│   │ AIM feature for regime       │   │                                      │       │
│   │ classification.              │   │ Writers: Online B1 data ingestion    │       │
│   │                              │   │ Readers: Online B1 features, B2     │       │
│   │ Writers: Online B1 (AIM)     │   └──────────────────────────────────────┘       │
│   │ Readers: Online B2           │                                                  │
│   └──────────────────────────────┘   ┌──────────────────────────────────────┐       │
│                                      │ p3_spread_history                     │       │
│   ┌──────────────────────────────┐   │ 628 rows                            │       │
│   │ D32  p3_d32_options_skew    │   │                                      │       │
│   │ 81 rows                      │   │ Bid-ask spread history per asset.    │       │
│   │                              │   │ Used by B5 trade selection for       │       │
│   │ Options skew data.           │   │ liquidity filtering — wide spreads   │       │
│   │ AIM feature for directional  │   │ indicate thin markets.              │       │
│   │ bias detection.              │   │                                      │       │
│   │                              │   │ Writers: Online B1 data ingestion    │       │
│   │ Writers: Online B1 (AIM)     │   │ Readers: Online B5                  │       │
│   │ Readers: Online B2           │   └──────────────────────────────────────┘       │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   SYSTEM OPERATIONS LAYER                                                           │
│   Monitoring, notifications, health, and operational state.                          │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D17  p3_d17_system_monitor   │   │ D14  p3_d14_api_connection_states    │       │
│   │ _state  ·  113 rows          │   │ 14,443 rows                         │       │
│   │                              │   │                                      │       │
│   │ Key-value system params:     │   │ TopstepX API connection log.         │       │
│   │ session logs, capacity       │   │ Auth attempts, token refreshes,      │       │
│   │ reports, manual halt flag,   │   │ WebSocket connects/disconnects,      │       │
│   │ default commission, system   │   │ rate limit events. High-volume       │       │
│   │ feature flags.               │   │ table (14K+ rows) for debugging      │       │
│   │                              │   │ connectivity issues.                 │       │
│   │ Writers: ALL processes       │   │                                      │       │
│   │ Readers: ALL processes       │   │ Writers: Command B3 API adapter      │       │
│   └──────────────────────────────┘   │ Readers: Command B2 GUI, System page │       │
│                                      └──────────────────────────────────────┘       │
│   ┌──────────────────────────────┐                                                  │
│   │ D10  p3_d10_notification_log │   ┌──────────────────────────────────────┐       │
│   │ 52 rows                      │   │ D22  p3_d22_system_health_diagnostic │       │
│   │                              │   │ 6 rows                              │       │
│   │ Every notification sent:     │   │                                      │       │
│   │ Telegram messages, alerts,   │   │ Periodic health snapshots:           │       │
│   │ trade confirmations. With    │   │ container status, DB connectivity,   │       │
│   │ priority level, delivery     │   │ Redis status, memory usage,          │       │
│   │ status, retry count.         │   │ process uptime.                      │       │
│   │                              │   │                                      │       │
│   │ Writers: Command B7 notif    │   │ Writers: Command B5 health           │       │
│   │ Readers: Command GUI, logs   │   │ Readers: Command GUI, /health API    │       │
│   └──────────────────────────────┘   └──────────────────────────────────────┘       │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D21  p3_d21_incident_log    │   │ D18  p3_d18_version_history          │       │
│   │ 2 rows                       │   │ 850 rows                            │       │
│   │                              │   │                                      │       │
│   │ Major system incidents:      │   │ Parameter version tracking. Every    │       │
│   │ circuit breaker trips,       │   │ time a D-table row is updated,       │       │
│   │ connectivity outages,        │   │ the old value is logged here.        │       │
│   │ manual interventions.        │   │ Full audit trail for rollback.       │       │
│   │                              │   │                                      │       │
│   │ Writers: ALL processes       │   │ Writers: ALL processes               │       │
│   │ Readers: Command reports     │   │ Readers: Diagnostics, reports        │       │
│   └──────────────────────────────┘   └──────────────────────────────────────┘       │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ D19  p3_d19_reconciliation   │   │ D09  p3_d09_report_archive           │       │
│   │ _log  ·  0 rows              │   │ 0 rows                              │       │
│   │                              │   │                                      │       │
│   │ Position/PnL reconciliation  │   │ Generated report snapshots (daily    │       │
│   │ between Captain's internal   │   │ summaries, weekly reports, custom    │       │
│   │ state and TopstepX API.      │   │ report runs). Stored as JSON blobs.  │       │
│   │ Flags any divergence.        │   │                                      │       │
│   │                              │   │ Writers: Command B6 report gen       │       │
│   │ Writers: Command B4 recon    │   │ Readers: Command GUI reports page    │       │
│   │ Readers: Command reports     │   └──────────────────────────────────────┘       │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
│   ┌──────────────────────────────┐                                                  │
│   │ p3_session_event_log         │                                                  │
│   │ 124 rows                     │                                                  │
│   │                              │                                                  │
│   │ Structured event log per     │                                                  │
│   │ trading session: block       │                                                  │
│   │ timings, signal counts,      │                                                  │
│   │ capacity results, errors.    │                                                  │
│   │ The primary debugging table. │                                                  │
│   │                              │                                                  │
│   │ Writers: ALL processes       │                                                  │
│   │ Readers: Command GUI, replay │                                                  │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│   REPLAY & OFFLINE JOBS LAYER                                                       │
│   Session replay infrastructure and async job processing.                            │
│                                                                                     │
│   ┌──────────────────────────────┐   ┌──────────────────────────────────────┐       │
│   │ p3_replay_results            │   │ p3_replay_presets                     │       │
│   │ 2 rows                       │   │ 0 rows                              │       │
│   │                              │   │                                      │       │
│   │ Saved replay session output: │   │ Saved replay configurations:         │       │
│   │ signals generated, trades    │   │ date ranges, assets, parameters,     │       │
│   │ simulated, PnL curves,       │   │ CB settings. Users can load a        │       │
│   │ comparison metrics.          │   │ preset instead of configuring        │       │
│   │                              │   │ each replay from scratch.            │       │
│   │ Writers: Command B11 replay  │   │                                      │       │
│   │ Readers: Command GUI replay  │   │ Writers: Command replay API          │       │
│   └──────────────────────────────┘   │ Readers: Command GUI replay page     │       │
│                                      └──────────────────────────────────────┘       │
│   ┌──────────────────────────────┐                                                  │
│   │ p3_offline_job_queue         │                                                  │
│   │ 0 rows                       │                                                  │
│   │                              │                                                  │
│   │ Async job queue for Offline  │                                                  │
│   │ process. Trade outcomes,     │                                                  │
│   │ retraining requests, decay   │                                                  │
│   │ scans queued here via Redis, │                                                  │
│   │ persisted for crash recovery.│                                                  │
│   │                              │                                                  │
│   │ Writers: Command orchestrator│                                                  │
│   │ Readers: Offline orchestrator│                                                  │
│   └──────────────────────────────┘                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘


╔══════════════════════════════════════════════════════════════════════════════════════╗
║                           DATA FLOW SUMMARY                                         ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║   ONLINE writes to:  D00, D03, D14, D17, D23, D29, D30, D31, D32, D33, spreads     ║
║   ONLINE reads from: D00, D01, D02, D04, D05, D07, D08, D12, D16, D17, D25, D26    ║
║                                                                                      ║
║   OFFLINE writes to: D00, D01, D02, D04, D05, D06, D06b, D07, D11, D12, D25, D27   ║
║   OFFLINE reads from: D00, D01, D02, D03, D04, D05, D12                             ║
║                                                                                      ║
║   COMMAND writes to: D08, D09, D10, D14, D15, D16, D17, D18, D19, D21, D22, D28    ║
║   COMMAND reads from: D00, D01, D03, D08, D10, D14, D16, D17, session_event_log     ║
║                                                                                      ║
║   BOOTSTRAP writes to: D00, D01, D02, D05, D12, D15, D16, D17, D25                 ║
║                                                                                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║   Tables with data:  26 (populated)     Tables empty:  12 (awaiting first trades)   ║
║   Total rows:        ~43,000            Heaviest:  D01 (18K), D14 (14K)             ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
```
