```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║                       KELLY 7-LAYER SIZING PIPELINE                                      ║
║              Offline Block 8 (L1) → Online Block 4 (L2–L7) → contracts                   ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝

  SIDE INPUTS                         PIPELINE
  ═══════════                         ════════

  P3-D05 (EWMA states)          ┌───────────────────────────────────────────────────────────┐
  per [asset][regime][session]  ►│  L1: REGIME-CONDITIONAL KELLY (Offline B8, P3-PG-15)     │
                                 │                                                           │
  P3-D03 (trade outcomes)      ►│  SERVICE: offline_engine / kelly_updater worker            │
  pnl_per_contract updates       │  TRIGGER: trade_outcome event from broker adapter         │
                                 │  READS:  P3-D05 (QuestDB: ewma_states table)              │
                                 │          P3-D03 (QuestDB: trade_outcomes table)            │
                                 │          BOCPD cp_prob (Redis: bocpd:{asset} key)          │
                                 │  WRITES: P3-D12 (QuestDB: kelly_params table)              │
                                 │  MODULE: kelly_pipeline.py → update_regime_kelly()         │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
  P2-D07 (regime probs)         ┌───────────────────────────────────────────────────────────┐
  P(LOW_VOL), P(HIGH_VOL)      ►│  L2: BLENDED KELLY (Online B4, P3-PG-24)                 │
                                 │                                                           │
                                 │  SERVICE: online_engine / session_evaluator                │
                                 │  READS:  P3-D12 (QuestDB: kelly_params)                   │
                                 │          P2-D07 (Redis: regime_probs:{asset} hash)         │
                                 │  MODULE: kelly_pipeline.py → compute_blended_kelly()       │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
  P3-D12 (shrinkage factor)     ┌───────────────────────────────────────────────────────────┐
  s(n) from Offline B8         ►│  L3: PARAMETER UNCERTAINTY SHRINKAGE                     │
                                 │                                                           │
                                 │  SERVICE: online_engine (inline call in session_evaluator) │
                                 │  READS:  P3-D12.shrinkage_factor (QuestDB)                │
                                 │  MODULE: kelly_pipeline.py → apply_shrinkage()             │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
                                 ┌───────────────────────────────────────────────────────────┐
                                 │  L4: ROBUST KELLY FALLBACK                               │
                                 │                                                           │
                                 │  SERVICE: online_engine (inline)                          │
                                 │  READS:  P3-D05 EWMA moments (QuestDB)                   │
                                 │          regime_probs max check (Redis)                    │
                                 │  MODULE: kelly_pipeline.py → robust_kelly_check()          │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
  P3-D02 (AIM weights)          ┌───────────────────────────────────────────────────────────┐
  DMA inclusion probs           ►│  L5: AIM MODIFIER                                        │
                                 │                                                          │
                                 │  SERVICE: online_engine (inline)                         │
                                 │  READS:  P3-D01 (Redis: aim_modifiers:{asset} hash)      │
                                 │          -- fields: aim_01..aim_16 (16 AIMs individually)  │
                                 │          --   aim_01=VRP, aim_02=Skew, aim_03=GEX,         │
                                 │          --   aim_04=PreMkt, aim_05=LOB(DEF), aim_06=Cal,  │
                                 │          --   aim_07=COT, aim_08=Corr, aim_09=Mom,         │
                                 │          --   aim_10=CalEff, aim_11=RegWarn, aim_12=Cost,  │
                                 │          --   aim_13=Sens, aim_14=Exp, aim_15=VolQual,     │
                                 │          --   aim_16=HMM (session budget)                  │
                                 │          P3-D02 (QuestDB: meta_weights table)              │
                                 │  MODULE: aim_aggregator.py → compute_combined_modifier()   │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
  P3-D08 (TSM state)            ┌───────────────────────────────────────────────────────────┐
  account classification        ►│  L6: ACCOUNT-TYPE ADJUSTMENT                             │
                                 │                                                           │
                                 │  SERVICE: online_engine (inline)                          │
                                 │  READS:  P3-D08 (QuestDB: tsm_configs table)              │
                                 │          P3-D16 (QuestDB: user_profiles)                   │
                                 │  MODULE: kelly_pipeline.py → account_kelly_adjustment()    │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
  P3-D08 (TSM state)            ┌───────────────────────────────────────────────────────────┐
  MDD/MLL limits, margin        ►│  L7: TSM HARD CONSTRAINTS                                │
                                 │                                                           │
  P3-D23 (intraday state)      ►│  SERVICE: online_engine (inline)                          │
  daily loss used                │  READS:  P3-D08 (QuestDB: tsm_configs — MDD/MLL limits)  │
                                 │          P3-D23 (Redis: intraday:{account_id} — live DD)   │
                                 │          fee schedule (Redis: fees:{asset} key)             │
                                 │  MODULE: kelly_pipeline.py → compute_final_contracts()     │
                                 │          fee_resolver.py → get_round_trip_fee()             │
                                 │  WRITES: sizing result to session evaluation context        │
                                 └──────────────────────────┬────────────────────────────────┘
                                                            ▼
                                 ╔═══════════════════════════════════════════════════════════╗
                                 ║  OUTPUT: contracts per account (integer ≥ 0)              ║
                                 ╚═══════════════════════════════════════════════════════════╝
```

