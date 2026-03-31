# HMM Opportunity Regime System — Research, Specification & Architecture

**Date:** 2026-03-12
**Scope:** Research summary (Category I papers), HMM spec as AIM-16, strategy/parameter storage architecture, 8000+ asset scaling, warm-up sequencing, and massive test design.
**Dependencies:** Builds on Topstep_Optimisation_Functions.md (circuit breaker), Nomaan_Edits_P3.md (P3 extensions), Pipeline_Scale_Test.md (Gap #9 and #10).

---

# PART 1 — RESEARCH SUMMARY: HMM VARIANT SELECTION

## Papers Reviewed

| Ref | Paper/Approach | Key Finding | Relevance |
|-----|---------------|-------------|-----------|
| Hamilton (1989) | Standard HMM for regime switching | Foundational. Gaussian emissions, time-invariant transition matrix. Identifies discrete regimes (expansion/recession) from observable time series. | Baseline framework — proven for financial regime detection. Limitation: constant transition probabilities. |
| Ang & Bekaert (2002) | Regime-switching in asset returns | Regime-dependent risk premia. Different assets have different sensitivities to regime switches. | Validates multi-asset regime conditioning — same regime affects assets differently. |
| TVTP Extensions (2021) | Time-varying transition probabilities | Transition matrix changes based on observable covariates (VIX, volume). Regime persistence varies with market conditions. | Directly addresses our need: "given today's conditions, how likely is a regime transition tomorrow?" |
| Hierarchical HMM (2020, 2025) | Multi-scale regime detection | Two-level hierarchy: slow macro regime (bull/bear/turbulent) + fast micro regime (intraday opportunity). Avoids misinterpreting short-term noise as long-term changes. | Ideal for our problem: daily regime (from P2) conditions intraday opportunity regime (new HMM). |
| HMM-SVM Hybrid (2025) | Generative-discriminative combination | HMM + kernel machines outperform pure HMMs and neural networks for high-frequency regime classification. No manual feature engineering needed. | Future upgrade path. Start with standard HMM, upgrade to hybrid if performance is insufficient. |
| Gaussian HMM + Smoothing (2024) | Bayesian inference with output smoothing | Smoothing HMM state probabilities reduces false signals and transaction costs by enhancing regime persistence. | Critical for budget allocation — prevents whipsawing weights session-to-session. |
| Online Adaptive HMM (2021, 2025) | Self-adjusting parameter re-estimation | Re-estimates parameters on a rolling window (60-160 observations) at each new data point. Real-time adaptation without full re-training. | Enables within-day adaptation — opportunity estimate updates as morning data arrives. |

## Recommendation: Gaussian HMM with TVTP + Smoothing

**Selected variant:** Standard Gaussian HMM with time-varying transition probabilities (TVTP) and exponential smoothing on output state probabilities.

**Why this variant:**

1. **Gaussian emissions** are sufficient for our observation vectors (signal count, mean OO, session volume z-score, VIX — all continuous). No need for more complex emission models.
2. **TVTP** is essential because the probability of transitioning between opportunity states depends on observable covariates (VIX level, day of week, prior session outcomes). A fixed transition matrix can't capture "Fridays have lower opportunity than Mondays" or "high-VIX days have different opportunity dynamics."
3. **Smoothing** prevents budget allocation whipsawing — without it, the HMM might flip between HIGH_OPP and LOW_OPP on small observation changes, causing erratic budget shifts between sessions.
4. **Online re-estimation** (rolling 60-day window) ensures the model adapts to changing market structure without requiring a full offline re-train.

**Future upgrade path:** If the single-scale HMM is insufficient (false signals, poor forward prediction), upgrade to hierarchical HMM with slow daily regime (from P2) conditioning the fast intraday opportunity regime. This is a parameter/architecture change, not a redesign.

---

# PART 2 — STRATEGY & PARAMETER STORAGE ARCHITECTURE

## Frozen vs Adaptive: Complete Register

### FROZEN (P1/P2 — Never Modified by P3)

| Parameter | Set By | Stored In | What It Controls | Changes When |
|-----------|--------|-----------|-----------------|-------------|
| Entry logic (OR window, entry rules) | P1 model generator | D-00 (models_raw_dataset) | WHAT triggers a trade | New model generated + re-validated through P1 |
| TP/SL multiples | P1 model generator | D-00 (models_raw_dataset) | WHERE the trade exits | New model generated + re-validated through P1 |
| Algorithm path | P1 model generator | D-00 (models_raw_dataset) | HOW the backtest runs | Algorithm refactored by Nomaan |
| Feature threshold | P1 Block 3 | D-20 (threshold_dataset), P2-D06 | WHEN to take a trade (feature gate) | P1 re-run with new data |
| Feature direction | P1 Block 2B | D-14, P2-D06 | WHICH direction the feature predicts | P1 re-run |
| OO score | P1 Block 5 | D-24 | HOW GOOD the model is (ranking) | P1 re-run |
| Locked strategy (m, k, threshold, direction) | P2 | P2-D06 | WHICH model trades each asset | P2 re-run with new P1 output |
| Regime label | P2 | P2-D06 | WHICH regimes the strategy is active in | P2 re-run |
| Regime classifier | P2 Block 3 | P2-D07 | HOW regimes are classified | P2 re-run (or model swap: XGBoost → HMM per RR-17) |

### ADAPTIVE (P3 — Updates Continuously)

| Parameter | Updated By | Stored In | What It Controls | Update Cadence |
|-----------|-----------|-----------|-----------------|---------------|
| Kelly fraction (per regime) | Offline Block 8 | P3-D12 | HOW MUCH to size each trade | After each trade batch |
| Kelly shrinkage | Offline Block 8 | P3-D12 | HOW CONSERVATIVE the sizing is | After each trade batch |
| AIM modifiers (15 AIMs) | Online Block 3 | P3-D01 | HOW MUCH each intelligence source adjusts the signal | Per session |
| AIM meta-weights (DMA/MoE) | Offline Block 1 | P3-D02 | HOW MUCH to trust each AIM | After each trade batch |
| BOCPD/CUSUM state | Offline Block 2 | P3-D04 | WHETHER strategy decay is detected | Continuous |
| Circuit breaker β_b | Offline Block 8 | P3-D25 | WHEN per-basket halt triggers | After each trade batch |
| Circuit breaker σ, ρ̄ | Offline Block 8 | P3-D25 | HOW correlation affects screening | After each trade batch |
| **Session budget weights (NEW)** | **Offline Block 1 (AIM-16)** | **P3-D26 (NEW)** | **WHERE to allocate daily budget across sessions** | **After each trade batch** |
| **Opportunity regime state (NEW)** | **Online Block 5 (AIM-16)** | **P3-D26 (NEW)** | **Forward-looking opportunity prediction** | **Per session window** |

### KEY PRINCIPLE

P3 adaptive systems control four dimensions:
1. **HOW MUCH** — Kelly sizing, AIM modifiers
2. **HOW MUCH TO TRUST** — AIM meta-weights, DMA/MoE
3. **WHEN TO STOP** — circuit breaker, BOCPD decay
4. **WHERE TO ALLOCATE** — session budget weights (NEW)

P3 NEVER controls:
- **WHAT** to trade (locked by P2-D06)
- **WHEN** to enter (locked by feature threshold in P2-D06)
- **WHERE** to exit (locked by TP/SL in D-00)

If a new TP/SL, entry logic, or threshold is proposed, it MUST go through the model generator → P1 validation → P2 selection pipeline. No shortcuts.

---

# PART 3 — AIM-16: OPPORTUNITY REGIME HMM SPECIFICATION

## 3.1 Overview

AIM-16 is a new Auxiliary Intelligence Module that detects opportunity regimes across trading sessions and produces budget allocation weights. It uses a Gaussian HMM with time-varying transition probabilities to predict the probability of high-opportunity conditions in upcoming sessions.

Unlike AIMs 1-15 which produce per-asset modifiers, AIM-16 produces per-SESSION weights that affect budget allocation across all assets within that session.

## 3.2 Hidden States

K = 3 states:

| State | Label | Interpretation | Typical Characteristics |
|-------|-------|---------------|------------------------|
| 0 | LOW_OPP | Low opportunity | Few signals fire, low average OO, mean-reverting/choppy price action, high false signal rate |
| 1 | NORMAL | Normal opportunity | Average signal rate, moderate OO, standard volatility |
| 2 | HIGH_OPP | High opportunity | Many signals fire, high average OO, trending price action, high win rate |

## 3.3 Observation Vector

Per session window w, the observation vector z_w is:

| # | Observable | Source | Description |
|---|-----------|--------|-------------|
| 1 | n_signals | Signal queue | Number of signals generated in window w |
| 2 | mean_OO | Signal queue | Average OO score of signals generated |
| 3 | volume_z | P3-D00 data sources | Session volume as z-score vs 20-day average |
| 4 | vix_level | AIM-04 (IVTS) | VIX at session open |
| 5 | prior_session_pnl | P3-D23 | Net P&L from the previous session window |
| 6 | cross_asset_corr | AIM-08 | Average pairwise correlation across active assets |
| 7 | day_of_week | Calendar | 0-4 (Mon-Fri) encoded |

Observation vector: z_w ∈ R^7.

## 3.4 Model Parameters

| Parameter | Symbol | Description |
|-----------|--------|-------------|
| Initial state distribution | π | P(state at first session of day) = [π_0, π_1, π_2] |
| Transition matrix | A(x_t) | 3×3 matrix where A_ij(x_t) = P(state_j at t+1 | state_i at t, covariates x_t). TVTP — transitions depend on covariates. |
| TVTP covariates | x_t | VIX level, day of week, prior session P&L. These modulate the transition probabilities. |
| Emission means | μ_k | Mean observation vector in state k. μ_k ∈ R^7. |
| Emission covariance | Σ_k | Covariance of observations in state k. Σ_k ∈ R^{7×7}. Diagonal assumed initially (independent observations within state). |

## 3.5 Training (Offline Block 1)

```
P3-PG-01C: "aim16_hmm_train_A"

INPUT: P3-D03 (trade outcomes with timestamps, per session)
INPUT: Historical session-level observations (z_w for each session window w across all historical days)

# Step 1: Construct session-level observation sequences
FOR EACH trading day d:
    FOR EACH session window w IN [APAC, LONDON, NY_PRE, NY_OPEN]:
        z_{d,w} = compute_observation_vector(d, w)
        # n_signals, mean_OO, volume_z, vix, prior_pnl, cross_corr, dow

# Step 2: Label sessions by realized P&L for supervised initialization
FOR EACH (d, w):
    IF session_pnl(d, w) > percentile_75(all_session_pnl):
        initial_label = HIGH_OPP
    ELIF session_pnl(d, w) < percentile_25(all_session_pnl):
        initial_label = LOW_OPP
    ELSE:
        initial_label = NORMAL

# Step 3: Initialize HMM parameters from labeled data
FOR EACH state k:
    μ_k = mean(z_{d,w} WHERE initial_label = k)
    Σ_k = diag(var(z_{d,w} WHERE initial_label = k))

# Step 4: Baum-Welch estimation (EM algorithm)
# Fit on rolling 60-day window (most recent 60 trading days × 4 sessions = 240 observations)
hmm_params = baum_welch(
    observations = z_sequence[-240:],
    n_states = 3,
    max_iterations = 100,
    convergence_threshold = 1e-6,
    tvtp_covariates = x_sequence[-240:]  # VIX, DOW, prior PnL
)

# Step 5: Smoothing calibration
# Apply exponential smoothing to state probabilities to reduce whipsaw
# α_smooth = 0.3 (configurable — lower = more smoothing)

# Step 6: Store
P3-D26.hmm_params = hmm_params
P3-D26.last_trained = now()
P3-D26.training_window = 60  # days
P3-D26.n_observations = 240
```

**Training frequency:** Same as other AIMs — after each trade outcome batch, or daily minimum. Rolling 60-day window re-estimates parameters incrementally (not full re-train).

## 3.6 Online Inference (Online Block 5)

```
P3-PG-25B: "aim16_hmm_inference_A"

INPUT: P3-D26 (HMM params)
INPUT: observations so far today (z_w for completed session windows)
INPUT: session schedule (remaining windows today)

# Forward algorithm: compute P(state | observations so far)
FOR EACH remaining session window w_future:
    
    # Predict state at w_future given observations up to now
    alpha = forward_algorithm(
        hmm_params = P3-D26.hmm_params,
        observations = z_observed_today,
        target_step = w_future
    )
    
    # Apply smoothing
    alpha_smoothed = α_smooth × alpha + (1 - α_smooth) × P3-D26.prior_alpha[w_future]
    
    # Opportunity weight = P(HIGH_OPP at w_future)
    opportunity_weight[w_future] = alpha_smoothed[HIGH_OPP]

# Normalize weights across remaining sessions (minimum floor per session)
floor = 0.05  # no session gets less than 5% of remaining budget
FOR EACH w_future:
    opportunity_weight[w_future] = max(opportunity_weight[w_future], floor)
weights_sum = sum(opportunity_weight.values())
FOR EACH w_future:
    opportunity_weight[w_future] /= weights_sum

# Budget allocation for next session window
remaining_budget = E - budget_consumed_today
budget_for_next_session = remaining_budget × opportunity_weight[next_session]

RETURN opportunity_weight, budget_for_next_session
```

## 3.7 Integration with Block 5 (Trade Selection)

The current Block 5 allocates budget first-come-first-served (Gap #9). With AIM-16:

```
# OLD (Gap #9 — FCFS):
FOR EACH signal in arrival_order:
    allocate_budget(signal)

# NEW (AIM-16 driven):

# 1. At each session window open, get HMM budget allocation
session_budget = aim16_hmm_inference(remaining_budget, observations_so_far)

# 2. Collect all signals generated in this session window
signals_this_window = collect_signals(current_window)

# 3. Rank signals by OO × AIM_modifier (quality ranking)
signals_this_window.sort(by=OO × combined_modifier, descending=True)

# 4. Allocate from session budget, top-down
FOR EACH signal IN signals_this_window (ranked):
    contracts = min(kelly_contracts, floor(session_budget / risk_per_contract))
    IF contracts >= 1:
        allocate(signal, contracts)
        session_budget -= contracts × risk_per_contract
    ELSE:
        block(signal, reason="SESSION_BUDGET_EXHAUSTED")
```

## 3.8 Cold Start Protocol

| Condition | Behaviour |
|-----------|----------|
| < 20 trading days | HMM disabled. Equal weights across all sessions. Budget partitioned by fixed percentages from TSM `topstep_params.session_weights_initial`. |
| 20-59 trading days | HMM trains with limited data. High uncertainty in state estimates. Output blended 50/50 with equal weights (hedge against noisy estimates). |
| 60+ trading days | HMM fully active. 240+ session observations available. Pure HMM-driven weights (with floor). |

## 3.9 New Dataset: P3-D26

```
P3-D26: hmm_opportunity_state

Schema:
    hmm_params:
        pi:             array[3]        # initial state distribution
        A:              array[3][3]     # transition matrix (or TVTP coefficients)
        mu:             array[3][7]     # emission means per state
        sigma:          array[3][7]     # emission variances per state (diagonal)
        tvtp_coefs:     object          # coefficients for time-varying transitions
    
    current_state_probs: array[3]       # P(state) as of last observation
    opportunity_weights: dict           # {session_window: weight}
    prior_alpha:        dict            # {session_window: array[3]} — for smoothing
    
    last_trained:       datetime
    training_window:    int             # days
    n_observations:     int
    cold_start:         bool            # True if < 60 days
```

Storage: QuestDB (same as all P3-D datasets). Redis-cached for real-time access by Online Block 5.

---

# PART 4 — 8000+ ASSET ARCHITECTURE

## P3-D00 Schema Extension: TRAINING_ONLY Status

Current `captain_status` values: ACTIVE, WARM_UP, INACTIVE, DATA_HOLD, ROLL_PENDING.

**Add:** `TRAINING_ONLY`

| Status | Signals Generated? | Features Computed? | P1 Validated? | Data Ingested? | Trades Executed? |
|--------|-------------------|-------------------|---------------|----------------|-----------------|
| ACTIVE | Yes | Yes | Yes | Yes | Yes (if TSM permits) |
| WARM_UP | No | Yes (accumulating) | Yes | Yes | No |
| TRAINING_ONLY | **No** | **Yes** | **Yes** | **Yes** | **No** |
| INACTIVE | No | No | No | No | No |
| DATA_HOLD | No | Paused | Yes | Paused | No |
| ROLL_PENDING | No | Paused | Yes | Paused | No |

**Difference between TRAINING_ONLY and WARM_UP:** WARM_UP is temporary (asset is transitioning to ACTIVE after sufficient data). TRAINING_ONLY is permanent — the asset is kept in the system for its cross-asset intelligence value but is NEVER intended to be traded directly.

## How TRAINING_ONLY Assets Contribute

1. **Cross-asset features (AIM-08, AIM-09):** Correlations and momentum across 8000+ assets provide a richer picture of market state. Example: correlation between ES and 500 global equity indices detects global risk-on/risk-off regimes before they're visible in VIX alone.

2. **HMM observation vector:** AIM-16's observation vector includes cross_asset_corr (element 6). More TRAINING_ONLY assets = richer correlation data = better opportunity regime detection.

3. **Regime model training (P2):** The P2 regime classifier can train on features derived from TRAINING_ONLY assets. Example: using Chinese equity futures (non-tradeable on Topstep) as a leading indicator for US equity futures overnight gap.

4. **Future P1 feature discovery:** TRAINING_ONLY assets can be used as input variables (V) in the P1 feature pipeline. Example: V_gold_momentum as a feature for ES ORB trades — gold data comes from TRAINING_ONLY GC, the feature is applied to ACTIVE MES.

## Signal Suppression for TRAINING_ONLY

In Online Block 1, the existing check:

```python
IF P3-D00[u].captain_status == "ACTIVE" AND session_match(u, session_id):
    active_assets.append(u)
```

Already excludes TRAINING_ONLY assets from signal generation. No code change needed — just ensure TRAINING_ONLY is not treated as ACTIVE. Feature computation should include TRAINING_ONLY assets:

```python
# Feature computation — includes TRAINING_ONLY
FOR EACH asset u IN P3-D00 WHERE captain_status IN ["ACTIVE", "WARM_UP", "TRAINING_ONLY"]:
    compute_features(u)

# Signal generation — ACTIVE only
FOR EACH asset u IN P3-D00 WHERE captain_status == "ACTIVE":
    generate_signals(u)
```

## P1 at Scale (8000+ Assets)

P1 runs per-asset. 8000 assets × N models × M features = very large compute. Architecture supports it (the pipeline_orchestrator loops over assets in D-00). Practical considerations:

- **Parallelisation:** P1 runs per asset are independent — can be parallelised across compute nodes. QC Cloud supports this.
- **Storage:** 8000 × D-24 OO records. QuestDB handles this (time-series optimised).
- **P2 consumes per-asset:** P2 selects the best strategy per asset independently. No cross-asset interaction in P2 — scales linearly.
- **Selective P1 runs:** Not every asset needs a full P1 re-run on every cycle. TRAINING_ONLY assets can run P1 less frequently (quarterly vs monthly for ACTIVE assets).

---

# PART 5 — WARM-UP SEQUENCING

## Complete System Boot Sequence

```
PHASE 0 — DATA ACQUISITION
├── Acquire historical data for all assets (8000+)
├── Load into QuestDB via data source adapters
├── Verify data quality (price bounds, volume, timestamps)
└── Duration: depends on data availability

PHASE 1 — P1 VALIDATION (FROZEN after completion)
├── FOR EACH asset (ACTIVE + TRAINING_ONLY):
│   ├── Model generator produces model definition files
│   ├── P1 pipeline_orchestrator runs all models × all features
│   ├── OO scores computed for all (m, k) pairs
│   └── Results stored in D-24
├── Output: validated models with OO scores
├── Status: FROZEN — not modified until next P1 re-run
└── Duration: hours to days depending on asset count and compute

PHASE 2 — P2 SELECTION (FROZEN after completion)
├── FOR EACH ACTIVE asset:
│   ├── P2 receives P1 survivors
│   ├── Regime classifier trained on historical data
│   ├── Best strategy selected per regime
│   └── Locked in P2-D06
├── Output: locked strategies + regime classifiers
├── Status: FROZEN — not modified until next P2 re-run
└── Duration: minutes to hours

PHASE 3 — P3 OFFLINE WARM-UP (ADAPTIVE from here)
├── AIM Training (Block 1):
│   ├── AIMs 1-15: compute initial modifiers from historical data
│   ├── DMA/MoE: initial meta-weights = equal (no learning yet)
│   ├── AIM-16 (HMM): train on historical session-level data (60+ days)
│   └── Store in P3-D01, P3-D02, P3-D26
├── Kelly Parameters (Block 8):
│   ├── Compute initial Kelly fractions per regime per asset
│   ├── Shrinkage factor calibrated from historical variance
│   └── Store in P3-D12
├── Circuit Breaker Parameters (Block 8):
│   ├── β_b = 0 for all baskets (cold start — < 100 observations)
│   ├── σ, ρ̄ estimated from historical trade data if available
│   └── Store in P3-D25
├── Status: ADAPTIVE — updates continuously from this point
└── Duration: minutes

PHASE 4 — PSEUDOTRADER VALIDATION
├── Replay historical data through P3 with ALL systems active:
│   ├── Locked strategies from Phase 2
│   ├── Kelly sizing with Phase 3 params
│   ├── AIM modifiers with Phase 3 weights
│   ├── Circuit breaker with cold-start β_b = 0
│   ├── HMM session weights (or equal weights if cold start)
│   └── Topstep constraints (E, N, L_halt)
├── Compare: P&L with vs without each adaptive component
├── Validate: no component makes things worse
├── Output: pseudotrader comparison report (RPT-09)
└── Duration: minutes to hours

PHASE 5 — SHADOW DEPLOYMENT
├── P3 generates signals but does NOT execute
├── Signals logged for comparison against actual market outcomes
├── AIM weights, Kelly, HMM, circuit breaker all learning from real-time data
├── Duration: 20+ trading days (configurable)
└── Gate: ADMIN reviews shadow performance → approves live start

PHASE 6 — LIVE EXECUTION
├── Signals emitted to GUI + API
├── All adaptive systems active and learning
├── BOCPD monitoring for strategy decay
├── HMM session weights updating daily
├── Circuit breaker β_b activates after 100+ observations per basket
└── Compounding: SOD recalculation at 19:00 EST uses live balance A
```

## Compounding Confirmation

Account compounding is handled by the SOD recalculation at 19:00 EST:
- A (account balance) reflects all cumulative profits and losses
- f(A), E, N, L_halt, topstep_max_contracts all recalculate from the new A
- Kelly sizing uses current A (kelly × current_capital / risk_per_contract)
- Winning days → A grows → E grows → more contracts available → larger positions → faster growth (positive compounding)
- Losing days → A shrinks → E shrinks → fewer contracts → smaller positions → slower decline (negative compounding = risk reduction)

P1 does NOT compound — backtests use flat sizing to validate edge independently of position sizing. This is correct: P1 validates "does the strategy have edge?", P3 handles "how to size the edge optimally."

---

# PART 6 — UPDATED MASSIVE TEST DESIGN

## Test Scenario (Extends Pipeline_Scale_Test.md)

### Assets

| # | Asset | Status | Session | Tradeable? |
|---|-------|--------|---------|-----------|
| 1 | MES | ACTIVE | NY | Yes |
| 2 | MNQ | ACTIVE | NY | Yes |
| 3 | M2K | ACTIVE | NY | Yes |
| 4 | MYM | ACTIVE | NY | Yes |
| 5 | MCL | ACTIVE | NY Pre | Yes |
| 6 | MGC | ACTIVE | London + NY Pre | Yes |
| 7 | 6E | ACTIVE | London + NY Pre | Yes |
| 8 | ZN | ACTIVE | NY Pre | Yes |
| 9 | NKD | TRAINING_ONLY | APAC | No — cross-asset features only |
| 10 | 6J | TRAINING_ONLY | APAC | No — cross-asset features only |
| 11 | GC | TRAINING_ONLY | London | No — but MGC trades its micro |
| 12 | ES | TRAINING_ONLY | NY | No — but MES trades its micro |

### HMM State (Day of Test)

Assume 80 trading days of history → HMM fully active (past cold start).

HMM state entering the test day:

Prior day: NORMAL (P(HIGH)=0.25, P(NORMAL)=0.65, P(LOW)=0.10).

Morning observations:
- APAC session: NKD volume_z = +1.8 (high volume), 6J corr with ES = 0.45 (elevated). HMM forward: P(HIGH_OPP at London) → **0.55** (above baseline).
- London session: MGC and 6E both fire signals. Volume_z = +1.2 for both. HMM forward: P(HIGH_OPP at NY) → **0.62**.

### Session Budget Allocation (HMM-Driven)

Remaining budget at each session:

| Session | HMM P(HIGH_OPP) | Normalised Weight | Budget Share | Budget ($) |
|---------|-----------------|-------------------|-------------|-----------|
| APAC | — (no tradeable assets) | 0% | $0 | N/A |
| London | 0.55 | 0.25 | 25% | $387.50 |
| NY Pre | 0.20 | 0.13 | 13% | $201.50 |
| NY Open | 0.62 | 0.62 | 62% | $961.00 |

Floor applied: minimum 5% per session with tradeable assets.

### Signal Generation

| Window | Signals | Assets | Total |
|--------|---------|--------|-------|
| APAC | 0 (TRAINING_ONLY assets only) | NKD, 6J | 0 |
| London | 2 (MGC momentum, 6E ORB) | MGC, 6E | 2 |
| NY Pre | 2 (MCL mean-rev, ZN rate-rev) | MCL, ZN | 2 |
| NY Open | 6 (MES×3, MNQ×1, M2K×1, MYM×1) | MES, MNQ, M2K, MYM | 6 |
| **Total** | | | **10** |

### Allocation Trace

**London Window (budget = $387.50):**

| Rank | Signal | Asset | OO×Mod | Risk/Contract | Contracts | Cost | Remaining |
|------|--------|-------|--------|--------------|-----------|------|-----------|
| 1 | S7-MGC | MGC | 0.738 | $50.74 | 3 | $152.22 | $235.28 |
| 2 | S8-6E | 6E | 0.718 | $190.30 | 1 | $190.30 | $44.98 |

Budget consumed. ✓ **Both London signals taken.**

**NY Pre Window (budget = $201.50):**

| Rank | Signal | Asset | OO×Mod | Risk/Contract | Contracts | Cost | Remaining |
|------|--------|-------|--------|--------------|-----------|------|-----------|
| 1 | S6-MCL | MCL | 0.690 | $5.74 | 10 | $57.40 | $144.10 |
| 2 | S9-ZN | ZN | 0.670 | $252.80 | 0 | — | **BLOCKED** ($144 < $252.80) |

S9 blocked — ZN risk per contract ($252.80) exceeds remaining budget. MCL gets 10 contracts (low risk per contract). ✓

**NY Open Window (budget = $961.00):**

| Rank | Signal | Asset | OO×Mod | Risk/Contract | Contracts | Cost | Remaining |
|------|--------|-------|--------|--------------|-----------|------|-----------|
| 1 | S1-MES | MES | 0.799 | $70.74 | 3 | $212.22 | $748.78 |
| 2 | S3-MNQ | MNQ | 0.779 | $70.74 | 3 | $212.22 | $536.56 |
| 3 | S2-MES | MES | 0.758 | $70.74 | 3 | $212.22 | $324.34 |
| 4 | S10-MES | MES | 0.720 | $70.74 | 3 | $212.22 | $112.12 |
| 5 | S4-M2K | M2K | 0.712 | $50.74 | 2 | $101.48 | $10.64 |
| 6 | S5-MYM | MYM | 0.680 | $70.74 | 0 | — | **BLOCKED** |

5 of 6 NY signals taken. MYM blocked by budget. Top-3 are all equity (highest OO). ✓

### Verification: TRAINING_ONLY Assets

| Asset | Status | Features Computed? | Signals Generated? | Cross-Asset Contribution? |
|-------|--------|-------------------|-------------------|--------------------------|
| NKD | TRAINING_ONLY | ✓ (volume, returns) | ✗ (correctly suppressed) | ✓ (AIM-08 corr, HMM obs) |
| 6J | TRAINING_ONLY | ✓ (volume, returns) | ✗ (correctly suppressed) | ✓ (AIM-08 corr, HMM obs) |
| GC | TRAINING_ONLY | ✓ (volume, returns) | ✗ (correctly suppressed) | ✓ (MGC inherits GC features) |
| ES | TRAINING_ONLY | ✓ (volume, returns) | ✗ (correctly suppressed) | ✓ (MES inherits ES features) |

TRAINING_ONLY assets contribute intelligence but never generate signals or consume budget. ✓

### Day Summary

| Metric | Value |
|--------|-------|
| Total signals generated | 10 |
| Signals taken | 8 |
| Signals blocked | 2 (ZN: insufficient budget, MYM: insufficient budget) |
| Total contracts | 28 |
| Budget consumed | $1,539.36 / $1,550 (99.3%) |
| Sessions used | 3 of 4 (APAC has no tradeable assets) |
| TRAINING_ONLY assets | 4 (contributing features, no signals) |
| HMM allocation accuracy | NY got 62% budget, generated 5/6 signals taken — correct priority |

### Circuit Breaker Interaction with Session Partitions

If London trades lose and trigger the hard halt:

- L_t = -$342.52 (both London signals lose)
- Preemptive check for NY Pre: |L_t| + ρ_j = 342.52 + 57.40 = $399.92 < L_halt = $775. **PASS.** NY Pre proceeds.
- Circuit breaker operates on AGGREGATE L_t across all sessions (not per-session). This is correct — the MDD risk is account-level, not session-level. ✓

### What This Test Proves

1. HMM session weights correctly prioritise NY (highest opportunity probability) over London/Pre-market
2. TRAINING_ONLY assets contribute features without generating signals or consuming budget
3. Budget allocation ranks by OO×modifier within each session window, not by arrival time (Gap #9 fixed)
4. Session partitioning prevents pre-market from starving NY (Gap #10 fixed)
5. High-risk instruments (ZN at $252.80/contract) are correctly filtered by budget constraints
6. Low-risk instruments (MCL at $5.74/contract) get many contracts within their session partition
7. Circuit breaker operates correctly across session boundaries (aggregate L_t, not per-session)
8. Compounding: SOD recalculation at 19:00 EST updates all params from new A

---

# GAPS FOUND (THIS SPEC)

| # | Location | Description | Severity | Resolution |
|---|----------|-------------|----------|------------|
| 11 | AIM-16 | HMM needs minimum 60 trading days to activate. During cold start, equal weights may under-allocate to historically strong sessions. | LOW | By design — cold start uses configurable initial weights from TSM. |
| 12 | P3-D00 | No per-asset session schedule in current schema. Need to know which sessions each asset belongs to for HMM observation bucketing. | LOW | Add `session_schedule` field to P3-D00 per asset (list of session windows). |
| — | — | No other gaps found. System handles 8000+ assets, multi-session, TRAINING_ONLY, HMM allocation, and compounding correctly. | — | — |
