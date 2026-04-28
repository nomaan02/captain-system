```
╔════════════════════════════════════════════════════════════════════════════════════════════════╗
║                    CAPTAIN OFFLINE — 9 BLOCKS (Strategic Brain)                                ║
║       Event-driven + Scheduled. Learns from trade outcomes. Updates all P3-D* stores.          ║
╚════════════════════════════════════════════════════════════════════════════════════════════════╝

  TRIGGER: Redis pub/sub "trades" event     TRIGGER: systemd cron (weekly/monthly)
           │                                         │
           ▼                                         ▼

│  BLOCK 1: AIM MODEL TRAINING & MANAGEMENT                                                    │
│                                                                                              │
│  SVC: offline_worker (Python daemon, event-driven + cron)                                    │
│  PG-01: R: P3-D01(QuestDB). W: P3-D01(QuestDB). MODULE: aim_lifecycle.py                    │
│  PG-01C: R: P3-D03(QuestDB). W: P3-D26(QuestDB). MODULE: hmm_trainer.py. DEPS: hmmlearn    │
│  PG-02: R: P3-D03,D02,D05(QuestDB). W: P3-D02(QuestDB). MODULE: dma_engine.py              │
│  PG-03: R/W: P3-D01,D02(QuestDB). MODULE: dma_engine.py → diversity_check(). CRON: weekly   │
│  PG-04: R: aim features(QuestDB). R: AutoEncoder models(disk: models/ae_*.pt).              │
│          R/W: ADWIN state(Redis: adwin:{aim_id}). W: P3-D02(QuestDB). MODULE: drift_det.py  │
│  SNAPSHOT: P3-D18(QuestDB) before every write. MODULE: version_manager.py                    │

                           ▼

│  BLOCK 2: STRATEGY DECAY DETECTION                                                           │
│                                                                                              │
│  SVC: offline_worker (event: trade outcome)                                                  │
│  PG-05: R: P3-D03(QuestDB). R/W: P3-D04.bocpd(QuestDB). MODULE: bocpd.py. DEPS: scipy.stats│
│  PG-06: R: P3-D03(QuestDB). R/W: P3-D04.cusum(QuestDB). MODULE: cusum.py                   │
│  PG-07: R: P3-D03(QuestDB). W: P3-D04.cusum.limits(QuestDB). CRON: quarterly                │
│  PG-08: W: P3-D12.sizing_override(QuestDB). W: P3-D00.captain_status(QuestDB).              │
│          PUB: Redis notification_queue. MODULE: decay_response.py                             │

                           ▼

│  BLOCK 3: PSEUDOTRADER                                                                       │
│  SVC: offline_worker. R: P3-D03,D22(QuestDB). W: P3-D11(QuestDB). MODULE: pseudotrader.py   │
│  PG-09B: MODULE: cb_replay.py. PG-09C: MODULE: cb_grid.py                                   │

│  BLOCK 4: INJECTION COMPARISON                                                               │
│  SVC: offline_worker. R: P2-D06,D07(QuestDB). W: P3-D06(QuestDB). MODULE: injection.py      │
│  PG-11: W: P3-D00(QuestDB). MODULE: transition.py                                           │

│  BLOCK 5: SENSITIVITY (AIM-13)                                                               │
│  SVC: offline_worker. CRON: monthly. R: D22(QuestDB). W: P3-D13(QuestDB).                   │
│  MODULE: sensitivity.py. DEPS: sklearn (isotonic), kneed                                     │

│  BLOCK 6: AUTO-EXPANSION (AIM-14)                                                            │
│  SVC: offline_worker. TRIGGER: L3 decay. MODULE: auto_expand.py. DEPS: deap (GA)            │

│  BLOCK 7: TSM SIMULATION                                                                     │
│  SVC: offline_worker. R: P3-D08,D03,D12(QuestDB). W: P3-D08(QuestDB).                       │
│  MODULE: tsm_simulator.py. CRON: after each trade + on TSM change                            │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  BLOCK 8: KELLY UPDATES                                                                      │
│  SVC: offline_worker. TRIGGER: trade outcome.                                                │
│  PG-15: R: P3-D03,D05(QuestDB). R: BOCPD cp(Redis). W: P3-D05,D12(QuestDB).                │
│          MODULE: kelly_ewma.py                                                                │
│  PG-16C: R: P3-D03(QuestDB). W: P3-D25(QuestDB). MODULE: beta_b_estimator.py               │
│  CHECKPOINT: SQLite WAL P3-D20 after each update                                             │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  BLOCK 9: SYSTEM HEALTH                                                                      │
│  SVC: offline_worker. CRON: weekly (D1-D7), monthly (D5 deep), event (D8 on resolve).        │
│  R: P2-D06,D07(QuestDB). R: P3-D00,D01,D02,D03,D04,D05,D06,D13,D17(QuestDB).               │
│  W: P3-D22(QuestDB). MODULE: system_health.py                                                │
└──────────────────────────────────────────────────────────────────────────────────────────────┘

INFRASTRUCTURE: offline_worker = Python daemon (systemd). Storage: QuestDB (all P3-D*).
Cache: Redis (ADWIN state, BOCPD cp for alpha). Models: disk (models/*.pt).
```

