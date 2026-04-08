# MOST Complete System Reference

> Comprehensive documentation of the MOST (Market Open Short-Term) trading system.
> Auto-generated from 1,854 observations across 414 development sessions (March 16-24, 2026).
> Synthesized by Claude from claude-mem's persistent memory database.

---

## Table of Contents

- [0. Executive Summary](#0-executive-summary)
- [1. Program 1 -- Feature Screening Pipeline](#1-program-1--feature-screening-pipeline)
- [2. Program 2 -- Regime Detection & Strategy Lock](#2-program-2--regime-detection--strategy-lock)
- [3. V3 Amendments & Completion Validation](#3-v3-amendments--completion-validation)
- [4. Infrastructure -- Docker, QuestDB, Redis](#4-infrastructure--docker-questdb-redis)
- [5. Captain Offline -- Strategic Brain](#5-captain-offline--strategic-brain)
- [6. Captain Online -- Signal Engine](#6-captain-online--signal-engine)
- [7. Captain Command -- Linking Layer](#7-captain-command--linking-layer)
- [8. Topstep Integration](#8-topstep-integration)
- [9. Local Backtester & Multi-Asset Screening](#9-local-backtester--multi-asset-screening)
- [10. Deployment, Safety & Stability](#10-deployment-safety--stability)

---

## 0. Executive Summary

### What Is MOST?

MOST (Market Open Short-Term) is an Opening Range Breakout (ORB) day-trading strategy targeting ES E-mini S&P 500 futures (and potentially 10 other futures assets). The system identifies the opening price range during the first minutes of a trading session, then enters directional trades when price breaks above or below that range, with machine-learning-driven feature selection determining when conditions favor breakout success.

### The Three-Program Pipeline

The MOST system was built through a rigorous three-program pipeline, each program feeding into the next:

**Program 1 (Feature Screening)** subjected 95,880 candidate model variants across 5 tiers to a multi-stage statistical attrition pipeline across 17 futures assets. The pipeline applied B2B Kendall tau correlation filtering, B3 control model hurdle rates, B4 gated model validation, and B5 OO-weighted scoring with constrained scoring rules. Result: 11,614 combined survivors across 11 assets, with each asset locking a unique (m, k) strategy pair. Top performers include M2K (OO=0.925), ZN (OO=0.906), and MGC (OO=0.889). Six assets (6J, M6A, M6B, M6E, MCL, SIL -- all currency and commodity futures) failed to produce any survivor at any pipeline stage.

**Program 2 (Regime Detection)** took all 11,614 P1 survivors and tested whether market regime conditioning could improve strategy selection per asset. The system computed daily volatility regimes via the Pettersson EWMA method, tested strategy-regime correlation via Kendall tau-b with BH-FDR correction, and trained XGBoost classifiers for regime prediction. Result: all 11 assets locked to REGIME_NEUTRAL (no statistically significant regime-strategy correlation after FDR correction at q=0.10), meaning all strategies run unconditionally. Each asset received a unique locked (m, k) pair via composite scoring `CS = OO × ln(N_total)`. Top P2 performers: MGC (CS=5.66, OO=0.889), ZN (CS=5.65, OO=0.906), ES (CS=5.39, OO=0.883).

**Program 3 (Captain Function)** is the production trading system -- a continuous 24/7 operation implemented as 3 independent Docker processes (Captain Offline, Captain Online, Captain Command) sharing QuestDB and Redis, comprising 28 functional blocks plus 3 orchestrators and 29 QuestDB tables. Captain Offline handles model retraining, decay detection, Kelly criterion sizing, and AIM (Adaptive Intelligence Module) lifecycle management. Captain Online runs the real-time signal pipeline from market data ingestion through regime detection, AIM inference, position sizing, and signal output. Captain Command provides the linking layer with core routing, GUI data serving, Topstep API integration, trade execution, and system monitoring.

### Topstep Integration

The system integrates with TopstepX (ProjectX) for funded futures trading accounts, supporting the full EVAL to XFA (Express Funded Account) to LIVE account lifecycle. The integration includes a REST client (18 endpoints), WebSocket streaming for real-time market data and order updates, a contract resolver mapping 10 asset symbols to Topstep contract IDs, and account lifecycle management with fee-aware payout calculations. A critical discovery during development: TopstepX Terms of Service Section 28 prohibits VPS-based trading, requiring local deployment on personal devices rather than cloud servers.

### V3 Amendments and Completion Validation

Isaac's V3 amendment package (March 2026) introduced 55 specification files with significant enhancements: a 7-layer circuit breaker system, HMM opportunity-regime session allocation, isotonic regression refactored to continuous returns, tier-preserving payout calculations, and constrained scoring mode for P1. A comprehensive completion validation process resolved 87 spec-to-code discrepancies across the full system, tracked in `CHANGE_TRACKER.md`.

### Key Numbers

| Metric | Value |
|--------|-------|
| Model variants screened (P1) | 95,880 across Tiers 2-5 |
| P1 combined survivors | 11,614 across 11 assets |
| Assets screened | 17 (11 survivors, 6 failed) |
| Regime result | REGIME_NEUTRAL (all assets) |
| Captain processes | 3 (Offline, Online, Command) |
| Functional blocks | 28 + 3 orchestrators |
| QuestDB tables | 29 |
| Redis pub/sub channels | 5 |
| Spec-to-code discrepancies resolved | 87 |
| V3 amendment files | 55 |
| Security vulnerabilities fixed | 12 |
| Circuit breaker layers | 7 |
| Topstep API endpoints integrated | 18 |
| Development sessions tracked | 414 |
| Total observations recorded | 1,854 |

### Current State (March 24, 2026)

The system generated its first 3 real trading signals on March 24, 2026, marking the transition from development to pre-production validation. All 28 blocks are implemented, Docker Compose orchestration is configured for 6 containers (3 Captain processes + QuestDB + Redis + nginx), and the GUI displays real-time signal data via WebSocket. Deployment is planned for local execution on personal devices (due to the Topstep VPS prohibition), with the pre-deployment checklist and safety validation as the final remaining gates before live trading.


---

## 1. Program 1 -- Feature Screening Pipeline

### Spec Reference

The P1 pipeline was built from the following specification documents:

- **Primary spec:** `docs/completion-validation-docs/Step 1 - Original Specs/01_Program1.md` — Isaac's 116-page specification defining the complete attrition pipeline, statistical test batteries, and OO aggregation methodology.
- **Consolidated configuration:** `docs/completion-validation-docs/01_START_HERE_P1_Consolidated_Config.md` — Single source of truth for all pipeline parameters, resolving every TBD value from the original spec: block thresholds, exit grids, sample periods, asset configurations, and input file requirements.
- **V3 amendments (P1-specific):** `docs/completion-validation-docs/Step_2-V3_Updates/11_Nomaan_Edits_P1.md` — Isaac's March 2026 amendments adding constrained scoring mode, parameterized exit logic, and automated model generation.
- **Dataset schemas:** `docs/completion-validation-docs/Step 1 - Original Specs/07_P3_Dataset_Schemas.md` — Formal dataset contracts (D-00 through D-24) defining I/O between IX indexing programs and PG pipeline blocks.
- **Satellite specifications:** `docs/send 2/05_SAT_Complete_All_Satellites.md` — 14 satellite programs (SAT-001 to SAT-014) feeding variables into P1 feature generation.
- **Batch 2 research extraction:** `docs/send 2/04_Model_Register_and_Specs.md` (model register), `docs/send 2/07_D-03_transformations_raw_2.md` (transformation schemas), `docs/send 2/08_Model_Generator_Config_2.md` (generator configuration).
- **Satellite validation pipeline:** `docs/completion-validation-docs/Step_3-V+Architecture/20_Satellite_Model_Validation_Pipeline.md` — Dual-path (static + dynamic) validation framework for satellite model promotion.

### What Was Built

Program 1 implements a multi-stage statistical screening pipeline that subjects thousands of candidate trading model/feature combinations to progressively stricter survival tests, ultimately selecting the strategies with genuine out-of-sample predictive value for promotion to Program 2.

#### Core Feature Engine

The feature engine auto-generates features by crossing input variables against statistical transformations, enforcing type compatibility rules:

| Component | File | Lines | Content |
|-----------|------|-------|---------|
| Variables | `fe_variables.py` | 755 (Batch 1); 1,280 (Batch 2) | 15 variables (V01-V15) in Batch 1, expanded to 25 (V01-V25) in Batch 2 |
| Transformations | `fe_transformations.py` | 953 (Batch 1); 1,158 (Batch 2) | 22 transforms (T01-T22) in Batch 1, expanded to 26 (T01-T26) in Batch 2 |
| Engine | `feature_engine.py` | 305 | V x T cross-product with compatibility enforcement |
| Tests | `test_feature_engine.py` | 524 | 33 tests validating 144 features (Batch 1) |

**Compatibility rules:** Type A variables (76 features) and Type C scalars (43 features) pair with historical transforms T01-T11. Type B sequences (25 features) pair with structural transforms T12-T18. Specific exclusions enforced: V05/V14 are incompatible with T10; T16 requires dual-input. These rules are hard-coded in `feature_engine.py` and verified by the test suite.

**Batch 1 output:** 15 variables x 22 transforms = 144 features (after compatibility filtering).
**Batch 2 output:** 25 variables x 26 transforms = 334 features (2.3x growth from 144).

All four feature engine files are **FROZEN/LOCKED** — no modifications permitted without explicit authorization.

#### Model Generator

`model_generator/model_generator.py` (437 lines) implements N-dimensional Cartesian product grid generation:

```
entry_variants × directions × param_sweeps × assets × exit_grid → model definition files
```

**Exit grid (shared across batches):**
- 5 TP multiples: 0.50, 0.70, 1.00 (Batch 2 uses 1.05 for Batch 1), 1.40/1.50, 2.00
- 4 SL multiples: 0.25, 0.35, 0.50, 0.75
- = 20 exit combinations per entry variant

Exit logic uses Opening Range multiples: `stop_loss = sl_multiple × or_range`, `take_profit = tp_multiple × or_range`.

**Batch 1:** 44 entry variants (M-001 to M-044) across 17 assets, generating ~9,200 model definition files.
**Batch 2:** 26 entry variants (M-045 to M-070) across 17 assets, generating ~1,240 additional variants. Strategy type distribution: ST-02 fade/reversal (9 ANTI models), ST-03 ORB conditional (10 models), ST-04 momentum confirmation (5 models), ST-05 delayed entry (2 models).
**Combined:** ~10,440 model variants for comprehensive P1 screening.

Configuration files:
- `model_generator/model_generator_config.json` — Production config (Batch 1, single exit combo tp=0.70, sl=0.35)
- `model_generator/model_generator_config_research.json` — Research config (44 variants, full 20-exit grid)
- `model_generator/model_generator_config_batch2.json` — Batch 2 config (26 variants, parameter sweeps)

#### IX Indexing Programs

Pre-pipeline indexing programs (`pipeline/ix_programs.py`) wrap registries into formal datasets:

| Program | Input | Output Dataset | Schema |
|---------|-------|---------------|--------|
| IX-1 | `fe_variables.py` | D-05 | VariableIndexed |
| IX-2 | `fe_transformations.py` | D-06 | TransformIndexed |
| IX-3/IX-3a | Sample periods config | D-07 | SampleIndexed (S1 tagged DISCOVERY, frozen per A4 immutability) |
| IX-4 | Feature engine output | D-08 | FeatureIndexed |
| IX-5 | Model JSON files | D-09 | ModelIndexed |
| IX-6 | Backtest trade logs | D-10 | TradeIndexed |

#### Pipeline Blocks (PG Programs)

The per-model pipeline executes sequentially via `pipeline/pg00_orchestrator.py`:

| Block | Program | Function | Input → Output |
|-------|---------|----------|----------------|
| Block 1 | `pg01_feature_gen.py` / IX-4 | Feature generation across all samples | D-05/D-06/D-07 → D-13 (feature values), D-08 |
| Block 2A | `pg02_model_test.py` | Backtest execution on QuantConnect | D-09 model def → D-10 (trade logs) |
| Block 2B | `pg03_kendall_tau.py` | Kendall tau-b correlation screening | D-10/D-13 → D-14..D-19 (tau results) |
| Block 3 | `pg04_threshold.py` | Hurdle rate determination (control model baseline) | D-14..D-19 → D-20 (thresholds) |
| Block 4 | `pg05_gated_test.py` | Gated model validation | D-20/D-10 → D-21/D-22 (gated trades) |
| Block 5 | `pg06_multi_test.py` + `pg07_oo_weighting.py` | Multi-test battery + OO aggregation | D-21/D-22 → D-11 (test results), D-23/D-24 (OO scores) |

**Execution model:** Strictly sequential. `batch_launcher.py` polls QuantConnect backtests one at a time with 15-second intervals and 30-minute timeout per backtest. No parallelization infrastructure is currently implemented (no `multiprocessing`, `concurrent.futures`, or async patterns), though the architecture naturally supports model-level, backtest-level, and sample-level parallelism.

#### Multi-Asset P1 Screening Infrastructure

Screening orchestration scripts process all 17 futures assets across 4 global trading sessions:

| Session | Assets | OR Window |
|---------|--------|-----------|
| NY | ES, NQ, MES, MNQ, M2K, MYM | 09:30-09:35 ET |
| LONDON | MGC, SIL, M6E, M6A, M6B | 03:00-03:05 ET |
| NY_PRE | MCL, ZN, ZT, ZB | 06:00-06:05 ET |
| APAC | NKD, 6J | 18:00-18:05 ET |

Key scripts:
- `run_full_screening.py` — Executes P1 Tiers 1-3,5 screening across all 17 assets with configurable tier selection.
- `run_asset_gap_fill.py` — Fills missing P1 data using micro futures as proxies for standard contracts where local backtester data is unavailable.
- `local_backtester/batch_optimised.py` — Enhanced with `--asset` filter flag for single-asset runs and `--output` flag for custom result paths.

Market data sourced from `mega-backtest-pipeline-extraction-new-decode/market_data/{asset}/` containing raw OHLCV bars. Feature extraction performed by `local_backtester/feature_extractor.py`, outputting to `local_backtester/d11_features/{ASSET}_features.json` with one entry per trading day.

### Pipeline Architecture

The P1 attrition pipeline implements a funnel that progressively eliminates candidate model/feature pairs through increasingly stringent statistical tests:

```
95,880 model variants × 17 assets × 5 tiers
         │
         ▼
   ┌─────────────┐
   │  Block 2B    │  Kendall tau-b screening
   │  (B2B)       │  OOS tau >= 0.30 × IS tau (tolerance_ktr=0.30)
   │              │  Block bootstrap L=20 for serial correlation
   └──────┬───────┘
          │
          ▼
   ┌─────────────┐
   │  Block 3     │  Control model hurdle rate
   │              │  E[win] and E[loss] from unfeaturised C2 baseline
   └──────┬───────┘
          │
          ▼
   ┌─────────────┐
   │  Block 4     │  Gated model validation
   │              │  survival_ratio >= 0.25 (tolerance_block4=0.25)
   └──────┬───────┘
          │
          ▼
   ┌─────────────┐
   │  Block 5     │  OO aggregation + threshold
   │              │  OO >= 0.55 absolute floor
   │              │  Top 15% percentile (percentile=0.85)
   │              │  Two-tier weighted aggregation + sigmoid transform
   │              │  OO = 1/(1 + e^(-IR_composite))
   └──────┬───────┘
          │
          ▼
   11,614 combined survivors
   across 11 of 17 assets
```

**Full screening run (2026-03-21):** 95,880 new model variants tested across Tiers 2, 3, and 5, plus pre-existing Tier 1 results for 6 core assets and Tier 1 Gap Fill for 5 micro/proxy assets. The pipeline ran for 5.1 hours, producing 11,614 combined survivors across 11 assets. Six assets (all currencies and commodities) produced zero survivors.

**OO Aggregation Algorithm** (implemented in `pipeline/pg07_oo_weighting.py`):
1. **Tier 1 (within-category):** Proportional weight allocation with floor constraint: `min_weight = 1 / (3 × n_tests_in_category)`, modulated by state function values.
2. **Tier 2 (across-category):** Uniform allocation across test categories.
3. **Final transform:** Sigmoid mapping `OO = 1 / (1 + e^(-IR_composite))` projecting to (0, 1) probability space, where OO > 0.5 indicates net positive signal across all validation tests.

**V3 Constrained Scoring Rules** (amendment to Block 5):
- C1: `win_rate < 0.35` — penalize strategies with very low hit rates
- C2: `rr_ratio > 1.5` — penalize extreme reward-to-risk ratios (likely curve-fit)
- C3: Removed (control expectancy > 0 constraint dropped per Isaac's redesign)

**Control Model Configuration:**
- 6 baseline models in registry: C2-FIX-STD, C2-FIX-XFA, C2-FIX-LIV, C2-CMP-STD, C2-CMP-XFA, C2-CMP-LIV (3 account types × 2 sizing modes)
- Fixed parameters: `sl_fraction=0.35`, `tp_fraction=0.70` (2:1 R:R ratio)
- OR window: 09:30-09:35 ET (5 minutes), EOD exit: 15:55 ET standard / 16:10 ET prop

**Sample Periods:**
- S1 Discovery: 2009-01-02 to 2020-12-31 (frozen per A4 immutability rule)
- S2 OOS: 2021-01-04 to 2023-12-29
- S3 Recent OOS: 2024-01-02 to present
- S4 AllTime: 2009-01-02 to 2026-present
- Warm-up: starts 2008-01-02 (WARMUP_DAYS=252)
- RANDOM_SEED=42

### Key Decisions

**Proxy instrument mapping for micro contracts.** Micro futures (MES, MNQ, MYM, M2K) launched May 2019, providing insufficient S1 Discovery period (2009-2020) historical coverage. `config.py` implements `PROXY_MAP` mapping MES→ES, MNQ→NQ, MYM→YM, M2K→RTY. Mathematical equivalence holds because parent and micro contracts trade identical underlying markets with identical tick structures; P1 Block 2B Kendall tau operates on rank-based statistics independent of absolute price values, so proxy substitution produces equivalent correlation results.

**Two-tier OO threshold (V3 amendment).** Block 5 applies both an absolute floor (OO > 0.55, better than random) and a relative rank (top 15th percentile of all tested (m, k) pairs). This dual gate was added to prevent marginal models from passing until DSR (Deflated Sharpe Ratio) test activation provides principled multiple-testing correction.

**Parameterized exit logic (V3 amendment).** QuantConnect algorithms read `tp_multiple` and `sl_multiple` from the params dictionary at runtime instead of hard-coded values, enabling a single algorithm file to handle all TP/SL configurations via the model generator. Zero changes required to P1 core components (IX-5, Blocks 1-5, OO computation).

**Local parallelization via exit-grid factoring.** The original QC cloud pipeline ran strictly sequentially (15-second polling, 30-minute timeout per backtest). The local backtester (`run_pipeline_optimised.py`) implemented 16-core multiprocessing with exit-grid factoring, reducing the full 95,880-variant screening to ~5.1 hours by exploiting the mathematical property that exit-grid siblings share identical trade dates and feature values.

**Multi-asset screening with strict survival criteria.** P1 screens 17 assets but applies identical statistical survival thresholds to all. Assets that fail to produce any "combined survivors" are excluded from P2 regardless of how many variants were tested. This enforces consistent quality standards across asset classes.

**Satellite integration architecture.** 14 satellite programs (SAT-001 to SAT-014) integrate at three levels: P1 (as V inputs for backtesting features), P2 (as macro features for regime classification), and P3 (as real-time SiloSignals through AIM wrappers). Each satellite's output follows a standardized `SiloSignal` schema with signal type (DIRECTIONAL/VOLATILITY/RISK/CONFIDENCE/CATALYST), confidence scores, and staleness limits.

**Dual-path validation for dynamic models.** Path A (static models) follows the frozen P1→P2→P3 pipeline. Path B (dynamic satellite models) follows P1-S→P2-S→Shadow→P3 with continuous monitoring. P1-S applies 7 statistical tests (signal-return correlation, monotonicity, timing, confidence calibration, AIM simulation, minimum trades, regime dependence). Shadow deployment requires 60-120 trading days of logging signals without influencing live trades. Four-tier degradation response: Tier 1 Silent (log), Tier 2 Reduce (halve weight), Tier 3 Suppress (zero weight), Tier 4 Quarantine (re-validate).

### Critical Fixes

**Proxy mapping for zero-survivor micro contracts.** Before proxy infrastructure, micro futures (MES, MNQ, MYM, M2K) produced zero P1 survivors due to insufficient pre-2019 historical data in S1 Discovery (2009-2020). The `PROXY_MAP` in `config.py` resolved this by transparently substituting full-size contract data during Kendall tau correlation testing, enabling all four micro contracts to pass statistical validation.

**ASSET_SESSION_MAP expansion.** The session map was expanded from 16 to 19 contracts, adding full-size equity index futures NQ, YM, and RTY as proxy targets. Without these entries, the proxy mapping had no parent contract data to reference.

**Constrained scoring rule C3 removal.** Isaac's V3 redesign removed the C3 constraint (control expectancy > 0), which had been incorrectly filtering strategies where the control model performed poorly — a condition that should increase confidence in the featurised model, not decrease it.

**P2 Block 1 adaptation from daily to minute bars.** The original P2 regime computation assumed daily bar inputs. Adaptation to session-specific minute bars with RTH period definitions (NY/London/APAC/NY_PRE) was required for multi-asset international futures support.

**D-22 trade log format mismatch.** P2 staging trade logs used array-format regime labels with null values, while the Captain bootstrap expected dictionary format (`date → LOW/MEDIUM/HIGH`). The `load_p2_multi_asset.py` bridge script (527 lines) handles this transformation along with field renaming (`trade_date→date`, `r_mi→r`, `LOW/MEDIUM/HIGH→LOW_VOL/HIGH_VOL`).

### Results

#### P1 Survivor Summary by Tier

The full screening run (`run_20260321_025856`, 5.1 hours) produced survivors distributed across tiers:

| Tier | Description | Survivors | Assets with Survivors |
|------|-------------|-----------|----------------------|
| Tier 1 (Pre-existing) | Core assets with legacy P1 data | 5,690 | ES, MGC, NKD, ZB, ZN, ZT |
| Tier 1 Gap Fill | Micro/proxy assets filling S1 history | 5,803 | M2K, MES, MNQ, MYM, NQ |
| Tier 2 | Full screening (63,240 variants) | 121 | M2K, MNQ, NKD, NQ |
| Tier 3 | Full screening (31,960 variants) | 0 | — |
| Tier 5 | Advanced cross-sectional (680 variants) | 0 | — |
| **Total** | | **11,614** | **11 assets** |

#### Top P1 Survivors by OO Score

| Rank | Asset | Model ID | m | k | OO Score | IR Composite |
|------|-------|----------|---|---|----------|-------------|
| 1 | ES | m60812 | 2 | 32 | 0.9903 | 4.62 |
| 2 | ZN | m21389 | 3 | 90 | 0.9775 | 3.77 |
| 3 | M2K | m48392 | 2 | 44 | 0.9747 | 3.65 |
| 4 | M2K | m48072 | 1 | 44 | 0.9699 | 3.47 |
| 5 | ES | m61132 | 4 | 32 | 0.9698 | 3.47 |

#### Per-Asset P1 Survivor Counts

| Asset | Class | Tier 1 Survivors | Tier 1 GF Survivors | Tier 2 Survivors | Best OO | Best (m, k) |
|-------|-------|-----------------|--------------------|--------------------|---------|-------------|
| ES | Equity | 2,109 | — | — | 0.9903 | (2, 32) |
| NQ | Equity | — | 819 | 3 | 0.906 | (4, 31) |
| M2K | Micro Russell | — | 1,197 | 21 | 0.9747 | (2, 44) |
| MES | Micro S&P | — | 1,983 | — | 0.9334 | (4, 47) |
| MNQ | Micro Nasdaq | — | 1,052 | 12 | 0.8894 | (1, 23) |
| MYM | Micro Dow | — | 752 | — | 0.883 | (5, 32) |
| NKD | Nikkei | 215 | — | 85 | 0.9301 | (3, 110) |
| MGC | Micro Gold | 1,785 | — | — | 0.9293 | (2, 97) |
| ZB | 30Y Treasury | 517 | — | — | 0.8054 | (10, 113) |
| ZN | 10Y Treasury | 240 | — | — | 0.9775 | (3, 90) |
| ZT | 2Y Treasury | 824 | — | — | 0.4121 | (1, 37) |

#### P2 Locked Strategies (All REGIME_NEUTRAL)

After P2 regime screening, each asset locked a single best (m, k) pair for production use. Note that the P2-locked strategy may differ from the P1 best OO model because P2 composite scoring uses `CS = OO × ln(N_total)`, rewarding both edge quality and statistical support:

| Asset | Session | P2 Candidates | Locked (m, k) | P2 OO | Composite Score | Production Status |
|-------|---------|--------------|---------------|-------|----------------|-------------------|
| ES | NY | 507 | (7, 33) | 0.883 | 5.39 | ACTIVE |
| NQ | NY | 194 | (3, 32) | 0.824 | 5.15 | ACTIVE |
| M2K | NY | 230 | (5, 32) | 0.925 | 5.38 | ACTIVE |
| MES | NY | 410 | (7, 32) | 0.888 | 4.80 | ACTIVE |
| MNQ | NY | 199 | (5, 32) | 0.824 | 5.22 | ACTIVE |
| MYM | NY | 181 | (9, 115) | 0.770 | 4.73 | ACTIVE |
| NKD | APAC | 140 | (6, 6) | 0.853 | 5.36 | ACTIVE |
| MGC | LONDON | 329 | (2, 29) | 0.889 | 5.66 | ACTIVE |
| ZB | NY_PRE | 170 | (10, 113) | 0.805 | 4.20 | ACTIVE |
| ZN | NY_PRE | 98 | (4, 37) | 0.906 | 5.65 | ACTIVE |
| ZT | NY_PRE | 97 | (1, 25) | 0.366 | 2.18 | **EXCLUDED** (OO < 0.50) |

All 11 locked strategies classified as **REGIME_NEUTRAL** (no statistically significant regime-strategy correlation after BH-FDR correction at q=0.10). ZT is excluded from active trading due to its OO score falling below the 0.50 floor threshold in the P2→P3 seeding script, leaving **10 production-active assets**.

#### 6 Assets Failed P1 Screening (Zero Survivors)

| Asset | Class | s1 Trade Count | Tier 2 Groups Tested | Tier 2 Variants | Outcome |
|-------|-------|---------------|---------------------|-----------------|---------|
| 6J | Currency (JPY) | 2,125 | 0 | 0 | Zero survivors |
| M6A | Currency (AUD) | 2,523 | 0 | 0 | Zero survivors |
| M6B | Currency (GBP) | 1,507 | 4 | 80 | Zero survivors |
| M6E | Currency (EUR) | 2,973 | 8 | 160 | Zero survivors |
| MCL | Commodity (Crude) | 1,059 | 24 | 480 | Zero survivors |
| SIL | Commodity (Silver) | 13 | 0 | 0 | Zero survivors (data sparsity) |

All 6 failed assets are currency and commodity futures. MCL tested the most variants (480) but produced zero survivors. SIL had only 13 S1 trades, indicating severe data sparsity. The ORB strategy architecture appears to be structurally unsuited to currency pairs and commodities.

#### P2 Correlation Analysis

For ES, P2 evaluated 507 candidate model/feature combinations from P1 survivors in `p2_d04_correlations.json`. Each record includes OO performance metric, Kendall tau-b correlation, bootstrap p-value, Benjamini-Hochberg multiple comparison correction, and regime-specific performance (mean returns and trade counts for LOW/HIGH volatility environments). Only the highest-composite-score strategy meeting statistical significance criteria gets locked into P2-D06.

#### Staging Data Scale

The complete P2 staging dataset for ES alone (`pipeline_p2/staging/d22_trade_log_es.json`) contains 6,335,542 trade records spanning December 2009 to 2026, covering all tested parameter combinations. Per-contract returns range from +70.8% to -111% (full stop-out). The Captain-system bootstrap version contains only the filtered trades for the locked strategy (~400 trades).

### Current State

#### Batch 1 (Complete, Production)

- **P1 pipeline fully operational** with 17-asset screening, proxy mapping, and multi-tier attrition.
- **11 locked strategies** promoted through P2 to Captain system (P3) bootstrap.
- **Feature engine frozen:** 15 variables, 22 transforms, 144 features. Files locked.
- **Configuration locked:** `config.py` parameters, control model registry (6 baselines), sample registry (4 periods), RANDOM_SEED=42.
- **P1→P2 bridge implemented:** `pipeline_p2/p1_local_bridge.py` converts local backtester outputs to P2 format (D-07 samples, D-20 thresholds, D-22 trade logs with VIX regime tags, D-24 OO scores).
- **P2→P3 bridge implemented:** `captain-system/scripts/load_p2_multi_asset.py` (527 lines) orchestrates data staging, format transformation, QuestDB registration, and optional bootstrap for all 11 assets. Implements OO performance threshold of 0.50, automatically marking underperforming assets as INACTIVE. Seeds Tier 1 AIMs [4, 6, 8, 11, 12, 15] as INSTALLED per asset.
- **P2 outputs per asset:** `p2_d01_rv_daily.json`, `p2_d02_regime_labels.json`, `p2_d04_correlations.json`, `p2_d05_composite_scores.json`, `p2_d06_locked_strategy.json`, `p2_d07_prediction_model.json`.
- **Screening run artifacts:** `p1_screening_runs/run_20260321_025856/` (consolidated report, per-asset tier logs), `p2_outputs/run_20260321_111438/` (10 assets), `p2_outputs/run_20260322_142153/` (NKD fix run).

#### Batch 2 (Implemented, Not Yet Screened)

- **Feature engine expanded:** 25 variables (+10: V16-V25 for Market Profile, realized moments, regime detection), 26 transforms (+4: T23-T26 for first derivative, CUSUM anomaly, regime run length, threshold indicators). Generates 334 features.
- **Model register defined:** 26 new models (M-045 to M-070) across 4 strategy types. 9 PRIMARY, 9 ANTI (systematic contrarian versions), 8 NOVEL (cross-concept combinations). Approx. 1,240 variants via parameter sweeps.
- **Satellite data fetchers built:** `captain-system/scripts/sat_013_gpr_fetch.py` (Caldara-Iacoviello GPR index, 15,050 rows downloaded), `captain-system/scripts/sat_014_google_trends_fetch.py` (pytrends API integration). All 11 P2 asset configs updated to include GPR_INDEX and GOOGLE_TRENDS_ATTENTION macro features.
- **Transformation schema documented:** 16 Batch 2 transforms (T-024 to T-039) with IX-2 integration metadata, min_history requirements (2 to 252 bars), and default parameter configurations. Three special-role transforms: T-039 (PBO meta-validation), T-032 (RMT correlation cleaning), T-033/T-034/T-035 (change-point detection).
- **Batch 2 progress summary:** `new-models-045-070/BATCH2_PROGRESS.md` documenting 4 completed phases and continuation checklists.
- **Pending:** Test suite update for 334 features, Tier 1 model file generation (24,480 files), parallelization for 59K+ backtests, Tier 2/3 models blocked on data subscriptions and satellite programs.

#### Pipeline Infrastructure

- **Local parallelization operational** — 16-core multiprocessing with exit-grid factoring enables 95,880-variant screening in ~5.1 hours.
- **Large data excluded from git:** `pipeline_p2/staging/` (495 MB trade logs) and `p1_screening_runs/` (multi-GB batch results) in `.gitignore`.
- **Satellite validation pipeline specified** but not yet exercised: dual-path (static/dynamic) validation with shadow deployment and 4-tier degradation response.

---

## 2. Program 2 -- Regime Detection & Strategy Lock

### Spec Reference

Program 2 is driven by Isaac's `02_Program2.md` specification (located at `docs/completion-validation-docs/Step 1 - Original Specs/02_Program2.md`), with V3 amendments integrated from `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/`. The specification defines six logical parts:

- **Part A:** Sample discipline, warm-up policy, NaN handling
- **Part B:** Index programs (P2-IX-1 regime method registry)
- **Part C:** Dataset schemas (P2-D00 through P2-D09)
- **Part F:** Block-level pipeline (Blocks 1, 2, Pre-3, 3a, 3b)
- **Part I:** Complexity tier system (C1-C4)
- **Part J:** Composite score specification and regime classification rules
- **Part K:** Open parameters (bootstrap iterations, thresholds, FDR q-values)
- **Part L:** Rationale and statistical framework justifications

### What Was Built

Program 2 is a multi-asset regime detection and strategy selection pipeline that determines whether each P1-surviving strategy's performance is correlated with volatility regimes. It produces a single **locked strategy** per asset — the production-ready parameter set deployed to the live Captain system.

The pipeline consists of five sequential stages, implemented in `pipeline_p2/`:

| File | Stage | Function |
|------|-------|----------|
| `p2_ix1_regime_methods.py` | P2-IX-1 | Regime method registry (runs once) |
| `p2_pg01_regime_compute.py` | Block 1 | Regime label generation (Pettersson EWMA vol) |
| `p2_pg02_strategy_regime_test.py` | Block 2 | Strategy-regime correlation (Kendall tau-b) |
| `p2_pg05_complexity_tier.py` | Pre-Block 3 | Complexity tier assignment (C1-C4) |
| `p2_pg03_strategy_selection.py` | Block 3a | Multi-objective selection and strategy lock |
| `p2_pg04_regime_prediction.py` | Block 3b | Regime prediction model training (XGBoost/LogReg/Pettersson) |
| `p2_orchestrator.py` | Orchestrator | Executes Blocks 1 through 3b per asset |

Supporting modules:
- `datasets_p2.py` — dataclass schemas for P2-D00 through P2-D09
- `registries_p2.py` — regime method registry constants and tier determination logic
- `p1_data_loader.py` / `p1_local_bridge.py` — read-only access to P1 outputs (D-01, D-07, D-20, D-22, D-24)

#### Block 1: Regime Label Generation (`p2_pg01_regime_compute`)

Computes daily volatility regime labels (LOW or HIGH) using the Pettersson (2014) method:

1. **Daily realised variance (RV_t):** Computed from intraday 15-second log returns during Regular Trading Hours (09:30-16:00 ET for NY session assets).
2. **EWMA volatility (sigma_t):** Exponentially weighted moving average with configurable mass centre (default: 60 trading days).
3. **Trailing threshold (phi_{J,t}):** Simple moving average of sigma over J trading days (default: J=120).
4. **Classification rule:** sigma_{t-1} < phi_{J,t-1} results in LOW; otherwise HIGH. Days within the warm-up window (300 days) receive NULL labels and are excluded from all downstream analysis.

Outputs: P2-D01 (rv_daily_dataset) and P2-D02 (regime_label_dataset).

Two regime methods are registered in P2-D09: G(1) Pettersson Vol State (active) and G(2) MS-HAR-GARCH (inactive, reserved for future tiers). Only method G(1) is used in production.

#### Block 2: Strategy-Regime Correlation (`p2_pg02_strategy_regime_test`)

Tests whether each P1-surviving candidate strategy's trade P&L correlates with the volatility regime state. The statistical pipeline:

1. **Join:** D-22 trade records (from P1) joined to P2-D02 regime labels by date, OOS samples only.
2. **Kendall tau-b:** Pooled OOS correlation between binary regime encoding (LOW=0, HIGH=1) and trade returns. Per-sample diagnostic tau values also computed.
3. **Block bootstrap:** 5,000 iterations with block length L=20, seed=42 for p-value estimation.
4. **BH-FDR correction:** Benjamini-Hochberg at q=0.10 across all candidates within each asset.
5. **Regime statistics:** Mean returns per regime, trade counts, dominant regime identification.
6. **Three-way classification gate:**
   - **REGIME_PREDICTABLE** — Significant correlation (post-FDR) with profitable dominant regime
   - **REGIME_NEUTRAL** — No significant correlation, or insufficient dominant trades (< 30)
   - **REGIME_MISALIGNED** — Significant correlation but unprofitable even in best regime

Constants: `BOOTSTRAP_ITERATIONS=5000`, `BOOTSTRAP_BLOCK_L=20`, `BH_FDR_Q=0.10`, `N_DOMINANT_MIN=30`, `MIN_TRADES_FOR_TAU=30`, `GLOBAL_SEED=42`.

Outputs: P2-D03 (strategy_regime_join) and P2-D04 (strategy_regime_correlation).

#### Pre-Block 3: Complexity Tier Assignment (`p2_pg05_complexity_tier`)

Determines classifier complexity based on available training data (valid trading days in the DISCOVERY sample with non-NULL regime labels):

| Tier | Threshold | Classifier |
|------|-----------|-----------|
| C1 | N >= 1,500 | Full XGBoost (4x3x3x3x2x2 = 432 hyperparameter combinations) |
| C2 | 750 <= N < 1,500 | Constrained XGBoost (2x2x2x2x1x1 = 16 combinations) |
| C3 | 300 <= N < 750 | L2 Logistic Regression with 3 features (f5, f8, f11) |
| C4 | N < 300 | No classifier — Pettersson binary label used directly |

#### Block 3a: Strategy Selection (`p2_pg03_strategy_selection`)

Computes composite scores (CS) and selects one locked strategy per asset:

- **REGIME_PREDICTABLE:** CS = OO x ln(N_dominant) x (1 + |tau_b_pooled|)
- **REGIME_NEUTRAL:** CS = OO x ln(N_total)
- **REGIME_MISALIGNED:** Excluded entirely (no score computed)

The top-1 candidate by CS becomes the locked strategy, written to P2-D06 (locked_strategy_register). The use of ln(N) prevents raw trade count from dominating the score in favour of genuinely better edge.

#### Block 3b: Regime Prediction Model Training (`p2_pg04_regime_prediction`)

Trains a classifier to predict tomorrow's regime from today's observable features. The feature set comprises 14 variables constructed from PRIOR-DAY data only (zero look-ahead):

**Asset-specific (f1-f10):** Prior-day return, trailing mean returns (5/20/60-day), prior-day RV, trailing mean RV (5/20/60-day), trailing Sharpe ratios (20/60-day).

**Macro (f11-f14, conditional):** Prior-day VIX, 5-day trailing mean VIX, term spread, credit spread.

Training uses expanding-window cross-validation on the DISCOVERY sample; validation occurs on all OOS samples. The OOS accuracy threshold for a classifier to be accepted is 0.52. The trained model is linked to the locked strategy via `link_prediction_to_locked_strategy()`.

Outputs: P2-D07 (regime_prediction_model) and P2-D08 (classifier_validation).

### Architecture

#### Orchestration

The pipeline is orchestrated by `p2_orchestrator.py::orchestrate()`, which:

1. Runs P2-IX-1 once to build the regime method registry (P2-D09)
2. Loads P2-D00 asset configurations from `pipeline_p2/asset_configs/`
3. Iterates `run_pipeline_for_asset()` for each asset, executing Blocks 1 -> 2 -> Pre-3 -> 3a -> 3b sequentially
4. Writes per-asset output files and a run summary

The production run (`run_20260321_111438`) processed 11 assets in 2,130 seconds. A supplementary NKD run (`run_20260322_142153`) added the Nikkei contract.

#### Dataset Flow

```
P1 Outputs (read-only)          P2 Pipeline                    P2 Outputs
──────────────────────          ───────────                    ──────────
D-01 (market data)    ──┐
D-07 (sample defs)    ──┤      Block 1                        P2-D01 (rv_daily)
D-20 (thresholds)     ──┤      ├── Regime compute ──────────> P2-D02 (regime_labels)
D-22 (trade log)      ──┤      │
D-24 (OO scores)      ──┘      Block 2
                                ├── Strategy-regime test ───> P2-D03 (join)
                                │                             P2-D04 (correlation)
                                │
                                Pre-Block 3
                                ├── Complexity tier ────────> tier assignment
                                │
                                Block 3a
                                ├── Selection ──────────────> P2-D05 (composite scores)
                                │                             P2-D06 (locked strategy) ★
                                │
                                Block 3b
                                └── Prediction training ───> P2-D07 (prediction model)
                                                              P2-D08 (classifier validation)
```

#### Live System Integration (Captain Online B2)

The P2 results feed into the live Captain system through Captain Online Block 2 (`captain-system/captain-online/captain_online/blocks/b2_regime_probability.py`), a 194-line module implementing dual-path regime classification:

**Path 1 — C4 assets (BINARY_ONLY):** The `_binary_regime()` function computes realised volatility from 20-day trailing returns (annualised with sqrt(252)) and performs a hard threshold comparison against phi (the Pettersson threshold from P2-D07). Above phi yields HIGH_VOL=1.0; below yields LOW_VOL=1.0.

**Path 2 — C1-C3 assets (trained classifier):** The `_classifier_regime()` function deserialises the XGBoost classifier from `model.classifier_object`, extracts a feature vector via `extract_classifier_features()` in the same order as `model.feature_list`, validates feature completeness (all non-None), and runs `predict_proba()`. Class ordering is assumed as [LOW_VOL, HIGH_VOL] for probability array indexing.

**REGIME_NEUTRAL short-circuit:** When the locked regime label is REGIME_NEUTRAL (which is the case for all 11 production assets), the classifier path returns equal probabilities {HIGH_VOL: 0.5, LOW_VOL: 0.5} without invoking any classifier — the strategy runs unconditionally.

**Uncertainty detection:** When `max(regime_probs) < 0.6`, the `regime_uncertain` flag is set to True, signalling downstream Block 4 (Kelly sizing) to use robust estimators that blend HIGH_VOL and LOW_VOL Kelly fractions rather than committing to a single regime.

**Fallback cascade:** Missing regime model -> neutral probs. Failed volatility computation -> neutral probs. Incomplete classifier features -> neutral probs. Classifier exception -> neutral probs. Every fallback sets `regime_uncertain=True` and logs a warning.

The `run_regime_probability()` entry point processes all active assets per session evaluation (NY/LON/APAC), called by the Captain Online orchestrator. The `argmax_regime()` utility extracts the dominant regime label for downstream decision logic.

#### Data Seeding

P2 outputs are loaded into the Captain system via `captain-system/scripts/load_p2_multi_asset.py`, which:

1. Reads P2-D06 locked strategies for all 11 assets from `p2_outputs/run_20260321_111438/` (and NKD from `run_20260322_142153/`)
2. Filters D-22 trade logs to the locked (m, k) pair per asset
3. Loads P2-D02 regime labels and maps LOW/MEDIUM -> LOW_VOL, HIGH -> HIGH_VOL
4. Registers each asset in `p3_d00_asset_universe` with locked strategy configuration
5. Optionally runs bootstrap to initialise EWMA, BOCPD/CUSUM, and Kelly state

Assets with OO below the floor threshold (`OO_FLOOR=0.50`) are excluded from active trading.

### Key Decisions

**REGIME_NEUTRAL lock:** All 11 assets received the REGIME_NEUTRAL classification. This means no statistically significant correlation was found between trade P&L and the volatility regime state after BH-FDR correction at q=0.10. The practical consequence is that the system trades unconditionally — it does not condition entry or sizing on whether the market is in a HIGH or LOW volatility regime.

**Composite score formula:** The REGIME_NEUTRAL branch uses CS = OO x ln(N_total), which rewards both out-of-sample edge (OO) and statistical support (log of trade count). The logarithmic transform prevents high-frequency strategies from dominating on sample size alone.

**Complexity tier outcomes:** Despite most assets being classified as C1 (sufficient data for full XGBoost), the REGIME_NEUTRAL classification means the trained classifiers are not actively used in production. The B2 module short-circuits to equal probabilities when `regime_label == "REGIME_NEUTRAL"`.

**Dual-path architecture:** The B2 module retains both the Pettersson binary rule (for C4 assets) and the XGBoost classifier path (for C1-C3) even though neither is actively invoked under REGIME_NEUTRAL. This preserves the ability to activate regime-conditioned trading if future decay-triggered reruns produce REGIME_PREDICTABLE results.

**Asset-specific strategy parameters:** Each asset locks its own (m, k) pair and threshold, not a global parameter set. The locked configurations vary significantly across the 11 assets (see Results below).

### Results

The production run on 2026-03-21 processed 11 assets (10 completed in the main run, NKD completed in a supplementary run on 2026-03-22):

| Asset | Tier | Locked (m, k) | OO | Composite Score | Candidates | Regime Class |
|-------|------|---------------|------|-----------------|------------|--------------|
| ES | C1 | (7, 33) | 0.8832 | 5.392 | 507 | REGIME_NEUTRAL |
| NQ | C1 | (3, 32) | 0.8242 | 5.150 | 194 | REGIME_NEUTRAL |
| M2K | C3 | (5, 32) | 0.9245 | 5.375 | 230 | REGIME_NEUTRAL |
| MES | C1 | (7, 32) | 0.8879 | 4.801 | 410 | REGIME_NEUTRAL |
| MNQ | C1 | (5, 32) | 0.8236 | 5.222 | 199 | REGIME_NEUTRAL |
| MYM | C1 | (9, 115) | 0.7705 | 4.734 | 181 | REGIME_NEUTRAL |
| NKD | — | (separate run) | — | — | — | REGIME_NEUTRAL |
| MGC | C1 | (2, 29) | 0.8892 | 5.662 | 329 | REGIME_NEUTRAL |
| ZB | C1 | (10, 113) | 0.8054 | 4.200 | 170 | REGIME_NEUTRAL |
| ZN | C1 | (4, 37) | 0.9058 | 5.649 | 98 | REGIME_NEUTRAL |
| ZT | C1 | (1, 25) | 0.3658 | 2.177 | 97 | REGIME_NEUTRAL |

Key observations:
- **OO range:** 0.37 (ZT) to 0.92 (M2K). ZT's low OO (0.3658) falls below the OO_FLOOR=0.50 threshold used during seeding, making it a candidate for exclusion from active trading.
- **All REGIME_NEUTRAL:** No asset showed statistically significant regime-strategy correlation after FDR correction.
- **No trained classifiers active:** All P2-D08 validation records show `confidence_flag: "NO_CLASSIFIER"` and zero accuracy metrics, confirming the REGIME_NEUTRAL short-circuit.
- **ES top candidate:** (m=7, k=33) with 507 eligible candidates screened, composite score 5.392, threshold -1.378816.

For ES specifically, the top-5 composite scores from P2-D05 were:

| Rank | (m, k) | OO | CS | N_effective | tau_b |
|------|--------|------|------|-------------|-------|
| 1 | (7, 33) | 0.8832 | 5.392 | 448 | 0.027 |
| 2 | (7, 21) | 0.8276 | 5.300 | 604 | -0.041 |
| 3 | (8, 23) | 0.9221 | 5.186 | 277 | 0.019 |
| 4 | (6, 17) | 0.8634 | 5.160 | 394 | 0.024 |
| 5 | (10, 27) | 0.9195 | 5.151 | 271 | 0.047 |

The historical ES regime label time series (P2-D02) spans from 2010-03-04 onwards, with 4,426+ daily labels alternating between LOW and HIGH states.

### Current State

**P2 pipeline status:** COMPLETE. All code is frozen and the locked results are authoritative. P2 code is not modified unless Captain Offline's Level 3 decay detection triggers a full pipeline rerun.

**Captain Online consumption:** Block 2 (`b2_regime_probability.py`) reads P2-D07 regime models from the seeded database. Under the current REGIME_NEUTRAL lock for all 11 assets, B2 returns equal regime probabilities ({HIGH_VOL: 0.5, LOW_VOL: 0.5}) and sets `regime_uncertain` appropriately. This flows into B3 (AIM aggregation) and B4 (Kelly sizing) without regime conditioning.

**Asset universe seeding:** The `load_p2_multi_asset.py` script stages all P2 outputs into `captain-system/data/p2_outputs/{asset}/` and registers them in the `p3_d00_asset_universe` QuestDB table. Each asset's locked_strategy JSON includes `model_id`, `feature_id`, `default_direction=0` (direction determined by Opening Range Breakout pattern), `OR_RANGE` stop-loss method, and `threshold`.

**P2 output locations:**
- Raw pipeline outputs: `p2_outputs/run_20260321_111438/{asset}/` (10 assets) and `p2_outputs/run_20260322_142153/NKD/` (supplementary)
- Captain-staged copies: `captain-system/data/p2_outputs/{asset}/` (11 assets, 3 files each: p2_d02, p2_d06, p2_d08)
- Pipeline source code: `pipeline_p2/` (12 Python modules)

**Decay rerun path:** If Captain Offline Block 1 (DMA monitoring) detects sustained edge decay escalating to Level 3, it triggers a full P1+P2 rerun. The P2 orchestrator can be re-executed with updated P1 outputs to produce new locked strategies, which would then be reseeded into the Captain system through the same `load_p2_multi_asset.py` workflow.

---

## 3. V3 Amendments & Completion Validation

### Spec Reference

Isaac's V3 amendment package is documented across 55 files in `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/`. The authoritative entry points are:

- **`Nomaan_Master_Build_Guide.md`** -- Master sequencing guide for integrating all V3 changes
- **`Cross_Reference_PreDeploy_vs_V3.md`** -- Line-by-line mapping of every V3 change to its insertion point in the original specs
- **`Nomaan_Edits_P3.md`** -- Circuit breaker layers, intraday state tracking, preemptive halt formulas
- **`Nomaan_Edits_Fees.md`** -- Fee integration into Kelly sizing and commission resolution
- **`Topstep_Optimisation_Functions.md`** (1,030 lines) -- MDD% function, payout optimization, trade sizing, fee schedules, SOD parameter computation
- **`HMM_Opportunity_Regime_Spec.md`** (579 lines) -- AIM-16 HMM training, TVTP transition matrices, session budget allocation
- **`Payout_Rules.md`** -- Tier-preserving withdrawal logic, MDD% band maintenance, winning-days requirements
- **`Nomaan_Edits_P3_Command_GUI.md`** -- Payout panel, scaling display, notification enhancements
- **`Pseudotrader_Account_Awareness_Amendment.md`** -- Multi-stage replay (EVAL to XFA to LIVE), capital unlock, dual-forecast structure

V3 files supersede the original specs (located in `docs/completion-validation-docs/Step 1 - Original Specs/`) wherever conflicts exist. The original specs remain valid for areas V3 does not touch.

### What the V3 Amendments Changed

The V3 amendment package introduced 11 categories of changes spanning all three Captain processes plus the P1 pipeline:

**Captain Online (6 changes):**

1. **O1 -- Fee integration in Kelly sizing.** `risk_per_contract` now includes expected fees via `get_expected_fee()`, and the final contract count takes the 4-way minimum of Kelly contracts, TSM cap, Topstep daily cap, and scaling cap. Source: `Nomaan_Edits_Fees.md` Change 2 + `Topstep_Optimisation_Functions.md` Part 6.

2. **O2 -- HMM session budget allocation.** Before trade selection ranking, AIM-16's HMM inference computes a per-session budget from the remaining daily budget and intraday observations. Signals exceeding the session budget are blocked with reason `SESSION_BUDGET_EXHAUSTED`. Source: `HMM_Opportunity_Regime_Spec.md` Part 3, Section 3.7.

3. **O3 -- Circuit breaker screen insertion.** A new block (B5C) runs after the quality gate and before signal output. It evaluates 7 layers of risk checks per account-asset pair. Non-Topstep accounts bypass the circuit breaker entirely. Source: `Topstep_Optimisation_Functions.md` Part 6.

4. **O4 -- Fee schedule resolution.** Commission resolution now checks `tsm.fee_schedule.fees_by_instrument` first (structured per-instrument round-turn fees), falling back to `commission_per_contract * 2` only if no fee schedule exists. This supports the distinct fee structures across Topstep Express ($2.80 RT for ES) and Topstep Live ($4.18 RT for NQ).

5. **O5 -- `get_expected_fee()` function.** New utility function providing expected fee lookups for pre-trade risk calculations throughout the Online process.

6. **O6 -- P3-D23 intraday state updates.** After each position resolution, the circuit breaker intraday state table receives cumulative P&L (`L_t`), trade count (`n_t`), and per-basket breakdowns (`L_b`, `n_b` keyed by `model_m`).

**Captain Offline (3 changes):**

7. **F1 -- AIM-16 HMM training (PG-01C).** New training procedure for the Opportunity Regime Hidden Markov Model with time-varying transition probabilities (TVTP), conditioning the transition matrix on market covariates. Warmup threshold set at 240 trades (vs 50 default). Source: `HMM_Opportunity_Regime_Spec.md` Part 3, Section 3.5.

8. **F2 -- Pseudotrader circuit breaker extension (PG-09B, PG-09C).** The pseudotrader gained two new operational modes: CB replay (replaying historical trades through the 4-layer protection system with per-basket tracking) and CB grid search (optimizing `c` and `lambda` parameters across a grid, selecting the best configuration with PBO < 0.5). Source: `Topstep_Optimisation_Functions.md` Part 8.

9. **F3 -- Beta_b estimation (PG-16C).** Circuit breaker parameter estimator computes per-basket conditional expectancy parameters (`r_bar`, `beta_b`, `sigma`, `rho_bar`) via OLS regression with significance gating (p < 0.05, n >= 100). During cold start, `beta_b = 0` and `mu_b = r_bar`, ensuring positive-expectancy baskets remain open. Source: `Nomaan_Edits_P3.md` Change 4.

**Captain Command (2 changes):**

10. **C1 -- SOD Topstep parameter computation.** Daily reconciliation (Block 8) now computes Start-of-Day locked parameters for Topstep accounts: `f(A) = 4500/A` for MDD%, `N(A,p,e,phi) = floor((e*A)/(4500*p + phi))` for max trades, and `E(A,e) = e*A` for daily exposure budget. All SOD parameters lock at 19:00 EST and persist directly in P3-D08. Source: `Topstep_Optimisation_Functions.md` Part 6.

11. **C2 -- Payout notification and GUI panels.** Payout recommendations include `f_post` (post-withdrawal MDD%), `payouts_remaining` count, and `next_eligible` winning-days countdown. New PayoutPanel and ScalingDisplay added to the GUI.

**P1 Pipeline (2 changes):**

12. **P1 -- OO threshold two-tier filter.** The previous TBD threshold became a two-tier gate: `OO >= 0.55` absolute floor AND `OO` in top 85th percentile of all `(m,k)` pairs. Implemented in `pg07_oo_weighting.py`.

13. **P2 -- Constrained scoring mode.** Added as authorized amendment to Block 5, with open parameters `threshold_OO_floor: 0.55` and `threshold_OO_percentile: 0.85`.

**Architecture (3 changes):**

14. **A1 -- Three new datasets.** P3-D23 (circuit_breaker_intraday_state), P3-D25 (circuit_breaker_params), P3-D26 (hmm_opportunity_state) added to QuestDB schema, bringing the total from 23 original to 29 tables (23 + 3 V3 + 2 auxiliary + 1 forecasts).

15. **A2 -- TRAINING_ONLY status.** New `captain_status` enum value allowing assets to accumulate observation data without generating live signals.

16. **A3 -- Open parameter additions.** `threshold_OO_floor`, `threshold_OO_percentile`, and `topstep_params {p, e, c, lambda}` added to the system parameter catalogue.

### Validation Process

Completion validation ran from 2026-03-16 in two parts, comparing all code against the 55 V3 spec files plus the 10 original spec documents.

**Phase 0 -- Documentation Discovery.** Extracted requirements from all spec files, building a crosswalk between spec sections and code locations. This produced the initial discrepancy list.

**Part 1 -- Phases A through F** addressed 87 discrepancies organized by severity and subsystem:

| Phase | Scope | Items | Priority |
|-------|-------|-------|----------|
| A | P3 Circuit Breaker + Risk | 5 | HIGHEST -- correctness bugs in live risk code |
| B | P1 Config (C2 models, point values, contract roll) | 3 | HIGH |
| C | P1 Pipeline Logic (MIN_TRADES, alpha rule) | 2 | HIGH |
| D | Signal Distribution | 3 | HIGH (deferred pending review) |
| E | MEDIUM P3 Fixes (14 items) | 14 | MEDIUM |
| F | MEDIUM P1 Pipeline Logic (8 items) | 8 | MEDIUM |
| G | LOW Items | 33 | LOW (deferred) |

Eight questions requiring Nomaan/Isaac decision were raised before execution:

- **Q1 (AIM aggregation formula):** AIMRegistry.md specified multiplicative product; Online spec specified additive sum. **Resolution:** Additive confirmed as authoritative.
- **Q2 (OO floor removal):** Condition 3 (positive expectancy) removed per Isaac Q1 answer. **Resolution:** Confirmed authorized.
- **Q4 (Warmup days):** 252 trading days vs 365 calendar days. **Resolution:** Equivalent in QC's trading-day framework; no change needed.
- **Q5 (Shape classification):** Area-under-curve vs 90th percentile ratio. **Resolution:** Intentional implementation choice; kept as-is.
- **Q7 (D23 collision):** Code uses D23 for circuit_breaker_intraday; V3 reserved it for strategy_type_register. **Resolution:** Future strategy_type_register renumbered to D28; existing CB table kept at D23 to avoid 4+ file changes.
- **Q8 (Pseudotrader account awareness):** Current `run_account_aware_replay()` integration deemed sufficient for V1.

**Part 2** executed the actual code changes, implementing all HIGH and MEDIUM items in priority order. Estimated scope was approximately 350 lines changed across Phase A alone.

### Key Rewrites

**Circuit Breaker: 5-Layer to 7-Layer (12-D1, 12-D2, 12-D3)**

The original implementation used 5 ad-hoc layers (daily_loss_beta, consecutive_losses, intraday_pnl, session_halt, manual_override). The V3 spec required a mathematically grounded composite decision function:

```
D_{j+1} = H(L_t, rho_j) * B(n_t) * C_b(L_b) * Q(L_b, n_t)
```

The rewrite produced a 560-line `b5c_circuit_breaker.py` with 7 layers:

- **Layer 0 (Scaling Cap):** XFA-only. Blocks when `current_open_micros + proposed_micros > scaling_tier_micros`.
- **Layer 1 (Preemptive Halt):** Blocks when `abs(L_t) + rho_j >= c * e * A`, where `rho_j = contracts * (SL_distance * point_value + fee)`. This prevents trades whose worst-case SL would breach the halt threshold, rather than waiting for losses to accumulate.
- **Layer 2 (Budget):** `N = floor((e * A) / (MDD * p + phi))`. Blocks when `n_t >= N`. The original formula was missing the `phi` fee drag term.
- **Layer 3 (Basket Expectancy):** `mu_b = r_bar + beta_b * L_b` with significance gate (p < 0.05 AND n >= 100). Cold-start default `beta_b = 0` ensures `mu_b = r_bar`, keeping positive-expectancy baskets open.
- **Layer 4 (Correlation Sharpe):** `S = mu_b / (sigma * sqrt(1 + 2 * n_t * rho_bar))` with `lambda` threshold defaulting to 0.0 (effectively disabled during cold start when `rho_bar = 0`).
- **Layer 5 (Session Halt):** VIX > 50.0 or DATA_HOLD count >= 3 blocks all Topstep accounts.
- **Layer 6 (Manual Override):** Operator halt capability preserved.

Critical tracking fix: `n_t` changed from consecutive-loss counter (reset on wins) to total-trades-today counter. `L_t` changed from loss-only accumulator to all-P&L accumulator. Per-basket `L_b`/`n_b` dictionaries added, keyed by `model_m`.

**Isotonic Regression: Binary to Continuous Returns (41-D3)**

The original `pg04_threshold.py` fitted isotonic regression on a binary win indicator (0/1). The V3 spec required fitting on raw returns `R_i`, producing a continuous monotonic mapping from threshold to expected return. This change affects how the threshold classification identifies optimal operating points.

**CWRM: Maximum to First-Qualifying (41-D2)**

The Conservative Win-Rate Maximizer previously selected the threshold with maximum win rate. The V3 spec required selecting the lowest qualifying threshold -- the first threshold that meets the hurdle rate. This produces more conservative threshold selection, preferring the earliest qualifying point over potentially overfit maxima.

**Kelly Scaling Cap: Open Position Subtraction (15-D4)**

The scaling cap function returned the raw tier maximum without accounting for currently open positions. The fix subtracts `current_open_micros` from `scaling_tier_micros`, preventing new trades from exceeding the XFA simultaneous position limit:

```python
available = tier_micros - current_open_micros
return max(available, 0)
```

**Tier-Preserving Payout Logic (17-D3)**

Payout recommendations previously had no floor protection. The V3 spec requires computing `f_post` (post-withdrawal MDD%) and capping the withdrawal amount to keep the account within the target MDD% band of 2.81-2.90%. The formula `W(A) = min(5000, 0.5 * (A - 150000))` with a maximum of 5 payouts before XFA-to-LIVE transition prevents payouts from dropping the account below its tier floor.

Additional payout fixes: withdrawal eligibility checks net-after-commission (not gross), and LIVE accounts receive distinct logic (0% commission, daily payouts after 30 winning days, separate `target_A`).

**P1 Pipeline Corrections (40-D1, 40-D4)**

Block 2 MIN_TRADES gate corrected from 30 to 200. Alpha rule corrected from "any OOS passes" to "ALL OOS must pass" -- a critical change that prevents strategies surviving on one lucky out-of-sample fold.

### 87 Discrepancies Resolved

The 87 discrepancies broke down by severity:

| Severity | Count | Actionable | Deferred |
|----------|-------|------------|----------|
| HIGH | 15 | 12 | 3 (LOCKED files) |
| MEDIUM | 34 | 24 | 10 |
| LOW | 38 | 5 | 33 |
| **Total** | **87** | **41** | **46** |

**HIGH severity (15 items):** Circuit breaker layer mismatch (12-D1), n_t/L_t tracking errors (12-D2), missing per-basket tracking (12-D3), scaling cap bug (15-D4), missing tier-preserving payout (17-D3), AIM aggregation spec conflict (P3ON-02), C2 model ATR-to-OR-range (D36-01), missing per-asset point_value (D23-02), contract normalization (D34-01), signal distributor unimplemented (38-D1/D2/D3), MIN_TRADES gate (40-D1), alpha rule (40-D4), feature engine numbering mismatch (49-D3, LOCKED).

**MEDIUM severity (34 items):** Spanned P1 pipeline logic (block bootstrap method, BH-FDR status, shape classification, CWRM strategy, isotonic regression target, C1 gate logic), P3 Captain system (CB preemptive halt formula, N formula missing phi, SOD storage location, Kelly daily cap source, HMM TVTP, HMM online inference, payout MDD% band, payout net check, LIVE payout rules, PayoutPanel fields, notification content, D23 table collision, Redis channel count), and configuration items (sample period storage, TSM templates, trading hours structure, vault backup volume).

**LOW severity (38 items):** Primarily naming conventions (singular vs plural keys, GATED vs FEATURE_GATED, UNASSIGNED vs UNTAGGED), organizational differences (extra fields in code as supersets of spec), and expected future-work gaps (52 variables in spec vs 15 in code for the LOCKED feature engine, 44 models in spec vs 2 C2 controls in current configuration).

**Most impactful discrepancies resolved:**

1. **12-D1 (Circuit breaker rewrite):** The entire risk management layer was structurally wrong -- 5 ad-hoc checks replaced by the mathematically specified 7-layer composite decision.
2. **12-D2 (n_t/L_t tracking):** Tracking consecutive losses instead of total trades and accumulating only losses instead of all P&L would have caused the budget and expectancy layers to produce incorrect decisions.
3. **15-D4 (Scaling cap):** Not subtracting open positions meant XFA accounts could exceed their simultaneous position limits.
4. **41-D2/D3 (CWRM + isotonic):** Together, these would have selected different threshold operating points for every strategy, potentially changing which strategies survive the P1 pipeline.
5. **40-D4 (Alpha rule):** "Any OOS" vs "ALL OOS" is the difference between a lenient and strict survival gate.

### Key Decisions

**Build V1+V2+V3 as one system.** Rather than implementing V1, then patching V2, then patching V3, the decision was made to integrate all amendment layers from day one. This avoided accumulating technical debt from sequential patches and ensured multi-user Topstep optimization was architected in from the start.

**Additive AIM aggregation confirmed.** When the AIMRegistry spec (multiplicative product of modifiers raised to meta-weight powers) conflicted with the Online spec (additive weighted sum), the additive formulation was confirmed as authoritative. The code already followed the Online spec.

**D23 table collision resolved by renumbering future work.** The existing circuit_breaker_intraday_state table at D23 was wired into 4+ production files. The future strategy_type_register (not yet implemented) was assigned D28 instead.

**HMM TVTP deferred to post-V1.** Standard Baum-Welch HMM was deemed sufficient for initial deployment. The time-varying transition probability extension (conditioning the transition matrix on market covariates) remains a documented enhancement.

**Shape classification kept as area-under-curve.** The spec's 90th percentile ratio method was acknowledged, but the area-under-curve implementation was confirmed as an intentional implementation choice.

**PAPER default enforced.** The `.env.template` TRADING_ENVIRONMENT default was changed from LIVE to PAPER, and all three Captain process entry points gained identical runtime validation that rejects invalid values, warns on LIVE, and defaults to PAPER. This prevents accidental real-money trading from template copy-paste.

**AlgorithmImports defensive wrapping.** All 40 captain-system Python modules received try/except wrapping around `from AlgorithmImports import *` to prevent Docker container crashes outside the QuantConnect cloud environment. This was a systematic 40-file, 160-insertion change.

### Confirmed Alignments

The validation also confirmed correct implementation across large sections of the codebase:

- **P1 Pipeline:** TEST_REGISTRY (13 tests), OO_CATEGORY_REGISTRY (4 categories), weight floor formula, orchestrator phase structure, ICIR computation, BH-FDR q=0.10, alpha tolerance 0.30, Block 4 tolerance 0.25, D-24 scoring_mode, SEED=42, sigmoid formulas
- **P2 Pipeline:** REGIME_METHOD_REGISTRY, complexity tiers (C1-C4), composite scoring, REGIME_MISALIGNED exclusion, dataset loading
- **P3 Offline:** AIM lifecycle states (7-state machine), BOCPD/CUSUM/level escalation, pseudotrader replay structure (4 operational modes with PBO/DSR anti-overfitting), sensitivity scanning (7-point perturbation grid), auto-expansion (GA search), TSM simulation, Kelly updates, CB parameter estimation (OLS + significance gate), 8-dimension diagnostic health scoring, bootstrap shortcut for Tier 1 AIMs
- **P3 Online:** 9-block pipeline, data ingestion, regime probability, AIM modifier bounds (0.5-1.5), Kelly 4-way min, fee integration, trade selection with HMM allocation, signal output per-user, position monitoring, concentration monitoring (30-day windowed), capacity evaluation (6 constraint types)
- **P3 Command:** All 10 blocks, signal routing (TAKEN/SKIPPED), WebSocket GUI, broker API adapter, TSM management, injection flow, 11 discretionary reports, Telegram notifications (26 event types), daily reconciliation with SOD computation, incident response, data validation
- **Infrastructure:** Docker 6-container stack, QuestDB 29 tables, Redis AOF with 5 pub/sub channels, nginx TLS 1.3, SQLite WAL journals, vault AES-256-GCM, TZ=America/New_York system-wide, RBAC multi-user
- **GUI:** 22 primary panels + 19 System Overview panels, PayoutPanel, ScalingDisplay, CircuitBreakerBanner, auth/RBAC components (51 files, 2,729 LOC, React 18 + TypeScript + Vite 5 + Tailwind CSS)

### Current State

All 87 discrepancies have been categorized, with 41 actionable items executed through Phases A-F and 46 deferred items (33 LOW severity naming/organizational, 10 MEDIUM future-work, 3 HIGH in LOCKED files requiring explicit approval). Phase G (LOW items) remains deferred as non-blocking for deployment.

The system stands at approximately 99% spec compliance, with the remaining gaps being either:
- LOCKED file changes requiring Isaac/Nomaan approval (feature engine numbering, C2 control model expansion)
- Future-work items explicitly scoped for post-V1 (strategy type registry, 44-model expansion, TVTP HMM, signal distributor)
- Naming-only differences that do not affect correctness

The completion validation tracker resides at `docs/completion-validation-docs/CHANGE_TRACKER.md` with full traceability from each discrepancy ID to its spec source, affected file, before/after state, confidence level, and resolution. The execution plan at `docs/completion-validation-docs/EXECUTION_PLAN.md` documents the phase ordering, verification steps, and Nomaan/Isaac answers to the 8 pre-execution questions.

**Key files:**
- `docs/completion-validation-docs/CHANGE_TRACKER.md` -- 87 discrepancies with full audit trail
- `docs/completion-validation-docs/EXECUTION_PLAN.md` -- Phase A-G execution sequencing
- `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/Cross_Reference_PreDeploy_vs_V3.md` -- Line-by-line V3 insertion points
- `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/Nomaan_Master_Build_Guide.md` -- V3 integration sequencing
- `.context/AMENDMENT_AUDIT_BASELINE.md` -- Audit baseline for V3 amendments

---

## 4. Infrastructure -- Docker, QuestDB, Redis

### Spec Reference

The infrastructure layer is defined across several specification documents:
- **03_Program3_Architecture.md** (original spec): Docker Compose topology, database selection, inter-process communication
- **07_P3_Dataset_Schemas.md** (original spec): All 29 QuestDB table schemas with ownership and partitioning rules
- **Nomaan_Master_Build_Guide.md** (V3 master guide): V3 table additions (D23, D25, D26), Redis Streams migration requirement
- **STABILITY_ANALYSIS.md** (operational document): 12-vulnerability analysis of the connection infrastructure with prioritized remediation

The infrastructure serves a single purpose: enable three independent Python processes (Captain Offline, Captain Online, Captain Command) to share persistent state via QuestDB and coordinate in real time via Redis, fronted by Nginx for GUI delivery and API access.

---

### Docker Architecture

#### Container Topology

The Captain System runs 7 Docker services (6 long-running, 1 ephemeral build container) defined across two Compose files:

| Service | Image | Role | Restart | Port Bindings |
|---------|-------|------|---------|---------------|
| `questdb` | `questdb/questdb:latest` | Time-series database | `unless-stopped` | `127.0.0.1:9000` (console), `127.0.0.1:8812` (PG wire), `127.0.0.1:9009` (InfluxDB line) |
| `redis` | `redis:7-alpine` | Message broker + pub/sub | `unless-stopped` | `127.0.0.1:6379` |
| `captain-offline` | Custom (Python 3.11-slim) | Strategic brain | `unless-stopped` | None |
| `captain-online` | Custom (Python 3.11-slim) | Signal engine | `unless-stopped` | None |
| `captain-command` | Custom (Python 3.11-slim) | Linking layer + FastAPI | `unless-stopped` | `127.0.0.1:8000` (dev) |
| `captain-gui` | Multi-stage (Node 20 + Alpine) | React SPA build | `"no"` (ephemeral) | None |
| `nginx` | `nginx:alpine` | Reverse proxy / static | `unless-stopped` | `127.0.0.1:80` (local override) |

All port bindings use `127.0.0.1` to prevent external network access. The default bridge network handles inter-container routing by service name.

#### Compose File Structure

Two Compose files are always used together:

- **`docker-compose.yml`** -- Base configuration with service definitions, volumes, health checks, and dependency ordering. Contains no port bindings for Nginx (deployment-specific).
- **`docker-compose.local.yml`** -- Local development override for Windows 11 / WSL 2. Adds memory limits, HTTP-only Nginx on port 80, and the local Nginx configuration file.

Usage: `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d`

The base file explicitly notes: *"Never run the base file alone -- always pair with an override."*

#### Memory Limits (Local Deployment)

Defined in `docker-compose.local.yml` to stay within WSL 2 memory allocation:

| Service | Limit | Reservation |
|---------|-------|-------------|
| `questdb` | 2 GB | 512 MB |
| `captain-online` | 2 GB | 768 MB |
| `captain-offline` | 1.5 GB | 512 MB |
| `captain-command` | 768 MB | 256 MB |
| `redis` | 256 MB | 64 MB |
| `nginx` | 128 MB | 32 MB |
| **Total** | **~6.6 GB** | |

Priority allocation gives the most memory to data-intensive services (QuestDB and Captain Online's signal pipeline).

#### Health Checks

Every long-running service has a health check. Infrastructure services (QuestDB, Redis) use lightweight probes; Captain processes verify dual connectivity to both dependencies:

**QuestDB:**
```
test: curl -f http://localhost:9000/exec?query=SELECT%201
interval: 10s, timeout: 5s, retries: 5
```

**Redis:**
```
test: redis-cli ping
interval: 10s, timeout: 5s, retries: 5
```

**Captain Online / Captain Offline (identical):**
```
interval: 30s, timeout: 10s, start-period: 60s, retries: 3
test: python -c "import psycopg2, redis; c=psycopg2.connect(...); c.close(); r=redis.Redis(...); r.ping()"
```

These dual health checks verify that both QuestDB and Redis remain reachable from within each process container, not just the process itself.

**Captain Command:**
```
interval: 30s, timeout: 10s, start-period: 60s, retries: 3
test: curl -sf http://localhost:8000/api/health || exit 1
```

Captain Command checks its own FastAPI endpoint since that is the externally-facing surface.

#### Dependency Ordering and Startup Sequence

Docker Compose `depends_on` with `condition: service_healthy` enforces startup order:

1. **QuestDB** and **Redis** start first (no dependencies)
2. **Captain Offline**, **Captain Online**, **Captain Command** start after QuestDB and Redis are healthy
3. **Captain GUI** runs independently (ephemeral build container)
4. **Nginx** starts after both `captain-command` is healthy AND `captain-gui` has completed successfully (`service_completed_successfully`)

The `captain-gui` container is ephemeral: it runs `npm run build` in a Node 20 Alpine stage, copies the `dist/` output to a shared `gui-dist` volume via an Alpine stage, then exits with code 0. Nginx uses `service_completed_successfully` (not `service_healthy`) because healthchecks are incompatible with containers that exit by design. This was a specific bug fix -- an earlier implementation attempted healthchecks on the build container, which always failed because Docker healthchecks only apply to long-running services.

#### Volume Architecture

```
gui-dist:          Shared volume -- captain-gui writes, nginx reads
vault-backup:      Named volume -- captain-command vault backups

./questdb/db       → /var/lib/questdb/db          (QuestDB data persistence)
./redis            → /data                         (Redis AOF persistence)
./shared           → /app/shared:ro                (Shared Python modules, read-only)
./config           → /captain/config:ro            (Configuration files)
./data             → /captain/data:ro              (Static data files)
./logs             → /captain/logs                 (Log output, writable)
./vault            → /captain/vault:ro             (Encrypted API credentials)
./<svc>/journal.sqlite → /captain/journal.sqlite   (Per-process crash recovery)
./scripts          → /captain/scripts:ro           (Only captain-offline, local override)
```

Each Captain process mounts its own `journal.sqlite` file for independent SQLite WAL crash recovery.

#### Dockerfile Pattern

All three Captain processes share an identical Dockerfile structure:
- Base image: `python:3.11-slim`
- System dependencies: `tzdata` (timezone), `curl` (health checks)
- Layer caching: `requirements.txt` copied and installed before application code
- Environment: `PYTHONUNBUFFERED=1`, `TZ=America/New_York`
- Entry point: `python -m captain_{offline|online|command}.main`

The GUI uses a multi-stage build: Stage 1 (Node 20) runs `npm ci && npm run build`, Stage 2 (Alpine 3.19) copies built assets and deploys them to the `gui-dist` volume on container start via `cp -r`.

#### Startup Script

`captain-start.sh` is a WSL 2 startup script that automates the full boot sequence:

1. Sets `vm.max_map_count >= 1048576` (required by QuestDB's memory-mapped I/O)
2. Waits up to 60 seconds for Docker Desktop daemon
3. Validates project directory and required files (`.env`, compose files, nginx conf)
4. Runs `docker compose up -d` with both compose files
5. Polls QuestDB SQL engine and Redis for readiness (60-second timeout)
6. Executes `init_questdb.py` via `captain-offline` container to create all tables (idempotent)
7. Waits for all 6 long-running services to reach `running` status (180-second timeout)
8. Verifies Captain Command API responds at `/api/health` (via Nginx and direct)

The script can be invoked by Windows Task Scheduler via `wsl.exe -d Ubuntu -- bash /mnt/c/.../captain-start.sh`.

---

### QuestDB -- Time-Series Database

#### Overview

QuestDB serves as the persistent data layer for the entire Captain System. It stores all historical data, model states, trade outcomes, and system parameters. QuestDB was chosen for its:

- Columnar storage optimized for time-series append-only patterns
- `LATEST ON` query syntax for efficient deduplication of append-only state tables
- PostgreSQL wire protocol compatibility (uses standard `psycopg2` driver)
- Sub-millisecond query performance on time-partitioned data
- Built-in web console for operational debugging (port 9000)

#### Connection Architecture

The shared module `shared/questdb_client.py` provides two access patterns:

**Connection Pool (hot path):**
```python
_CONNECT_KWARGS = dict(
    host=QUESTDB_HOST,          # "questdb" inside Docker, "localhost" outside
    port=QUESTDB_PORT,          # 8812
    user=QUESTDB_USER,          # "admin"
    password=QUESTDB_PASSWORD,  # "quest"
    database=QUESTDB_DB,        # "qdb"
    connect_timeout=5,          # 5-second TCP connect timeout
    options="-c statement_timeout=15000",  # 15-second query timeout
)
```

The `get_cursor()` context manager yields a cursor from a `ThreadedConnectionPool` (min=2, max=10 connections). All queries use `autocommit=True` since QuestDB's append-only architecture persists each INSERT immediately without explicit COMMIT. The pool uses thread-safe lazy initialization with double-checked locking.

**Standalone connection (startup only):**
`get_connection()` creates an unpooled connection used exclusively by `verify_connections()` during process startup. The caller is responsible for calling `conn.close()`.

#### JVMCI Compiler Fix

QuestDB runs on a JVM that includes the GraalVM JVMCI compiler. In containerized/WSL 2 environments, this compiler causes JVM segfaults under concurrent query load. The fix disables it via environment variable in docker-compose.yml:

```yaml
JAVA_TOOL_OPTIONS: "-XX:-UseJVMCICompiler"
```

This forces QuestDB to use the standard C2 JIT compiler, which is stable in containerized environments at the cost of slightly lower peak throughput -- an acceptable trade-off for a system that prioritizes reliability over microsecond latency.

#### Additional Configuration

```yaml
QDB_CAIRO_COMMIT_LAG: 1000      # Commit lag in milliseconds for WAL writes
QDB_LINE_TCP_ENABLED: "true"    # Enable InfluxDB line protocol ingestion
```

#### Schema -- 28 QuestDB Tables

The `scripts/init_questdb.py` script creates all tables using `CREATE TABLE IF NOT EXISTS` (idempotent). Tables are organized into three groups:

**Original Tables (P3-D00 through P3-D22, excluding D20):**

| Table | Name | Owner | Partitioning | Purpose |
|-------|------|-------|-------------|---------|
| D00 | `p3_d00_asset_universe` | Command | By `last_updated` | Asset configuration, strategy locks, session hours |
| D01 | `p3_d01_aim_model_states` | Offline B1 | By `last_updated` | 16 AIM model states per asset (status, warmup, modifiers) |
| D02 | `p3_d02_aim_meta_weights` | Offline B1 | By `last_updated` | Inclusion probability and effectiveness per AIM |
| D03 | `p3_d03_trade_outcome_log` | Online B7 | `PARTITION BY DAY` | Complete trade records (entry, exit, PnL, regime context) |
| D04 | `p3_d04_decay_detector_states` | Offline B2 | By `last_updated` | BOCPD, CUSUM, ADWIN states per asset |
| D05 | `p3_d05_ewma_states` | Offline B8 | By `last_updated` | Win rate, avg win/loss by asset x regime x session |
| D06 | `p3_d06_injection_history` | Offline B4 | `PARTITION BY MONTH` | Strategy injection candidates and outcomes |
| D06B | `p3_d06b_active_transitions` | Offline B4 | By `last_updated` | Active strategy transition phasing |
| D07 | `p3_d07_correlation_model_states` | Offline | By `last_updated` | DCC correlation matrix and parameters |
| D08 | `p3_d08_tsm_state` | Command | By `last_updated` | Trading System Manager per-account state (balances, limits, scaling) |
| D09 | `p3_d09_report_archive` | Command | `PARTITION BY MONTH` | Generated report storage |
| D10 | `p3_d10_notification_log` | Command | `PARTITION BY DAY` | Notification delivery tracking (GUI, Telegram, email) |
| D11 | `p3_d11_pseudotrader_results` | Offline B3 | `PARTITION BY MONTH` | Pseudotrader simulation results |
| D12 | `p3_d12_kelly_parameters` | Offline B8 | By `last_updated` | Kelly fraction by asset x regime x session |
| D13 | `p3_d13_sensitivity_scan_results` | Offline B5 | By `scan_date` | Robustness scan (Sharpe stability, PBO, DSR) |
| D14 | `p3_d14_api_connection_states` | Command | By `last_updated` | API adapter health (TopstepX, etc.) |
| D15 | `p3_d15_user_session_data` | Command | By `last_active` | User authentication and preferences |
| D16 | `p3_d16_user_capital_silos` | Command | By `last_updated` | Per-user capital allocation, risk limits, Kelly ceiling |
| D17 | `p3_d17_system_monitor_state` | Online/Command | By `last_updated` | Key-value system parameter store |
| D18 | `p3_d18_version_history` | Offline | `PARTITION BY MONTH` | Model version tracking with state hashes |
| D19 | `p3_d19_reconciliation_log` | Command | `PARTITION BY MONTH` | Position reconciliation audit trail |
| D21 | `p3_d21_incident_log` | Command | `PARTITION BY MONTH` | Incident tracking with root cause and resolution |
| D22 | `p3_d22_system_health_diagnostic` | Offline B9 | `PARTITION BY MONTH` | Health scores and action queue |

Note: D20 is SQLite WAL (not in QuestDB -- one `journal.sqlite` per process for crash recovery).

**V3 Amendment Tables:**

| Table | Name | Owner | Purpose |
|-------|------|-------|---------|
| D23 | `p3_d23_circuit_breaker_intraday` | Online B7B / Command B8 | Intraday circuit breaker state (loss tracking, breach counts) |
| D25 | `p3_d25_circuit_breaker_params` | Offline B8 | Circuit breaker model parameters (r_bar, beta_b, sigma) |
| D26 | `p3_d26_hmm_opportunity_state` | Offline B1 / Online B5 | HMM regime state, opportunity weights, prior alpha |

**Auxiliary Tables:**

| Table | Name | Owner | Purpose |
|-------|------|-------|---------|
| -- | `p3_offline_job_queue` | Offline orchestrator | Job queue for decay-triggered, scheduled, and manual tasks |
| -- | `p3_session_event_log` | Command B1/B5/B7/B8 | Command-side audit trail (signals, confirmations, TSM switches) |
| D27 | `p3_d27_pseudotrader_forecasts` | Offline B3 | Two-forecast structure (full history + rolling 252-day) |
| D28 | `p3_d28_account_lifecycle` | Shared (Offline B3, Command B8) | EVAL/XFA/LIVE stage transitions, fees, payouts, resets |

**QuestDB Type Conventions:**
- `SYMBOL` -- Indexed string, used for foreign-key-like fields (`asset_id`, `user_id`, `account_id`)
- `STRING` -- Unindexed string, used for JSON blobs and free text
- `TIMESTAMP` -- Microsecond precision, used as designated timestamp for `LATEST ON` queries
- `DOUBLE` -- 64-bit float for prices, fractions, and metrics
- `INT` / `LONG` -- 32-bit and 64-bit integers
- `BOOLEAN` -- true/false flags

---

### Redis -- Inter-Process Communication

#### Overview

Redis serves as the central nervous system of the Captain architecture, enabling real-time messaging between the three core processes without tight coupling. It runs as `redis:7-alpine` with append-only file persistence (`--appendonly yes --appendfsync everysec`).

#### Connection Architecture

The shared module `shared/redis_client.py` implements a module-level singleton with thread-safe double-checked locking:

```python
redis.Redis(
    host=REDIS_HOST,               # "redis" inside Docker
    port=REDIS_PORT,               # 6379
    decode_responses=True,         # Return strings, not bytes
    socket_timeout=5,              # 5s read/write timeout
    socket_connect_timeout=5,      # 5s TCP connect timeout
    retry_on_error=[TimeoutError], # Auto-retry on transient timeouts
    health_check_interval=30,      # Periodic PING every 30s to detect stale connections
)
```

All callers across all processes share a single connection pool (redis-py internally manages up to 50 connections per pool). The `get_redis_pubsub()` function returns a PubSub instance from the same singleton client.

#### Original Pub/Sub Channels (Legacy Constants)

The original design used five pub/sub channels. These constants remain defined in `redis_client.py` for reference:

| Constant | Channel Pattern | Publisher | Subscriber | Payload |
|----------|----------------|-----------|------------|---------|
| `CH_SIGNALS` | `captain:signals:{user_id}` | Online B6 | Command B1 | Signal batch (direction, size, TP/SL, per-account) |
| `CH_TRADE_OUTCOMES` | `captain:trade_outcomes` | Online B7 | Offline orchestrator | Trade outcome (trade_id, PnL, regime, AIM context) |
| `CH_COMMANDS` | `captain:commands` | Command B1 | Online + Offline | TAKEN/SKIPPED, strategy decisions, TSM, AIM control |
| `CH_ALERTS` | `captain:alerts` | Any process | Command | Alert with priority (CRITICAL/HIGH/MEDIUM/LOW) |
| `CH_STATUS` | `captain:status` | All processes | Command | Heartbeat + health status |

#### Redis Streams Migration (Current Implementation)

The critical channels were migrated from pub/sub to Redis Streams to provide message persistence, acknowledgment, and replay capabilities. Pub/sub's fire-and-forget semantics meant that a lost `captain:trade_outcomes` message could break the feedback loop, leaving EWMA, Kelly, and AIM states permanently stale.

Three streams with four consumer groups now handle the critical message paths:

| Stream | Consumer Group | Consuming Process | Purpose |
|--------|---------------|-------------------|---------|
| `stream:signals` | `command_signals` | Captain Command | Receive trading signals from Online |
| `stream:trade_outcomes` | `offline_outcomes` | Captain Offline | Receive trade results for model updates |
| `stream:commands` | `offline_commands` | Captain Offline | Receive user/system commands |
| `stream:commands` | `online_commands` | Captain Online | Receive user/system commands |

Key implementation details:
- `publish_to_stream()` uses `XADD` with `maxlen=1000` to cap stream length and prevent unbounded growth
- Payloads are JSON-serialized into a single `payload` field
- `ensure_consumer_group()` is called at startup in each process's `main.py`, using `XGROUP CREATE` with `mkstream=True` (idempotent -- catches `BUSYGROUP` errors silently)
- `read_stream()` uses `XREADGROUP` with `block=1000` (1-second blocking poll) and `count=10` (batch size)
- `ack_message()` calls `XACK` to remove processed messages from the pending entries list

The alerts (`captain:alerts`) and status (`captain:status`) channels remain on pub/sub since they are non-critical monitoring data where fire-and-forget semantics are acceptable.

An audit confirmed no legacy `client.publish()` calls remain for the three migrated channels. All services use `publish_to_stream()` exclusively.

---

### Nginx -- API Gateway

Nginx (`nginx:alpine`) serves as the entry point for all browser traffic, configured via `nginx-local.conf` for local deployment.

#### Routing

| Location | Backend | Purpose |
|----------|---------|---------|
| `/api/` | `captain-command:8000` | REST API proxy |
| `/api/auth/` | `captain-command:8000` | Authentication (stricter rate limit) |
| `/ws/` | `captain-command:8000` | WebSocket (HTTP 1.1 upgrade, 24-hour timeout) |
| `/` | Static files | SPA with `try_files` fallback to `index.html` |
| `*.(js\|css\|png\|...)` | Static files | Immutable asset caching (1 year) |

#### Rate Limiting

```
api zone:   30 req/s per IP, burst of 10 (nodelay)
auth zone:  5 req/min per IP, burst of 3 (nodelay)
```

#### WebSocket Configuration

The `/ws/` endpoint uses HTTP 1.1 upgrade headers with `proxy_read_timeout 86400` (24 hours), maintaining persistent connections for real-time GUI data streaming. The GUI WebSocket client is configured with `MAX_RECONNECT_ATTEMPTS = Infinity` to handle development restarts gracefully.

#### Security Headers

- `X-Frame-Options: DENY` -- Prevents clickjacking
- `X-Content-Type-Options: nosniff` -- Prevents MIME sniffing
- `X-XSS-Protection: 1; mode=block` -- XSS filter
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` -- Allows `self`, `ws://localhost:*`, `http://localhost:*` for connect-src
- `Permissions-Policy` -- Disables camera, microphone, geolocation

No HSTS header in local mode (no TLS). Production override would add TLS 1.3 and HSTS.

#### Caching Strategy

- HTML (`index.html`): `no-cache, no-store, must-revalidate` -- Users always get the latest SPA shell
- Static assets (JS, CSS, images, fonts): `expires 1y` with `Cache-Control: public, immutable`

---

### Connection Resilience

The infrastructure layer implements several patterns to achieve 24/7 stability under network instability, service restarts, and external API failures.

#### QuestDB Connection Pooling

`psycopg2.pool.ThreadedConnectionPool` (min=2, max=10) eliminates the original connection-per-query pattern that created hundreds of TCP connections per minute. The pool is a thread-safe singleton with lazy initialization. Connection parameters are centralized in `_CONNECT_KWARGS` with `connect_timeout=5` (seconds) and `statement_timeout=15000` (milliseconds). The 5-second connect timeout prevents indefinite blocking on dead connections; the 15-second statement timeout prevents threads from hanging on slow queries.

#### Redis Singleton

A module-level singleton with thread-safe double-checked locking replaces the original pattern of creating a new `redis.Redis` instance per call. The `socket_timeout=5`, `socket_connect_timeout=5`, `retry_on_error=[TimeoutError]`, and `health_check_interval=30` configuration provides automatic recovery from transient failures while detecting stale connections proactively.

#### Orchestrator Reconnection

Both Captain Offline and Captain Online command listeners wrap their Redis subscription loops in reconnection logic with exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s. This prevents connection storms while ensuring rapid recovery when Redis becomes available. Listeners handle shutdown signals gracefully during backoff cycles.

#### External API Retry

TopstepX REST API calls use the `tenacity` library with exponential backoff in `_do_post()`. TopstepX WebSocket streams implement a 60-second delayed reconnect after rapid failure cascades (5 failures within 10 seconds), preventing the permanent reconnection surrender that occurred with the original 5-attempt limit.

#### Docker Health Check Verification

All Dockerfiles for Captain processes include dual health checks that verify connectivity to both QuestDB and Redis (not just process liveness). Captain Command checks its own `/api/health` FastAPI endpoint. This ensures Docker's `service_healthy` condition accurately reflects the process's ability to function, not merely that it is running.

---

### Key Decisions

**Why QuestDB over PostgreSQL/TimescaleDB:** QuestDB's `LATEST ON` query syntax provides efficient deduplication over append-only state tables without requiring UPDATE statements. The append-only pattern means all 28 tables can use INSERT-only writes with `autocommit=True`, eliminating transaction overhead and simplifying crash recovery. QuestDB's columnar storage provides fast analytical queries over time-partitioned trade data.

**Why Redis Streams over pub/sub:** The original pub/sub design had no delivery guarantee -- a Redis disconnect or slow subscriber meant permanently lost messages. For the critical feedback loop (trade outcome from Online B7 -> Offline -> updated Kelly/EWMA/AIM -> next signal), message loss causes parameter drift and stale model states. Redis Streams provide persistence, consumer group acknowledgment, and replay of unacknowledged messages after reconnection.

**Why ephemeral GUI container:** Separating the React build step from runtime serving means Nginx serves pre-built static files directly without needing Node.js at runtime. This reduces memory footprint and attack surface. The `gui-dist` shared volume decouples build timing from Nginx availability.

**Why SQLite WAL per process:** Each Captain process maintains its own `journal.sqlite` for crash recovery (checkpointing). SQLite WAL is process-local, avoiding network round-trips and ensuring recovery data is always available even if QuestDB or Redis are temporarily unreachable. This provides a last-resort state recovery mechanism independent of the shared infrastructure.

**Why localhost-only bindings:** All ports are bound to `127.0.0.1` to enforce that access is only possible from the local machine (or via Nginx reverse proxy). This is a defense-in-depth measure complementing Docker's internal networking. TopstepX Terms of Service (section 28) prohibit VPS deployment, so the system must run locally on personal devices.

---

### Current State

The infrastructure is fully implemented and operational:

- **Docker Compose:** 7 services configured across base + local override files, with health checks, dependency ordering, memory limits, and volume mounts all in place
- **QuestDB:** 28 tables created via idempotent `init_questdb.py`, with connection pooling (2-10 connections), 5s/15s timeouts, and JVMCI compiler disabled
- **Redis:** Singleton client with Streams migration complete for three critical channels (`stream:signals`, `stream:trade_outcomes`, `stream:commands`); alerts and status remain on pub/sub
- **Nginx:** Reverse proxy with WebSocket support, rate limiting, security headers, and SPA caching strategy
- **Startup automation:** `captain-start.sh` handles the full boot sequence from `vm.max_map_count` tuning through API health verification
- **Vulnerability remediation:** All 12 identified vulnerabilities have been addressed (JVMCI fix, connection pooling, timeouts, Redis singleton, Streams migration, dual health checks, retry logic, reconnection backoff)

Key file paths:
- `/captain-system/docker-compose.yml` -- Base compose configuration
- `/captain-system/docker-compose.local.yml` -- Local override with memory limits
- `/captain-system/shared/questdb_client.py` -- QuestDB connection pool singleton
- `/captain-system/shared/redis_client.py` -- Redis singleton, Streams API, channel/stream constants
- `/captain-system/scripts/init_questdb.py` -- Schema initialization (28 tables)
- `/captain-system/nginx/nginx-local.conf` -- Nginx reverse proxy configuration
- `/captain-system/captain-start.sh` -- WSL 2 startup automation script
- `/captain-system/.env.template` -- Environment variable reference

---

## 5. Captain Offline -- Strategic Brain

### Spec Reference

The Captain Offline process is specified in `04_Program3_Offline.md` (original spec, OFF lines 1-1191), with V3 amendments in `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/Program3_Offline.md`, `Topstep_Optimisation_Functions.md`, `HMM_Opportunity_Regime_Spec.md`, and `Pseudotrader_Account_Awareness_Amendment.md`. The completion validation tracker (`docs/completion-validation-docs/CHANGE_TRACKER.md`) documents 87 resolved spec-to-code discrepancies across the full system, many of which touched Offline blocks.

### Process Architecture

Captain Offline runs as a single Docker container (`captain-offline`) that serves as the system's "Strategic Brain." Unlike Captain Online (real-time signal generation) and Captain Command (user interaction), Offline operates in the background processing trade outcomes and performing model maintenance to continuously improve system parameters.

**Entry Point:** `captain-system/captain-offline/captain_offline/main.py`

On startup, `main()` performs the following sequence:

1. Verifies QuestDB and Redis connectivity (exits on failure)
2. Initializes Redis Stream consumer groups (`GROUP_OFFLINE_OUTCOMES`, `GROUP_OFFLINE_COMMANDS`)
3. Calls `_seed_aim_states()` to ensure all 16 AIMs exist in P3-D01 for every asset in P3-D00 (idempotent)
4. Checks last journal checkpoint for crash recovery
5. Instantiates `OfflineOrchestrator` and calls `start()`, which blocks indefinitely
6. Registers SIGTERM/SIGINT handlers for graceful shutdown

Journal checkpoints track the lifecycle: `STARTUP` -> `AIMS_SEEDED` -> `ORCHESTRATOR_STARTED` -> `SHUTDOWN`.

**AIM Seeding:** The `_seed_aim_states()` function queries `p3_d00_asset_universe` for all active assets, then creates `p3_d01_aim_model_states` rows for all 16 AIMs per asset. Tier 1 AIMs (`{4, 6, 8, 11, 12, 15}`) are seeded with status `BOOTSTRAPPED` and `warmup_progress=1.0`; all others receive `INSTALLED` with `warmup_progress=0.0`. The function checks existing `(aim_id, asset_id)` pairs to avoid duplicate inserts. During initial deployment, this created 110 new rows across 11 assets, filling gaps where only AIM 4 (IVTS) had previously been initialized.

**Orchestrator Architecture:** `OfflineOrchestrator` (`captain-system/captain-offline/captain_offline/blocks/orchestrator.py`) runs two parallel execution paths:

- **Redis Stream Listener** (background daemon thread): Subscribes to `STREAM_TRADE_OUTCOMES` and `STREAM_COMMANDS` using consumer groups with durable delivery and acknowledgment. Reconnects with exponential backoff (1s -> 2s -> 4s -> ... -> 30s cap) on any connection failure, resetting to 1s on success.
- **Time-based Scheduler** (main thread): Polls every 60 seconds, executing tasks on four cadences:
  - **Daily** (after 16:00 ET): Drift detection, AIM lifecycle, warmup check, transition advancement, job dispatch
  - **Weekly** (Monday 00:00): Tier 1 AIM retrain, HDWM diversity check, system health diagnostic
  - **Monthly** (1st of month): Tier 2/3 AIM retrain, sensitivity scan on 252-day windows, monthly diagnostic
  - **Quarterly** (Jan/Apr/Jul/Oct): CUSUM recalibration using all historical in-control returns

The orchestrator maintains two stateful dictionaries:
- `_detectors: dict[str, tuple[BOCPDDetector, CUSUMDetector]]` -- per-asset decay detector instances
- `_active_transitions: dict[str, TransitionPhaser]` -- gradual strategy adoption phasers, resumed from QuestDB on startup

### Block-by-Block Implementation

#### B1: AIM Lifecycle, HMM, Diversity, DMA, and Drift Detection

The B1 block group spans five source files managing the 16 Adaptive Investment Models.

**B1 AIM Lifecycle** (`b1_aim_lifecycle.py`, task P3-PG-01)

Implements a 7-state machine for each AIM:

```
INSTALLED -> COLLECTING -> WARM_UP -> ELIGIBLE -> ACTIVE
BOOTSTRAPPED -> ACTIVE (shortcut via asset_bootstrap)
ACTIVE <-> SUPPRESSED (auto-recovery)
```

Key functions:
- `_load_aim_states(asset_id)` -- Queries P3-D01 for all AIM states of an asset, returning status, warmup_progress, current_modifier, last_retrained, missing_data_rate_30d
- `_load_meta_weight(aim_id, asset_id)` -- Reads inclusion_probability from P3-D02
- `_update_aim_status(aim_id, asset_id, new_status)` -- Inserts a new row into P3-D01 (append-only audit trail, not UPDATE)
- `run_aim_lifecycle(asset_id)` -- Daily lifecycle check across all AIMs for an asset
- `run_tier_retrain(asset_id, aim_ids)` -- Scheduled retraining for specific AIM tiers

Constants:
- `SUPPRESSION_CONSECUTIVE_ZERO = 20` -- Suppress after 20 consecutive trades with zero meta-weight
- `RECOVERY_WEIGHT_THRESHOLD = 0.1` -- Recovery requires meta-weight above this
- `RECOVERY_CONSECUTIVE = 10` -- Recovery requires 10 consecutive above-threshold trades
- `TIER_1_AIMS = {4, 6, 8, 11, 12, 15}` -- VRP, Economic Calendar, Cross-Asset Correlation, Regime Warning, Dynamic Costs, Opening Volume
- `TIER_23_AIMS` -- Remaining AIMs requiring monthly retraining

Warmup thresholds vary by AIM complexity: 50 trades (default), 100 trades (AIM-05), 240 trades (AIM-16 HMM). The `ELIGIBLE -> ACTIVE` transition requires explicit user activation via GUI, preventing AIMs from automatically generating trading signals.

State persistence uses an INSERT-based pattern into `p3_d01_aim_model_states` rather than UPDATE, maintaining a complete time-series audit trail of every status transition.

**B1 AIM-16 HMM** (`b1_aim16_hmm.py`, task P3-PG-01C)

Trains a 3-state Hidden Markov Model to classify session-level opportunity regimes using Baum-Welch Expectation-Maximization.

Hidden states (K=3):
- State 0: `LOW_OPP` -- Few signals, low OO, choppy markets
- State 1: `NORMAL` -- Average signal rate, moderate OO
- State 2: `HIGH_OPP` -- Many signals, high OO, trending markets

Observation vector (7 dimensions per session window):
1. Signal count
2. Mean OO (out-of-sample objective)
3. Volume z-score
4. VIX level
5. Prior session PnL
6. Cross-asset correlation
7. Day of week

Parameters:
- `N_STATES = 3`, `N_FEATURES = 7`
- `TRAINING_WINDOW_DAYS = 60` (240 session observations at 4 sessions/day: APAC, London, NY Pre, NY Open)
- `MAX_EM_ITERATIONS = 100`, `CONVERGENCE_THRESHOLD = 1e-6`
- `SMOOTHING_ALPHA = 0.3`, `FLOOR_PER_SESSION = 0.05`

Training algorithm: Each EM iteration performs Forward-Backward passes with O(T x K^2) complexity, computing alpha (forward probabilities), beta (backward probabilities), gamma (state posteriors), and xi (transition posteriors). The algorithm maintains three parameter sets: initial state probabilities (pi), transition matrix (A), and Gaussian emission parameters (mu, sigma per state per feature).

Supervised initialization uses realized PnL percentiles: >75th percentile sessions labeled `HIGH_OPP`, <25th labeled `LOW_OPP`, remainder `NORMAL`. This provides better starting parameters than random initialization.

Cold start protection:
- `< 20 trading days`: HMM disabled, uniform opportunity weights used
- `20-59 days`: HMM predictions blended 50/50 with uniform priors
- `>= 60 days`: Full HMM inference activated

State inference computes P(HIGH_OPP) as opportunity weight for session allocation. Results written to `p3_d26_hmm_opportunity_state`. Runs during monthly Tier 2/3 AIM retraining.

**B1 HDWM Diversity** (`b1_hdwm_diversity.py`, task P3-PG-03)

Weekly check ensuring ensemble diversity across six seed types:

```python
SEED_TYPES = {
    "options": [1, 2, 3],
    "microstructure": [4, 5, 15],
    "macro_event": [6, 7],
    "cross_asset": [8, 9],
    "temporal": [10, 11],
    "internal": [12, 13, 14],
}
# AIM-16 (HMM) is standalone -- not part of diversity groups
```

If ALL AIMs of a seed type are SUPPRESSED, the function `_reactivate_aim()` force-reactivates the one with the highest `recent_effectiveness` from P3-D02 to maintain ensemble diversity. Reactivation assigns equal weight: `1.0 / (num_active + 1)`.

Key functions:
- `_get_aim_status(aim_id, asset_id)` -- Current status from P3-D01
- `_get_recent_effectiveness(aim_id, asset_id)` -- Effectiveness metric from P3-D02
- `_count_active_aims(asset_id)` -- Count of ACTIVE AIMs
- `run_hdwm_diversity_check(asset_id)` -- Main entry point, called weekly

**B1 DMA Update** (`b1_dma_update.py`, task P3-PG-02)

Updates AIM inclusion probabilities using Dynamic Model Averaging after each trade outcome.

Parameters:
- `DEFAULT_LAMBDA = 0.99` -- Forgetting factor
- `DEFAULT_INCLUSION_THRESHOLD = 0.02` -- Below this, `inclusion_flag` set to False
- `Z_CLAMP = 3.0` -- Maximum z-score magnitude for likelihood computation

Algorithm: Loads all active AIM weights from P3-D02, computes z-score-based likelihood for each AIM's prediction accuracy on the trade outcome, applies forgetting factor, and renormalizes across all active AIMs. The magnitude-weighted likelihood (SPEC-A9) maps clamped z-scores to [0, 1] probabilities.

Reads: P3-D03 (trade outcome), P3-D02 (current weights), P3-D05 (EWMA stats). Writes: P3-D02 (updated weights).

**B1 Drift Detection** (`b1_drift_detection.py`, task P3-PG-04)

Daily per-AIM concept drift detection using AutoEncoder reconstruction error monitored by ADWIN (Adaptive Windowing, Bifet & Gavalda 2007).

Parameters:
- `DRIFT_REDUCTION_FACTOR = 0.5` -- Multiply inclusion_probability by 0.5 on drift
- `ADWIN_DELTA = 0.002` -- ADWIN confidence parameter

The `ADWINDetector` class wraps `river.drift.ADWIN` when available, falling back to a simple two-window comparison with a 500-element deque. On drift detected: (1) flag AIM for retraining, (2) reduce inclusion_probability by 50%, (3) renormalize all DMA weights. Drift reduces meta-weight but does NOT change AIM status from ACTIVE.

#### B2: BOCPD and CUSUM Decay Detection

The B2 block group implements dual decay detection through two complementary statistical methods.

**B2 BOCPD** (`b2_bocpd.py`, task P3-PG-05)

Bayesian Online Changepoint Detection (Adams & MacKay 2007) maintains a posterior distribution over run length r_t (trades since last changepoint).

Parameters:
- `DEFAULT_HAZARD_RATE = 1/200` -- Prior belief: expected 200 trades between changepoints
- `MAX_RUN_LENGTH = 500` -- Maximum tracked run length states

Core data structures:
- `NIGPrior` dataclass: Normal-Inverse-Gamma sufficient statistics (mu, kappa, alpha, beta)
- `BOCPDDetector` class: Maintains `run_length_posterior` (500-element numpy array), per-state NIG priors, `cp_probability` (posterior mass at r=0), and `cp_history` (list of historical changepoint probabilities)

Algorithm per observation:
1. Compute Student-t predictive probability P(x | NIG prior) for each run length using `scipy.stats.t.pdf`
2. Growth: P(r+1) = P(r) * pred * (1 - H) where H = hazard_rate
3. Changepoint: P(0) = sum(P(r) * pred * H) across all run lengths
4. Normalize posterior
5. Update NIG sufficient statistics analytically

The `initialize()` method sets NIG priors from in-control returns (mu = mean, beta = variance). The `run_bocpd_update()` function processes per-contract PnL (removing sizing bias) and persists `cp_probability` and 100-element `cp_history` to `p3_d04_decay_detector_states`.

**B2 CUSUM** (`b2_cusum.py`, tasks P3-PG-06/07)

Distribution-free two-sided CUSUM for persistent mean-shift detection, complementary to BOCPD.

Parameters:
- `BOOTSTRAP_B = 2000` -- Bootstrap replications for calibration
- `ARL_0 = 200` -- Target average run length under H0
- `MAX_SPRINT = 100` -- Maximum consecutive above-zero observations tracked

`CUSUMDetector` class implements:
```
C_up   = max(0, C_up_prev + x - k)
C_down = max(0, C_down_prev - x - k)
```
where `k = allowance = std / 2` (half the in-control standard deviation). Sequential control limits h(sprint_length) are calibrated quarterly via bootstrap. A `BREACH` signal fires when either C_up or C_down exceeds h, then both accumulators reset.

The `calibrate_and_persist()` function runs quarterly, performing B=2000 bootstrap simulations to determine control limits that achieve ARL_0=200 under the null hypothesis.

**B2 Level Escalation** (`b2_level_escalation.py`, task P3-PG-08)

Interprets BOCPD and CUSUM outputs to trigger escalating responses:

- **Level 2** (`cp_prob > 0.8`): Autonomous sizing reduction. Formula: `reduction_factor = max(0.5, 1.0 - (severity - 0.8) * 2.5)`. At severity=0.85 the factor is 0.875; at 0.90 it is 0.75; at 1.00 it hits the floor of 0.5. Written to `P3-D12.sizing_override`.
- **Level 3** (`cp_prob > 0.9` for 5+ consecutive trades): Trading halt. Sets `captain_status = DECAYED` in P3-D00, schedules P1/P2 rerun job, and triggers AIM-14 auto-expansion. Publishes CRITICAL alert via Redis `CH_ALERTS`.

Both levels log events to `P3-D04.decay_events` as JSON with timestamp, asset, level, severity, and source.

#### B3: Pseudotrader

**File:** `captain-system/captain-offline/captain_offline/blocks/b3_pseudotrader.py` (tasks P3-PG-09, P3-PG-09B, P3-PG-09C)

The pseudotrader implements counterfactual replay in three modes:

**PG-09 Baseline:** Replays historical trades with CURRENT vs PROPOSED parameters. Computes sharpe_improvement, drawdown_change, winrate_delta, PBO (Probability of Backtest Overfitting via CSCV with S=16 splits), and DSR (Deflated Sharpe Ratio). Decision rule: ADOPT if sharpe > 0 AND pbo < 0.5 AND dsr > 0.5, else REJECT.

**PG-09B Circuit Breaker Extension (V3):** Replays at intraday resolution with and without circuit breaker layers, tracking blocked trades and per-layer breakdown across all 4 CB layers (hard halt, budget, basket expectancy, correlation Sharpe).

**PG-09C Grid Search (V3):** Sweeps over CB parameters (c, lambda) to find optimal configuration.

**Account-Aware Replay:** The `run_account_aware_replay()` function enforces Topstep qualification pathway constraints during historical replay:
- **DLL (Daily Loss Limit):** Halts same-day trading after $3,000 loss
- **MDD (Max Drawdown Limit):** Permanently stops trading after $4,500 total drawdown
- **XFA Contract Scaling:** Proportionally reduces P&L when position size exceeds tier limits (30 micros at tier 1, scaling to 150 micros at tier 5 at $154.5k+)
- **Trading Hours:** Blocks entries after 15:55 EST buffer, enforces flat-by 16:10 EST
- **Consistency Rules:** Flags days exceeding $4,500 profit

**LIVE Capital Unlock:** LIVE accounts start with $30,000 tradable balance with remaining funds held in 4 reserve blocks. Each $9,000 profit milestone unlocks one block, transferring reserve_per_block from reserve_balance to tradable_balance. Mirrors `MultiStageTopstepAccount._check_live_unlock()` from `shared/account_lifecycle.py`.

**Two-Forecast Structure:** `generate_dual_forecasts()` produces two standardized forecasts stored in `p3_d27_pseudotrader_forecasts`:
- **Forecast A** (full history): Spans 2009-present using fixed capital. Monthly equity curve aggregation reduces storage from 4000+ daily points to ~200 monthly points. Includes Sharpe, Sortino, Calmar, profit factor, win rate, expectancy, and 15+ other metrics.
- **Forecast B** (rolling 252-day): Provides recent performance with momentum_indicator (60-day rolling Sharpe slope), current_regime identification, regime_distribution percentages, and consecutive winning/losing streak counts.

The `_build_system_state_snapshot()` function captures pipeline parameters and AIM weights from P3-D02, generating a SHA256 hash for version comparison. `_forecast_caveats()` generates warnings for hypothetical performance, retroactive constraint application, regime concentration >80%, and short windows <100 days.

**Validation Results:** Pre-deployment testing processed 14,815 trades across 11 futures assets spanning 2009-2025. Seven of 11 assets successfully reached XFA stage; ZT failed 17 consecutive EVAL attempts. All 24 unit tests passed covering DLL, MDD, scaling, trading hours, consistency rules, and eval account logic.

Reads: P3-D03 (trade outcomes), P3-D25 (CB params). Writes: P3-D11 (pseudotrader results), P3-D27 (forecasts).

#### B4: Injection Comparison and Transition Phasing

**File:** `captain-system/captain-offline/captain_offline/blocks/b4_injection.py` (tasks P3-PG-10/11)

**PG-10 Injection Comparison:** Compares new strategy candidate against current using AIM-adjusted expected edge. Decision thresholds:
- `ADOPT_RATIO = 1.2` -- New must exceed 1.2x current expected edge AND pbo < 0.5
- `PARALLEL_RATIO = 0.9` -- Between 0.9x and 1.2x triggers PARALLEL_TRACK (20 days monitoring)
- Below 0.9x: REJECT

The `_compute_aim_adjusted_edge()` function applies DMA-weighted AIM modifiers retroactively to historical performance: `expected_edge = mean(pnl) * mean(modifier)`.

**PG-11 Transition Phasing:** `TransitionPhaser` class manages gradual strategy adoption:
- Linear ramp over `DEFAULT_TRANSITION_DAYS = 10` days
- `weight_new(d) = d / transition_days`
- `blended_size = weight_new * size_new + weight_old * size_old`
- Direction follows new strategy throughout
- Parallel tracking mode: 20 days, current strategy executed, candidate logged only
- State persisted to QuestDB; `load_active()` resumes incomplete transitions on startup

The orchestrator stores active phasers in `_active_transitions` and calls `_advance_transitions()` daily, removing completed phasers and logging progress.

#### B5: Sensitivity Scanner

**File:** `captain-system/captain-offline/captain_offline/blocks/b5_sensitivity.py` (task P3-PG-12, AIM-13)

Monthly automated robustness scan that perturbs locked strategy parameters across a 7-point grid: `[-20%, -10%, -5%, 0%, +5%, +10%, +20%]` applied to SL and TP multipliers.

Stability metric: Coefficient of Variation (CV) of Sharpe ratios across the perturbation grid.

Anti-overfitting checks:
- PBO via CSCV with `S=8` splits (delegated to `shared.statistics.compute_pbo`)
- DSR (Deflated Sharpe Ratio, delegated to `shared.statistics.compute_dsr`)

Fragility determination: `FRAGILE` if 2 or more flags fire (sharpe_stability > 0.5, pbo > 0.5, dsr < 0.5). On FRAGILE, AIM-13 modifier set to `0.85` (15% reduction).

The `_backtest_perturbed()` function loads replay context and applies delta perturbation to locked strategy SL/TP multipliers, running `SignalReplayEngine.strategy_replay()` when available, falling back to return scaling `r * (1 + delta)` when replay context cannot be loaded.

Reads: P3-D00, P3-D01, P3-D03. Writes: P3-D13 (scan results), P3-D01 (AIM-13 modifier).

#### B6: Auto-Expansion (AIM-14)

**File:** `captain-system/captain-offline/captain_offline/blocks/b6_auto_expansion.py` (task P3-PG-13)

Triggered by Level 3 decay detection. Generates replacement strategy candidates using theory-constrained Genetic Algorithm with rough sets search.

GA Parameters:
- `POPULATION_SIZE = 100`, `GENERATIONS = 50`
- `CROSSOVER_RATE = 0.8`, `MUTATION_RATE = 0.1`
- `TOURNAMENT_SIZE = 5`, `TOP_K_CANDIDATES = 5`
- `SEED = 42`

Search space: OR_window (3-15 min), threshold (0.05-0.30), SL multiplier (0.20-0.50), TP multiplier (0.50-1.50), feature index (top 10 features).

Validation uses walk-forward double out-of-sample testing. Final OOS test runs ONCE per Paper 161. Acceptance: pbo < 0.5 AND dsr > 0.5. Viable candidates feed into injection comparison (Block 4).

The orchestrator calls `_run_aim14_expansion()` from the job dispatcher, loading trade returns from P3-D03, splitting 80/20 for training/holdout, and requiring a minimum of 60 returns.

#### B7: TSM Simulation

**File:** `captain-system/captain-offline/captain_offline/blocks/b7_tsm_simulation.py` (task P3-PG-14)

Estimates pass_probability for prop firm evaluations via block bootstrap Monte Carlo simulation.

Parameters:
- `N_PATHS = 10,000` simulation paths
- `BLOCK_SIZES = [3, 5, 7]` -- Random block sizes preserving autocorrelation
- `SEED = 42`

The `_block_bootstrap_path()` function generates paths by sampling contiguous blocks of random size from historical trade returns, preserving serial correlation structure. Each path is simulated against account constraints (MDD breach, MLL breach), with pass defined as surviving constraints AND reaching profit target.

Risk goal alert thresholds:
- `PASS_EVAL`: pass_prob < 0.3 triggers CRITICAL alert, < 0.5 triggers HIGH
- `GROW_CAPITAL`: ruin_prob > 0.3 triggers HIGH
- `PRESERVE_CAPITAL`: pass_prob < 0.7 triggers HIGH

The orchestrator invokes `_run_tsm_for_account()` both after trade outcomes and on TSM_CHANGE command events. It loads TSM config from `p3_d08_tsm_state` and trade returns from `p3_d03_trade_outcome_log`, requiring a minimum of 10 trades before running simulation.

Reads: P3-D03, P3-D08, P3-D12. Writes: P3-D08 (pass_probability, simulation_date).

#### B8: Kelly Parameter Update and CB Parameter Estimation

**Kelly Update** (`b8_kelly_update.py`, task P3-PG-15)

Executes after every trade outcome, implementing adaptive EWMA with BOCPD integration.

Algorithm:
1. Normalize PnL to per-contract (removes sizing bias)
2. Fetch current BOCPD changepoint probability from P3-D04
3. Compute adaptive EWMA alpha using SPEC-A12 span thresholds:
   - `cp_prob < 0.2`: span=30 (alpha=0.0645, slow learning, stable regime)
   - `cp_prob < 0.5`: span=20 (alpha=0.0952, default)
   - `cp_prob < 0.8`: span=12 (alpha=0.1538, elevated instability)
   - `cp_prob >= 0.8`: span=8 (alpha=0.2222, near-changepoint, fast adaptation)
4. Update EWMA for `[asset][regime][session]` cell: win_rate, avg_win, avg_loss, n_trades
5. Recompute Kelly fraction for ALL 6 regime/session combinations (2 regimes x 3 sessions)
6. Update asset-level shrinkage factor

Kelly formula: `f* = p - (1-p)/b` where `b = avg_win/avg_loss`. Returns 0 if no edge.

Shrinkage: `max(0.3, 1.0 - 1/sqrt(N))` where N = total asset trades. `SHRINKAGE_FLOOR = 0.3`. Approaches 1.0 as data accumulates.

Observed Kelly values from bootstrapped data:
- ES: 0.038-0.059 (conservative 4-6%, thin edge, high win rate 54-55%)
- ZN: 0.18-0.29 (moderate-aggressive, trend-following profile)
- ZB: 0.16-0.22 (moderate, with 0.958 shrinkage)

EWMA states stored in `p3_d05_ewma_states` with 6 cells per asset (LOW_VOL/HIGH_VOL x NY/LON/APAC). Kelly fractions stored in `p3_d12_kelly_parameters`. Both use `version_snapshot.snapshot_before_update()` for audit trail.

**CB Parameter Estimation** (`b8_cb_params.py`, task P3-PG-16C)

Estimates per-account per-model circuit breaker parameters from trade history:
- `r_bar`: Unconditional mean return per trade
- `beta_b`: Loss-predictiveness coefficient via OLS regression (r_{j+1} on L_b)
- `sigma`: Per-trade return standard deviation
- `rho_bar`: Average same-day trade correlation

Beta_b interpretation: positive means losses predict losses (shut basket); negative means mean reversion (keep open). Significance gate: `p_value > 0.05 OR n_obs < 100` forces `beta_b = 0`. Cold start: `beta_b = 0, rho_bar = 0` (CB layers 3-4 disabled, layers 1-2 active).

The `_ols_regression()` function implements simple OLS with standard error computation and t-test for significance. Minimum 100 observations required (`MIN_OBSERVATIONS = 100`).

Reads: P3-D03. Writes: P3-D25 (circuit_breaker_params).

#### B9: System Health Diagnostic

**File:** `captain-system/captain-offline/captain_offline/blocks/b9_diagnostic.py` (task P3-PG-16B)

Eight-dimension diagnostic with `QUEUE_ACTION` helper for human action items.

Dimensions:
- **D1 Strategy Portfolio Health:** Diversity across strategy types, freshness of locked parameters, OO scores. Weakness threshold: `OO_WEAKNESS_THRESHOLD = 0.55`.
- **D2 Feature Portfolio Health:** Distinct features in use, feature reuse across AIMs, active decay flags.
- **D3 Model Staleness:** P1/P2 model ages (`STALENESS_MEDIUM_DAYS = 90`, `STALENESS_HIGH_DAYS = 180`), regime model recency, AIM retrain recency.
- **D4 AIM Effectiveness:** Active AIM count, dormant AIMs (weight < 0.05 for 30+ days), dominant AIMs (weight > 0.30), warmup progress.
- **D5 Edge Trajectory:** 30/60/90-day rolling edge, trend direction, regime breakdown. MONTHLY ONLY. Decline threshold: `EDGE_DECLINE_THRESHOLD = 0.15`.
- **D6 Data Coverage Gaps:** AIM missing data rates (30-day), asset data holds.
- **D7 Research Pipeline:** Injection recency, unresolved Level 3 decay events.
- **D8 Resolution Verification:** Resolved action items verified, stale detection (`ACTION_STALE_DAYS = 90`).

Schedule: WEEKLY runs D1-D4, D6-D8. MONTHLY runs all D1-D8 including D5 edge trajectory.

The `_queue_action()` helper adds or updates action items with deduplication, attaching priority (CRITICAL/HIGH/MEDIUM/LOW), category, dimension, constraint type, title, detail, recommendation, and optional metric snapshot.

Reads: P2-D06, P2-D07, P3-D00 through D06, D13, D17, D22. Writes: P3-D22 (diagnostic results).

### Bootstrap and Seeding

**File:** `captain-system/captain-offline/captain_offline/blocks/bootstrap.py`

The `asset_bootstrap()` function initializes statistical state for new trading assets from historical data:

1. **Minimum data gate:** Requires 20+ historical trades (`MIN_BOOTSTRAP_TRADES = 20`)
2. **EWMA initialization:** Creates 6 cells (2 regimes x 3 sessions) in `p3_d05_ewma_states`. Cells with fewer than 5 trades (`MIN_PER_CELL_TRADES = 5`) fall back to unconditional statistics computed from all returns.
3. **BOCPD/CUSUM initialization:** Sets NIG prior mu to mean returns, beta to variance, with initial cp_probability of 0.01. CUSUM allowance set to `std * 0.5`.
4. **Kelly computation:** Computes initial Kelly fractions per regime/session with shrinkage: `max(0.3, 1.0 - 1/sqrt(n_trades))`.
5. **Tier 1 AIM activation:** Sets AIMs {4, 6, 8, 11, 12, 15} to BOOTSTRAPPED status.

The `asset_warmup_check()` function runs daily, validating four conditions for WARM_UP -> ACTIVE transition:
1. EWMA baseline exists (6 cells populated)
2. Tier 1 AIMs ready (all have BOOTSTRAPPED or ACTIVE status)
3. Regime model available
4. P1/P2 pipeline validated

Warmup progress tracked as fraction of conditions met (0.0 to 1.0).

**Seeding Script:** `captain-system/scripts/seed_real_asset.py` loads ES historical data from P1/P2 files (d22_trade_log_es.json, p2_d02_regime_labels.json, p2_d06_locked_strategy.json, p2_d08_classifier_validation.json) and calls `asset_bootstrap()`. Maps D-22 fields (trade_date, r_mi) to bootstrap format (date, r) and D-02 labels (LOW/MEDIUM/HIGH) to volatility regimes (LOW_VOL/HIGH_VOL). Supports `--dry-run` flag and Docker-mounted data volumes.

### Command Handling

The orchestrator processes five command types received via Redis `STREAM_COMMANDS`:

| Command | Handler | Action |
|---------|---------|--------|
| `ASSET_ADDED` | `_handle_asset_added()` | Calls `asset_bootstrap()` with historical trades and regime labels |
| `INJECTION` | `_handle_injection()` | Calls `run_injection_comparison()` for candidate vs current strategy |
| `ADOPTION_DECISION` | `_handle_adoption()` | Creates `TransitionPhaser` for ADOPT/PARALLEL_TRACK, ignores REJECT |
| `TSM_CHANGE` | `_run_tsm_for_account()` | Re-runs Monte Carlo simulation for account |
| `ACTIVATE_AIM` / `DEACTIVATE_AIM` | `_handle_aim_activation()` | Updates status for aim_id across ALL assets via `_update_aim_status()` |
| `ACTION_RESOLVED` | `run_diagnostic("WEEKLY")` | Triggers D8 verification diagnostic |

### Job Dispatch

The `_dispatch_pending_jobs()` function runs daily, reading from `p3_offline_job_queue` where `status = 'PENDING'`:

- `AIM14_EXPANSION`: Executes automatically via `_run_aim14_expansion()`, which loads returns from P3-D03, splits 80/20, and calls `run_auto_expansion()`. Requires minimum 60 returns.
- `P1P2_RERUN`: Logged as `AWAITING_MANUAL` -- requires external pipeline execution. Cannot be automated within Offline.

Jobs transition through states: `PENDING -> RUNNING -> COMPLETED/FAILED/AWAITING_MANUAL`.

### Key Decisions

1. **INSERT-only persistence:** All QuestDB writes use INSERT rather than UPDATE, creating append-only audit trails. Latest state retrieved via `ORDER BY last_updated DESC LIMIT 1` queries.

2. **Per-contract PnL normalization:** Both BOCPD and Kelly updates normalize trade PnL by dividing by contract count, removing sizing bias so decay detection and parameter estimation reflect strategy quality rather than position size changes.

3. **Adaptive EWMA via BOCPD integration:** The SPEC-A12 adaptive alpha mechanism links Kelly parameter learning speed to changepoint probability. Near changepoints (cp_prob > 0.8), the EWMA span drops to 8, enabling rapid parameter adaptation. During stable regimes, span=30 provides smooth updates.

4. **Dual decay detection:** BOCPD provides probabilistic changepoint detection with Student-t predictive distributions; CUSUM provides distribution-free mean-shift detection. The combination reduces false negatives since each method catches different failure modes.

5. **Conservative cold start:** HMM disabled for <20 days, CB layers 3-4 disabled without beta_b data, Kelly shrinkage floors at 0.3 with limited data. The system progressively unlocks capabilities as data accumulates.

6. **User Kelly ceiling of 15%:** Capital silo configuration caps all Kelly fractions at 0.15, overriding calculated values. ES (natural Kelly ~5%) passes through unchanged, while ZN (~29%) gets halved to 15%.

### Critical Fixes

1. **AIM Seeding Gap:** Initial deployment only had AIM 4 (IVTS) entries in P3-D01. The `_seed_aim_states()` function was added to `main.py` to create all 16 AIM entries per asset on startup, resolving GUI panels displaying identical AIM identifiers. Created 110 new rows across 11 assets.

2. **Pseudotrader Spec-to-Implementation Gaps:** Five gaps identified and resolved:
   - Capital unlock for LIVE accounts (profit-target $9k milestones) -- implemented in `run_account_aware_replay()`
   - Two-forecast structure (Forecast A full history, Forecast B rolling 252-day) -- implemented in `generate_dual_forecasts()` writing to P3-D27
   - Version tracking via SHA256 state snapshots -- implemented in `_build_system_state_snapshot()`
   - Runner script code duplication -- `run_pseudotrader_backtest.py` reimplemented logic inline instead of calling B3 functions (identified as tech debt)
   - P3-D03 integration -- validation currently uses synthetic P1 data; live trade replay requires deployed system

3. **Redis Connection Resilience:** The Redis listener was enhanced with automatic reconnection using exponential backoff (1s -> 30s cap) on connection failures. Previously, any Redis error terminated the listener thread permanently, requiring a full process restart.

### Current State

As of 2026-03-24, the Captain Offline process is operationally deployed with the following state:

- **Assets:** 11 active in `p3_d00_asset_universe` (ES, MES, NQ, MNQ, M2K, MYM, ZN, ZB, ZT, NKD, MGC)
- **AIMs:** 176 total entries (11 assets x 16 AIMs). Tier 1 AIMs BOOTSTRAPPED; remainder INSTALLED
- **EWMA:** Populated from historical backtest data. ES shows 449-998 trade samples with 54-55% win rates. ZN/ZB have complete data with trend-following profiles
- **Kelly:** ES fractions at 0.038-0.059 (conservative); ZN at 0.18-0.29; ZB at 0.16-0.22. All bootstrapped 2026-03-22
- **BOCPD/CUSUM:** Initialized from in-control returns with cp_probability at 0.01 (no active changepoints)
- **Trade Outcome Log:** Zero live trades in P3-D03. EWMA n_trades values represent historical backtest samples, not live trading. B5B quality gate defaults to 50% data maturity (cold-start floor `max(0.5, trade_count/50)`)
- **Capital Silo:** $150,000 capital, 15% Kelly ceiling, 10% max portfolio risk, 3 simultaneous positions maximum
- **Orchestrator:** Running event loop with Redis subscriber (reconnection-resilient) and time-based scheduler. All scheduled tasks operational. TransitionPhaser resume-on-startup verified

---

## 6. Captain Online -- Signal Engine

### Spec Reference

The Captain Online process is specified in `05_Program3_Online.md` (original spec, located at `docs/completion-validation-docs/Step 1 - Original Specs/05_Program3_Online.md`). V3 amendments affecting Online are spread across multiple files in `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/`, with the most significant being:

- `Topstep_Optimisation_Functions.md` (Parts 4-6): 7-layer circuit breaker rewrite (B5C)
- `Nomaan_Edits_Fees.md` (Change 2): Fee integration in B4 Kelly sizing and B7 commission resolution
- `HMM_Opportunity_Regime_Spec.md`: AIM-16 HMM session allocation in B5
- `Cross_Reference_PreDeploy_vs_V3.md`: Consolidated V3 amendment mapping for Online blocks

The block-to-spec-section mapping is:

| Block | Spec Section | Lines |
|-------|-------------|-------|
| B1 Data Ingestion | P3-PG-21 | ON 580-612 |
| B2 Regime Probability | P3-PG-22 | ON 616-656 |
| B3 AIM Aggregation | P3-PG-23 | ON 660-706 |
| B4 Kelly Sizing | P3-PG-24 | ON 710-892 |
| B5 Trade Selection | P3-PG-25 | ON 896-968 |
| B5B Quality Gate | P3-PG-25B | ON 972-1072 |
| B5C Circuit Breaker | P3-PG-27B | V3 Amendment |
| B6 Signal Output | P3-PG-26 | ON 1076-1177 |
| B7 Position Monitor | P3-PG-27 | ON 1181-1345 |
| Orchestrator | P3-PG-20 | ON 1349-1430 |

Source files are located under `captain-system/captain-online/captain_online/blocks/`.

---

### Process Architecture

Captain Online is the signal generation engine of the Captain system. It runs as a standalone Docker container (`captain-system-captain-online-1`) with a singular purpose: monitor live market data and produce trading signals at session open times. It does not handle user interaction or trade execution; those responsibilities belong to Captain Command.

**Process entry point:** `captain-system/captain-online/captain_online/main.py`

On startup, the process executes the following initialization sequence:

1. Verify QuestDB connectivity (exit on failure).
2. Verify Redis connectivity (exit on failure).
3. Initialize Redis Stream consumer groups (`STREAM_COMMANDS` / `GROUP_ONLINE_COMMANDS`).
4. Authenticate with TopstepX API via `get_topstep_client().authenticate()`.
5. Resolve all active contract IDs via `preload_contracts()`.
6. Create a single `MarketStream` WebSocket subscribed to all contract IDs simultaneously, populating `quote_cache`.
7. Instantiate and start `OnlineOrchestrator`, which blocks in the main thread running the 24/7 session loop.

Journal checkpoints track the lifecycle: `STARTUP` -> `STREAMS_STARTED` -> orchestrator running. Signal handlers for SIGTERM and SIGINT trigger graceful shutdown of both the orchestrator and market stream.

The MarketStream provides live bid/ask/volume data to multiple blocks:
- B1 uses it for current prices and volume validation.
- B1-features uses it for OHLCV bars and bid-ask spreads.
- B7 uses it for real-time position P&L monitoring.

---

### Signal Generation Pipeline

The end-to-end signal generation flow executes once per session open. The pipeline is divided into three phases: shared intelligence (computed once per session for all users), per-user signal generation (looped for each active user), and post-loop analysis.

```
Session Open Detected (NY 9:30 / LON 3:00 / APAC 20:00 ET)
  |
  v
Circuit Breaker Pre-Check (DATA_HOLD >= 3? VIX > 50? manual_halt?)
  |
  v  [SHARED -- once per session]
B1: Data Ingestion (load assets, features, models from QuestDB + TopstepX)
  |
  v
B2: Regime Probability (Pettersson binary or XGBoost classifier)
  |
  v
B3: AIM Aggregation (MoE/DMA weighted modifier computation)
  |
  v  [PER-USER LOOP]
B4: Kelly Sizing (12-stage: blended Kelly -> shrinkage -> constraints -> 4-way min)
  |
  v
B5: Trade Selection (expected edge ranking, HMM session allocation)
  |
  v
B5B: Quality Gate (quality_score = edge x modifier x data_maturity vs floor/ceiling)
  |
  v
B5C: Circuit Breaker Screen (7-layer composite per Topstep account)
  |
  v
B6: Signal Output (publish to Redis captain:signals:{user_id})
  |
  v  [POST-LOOP]
B8: Concentration Monitor (cross-user crowding detection)
B9: Capacity Evaluation (aggregate exposure vs liquidity)
  |
  v  [CONTINUOUS]
B7: Position Monitor (10s poll: TP/SL/time exits -> trade outcome -> Offline feedback)
```

---

### Block-by-Block Implementation

#### B1: Data Ingestion

**File:** `captain-system/captain-online/captain_online/blocks/b1_data_ingestion.py` (757 lines)
**Spec:** P3-PG-21
**Function:** `run_data_ingestion(session_id: int) -> dict | None`

B1 serves as the entry point for the entire signal pipeline, responsible for loading, validating, and assembling all data required by downstream blocks. It queries nine QuestDB tables and the TopstepX API:

| Source | Table/API | Data Loaded |
|--------|-----------|-------------|
| Assets | P3-D00 `p3_d00_asset_universe` | Active assets filtered by `captain_status` and `session_hours` |
| AIM States | P3-D01 `p3_d01_aim_state` | Per-asset model objects, warmup progress, current modifier |
| AIM Weights | P3-D02 `p3_d02_aim_weights` | DMA inclusion probabilities and effectiveness scores |
| EWMA | P3-D05 `p3_d05_ewma_states` | Regime/session-specific win rates, avg_win, avg_loss, n_trades |
| TSM Configs | P3-D08 `p3_d08_tsm_state` | Account risk limits, classification, Topstep parameters |
| Kelly Params | P3-D12 `p3_d12_kelly_parameters` | Per-regime Kelly fractions and shrinkage factors |
| System Params | P3-D17 `p3_d17_system_monitor_state` | Quality thresholds, manual halt flags |
| TopstepX | `quote_cache` + REST API | Live prices (sub-second), daily bars (fallback) |
| Strategies | P3-D00 `locked_strategy` column | Model ID, feature set, SL/TP multiples |

Asset filtering uses `captain_status` in `(ACTIVE, WARM_UP, TRAINING_ONLY)` combined with session matching. Session matching maps `session_id` (1=NY, 2=LON, 3=APAC) against the asset's `session_hours` JSON configuration (e.g., `{"NY":true,"LON":true,"APAC":true}`).

**Data Moderator** validation includes:
- Price deviation check: current price vs prior close with 5% threshold, triggering `DATA_HOLD` status on breach.
- Volume sanity: zero volume flagged as `ZERO_VOLUME`, 10x average flagged as `VOLUME_EXTREME`.
- Contract roll calendar: `ROLL_PENDING` status when `next_roll_date` reached without `roll_confirmed`.
- Timezone validation: enforces `America/New_York` via `TZ` environment variable.

All loaders use `ORDER BY last_updated DESC` with in-memory deduplication via `seen` sets to get the latest record per composite key. AIM states provide dual indexing: `by_asset_aim` for per-asset lookups and `global` for cross-asset AIM status checks.

Data quality incidents are written to P3-D21 with severity `P2_HIGH`, and critical alerts (contract rolls, data quality failures) are published to Redis `CH_ALERTS`.

**Latency target:** less than 5 seconds for complete ingestion and feature computation.

If no active assets pass filtering, `run_data_ingestion()` returns `None` and the session is skipped.

---

#### B2: Regime Probability

**File:** `captain-system/captain-online/captain_online/blocks/b2_regime_probability.py` (194 lines)
**Spec:** P3-PG-22
**Function:** `run_regime_probability(active_assets, features, regime_models) -> dict`

B2 classifies the current market regime for each active asset using a dual-path approach:

**Path 1 -- C4 Assets (BINARY_ONLY):** The Pettersson binary rule computes realized volatility as the standard deviation of 20-day returns scaled by sqrt(252) for annualization. The result is compared against a learned threshold `phi` stored in P2-D07:
- `sigma_t > phi` -> `{HIGH_VOL: 1.0, LOW_VOL: 0.0}`
- `sigma_t <= phi` -> `{HIGH_VOL: 0.0, LOW_VOL: 1.0}`

Implemented in `_binary_regime()`, which calls `_compute_realised_vol()` using `b1_features._get_daily_returns(asset_id, lookback=20)`.

**Path 2 -- C1-C3 Assets (Trained Classifier):** A serialized XGBoost classifier from P2-D07 runs `predict_proba()` on an extracted feature vector, producing class probabilities mapped to `{LOW_VOL: proba[0], HIGH_VOL: proba[1]}`.

Implemented in `_classifier_regime()`, which calls `b1_features.extract_classifier_features()` and `classifier_obj.predict_proba()`. For V1, assets with `regime_label == "REGIME_NEUTRAL"` (the locked P2 result) return equal probabilities `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` without running the classifier.

**Uncertainty detection:** When `max(regime_probs.values()) < 0.6`, the `regime_uncertain` flag is set to `True`. This triggers robust Kelly sizing in B4, which uses worst-case bounds-based sizing instead of betting on a single regime.

**Fallback cascade:** Missing model, failed vol computation, incomplete features, or classifier exception all produce neutral probabilities `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` with `regime_uncertain = True`.

**Outputs:**
- `regime_probs`: `{asset_id: {HIGH_VOL: float, LOW_VOL: float}}`
- `regime_uncertain`: `{asset_id: bool}`

B2 is a pure computation block -- it reads no tables directly (all data comes from B1) and writes nothing.

---

#### B3: AIM Inference (Aggregation)

**File:** `captain-system/captain-online/captain_online/blocks/b3_aim_aggregation.py`
**Spec:** P3-PG-23
**Function:** `run_aim_aggregation(active_assets, features, aim_states, aim_weights) -> dict`

B3 aggregates up to 16 Adaptive Investment Model (AIM) modifiers per asset using Mixture-of-Experts (MoE) gating with DMA (Dynamic Model Averaging) weights.

**Per-asset aggregation flow:**

1. For each AIM (IDs 1-16), check status in P3-D01 (`aim_states["by_asset_aim"]`). Only `ACTIVE` AIMs proceed.
2. Check DMA inclusion flag in P3-D02 (`aim_weights`). Excluded AIMs are skipped.
3. Call `compute_aim_modifier(aim_id, features, asset_id, state)` to get the per-AIM modifier.
4. Clamp each modifier to `[MODIFIER_FLOOR=0.5, MODIFIER_CEILING=1.5]`.
5. Compute weighted average using DMA `inclusion_probability` as weights:
   `combined_modifier = sum(modifier_i * weight_i) / sum(weight_i)`
6. Clamp combined result to `[0.5, 1.5]`.

If no active AIMs exist for an asset, `combined_modifier` defaults to `1.0` (neutral).

**AIM Dispatch Table:**

| AIM | Name | Key Feature | Modifier Range |
|-----|------|-------------|---------------|
| 01 | VRP | `vrp` sign/magnitude | 0.85-1.15 |
| 02 | Skew | `pcr`, `put_skew` | 0.85-1.15 |
| 03 | GEX | Dealer gamma sign | 0.85-1.15 |
| 04 | IVTS | VIX term structure | 0.85-1.15 |
| 05 | DEFERRED | -- | -- |
| 06 | Calendar | Event proximity/tier | 0.80-1.10 |
| 07 | COT | SMI polarity alignment | 0.90-1.10 |
| 08 | Cross-Asset Corr | Correlation z-score | 0.85-1.15 |
| 09 | Cross-Asset Momentum | Momentum alignment | 0.90-1.10 |
| 10 | Calendar Effects | OPEX/day-of-week | 0.85-1.10 |
| 11 | Regime Warning | VIX z-score | 0.70-1.00 |
| 12 | Dynamic Costs | Spread z-score | 0.85-1.10 |
| 13 | Sensitivity | Offline B5 fragility | 0.85-1.00 |
| 14 | Auto-Expansion | Always 1.0 | 1.00 |
| 15 | Opening Volume | Volume ratio | 0.85-1.15 |
| 16 | HMM Opportunity | Offline B1 HMM state | 0.80-1.20 |

**Outputs:**
- `combined_modifier`: `{asset_id: float}` in [0.5, 1.5]
- `aim_breakdown`: `{asset_id: {aim_id: {modifier, confidence, reason_tag, dma_weight}}}`

B3 is a pure computation block with no database reads or writes.

---

#### B4: Kelly Sizing

**File:** `captain-system/captain-online/captain_online/blocks/b4_kelly_sizing.py` (460+ lines)
**Spec:** P3-PG-24
**Function:** `run_kelly_sizing(...) -> dict | None`

B4 is the most computationally complex block in the Online pipeline. It implements a 12-stage position sizing pipeline that runs once per user per session, computing optimal contract counts per asset per account.

**12-Stage Pipeline:**

| Stage | Description | Key Formula/Logic |
|-------|------------|-------------------|
| 0 | Silo drawdown check | `(1 - total_capital/starting_capital) > 0.30` -> BLOCKED all, CRITICAL alert |
| 1 | Blended Kelly | `sum(regime_weight_i * kelly_fraction_i)` across HIGH_VOL and LOW_VOL |
| 2 | Shrinkage | `adjusted = blended * shrinkage_factor` (from P3-D12, typically 0.95-0.98) |
| 3 | Robust fallback | If `regime_uncertain`, compute bounds-based Kelly via `compute_robust_kelly()` and take min |
| 4 | AIM modifier | `kelly_with_aim = adjusted * combined_modifier` |
| 5 | User ceiling | `kelly_with_aim = min(kelly_with_aim, user_kelly_ceiling)` (e.g., 0.15 = 15%) |
| 6 | Per-account sizing | Branch by account category (PROP_EVAL/FUNDED/SCALING vs BROKER_RETAIL/INSTITUTIONAL) |
| 7 | Risk-goal adjustment | PASS_EVAL: 50-85% reduction; PRESERVE_CAPITAL: 50% reduction; GROW_CAPITAL: no change |
| 8 | TSM hard constraints | MDD budget, MLL budget, max_contracts, scaling plan tiers |
| 9 | V3 Fee integration | `risk_per_contract_with_fee = risk_per_contract + expected_fee` |
| 10 | V3 4-way min | `final = min(kelly_contracts, tsm_cap, topstep_daily_cap, scaling_cap)` |
| 11 | Portfolio risk cap | `total_risk = sum(contracts * SL * point_value)`; scale down if > `max_portfolio_risk_pct * capital` |
| 12 | Level 2 override | Apply `sizing_override` multiplier from P3-D12 if present |

**Per-account TSM constraint logic (Stage 8):**

For prop firm accounts (`PROP_EVAL`, `PROP_FUNDED`, `PROP_SCALING`):
- `daily_budget = remaining_mdd / budget_divisor` where `budget_divisor` = remaining eval days or default 20
- `max_by_mdd = floor(daily_budget / risk_per_contract)`
- `max_by_mll = floor((max_daily_loss - daily_used) / risk_per_contract)`
- `tsm_cap = min(max_by_mdd, max_by_mll, max_contracts)`, further constrained by scaling plan tiers

For broker accounts (`BROKER_RETAIL`, `BROKER_INSTITUTIONAL`):
- `cap = floor(balance / (margin * buffer))` with configurable `margin_buffer_pct` (default 1.5x)

**V3 additions:**
- `_compute_topstep_daily_cap()`: Uses `E_daily_exposure` from SOD reconciliation, computed as `e * A` where `e` is the daily exposure fraction and `A` is account balance.
- `_compute_scaling_cap()`: Prevents exceeding XFA scaling plan micro-equivalent tier limits.
- Fee integration: `_get_expected_fee()` resolves per-contract round-turn fees from `fee_schedule.fees_by_instrument`, falling back to `commission_per_contract * 2`.

**Account recommendation outputs:**
- `"TRADE"`: Positive contract allocation, proceed to signal.
- `"BLOCKED"`: Hard constraint hit (daily loss limit, insufficient MDD headroom).
- `"SKIP"`: Soft constraint (no TSM config, not eligible, rounded to zero).
- `"REDUCED_TO_ZERO"`: Level 2 override reduced allocation below 1 contract.

**Silo drawdown circuit breaker:** If `total_capital` falls 30% below `starting_capital`, B4 publishes a CRITICAL alert to Redis `CH_ALERTS`, blocks all assets/accounts with `final_contracts = 0`, and returns `silo_blocked = True` to halt the entire user's trading.

**Observed values (first live run):**
- ES Kelly fractions: 3.8-5.9% across HIGH_VOL/LOW_VOL with 0.974 shrinkage
- ZN Kelly fractions: 18-29% across regimes with 0.975 shrinkage
- ZB Kelly fractions: 16-22% across regimes with 0.958 shrinkage
- User Kelly ceiling: 15% (capping ZN/ZB but not ES)
- Portfolio risk cap: 10% of $150,000 = $15,000

---

#### B5b: Quality Gate

**File:** `captain-system/captain-online/captain_online/blocks/b5b_quality_gate.py` (158 lines)
**Spec:** P3-PG-25B
**Function:** `run_quality_gate(selected_trades, expected_edge, combined_modifier, regime_probs, user_silo, session_id) -> dict`

B5B filters selected trades by minimum quality threshold before signal generation. The quality score combines three factors:

```
quality_score = expected_edge * combined_modifier * data_maturity
```

**Parameters (from P3-D17):**
- `quality_hard_floor`: 0.003 ($0.003 or 0.3 cents per contract) -- minimum threshold
- `quality_ceiling`: 0.010 ($0.01 or 1 cent per contract) -- full-strength threshold

**Data maturity calculation:**
```python
data_maturity = min(1.0, max(0.5, trade_count / 50.0))
```

The `trade_count` is queried from `p3_d03_trade_outcome_log` per asset via `_get_trade_count()`.

**Cold-start floor:** The `max(0.5, ...)` ensures a minimum 50% data maturity even with zero live trades. Without this floor, `data_maturity = 0.0` would produce `quality_score = 0.0`, which falls below `hard_floor = 0.003`, creating an impossible condition where the system could never generate its first signal.

**Gate logic:**
- `quality_score < hard_floor` -> `passes_gate = False`, `quality_multiplier = 0.0` -- signal excluded as `available_not_recommended`
- `quality_score >= hard_floor` -> `passes_gate = True`, `quality_multiplier = min(1.0, quality_score / quality_ceiling)` -- graduated sizing between floor and ceiling

**Observed values (first live run):**
- ES expected edge: $0.035-0.055 per contract
- With 50% cold-start maturity: quality_score = $0.0175-0.0275, exceeding the 1-cent ceiling by 1.75-2.75x
- All 3 recommended signals passed quality gate; zero rejected

Results are logged to `p3_d17_system_monitor_state` as `session_log_{session_id}_{user_id}`.

---

#### B5c: Circuit Breaker

**File:** `captain-system/captain-online/captain_online/blocks/b5c_circuit_breaker.py` (579 lines)
**Spec:** P3-PG-27B (V3 Amendment, per `Topstep_Optimisation_Functions.md` Parts 4-6)
**Function:** `run_circuit_breaker_screen(recommended_trades, final_contracts, account_recommendation, ...) -> dict`

B5C implements the V3 7-layer composite circuit breaker per the mathematical specification:

```
D_{j+1} = H(L_t, rho_j) * B(n_t) * C_b(L_b) * Q(L_b, n_t)
```

Non-Topstep accounts bypass the circuit breaker entirely (`topstep_optimisation = False`).

**7-Layer Architecture:**

| Layer | Name | Formula / Check | Blocks When |
|-------|------|----------------|-------------|
| L0 | Scaling Cap | `current_open_micros + proposed_micros > scaling_tier_micros` | XFA accounts exceeding tier limit |
| L1 | Preemptive Halt | `abs(L_t) + rho_j >= c * e * A` | Worst-case SL would breach halt threshold |
| L2 | Budget | `n_t >= N` where `N = floor((e * A) / (MDD * p + phi))` | Daily trade count exhausted |
| L3 | Basket Expectancy | `mu_b = r_bar + beta_b * L_b`; if `mu_b <= 0` | Negative expected return for model basket |
| L4 | Correlation Sharpe | `S = mu_b / (sigma * sqrt(1 + 2*n_t*rho_bar))`; if `S <= lambda` | Sharpe below minimum threshold |
| L5 | Session Halt | VIX > 50.0 or DATA_HOLD count >= 3 | Dangerous market conditions |
| L6 | Manual Override | `manual_halt` flag in P3-D17 | Admin-initiated trading halt |

**Key parameters:**
- `c`: Hard halt fraction (default 0.5)
- `e`: Daily exposure fraction (default 0.01)
- `A`: Current account balance
- `p`: Fraction of MDD% risked per trade (default 0.005)
- `phi`: Expected round-turn fee per contract
- `rho_j`: Worst-case risk = `contracts * (SL_distance * point_value + fee_per_trade)`
- `lambda`: Minimum conditional Sharpe threshold (default 0.0)

**Cold-start behavior:**
- Layer 3: `beta_b` is only used when statistically significant (`p < 0.05` AND `n_observations >= 100`). Otherwise `beta_b = 0`, making `mu_b = r_bar` which is positive for positive-expectancy strategies, so the filter never triggers.
- Layer 4: With `rho_bar = 0` (cold start), the denominator reduces to `sigma`, making `S = mu_b / sigma` (unconditional Sharpe). With `lambda = 0` (default), the filter never triggers if `mu_b > 0`.

**Data sources:**
- `_load_cb_params()`: Reads `p3_d25_circuit_breaker_params` keyed by `(account_id, model_m)` for `r_bar`, `beta_b`, `sigma`, `rho_bar`, `n_observations`, `p_value`
- `_load_intraday_state()`: Reads `p3_d23_circuit_breaker_intraday` keyed by `account_id` for `l_t` (accumulated PnL), `n_t` (trade count), `l_b`/`n_b` (per-basket metrics)
- `_resolve_fee()`: Tiered fee resolution: `fee_schedule.fees_by_instrument[asset].round_turn` -> `commission_per_contract * 2` -> fallback parameter

**beta_b errata (documented in file header):**
- `beta_b > 0`: Positive serial correlation -- losses predict more losses, so shut down.
- `beta_b < 0`: Mean reversion -- losses predict recovery, so keep trading.

After all layers are checked, assets where all accounts are `BLOCKED` are removed from `recommended_trades`.

---

#### B6: Signal Output

**File:** `captain-system/captain-online/captain_online/blocks/b6_signal_output.py` (338 lines)
**Spec:** P3-PG-26
**Function:** `run_signal_output(recommended_trades, available_not_recommended, quality_results, final_contracts, ...) -> dict`

B6 constructs fully specified trading signals and publishes them to Redis for Captain Command to route.

**Signal structure (per asset):**

```python
{
    "signal_id": "SIG-{hex12}",       # Unique ID, e.g., "SIG-A1B2C3D4E5F6"
    "user_id": str,
    "asset": str,
    "session": int,
    "timestamp": ISO8601,
    "direction": int,                   # 1=LONG, -1=SHORT, 0=pending OR breakout
    "tp_level": float,                  # entry + (tp_multiple * or_range * direction)
    "sl_level": float,                  # entry - (sl_multiple * or_range * direction)
    "sl_method": "OR_RANGE",
    "per_account": {
        account_id: {
            "contracts": int,
            "recommendation": "TRADE"|"BLOCKED"|"SKIP",
            "skip_reason": str|None,
            "account_name": str,
            "category": str,
            "risk_goal": str,
            "remaining_mdd": float,
            "remaining_mll": float,
            "pass_probability": float,
            "risk_budget_pct": float,
            "api_validated": bool,
        }
    },
    "aim_breakdown": dict,              # Per-AIM modifier details
    "combined_modifier": float,
    "regime_state": "LOW_VOL"|"HIGH_VOL",
    "regime_probs": dict,
    "expected_edge": float,
    "win_rate": float,
    "payoff_ratio": float,
    "quality_score": float,
    "quality_multiplier": float,
    "data_maturity": float,
    "confidence_tier": "HIGH"|"MEDIUM"|"LOW",
    "user_total_capital": float,
    "user_daily_pnl": float,
}
```

**Direction resolution:** For ORB strategies, direction is only known after the Opening Range period closes. Pre-session signals carry `default_direction = 0`; actual direction is resolved at breakout.

**TP/SL computation:** `_compute_tp()` and `_compute_sl()` use the locked strategy's `tp_multiple` (default 2.0) and `sl_multiple` (default 1.0) multiplied by the computed `or_range` from features.

**Confidence tier classification** (`_classify_confidence()`):
- `HIGH`: edge > `quality_ceiling` AND modifier > 1.0
- `MEDIUM`: edge > `quality_hard_floor`
- `LOW`: everything else

**Below-threshold signals** are included as `available_not_recommended` for transparency, providing the GUI with a view of opportunities that exist but do not meet quality standards.

**Publishing:** `_publish_signals()` writes to Redis via `publish_to_stream(STREAM_SIGNALS, ...)`, which is the durable delivery mechanism. Captain Command's orchestrator subscribes to this stream.

**Logging:** Results are written to `p3_d17_system_monitor_state` with key `signal_output_{session_id}_{user_id}`.

---

#### B7: Position Monitor

**File:** `captain-system/captain-online/captain_online/blocks/b7_position_monitor.py` (451 lines)
**Spec:** P3-PG-27
**Function:** `monitor_positions(open_positions: list[dict], tsm_configs: dict) -> list[dict]`

B7 implements the critical feedback mechanism that connects trading outcomes back to the Offline learning loop. It runs continuously every second (orchestrator heartbeat) while any positions are open.

**Monitoring checks (per position, per pass):**

1. **Live P&L tracking:** `current_pnl = (current_price - entry_price) * direction * contracts * point_value`
2. **TP proximity alert:** When price within 10% of target distance from entry, publish `HIGH` notification.
3. **SL proximity alert:** When price within 10% of target distance from entry, publish `CRITICAL` notification.
4. **VIX spike detection:** Stub in V1 (`_check_vix_spike()` -- to be implemented).
5. **Regime shift detection:** Stub in V1 (`_regime_shift_detected()` -- returns `False`).
6. **TP hit resolution:** LONG exits when `price >= TP`, SHORT exits when `price <= TP`.
7. **SL hit resolution:** LONG exits when `price <= SL`, SHORT exits when `price >= SL`.
8. **Time exit:** For no-overnight accounts, forced close 5 minutes before `trading_hours` end time.

**Position resolution (`resolve_position()`):**

This function executes the complete feedback cycle on position closure:

1. Calculate `gross_pnl = (exit_price - entry_price) * direction * contracts * point_value`.
2. Resolve commission via `resolve_commission()` using V3 tiered priority:
   - Source 1: API fill data (stub in V1)
   - Source 2: `fee_schedule.fees_by_instrument[asset].round_turn * contracts`
   - Source 3: `commission_per_contract * contracts * 2` (round-trip)
   - Source 4: Log warning, return 0
3. Compute `net_pnl = gross_pnl - commission`.
4. Compute slippage: `(actual_entry_price - signal_entry_price) * direction * contracts * point_value`.
5. Generate trade ID: `TRD-{hex12}`.
6. **Write to P3-D03** (`p3_d03_trade_outcome_log`): Full trade outcome including `trade_id`, `user_id`, `account_id`, `asset`, `direction`, `entry_price`, `signal_entry_price`, `exit_price`, `contracts`, `gross_pnl`, `commission`, `pnl` (net), `slippage`, `outcome` (TP_HIT/SL_HIT/TIME_EXIT), `regime_at_entry`, `aim_modifier_at_entry`, `aim_breakdown_at_entry`, `session`, `tsm_used`.
7. **Update P3-D16** (`p3_d16_user_capital_silos`): Add `net_pnl` to `total_capital`.
8. **Update P3-D23** (`p3_d23_circuit_breaker_intraday`): Increment `l_t` (accumulated PnL), `n_t` (trade count), and per-basket `l_b`/`n_b` metrics.
9. **Publish to Redis** (`STREAM_TRADE_OUTCOMES`): Complete trade outcome payload including `regime_at_entry`, `aim_modifier_at_entry`, `aim_breakdown_at_entry` for offline correlation analysis.
10. **Notify user:** CRITICAL notification with asset, outcome type, net PnL, and commission.

**Live price resolution** (`_get_live_price()`):
- Primary: TopstepX `quote_cache` via `resolve_contract_id()` (sub-second freshness)
- Fallback: TopstepX REST API 1-minute bars from the last 5 minutes

**The critical feedback loop:**

The Redis publication in step 9 is THE bridge to Captain Offline's learning loop. Offline processes subscribe to `STREAM_TRADE_OUTCOMES`, consume trade outcomes with their associated market conditions and model predictions, and use this data to:
- Retrain AIM models (update model states in P3-D01)
- Update EWMA performance statistics (P3-D05)
- Recalculate Kelly parameters (P3-D12)
- Adjust DMA meta-weights (P3-D02)

Without this feedback loop, the system cannot learn from actual trading results and would remain static.

---

### Orchestrator

**File:** `captain-system/captain-online/captain_online/blocks/orchestrator.py` (444 lines)
**Class:** `OnlineOrchestrator`

The orchestrator manages the 24/7 event loop, session scheduling, command handling, and position monitoring.

**Session schedule:**

| Session | ID | Open Time (ET) | Tolerance |
|---------|-----|---------------|-----------|
| NY | 1 | 09:30 | +/- 2 minutes |
| LON | 2 | 03:00 | +/- 2 minutes |
| APAC | 3 | 20:00 | +/- 2 minutes |

The main loop (`_session_loop()`) runs a 1-second heartbeat. Each tick checks whether any session is within its 2-minute open window via `_is_session_opening()`. The `_session_evaluated_today` dictionary (keyed by `session_id` and date) prevents double-evaluation of the same session.

**Session evaluation flow (`_run_session()`):**

1. Pre-check circuit breaker: `_circuit_breaker_check()` queries `_get_data_hold_count()`, `_get_current_vix()`, and `_is_manual_halt()`.
2. Run shared intelligence: `run_data_ingestion()` -> `run_regime_probability()` -> `run_aim_aggregation()`.
3. Load active users from P3-D15 (`p3_d15_user_session_data`) via `_get_active_users()`, with fallback to `{"user_id": "primary_user", "role": "ADMIN"}` if none found.
4. For each user, load capital silo from P3-D16 (`p3_d16_user_capital_silos`) via `_load_user_silo()`.
5. Call `_process_user()` for each user (B4 -> B5 -> B5B -> B5C -> B6).
6. If multiple users exist, run B8 concentration monitor.
7. Run B9 capacity evaluation.
8. Mark session as evaluated for today.

**User silo fields loaded:**
- `starting_capital`, `total_capital`, `accounts` (JSON array of account IDs)
- `max_simultaneous_positions` (e.g., 3)
- `max_portfolio_risk_pct` (e.g., 0.10 = 10%)
- `correlation_threshold` (e.g., 0.7)
- `user_kelly_ceiling` (e.g., 0.15 = 15%)

**Command listener:**

A daemon thread runs `_command_listener()`, subscribing to `STREAM_COMMANDS` via Redis Stream consumer group `GROUP_ONLINE_COMMANDS`. Commands handled:

- `MANUAL_HALT`: Logged (actual halt state stored in D17 by Command process).
- `TAKEN_SKIPPED`: When action is `TAKEN`, a position object is created and added to `open_positions` for B7 monitoring. The position includes all fields needed for resolution: `entry_price`, `signal_entry_price`, `actual_entry_price`, `contracts`, `tp_level`, `sl_level`, `point_value`, `risk_amount`, `regime_state`, `combined_modifier`, `aim_breakdown`, `tsm_id`.

The command listener uses exponential backoff (1s -> 30s) on connection failures.

**Position monitoring:**

When `open_positions` is non-empty, `_run_position_monitor()` is called every loop iteration. It loads current TSM configs via `_load_tsm_configs()` and calls `monitor_positions()`. Resolved positions are removed from the list.

---

### Key Decisions

**Cold-start handling:** Multiple safeguards prevent the system from deadlocking on day 1:
- B5B quality gate uses a 0.5 data_maturity floor instead of 0.0, ensuring non-zero quality scores with zero trade history.
- B2 defaults to neutral regime `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` when regime models are missing.
- B4 Kelly sizing falls back to `0.0` when Kelly parameters are absent, which produces zero contracts (safe) rather than exceptions.
- B5C circuit breaker layers 3-4 use `beta_b = 0` when parameters lack statistical significance, making these layers inert during cold start.

**Quality gate thresholds:** The 0.3-cent floor and 1-cent ceiling were calibrated for futures strategies with typical edges in the 1-5 cent range. ES with $0.035-0.055 expected edge exceeds the ceiling even after 50% cold-start maturity penalty, receiving full quality multiplier.

**AUTO_EXECUTE:** When the `AUTO_EXECUTE` environment variable is set to `true` in Captain Command, signals generated by Online are automatically converted to broker orders without manual TAKEN/SKIPPED confirmation. This bypasses the GUI confirmation workflow entirely, suitable for funded scaling accounts after evaluation.

**Session hours configuration:** All 10 configured futures assets (ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN) are enabled for NY, LON, and APAC sessions via `session_hours = {"NY":true,"LON":true,"APAC":true}` in P3-D00.

---

### Critical Fixes

**Cold-start quality gate deadlock (B5B):** The original `data_maturity = min(1.0, trade_count / 50.0)` formula returned 0.0 when `trade_count = 0`, causing `quality_score = edge * modifier * 0.0 = 0.0`, which always failed the `hard_floor = 0.003` threshold. This created an impossible condition where the system needed trade history to generate signals but could not build trade history without generating signals. Fixed by changing to `min(1.0, max(0.5, trade_count / 50.0))`, establishing a 50% data maturity baseline for new systems.

**Session hours JSON encoding (P3-D00):** Initial database INSERT statements produced malformed JSON due to URL encoding issues, where only `"APAC":true` was visible. Re-inserted with properly formatted `{"NY":true,"LON":true,"APAC":true}` to ensure `session_match()` correctly evaluates assets for all three sessions.

**Asset universe population:** The NY session was initially skipping due to no active assets in the database. Resolved by populating `p3_d00_asset_universe` with 10 futures contracts, each configured with model_id=4, feature_id=017, OR_RANGE stop-loss method, threshold=4.0, 1.0x SL multiple, 2.0x TP multiple, and `captain_status = WARM_UP`.

**TopstepX WebSocket reconnection:** Both MarketStream and UserStream were tuned to use consistent reconnection parameters: 15-second keep-alive/reconnect intervals, 10 maximum attempts, and intelligent rapid-failure detection (stops reconnection after 5 rapid failures with <10 second uptime) to prevent log spam during off-market hours.

**Kelly parameter coverage gap:** Only ZN and ZB had Kelly parameters from the initial Offline bootstrapping run. The remaining 8 assets (including ES) had parameters populated in a subsequent batch, with ES showing 4-6% Kelly fractions matching its lower-edge profile compared to 16-29% for treasury futures.

---

### Current State

As of March 24, 2026, Captain Online has completed its first successful end-to-end pipeline execution:

- **First signals generated:** 3 trading signals produced during NY session 1 evaluation.
- **Pipeline timing:** Full evaluation completed in approximately 21 seconds for 1 user across 10 assets.
- **Block execution:** All 9 pipeline blocks (B1-B6, B8, B9) executed without errors.
  - B1 computed 220 features across 10 active assets.
  - B2 used neutral regime fallback for all 10 assets (no trained regime models yet).
  - B3 processed 10 assets with zero active AIM models contributing (neutral modifier).
  - B4 calculated position sizes for primary_user across 1 account and 10 assets.
  - B5 selected 3 out of 10 assets as viable trading opportunities.
  - B5B passed all 3 recommended signals with zero rejected.
  - B6 published 3 signals for primary_user session 1.
  - B9 completed with 3 active constraints.
- **EWMA data:** Bootstrapped from historical backtest data (449-998 trade samples for ES), not live trades. P3-D03 trade outcome log contains zero live trades, confirming the system is starting from zero live trading history.
- **User silo:** primary_user configured with $150,000 capital, 15% Kelly ceiling, 10% portfolio risk cap, 3 maximum simultaneous positions, linked to Topstep account 20319811.
- **Docker deployment:** All 6 containers running and healthy: captain-online, captain-command, captain-offline, nginx, redis, questdb. Captain-online connected to 10 futures contract market streams via single MarketStream WebSocket.
- **Stubs for V2:** VIX spike detection (`_check_vix_spike`) and regime shift detection (`_regime_shift_detected`) are stubbed in B7, awaiting implementation for live VIX data integration and BOCPD/HMM mid-trade monitoring.

---

## 7. Captain Command -- Linking Layer

### Spec Reference

The Captain Command process is specified in `06_Program3_Command.md` (original spec, lines 32-877), with V3 amendments from `Nomaan_Master_Build_Guide.md`, `Cross_Reference_PreDeploy_vs_V3.md`, `Topstep_Optimisation_Functions.md`, and `NotificationSpec.md`. The implementation spans 10 blocks plus an orchestrator, a FastAPI application module (`api.py`), an entry point (`main.py`), and a Telegram bot module (`telegram_bot.py`).

### Process Architecture

Captain Command is the always-on linking layer that bridges Captain Online (signal generation), Captain Offline (strategic brain), the GUI, external broker APIs, and notification channels. It runs as a single Docker container exposing port 8000 via nginx.

**Startup sequence** (`main.py`):

1. `verify_connections()` -- confirms QuestDB and Redis are reachable; exits with code 1 on failure. Initializes Redis Stream consumer group `GROUP_COMMAND_SIGNALS` on `STREAM_SIGNALS`.
2. `load_tsm_files()` -- loads and validates all TSM JSON configuration files from `/captain/config/tsm/providers/` via `b4_tsm_manager.load_all_tsm_files()`.
3. `start_telegram_bot()` -- creates and starts the Telegram bot with a TAKEN/SKIPPED callback that routes through `b1_core_routing.route_command()`. Returns `None` if no bot token is configured.
4. `_init_topstep()` -- authenticates to the TopstepX API, resolves the target account, preloads contract IDs via `preload_contracts()`, starts a single `MarketStream` WebSocket for all resolved contracts, and starts a `UserStream` WebSocket for live account/position updates. Registers a `TopstepXAdapter` with `b3_api_adapter.register_connection()` for health monitoring.
5. `_link_tsm_to_account()` -- auto-links the discovered TopstepX account to the best matching TSM template based on account name prefix (`PRAC` -> `STAGE_1`, `XFA` -> `XFA`, else -> `LIVE`) and provider/balance fallback. Checks P3-D08 for existing links to prevent duplicate rows.
6. `CommandOrchestrator` starts in a background daemon thread.
7. FastAPI/uvicorn runs in the main thread on `0.0.0.0:8000`.

SIGTERM and SIGINT handlers ensure graceful shutdown of all streams, the orchestrator, and the Telegram bot.

**Thread model** (4 concurrent threads):

| Thread | Name | Role |
|--------|------|------|
| Main | uvicorn | FastAPI HTTP + WebSocket server |
| Background 1 | `cmd-signals` | Redis Stream consumer for durable signal delivery |
| Background 2 | `cmd-redis` | Redis pub/sub for alerts, status, commands |
| Background 3 | `cmd-orchestrator` | Scheduler: periodic tasks (market push, dashboard, health, reconciliation) |
| Background 4 | Telegram | Long-polling bot (if token configured) |

### Block-by-Block Implementation

#### B1: Core Routing (`b1_core_routing.py`)

The central message bus. B1 subscribes to Redis channels, routes messages to GUI sessions and API adapters, and forwards user commands to Online/Offline. The cardinal rule: **Command NEVER modifies signals** -- it only formats, routes, and logs.

**Signal routing** -- `route_signal_batch(payload, gui_push_fn, api_route_fn)`:

- Receives a signal batch published by Online B6 to `captain:signals:{user_id}`.
- For each signal, generates a unique `signal_id` (format: `SIG-{12hex}`), logs it to P3-D17 (`p3_session_event_log`) via `_log_signal_received()`, and pushes the full signal context to the GUI with message type `"signal"`.
- If `api_route_fn` is provided (auto-execute mode), iterates through per-account contract allocations and sends sanitized orders via `sanitise_for_api()`.
- Below-threshold signals are pushed separately with type `"below_threshold"` so the GUI can display suppressed signals.

**Sanitization boundary** -- `sanitise_for_api(signal, ac_id, ac_detail)`:

Enforces the one-way security boundary. Only 6 fields leave Captain:
- `asset`, `direction`, `size`, `tp`, `sl`, `timestamp`

Fields in `PROHIBITED_EXTERNAL_FIELDS` (AIM modifiers, regime state, Kelly details, confidence tiers) are never transmitted externally.

**Command routing** -- `route_command(data, gui_push_fn)`:

Dispatches inbound commands from the GUI/API to the correct subsystem. Supported command types and their routing:

| Command Type | Destination | Delivery |
|---|---|---|
| `TAKEN_SKIPPED` | Online (via `STREAM_COMMANDS`) | Durable stream with full trade context (entry_price, contracts, tp/sl, regime, AIM breakdown) |
| `ADOPT_STRATEGY`, `REJECT_STRATEGY`, `PARALLEL_TRACK` | Offline (via `STREAM_COMMANDS`) | Strategy injection decisions |
| `SELECT_TSM` | Local (P3-D08 update) | TSM switch logged to session event log |
| `ACTIVATE_AIM`, `DEACTIVATE_AIM` | Offline (via `STREAM_COMMANDS`) | AIM control commands |
| `CONCENTRATION_PROCEED`, `CONCENTRATION_PAUSE` | Local | Concentration response logged |
| `CONFIRM_ROLL` | Local | Contract roll confirmation logged |
| `UPDATE_ACTION_ITEM` | Local | Action item status update |
| `TRIGGER_DIAGNOSTIC` | Offline (via `STREAM_COMMANDS`) | On-demand diagnostic |
| `MANUAL_PAUSE`, `MANUAL_RESUME` | Online (via `STREAM_COMMANDS`) | Asset-level halt/resume |

Every command generates a `command_ack` WebSocket message back to the GUI for confirmation.

**Notification routing** -- `route_notification(notif, gui_push_fn, telegram_fn)`:

Pushes notifications to all target users via GUI WebSocket. CRITICAL and HIGH priority notifications also route to Telegram if `telegram_fn` is provided. Notifications are logged to P3-D10 (`p3_d10_notification_log`).

**Status handling** -- `handle_status_message(data, process_health)`:

Updates the in-memory `process_health` dict from heartbeat messages. Tracks status for OFFLINE, ONLINE, and COMMAND roles.

#### B2: GUI Data Server (`b2_gui_data_server.py`)

Two-layer data server that assembles dashboard payloads for WebSocket push to connected GUI clients.

**Layer 1: Main Dashboard** -- `build_dashboard_snapshot(user_id)`:

Called every 60 seconds by the orchestrator and on initial WebSocket connect. Assembles 12 data sources into a single payload:

| Field | Source | Description |
|---|---|---|
| `capital_silo` | UserStream > REST API > P3-D16 | Three-tier data fallback for live balance |
| `open_positions` | P3-D03 `trade_outcome_log` | Rows where `outcome IS NULL` (still open) |
| `pending_signals` | P3-D17 `session_event_log` | Recent `SIGNAL_RECEIVED` events |
| `aim_states` | P3-D01 `aim_model_states` | Python-side deduplication keeping latest per `(aim_id, asset_id)` |
| `tsm_status` | P3-D08 `tsm_state` | Uses `LATEST ON last_updated PARTITION BY account_id`; computes MDD% and daily loss% |
| `decay_alerts` | P3-D04 `decay_detector_states` | Assets with `bocpd_cp_probability > 0.5` |
| `warmup_gauges` | P3-D00 `asset_universe` | Uses `LATEST ON last_updated PARTITION BY asset_id`, filters WARM_UP/ACTIVE/TRAINING_ONLY |
| `notifications` | P3-D10 `notification_log` | Last 100 notifications for user |
| `payout_panel` | P3-D08 (V3) | Payout recommendations for Topstep accounts |
| `scaling_display` | P3-D08 (V3) | Scaling tier progress for accounts with `scaling_plan_active = true` |
| `live_market` | `quote_cache` dict | Live bid/ask/volume from MarketStream WebSocket |
| `api_status` | TopstepX client state | API authentication, UserStream state, MarketStream freshness |

**Capital silo tiered fallback**: The `_get_capital_silo()` function implements a three-tier data priority:
1. `UserStream.account_data` -- real-time WebSocket (sub-second latency)
2. TopstepX REST API -- `client.get_accounts(only_active=True)`
3. QuestDB P3-D16 -- database fallback

**Live market data**: `_get_live_market_data(asset_id)` reads from `quote_cache` (populated by `MarketStream`), returns `last_price`, `best_bid`, `best_ask`, `spread`, `change`, `change_pct`, `volume`, and OHLC data. Returns `{connected: False}` if no quote is cached for the contract.

**V3: Payout panel** -- `_get_payout_panel(user_id)`:
Computes payout recommendations per Topstep account: `W(A) = min(max_per_payout, 0.50 * profit)`, net after commission, MDD% before and after withdrawal, tier impact, and a `recommended` flag (true when `W >= 500` and profit exceeds `scaling_tier_floor`).

**V3: Scaling display** -- `_get_scaling_display(user_id)`:
Returns current tier label, max micros, open positions in micros, available slots, and profit needed for next tier from accounts with `scaling_plan_active = true`.

**Layer 2: System Overview (ADMIN)** -- `build_system_overview()`:

9 admin-only data sources: `network_concentration` (aggregate exposure from P3-D03), `signal_quality` (7-day pass rate from P3-D17), `capacity_state` (latest Online B9 evaluation), `diagnostic_health` (8-dimension scores from P3-D22), `action_queue` (open action items from P3-D22), `system_params` (P3-D17 monitor state), `data_quality` (asset freshness from P3-D00), `incident_log` (last 50 from P3-D21), and `compliance_gate` (JSON config file).

**High-frequency market push** -- `build_live_market_update()`:
Lightweight wrapper called every 1 second by the orchestrator. Returns only the `live_market` field. The orchestrator excludes `live_market` from the 60-second dashboard refresh to prevent overwriting the continuously-updated 1Hz market data stream on the frontend.

#### B3: API Adapter (`b3_api_adapter.py`)

Implements the secure one-way boundary between Captain and external broker APIs.

**Block 3.1 -- API Adapter Interface**: `APIAdapter` abstract base class with 5 lifecycle methods:
- `connect(api_key, endpoint)` -> `{connected, message}`
- `send_signal(order)` -> `{order_id, status}` (6 outbound fields)
- `receive_fill(order_id)` -> `{fill_price, fill_time}` (2 of 4 inbound fields)
- `get_account_status()` -> `{balance, equity, drawdown, open_positions}` (4 inbound fields)
- `disconnect()`
- `ping()` -> latency in ms (default returns -1.0)

**TopstepXAdapter**: Concrete implementation for TopstepX/ProjectX Gateway. Key behaviors:
- `connect()` authenticates via `get_topstep_client()`, resolves the target account by name or first active.
- `send_signal()` places a bracket order: market entry + stop loss (stop order) + take profit (limit order). Checks the compliance gate first; if `MANUAL` mode and not allowed, returns `MANUAL_PENDING`.
- `receive_fill()` queries recent orders to find fill price and time for a given order ID.
- `get_account_status()` fetches balance from the TopstepX API and counts open positions.
- Contract resolution uses `resolve_contract_id(asset_id)` to map symbols like "ES" to TopstepX contract IDs.

**Adapter registry**: `ADAPTER_REGISTRY = {"TopstepX": TopstepXAdapter}`. `get_adapter(provider)` instantiates by name.

**Block 3.2 -- Connection Health Monitoring**: `run_health_checks(notify_fn)` runs every 30 seconds. Pings each registered connection; if latency < 0 (connection lost), attempts up to 3 reconnects. Failed reconnections trigger a CRITICAL notification. Health results are batch-logged to P3-D14 (`p3_d14_api_connection_states`).

**Block 3.3 -- API Key Vault Integration**: Keys retrieved via `get_api_key(account_id)` from `shared.vault` with AES-256-GCM encryption and 90-day rotation policy.

**Block 3.4 -- Compliance Gate**: `check_compliance_gate()` reads `/captain/config/compliance_gate.json`. All 11 RTS 6 requirements must be `satisfied == True` for automated execution. **LOCKED in V1** -- the compliance gate is always in MANUAL mode, and the orchestrator passes `api_route_fn=None` unless `AUTO_EXECUTE` is explicitly set.

#### B4: TSM Manager (`b4_tsm_manager.py`)

Configuration-driven risk management. Each trading account is governed by a JSON file defining its operational parameters.

**Schema validation** -- `validate_tsm(tsm)`:
Required fields: `name`, `classification` (with `provider`, `category`, `stage`, `risk_goal`), `starting_balance`, `max_drawdown_limit`, `max_contracts`. Valid categories include `PROP_EVAL`, `PROP_FUNDED`, `PROP_SCALING`, `BROKER_RETAIL`, `PERSONAL`. Valid stages: `STAGE_1`, `STAGE_2`, `STAGE_3`, `XFA`, `LIVE`, `FUNDED`, `N_A`. V3 additions: `fee_schedule`, `payout_rules`, `scaling_plan`.

**File loading** -- `load_all_tsm_files()`:
Reads all `.json` files from `TSM_CONFIG_DIR` (`/captain/config/tsm/providers/`), validates each, returns list of `{filename, tsm, validation}` dicts. Invalid files are logged but do not halt startup.

**Parameter translation** -- `translate_for_tsm(signal_contracts, trade_risk, tsm)`:
Applies account-specific constraints to Kelly-sized signals:
1. Caps at `max_contracts` ceiling.
2. Computes remaining daily loss budget: `remaining = max_daily_loss - daily_loss_used`.
3. If trade risk exceeds budget, reduces contracts proportionally: `affordable = floor(remaining / risk_per_contract)`.
4. Returns `{contracts, suppressed, reason}`. Suppressed if final contracts < 1.

**V3: Fee integration** -- `get_fee_for_instrument(tsm, instrument)`:
Looks up round-turn fees from `fee_schedule.fees_by_instrument` dict; falls back to `commission_per_contract * 2`.

**V3: Scaling tiers** -- `get_scaling_tier(tsm, current_profit)`:
Sorts `scaling_plan` by `balance_threshold`, finds the current tier where `current_balance >= threshold`, returns `{tier_label, max_contracts, max_micros, profit_to_next_tier, next_tier_label}`.

**Database storage** -- `_store_tsm_in_d08(account_id, tsm, retries=3)`:
Inserts full TSM state into `p3_d08_tsm_state` with retry logic for QuestDB "table busy" errors. Stores `topstep_state` as JSON containing `topstep_params`, `payout_rules`, `fee_schedule`, and `scaling_plan`.

#### B5: Strategy Injection Flow (`b5_injection_flow.py`)

Routes the strategy injection workflow between the GUI and Offline B4.

**Injection notification** -- `notify_new_candidate(asset, candidate_id, gui_push_fn, user_id)`:
Pushes a HIGH-priority notification to the GUI when Offline B4 produces a new strategy comparison.

**Comparison panel** -- `get_injection_comparison(candidate_id)`:
Queries P3-D06 (`p3_d06_injection_history`) for side-by-side metrics (Sharpe, drawdown, win rate, expected edge) for current vs. proposed strategy. Also fetches pseudotrader results from P3-D11 (`p3_d11_pseudotrader_results`) including PnL impact, drawdown impact, Sharpe delta, PBO score, and DSR score.

**Decision routing** -- `route_injection_decision(candidate_id, decision, user_id, gui_push_fn)`:
Accepts `ADOPT`, `PARALLEL_TRACK`, or `REJECT`. Publishes to `CH_COMMANDS` for Offline consumption. Logs to P3-D17.

**Parallel tracking** -- `get_parallel_tracking_status(asset)`:
Fetches active parallel-track candidates from P3-D06 for display during the ~20-day tracking period.

#### B6: Discretionary Reports (`b6_reports.py`)

11 report types (RPT-01 through RPT-11). RPT-01 and RPT-07 render in-app; all others produce CSV.

| Report | Name | Trigger | Data Sources |
|--------|------|---------|--------------|
| RPT-01 | Pre-Session Signal Report | Pre-session | P3-D17 signals + P3-D00 assets |
| RPT-02 | Weekly Performance Review | End of week | P3-D03 (7-day trades) |
| RPT-03 | Monthly Decay & Warm-Up | First of month | P3-D04 decay states |
| RPT-04 | AIM Effectiveness | Monthly | P3-D01 + P3-D02 |
| RPT-05 | Strategy Comparison | On P1/P2 run | P3-D06 injection history |
| RPT-06 | Regime Change | Regime change | P3-D17 regime events |
| RPT-07 | Daily Prop Account | Daily | P3-D08 TSM state |
| RPT-08 | Regime Calibration | Monthly | P3-D03 (30-day trades) |
| RPT-09 | Parameter Change Audit | On demand | P3-D17 param/TSM/pause events |
| RPT-10 | Annual Performance | Annually | P3-D03 (year trades) |
| RPT-11 | Financial Summary Export | Monthly | P3-D03 (gross/net PnL, commission, slippage) |

Reports are archived to P3-D09 (`p3_d09_report_archive`) with metadata. Each report is assigned a unique ID (`RPT-{12hex}`). REST endpoints: `GET /api/reports/types` and `POST /api/reports/generate`.

#### B7: Notification System (`b7_notifications.py`)

Full notification routing system with 26 event types mapped to 4 priority levels.

**Event registry** -- `EVENT_REGISTRY` maps 26 event types to priorities and target roles:
- **CRITICAL (10 events)**: TP_HIT, SL_HIT, DECAY_LEVEL3, TSM_MDD_BREACH, TSM_MLL_BREACH, SYSTEM_CRASH, MID_TRADE_REGIME_SHIFT, API_KEY_COMPROMISE, API_CONNECTION_LOST, ENTRY_PRICE_MISSING
- **HIGH (9 events)**: SIGNAL_GENERATED, DECAY_LEVEL2, REGIME_CHANGE, AIM_FRAGILE, INJECTION_AVAILABLE, VIX_SPIKE, AUTO_EXEC_GATE, HEALTH_DIAGNOSTIC, ACTION_ITEM_REOPENED
- **MEDIUM (4 events)**: AIM_WARMUP_COMPLETE, WEEKLY_REPORT_READY, PARALLEL_TRACKING_DONE, API_KEY_ROTATION_DUE
- **LOW (4 events)**: MONTHLY_REPORT_READY, RETRAIN_COMPLETE, SYSTEM_STATUS, ANNUAL_REVIEW_READY

Each event type has a template string with `{placeholder}` substitution and role-based targeting (TRADER, ADMIN, DEV).

**Routing logic** -- `route_notification(notif, gui_push_fn, telegram_bot)`:
1. Resolves priority and message from the event registry (or uses ad-hoc `priority`/`message` fields).
2. Determines target users by `user_id` or role-based lookup from P3-D16.
3. **GUI**: Always delivered (cannot disable). Respects `gui_min_priority` preference. Includes `sound` flag for critical/high alerts.
4. **Telegram**: Delivered if `telegram_enabled` and priority meets threshold (`min_telegram_priority`, default HIGH). SIGNAL_GENERATED events use `send_signal_notification()` with inline TAKEN/SKIPPED buttons. During quiet hours, non-CRITICAL notifications are queued.
5. Logs full delivery state to P3-D10.

**Quiet hours** -- Configurable per user (default 22:00-06:00 ET). Non-CRITICAL notifications queued to `_quiet_queue` (max 50 per user, oldest dropped). `flush_quiet_queue()` called by the scheduler when quiet hours end.

**User preferences** -- Stored as `NOTIFICATION_PREFS` events in P3-D17. Defaults include `telegram_enabled: True`, `min_telegram_priority: "HIGH"`, `quiet_hours_enabled: True`, `notify_assets: ["ALL"]`, and sound configuration per priority level.

#### B8: Daily Reconciliation (`b8_reconciliation.py`)

Runs at 19:00 EST, triggered by the orchestrator's `_check_reconciliation_trigger()`. Four responsibilities:

**Step 1: Balance reconciliation** -- For API-connected accounts, `_reconcile_api_account()` fetches broker balance and compares to system balance. Mismatches > $1.00 trigger auto-correction from broker (trusted source) with a MEDIUM notification to the GUI. Manual accounts receive a `CONFIRM_BALANCE` notification requesting user input via `_request_manual_reconciliation()`. Results logged to P3-D19 (`p3_d19_reconciliation_log`).

**Step 2: SOD Topstep parameter computation (V3)** -- `_compute_sod_topstep_params()` computes start-of-day parameters for accounts with `topstep_optimisation == true`:

| Parameter | Formula | Description |
|-----------|---------|-------------|
| `f(A)` | `MDD / A` | MDD as fraction of current balance |
| `R_eff` | `p * f(A) + phi/A` | Effective risk per trade |
| `N` | `floor((e * A) / (MDD * p + phi))` | Max trades per day |
| `E` | `e * A` | Daily exposure budget ($) |
| `L_halt` | `c * e * A` | Hard halt threshold ($) |
| `W(A)` | `min(max_per_payout, 0.50 * profit)` | Max payout amount |
| `g(A)` | `MDD / (A - W(A))` | Post-payout MDD fraction |

Where `p`, `e`, `c` are configured per account in `topstep_params`. Results stored in P3-D08 `topstep_state.computed_sod`.

**Step 3: Payout recommendation (V3)** -- `_check_payout_recommendation()` implements a 4-step decision:
1. **Tier-preserving max**: `tier_preserving_max = profit - scaling_tier_floor`. Skip if <= 0.
2. **Cap withdrawal**: `withdraw = min(W, tier_preserving_max)`.
3. **Net after commission**: `net = withdraw * (1 - commission_rate)`. Skip if < $500.
4. **MDD% impact check**: If `f_post = MDD / (A - withdraw) > 0.03`, reduce withdrawal to maintain `f_target_max = 0.03`.

Account-type-aware: BROKER_LIVE accounts have 0% commission but require 30 winning days before payouts.

**Step 4: Daily counter resets** -- `_reset_daily_counters()` logs a DAILY_RESET event to P3-D17 and inserts fresh zero rows into P3-D23 (`p3_d23_circuit_breaker_intraday`) for each account (resetting `L_t`, `n_t`, `L_b`, `n_b`).

#### B9: Incident Response (`b9_incident_response.py`)

Auto-generated incident reports with severity classification and notification routing.

**Incident creation** -- `create_incident(incident_type, severity, component, details, ...)`:
Generates a unique ID (`INC-{12hex}`), stores to P3-D21 (`p3_d21_incident_log`), and routes notifications based on severity:

| Severity | Channels | Targets |
|----------|----------|---------|
| P1_CRITICAL | GUI + Telegram | ADMIN |
| P2_HIGH | GUI + Telegram | ADMIN |
| P3_MEDIUM | GUI | ADMIN |
| P4_LOW | (logged only) | -- |

Incident types: `CRASH`, `DATA_QUALITY`, `RECONCILIATION`, `PERFORMANCE`, `SECURITY`, `OPERATIONAL`.

**Resolution** -- `resolve_incident(incident_id, resolution, resolved_by)`:
Inserts a resolution row to P3-D21 with status `RESOLVED` (QuestDB append-only pattern).

**Queries** -- `get_open_incidents()` and `get_incident_detail(incident_id)` support the System Overview panel. Detail returns creation and resolution history.

#### B10: Data Input Validation (`b10_data_validation.py`)

Two validation subsystems per spec blocks P3-PG-41 and P3-PG-42.

**P3-PG-41: User Input Validation** -- `validate_user_input(input_type, value, context)`:
Validates three input types with deviation thresholds:
- `ACTUAL_ENTRY_PRICE`: Flags if > 2% deviation from `signal_entry_price`. Returns `requires_confirmation: True`.
- `ACTUAL_COMMISSION`: Flags if > 10x expected (`commission_per_contract * contracts * 2`).
- `ACCOUNT_BALANCE`: Flags if > 5% deviation from `last_known_balance`.

**P3-PG-42: Asset Configuration Validation** -- `validate_asset_config(asset_config)`:
Validates 10 required fields for asset onboarding (`asset_id`, `exchange_timezone`, `point_value`, `tick_size`, `margin_per_contract`, `session_hours`, `roll_calendar`, `p1_data_path`, `p2_data_path`, `data_sources`). Checks P1/P2 output path existence, data source adapter types (REST/FILE/WEBSOCKET/BROKER_API), URL format, session hours format (`HH:MM-HH:MM Timezone`), and numeric sanity.

Accessible via WebSocket (`validate_input` message type) and REST (`POST /api/validate/input`, `POST /api/validate/asset-config`).

### Command Orchestrator (`orchestrator.py`)

The `CommandOrchestrator` class is the event loop coordinating all asynchronous operations.

**Signal stream reader** (`_signal_stream_reader`):
Reads from `STREAM_SIGNALS` Redis Stream using consumer group `GROUP_COMMAND_SIGNALS` with consumer name `command_1`. Uses `read_stream()` with 2-second blocking reads. Each message is passed to `_handle_signal()` and acknowledged via `ack_message()`. Provides durable delivery guarantees -- messages persist in the stream until acknowledged, enabling replay on consumer failure. Reconnects with exponential backoff (capped at 30 seconds) and creates a P2_HIGH incident on connection failure.

**Pub/sub listener** (`_redis_listener`):
Subscribes to `CH_COMMANDS`, `CH_ALERTS`, and `CH_STATUS` for non-critical messages. Commands route through `_handle_command()` (which delegates to `b1_core_routing.route_command()`), alerts through `_handle_alert()` (which delegates to `b7_notifications.route_notification()`), and status through `_handle_status()` (which updates `process_health`).

**Signal handling** (`_handle_signal`):
The `AUTO_EXECUTE` environment variable controls execution mode. When `false` (default/safe), signals are pushed to the GUI for manual TAKEN/SKIPPED confirmation. When `true`, `_auto_execute_signal()` sends orders directly via the `TopstepXAdapter`. Auto-execute skips signals where direction is not BUY or SELL (ORB pending breakout). Each signal also generates a Telegram notification via `b7_notifications.route_notification()`.

**Scheduler** (`_run_scheduler`):
Runs on a 1-second tick with the following periodic tasks:

| Task | Interval | Function |
|------|----------|----------|
| Live market push | 1 second | `_push_live_market()` -- pushes `build_live_market_update()` to all WebSocket users |
| Dashboard refresh | 60 seconds | `_refresh_dashboards()` -- pushes `build_dashboard_snapshot()` with `live_market` excluded |
| API health checks | 30 seconds | `_run_health_checks()` -- runs `b3_api_adapter.run_health_checks()` |
| Heartbeat | 30 seconds | `_publish_heartbeat()` -- publishes to `CH_STATUS` with connection summary |
| Quiet queue flush | 60 seconds | `_flush_quiet_queues()` -- flushes Telegram queues when quiet hours end |
| Daily reconciliation | 19:00 EST | `_check_reconciliation_trigger()` -- runs `b8_reconciliation.run_daily_reconciliation()` |

### FastAPI Application (`api.py`)

The HTTP/WebSocket gateway between the GUI and the Captain system backend.

**WebSocket endpoint** (`/ws/{user_id}`):
- Maximum 3 concurrent sessions per user (`MAX_SESSIONS_PER_USER`). Oldest evicted with close code 4001 (client knows not to auto-reconnect on this code).
- Inbound message types: `command` (routed via `route_command()` with GUI-to-internal type remapping), `validate_input` (delegated to `b10_data_validation`), or echo.
- Cleanup in `finally` block removes disconnected sessions and prunes empty user entries.

**`gui_push(user_id, message)`**:
Non-blocking push to all connected WebSocket sessions for a user. Uses `asyncio.run_coroutine_threadsafe()` to safely schedule sends from background threads (orchestrator, Redis listener) onto the uvicorn event loop. `_make_json_safe()` sanitizes `datetime` to ISO strings and `NaN`/`Infinity` to `null` for browser JSON.parse compatibility. Dead sessions are cleaned up asynchronously via `_safe_ws_send()` with a 10-second timeout.

**REST endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | External health: aggregate status, uptime, circuit breaker state, API connections |
| `/api/status` | GET | Detailed internal status with per-process health and WebSocket session counts |
| `/api/dashboard/{user_id}` | GET | Full dashboard snapshot (sync def -- runs in thread pool to avoid blocking event loop) |
| `/api/system-overview` | GET | Admin-only system overview |
| `/api/reports/types` | GET | List 11 available report types |
| `/api/reports/generate` | POST | Generate a report by type |
| `/api/validate/input` | POST | Validate user input (price/commission/balance) |
| `/api/validate/asset-config` | POST | Validate asset configuration for onboarding |
| `/api/notifications/preferences/{user_id}` | GET | Get notification preferences |
| `/api/notifications/preferences` | POST | Save notification preferences |
| `/api/notifications/read` | POST | Mark notification as read |
| `/api/notifications/test` | POST | Send test notification (admin) |

### Key Decisions

1. **Redis Streams for signal delivery**: Signals migrated from Redis pub/sub (fire-and-forget) to Redis Streams with consumer groups. `STREAM_SIGNALS` with `GROUP_COMMAND_SIGNALS` provides message persistence, acknowledgment via `ack_message()`, and replay capabilities. No legacy `client.publish` calls remain for signals -- audit confirmed complete migration across all three services.

2. **TSM auto-linking with duplicate prevention**: The `_link_tsm_to_account()` function in `main.py` queries P3-D08 for existing rows before inserting. Without this check, every container restart created a duplicate TSM row (observed as 10 identical rows in production). The fix uses a `SELECT count()` existence check.

3. **60-second dashboard excludes live_market**: The `_refresh_dashboards()` method calls `snapshot.pop("live_market", None)` before pushing. This prevents the slower 60-second full snapshot from overwriting the continuously-updated 1Hz market data stream on the frontend, which would cause visible price flickering.

4. **Background-to-async thread bridge**: `gui_push()` uses `asyncio.run_coroutine_threadsafe()` to schedule WebSocket sends on the uvicorn event loop from background threads. This avoids the thread-safety issues of directly calling async code from synchronous Redis listener or scheduler threads.

5. **Compliance gate LOCKED in V1**: The `check_compliance_gate()` function requires all 11 RTS 6 requirements to be satisfied before automated execution is allowed. In V1, this is intentionally locked -- automated order routing is prevented unless `AUTO_EXECUTE` is explicitly enabled.

### Critical Fixes

1. **Warmup gauge query** (`_get_warmup_gauges`): The original query filtered by `captain_status IN ('WARM_UP', 'ACTIVE', 'TRAINING_ONLY')` in a WHERE clause without ensuring the latest row per asset was selected. This caused the GUI to show only ES. Fixed by adding `LATEST ON last_updated PARTITION BY asset_id` before the status filter, then filtering in a Python list comprehension.

2. **AIM status query** (`_get_aim_states`): Could return duplicate AIM status records because the INSERT-based status change pattern (append-only in QuestDB) accumulates historical rows. Fixed by ordering by `last_updated DESC` and deduplicating in Python using a `seen` dict keyed by `(aim_id, asset_id)`, keeping only the first (most recent) row per pair.

3. **TSM duplicate rows**: The `_link_tsm_to_account()` function was called on every container startup without checking for existing links, creating duplicate rows in P3-D08. Fixed by adding a `SELECT count()` check that skips linking if `count > 0`. Confirmed operational with log message "TSM already linked for account PRAC-V2-551001-43861321 -- skipping".

### QuestDB Tables Accessed

| Table | Block | Access Pattern |
|-------|-------|----------------|
| `p3_d00_asset_universe` | B2 | Warmup gauges, data quality |
| `p3_d01_aim_model_states` | B2 | AIM states (deduplicated) |
| `p3_d03_trade_outcome_log` | B2, B6 | Open positions, reports |
| `p3_d04_decay_detector_states` | B2, B6 | Decay alerts |
| `p3_d06_injection_history` | B5, B6 | Strategy comparison |
| `p3_d08_tsm_state` | B2, B4, B8 | TSM config, payout, scaling |
| `p3_d09_report_archive` | B6 | Report metadata |
| `p3_d10_notification_log` | B1, B7 | Notification delivery log |
| `p3_d11_pseudotrader_results` | B5 | Pseudotrader metrics |
| `p3_d14_api_connection_states` | B3 | API health log |
| `p3_d16_user_capital_silos` | B1, B2, B7 | User lookup, capital |
| `p3_d17_system_monitor_state` | B2 | System parameters |
| `p3_d19_reconciliation_log` | B8 | Reconciliation results |
| `p3_d21_incident_log` | B2, B9 | Incident tracking |
| `p3_d22_system_health_diagnostic` | B2 | Health scores, action queue |
| `p3_d23_circuit_breaker_intraday` | B8 | Intraday CB state (daily reset) |
| `p3_session_event_log` | B1, B5, B7, B8 | Audit trail (multi-purpose) |

### Current State

Captain Command is operational as of 2026-03-24. The process successfully:
- Authenticates to TopstepX API and maintains UserStream + MarketStream WebSockets
- Resolves 10 futures contracts (ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN)
- Auto-links TSM configuration to discovered accounts with duplicate prevention
- Routes signals from Online B6 through Redis Streams to GUI WebSocket clients
- Pushes live market data at 1Hz and dashboard snapshots every 60 seconds
- Runs API health checks every 30 seconds with connection status monitoring
- Successfully received and routed 3 trading signals during the first NY session evaluation (21-second pipeline execution)
- Telegram bot operational for signal notifications with inline TAKEN/SKIPPED buttons

The Redis Streams migration from pub/sub is complete across all three services. No legacy `client.publish` calls remain for signals, trade outcomes, or commands. All services use `publish_to_stream` with `STREAM_SIGNALS`, `STREAM_TRADE_OUTCOMES`, and `STREAM_COMMANDS`.

---

## 8. Topstep Integration

### Spec Reference

- `TOPSTEPX_API_REFERENCE.md` (project root) -- Condensed REST and WebSocket API reference validated against official Swagger spec
- `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/Topstep_Optimisation_Functions.md` -- Isaac's complete risk management specification for $150K Topstep accounts with $4,500 trailing MDD
- `docs/completion-validation-docs/Step 1 - Original Specs/06_Program3_Command.md` lines 318-434 -- Block 3 API adapter architecture spec
- `shared/account_lifecycle.py` -- EVAL/XFA/LIVE stage management with constraints per stage

### REST API Client

The REST API client (`captain-system/shared/topstep_client.py`) provides a thread-safe singleton wrapper around the TopstepX / ProjectX Gateway REST API. All endpoints use `POST` requests to `https://api.topstepx.com/api/...` with JSON bodies and Bearer token authentication.

**Authentication Flow:**

1. Initial login via `POST /Auth/loginKey` with `{userName, apiKey}` returns a JWT token valid for approximately 24 hours.
2. The `userName` field requires the user's email address (not a display name).
3. Token refresh occurs automatically via `POST /Auth/validate` when the token age exceeds 20 hours (`TOKEN_REFRESH_THRESHOLD_S = 20 * 3600`).
4. Session termination via `POST /Auth/logout`.
5. All environment variables use the `TOPSTEP_` prefix: `TOPSTEP_USERNAME`, `TOPSTEP_API_KEY`, `TOPSTEP_ACCOUNT_NAME`.

**18 Endpoint Methods:**

| Category | Method | Endpoint | Purpose |
|----------|--------|----------|---------|
| Auth | `authenticate()` | `/Auth/loginKey` | Initial login with API key |
| Auth | `validate_token()` | `/Auth/validate` | Token refresh (no body) |
| Auth | `logout()` | `/Auth/logout` | End session |
| Accounts | `get_accounts()` | `/Account/search` | List active accounts |
| Accounts | `get_account_by_name()` | `/Account/search` | Find account by name string |
| Contracts | `search_contracts()` | `/Contract/search` | Search by text (e.g., "ES") |
| Contracts | `get_contract_by_id()` | `/Contract/searchById` | Lookup by full contract ID |
| History | `get_bars()` | `/History/bars` | OHLCV bars (barUnit: 1=Tick, 2=Min, 3=Hour, 4=Day) |
| Orders | `place_order()` | `/Order/place` | Generic order with type/side/size/price |
| Orders | `place_market_order()` | `/Order/place` | Convenience: type=2 (Market) |
| Orders | `place_limit_order()` | `/Order/place` | Convenience: type=1 (Limit) |
| Orders | `place_stop_order()` | `/Order/place` | Convenience: type=4 (Stop) |
| Orders | `modify_order()` | `/Order/modify` | Modify size or price |
| Orders | `cancel_order()` | `/Order/cancel` | Cancel by orderId |
| Orders | `search_orders()` | `/Order/search` | Orders by time range |
| Orders | `search_open_orders()` | `/Order/searchOpen` | Currently working orders |
| Positions | `search_positions()` | `/Position/search` | Open positions for account |
| Positions | `close_position()` | `/Position/close` | Close by contractId + size |
| Trades | `search_trades()` | `/Trade/search` | Trade history with timestamps |

**Enum Constants (validated against Swagger spec):**

```
OrderSide:    0=Bid(Buy), 1=Ask(Sell)
OrderType:    0=Unknown, 1=Limit, 2=Market, 3=StopLimit, 4=Stop, 5=TrailingStop, 6=JoinBid, 7=JoinAsk
OrderStatus:  0=None, 1=Open, 2=Filled, 3=Cancelled, 4=Expired, 5=Rejected, 6=Pending
PositionType: 0=Undefined, 1=Long, 2=Short
```

**Resilience:** The client uses `tenacity` retry decorators on the underlying `_do_post()` method, retrying up to 3 times with exponential backoff (1-10 seconds) on `requests.Timeout` and `requests.ConnectionError`. A persistent `requests.Session` is reused across all calls. The module exposes a `get_topstep_client()` function that returns a thread-safe singleton instance via double-checked locking.

**Latency Measurement:** `measure_latency()` issues a `/Auth/validate` call and returns round-trip time in milliseconds, used by Block 3.2 health monitoring for 30-second heartbeat checks.

### WebSocket Streaming

The streaming layer (`captain-system/shared/topstep_stream.py`) provides two SignalR WebSocket stream classes for real-time market data and user account updates.

**Protocol:** Microsoft SignalR over WebSocket, using the `signalrcore` Python library. The connection URL converts `https://` to `wss://` and appends the access token as a query parameter (`?access_token={token}`). Negotiation is skipped (`skip_negotiation: True`) for direct WebSocket transport.

**MarketStream** (`rtc.topstepx.com/hubs/market`):

- Supports single-contract or multi-contract subscriptions on a single WebSocket connection.
- Subscribes via `SubscribeContractQuotes([contractId])` on connection open; unsubscribes via `UnsubscribeContractQuotes([contractId])` on stop.
- Three event handlers: `GatewayQuote` (price, bid/ask, volume), `GatewayTrade` (last trade), `GatewayDepth` (DOM level updates).
- **QuoteCache:** A thread-safe module-level singleton (`quote_cache`) that merges partial quote updates. TopstepX sends only changed fields per tick, so the cache overlays non-null values onto existing entries, keyed by contract ID.
- **Symbol Mapping:** Builds a reverse lookup from `config/contract_ids.json` mapping three key formats to canonical contract IDs: full ID (`CON.F.US.EP.M26`), contract name (`ESM6`), and exchange symbol root (`F.US.EP`). This resolves which contract an incoming quote belongs to in multi-contract mode.
- `add_contract()` allows dynamic subscription to additional contracts on a live connection.

**UserStream** (`rtc.topstepx.com/hubs/user`):

- Subscribes to four event channels on connection open: `SubscribeAccounts()`, `SubscribeOrders(accountId)`, `SubscribePositions(accountId)`, `SubscribeTrades(accountId)`.
- Four event handlers: `GatewayUserAccount` (balance, canTrade), `GatewayUserOrder` (order status changes), `GatewayUserPosition` (position updates), `GatewayUserTrade` (trade executions with P&L and fees).
- Maintains internal caches for account data and positions (positions removed from cache when size drops to zero).

**Reconnection Strategy:**

Both streams implement identical multi-tier reconnection:

1. **SignalR automatic reconnect:** `keep_alive_interval=15s`, `reconnect_interval=15s`, `max_attempts=10`.
2. **Rapid failure detection:** If the connection is open for less than 10 seconds before closing, it counts as a rapid failure. After 5 rapid failures, the stream enters a 60-second backoff before retrying.
3. **Delayed reconnect loop:** After the 60-second backoff, `_delayed_reconnect()` attempts to restart the stream. On failure, it schedules another 60-second retry via `threading.Timer`.
4. **Token refresh:** `update_token(new_token)` stops the stream, waits 1 second, and restarts with the fresh token. Called periodically since tokens expire at approximately 24 hours.

**Stream State Machine:** Tracked via `StreamState` enum: `IDLE` -> `CONNECTING` -> `CONNECTED` -> `RECONNECTING` -> `DISCONNECTED` or `ERROR`.

**GUI WebSocket:** The frontend (`captain-gui/src/ws/useWebSocket.ts`) maintains its own WebSocket connection to the captain-command FastAPI server. The GUI reconnection was updated to use infinite retry attempts (previously capped at 30) with exponential backoff (2-second base, 30-second cap) to prevent permanent disconnection during backend restarts or container rebuilds.

### Contract Resolver

The contract resolver (`captain-system/shared/contract_resolver.py`) maps human-readable asset identifiers (e.g., `"ES"`) to TopstepX contract IDs (e.g., `"CON.F.US.EP.M26"`). It uses a four-tier resolution priority:

1. **Session cache** -- In-memory dict populated at startup, thread-safe via `threading.Lock`.
2. **config/contract_ids.json** -- Verified mapping file with tick size and tick value metadata.
3. **P3-D00 roll_calendar** -- Dynamic lookup from the `topstep_contract_id` field in the QuestDB asset universe table.
4. **TopstepX API search** -- Last resort, calls `/Contract/search` with the asset ID as search text.

**10 Configured Assets** (from `captain-system/config/contract_ids.json`, auto-updated 2026-03-23):

| Asset | Contract ID | Name | Tick Size | Tick Value |
|-------|-------------|------|-----------|------------|
| ES | `CON.F.US.EP.M26` | ESM6 | 0.25 | $12.50 |
| MES | `CON.F.US.MES.M26` | MESM6 | 0.25 | $1.25 |
| NQ | `CON.F.US.ENQ.M26` | NQM6 | 0.25 | $5.00 |
| MNQ | `CON.F.US.MNQ.M26` | MNQM6 | 0.25 | $0.50 |
| M2K | `CON.F.US.M2K.M26` | M2KM6 | 0.10 | $0.50 |
| MYM | `CON.F.US.MYM.M26` | MYMM6 | 1.00 | $0.50 |
| NKD | `CON.F.US.NKD.M26` | NKDM6 | 5.00 | $25.00 |
| MGC | `CON.F.US.MGC.J26` | MGCJ6 | 0.10 | $1.00 |
| ZB | `CON.F.US.USA.M26` | ZBM6 | 0.03125 | $31.25 |
| ZN | `CON.F.US.TYA.M26` | ZNM6 | 0.015625 | $15.625 |

Note: MGC uses April expiry (J26); all others use June (M26). ZN uses TYA (standard 10yr Treasury), not TNA (Ultra).

The resolver exposes `preload_contracts()` for startup initialization, `invalidate()` for cache clearing after contract rolls, and `get_all_contract_ids()` to retrieve the current cache state.

### Account Lifecycle

The account lifecycle module (`captain-system/shared/account_lifecycle.py`) models the TopstepX qualification pathway as a three-stage state machine: EVAL -> XFA -> LIVE.

**EVAL (Evaluation / Trading Combine):**

- Starting balance: $150,000
- Maximum loss limit (MLL): $4,500 trailing from peak equity
- Profit target: $9,000 (triggers transition to XFA)
- Contract limit: 15 minis / 150 micros
- No daily loss limit. No payouts permitted.
- No scaling plan.

**XFA (Express Funded Account):**

- MLL: $4,500 trailing
- Contract scaling plan (balance-based tiers):
  - $150,000: 3 minis / 30 micros
  - $151,500: 4 minis / 40 micros
  - $152,000: 5 minis / 50 micros
  - $153,000: 10 minis / 100 micros
  - $154,500: 15 minis / 150 micros
- Maximum 5 payouts; 10% commission on each payout
- Consistency rule: max daily profit $4,500
- After 5 payouts taken, automatic transition to LIVE

**LIVE (Fully Funded):**

- No trailing MLL (MLL = $0 account balance floor)
- Daily drawdown: $4,500 (drops to $2,000 if balance falls below $10,000)
- Daily drawdown breach: auto-liquidate all positions + halt trading until 19:00 EST
- Capital structure: tradable balance capped at $30,000, remainder held in reserve
- Capital unlock: 4 reserve blocks released when cumulative profit reaches $9,000 milestones
- 0% commission on payouts

**Failure at Any Stage:** $226.60 fee logged, immediate revert to fresh $150,000 EVAL account with all counters reset.

The `MultiStageTopstepAccount` class implements the full state machine with `process_trade()` for per-trade constraint enforcement, `end_of_day()` for EOD transition checks, `process_payout()` for withdrawal processing, and `handle_failure()` for breach handling. Every lifecycle event (transition, failure, payout, capital unlock) is recorded as a `LifecycleEvent` dataclass with unique ID, timestamps, balances, and trigger details.

The `to_tsm_dict()` method exports the current stage configuration as a TSM-compatible dict for integration with the pseudotrader replay system and p3_d08_tsm_state records.

**Pre-Deployment Validation:** A comprehensive pseudotrader validation ran the lifecycle state machine across 11 futures assets using 14,815 trades spanning 2009-2025. Results: 7 of 11 assets successfully reached XFA stage (ES, MGC, MNQ, NKD, NQ, ZB, ZN), 3 remained in EVAL (M2K, MES, MYM), and ZT was flagged as unsuitable (17 consecutive EVAL failures, -$1,780 net P&L). Top performers: ZN ($118,420 net P&L, 5.153 Sharpe, zero resets), NQ ($43,217 net, 3 resets), MGC ($32,836 net, zero resets).

### API Adapter (B3)

Block 3 (`captain-system/captain-command/captain_command/blocks/b3_api_adapter.py`) implements the secure one-way boundary between Captain's internal signal pipeline and external broker APIs.

**Security Boundary:**

- 6 sanitized fields outbound: `asset`, `direction`, `size`, `tp`, `sl`, `timestamp`
- 4 fields inbound: `fill_price`, `fill_time`, `balance`, `open_positions`
- Internal system details, strategy logic, AIM information, and regime state are never transmitted externally.

**Abstract Interface (`APIAdapter`):** Five lifecycle methods that all concrete adapters must implement:

1. `connect(api_key, endpoint)` -- Authenticate and establish connection
2. `send_signal(order)` -- Place a sanitized order
3. `receive_fill(order_id)` -- Check fill status
4. `get_account_status()` -- Query account balance and positions
5. `disconnect()` -- Clean shutdown

**TopstepXAdapter Implementation:**

- `connect()` authenticates via the singleton `TopstepXClient`, resolves the target account by name (from `TOPSTEP_ACCOUNT_NAME` env var) or falls back to first active account.
- `send_signal()` implements bracket order placement:
  1. Checks compliance gate (returns `MANUAL_PENDING` if gate locked)
  2. Resolves contract ID from asset symbol via `contract_resolver`
  3. Places market entry order via `place_market_order()`
  4. Places stop-loss exit via `place_stop_order()` at opposite side
  5. Places take-profit exit via `place_limit_order()` at opposite side
  6. Returns composite result with `entry_order_id`, `sl_order_id`, `tp_order_id`
- `receive_fill()` searches recent orders for matching order ID and returns fill price if status is `FILLED` (enum value 2).
- `get_account_status()` queries account balance and aggregates open position sizes.
- `ping()` delegates to `TopstepXClient.measure_latency()` for health monitoring.

**Adapter Registry:** `ADAPTER_REGISTRY = {"TopstepX": TopstepXAdapter}` enables provider-based adapter instantiation via `get_adapter("TopstepX")`.

**Connection Health Monitoring (Block 3.2):** Every 30 seconds (`HEALTH_CHECK_INTERVAL_S`), `run_health_checks()` pings all registered adapters. On failure, it attempts 3 reconnection retries. Persistent failures trigger CRITICAL alerts via the notification system. Health check results are batch-inserted into `p3_d14_api_connection_states` in QuestDB.

**Compliance Gate (Block 3.4):** Implements 11 RTS 6 regulatory requirements via a JSON configuration file. All 11 requirements must be satisfied for automated execution to proceed. In V1, the gate is ALWAYS LOCKED (`execution_mode: "MANUAL"`), meaning all signals require manual confirmation through the GUI unless the `AUTO_EXECUTE` environment variable is explicitly enabled.

### Key Decisions

**VPS Prohibition and Local Deployment:**
TopstepX Terms of Service Section 28 explicitly prohibits trading from VPS, VPN, or cloud-hosted infrastructure. All trading must originate from the trader's own personal device. This constraint fundamentally shaped the deployment architecture: the original two-VPS Hetzner deployment plan was abandoned in favor of local Docker deployment on personal machines. The `docker-compose.local.yml` provides a WSL-specific override with HTTP-only localhost access (no TLS required for local deployment).

**AUTO_EXECUTE Flag:**
The `AUTO_EXECUTE` environment variable (accepts `"1"`, `"true"`, or `"yes"`, case-insensitive) controls whether signals bypass the manual TAKEN/SKIPPED confirmation workflow. When enabled, the `CommandOrchestrator._auto_execute_signal()` method retrieves the TopstepXAdapter from the active connections registry, validates connection status, and calls `adapter.send_signal()` with the sanitized 6-field order. Auto-execution status is included in Telegram notifications. Default is `false` (manual confirmation required).

**Reconnection Strategy:**
A multi-layer reconnection architecture ensures resilience:
- REST client: `tenacity` retry with exponential backoff (3 attempts, 1-10s)
- WebSocket streams: SignalR auto-reconnect (10 attempts, 15s interval) + rapid failure detection (5 failures in 10s triggers 60s backoff) + infinite delayed reconnect loop
- GUI WebSocket: infinite retry with exponential backoff (2s base, 30s cap)
- API adapter health: 30s heartbeat with 3 reconnect retries per cycle

**TSM Configuration Templates:**
The `topstep_150k_eval.json` template provides a complete TSM configuration for EVAL accounts, including $150,000 starting balance, $4,500 MDD, $9,000 profit target, instrument-specific round-turn fees (ES/NQ: $2.80, MES/MNQ: $0.74), and TopstepX optimization parameters (`p=0.005`, `e=0.01`, `c=0.5`). TSM files auto-link to discovered TopstepX accounts by matching provider, stage, and balance.

**SOD Parameter Recalculation:**
Per the Topstep Optimisation Functions spec, all start-of-day (SOD) locked parameters recalculate at 19:00 EST (TopstepX's MDD recalculation time). The trading day runs from 19:00 EST to 18:59 EST. Each day is treated as an independent time series. The MDD% function `f(A) = 4500/A` is convex, meaning the first dollar of profit causes the most MDD% damage -- proof that optimal payout strategy is to take the maximum payout ($5,000) as early as possible.

### Critical Constraints

**ToS Section 28 -- VPS Prohibition:**
TopstepX Terms of Service Section 28 categorically prohibits execution from VPS, VPN, or cloud-hosted environments. Violation constitutes grounds for immediate account termination. All Captain System deployment must occur on the trader's personal device running Docker locally. This is the single most important deployment constraint.

**Single WebSocket Session Per Username:**
TopstepX enforces one WebSocket connection per username. Running the Captain System API and the TopstepX trading platform simultaneously creates a session conflict. The recommended procedure is to start the Captain System API first, then open the TopstepX platform charts (which use a separate data path).

**API Risk Parameter Gap:**
The TopstepX `/Account/search` endpoint and `GatewayUserAccount` WebSocket event both return minimal account data: `id`, `name`, `balance`, `canTrade`, `simulated`. They do not expose risk management parameters required for TSM initialization: `max_drawdown_limit`, `max_daily_loss`, `profit_target`, `starting_balance`, or `risk_goal`. These values must be provided via TSM template files (e.g., `topstep_150k_eval.json`) and cannot be auto-discovered from the API.

**Token Expiry:**
Authentication tokens expire after approximately 24 hours. WebSocket streams do not auto-refresh tokens. The REST client handles this transparently via `_ensure_token()`, but streams require explicit `update_token()` calls that trigger a stop-wait-restart cycle.

**Rate Limits:**
The API supports approximately 400 concurrent requests. No formal rate limit documentation exists; this value was determined empirically.

**Contract Roll Management:**
Contract IDs change quarterly (e.g., `CON.F.US.EP.M26` for June 2026 expiry). The `contract_ids.json` file was last auto-updated 2026-03-23. After a contract roll, `contract_resolver.invalidate()` clears the cache to force re-resolution from the updated config or API.

**Session Hours:**
All 10 configured assets have session hours set to `{"NY":true,"LON":true,"APAC":true}` in the P3-D00 asset universe table, enabling trading at New York (9:30am ET), London (3am ET), and APAC (8pm ET) session opens. Prior to this configuration, null session hours caused a default to NY-only, which would have filtered out all assets during London and APAC evaluations.

### Current State

The TopstepX integration is fully implemented and operational:

- **REST Client:** 18 endpoints implemented with automatic token management, retry logic, and thread-safe singleton pattern. Authentication tested with live TopstepX credentials.
- **WebSocket Streaming:** MarketStream and UserStream classes operational with multi-contract support, partial quote merging, symbol mapping, and multi-tier reconnection. MarketStream confirmed receiving live quotes for all 10 configured contracts.
- **Contract Resolver:** Four-tier resolution chain populated with 10 futures assets. Config file auto-maintained.
- **Account Lifecycle:** Full EVAL/XFA/LIVE state machine validated across 14,815 trades and 11 assets in pre-deployment pseudotrader testing. 24/24 unit tests passing.
- **API Adapter:** Bracket order placement (entry + SL + TP) implemented with compliance gate, contract resolution, and health monitoring. V1 compliance gate locked to MANUAL mode by default.
- **Deployment:** Infrastructure configured for local Docker deployment with `docker-compose.local.yml` (WSL/localhost override). All 6 containers (QuestDB, Redis, captain-offline, captain-online, captain-command, nginx) health-checked and operational.

**Known Stability Vulnerabilities (from connectivity audit):**

A comprehensive connectivity audit identified 12 vulnerability points. The most relevant to TopstepX integration:
- VUL-05 (P1): TopstepX WebSocket streams permanently stop reconnecting after 5 rapid failures within 10 seconds. Mitigated by the delayed reconnect loop but not fully eliminated.
- VUL-10 (P1): TopstepX REST client retry logic handles transient network errors but does not retry on HTTP 5xx responses from the API itself.
- The QuestDB JVM crash vulnerability (VUL-07, P0) on WSL2 can indirectly affect TopstepX integration by disrupting the signal pipeline that produces trade orders.

---

## 9. Local Backtester & Multi-Asset Screening

### Spec Reference

- **P1 Pipeline Spec:** `docs/completion-validation-docs/Step 1 - Original Specs/01_Program1.md` -- P1 model screening with 144 features across 6 control models
- **P2 Regime Spec:** `docs/completion-validation-docs/Step 1 - Original Specs/02_Program2.md` -- Regime-conditioned strategy selection
- **Model Generator Config:** `model_generator/model_generator_config_research.json` -- 44+ strategy definitions across 5 tiers
- **Exit Grid Spec:** V3 amendments requiring parameterized TP/SL as OR-range multiples with combinatorial grid testing
- **Multi-Asset Architecture:** `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/Nomaan_Master_Build_Guide.md` -- 17-asset universe across 4 global sessions

### What Was Built

The MOST project's P1/P2 pipeline was originally designed to execute on QuantConnect (QC) cloud infrastructure, where backtests ran one at a time with 15-second polling intervals and 30-minute timeouts per backtest via `batch_launcher.py`. This sequential execution model made comprehensive multi-asset screening across thousands of model variants impractical -- a single-asset run could take days.

A local backtesting infrastructure was built to run the entire P1/P2 screening pipeline outside QC cloud, enabling:

1. **Parallel execution** -- 16-core multiprocessing at the model-group level, replacing sequential QC polling
2. **Exit-grid factoring** -- exploiting the mathematical property that sibling exit variants share identical trade dates and feature values, differing only in returns (`r_mi`), reducing computation by up to 20x per entry variant
3. **Multi-asset screening** -- processing 17 futures instruments across 4 global sessions (NY, London, APAC, NY_PRE) in a single orchestrated pipeline run
4. **Full local data pipeline** -- raw OHLCV bars extracted from QC Object Store, decoded locally, and consumed by a local feature extractor and backtest engine

The local infrastructure lives primarily in three locations:

| Path | Purpose |
|------|---------|
| `local_backtester/` | Core backtest engine, feature extraction, optimized pipeline runner |
| `run_full_screening.py` | Top-level 5-phase multi-tier screening orchestrator |
| `run_asset_gap_fill.py` | Gap-fill runner for assets missing sample history |
| `model_generator/` | Automated model variant generation from strategy configs |
| `pipeline_p2/` | P2 regime screening pipeline with local P1 bridge |
| `mega-backtest-pipeline-extraction-new-decode/` | Raw market data storage and encode/decode utilities |

### Pipeline Architecture

#### Model Generation

The model generator (`model_generator/model_generator.py`) creates an N-dimensional Cartesian product grid:

```
total_variants = entry_variants x directions x param_sweeps x assets x exit_grid
```

Strategy definitions are organized into 5 tiers by complexity:

| Tier | Content | Strategy Types |
|------|---------|----------------|
| 1 | Foundational ORB, volume-confirmed momentum, gap-filtered entries | ST-01 breakout |
| 2 | Regime detection, macro triggers, cross-market analysis | ST-02 fade, ST-03 conditional ORB |
| 3 | Temporal patterns, sentiment contrarian, factor uncertainty | ST-04 momentum, ST-05 delayed |
| 5 | Advanced cross-sectional ML approaches | ST-06 cross-asset |

The exit grid defines 20 combinations per entry variant: 5 take-profit multiples (0.50, 0.70, 1.05, 1.40, 2.00) crossed with 4 stop-loss multiples (0.25, 0.35, 0.50, 0.75), where each value is an OR-range multiplier (e.g., `sl = 0.35 x opening_range`).

Configuration files in `model_generator/`:

- `model_generator_config.json` -- Production Batch 1 config (single exit combo: tp=0.70, sl=0.35)
- `model_generator_config_research.json` -- Full research config (44+ strategies, 20 exit combos)
- `model_generator_config_batch2.json` -- Batch 2 config (26 models M-045 to M-070, ~1,240 variants)
- `model_generator_config_nq_only.json` -- NQ-specific single-asset config

Combined Batch 1 (~9,200) and Batch 2 (~1,240) produce approximately 10,440 model variants for comprehensive screening.

#### Optimized Pipeline Runner

`local_backtester/run_pipeline_optimised.py` (37KB) implements exit-grid factoring to dramatically reduce computation:

1. **Group identification** -- Entry variants are grouped by strategy, direction, and parameters. Each group has 20 exit-grid siblings sharing identical trade dates and feature values.
2. **Representative execution** -- Full optimized Block 2B (B2B) runs on 1 representative model per group.
3. **Parametric check** -- 19 siblings receive a parametric-only evaluation (recomputing returns with different TP/SL but reusing cached trade structure).
4. **Bootstrap fallback** -- Borderline siblings that cannot be resolved parametrically receive full bootstrap evaluation.
5. **Multiprocessing** -- 16-core parallel execution at the group level via Python's `multiprocessing` module.

Supporting modules in `local_backtester/`:

| Module | Size | Purpose |
|--------|------|---------|
| `backtest_engine.py` | 22KB | Core backtest execution engine |
| `batch_optimised.py` | 27KB | Batch runner with `--asset` and `--output` flags |
| `block2b_optimised.py` | 25KB | Optimized Block 2B implementation |
| `feature_extractor.py` | 10KB | D-11 feature extraction (144 features) from OHLCV bars |
| `feature_bridge.py` | 8KB | Bridge between feature engine and backtester |
| `data_loader.py` | 11KB | Market data loading from local filesystem |
| `exit_replayer.py` | 11KB | Exit-grid replay for parametric sibling evaluation |
| `pipeline_adapter.py` | 8KB | Adapter connecting local backtester to P1 pipeline blocks |
| `output_manager.py` | 11KB | Result serialization and output directory management |

#### 5-Phase Multi-Tier Screening

`run_full_screening.py` orchestrates the complete screening pipeline:

| Phase | Operation | Models | Est. Runtime |
|-------|-----------|--------|-------------|
| 1 | Generate models for Tiers 2, 3, 5 | 95,880 generated | ~2 minutes |
| 2 | Tier 1 Gap Fill (NQ + proxied micros) | 19,200 existing | ~2-3 hours |
| 3 | Tier 2 Full Screening (all 17 assets) | 63,240 models | ~4-6 hours |
| 4 | Tier 3 Full Screening (all 17 assets) | 31,960 models | ~2-3 hours |
| 5 | Tier 5 Full Screening (all 17 assets) | 680 models | ~15 minutes |
| **Total** | | **95,880 new** | **~8-12 hours** |

Execution controls:

```
python run_full_screening.py --dry-run                # Validate without executing
python run_full_screening.py --batch-workers 5 --pipeline-workers 20
python run_full_screening.py --skip-phase 1,2         # Resume from Phase 3
python run_full_screening.py --only-phase 2           # Run only Tier 1 gap fill
```

All outputs are stored in timestamped directories (`p1_screening_runs/run_YYYYMMDD_HHMMSS/`) guaranteeing no existing data is overwritten. Intelligent progress filtering (20 regex patterns, 10-second heartbeat, lines_total/lines_shown tracking) provides uniform terminal experience across both the multi-phase screener and single-phase gap fill runner.

### Multi-Asset Screening

#### Asset Universe

P1 screening processed 17 futures instruments across 4 global trading sessions:

| Session | Assets | Trading Hours (ET) |
|---------|--------|-------------------|
| NY | ES, NQ, MES, MNQ, M2K, MYM | 09:30-16:10 |
| LONDON | MGC, SIL, M6E, M6A, M6B | 03:00-11:30 |
| NY_PRE | MCL, ZN, ZT, ZB | 06:00-13:30 |
| APAC | NKD, 6J | 18:00-03:00 (overnight) |

Market data sourced from `mega-backtest-pipeline-extraction-new-decode/market_data/{asset}/` containing raw OHLCV bars extracted from QC Object Store via the paste-back workflow. Feature extraction (`local_backtester/feature_extractor.py`) consumes these bars and outputs D-11 features to `local_backtester/d11_features/{ASSET}_features.json`, with 1,131 to 4,381 days of data per asset.

#### Proxy Infrastructure

Micro futures contracts lack pre-2019 historical data. The gap-fill runner (`run_asset_gap_fill.py`) employs proxy mapping to use full-size contract bars:

| Micro Contract | Proxy Source | Relationship |
|---------------|-------------|--------------|
| MES | ES | Identical OHLCV, 10x point-value multiplier |
| MNQ | NQ | Identical OHLCV, 10x point-value multiplier |
| MYM | YM | Identical OHLCV, 10x point-value multiplier |
| M2K | RTY | Identical OHLCV, 10x point-value multiplier |

This proxy infrastructure enables screening micro contracts against the full 2009-2026 sample history of their parent instruments.

#### P1 Outputs Inventory

P1 outputs are stored in `captain-system/data/p1_outputs/` with 19 asset directories (17 instruments plus ES and RTY proxy parents) containing 56 JSON files:

| Asset Pattern | Files | Contents |
|--------------|-------|----------|
| 12 dual-strategy assets (6J, M6A, M6B, M6E, MCL, MES, MGC, NKD, SIL, ZB, ZN, ZT) | `s1_d13_features.json`, `s1_trade_log.json`, `s2_d13_features.json`, `s2_trade_log.json` | Feature weights + trade logs for 2 strategy sessions |
| 3 single-strategy assets (M2K, MNQ, MYM) | `s1_d13_features.json`, `s1_trade_log.json` | Feature weights + trade logs for 1 strategy session |
| ES | `d22_trade_log_es.json` | Bootstrap-specific format (14,472 trades, 2009-2026) |

P1 screening run output (`p1_screening_runs/run_20260321_025856/`):

- `consolidated_report.json` -- Combined survivors across all tiers
- `final_report.json` -- Final filtered results
- `logs/` -- Phase-organized logs: `phase{N}a_batch.log` (batch ops) + `phase{N}b_{SYMBOL}_pipeline.log` (per-symbol)
- `models_tier2/` -- Model files: `M-{ID}_{Strategy}_{Direction}_parameters_{Asset}_tp_multiple{X}_sl_multiple{Y}.json`

#### Survivor Counts by Tier

The P1 screening run (March 21, 2026) produced survivors distributed across tiers:

- **Tier 1 Gap Fill:** 5,803 survivors across M2K, MES, MNQ, MYM, NQ
- **Tier 2 Screening:** 121 survivors across M2K, MNQ, NKD, NQ
- **Tier 3 Screening:** 0 survivors
- **Total combined survivors:** 11,614 across 11 assets

### Missing Asset Screening

Six assets from the original 17-asset universe failed P1 screening entirely, producing zero combined survivors:

| Asset | Class | s1 Trade Count | Tier 2 Groups Tested | Tier 2 Variants | Survivors |
|-------|-------|---------------|---------------------|-----------------|-----------|
| 6J | Currency (JPY) | 2,125 | 0 | 0 | 0 |
| M6A | Currency (AUD) | 2,523 | 0 | 0 | 0 |
| M6B | Currency (GBP) | 1,507 | 4 | 80 | 0 |
| M6E | Currency (EUR) | 2,973 | 8 | 160 | 0 |
| MCL | Commodity (Crude) | 1,059 | 24 | 480 | 0 |
| SIL | Commodity (Silver) | 13 | 0 | 0 | 0 |

All six assets were processed through the full pipeline including Tier 2 and Tier 3 screening phases with per-symbol pipeline logs. MCL (crude oil) tested the most variants (480) but produced zero survivors. SIL had only 13 s1 trades, indicating severe data sparsity. The four currency pairs (6J, M6A, M6B, M6E) and two commodities (MCL, SIL) uniformly failed to meet P1 survival criteria at every screening stage.

Because they produced zero combined survivors, these six assets were excluded from P2 run configuration (`p2_outputs/run_20260321_111438/run_config.json` lists only 11 assets) and no D-22 staging files were generated for them.

### Data Integration

#### P2 Pipeline

The P2 regime screening pipeline (`pipeline_p2/`) implements five processing groups:

| Group | Module | Size | Purpose |
|-------|--------|------|---------|
| PG01 | `p2_pg01_regime_compute.py` | 26KB | Daily realized variance, VIX regime classification |
| PG02 | `p2_pg02_strategy_regime_test.py` | 33KB | Strategy performance by regime |
| PG03 | `p2_pg03_strategy_selection.py` | 27KB | Locked strategy selection (best m, k per asset) |
| PG04 | `p2_pg04_regime_prediction.py` | 58KB | XGBoost regime classifier training |
| PG05 | `p2_pg05_complexity_tier.py` | 6KB | Complexity tier assignment |

The critical integration layer is `p1_local_bridge.py` (34KB), which converts local backtester P1 outputs to P2-consumable format including D-07 samples, D-20 thresholds, D-22 trade logs with VIX regime tags, and D-24 OO scores. This bridge was modified March 22, 2026, aligning with the P1 run timestamp.

P2 Block 1 was adapted for minute-bar data with session-specific regular trading hours (NY/London/APAC/NY_PRE) replacing daily bar assumptions from the original QC cloud implementation.

Three P2 pipeline runs were executed March 21-22, 2026:

- `run_20260321_105825` -- Initial run
- `run_20260321_111438` -- Main 10-asset run
- `run_20260322_142153` -- NKD fix run

All 11 assets classified as **REGIME_NEUTRAL** with locked strategy parameters:

```
ES(m=7,k=33)  NQ(m=3,k=32)  M2K(m=5,k=32)  MES(m=7,k=32)  MNQ(m=5,k=32)
MYM(m=9,k=115) NKD(m=6,k=6)  MGC(m=2,k=29)  ZB(m=10,k=113) ZN(m=4,k=37) ZT(m=1,k=25)
```

Each asset generates a standardized P2 output suite: `p2_d01_rv_daily.json`, `p2_d02_regime_labels.json`, `p2_d04_correlations.json`, `p2_d05_composite_scores.json`, `p2_d06_locked_strategy.json`, `p2_d07_prediction_model.json`.

#### VIX/VXV Data

VIX data resides in `captain-system/data/vix/vix_daily_close.csv` containing 4,360 records spanning approximately 17 years (1990-01-02 through 2026-03-21). The data was extracted from CBOE via QuantConnect's DataSource library using the paste-back workflow: running a research notebook cell, copying output to `viv_vxv_raw.txt`, then processing with local decode scripts. IVTS (Implied Volatility Term Structure) analysis uses the VIX/VXV ratio to detect term structure shape -- ratios above 1.0 signal backwardation (market stress), ratios below 1.0 indicate normal contango.

VIX data serves dual purposes: AIM-11 z-score calculations for abnormal volatility regime detection, and B5C circuit breaker VIX spike detection.

#### Captain-System Data Directory

`captain-system/data/` integrates nine data categories mounted read-only into Docker containers at `/captain/data/`:

| Directory | Contents |
|-----------|----------|
| `p1_outputs/` | P1 trade logs and feature weights for 17 assets (56 JSON files) |
| `p2_outputs/` | P2 regime labels, locked strategies, prediction models |
| `calendar/` | Trading day schedules and holiday calendars |
| `cot/` | Commitment of Traders positioning data |
| `macro/` | GPR geopolitical risk index, macroeconomic indicators |
| `market/` | Historical and real-time market data |
| `options/` | Options market data |
| `roll_calendar/` | Futures contract roll date management |
| `vix/` | VIX daily close history (4,360 records) |

#### P2 Staging Data

`pipeline_p2/staging/` contains intermediate processing outputs including the exhaustive ES trade log (`d22_trade_log_es.json`, 6.3 million lines covering all parameter combinations from 2009 onwards). This staging directory is excluded from git via `.gitignore` as regenerable data (~495 MB trade logs).

#### Bootstrap Loading

`scripts/load_p2_multi_asset.py` provides comprehensive multi-asset seeding capability for the Captain system. It loads P2 outputs from both pipeline runs (March 21-22, 2026) for all 11 assets, filters by OO score floor (>= 0.50), converts regime labels from P2 format (LOW/MEDIUM/HIGH) to bootstrap format (LOW_VOL/HIGH_VOL), and seeds Tier 1 AIMs (models 4, 6, 8, 11, 12, 15). Three execution modes: `--dry-run` (preview), default (stage + register in QuestDB), `--bootstrap` (stage + register + full EWMA/BOCPD/Kelly initialization).

### Key Decisions

1. **Exit-grid factoring over brute force.** The observation that 20 exit-grid siblings share identical trade dates and feature values (differing only in `r_mi`) enabled a 20x reduction in full backtest computation. The optimized runner executes full B2B on one representative per group and uses parametric replay for siblings.

2. **Multi-tier over single-tier screening.** The 5-tier strategy library stratifies by complexity: Tier 1 foundational strategies establish baseline, Tier 2 adds regime conditioning, Tier 3 incorporates macro/sentiment triggers, Tier 5 tests cross-sectional ML. This prevents simpler strategies from being drowned out by parameter-rich alternatives during OO aggregation.

3. **Proxy mapping for micro contracts.** Rather than discarding micro futures due to limited history (post-2019 only), the system maps them to parent contracts (MES to ES, MNQ to NQ, MYM to YM, M2K to RTY) with adjusted point-value multipliers. This preserves the 2009-2026 sample depth required for statistically robust screening.

4. **Local over cloud execution.** QC cloud's sequential polling model (15-second intervals, 30-minute timeout per backtest) made 96,000-variant screening infeasible. Local multiprocessing on a 24-core machine reduced total runtime from weeks to 8-12 hours.

5. **Timestamped run isolation.** All pipeline outputs go to timestamped directories (`run_YYYYMMDD_HHMMSS/`) ensuring no overwrite of prior results. Old runs can be cleared with explicit directory deletion when no longer needed.

6. **OO threshold filter.** A two-tier filter was added to Block 5: absolute floor OO > 0.55 AND top 15% percentile of all tested (m, k) pairs. This prevents weak-signal strategies from consuming AIM registry slots.

### Results

**P1 Screening Summary:**

- **17 assets** processed through full P1 screening pipeline
- **11 assets** produced combined survivors: ES, NQ, M2K, MES, MNQ, MYM, NKD, MGC, ZB, ZN, ZT
- **6 assets** produced zero survivors: 6J, M6A, M6B, M6E, MCL, SIL (all currencies and commodities)
- **11,614 total survivor strategies** across the 11 qualifying assets
- All 6 failed assets are currency pairs or commodities, suggesting ORB-style strategies underperform in these markets

**P2 Regime Classification:**

- All 11 surviving assets classified as **REGIME_NEUTRAL** (tau threshold = 0.06, p-value = 0.19)
- Each asset received a locked (m, k) strategy pair for production use
- OO score floor of 0.50 applied to exclude weak performers from active trading

**Data Pipeline:**

- P1 outputs: 56 JSON files across 17 asset directories
- P2 outputs: 3 pipeline runs, 7 output files per asset, 11 asset configurations
- ES bootstrap trade log: 14,472 records spanning 2009-2026 (247KB curated; 6.3M lines exhaustive in staging)
- VIX history: 4,360 daily records for z-score and spike detection

### Current State

The local backtester infrastructure is fully operational and available for future use. Primary scenarios for re-execution:

1. **Decay-triggered P1 rescreen.** If Captain Offline's Level 3 decay detection (BOCPD/CUSUM) flags strategy degradation, the pipeline can re-run P1 screening with updated market data to identify replacement strategies.
2. **New asset addition.** If TopstepX adds new futures instruments, model generation configs can be extended and the full 5-phase pipeline executed for the new assets.
3. **Strategy library expansion.** Batch 2 model definitions (`model_generator_config_batch2.json`) are ready for execution, adding 1,240 variants across 26 new entry strategies.
4. **Exit grid refinement.** The exit-grid factoring infrastructure enables rapid re-evaluation of alternative TP/SL combinations without re-running full backtests.

Pipeline run directories (`p1_screening_runs/`, `p1_gap_fill_runs/`) are excluded from git and can be cleared between runs. The current P1 run (`run_20260321_025856`) is retained as the authoritative screening result feeding into production P2 outputs and captain-system bootstrap data.

---

## 10. Deployment, Safety & Stability

### Spec Reference

- `DEPLOYMENT_PLAN.md` -- Hetzner two-VPS deployment plan (superseded by local-only requirement)
- `PRE_DEPLOY_CHECKLIST.md` -- Pre-deployment verification steps
- `captain-system/docs/VULNERABILITY_BUILD_PLAN.md` -- 12-vulnerability phased remediation plan
- `captain-system/.env.template` -- Environment variable documentation with safety defaults
- `captain-system/docker-compose.yml` -- Container orchestration (6 services)
- `captain-system/docker-compose.local.yml` -- Local deployment overlay (localhost HTTP)

---

### Deployment Architecture

#### Local-Only Constraint (TopstepX ToS Section 28)

The Captain System is deployed exclusively on each trader's personal machine. TopstepX Terms of Service Section 28 explicitly prohibits "Using any VPN or VPS on Accounts," with consequences including account termination and profit forfeiture. This prohibition applies to all VPS interaction, not solely order execution. JWT authentication, WebSocket market data streams, and REST health checks all constitute "using a VPS on Accounts." A split deployment approach -- running signal generation on a VPS while executing orders locally -- also violates the ToS because the VPS holds an authenticated TopstepX session.

The original deployment plan (`DEPLOYMENT_PLAN.md`) specified a two-VPS Hetzner architecture for multi-user IP isolation. This plan was superseded when the ToS prohibition was identified. The system now targets Windows 11 with WSL 2 and Docker Desktop as the deployment platform, running on the trader's personal device. TopstepX explicitly permits API automation from personal devices, making local Docker deployment fully compliant.

This constraint is non-negotiable and applies to all future architecture decisions. If deployment architecture is revisited, local-only operation on personal devices remains the baseline requirement.

#### Container Topology

The Captain System runs as six Docker containers orchestrated via Docker Compose:

| Container | Role | Restart Policy | Health Check |
|-----------|------|----------------|--------------|
| `questdb` | Time-series database (29 tables) | `unless-stopped` | HTTP query `SELECT 1` every 10s |
| `redis` | Message broker (Streams + cache) | `unless-stopped` | `redis-cli ping` every 10s |
| `captain-offline` | Strategic brain (AIM training, decay, Kelly) | `unless-stopped` | Dual: QuestDB connect + Redis ping |
| `captain-online` | Signal engine (data through signal output) | `unless-stopped` | Dual: QuestDB connect + Redis ping |
| `captain-command` | Linking layer (routing, GUI API, reconciliation) | `unless-stopped` | FastAPI `/api/health` endpoint |
| `captain-gui` | React build container (ephemeral) | `no` | N/A (exits after build) |
| `nginx` | Reverse proxy serving GUI + API | `unless-stopped` | Depends on upstream health |

All service ports are bound to `127.0.0.1` only, preventing external network access. The QuestDB web console (port 9000), PostgreSQL wire protocol (port 8812), Redis (port 6379), and FastAPI (port 8000) are accessible only from localhost.

Docker Compose dependency chains ensure correct startup ordering:

1. `questdb` and `redis` start first with health checks.
2. `captain-offline`, `captain-online`, and `captain-command` wait for both `questdb` and `redis` to report `service_healthy`.
3. `captain-gui` builds React assets into a shared `gui-dist` volume, then exits.
4. `nginx` waits for both `captain-command` (service_healthy) and `captain-gui` (service_completed_successfully) before starting.

The `captain-gui` container uses `service_completed_successfully` rather than `service_healthy` as its dependency condition because it is an ephemeral build container. It runs `npm build`, copies the compiled assets to the shared volume, and exits with status code 0. Docker Compose healthchecks only function for long-running containers, so `service_completed_successfully` is the correct orchestration primitive for build-once containers.

#### Environment Configuration

The `.env.template` file documents all required and optional environment variables with safety-conscious defaults:

- **`TRADING_ENVIRONMENT=PAPER`** -- Default is PAPER mode, requiring explicit override to LIVE.
- **`AUTO_EXECUTE=false`** -- Default requires manual GUI confirmation for all signals. When set to `true`, signals bypass the TAKEN/SKIPPED confirmation workflow and route directly through the TopstepX API adapter for automated order placement.
- **`VAULT_MASTER_KEY`** -- AES-256-GCM encryption key for the API credential vault. Must be generated once and securely stored.
- **`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`** -- Optional notification delivery. Invalid tokens do not block trading execution.

The `.env.template` includes explicit warnings about `AUTO_EXECUTE=true`, stating it should be enabled "ONLY for practice accounts or when you want fully automated trading." This converts Captain from a decision-support system to a fully autonomous trading system.

All three Captain processes validate required environment variables at startup. Missing TopstepX credentials, invalid contract IDs, or absent vault keys cause immediate startup failure rather than silent runtime errors.

#### Timezone Standardization

All containers set `TZ: America/New_York` as an environment variable. Session open detection (NY 9:30 AM, LON 3:00 AM, APAC 8:00 PM), trade timestamps, and QuestDB time-series data all operate in Eastern Time. This eliminates timezone conversion errors across the pipeline.

---

### Safety Guards

#### PAPER as Default Trading Environment

The `TRADING_ENVIRONMENT` variable defaults to `PAPER` in `.env.template`. This ensures that a fresh installation cannot accidentally execute live trades. Transitioning to `LIVE` requires deliberate operator action -- editing the `.env` file and restarting the affected containers (`captain-command` and `captain-online`).

#### Environment Validation at Startup

Each of the three Captain processes performs environment validation during initialization. The `main.py` entry point for each service checks for required environment variables before entering the event loop. This fail-fast behavior prevents scenarios where a misconfigured service runs for hours before encountering a missing credential at trade execution time.

#### Auto-Execute Safety

The `AUTO_EXECUTE` environment variable controls whether generated signals are automatically submitted as broker orders or presented in the GUI for manual confirmation. The default value of `false` implements a conservative workflow:

- **`AUTO_EXECUTE=false`** (default): Signals appear in the GUI. The operator reviews each signal and explicitly selects TAKEN or SKIPPED. Only TAKEN signals proceed to order placement.
- **`AUTO_EXECUTE=true`**: Signals generated by Captain Online B6 are published to Redis, consumed by Captain Command, and immediately routed through the TopstepX API adapter to place bracket orders (entry + stop-loss + take-profit) without human intervention.

#### Non-Root Docker Containers (Attempted and Reverted)

An initial safety measure added non-root `USER` directives to all Dockerfiles. This was subsequently removed (commit `471220f`) because non-root users are incompatible with Docker volume mounts on the host filesystem. The containers run as root within their isolated Docker environment, with security enforced at the network level (localhost-only port bindings) rather than at the user level.

#### Localhost-Only Port Bindings

All exposed ports in `docker-compose.yml` are bound to `127.0.0.1`, ensuring no container is directly accessible from the network. Access is mediated through the nginx reverse proxy, which itself listens only on localhost in the local deployment configuration (`docker-compose.local.yml`).

---

### Vulnerability Remediation (12 Vulnerabilities, 4 Phases)

The vulnerability remediation project identified and resolved 12 instability points across the Captain System infrastructure. The work was organized into a phased build plan documented in `captain-system/docs/VULNERABILITY_BUILD_PLAN.md`, progressing from critical connection failures through message delivery guarantees to user experience polish. All 12 vulnerabilities were addressed in a single day (March 24, 2026), transforming the system from a fragile prototype to a production-capable trading infrastructure.

#### Pre-Phase (P0): Critical Fixes (3 Vulnerabilities)

Three critical vulnerabilities were resolved before the formal phased plan began:

| ID | Vulnerability | Fix | File |
|----|--------------|-----|------|
| VUL-07 | QuestDB JVM JVMCI compiler crashes | `JAVA_TOOL_OPTIONS: "-XX:-UseJVMCICompiler"` | `docker-compose.yml:13` |
| VUL-02 | Indefinite database connection hangs | `connect_timeout=5`, `statement_timeout=15000` | `shared/questdb_client.py:37-38` |
| VUL-04 | Tight retry loops exhausting resources | Exponential backoff (1s to 30s cap) | `offline/orchestrator.py`, `online/orchestrator.py` |

VUL-07 disabled the JVM JVMCI compiler that caused intermittent QuestDB process crashes. VUL-02 added socket-level and statement-level timeouts to prevent queries from blocking indefinitely on a degraded database. VUL-04 replaced tight retry loops in both orchestrators with exponential backoff capped at 30 seconds, preventing CPU and connection exhaustion during extended outages.

#### Phase 1: Connection Resilience (3 Vulnerabilities)

Phase 1 eliminated connection exhaustion and enabled automatic recovery across the two primary data stores.

**VUL-01 -- QuestDB Connection Pooling** (`shared/questdb_client.py`)

The original `get_connection()` function created a new TCP connection per call. Under load, this generated hundreds of connections per minute, risking exhaustion of QuestDB's 256-connection limit. The fix replaced per-call connections with a `ThreadedConnectionPool` (min=2, max=10) using thread-safe double-checked locking for lazy initialization. The pool's `getconn()` and `putconn()` lifecycle management ensures connections are reused rather than created and destroyed. The context manager `get_cursor()` wraps the pool interaction, guaranteeing connections are returned even when exceptions occur. All existing callers remained compatible -- the API signatures were unchanged.

**VUL-06 -- Redis Client Singleton** (`shared/redis_client.py`)

Each call to `get_redis_client()` previously created a new `redis.Redis` instance, each with its own internal connection pool (default capacity: 50 connections). Calling the function N times could create N x 50 potential connections. The fix implemented a module-level singleton with thread-safe double-checked locking. The singleton client is configured with `socket_timeout=5` and `socket_connect_timeout=5` to prevent indefinite blocking on dead connections, `retry_on_error=[TimeoutError]` for automatic retry on transient socket timeouts, and `health_check_interval=30` for periodic PING-based connection validation. The `get_redis_pubsub()` function was simplified to return a pubsub instance from the singleton client. A subsequent fix replaced the deprecated `retry_on_timeout=True` parameter with `retry_on_error=[TimeoutError]` for compatibility with redis-py 6.0+.

**VUL-12 -- Dual Health Checks** (`captain-offline/Dockerfile`, `captain-online/Dockerfile`)

Both the offline and online Dockerfiles originally checked only QuestDB connectivity in their health checks. A container could be marked healthy even when Redis was unavailable, causing runtime failures when the orchestrator attempted to subscribe to Redis channels or publish signals. The fix extended both health checks to validate both QuestDB (via `psycopg2.connect()`) and Redis (via `redis.Redis().ping()`) in a single health check command. If either dependency is unreachable, Docker marks the container as unhealthy, preventing premature startup and ensuring proper orchestration ordering. Health check parameters remained at 30-second intervals, 10-second timeouts, 60-second start periods, and 3 retries.

#### Phase 2: External API Resilience (2 Vulnerabilities)

Phase 2 hardened the TopstepX integration against transient API failures and network instability.

**VUL-10 -- TopstepX REST Retry Logic** (`shared/topstep_client.py`)

The `_do_post()` method originally made a single attempt with a 15-second timeout. Any transient network failure (DNS resolution, TCP reset, timeout) would immediately raise an exception and halt the calling pipeline. The fix added a `tenacity` retry decorator configured for 3 attempts with exponential backoff (1 second minimum, 10 seconds maximum). The decorator retries only on `ConnectionError` and `Timeout` exceptions from the `requests` library, preserving immediate failure for application-level errors (authentication failures, invalid parameters). The `tenacity>=8.0` dependency was added to all three service `requirements.txt` files.

**VUL-05 -- TopstepX Stream Reconnection** (`shared/topstep_stream.py`)

Both `MarketStream` and `UserStream` classes previously surrendered permanently after a rapid sequence of connection failures. The fix implemented a 60-second delayed retry instead of permanent surrender. After detecting a rapid failure cascade (multiple disconnections within a short window), the stream waits 60 seconds before attempting reconnection, allowing transient network issues to resolve. This prevents the stream from permanently losing its market data or user event feed due to a brief network interruption.

#### Phase 3: Redis Streams Migration (1 Vulnerability, 10 Files Modified)

Phase 3 was the most architecturally significant change, migrating the three critical inter-process communication channels from Redis pub/sub to Redis Streams.

**VUL-03 -- Message Delivery Guarantee via Redis Streams**

Redis pub/sub operates as fire-and-forget: if a subscriber is disconnected when a message is published, that message is permanently lost. For a trading system where trade outcomes, commands, and signals are the lifeblood of the feedback loop, message loss could cause the system to silently diverge from reality.

The migration replaced three pub/sub channels with three Redis Streams:

| Old Channel (Pub/Sub) | New Stream | Consumer Group | Purpose |
|----------------------|------------|----------------|---------|
| `captain:signals:{user_id}` | `STREAM_SIGNALS` | `GROUP_COMMAND_SIGNALS` | Signal delivery from Online to Command |
| `captain:trade_outcomes` | `STREAM_TRADE_OUTCOMES` | (consumed by Offline) | Trade outcome feedback to Offline |
| `captain:commands` | `STREAM_COMMANDS` | `GROUP_ONLINE_COMMANDS` | Command routing to Online and Offline |

Redis Streams provide:

- **Message persistence**: Messages are stored in the stream until explicitly trimmed, surviving subscriber disconnections.
- **Consumer groups**: Each consumer group tracks its own read position. Messages are acknowledged (`XACK`) after successful processing, enabling replay of unacknowledged messages after a crash.
- **Delivery guarantee**: A consumer that reconnects after a failure can resume from its last acknowledged position, ensuring no messages are lost.

The migration touched 10 files across the codebase:

1. `shared/redis_client.py` -- Added `publish_to_stream()`, stream name constants, and consumer group initialization functions (`ensure_consumer_group`).
2. Three publisher modules -- Replaced `client.publish()` calls with `publish_to_stream()` using `XADD`.
3. Three subscriber/orchestrator modules -- Replaced `pubsub.subscribe()` and message polling with `XREADGROUP` and `XACK` consumer group operations.
4. Three `main.py` files -- Added `ensure_consumer_group()` calls during startup to create consumer groups before the event loop begins.

Post-migration audit confirmed zero legacy `client.publish()` calls remain in the codebase for the three migrated channels. All services properly use stream-based messaging with consumer group semantics.

#### Phase 4: Polish (3 Vulnerabilities)

Phase 4 addressed user experience and operational refinements.

**VUL-09 -- GUI WebSocket Infinite Reconnect** (`captain-gui/src/ws/useWebSocket.ts`)

The WebSocket client had a fixed `MAX_RECONNECT_ATTEMPTS` limit (30 attempts). During development cycles where the backend is frequently restarted, the frontend would exhaust its reconnection budget and require a manual page reload. The fix set `MAX_RECONNECT_ATTEMPTS = Infinity`, enabling perpetual reconnection attempts. This is particularly important for the local deployment model where the developer frequently rebuilds and restarts backend containers.

**VUL-11 -- Nginx GUI Build Dependency** (`docker-compose.yml`)

The nginx container originally started based on a simple dependency list, without waiting for the captain-gui build to complete. This caused nginx to serve 404 errors for the GUI until the React build finished and copied assets to the shared volume. The initial fix added a healthcheck to captain-gui that tested for `/gui-dist/index.html` existence, with nginx depending on `service_healthy`. This was subsequently corrected to use `service_completed_successfully` because captain-gui is an ephemeral build container that exits after compilation -- Docker healthchecks only function for long-running containers.

**VUL-08 -- TSM Duplicate Prevention** (manual operation)

TSM (Trading State Machine) duplicate records in QuestDB were addressed with duplicate prevention logic in the `_link_tsm_to_account` function. The code checks for existing TSM links before attempting auto-linking operations during initialization. Cleanup of existing duplicates is a manual SQL operation performed through the QuestDB web console at `localhost:9000`, not a code change.

---

### First Live Market Session (March 24, 2026)

The Captain System executed its first complete end-to-end signal generation pipeline on March 24, 2026, during the New York session open at 9:30 AM ET.

#### Pre-Market Preparation

System preparation began at approximately 01:00 AM ET with environment configuration, progressing through several stages:

1. **Environment correction**: TopstepX credentials were corrected in `.env` (email-formatted username, valid API key, M26 contract IDs replacing expired H26 defaults).
2. **Container restarts**: `captain-command` and `captain-online` were selectively restarted to load the corrected configuration. Infrastructure services (nginx, redis, questdb, captain-offline) remained running.
3. **Quality gate cold-start fix**: The B5B quality gate was modified to set a minimum `data_maturity` floor of 0.5 instead of 0.0 for fresh systems with zero trade history, preventing complete signal blockage on day 1.
4. **Container rebuild and deployment**: Captain-online was rebuilt with `docker compose --build` to include the quality gate fix and session_hours configuration updates.

#### Preflight Verification

A comprehensive preflight check at approximately 01:30 AM ET confirmed system readiness:

- **504,802 ACTIVE AIMs** in P3-D01, with 52,748 COLLECTING, 236 INSTALLED, and 60 BOOTSTRAPPED.
- **60 EWMA states** in P3-D05 (10 assets x 2 regimes x 3 sessions).
- **60 Kelly parameters** in P3-D12 with matching regime/session structure.
- **P3-D08 TSM state** linking account 20319811 to `primary_user` with $150,000 balance.
- **P3-D16 user capital silo** configured for `primary_user`.
- **MarketStream** connected to 10 futures contracts (ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN).
- **All 6 containers** running and healthy with zero OOM kills.

#### Stability Verification (T-39 Minutes)

At 8:51 AM ET, 39 minutes before market open, a final stability check confirmed:

- Five containers (captain-command, captain-online, captain-offline, nginx, redis) at `RestartCount=0`.
- QuestDB at `RestartCount=1` (historical, from initial setup), currently stable with 8-hour uptime.
- Zero `OOMKilled` flags across all containers.
- Total memory footprint: 582 MB across all containers (8.8% of 6.65 GB Docker limit).

#### TSM Fix Deployment (T-43 Minutes)

At 8:47 AM ET, the captain-command container was rebuilt and redeployed with a TSM duplicate prevention fix. The modified `_link_tsm_to_account` function checks for existing TSM links before attempting auto-linking, preventing duplicate records that could block the Uvicorn web server startup sequence.

#### Signal Generation (9:30 AM ET)

The NY session 1 evaluation completed successfully, processing 10 futures assets through all 9 pipeline blocks in approximately 21 seconds:

| Block | Action | Result |
|-------|--------|--------|
| ON-B1 | Data ingestion | 220 features computed across 10 assets |
| ON-B2 | Regime probability | Neutral regime fallback for all 10 assets (no trained regime models yet) |
| ON-B3 | AIM aggregation | 10 assets processed, 0 active AIM models contributing |
| ON-B4 | Kelly sizing | Position sizes calculated for `primary_user` across 1 account and 10 assets |
| ON-B5 | Trade selection | 3 of 10 assets selected as viable trading opportunities |
| ON-B5B | Quality gate | All 3 signals passed, 0 rejected below threshold |
| ON-B6 | Signal output | 3 signals published for `primary_user` session 1 |
| ON-B9 | Capacity evaluation | Supply ratio 0.0, quality rate 0%, 3 active constraints |

Three trading signals were generated and published to the database. The system was configured with `AUTO_EXECUTE=true` and `TRADING_ENVIRONMENT=LIVE`, meaning signals routed directly through the TopstepX API adapter for automated order placement on the connected $150,000 practice evaluation account (PRAC-V2-551001-43861321).

---

### VIX Spike Detection and Regime Shift Monitoring

Commit `b33725b` implemented VIX spike detection and regime shift monitoring as part of the B3 pseudotrader pre-deployment preparation. This capability enables the system to detect volatility regime changes in real-time, feeding into the circuit breaker and position sizing pipeline. VIX/VXV data integration was completed as part of the V3 amendments, with raw data stored in `viv_vxv_raw.txt` and processed through the feature engine for regime classification.

---

### Key Decisions

#### Decision: Local-Only Deployment

**Context**: The original architecture specified a two-VPS Hetzner deployment for multi-user IP isolation.
**Decision**: Deploy exclusively on each trader's personal machine (Windows 11 + WSL 2 + Docker Desktop).
**Rationale**: TopstepX ToS Section 28 prohibits VPS usage on accounts, with consequences including account termination and profit forfeiture. This applies to all authenticated API interactions, not just order execution.
**Impact**: Eliminates multi-user IP isolation via VPS. Each trader runs an independent Captain System instance on their personal device. The `docker-compose.local.yml` overlay provides localhost-only HTTP access without TLS (unnecessary for local deployment).

#### Decision: Vulnerability Prioritization (P0 before Phased Plan)

**Context**: 12 vulnerabilities were identified during pre-deployment review.
**Decision**: Fix 3 critical vulnerabilities immediately (P0) before creating the formal phased remediation plan.
**Rationale**: VUL-07 (JVM crashes), VUL-02 (indefinite hangs), and VUL-04 (tight retry loops) posed immediate stability risks that could prevent the system from running long enough to generate signals. These were fixed first to establish a stable baseline for the remaining work.

#### Decision: Redis Pub/Sub to Streams Migration

**Context**: Redis pub/sub is fire-and-forget -- messages published while a subscriber is disconnected are permanently lost.
**Decision**: Migrate all three critical inter-process channels (signals, trade outcomes, commands) to Redis Streams with consumer groups.
**Rationale**: The Captain System's feedback loop (signal -> trade -> outcome -> model update -> next signal) depends on reliable message delivery. A lost trade outcome would cause the Offline process to miss a Kelly update, potentially allowing the Online process to over-size the next position. Redis Streams provide message persistence, consumer group tracking, and acknowledgment-based delivery that eliminates this class of failure.
**Scope**: 10 files modified across all three services plus the shared Redis client module.

#### Decision: Ephemeral GUI Build Container

**Context**: The captain-gui container runs `npm build` and exits. Docker healthchecks require a running process.
**Decision**: Use `restart: "no"` with `service_completed_successfully` dependency condition instead of healthchecks.
**Rationale**: Docker Compose healthchecks only function for long-running containers. An ephemeral build container that exits with code 0 should use `service_completed_successfully` to signal downstream dependencies (nginx) that the build artifacts are ready.

#### Decision: PAPER as Default with Explicit AUTO_EXECUTE Opt-In

**Context**: The system supports both decision-support (manual confirmation) and fully autonomous (auto-execute) modes.
**Decision**: Default to `TRADING_ENVIRONMENT=PAPER` and `AUTO_EXECUTE=false` in the template.
**Rationale**: A fresh installation should never accidentally execute live trades. Both transitions (PAPER to LIVE, manual to auto-execute) require deliberate operator action and container restart.

---

### Current State

As of March 24, 2026:

- **12 of 12 vulnerabilities** resolved across 4 phases (P0 + Phases 1-4).
- **All 6 containers** running and healthy with zero OOM kills and stable memory utilization (582 MB total).
- **First live market session** completed successfully, generating 3 trading signals through the full 9-block pipeline in 21 seconds.
- **Redis Streams migration** complete with zero legacy pub/sub calls remaining for critical channels.
- **Dual health checks** deployed on both captain-offline and captain-online, validating QuestDB and Redis connectivity.
- **Connection pooling** active for QuestDB (ThreadedConnectionPool, min=2, max=10) and Redis (singleton with 5-second timeouts and 30-second health check intervals).
- **TopstepX API resilience** in place with tenacity-based retry logic (3 attempts, exponential backoff) and 60-second delayed stream reconnection.
- **Local deployment** running on Windows 11 with Docker Desktop, fully compliant with TopstepX ToS Section 28.
- **System operational** in 24/7 event loop, evaluating sessions at NY 9:30 AM, LON 3:00 AM, and APAC 8:00 PM ET.

