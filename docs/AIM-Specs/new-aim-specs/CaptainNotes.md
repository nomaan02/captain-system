> **SUPERSEDED** — Pre-specification design notes only. For authoritative specs, see: `Program3_Architecture.md`, `Program3_Offline.md`, `Program3_Online.md`, `Program3_Command.md`.

# Captain System (Program 3) — Pre-Specification Design Notes (ARCHIVED)

**Created:** 2026-03-01
**Status:** SUPERSEDED — all formal specifications now complete
**Purpose:** Comprehensive context for building `Program3.md` to the same standard as `Program1.md` and `Program2.md`
**Companion documents:** `GUI_Notes.md`, `AIMRegistry.md`, `AIM_Research_Notes.md`

---

# PART A — CAPTAIN ARCHITECTURE

## A1. Three Components

| Component | Role | Execution |
|-----------|------|-----------|
| **Captain (Offline)** | Strategic brain. Handles pipeline re-runs, strategy decay detection, AIM model training, regime model retraining, TSM simulation, parameter optimisation. Where the system "learns" and recalibrates. | Periodic (scheduled + event-triggered) |
| **Captain (Online)** | Continuous 24/7 signal engine. Evaluates at each major session open (NY 9:30 ET, London 8:00 GMT, APAC sessions). Computes regime probabilities, regime-adjusted expected edge, blended Kelly sizing with parameter shrinkage, applies AIM modifiers via DMA/MoE, applies TSM constraint envelope. Monitors open positions intraday. Outputs trading decisions per asset per session. Strategy-agnostic: processes ANY strategy type from Program 1 (ORB now, swing/multi-day later). | Continuous (session-triggered + intraday monitoring) |
| **Captain (Command)** | Linking and interface layer. Connects Offline and Online. Exposes GUI. Manages TSM selection, parameter translation, trade alerts, strategy injection flow, and all human-in-the-loop interactions. Single point of contact for the GUI — Online and Offline never receive instructions directly from the interface. | Always running |

## A2. Information Flow

```
Captain (Offline)
    │
    ├── Trains AIM models (continuous)
    ├── Runs BOCPD + distribution-free CUSUM decay detection
    ├── Triggers Programs 1/2 re-runs (Level 3)
    ├── Runs TSM pass probability simulation
    ├── Performs walk-forward parameter optimisation
    ├── Runs AIM-13 sensitivity scans (monthly)
    ├── Runs AIM-14 auto-expansion (on Level 3 trigger)
    │
    └──► Writes to: persistent knowledge store
              │
              ▼
Captain (Online)
    │
    ├── Reads: persistent knowledge store
    ├── Reads: AIM model states
    ├── Reads: locked strategy from P2-D06
    ├── Reads: regime prediction model from P2-D07
    ├── Computes: P(regime | features_t) via P2-D07
    ├── Computes: E[R | regime] via EWMA of historical conditional returns
    ├── Computes: blended Kelly × shrinkage × AIM_aggregate (DMA/MoE)
    ├── Applies: robust Kelly fallback during high uncertainty
    ├── Applies: TSM constraint envelope via Thompson Sampling (CBwK/CCB)
    ├── Monitors: open positions intraday (TP/SL levels, condition changes)
    │
    └──► Outputs: per-session signal per asset + intraday alerts
              │
              ▼
Captain (Command)
    │
    ├── Routes: signals to GUI (Layer 1 display)
    ├── Routes: user decisions from GUI (Layer 2) → Online/Offline
    ├── Manages: TSM file loading, switching, translation
    ├── Manages: strategy injection comparison protocol
    ├── Manages: AIM activation/deactivation
    ├── Generates: discretionary reports RPT-01 to RPT-10
    │
    └──► GUI (bidirectional)
```

## A3. Captain as a Persistent Learning System

The Captain is NOT a run-once pipeline. It is a **persistent, stateful learning system** that improves continuously.

### Two Modes of Information Intake

**Mode 1 — Continuous (every day, no human involvement):**
Every morning, Captain (Online) processes new data. Every AIM updates its model. EWMA of expected returns shifts. Cost estimator refines slippage estimates. Regime model ingests yesterday's features. Correlation monitor updates. Trade outcomes feed decay detectors. No re-run of Programs 1/2 needed.

**Mode 2 — Discrete injection (only when the team decides):**
Team runs a new idea through Programs 1 and 2 offline. Output (OO scores, regime correlations, locked strategy candidate) arrives at the Captain as an **injection event**. The Captain does NOT blindly adopt the injection — it runs a comparison protocol (see Part D).

### Persistent Knowledge Store

The Captain retains and grows:
- All historical AIM model states and meta-weights
- All historical trade outcomes with AIM-contextualised metadata
- All previous strategy injection events (comparison results, decisions, reasons)
- EWMA states, SPRT/CUSUM states, correlation model states
- Strategy performance history by asset, regime, and calendar context
- AIM effectiveness scores over time

---

# PART B — TIERED AUTONOMY

| Level | Trigger | Autonomy | Human Gate |
|-------|---------|----------|------------|
| **Level 1** | Scheduled retrain cycle | Fully autonomous | None — silent |
| **Level 2** | SPRT/CUSUM decay flag | Autonomous sizing reduction + GUI alert | User acknowledges, no approval needed |
| **Level 3** | Sustained decay → re-evaluation | Autonomous Programs 1/2 re-run trigger | Re-run automatic; strategy ADOPTION is human-gated |

### Level 3 Flow (Manual Execution Mode)

1. Decay detected → Captain (Offline) autonomously triggers Programs 1/2 re-run
2. Signal generation HALTED for affected asset during re-run
3. GUI shows "STRATEGY REVIEW IN PROGRESS — no signals for [asset]"
4. Re-run completes → Captain (Command) auto-generates RPT-05 Injection Comparison
5. User approves or rejects via GUI → signals resume with new or retained strategy
6. If adopted: transition phasing over ~10 trading days

### Rationale

Manual execution means the worst case of full autonomy (bad strategy adopted and immediately traded) cannot occur. The user sees every signal before acting. Therefore Level 3 only gates strategy ADOPTION, not the investigation.

---

# PART C — TRADING SYSTEM MODEL (TSM) LAYER

## C1. What TSMs Are

Pluggable configuration files defining platform-specific rules:
- **Prop firm TSM:** Capital rules, MDL, MDD, evaluation targets, contract size constraints, evaluation stages, scaling plans, time limits. Objective = maximise pass probability
- **Direct broker TSM:** Commission schedule, margin requirements, overnight rules. Objective = maximise risk-adjusted return

## C2. TSM Architecture

- TSM files stored in designated folder
- Captain (Command) loads and manages TSM files, live-updates when files change
- TSM selection via GUI triggers Captain (Command) → translates constraints → Captain (Online) applies envelope
- Switching TSMs triggers Captain (Offline) to re-simulate pass probability under new rules

## C3. Strategy Parameter Translation

Original model parameters (from D-09, D-20) are NEVER modified. The translation layer applies TSM-specific adjustments at execution time:
- If 0.35 × OR × contracts > TSM MDL limit → reduce contracts (not SL)
- If minimum 1 contract × 0.35 × OR > MDL limit → suppress trade for the day
- Translation logged in RPT-01 Daily Signal Report

## C4. TSM-Specific Captain (Online) Behaviour

**Prop firm mode:** Daily risk budget = (remaining MDL − current drawdown) / estimated remaining trading days. Sizes to protect pass probability, not just maximise returns.

**Direct broker mode:** Standard Kelly sizing with risk management constraints only.

---

# PART D — STRATEGY INJECTION COMPARISON PROTOCOL

When a new Programs 1/2 run completes:

1. **Contextualise:** Run new candidate through every active AIM's historical model retroactively. Compute what each AIM would have said about this strategy over the last N months

2. **Compare:** Evaluate expected future performance of new candidate vs. current locked strategy, adjusted for accumulated AIM intelligence. Not raw OO alone

3. **Decide (presented via GUI as RPT-05):**
   - Clearly superior → propose **Adopt** (with transition phasing)
   - Comparable → propose **Parallel Track** (~20 trading days — both produce signals, only current one acted on)
   - Worse → propose **Reject** (log reason, retain current)

4. **Transition phasing:** If adopted, phase in over ~10 trading days. Both strategies tracked. Prevents abrupt change coinciding with adverse regime

5. **Memory:** Every injection event stored in persistent knowledge store — details, comparison, decision, reason

---

# PART E — SAMPLE DISCIPLINE

Captain (Offline) uses **expanding window that grows with live trading data**:
- Walk-forward validation: train on expanding window, validate on most recent held-out period
- Re-testing performed when window expands significantly (e.g., quarterly)
- Independent of Programs 1/2 sample definitions — Captain operates on LIVE data accumulated after P1/P2 runs
- When P1/P2 are re-run (Level 3), sample periods can be updated — but this is a human decision

---

# PART F — CORE ALGORITHMS

## F1. Expected Return Estimation

- EWMA of regime-conditional trade returns
- Computed SEPARATELY for win rate and average win/loss ratio (these move independently)
- `E[R | regime]` per asset, per regime state
- Note: for fixed TP/SL strategies (which MOST uses), win rate and payoff ratio are more stable than for adaptive exit strategies, but they still vary with regime and over time

## F2. Capital Allocation — Kelly Sizing (UPGRADED per research)

**Three-layer Kelly architecture (Papers 217, 218, 219):**

1. **Blended Kelly across regimes (Paper 219 — MacLean & Zhao):** Each regime has its own optimal Kelly portfolio. Regime weights combine them using current transition probabilities. Multi-asset problem reduces to: determine regime weights + fraction allocated to risky assets. VaR constraint at EACH decision point (not just horizon). Shortfalls penalised with convex function (linked to Prospect Theory).

2. **Parameter uncertainty shrinkage (Paper 217 — Baker & McHale):** Raw Kelly systematically overestimates when probabilities are estimated. Shrinkage factor depends on estimation variance. For log utility, shrinkage is ALWAYS the right direction. Half-Kelly (0.5 × full) is a conservative starting point. As data accumulates → shrinkage factor gradually increases toward 1.0.

3. **Distributional robust Kelly fallback (Paper 218 — Sun & Boyd, Stanford):** When regime is uncertain (transition zone, novel conditions) → maximise worst-case log growth across uncertainty set. Convex, tractable via CVXPY. Provides safety net preventing over-betting on uncertain estimates.

**Formula:** `blended_kelly(regime_probs) × shrinkage_factor × min(adjusted, robust_fallback) × AIM_aggregate × TSM_constraints`

**Constrained action selection (Paper 204):** Thompson Sampling for Contextual Bandits with Knapsacks (CBwK) maps to Captain maximising P&L under TSM constraints (MDD, MLL). Conservative Bandits (CCB) ensures performance stays above baseline.

- Multi-asset Kelly with covariance adjustment (from AIM-08)
- Kelly with absorbing barriers for prop firm evaluations (constraint-adjusted via TSM)
- AIM_aggregate modifier applied after Kelly computation via DMA/MoE weighted aggregation

## F3. Strategy Decay Detection (UPGRADED per research)

**Primary: BOCPD (Paper 231 — Adams & MacKay):**
- Online exact posterior over run length r_t at each timestep
- P(changepoint | history) computed daily — probabilistic, not binary
- Apply SEPARATELY to: trade P&L stream, per-AIM accuracy streams, regime features
- When P(changepoint) > 0.8 → trigger Level 2 (sizing reduction + alert)
- When P(changepoint) > 0.9 sustained for 5+ days → trigger Level 3 (strategy re-evaluation)

**Complementary: Distribution-free CUSUM with bootstrap (Paper 232 — Chatterjee & Qiu):**
- Trade returns are NOT Normal (fat tails, skewness) → standard CUSUM gives wrong false alarm rates
- Bootstrap-based sequential control limits calibrated to actual in-control distribution
- Sprint length T_n conditioning → (C_n, T_n) Markov process → more precise than single limit
- Detects MEAN shifts (edge decay) complementing BOCPD's distributional change detection

**Extended: BOCPD MBO(q) for autocorrelated data (Paper 228 — Tsaknaki):**
- Standard BOCPD assumes independence within regimes → violated in trading data
- MBO(q) extends to autoregressive dynamics; score-driven variant handles heteroskedasticity
- Bridges decay detection and Kelly re-evaluation in single framework

- Separate monitoring for win rate decay vs. payoff ratio decay
- Regime changes should not trigger false decay — decay detectors are regime-conditional
- Per-AIM drift detection via AutoEncoder reconstruction error + ADWIN (Paper 191)

## F4. TSM Simulation

- Monte Carlo simulation (block bootstrapping) for pass probability
- Uses actual trade return distribution + AIM-adjusted sizing
- Simulates remaining evaluation period under current conditions
- Updated after each trade outcome
- ~10,000 simulation paths

## F5. AIM Aggregation (UPGRADED per research)

**Architecture: Mixture-of-Experts (MoE) with DMA gating (Papers 187, 190, 209, 211)**

15 AIMs = 15 specialised experts. DMA-based gating function dynamically selects which experts are active and how much weight each receives. Not all AIMs active every day — gating determines relevance.

**Startup: EQUAL WEIGHTS (Paper 209 — Dormann et al.):**
- Equal weights are theoretically justified for reasonable model sets
- Finance (noisy, variance-dominated) meets conditions where model averaging is beneficial
- Low covariance between diverse AIM types is critical → AIMs designed to be diverse

**Learning: DMA (Paper 187 — Nonejad):**
- Forgetting factors + Kalman filter → computationally lightweight, no simulation
- Model probabilities update each period → identifies which AIMs matter NOW
- Inclusion probability output → Captain automatically knows which AIMs are contributing
- Forgetting factor provides regularisation against weight over-fitting

**Diversity: HDWM heterogeneous ensemble (Paper 190 — Idrees et al.):**
- "Seed" learners of each AIM type maintain diversity even when some underperform
- Handles RECURRING concept drifts (market regimes recur)
- Best model type changes over time → ensemble adapts automatically

```
# Daily aggregation:
aim_outputs = [AIM_1.modifier, ..., AIM_15.modifier]
model_probs = DMA_update(aim_outputs, forgetting_factor, prior_probs)
combined_modifier = weighted_average(aim_outputs, weights=model_probs)
Kelly_adjusted = Kelly_base × combined_modifier
```

Meta-weights learned via DMA from trade outcome feedback. Combined modifier capped at FLOOR/CEILING (0.5/1.5).

---

# PART G — RESEARCH FINDINGS APPLIED TO CAPTAIN

## G1. Adaptive Exit Management — Verdict: Fixed Exits

Papers 22 (Leung & Zhang 2021), 27 (Huber 2025), 29 (Lo & Remorov 2017) establish:
- Trailing stops only optimal under mean-reverting dynamics. ORB is a breakout/momentum strategy → fixed exits are correct
- RL system (MaxAI) achieves positive edge on NQ with FIXED TP/SL under realistic costs
- Tight stop-loss strategies generally underperform due to transaction costs

**Decision:** Captain uses fixed TP/SL from Program 1. No adaptive exit AIM.

Paper 24 (Koegelenberg & van Vuuren 2024): VaR-based price jump detection — noted as future Captain (Online) intraday risk management feature, not an AIM.

## G2. Cross-Asset Signal Agreement

Paper 14 (Amado & Teräsvirta 2014): TV-GARCH → AIM-08 architecture
Paper 18 (Soury 2024): RS Copula → AIM-08 tail dependence
Paper 19 (Tan, Roberts & Zohren 2023): SLP with MACD → AIM-09 architecture

## G3. Regime Classification

Paper 10 (Pettersson 2014): Tier 1 → Program 2 Block 1 + AIM-11 input
Paper 4 (Qiao et al. 2024): Tier 2 → Program 2 Block 1 (inactive)
Paper 11 (Shu, Yu & Mulvey 2025): Supervised prediction → Program 2 Block 3b

---

# PART H — PROFIT BOOSTERS STATUS

| Hole | Resolution | Location |
|------|-----------|----------|
| Adaptive Trade Management | RESOLVED — fixed exits per research | N/A |
| Pre-Market Information | AIM-04 | AIMRegistry.md |
| Cross-Asset Signal Agreement | AIM-08 + AIM-09 | AIMRegistry.md |
| Fee and Slippage Optimisation | AIM-12 | AIMRegistry.md |
| Temporal Pattern Exploitation | AIM-10 | AIMRegistry.md |
| Scaling In/Out | DEFERRED — not applicable for fixed TP/SL ORB at current scale | Future |
| Options-Derived Intelligence | AIM-01, AIM-02, AIM-03 | AIMRegistry.md |
| Regime Transition Early Warning | AIM-11 | AIMRegistry.md |
| Economic Calendar Conditioning | AIM-06 | AIMRegistry.md |
| Strategy Robustness Monitoring | AIM-13 | AIMRegistry.md |
| Automated Strategy Expansion | AIM-14 | AIMRegistry.md |
| Volume Quality Confirmation | AIM-15 | AIMRegistry.md |

---

# PART I — FUTURE SCALING CAPABILITIES

| Capability | When Relevant | Notes |
|------------|--------------|-------|
| Automated trade execution | Non-prop-firm accounts active | Captain (Command) → broker API. GUI → monitoring mode. Built in but locked |
| VWAP/TWAP execution | 50+ contracts | Captain (Command) execution layer, not an AIM. Immediate market order correct at current scale (1–5 contracts) |
| Multi-asset-class support | FX or other classes added | Captain core is asset-class-agnostic. Add new adapter + AIM sub-components per class. No Captain core changes |
| Scaling in/out | Larger position sizes | Dynamic position building. Requires real-time intraday monitoring |

---

# PART J — EXECUTION MODE

| Property | Current | Future |
|----------|---------|--------|
| Trade execution | Manual — GUI displays signals | Automated — Captain (Command) → broker API |
| Trade confirmation | Required — "Taken / Skipped" toggle | Automatic logging |
| Prop firm compatibility | Yes — TSM layer | Yes — same TSM layer |

---

# PART K — OPEN DECISIONS & PARAMETERS

| Parameter | Status | Suggested |
|-----------|--------|-----------|
| Kelly fraction (shrinkage start) | INFORMED | Start at 0.5 (half-Kelly per Paper 217), DMA adjusts dynamically |
| EWMA decay for E[R] | LOCKED | Adaptive span [8,30] via SPEC-A12 (BOCPD cp_prob scales alpha). Default span=30 at low cp_prob, 20 at medium. Supersedes static ~20 suggestion. |
| BOCPD Level 2 threshold | INFORMED | P(changepoint) > 0.8 (Paper 231) |
| BOCPD Level 3 threshold | INFORMED | P(changepoint) > 0.9 sustained 5+ days |
| CUSUM control limit | INFORMED | Bootstrap from in-control data (Paper 232) |
| DMA forgetting factor | LOCKED | 0.99 (top of 0.95–0.99 range; conservative for production start) |
| AIM modifier bounds | LOCKED | FLOOR=0.5, CEILING=1.5 |
| AIM meta-learning EWMA decay | LOCKED | λ=0.99 → effective window ≈100 trades (same parameter as DMA forgetting factor) |
| AIM minimum evaluation period | LOCKED | 50 trades before meta-weight adjusts |
| Parallel tracking observation period | LOCKED | 20 trading days |
| Transition phasing window | LOCKED | 10 trading days |
| TSM simulation iterations | LOCKED | 10,000 Monte Carlo paths |
| Captain (Offline) retrain schedule | LOCKED | Tier 1 AIMs weekly, Tier 2/3 AIMs + sensitivity scan monthly |
| VIX timing for regime_tag (P1 open param) | RESOLVED | Prior-day closing VIX (16:00 ET) — communicated to Nomaan |

---

# PART L — WHAT NEEDS TO BE BUILT INTO PROGRAM3.MD

1. Notation & conventions — extending P1/P2 notation for Captain-specific indexes
2. Datasets — persistent knowledge store, AIM model states, trade outcome logs, injection history, TSM files, report archives
3. Index programs — AIM index (A_{(a)}), TSM index, injection event index
4. Programs — Captain (Offline) programs, Captain (Online) programs, Captain (Command) programs with pseudocode
5. Orchestrator — how three components interact and schedule
6. Block-by-block flow — Captain (Online) daily flow, Captain (Offline) periodic flow
7. Data flow diagrams — from Programs 1/2 outputs through Captain to GUI
8. TSM specification — file format, loading protocol, constraint translation
9. AIM integration — plug-in interface per AIM (reference AIMRegistry.md)
10. Reporting programs — how each RPT is generated (reference AIMRegistry.md Part H)
11. Error handling — component failure policies
12. Warm-up policy — Captain's own warm-up requirements
13. Sample discipline — expanding window details
14. Open parameters — all TBD values
15. Pipeline flow diagram — full system P1 → P2 → P3 → GUI

---

# PART M — RESEARCH STATUS

## System Papers (4 topic areas, 6 prompts) — ALL COMPLETE

| Topic | Papers Extracted | Key Findings |
|-------|-----------------|--------------|
| System 1: Multi-signal aggregation | 4 (180, 183, 184, 187) | DMA is THE framework. Forecast combination correct for low-SNR. MLA architecture. |
| System 2: Kelly with uncertainty | 3 (217, 218, 219) | Blended Kelly + shrinkage + robust fallback. THE sizing formula. |
| System 3: Sequential monitoring | 3 (228, 231, 232) | BOCPD primary. Distribution-free CUSUM. MBO for autocorrelated data. |
| System 4a: Concept drift | 5 (189, 190, 191, 192, 193) | HDWM architecture. OBAL multistream. AREBA rare events. Unsupervised detection. |
| System 4b: RL / Bandits | 4 (197, 200, 204, 205) | Thompson Sampling for constrained bandits. Simplicity principle. |
| System 4c: Ensemble meta-learning | 3 (206, 209, 211) | MoE = Captain architecture. Equal weights start. Trading IS concept drift. |

## AIM Papers (15 modules) — ALL COMPLETE

All 15 AIMs screened AND fully extracted (~95 papers total). Design conclusions written for every module.
Full findings in `AIM_Extractions.md` (3,720 lines) and `AIM_Research_Notes.md`.

## Research Phase Complete

Total: ~115 papers extracted across 21 modules. Phase 3 (full extraction) completed.
Program3 specification build is the CURRENT STEP.

---

# PART N — DOCUMENT CROSS-REFERENCE

| Document | Purpose | Status |
|----------|---------|--------|
| `Program1.md` | Program 1 specification (FINAL-v2) | Complete |
| `Program2.md` | Program 2 specification (v1.0) | Complete |
| `AIMRegistry.md` | AIM framework, 15 modules, meta-learning, 10 reports | Complete — living |
| `GUI_Notes.md` | GUI requirements for Captain (Command) | Complete — living |
| `CaptainNotes.md` | This document — pre-specification design notes | Complete — living |
| `AIM_Research_Notes.md` | Running record of research findings per AIM | Complete — all 21 modules screened + extracted |
| `AIM_Extractions.md` | Detailed paper extraction findings (~3,720 lines) | Complete |
| `Phase3_Upload_Checklist.md` | Paper upload tracking for extraction phase | Complete — all 21/21 |
| `Program3_Architecture.md` | Captain system overview + reference for Nomaan | BUILDING |
| `Program3_Offline.md` | Captain (Offline) specification | BUILDING |
| `Program3_Online.md` | Captain (Online) specification | BUILDING |
| `Program3_Command.md` | Captain (Command) specification | BUILDING |
| `UserManagementSetup.md` | User management + multi-user migration | BUILDING |
| `NotificationSpec.md` | Telegram/push notification system | BUILDING |
| `XGBoost (Regime Classifier) Manual.md` | P2 Block 3b implementation guide | Complete |
| `Program2Tier2Report.md` | Tier 2 installation report | Complete |
| `RegimeClassificationMethods.md` | Papers 4, 10, 11 synthesis | Complete |

---

# PART O — CONTINUOUS 24/7 OPERATION (NEW — per design review)

## O1. Multi-Session Evaluation

Captain (Online) is NOT a pre-open-only engine. It runs continuously and evaluates at each major session open:

| Session | Time | Assets Evaluated |
|---------|------|-----------------|
| New York | 9:30 ET | ES, NQ, CL (primary) |
| London | 8:00 GMT | Index futures with London session liquidity |
| APAC | Various | Future expansion: HSI, Nikkei, ASX |

Each session evaluation = full pipeline run: data ingestion → regime computation → AIM aggregation → Kelly sizing → trade selection → signal output.

## O2. Strategy-Agnostic Design

Captain accepts ANY strategy type validated through Program 1:
- Market-open ORB strategies (current — short-term intraday)
- Swing/multi-day strategies (future — different holding periods)
- Multi-session strategies (future — different entry windows)

The Captain does NOT know or care what type of strategy it is managing. It processes: direction, entry conditions, TP, SL, holding period, expected edge — all provided by the locked strategy from Program 2. Different strategy types coexist in the same Captain instance and compete for capital allocation via the universe-level trade selection.

## O3. Intraday Position Monitoring

While positions are open, Captain (Online) continuously monitors:
- Live P&L against TP/SL levels
- Unexpected volatility spikes (VIX, realised vol)
- Regime shift indicators (AIM-11 early warning)
- Mid-trade condition changes requiring alerts

Alerts routed via Captain (Command) to GUI + notification system (Telegram).

---

# PART P — UNIVERSE MANAGEMENT AND ASSET WARM-UP (NEW)

## P1. Asset Universe Register

A formal register tracking all assets in the Captain's active portfolio:

```
asset_universe_register:
    asset_id        : string (e.g., "ES", "NQ", "CL")
    p1_status       : VALIDATED | PENDING | FAILED
    p2_status       : LOCKED | PENDING | NOT_RUN
    captain_status  : WARMING_UP | ACTIVE | PAUSED | DECAYED
    locked_strategy : reference to P2-D06 entry
    regime_model    : reference to P2-D07 entry
    warmup_progress : float ∈ [0, 1]
    warmup_required : int (trading days or trade count)
    date_added      : datetime
    last_signal     : datetime
```

## P2. Universe Upload

Assets are uploaded into Captain with their P1/P2 validation outputs. Captain matches asset-specific data from previous steps to the correct asset entry. All assets are saved but only assets with sufficient warm-up data produce trading signals.

## P3. Asset Warm-Up

Each asset in the universe requires a warm-up period before Captain generates trading signals:
- EWMA of regime-conditional returns needs ~20 trades
- AIM baselines (z-scores) need 60-252 trading days depending on AIM
- Correlation matrix (AIM-08) needs 252 trading days for full calibration
- Per-AIM warm-up tracked independently

GUI shows asset universe sub-tab with per-asset warm-up progress bars, estimated completion dates, and validation status.

---

# PART Q — POST-UPDATE RETEST (PSEUDOTRADER) SYSTEM (NEW)

## Q1. Purpose

When Captain proposes an update (new AIM weights, retrained model, injected strategy), it must demonstrate the update would have improved performance by "replaying" on historical data.

## Q2. Mechanism

1. Take the proposed update and apply it to the expanding historical window (all data from Captain start to now)
2. Run the full Captain (Online) pipeline in replay mode — same sequence of decisions but WITH the proposed change
3. Compare: system WITH update vs. system WITHOUT (actual historical performance)
4. Compute: Sharpe improvement, drawdown change, win rate delta, number of trades affected

## Q3. Validation

- PBO (Paper 152) computed on the pseudo-traded results to check for overfitting
- DSR (Paper 150) applied to the performance differential
- Walk-forward expanding window (Paper 161) ensures temporal integrity
- Results presented in RPT-09 (Decision Change Impact)

## Q4. Scope

Applied to:
- Strategy injection comparisons (Part D)
- AIM-13 sensitivity scan results
- AIM-14 auto-expansion candidates
- Manual parameter changes (user-initiated via GUI)

---

# PART R — SECURE API ARCHITECTURE (NEW)

## R1. Security Boundary

Captain's intelligence is protected behind a one-way valve:

```
Captain (Online) → signal → Captain (Command) → [SECURITY BOUNDARY] → API adapter → Broker/Prop Firm
                                                       ↑ (fill confirmations, account status ONLY)
                                                       └── NO strategy data, NO AIM data, NO model data flows out
```

## R2. Data Transmitted OUT (to broker/prop firm)

- Asset identifier
- Direction (long/short)
- Size (contracts)
- TP level
- SL level
- Timestamp

NOTHING ELSE. No strategy name, no AIM modifiers, no regime state, no confidence scores.

## R3. Data Received IN (from broker/prop firm)

- Fill price and fill time
- Account balance
- Current drawdown
- Position status (open/closed)

## R4. Per-Account API Management

- Each trading account has its own API adapter instance
- API keys stored in encrypted vault (see UserManagementSetup.md)
- Key rotation policy enforced
- Connection health monitoring
- Automatic reconnection on failure

## R5. TopstepX API Compatibility

Architecture designed with TopstepX API as the first integration target. API adapter interface is standardised so additional brokers/prop firms can be added by implementing the same interface.
