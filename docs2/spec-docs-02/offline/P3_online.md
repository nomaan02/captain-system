```
╔════════════════════════════════════════════════════════════════════════════════════════════════╗
║                   CAPTAIN ONLINE — 9 BLOCKS + 5B + CIRCUIT BREAKER                            ║
║            Session-driven (NY/LON/APAC). Blocks 1-3 SHARED. Blocks 4-9 PER-USER.              ║
╚════════════════════════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  B1 PG-21: DATA INGESTION                                                                    │
│  SVC: online_engine / session_evaluator (Python daemon)                                      │
│  TRIGGER: session open event (cron: 09:30 NY, 08:00 LON, APAC)                              │
│  READS: P3-D00,D01,D02,D05,D08,D12(QuestDB). P2-D06,D07(QuestDB).                          │
│         Market data: price_feed, options_chain, vix_feed, cot_data, econ_calendar(Redis)      │
│  WRITES: features → Redis cache (TTL=session). P3-D17.data_quality_log(QuestDB)              │
│  MODULES: data_ingestion.py, data_moderator.py, aim_feature_compute.py                       │
└──────────────────────────┬───────────────────────────────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  B2 PG-22: REGIME PROBABILITY                                                                │
│  SVC: online_engine (inline in session_evaluator)                                            │
│  READS: P2-D07(QuestDB, joblib deserialized). features(Redis)                                │
│  WRITES: regime_probs → Redis hash regime_probs:{asset}                                      │
│  MODULE: regime_classifier.py. DEPS: xgboost, sklearn                                        │
└──────────────────────────┬───────────────────────────────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  B3 PG-23: AIM AGGREGATION                                                                   │
│  SVC: online_engine (inline)                                                                 │
│  READS: P3-D01(Redis: aim_modifiers:{asset}). P3-D02(QuestDB: meta_weights).                 │
│         P3-D26(QuestDB: hmm_states). features(Redis)                                         │
│  WRITES: combined_modifier → Redis. session_budget_wts → Redis. aim_breakdown → Redis         │
│  MODULES: aim_aggregator.py, moe_gating.py, hmm_inference.py                                │
│  AIM MODULES: aim_01_vrp.py .. aim_16_hmm.py (see doc 31 Backend for full list)              │
└──────────────────────────┬───────────────────────────────────────────────────────────────────┘
                           │ ════════════ SHARED → PER-USER ════════════
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  B4 PG-24: KELLY SIZING                                                                      │
│  SVC: online_engine / per-user worker (parallel)                                             │
│  READS: P3-D12(QuestDB: kelly_params). P3-D05(QuestDB: ewma). P3-D08(QuestDB: tsm).         │
│         P3-D16(QuestDB: user_profiles). combined_modifier(Redis). regime_probs(Redis).        │
│         P3-D23(Redis: intraday:{ac}). fees(Redis: fees:{asset})                              │
│  MODULE: kelly_pipeline.py → L2 blend, L3 shrink, L4 robust, L5 aim, L6 account, L7 caps    │
│          fee_resolver.py → get_round_trip_fee()                                               │
└──────────────────────────┬───────────────────────────────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  B5+5B PG-25/25B: TRADE SELECTION + QUALITY GATE                                             │
│  SVC: online_engine (inline). READS: Kelly output, P3-D26 HMM budget(QuestDB/Redis)          │
│  MODULE: trade_selector.py, quality_gate.py                                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  CIRCUIT BREAKER PG-27B:                                                                     │
│  SVC: online_engine (inline). READS: P3-D08(QuestDB: scaling tiers, MDD/MLL/E/L_halt).       │
│  P3-D23(Redis: intraday L_t, n_t). P3-D25(QuestDB: beta_b params). fees(Redis).              │
│  MODULE: circuit_breaker.py → L0 scaling, L1 preemptive, L2 budget, L3 beta_b, L4 sharpe    │
└──────────────────────────┬───────────────────────────────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  B6 PG-26: SVC: online_engine. W: Redis pub/sub signals:{uid}. MODULE: signal_emitter.py     │
│            anti_copy_jitter.py (multi-user). signal_distributor.py (PG-30 if >1 prop user)   │
│  B7 PG-27: SVC: online_engine (continuous). R: broker API fills. W: P3-D03,D23(QuestDB).     │
│            PUB: Redis "trades" → Offline workers. MODULE: position_monitor.py, fee_resolver   │
│  B8 PG-28: SVC: online_engine. R: Redis open_positions. W: notification_queue. MODULE: conc  │
│  B9 PG-29: SVC: online_engine (session-end). R: broker fills. W: P3-D17(QuestDB). MODULE: cap│
└──────────────────────────────────────────────────────────────────────────────────────────────┘

INFRASTRUCTURE: online_engine = Python daemon (systemd, event loop).
  Cache: Redis (TTL-managed features, real-time state). Storage: QuestDB (persistent).
  External: broker adapters (mTLS), price feeds (WebSocket/REST).
```

