```
╔════════════════════════════════════════════════════════════════════════════════════════════════╗
║                    AIM SYSTEM — 16 INDIVIDUAL MODULES BY SEED TYPE                            ║
║       Each AIM: data source → internal model → modifier ∈ [0.5, 1.5] → DMA/MoE → Kelly       ║
╚════════════════════════════════════════════════════════════════════════════════════════════════╝

  ┌──── OPTIONS ───────────────────────────────────────────────────────────────────────────────┐
  │ AIM-01: MODULE: aim_01_vrp.py                                                               │
  │   READS: options_chain adapter(Redis: iv_atm:{asset}), P2-D01(QuestDB: rv)                 │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_01)                                │
  │ AIM-02: MODULE: aim_02_skew.py                                                              │
  │   READS: options_chain adapter(Redis: pcr:{asset}, put_skew:{asset})                       │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_02)                                │
  │ AIM-03: MODULE: aim_03_gex.py. DEPS: scipy (BSM gamma computation)                        │
  │   READS: options_chain adapter(Redis: option_chain:{asset})                                 │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_03)                                │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──── MICROSTRUCTURE ────────────────────────────────────────────────────────────────────────┐
  │ AIM-04: MODULE: aim_04_premarket.py                                                         │
  │   READS: vix_feed(Redis: vix_close, vxv_close), price_feed(Redis: overnight_return)        │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_04)                                │
  │ AIM-05: MODULE: aim_05_orderbook.py (DEFERRED stub — returns 1.0)                          │
  │   READS: N/A. WRITES: P3-D01 field aim_05 = 1.0                                           │
  │ AIM-15: MODULE: aim_15_volume_quality.py                                                    │
  │   READS: price_feed(Redis: volume_or:{asset}), QuestDB(avg_volume_20d)                     │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_15)                                │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──── MACRO / EVENT ─────────────────────────────────────────────────────────────────────────┐
  │ AIM-06: MODULE: aim_06_calendar.py                                                          │
  │   READS: economic_calendar adapter(disk: /captain/data/economic_calendar.json)              │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_06)                                │
  │ AIM-07: MODULE: aim_07_cot.py                                                               │
  │   READS: cot_data adapter(disk: /captain/data/cot_weekly/). Weekly download (3d lag).       │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_07)                                │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──── CROSS-ASSET ───────────────────────────────────────────────────────────────────────────┐
  │ AIM-08: MODULE: aim_08_correlation.py. DEPS: arch (DCC-GARCH)                              │
  │   READS: cross_asset_prices(Redis: prices:{ES,NQ,CL,DXY,10Y,USDCAD})                     │
  │   R/W: P3-D07(QuestDB: correlation_model_states)                                           │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_08)                                │
  │ AIM-09: MODULE: aim_09_momentum.py                                                         │
  │   READS: cross_asset_prices(Redis). WRITES: P3-D01 field aim_09                            │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──── TEMPORAL ──────────────────────────────────────────────────────────────────────────────┐
  │ AIM-10: MODULE: aim_10_calendar_effect.py                                                   │
  │   READS: system calendar (internal), price_feed(Redis), P3-D00(QuestDB: OPEX dates)        │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_10)                                │
  │ AIM-11: MODULE: aim_11_regime_warning.py                                                    │
  │   READS: vix_feed(Redis), macro_data(Redis: credit_spreads), P2 regime state(QuestDB)      │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_11)                                │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──── INTERNAL ──────────────────────────────────────────────────────────────────────────────┐
  │ AIM-12: MODULE: aim_12_cost_estimator.py                                                    │
  │   READS: P3-D03(QuestDB: execution_history), price_feed(Redis: live_spread)                │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_12)                                │
  │ AIM-13: MODULE: aim_13_sensitivity.py                                                       │
  │   READS: P3-D13(QuestDB: sensitivity_scan_results)                                         │
  │   WRITES: P3-D01(Redis: aim_modifiers:{asset} field aim_13)                                │
  │ AIM-14: MODULE: aim_14_auto_expansion.py                                                    │
  │   READS: P3-D04(QuestDB: decay_events). Not a modifier — returns 1.0.                     │
  │   TRIGGER: Level 3 decay → Offline Block 6 (PG-13)                                         │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

  ┌──── OPPORTUNITY ───────────────────────────────────────────────────────────────────────────┐
  │ AIM-16: MODULE: aim_16_hmm.py. DEPS: hmmlearn (GaussianHMM)                               │
  │   TRAIN (Offline PG-01C): R: P3-D03(QuestDB). W: P3-D26(QuestDB: hmm_states)              │
  │   INFER (Online B3): R: P3-D26(QuestDB). W: Redis(session_budget_weights)                  │
  │   Not per-asset — produces session-level budget allocation weights                          │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

                    │ all 16 modifier outputs via Redis hash aim_modifiers:{asset}
                    ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────────┐
  │  DMA/MoE AGGREGATION                                                                       │
  │  SVC: offline_worker (DMA update after trade). MODULE: dma_engine.py                       │
  │    R: P3-D01 snapshot(QuestDB PIT query). R/W: P3-D02(QuestDB: meta_weights)               │
  │  SVC: online_engine (MoE gating per session). MODULE: aim_aggregator.py, moe_gating.py     │
  │    R: P3-D01(Redis). R: P3-D02(QuestDB). W: Redis(combined_modifier:{asset})              │
  │  SVC: offline_worker (HDWM weekly). MODULE: dma_engine.py → diversity_check()              │
  │    R/W: P3-D01,D02(QuestDB)                                                                │
  │  SVC: offline_worker (drift daily). MODULE: drift_detector.py                               │
  │    R: aim features(QuestDB). R: models/ae_*.pt(disk). R/W: ADWIN(Redis). W: D02(QuestDB)  │
  └────────────────────────────────────────────────────────────────────────────────────────────┘

INFRASTRUCTURE: AIM modules run inside online_engine (feature compute) and offline_worker
  (training, DMA update). Each AIM's modifier cached in Redis hash with TTL=session.
  Training models stored on disk (models/aim_*.pt). Feature data from Redis (real-time)
  and QuestDB (historical). AutoEncoder models for drift: models/ae_01.pt .. ae_15.pt.
```


