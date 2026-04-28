```

╔════════════════════════════════════════════════════════════════════════════════════════════╗

║                     DMA / MoE META-LEARNING PIPELINE                                     ║

║         16 AIMs → DMA (Offline B1) → MoE Gating (Online B3) → Kelly L5                  ║

╚════════════════════════════════════════════════════════════════════════════════════════════╝

  
  

┌───────────────────────────────────────────────────────────────────────────────────────────┐

│  16 AUXILIARY INTELLIGENCE MODULES (AIMs)                                                 │

│                                                                                           │

│  SERVICE: aim_compute_workers (one per AIM or batched)                                    │

│  READS:  market data feeds (Redis pub/sub: market:{asset}),                               │

│          AIM-specific feature stores (QuestDB: aim_features_{N})                          │

│  WRITES: P3-D01 (Redis hash: aim_modifiers:{asset} field aim_{N})                         │

│  MODULES BY SEED TYPE:                                                                    │

│    OPTIONS:        aim_01_vrp.py, aim_02_skew.py, aim_03_gex.py                           │

│    MICROSTRUCTURE: aim_04_premarket.py, aim_05_orderbook.py (DEFERRED),                   │

│                    aim_15_volume_quality.py                                                │

│    MACRO/EVENT:    aim_06_calendar.py, aim_07_cot.py                                      │

│    CROSS-ASSET:    aim_08_correlation.py, aim_09_momentum.py                              │

│    TEMPORAL:       aim_10_calendar_effect.py, aim_11_regime_warning.py                    │

│    INTERNAL:       aim_12_cost_estimator.py, aim_13_sensitivity.py,                       │

│                    aim_14_auto_expansion.py                                                │

│    OPPORTUNITY:    aim_16_hmm.py (session-level, not per-asset)                           │

└──────────────┬──────────────────────────────────────────────────────────┬──────────────────┘

               │ modifiers per asset                                     │ modifiers per asset

               ▼                                                         ▼

  

═══════════════════════════════════════   ═══════════════════════════════════════════════════

 OFFLINE PATH (after each trade)          ONLINE PATH (each session evaluation)

═══════════════════════════════════════   ═══════════════════════════════════════════════════

  

┌─────────────────────────────────────┐

│  TRADE OUTCOMES (P3-D03)            │

│  STORE: QuestDB table trade_outcomes│

│  TRIGGER: broker adapter event →    │

│           Redis pub/sub: trades     │

└──────────────┬──────────────────────┘

               │

               ▼

┌─────────────────────────────────────┐   ┌─────────────────────────────────────────────────┐

│  DMA UPDATE (Offline B1, P3-PG-02) │   │  MoE GATING (Online B3, P3-PG-23)              │

│                                     │   │                                                 │

│  SERVICE: offline_engine /          │   │  SERVICE: online_engine / session_evaluator      │

│           dma_update_worker         │   │  TRIGGER: session window open event              │

│  TRIGGER: trade outcome event       │   │  READS:  P3-D01 (Redis: aim_modifiers:{asset})  │

│  READS:  P3-D01 snapshot at trade   │   │          P3-D02 (QuestDB: meta_weights table)   │

│          time (Redis or QuestDB     │   │  MODULE: aim_aggregator.py →                    │

│          point-in-time query)       │   │          compute_combined_modifier()             │

│          P3-D05 (QuestDB: ewma)     │   │  OUTPUT: combined_modifier → passed to          │

│  WRITES: P3-D02 (QuestDB:          │   │          kelly_pipeline.py (L5 inline)           │

│          meta_weights table —       │   └─────────────────────────┬───────────────────────┘

│          inclusion_prob, flag)      │                             │

│  MODULE: dma_engine.py →           │                             │

│          update_dma(),              │   ─ ─ P3-D02 (QuestDB) ─ ─►│

│          mag_weighted_likelihood()  │                             ▼

└──────────────┬──────────────────────┘  ┌──────────────────────────────────────────────────┐

               │                         │  ► KELLY LAYER 5 (Online B4)                     │

               │                         │  SERVICE: online_engine / session_evaluator       │

               │                         │  MODULE: kelly_pipeline.py → apply_aim_modifier() │

               │                         └──────────────────────────────────────────────────┘

               │

               ▼

┌─────────────────────────────────────┐

│  HDWM DIVERSITY CHECK              │

│  (Offline B1, P3-PG-03, weekly)    │

│                                     │

│  SERVICE: offline_engine /          │

│           weekly_maintenance cron   │

│  READS:  P3-D01 status (QuestDB)   │

│          P3-D02 weights (QuestDB)   │

│  WRITES: P3-D01, P3-D02 (QuestDB)  │

│  MODULE: dma_engine.py →           │

│          diversity_check()          │

└─────────────────────────────────────┘

  

               │ (same offline cycle)

               ▼

┌─────────────────────────────────────┐

│  DRIFT DETECTION (ADWIN)           │

│  (Offline B1, P3-PG-04, daily)     │

│                                     │

│  SERVICE: offline_engine /          │

│           daily_drift_check cron    │

│  READS:  AIM feature vectors       │

│          (QuestDB: aim_features)    │

│          AutoEncoder models         │

│          (disk: models/ae_{N}.pt)   │

│          ADWIN state (Redis:        │

│          adwin:{aim_id})            │

│  WRITES: P3-D02 weights (QuestDB)  │

│          retrain flag (Redis)       │

│  MODULE: drift_detector.py →       │

│          check_aim_drift()          │

└─────────────────────────────────────┘

  

               │ feedback loop

               ▼

┌─────────────────────────────────────┐

│  TRADE OUTCOMES FEEDBACK (P3-D03)  │

│                                     │

│  EVENT: broker adapter writes       │

│         next trade → QuestDB        │

│  PUB:   Redis pub/sub: trades       │

│  DMA worker picks up event →        │

│  cycle repeats.                     │

└────────────── ↺ back to DMA ────────┘

```

## References

- [[31_AIM_Individual_Specifications|AIM Specifications (doc 31)]]
- [[22_HMM_Opportunity_Regime|AIM-16 HMM (doc 22)]]
- [[24_P3_Dataset_Schemas|P3-D01 (AIM Modifiers)]]
- [[24_P3_Dataset_Schemas|P3-D02 (Meta Weights)]]
- [[24_P3_Dataset_Schemas|P3-D03 (Trade Outcomes)]]
- [[24_P3_Dataset_Schemas|P3-D05 (EWMA States)]]
- [[32_P3_Offline_Full_Pseudocode|PG-02 (DMA Update)]]
- [[32_P3_Offline_Full_Pseudocode|PG-03 (HDWM Diversity Check)]]
- [[32_P3_Offline_Full_Pseudocode|PG-04 (Drift Detection)]]
- [[33_P3_Online_Full_Pseudocode|PG-23 (MoE Gating)]]
- [[System 1/Backend/P3 Offline.canvas|P3 Offline]]
- [[System 1/Backend/P3 Online.canvas|P3 Online]]