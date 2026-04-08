just # V3+ Multi-Strategy System — Architectural Plan

**Purpose:** Define how the MOST system evolves from a single-strategy market-open ORB engine into a fully general, multi-strategy, multi-asset, multi-data-source autonomous trading system — while maintaining full backward compatibility with the V1 architecture and providing Nomaan with clear, modular extension points.

**Built on:** `Exhaustive_Strategy_Taxonomy.md` (Step 1) — ~750+ taxonomy items across 12 parts.
**Compatible with:** `Program3_Architecture.md` and all V1 companion specs.
**Date:** 2026-03-09

**Convention:** Items marked with **[RESEARCH REQUIRED]** indicate gaps where existing literature does not provide a ready answer and empirical research, academic investigation, or model development is needed before implementation. Each flag includes a brief description of what research is needed and why.

---

# PART 1 — ARCHITECTURAL PHILOSOPHY

## 1.1 Extension, Not Replacement

The V1 system (Programs 1, 2, 3) is architecturally sound. Captain's Section 1.3 already declares the system "strategy-agnostic" — it accepts any strategy type validated through Program 1. The V3+ upgrade operationalises this promise across the full taxonomy.

**Design rule:** Every V3+ addition attaches to an existing V1 interface or creates a new parallel module. No existing block is rewritten. If an existing block's logic must change, the change is additive (new branch, new field, new config option) — never destructive.

**For Nomaan:** This means the upgrade is a series of:
- New Python classes implementing existing interfaces (new AIMs, new adapters)
- New fields in existing datasets (P3-D00, P3-D03, P3-D05, P3-D12)
- New modules alongside existing blocks (arbitration engine alongside Block 5)
- New Docker services alongside the existing stack (satellite silos as separate containers or separate servers)

Nothing he has already built gets torn out.

## 1.2 The Abstraction Stack

The V3+ system is best understood as five abstraction layers, each independent and pluggable:

```
LAYER 5: CAPITAL ARBITRATION ENGINE
    Decides how much capital goes to which strategy on which asset at which moment.
    Resolves all conflict scenarios (SC-01 through SC-32).
    
LAYER 4: STRATEGY EVALUATION & SIGNAL GENERATION
    Evaluates validated strategies per session.
    Regime conditioning, AIM aggregation, Kelly sizing, quality gating.
    (This is Captain Online Blocks 1-6 — already exists.)

LAYER 3: INTELLIGENCE INTEGRATION
    Normalises all intelligence sources into a common signal format.
    AIMs (internal) + Satellite Silos (external) → unified modifier/signal space.

LAYER 2: DATA INGESTION & NORMALISATION
    Ingests price data, alternative data, silo outputs, broker feeds.
    Validates, timestamps, and routes to the appropriate consumer.
    (This is Captain Online Block 1 + data source adapters — partially exists.)

LAYER 1: EXECUTION & SETTLEMENT
    Sends signals to venues, receives fills, reconciles.
    Venue-agnostic, protocol-agnostic.
    (This is Captain Command Block 3 + API adapters — already exists.)
```

V1 already has Layers 1, 2, and 4 built. V3+ adds Layer 3 (intelligence integration via satellite silos) and Layer 5 (capital arbitration). Layer 2 gets extended to handle silo outputs. Layer 4 gets extended to handle multiple strategy types per asset.

## 1.3 Version Upgrade Path: V1 → V2 → V3

The system evolves through three major versions:

| Version | What It Adds | Architecture Impact |
|---------|-------------|---------------------|
| **V1** | Single user, manual execution, all security/infra built from day one | Baseline. Captain Offline/Online/Command. 23 datasets. 15 AIMs. |
| **V2** | Multi-user. Per-user capital silos (P3-D16), RBAC (6 roles), per-user key vault isolation, parallel per-user deployment loops | Online pipeline splits into SHARED (Blocks 1-3, computed once) and PER-USER (Blocks 4-6, run per active user). Capital is siloed per user. Intelligence is shared. |
| **V3+** | Multi-strategy, satellite silos, capital arbitration, continuous/event evaluation | New components must respect the V2 shared/per-user boundary. See Section 1.4. |

**Critical design rule:** V3+ is built ON V2, not alongside it. Every V3+ component must specify whether it operates in the SHARED layer or the PER-USER layer of the V2 architecture.

## 1.4 V3+ Component Placement in the V2 Shared/Per-User Split

```
SHARED INTELLIGENCE (computed ONCE per session — same for all users)
┌────────────────────────────────────────────────────────────────────┐
│  Block 1: Data Ingestion (existing)                                │
│      + Silo data adapters (V3+ — silo outputs ingested here)      │
│                                                                    │
│  Block 2: Regime Probability (existing — unchanged)                │
│                                                                    │
│  Block 3: AIM Aggregation (existing)                               │
│      + AIM-16 to AIM-26 (V3+ — silo-backed AIMs included here)   │
│      + DMA/MoE learns weights for new AIMs alongside existing     │
│                                                                    │
│  Outputs: features, regime_probs, combined_modifier, aim_breakdown │
│           ↓ passed to EVERY user's deployment loop                 │
└────────────────────────────────────────────────────────────────────┘

PER-USER DEPLOYMENT (computed for EACH active user independently)
┌────────────────────────────────────────────────────────────────────┐
│  Block 4: Kelly Sizing (existing — uses THIS user's P3-D16 silo) │
│      + V3+: multi-strategy Kelly when multiple strategy types     │
│        active (separate Kelly per strategy_type_id)               │
│                                                                    │
│  Block 5: Trade Selection (existing — per-user sizing applied)    │
│      + V3+ ARBITRATION ENGINE (NEW — runs per-user)               │
│        Uses THIS user's capital silo, TSM configs, jurisdiction   │
│        Steps 1-6: conflict resolution → ranking → risk check →   │
│        capital allocation → reallocation → cascade evaluation     │
│                                                                    │
│  Block 5B: Quality Gate (existing — unchanged)                     │
│                                                                    │
│  Block 6: Signal Output (existing — per-user signal queue)        │
│                                                                    │
│  Inputs: shared intelligence + P3-D16[THIS_USER] capital silo     │
│  Outputs: per-user signal queue → Command → GUI/API               │
└────────────────────────────────────────────────────────────────────┘

POST-USER AGGREGATION (computed ONCE after all user loops complete)
┌────────────────────────────────────────────────────────────────────┐
│  Block 8: Network Concentration Monitor (existing)                 │
│      + V3+: concentration tracked per (asset, strategy_type)      │
│        not just per asset. 20 users in ES via 5 different         │
│        strategies is still concentration risk on ES.               │
│                                                                    │
│  Block 9: Capacity Evaluation (existing — unchanged)               │
└────────────────────────────────────────────────────────────────────┘

V3+ CONTINUOUS/EVENT EVALUATORS (async loops — follow same pattern)
┌────────────────────────────────────────────────────────────────────┐
│  ContinuousEvaluator / EventEvaluator:                             │
│      Uses CACHED shared intelligence (regime, AIM modifiers)      │
│      When triggered, runs a LIGHTWEIGHT per-user deployment loop: │
│        Block 4 (Kelly) → Block 5 (Selection) → Arbitration →     │
│        Block 5B (Quality) → Block 6 (Output)                      │
│      Each user evaluated independently using their capital silo   │
│      Signal output per-user, same as session-open flow            │
└────────────────────────────────────────────────────────────────────┘
```

**Why this matters for Nomaan:**
- Silo AIM integration (AIM-16+) is in the SHARED layer → coded once, benefits all users automatically
- Arbitration Engine is in the PER-USER layer → each user's capital silo drives their own allocation decisions
- ContinuousEvaluator produces per-user signals → it must loop through active users just like the session evaluator does
- A user's `strategy_type_whitelist` (TSM V3) filters which strategy types run in THEIR per-user loop — other users' whitelists don't affect them
- Capital reservation (Step 4) reserves from THIS user's available capital, not from a shared pool

## 1.5 Backward Compatibility Contract

The following invariants hold across all upgrades:

| Invariant | Description |
|-----------|-------------|
| BC-01 | Any strategy that works in V1 works identically in V3+ with zero configuration changes |
| BC-02 | All 23 P3-D datasets retain their existing fields. New fields are additive only |
| BC-03 | The Kelly sizing pipeline (7 layers) continues to operate unchanged for single-strategy assets |
| BC-04 | BOCPD/CUSUM decay detection works per-strategy, not per-asset (extends naturally) |
| BC-05 | The API adapter interface does not change — signals OUT, fills IN |
| BC-06 | The GUI shows additional information (multi-strategy views) but existing views remain |
| BC-07 | TSM configurations continue to work without modification |
| BC-08 | Single-user V1 and multi-user V2 deployments both support V3+ features |
| BC-09 | V2 shared/per-user boundary is preserved. No V3+ component in the PER-USER layer reads or modifies another user's data |
| BC-10 | V2 RBAC roles (ADMIN, DEV, RISK, TRADER, VIEWER, SUPPORT) continue to apply. V3+ strategy management follows existing role permissions — TRADER can view/act on signals, ADMIN can modify strategy_type_register and silo configs |
| BC-11 | V2 per-user key vault isolation is maintained. Silo API keys (if any) are stored in the system vault, not per-user vaults — silos are shared infrastructure, not per-user resources |

---

# PART 2 — STRATEGY ABSTRACTION LAYER

## 2.1 The Strategy Type Problem

V1 assumes one strategy per asset — the locked strategy from Program 2 (P2-D06). V3+ must handle:
- Multiple strategy types per asset (ORB + swing + 0DTE on ES simultaneously)
- Strategy types with different holding periods (minutes vs. days vs. weeks)
- Strategy types with different evaluation cadences (session-open only vs. continuous vs. event-driven)
- Strategy types with different exit mechanisms (SL/TP vs. time-based vs. signal-reversal vs. expiry)

## 2.2 Strategy Type Registry (New Dataset: P3-D23)

A new persistent dataset extending the knowledge store:

```
P3-D23: strategy_type_register

Fields:
    strategy_type_id:       STRING      // unique identifier (e.g., "ORB_5MIN", "SWING_TREND", "0DTE_GAMMA")
    holding_period_class:   ENUM        // maps to taxonomy Part 1 tiers:
                                        // ULTRA_HF, HF, INTRADAY_SHORT, INTRADAY_MEDIUM,
                                        // OVERNIGHT, SWING, POSITION, LONG_TERM, PERPETUAL
    evaluation_cadence:     ENUM        // SESSION_OPEN, CONTINUOUS, EVENT_DRIVEN, SCHEDULED
    exit_mechanism:         ENUM        // SL_TP, TIME_BASED, SIGNAL_REVERSAL, EXPIRY, COMPOSITE
    capital_lockup_type:    ENUM        // NONE (intraday), OVERNIGHT, MULTI_DAY, INDEFINITE
    margin_type:            ENUM        // CASH, REG_T, PORTFOLIO_MARGIN, SPAN
    max_concurrent_per_asset: INT       // how many simultaneous positions per asset
    signal_format: {
        requires_direction:   BOOL
        requires_tp:          BOOL
        requires_sl:          BOOL
        requires_expiry:      BOOL      // for options/0DTE
        requires_legs:        INT       // 1 for simple, 2+ for spreads/pairs
        requires_greeks:      BOOL      // for options strategies
    }
    signal_ttl:             DURATION    // how long a generated signal remains valid before expiry.
                                        // SESSION_OPEN strategies: default = time until next session eval.
                                        // CONTINUOUS: strategy-specific (e.g., 5 minutes).
                                        // EVENT_DRIVEN: event-specific (e.g., 30 minutes post-event).
                                        // Expired signals are removed from the arbitration queue.
    p1_validation_method:   STRING      // which P1 blocks apply to this strategy type
    compatible_assets:      LIST[STRING]// asset types this strategy can trade
    status:                 ENUM        // ACTIVE, WARM_UP, ARCHIVED, PROPOSED
    created:                DATETIME
    last_validated:         DATETIME
```

**Why this matters:** Every component downstream (Kelly sizing, decay detection, trade selection, risk aggregation) uses `strategy_type_id` to apply the correct logic. An ORB strategy and a swing strategy on the same asset have different Kelly parameters, different EWMA decay rates, different BOCPD baselines, and different position monitoring rules. The registry tells the system what rules apply.

## 2.3 Strategy Type × Holding Period Matrix

The taxonomy identifies 9 holding period tiers. The system must handle any combination, but not all at once. The architectural approach is tiered activation:

| Tier | Holding Period | V3+ Status | Architectural Requirement |
|------|---------------|------------|---------------------------|
| 1.1 | Ultra-HF (ns-ms) | DEFERRED | Requires FPGA/co-location hardware. Incompatible with current Docker/cloud architecture. Accommodated by defining the interface but not implementing the execution layer. |
| 1.2 | HF (ms-s) | DEFERRED | Requires DMA (Direct Market Access) and low-latency execution. Same deferral approach. |
| 1.3 | Intraday Short (s-min) | ACTIVE | Current primary (ORB). Fully supported. |
| 1.4 | Intraday Medium (min-hr) | READY | Captain's session-based evaluation + intraday monitoring already support this. Needs multi-evaluation-per-session capability. |
| 1.5 | Overnight/Short Swing (hr-days) | READY | Requires position carry-over logic. Online Block 7 (monitoring) already supports intraday; needs extension to persist positions across sessions. |
| 1.6 | Swing/Multi-Day (days-weeks) | READY | Same as 1.5 with longer holding periods. Kelly sizing needs separate EWMA for multi-day returns. |
| 1.7 | Position/Medium-Term (weeks-months) | FUTURE | Requires portfolio-level rebalancing logic. Capital lockup conflicts with intraday strategies. |
| 1.8 | Long-Term/Strategic (months-years) | FUTURE | Requires different risk framework (drawdown tolerance vs. daily VaR). |
| 1.9 | Multi-Generational (years-decades) | OUT OF SCOPE | Fundamentally different product (wealth management, not trading). Accommodated by defining the interface but never activating. |

**[RESEARCH REQUIRED: Multi-Horizon Kelly Sizing]**
Kelly criterion is well-defined for single-period bets (one trade at a time with known edge and odds). When strategies with different holding periods coexist:
- A daily ORB trade resolves in hours. Its Kelly fraction updates daily.
- A swing trade resolves in days-weeks. Its Kelly fraction updates weekly.
- Capital allocated to a swing trade is unavailable for daily ORB trades during the holding period.

The research question: **How do you compute optimal capital allocation across strategies with heterogeneous time horizons?** The standard Kelly formula doesn't handle this directly. Multi-period Kelly extensions exist (Thorp, 2006; MacLean, Thorp & Ziemba, 2011) but typically assume homogeneous bet frequencies. We need a framework that handles simultaneous strategies with different turnover rates competing for the same capital pool.

**Research approach:** Review multi-period Kelly literature (Thorp, MacLean-Ziemba), continuous-time Kelly (Merton's portfolio problem), and multi-asset Kelly with stochastic opportunity arrival. Document findings as an experiment proposal for empirical validation on Sample 1.

**[RESEARCH REQUIRED: Cross-Frequency Correlation Estimation]**
When strategies operate at different frequencies (intraday vs. multi-day), their return series have different sampling rates. Computing correlation between a daily-resolution return stream and a weekly-resolution return stream for risk aggregation is not straightforward.

**Research approach:** Review mixed-frequency VAR (MF-VAR), MIDAS (Mixed Data Sampling), and Hayashi-Yoshida estimator for asynchronous correlation. Determine which method is most appropriate for our use case (2-5 strategy types, not hundreds).

## 2.4 Evaluation Cadence Extensions

V1 evaluates at session open only. V3+ needs three cadences:

### SESSION_OPEN (Current — No Change)
Strategies that generate signals at a fixed time (NY open 09:30, LON open 08:00, APAC open varies). This is exactly what Captain Online does now. No modification needed.

### CONTINUOUS (New)
Strategies that generate signals throughout the session (e.g., 0DTE options responding to intraday volatility, intraday mean reversion scanning for entry setups). 

**Implementation:** Online Block 1 (data ingestion) already receives streaming price data. Add a `ContinuousEvaluator` module that:
1. Subscribes to intraday price updates via the existing data feed
2. When a continuous strategy's entry conditions are met, runs a lightweight evaluation:
   - Uses CACHED shared intelligence (regime_probs, combined_modifier from the last session-open evaluation)
   - Runs the PER-USER deployment loop (Blocks 4-6 + Arbitration) for EACH active user whose TSM permits continuous strategies
   - Each user's capital silo, accounts, and constraints are applied independently
3. Produces per-user signals through the same Block 5B quality gate and Block 6 signal output
4. Signal delivery is per-user, identical to session-open flow

**For Nomaan:** The ContinuousEvaluator is a new Python class in the Online container. It shares the same Redis pub/sub channels, QuestDB connections, and AIM states as the session evaluator. It runs as a separate async loop within the Online process (not a separate container — latency of cross-container IPC is unnecessary here). **V2 critical:** The per-user loop in the ContinuousEvaluator must follow the same pattern as the session evaluator's per-user loop — iterate through active users, load each user's P3-D16 silo, apply their TSM, generate their signals independently.

**[RESEARCH REQUIRED: Continuous Evaluation Signal Quality Calibration]**
The Block 5B quality gate was designed for session-open signals. Continuous signals have different statistical properties — higher volume of lower-quality signals, time-varying quality distribution, and signal clustering around events. The quality floor and ceiling parameters (currently OPEN, placeholder 0.003-0.010) need separate calibration for continuous strategies.

**Research approach:** After at least one continuous strategy is validated through P1, analyse the distribution of signal quality scores across the session. Determine whether a single quality gate works or whether time-of-day-conditional gates are needed.

### EVENT_DRIVEN (New)
Strategies that trigger on specific events (FOMC announcement, earnings release, sentiment spike, satellite silo alert). These don't have a predictable schedule.

**Implementation:** Add an `EventEvaluator` module that:
1. Subscribes to event channels (economic calendar from AIM-06, satellite silo alerts, news sentiment spikes)
2. When an event fires, evaluates registered EVENT_DRIVEN strategies against that event
3. Runs the PER-USER deployment loop for each active user whose TSM permits event-driven strategies
4. Produces per-user signals through the standard pipeline

**For Nomaan:** Similar to ContinuousEvaluator but triggered by Redis pub/sub events rather than polling. Each event type has a registered set of strategies that care about it. **V2 critical:** Same per-user loop requirement as ContinuousEvaluator — each user evaluated independently with their own capital silo and constraints.

**[RESEARCH REQUIRED: Event-Driven Strategy Validation Through P1]**
Program 1's current 5-block pipeline assumes a strategy produces a regular stream of trades across the sample period. Event-driven strategies produce irregular, clustered trades (e.g., 8 FOMC days per year, ~4 earnings reports per quarter per stock). The OO scoring methodology may not be statistically valid for small-sample, clustered trade distributions.

**Research approach:** Review small-sample statistical testing for trading strategies (White's Reality Check, Hansen's SPA test, Romano-Wolf stepdown). Determine minimum trade count for valid P1 evaluation of event-driven strategies. If standard P1 is insufficient, design a modified validation block for event-driven strategies.

## 2.5 Multi-Strategy Per Asset: Data Model Changes

Existing P3-D datasets that currently assume one strategy per asset need extension:

| Dataset | Current | V3+ Extension |
|---------|---------|---------------|
| P2-D06 (locked_strategy_register) | One locked (model, feature, threshold, regime_method) per asset | One locked strategy per **(asset, strategy_type)** pair. P2-D06 becomes a list per asset, each entry tagged with strategy_type_id |
| P3-D03 (trade_outcome_log) | Trades logged by asset | Add `strategy_type_id` field. Every trade is tagged with which strategy generated it |
| P3-D05 (ewma_states) | EWMA indexed by [asset][regime][session] | Add `strategy_type_id` dimension: [asset][strategy_type][regime][session]. Each strategy type has its own win rate, avg_win, avg_loss tracked independently |
| P3-D12 (kelly_parameters) | Kelly fractions per asset | Kelly fractions per **(asset, strategy_type)**. Different strategies on the same asset have different edges and different optimal sizing |
| P3-D04 (decay_detector_states) | BOCPD/CUSUM per asset | BOCPD/CUSUM per **(asset, strategy_type)**. A swing strategy on ES can decay independently of the ORB strategy on ES |
| P3-D02 (aim_meta_weights) | DMA weights per AIM per asset | DMA weights per AIM per **(asset, strategy_type)**. An AIM may be highly relevant for ORB but irrelevant for swing |

**For Nomaan:** These are additive field changes. The new `strategy_type_id` field defaults to `"PRIMARY"` for all existing single-strategy data, maintaining backward compatibility (BC-01). New strategy types added later produce new rows indexed by their strategy_type_id.

---

# PART 3 — SATELLITE SILO INTEGRATION ARCHITECTURE

## 3.1 Conceptual Model

A satellite silo is an **independent program** that:
1. Ingests raw domain-specific data (weather feeds, satellite imagery, blockchain data, etc.)
2. Runs domain-specific models (trained by domain experts, not by Captain)
3. Outputs a standardised signal that Captain can consume

**The silo is NOT inside Captain.** It runs on its own infrastructure (could be a separate Docker container, a separate server, a cloud function, a third-party API). Captain treats silo output identically to any other data source — it arrives via the existing data adapter framework (REST, WebSocket, FILE) and feeds into a dedicated AIM instance.

```
SATELLITE SILO (Independent)                    CAPTAIN (Existing)
┌──────────────────────────────┐               ┌──────────────────────────┐
│ Weather Silo                 │               │ Captain (Online)         │
│   ├── Ingests: NOAA, ECMWF  │               │   ├── Data Ingestion     │
│   ├── Models: temp anomaly,  │  ──SIGNAL──►  │   │   └── Silo Adapter   │
│   │   precip forecast, etc.  │  (standard    │   ├── AIM-16 (Weather)   │
│   ├── Outputs: commodity     │   schema)     │   │   └── Wraps signal   │
│   │   risk scores            │               │   ├── DMA/MoE learns     │
│   └── Schedule: own cadence  │               │   │   weight over time   │
└──────────────────────────────┘               └──────────────────────────┘
```

## 3.2 Silo Output Schema (From Taxonomy Part 6.3)

Every silo, regardless of domain, outputs signals in this exact format:

```
SiloSignal:
    silo_id:            STRING          // "WEATHER_V1", "SATELLITE_IMAGERY_V2", etc.
    silo_domain:        STRING          // maps to taxonomy Part 6.2 categories
    signal_id:          STRING          // unique signal identifier
    timestamp:          DATETIME        // when the signal was generated (America/New_York)
    asset_relevance:    MAP[asset_id → relevance_score(0.0-1.0)]
    signal_value:       FLOAT           // normalised output
    signal_type:        ENUM            // DIRECTIONAL | VOLATILITY | RISK | CONFIDENCE | CATALYST | INFORMATIONAL
    confidence:         FLOAT(0.0-1.0)  // silo's self-assessed confidence
    latency_class:      ENUM            // REAL_TIME | HOURLY | DAILY | WEEKLY | MONTHLY | EVENT_DRIVEN
    staleness_limit:    DURATION        // how long before this signal should be ignored
    metadata:           JSON            // domain-specific context
```

### Signal Type Semantics

| Signal Type | What It Means | How Captain Uses It |
|-------------|---------------|---------------------|
| DIRECTIONAL | Bullish/bearish directional view (-1.0 to +1.0) | Modifies AIM aggregation — reinforces or dampens directional signals |
| VOLATILITY | Expected volatility change (0.0 = calm, 1.0 = extreme) | Modifies regime probability — shifts toward HIGH_VOL regime |
| RISK | Risk warning level (0.0 = safe, 1.0 = extreme risk) | Modifies Kelly fraction — reduces position sizing as risk rises |
| CONFIDENCE | Confidence in current market state (0.0 to 1.0) | Modifies signal quality gate — higher confidence lowers the quality threshold |
| CATALYST | Event-driven alert (0.0 = no event, 1.0 = major catalyst) | Triggers EVENT_DRIVEN strategy evaluation |
| INFORMATIONAL | Context data with no direct trading implication | Logged to P3-D03 metadata for post-trade analysis; no real-time effect |

## 3.3 Silo-to-AIM Mapping

Each satellite silo is wrapped by a dedicated AIM instance. The AIM acts as the "translator" between the silo's domain-specific output and Captain's unified intelligence framework.

### New AIM Instances (AIM-16+)

| AIM ID | Silo Domain | Primary Signal Type | Affected Strategies | Tier |
|--------|-------------|--------------------|--------------------|------|
| AIM-16 | Weather / Climate | DIRECTIONAL, VOLATILITY | Commodity strategies (CL, NG, agricultural futures) | 3 (when activated) |
| AIM-17 | Satellite Imagery | DIRECTIONAL, CONFIDENCE | Commodity, retail, macro strategies | 3 |
| AIM-18 | Geopolitical Risk | RISK, VOLATILITY | FX, EM, commodity, macro strategies | 2 |
| AIM-19 | NLP / Sentiment (Extended) | DIRECTIONAL, CONFIDENCE | All strategy types (universal modifier) | 2 |
| AIM-20 | Macroeconomic Nowcasting | DIRECTIONAL, VOLATILITY | Macro, duration, equity timing strategies | 2 |
| AIM-21 | Supply Chain / Logistics | DIRECTIONAL, CATALYST | Commodity, corporate fundamental strategies | 3 |
| AIM-22 | Epidemiological / Health | CATALYST, RISK | Pharma/biotech, macro, insurance strategies | 3 |
| AIM-23 | Energy Systems | DIRECTIONAL, VOLATILITY | Energy commodity, utility, carbon strategies | 3 |
| AIM-24 | Blockchain / On-Chain | DIRECTIONAL, RISK | Crypto, DeFi, tokenized asset strategies | 3 |
| AIM-25 | Scientific / Physical | RISK, CATALYST | Cat bond, insurance, infrastructure strategies | 3 |
| AIM-26 | Autonomous Intelligence | CONFIDENCE, DIRECTIONAL | Meta-layer: aggregates outputs from other AI systems | 3 |

**For Nomaan:** Each AIM-16+ is a Python class inheriting from the existing AIM base class (defined in AIMRegistry.md). The class:
1. Reads silo output from the data source adapter (REST/WebSocket/FILE)
2. Validates the SiloSignal schema
3. Checks staleness (reject if `now() - timestamp > staleness_limit`)
4. Converts `signal_value` and `signal_type` to an AIM modifier (0.5 to 1.5, matching existing AIM bounds)
5. Outputs the modifier through the standard AIM interface

The DMA meta-learning system (Offline Block 1) learns the weight of each silo-backed AIM over time. If a weather silo produces noise, its weight converges to zero. If it produces genuine signal, its weight increases. No manual tuning needed after initial warm-up.

## 3.4 Silo Confidence Calibration

**[RESEARCH REQUIRED: Cross-Domain Confidence Calibration]**
Each silo self-reports a `confidence` score (0.0 to 1.0). But a weather model's 0.8 confidence is not comparable to a geopolitical model's 0.8 confidence — different domains have different calibration, different base rates, and different error distributions. If Captain naively treats all confidence scores as equivalent, it will overweight domains with overconfident models.

**The problem:** Confidence scores from heterogeneous sources are not on the same scale. A satellite imagery model trained on 10 years of corn yield data might be well-calibrated. A geopolitical risk model trained on 50 conflict events might be systematically overconfident.

**Research approach:**
1. **Platt scaling / isotonic regression** — post-hoc calibration of each silo's confidence against actual outcomes. Requires accumulating silo-signal → outcome pairs over time.
2. **Bayesian confidence updating** — maintain a prior on each silo's calibration quality. Update the prior as outcomes arrive. Apply a calibration correction factor per silo.
3. **Literature review:** Gneiting & Raftery (2007) on proper scoring rules, Kuleshov et al. (2018) on calibration of modern ML models. Determine whether simple Platt scaling is sufficient or whether silo-specific calibration methods are needed.

**Interim approach (pre-research):** Captain already handles this implicitly through DMA meta-learning. If a silo's confidence claims are systematically wrong, the DMA will downweight that silo-backed AIM. Research determines whether explicit confidence recalibration would converge faster than letting DMA learn it.

## 3.5 Silo Lifecycle Management

### 3.5.1 Adding a New Silo

| Step | Action | Owner | System Response |
|------|--------|-------|-----------------|
| 1 | Silo developer creates the silo program (independent codebase) | External / Isaac's team | N/A |
| 2 | Silo developer implements SiloSignal output schema | External | N/A |
| 3 | Silo operator deploys the silo (separate infrastructure) | External | N/A |
| 4 | Isaac registers a new AIM instance (AIM-N) in AIMRegistry | Isaac | AIM-N created in PROPOSED state |
| 5 | Nomaan creates the AIM-N Python class + data source adapter config | Nomaan | AIM-N code + config committed |
| 6 | AIM-N enters WARM_UP | Automatic | DMA includes AIM-N with neutral weight. 50-trade minimum before weight adjusts. Modifier locked at 1.0 during warm-up. |
| 7 | AIM-N reaches ELIGIBLE after 50+ trades with silo data | Automatic | DMA begins learning AIM-N's weight. If weight > 0.05 after 30 days → AIM-N contributes to signals. |
| 8 | If DMA weight converges to <0.01 for 90 days → AIM-N auto-archived | Automatic | AIM-N moved to DORMANT. No resource cost. Can be reactivated. |

### 3.5.2 Silo Failure Handling

Inherits Captain's existing graceful degradation (Architecture Section 10.2):
- If silo is unreachable → AIM-N outputs modifier 1.0 (neutral). Other AIMs continue.
- If silo data is stale (beyond staleness_limit) → AIM-N outputs modifier 1.0 + logs warning.
- If silo outputs invalid schema → AIM-N rejects signal, outputs 1.0 + alerts ADMIN.
- No silo failure can crash Captain or affect other silos/AIMs.

### 3.5.3 Basis Divergence Monitoring (AIM-08 Extension)

When two positions are explicitly linked as a hedge pair (e.g., long ES futures + short SPY options), AIM-08 (Cross-Asset Correlation) is extended to monitor basis divergence between the paired instruments:

```
basis_monitor(pair):
    current_basis = price(instrument_A) - beta_adjusted_price(instrument_B)
    historical_basis_mean = EWMA(basis, span=60_days)
    historical_basis_std = rolling_std(basis, span=60_days)
    basis_z_score = (current_basis - historical_basis_mean) / historical_basis_std

    IF abs(basis_z_score) > basis_alert_threshold:  // default 3.0
        ALERT "Basis divergence on hedged pair {pair}: z-score = {basis_z_score}"
        IF abs(basis_z_score) > basis_deleverage_threshold:  // default 4.0
            AUTO-REDUCE both legs proportionally by 50%
            CREATE incident("RISK", "P1_HIGH", "BASIS_DIVERGENCE", ...)
```

This addresses R-13 (basis blow-up). The `basis_monitor` flag is set on positions that are explicitly tagged as hedge pairs in the Arbitration Engine's Step 1 output. Non-hedged positions are not monitored for basis (no concept of basis for a standalone position).

## 3.6 Silo Architecture for Taxonomy Coverage

The taxonomy identifies 11 silo domains (Part 6.2). Here is the implementation priority and research status for each:

| Silo Domain | Taxonomy Ref | Implementation Priority | Research Status |
|-------------|-------------|------------------------|-----------------|
| NLP / Sentiment | 3.9 | HIGH — universal modifier, applicable to current ORB strategies | Partial — sentiment models exist; need to evaluate which produces tradeable signal on ES futures |
| Macroeconomic Nowcasting | 3.4 | HIGH — regime classification augmentation | Partial — nowcasting models well-studied; need to evaluate signal-to-noise ratio for intraday strategies |
| Geopolitical Risk | 3.5 | MEDIUM — tail risk management, FX/commodity strategies | **[RESEARCH REQUIRED]** — geopolitical risk indices (GPR) exist but their predictive power for intraday futures is unstudied |
| Weather / Climate | 3.7 | MEDIUM — commodity strategies (CL, NG, agricultural) | **[RESEARCH REQUIRED]** — weather→commodity price transmission well-documented in literature but lag structure varies by commodity |
| Satellite Imagery | 3.6 | MEDIUM — commodity, macro strategies | **[RESEARCH REQUIRED]** — satellite-derived signals (parking lot fills, oil storage) have demonstrated alpha in equity markets (RS Metrics, Orbital Insight research). Applicability to futures markets less studied |
| Supply Chain / Logistics | 3.10 | LOW — requires AIS/shipping data infrastructure | **[RESEARCH REQUIRED]** — supply chain stress indices exist but real-time signal extraction is nascent |
| Blockchain / On-Chain | 3.10 | LOW — only relevant when crypto strategies activated | Partial — on-chain analytics is mature (Glassnode, Chainalysis). Need to evaluate signal decay in competitive environment |
| Epidemiological / Health | 3.8 | LOW — event-driven, infrequent | **[RESEARCH REQUIRED]** — pandemic trading alpha is well-documented retrospectively but real-time signal extraction is unreliable |
| Energy Systems | 3.10 | LOW — requires power grid data access | **[RESEARCH REQUIRED]** — energy market microstructure research exists but integration into a general system is novel |
| Scientific / Physical | 3.11 | VERY LOW — frontier/speculative | **[RESEARCH REQUIRED]** — no established literature on trading signals from seismic, volcanic, or space weather data |
| Autonomous Intelligence | 3.11 | VERY LOW — meta-layer, requires multiple active silos | **[RESEARCH REQUIRED]** — multi-agent AI consensus for trading is an open research area. No established methodology |

---

# PART 4 — CAPITAL ARBITRATION ENGINE

## 4.1 The Core Problem

When multiple strategies across multiple assets generate signals simultaneously, with finite capital, the system must decide:
1. **Which trades to take** (selection)
2. **How much capital for each** (sizing)
3. **Whether to liquidate existing positions** to fund new ones (reallocation)
4. **How to handle conflicting signals** on the same asset (conflict resolution)

V1 handles this partially in Online Block 5 (trade selection with correlation adjustment). V3+ formalises this into a dedicated Capital Arbitration Engine that sits between the signal generation pipeline and the execution layer.

## 4.2 Arbitration Engine Architecture

```
INPUTS (from Layer 4 — Strategy Evaluation):
    ├── Signal_1: {asset=ES, strategy=ORB, direction=LONG, kelly_fraction=0.12, quality=0.008}
    ├── Signal_2: {asset=ES, strategy=SWING, direction=LONG, kelly_fraction=0.08, quality=0.005}
    ├── Signal_3: {asset=CL, strategy=ORB, direction=SHORT, kelly_fraction=0.15, quality=0.012}
    ├── Signal_4: {asset=NQ, strategy=0DTE, direction=LONG, kelly_fraction=0.05, quality=0.004}
    └── (N more signals)

ARBITRATION ENGINE (New — Layer 5):
    │
    ├── Step 1: CONFLICT RESOLUTION
    │       Detect and resolve conflicting signals on same asset
    │       (SC-03, SC-04, SC-10, SC-15, SC-17, SC-18)
    │
    ├── Step 2: EXPECTED VALUE RANKING
    │       Rank all surviving signals by risk-adjusted expected value
    │       Net of transaction costs, slippage, and capital lockup cost
    │
    ├── Step 3: PORTFOLIO-LEVEL RISK CHECK
    │       Compute portfolio-level VaR / correlation / concentration
    │       Apply cross-strategy risk limits (R-01 through R-16)
    │
    ├── Step 4: CAPITAL ALLOCATION
    │       Given: available capital, ranked signals, risk constraints
    │       Solve for: optimal allocation vector
    │       Subject to: per-account TSM constraints, margin, position limits
    │       Capital reservation: if AIM-06 (economic calendar) or a silo predicts
    │       a high-probability catalyst within the reservation_horizon (configurable,
    │       default 24h), withhold capital_reservation_pct (configurable, default 10%)
    │       of available capital from allocation. Reserved capital is released when the
    │       catalyst window passes or the catalyst signal expires.
    │       (Addresses S-15: capital reserved for future signal)
    │
    ├── Step 5: REALLOCATION COST-BENEFIT
    │       For each "new signal that requires liquidating an existing position":
    │       Compare: expected gain from new trade vs. cost of exiting + expected remaining gain from existing
    │       Include re-entry feasibility: re_entry_probability estimate (default 1.0 for
    │       liquid futures; reduced for illiquid instruments based on historical spread/depth).
    │       Only reallocate if net benefit × re_entry_probability > reallocation_threshold
    │       (SC-01, SC-05, SC-07, A-11; addresses L-08/L-09/L-10)
    │
    ├── Step 5B: CASCADE EVALUATION (second pass)
    │       After initial allocation, check: does taking trade A now make trade B viable
    │       that was previously rejected? (e.g., a hedge enables a larger directional bet)
    │       Re-run Steps 1-5 with updated portfolio state. Cap at 2 total passes to
    │       prevent infinite recursion. If second pass produces no new trades → done.
    │       (Addresses C-12: cascade signals)
    │
    └── Step 6: FINAL SIGNAL OUTPUT
            Surviving, sized, risk-checked signals → Block 6 → Command → GUI/API

OUTPUTS:
    ├── Selected trades with final position sizes (per user, per account)
    ├── Reallocation instructions (if any existing positions should be reduced)
    └── Rejected signals with rejection reasons (for trade outcome log)
```

## 4.3 Conflict Resolution Logic (Step 1)

For each conflict type from the taxonomy (Part 8):

### Signal Expiry Pre-Filter (C-13)
Before conflict resolution begins, all signals in the arbitration queue are checked against their strategy type's `signal_ttl` (from P3-D23). Any signal where `now() - signal_timestamp > signal_ttl` is removed from the queue and logged as EXPIRED in P3-D03 (trade outcome log, outcome = "SIGNAL_EXPIRED"). This prevents stale internal signals from competing with fresh ones.

### Same Asset, Same Direction, Multiple Strategies (C-03)
**Resolution:** Aggregate. Use the highest-quality signal's parameters. Kelly fraction is the maximum of individual Kelly fractions (not the sum — that would be double-counting edge).

### Same Asset, Opposite Direction, Multiple Strategies (C-04)
**Resolution:** Net the directional signals weighted by Kelly fraction × quality score. If the net direction has absolute value > threshold → take the trade in the net direction. If the net is below threshold → skip (strategies cancel out, no clear edge).

**[RESEARCH REQUIRED: Opposing Signal Aggregation]**
How should conflicting directional signals be combined? Simple weighted netting is intuitive but may not be optimal. The short-term signal may be more accurate for the next hour while the long-term signal is more accurate for the next week. Time-horizon-aware aggregation is needed.

**Research approach:** Review forecast combination literature (Timmermann, 2006), optimal pooling of forecasts with different horizons. Determine whether time-horizon-conditional combination outperforms simple netting.

### Conflicting Time Horizons (C-10)
**Resolution:** Allow coexistence. A short-term bearish ORB trade and a long-term bullish swing position on the same asset can coexist IF total net exposure is within risk limits. This is standard at institutional desks (day trading desk and position trading desk can have opposing views on the same asset).

**For Nomaan:** Implement as separate position slots per strategy_type. Net exposure is calculated for risk purposes but trades are managed independently per strategy.

### New High-Value Signal While Capital Is Deployed (C-07, SC-01, SC-05)
**Resolution:** Run the reallocation cost-benefit analysis (Step 5). Compute:

```
reallocation_benefit = expected_value(new_signal) - [exit_cost(existing_position) + forgone_value(existing_position)]

IF reallocation_benefit > reallocation_threshold:
    REALLOCATE (exit existing, enter new)
ELSE:
    HOLD (keep existing, skip new signal, log opportunity cost)
```

**[RESEARCH REQUIRED: Opportunity Cost Estimation]**
Computing `forgone_value(existing_position)` requires estimating the expected remaining return of the current trade. For an intraday trade with a TP and SL, this is tractable (conditional expectation given current P&L and time remaining). For a swing trade with no fixed exit, this requires a conditional expected return model.

**Research approach:** Review optimal stopping theory (Shiryaev, 1978), expected remaining life models for trading positions. Determine whether a simple heuristic (e.g., expected value decays linearly with holding time) is sufficient or whether a more sophisticated model is needed.

## 4.4 Expected Value Ranking (Step 2)

Each signal is ranked by a unified score:

```
arbitration_score(signal) = 
    kelly_fraction(signal)
    × quality_score(signal)
    × confidence_modifier(signal)
    × (1 - capital_lockup_penalty(signal))
    × (1 - correlation_penalty(signal, existing_portfolio))
    × (1 - fx_conversion_cost(signal))
    + hedging_value(signal, existing_portfolio)
```

Where:
- `kelly_fraction` — from Online Block 4 (strategy-specific Kelly)
- `quality_score` — from Online Block 5B quality gate
- `confidence_modifier` — aggregate confidence from all relevant AIMs and silos
- `capital_lockup_penalty` — penalty for strategies that lock capital for extended periods (reduces attractiveness of swing trades when intraday opportunities are available)
- `correlation_penalty` — penalty for signals that are correlated with existing positions (reduces concentration risk)
- `fx_conversion_cost` — penalty for signals requiring cross-currency capital conversion. Zero for same-currency trades (all current futures). Non-zero when capital must be converted (e.g., trading EUR-denominated instruments from a USD capital pool). Computed as: estimated round-trip FX spread + conversion fee. (Addresses S-12)
- `hedging_value` — **additive** (not multiplicative) term measuring the portfolio risk reduction from adding this position. Computed as: marginal VaR reduction × portfolio_size / position_cost. A signal with negative standalone EV (kelly_fraction ≈ 0) but positive hedging_value can survive arbitration if hedging_value > standalone loss. Requires portfolio risk computation from Step 3. (Addresses C-11, A-09)

**[RESEARCH REQUIRED: Hedging Value Computation — RR-22]**
How to quantify the portfolio risk reduction of a hedging position and convert it to an arbitration_score-compatible value. The hedging_value must be in the same units as the multiplicative portion of the score so they're comparable. Marginal contribution to portfolio VaR (Euler decomposition) is the standard institutional approach, but requires a full portfolio risk model.

**Research approach:** Review marginal risk contribution / Euler decomposition (Tasche, 1999; McNeil, Frey & Embrechts, 2005). For linear portfolios: closed-form solution using correlation matrix. For portfolios with options: simulation-based marginal VaR. Start with the linear case (futures only) and extend to non-linear when options are added (Phase 8).

**[RESEARCH REQUIRED: Capital Lockup Penalty Function]**
How should capital lockup duration be penalised? A linear penalty (1% per day locked) is simple but doesn't account for the option value of having capital available for future opportunities. The penalty should reflect the expected opportunity cost of capital being unavailable.

**Research approach:** Review real options theory applied to capital allocation. The penalty function should approximate the expected value of intraday opportunities foregone while capital is locked in a multi-day position. This requires historical analysis of opportunity arrival rates and quality distributions.

**[RESEARCH REQUIRED: Optimal Capital Reservation Ratio — RR-23]**
Step 4 reserves a configurable percentage of capital when a future catalyst is predicted (e.g., FOMC tomorrow). The question: **what is the optimal reservation ratio?** Too high → capital sits idle and misses current opportunities. Too low → insufficient capital available when the catalyst fires.

**Research approach:** Review cash management models (Miller-Orr, 1966), inventory theory applied to capital buffers. The optimal reservation depends on: (a) the expected signal quality of catalyst-driven trades vs. regular trades, (b) the frequency of catalyst events, (c) the historical hit rate of catalyst predictions. Start with a fixed 10% default and refine empirically using P1/P2 data on FOMC/earnings event returns vs. regular session returns.

## 4.5 Portfolio-Level Risk Aggregation (Step 3)

**[RESEARCH REQUIRED: Cross-Strategy Risk Aggregation]**
V1 computes risk per-asset, per-strategy. V3+ needs portfolio-level risk across all active positions across all strategy types. The challenges:

1. **Heterogeneous holding periods** — a 1-hour ORB trade and a 5-day swing trade have different risk profiles. How do you compute a meaningful portfolio VaR that combines both?
2. **Non-linear instruments** — if options strategies (0DTE) are included, portfolio risk is no longer additive. Greeks (delta, gamma, vega, theta) must be aggregated.
3. **Cross-asset correlations at different horizons** — the correlation between ES and CL is different at the 1-hour horizon vs. the 5-day horizon.

**Research approach:**
1. For linear instruments (futures): multi-horizon VaR using Christoffersen et al. (2012) dynamic conditional correlation at appropriate horizons per strategy type.
2. For non-linear instruments (options): portfolio Greeks aggregation using standard options risk analytics. Delta-equivalent exposure for comparison with linear positions.
3. For mixed portfolios: review RiskMetrics (1996) multi-asset VaR methodology and extensions for heterogeneous holding periods.

**Interim approach (pre-research):** Use the existing per-asset Kelly sizing with a heuristic portfolio-level drawdown limit. If total portfolio drawdown (across all strategies) exceeds X% of total capital, reduce all position sizes proportionally. This is crude but safe.

## 4.6 Per-Account TSM Integration (Step 4)

The TSM (Trading System Manager) layer already handles per-account constraints (prop firm rules, drawdown limits, daily loss limits, contract scaling). V3+ extends TSM to be strategy-aware:

```
TSM_V3 constraints:
    Original (V1):
        - max_daily_loss per account
        - trailing_max_loss per account  
        - contract_scaling_plan per account
        - consistency_rule per account
    
    New (V3+):
        - max_allocation_per_strategy_type per account
            (e.g., "no more than 40% of this account's capital in swing trades")
        - strategy_type_whitelist per account
            (e.g., "this Topstep XFA account only trades intraday strategies — no overnight holds")
        - holding_period_limit per account
            (e.g., "all positions must be flat by 16:10 ET" — Topstep rule, overrides swing strategies)
        - jurisdiction per account
            (e.g., "US_CFTC", "UK_FCA", "EU_ESMA"). Capital allocation respects
            jurisdiction boundaries — capital in a US-regulated account cannot fund
            trades in an EU-regulated account without explicit cross-jurisdiction
            transfer. (Addresses S-13: multi-jurisdiction capital)
```

**For Nomaan:** These are new optional fields in the TSM JSON schema (P3-D08). Existing TSM configs without these fields default to: no per-strategy limits, all strategy types allowed, no holding period override (strategy's own exit rules apply).

## 4.7 Handling All 32 Conflict Scenarios

The taxonomy defines 32 specific hard cases (SC-01 through SC-32). Here is the architectural resolution for each:

### Capital Arbitration Conflicts (SC-01 through SC-06)

| Scenario | Resolution | Module |
|----------|-----------|--------|
| SC-01: Multi-day trade open + 0DTE signal + insufficient capital | Reallocation cost-benefit (Step 5). Compare: remaining EV of multi-day trade vs. expected 0DTE gain minus exit cost. | Arbitration Engine Step 5 |
| SC-02: Three strategies signal, capital for one | Expected value ranking (Step 2). Take highest arbitration_score signal. | Arbitration Engine Step 2 |
| SC-03: Best signal is in a decaying strategy (BOCPD Level 2) | Apply decay penalty to arbitration_score. If decay-adjusted score still highest → take trade with reduced sizing. If not → skip. | Arbitration Engine Step 2 (decay modifier) |
| SC-04: User account constraints vs. system optimal | TSM constraints override system optimal. Per-account allocation respects prop firm rules regardless of system-level recommendation. | TSM V3 integration (Step 4) |
| SC-05: Multi-day trade at 80% TP + 0DTE appears | Compute forgone value (remaining ~20% TP × probability of reaching). If 0DTE expected value net of exit costs exceeds forgone value → reallocate. | Arbitration Engine Step 5 |
| SC-06: Silos provide conflicting signals | Each silo maps to a separate AIM. Conflicting AIM modifiers partially cancel. DMA weighting determines which silo has more influence based on historical track record. If residual signal is weak → quality gate filters it. | AIM aggregation (Block 3, existing) |

### Timing Conflicts (SC-07 through SC-11)

| Scenario | Resolution | Module |
|----------|-----------|--------|
| SC-07: Market open signal + spread widened at execution | AIM-12 (Dynamic Costs) already handles this. Cost modifier reduces position size or kills trade if slippage exceeds edge. V3+: no change needed. | AIM-12 (existing) |
| SC-08: Overnight event changes regime between signal generation and execution | Online Block 2 (regime computation) runs at session open with CURRENT data. The signal is generated AFTER regime update. If a pre-session overnight event changes the regime between Offline cycle and session open, the Online Block 2 regime computation reflects it. V3+: no change needed. | Online Block 2 (existing) |
| SC-09: 0DTE continuous signals vs. multi-day session-open signals | Different evaluation cadences feed into the same Arbitration Engine. Continuous signals arrive throughout the day; session-open signals arrive once. The Arbitration Engine processes all available signals at each evaluation point. | ContinuousEvaluator + Arbitration Engine |
| SC-10: Settlement delay blocks capital reuse | Track settlement state per position in P3-D03 (new field: `settlement_status`). Capital locked in settlement is excluded from available capital for new trades. Arbitration Engine sees reduced available capital. | Arbitration Engine Step 4 (available capital computation) |
| SC-11: Cross-timezone signals conflict | Each session (NY, LON, APAC) generates signals independently. The Arbitration Engine at each session open considers all outstanding signals and open positions. London's signal doesn't override NY's — they coexist and compete. | Multi-session evaluation (existing P3-IX-05) |

### Risk Cascade Conflicts (SC-12 through SC-16)

| Scenario | Resolution | Module |
|----------|-----------|--------|
| SC-12: Flash crash — all strategies signal opportunity but risk limits say reduce | Circuit breaker (Architecture Section 19.6) supersedes all signal generation. VIX > threshold → HALT_ALL_SIGNALS. Risk limits always override opportunity signals. | Circuit Breaker (existing) + Arbitration Engine Step 3 |
| SC-13: Correlated drawdown across strategy types | Portfolio-level drawdown monitoring (new). Per-strategy drawdowns are within limits but portfolio-level is not. → Reduce ALL position sizes proportionally. | Risk Aggregation (Step 3) |
| SC-14: Liquidation cascade (exiting one position pushes another below margin) | Margin pre-check before any reallocation. Arbitration Engine Step 5 computes the cascade effect BEFORE executing the exit. If cascade → abort reallocation. | Arbitration Engine Step 5 (cascade check) |
| SC-15: Model says "strong buy" but BOCPD says "decaying" | BOCPD signal reduces Kelly fraction (Level 2 autonomy). The "strong buy" signal proceeds with reduced sizing. If BOCPD is Level 3 → signals halted for that (asset, strategy_type). System design already handles this. | BOCPD integration (existing) |
| SC-16: Silo data contradicts price trend | The silo's signal feeds through AIM-N with DMA-learned weight. If the silo has historically been right when contradicting price → DMA weight is high → signal has influence. If it's historically been wrong → DMA weight is low → signal is dampened. No special handling needed. | DMA meta-learning (existing) |

### Multi-Asset / Multi-Strategy Conflicts (SC-17 through SC-20)

| Scenario | Resolution | Module |
|----------|-----------|--------|
| SC-17: Long ES futures + short SPY 0DTE call | Track net exposure across instruments. ES and SPY are ~0.99 correlated. Net delta = ES_delta + SPY_call_delta. If net exposure exceeds risk limit → reduce the smaller position. **[RESEARCH REQUIRED]** — options Greeks aggregation with futures for portfolio-level exposure. | Risk Aggregation (Step 3) + Greeks Module (new) |
| SC-18: Pairs trade open + new single-name signal on one leg | The pairs trade is a single strategy_type with 2 legs. The single-name signal is a different strategy_type. They coexist unless net exposure on the shared leg exceeds limits. Arbitration Engine tracks per-asset net exposure across all active strategy types. | Arbitration Engine Step 3 (net exposure) |
| SC-19: 10 strategies × 5 assets, correlation clusters | Compute correlation matrix across all active signals (not just assets — signals from different strategies on the same asset are correlated). Apply correlation penalty in Step 2. Group highly correlated signals and select the best from each cluster. **[RESEARCH REQUIRED]** — signal-level correlation estimation (vs. asset-level, which is simpler). | Arbitration Engine Step 2 (correlation penalty) |
| SC-20: One strategy outperforming, captain should increase allocation, but concentration risk | Define maximum single-strategy allocation cap (configurable per account in TSM V3). System can increase allocation up to the cap but not beyond. Cap is a risk management decision by Isaac. | TSM V3 (max_allocation_per_strategy_type) |

### External Data / Satellite Silo Conflicts (SC-21 through SC-24)

| Scenario | Resolution | Module |
|----------|-----------|--------|
| SC-21: Crop damage silo (bullish) vs. rain recovery silo (bearish) | Two different silo-backed AIMs with conflicting modifiers. DMA meta-learning resolves based on historical accuracy. If both are new with low confidence → they partially cancel → net modifier near 1.0 (neutral). This is correct behaviour — low information → no strong modification. | DMA (existing) |
| SC-22: Geopolitical silo vs. NLP sentiment silo | Same as SC-21. Two AIMs with conflicting signals. DMA resolves. | DMA (existing) |
| SC-23: Blockchain silo (bullish crypto) vs. macro silo (bearish risk assets) | Same mechanism. These are different AIM instances on potentially different assets. If they affect the same asset → DMA resolves. If they affect different assets → no conflict (independent). | DMA (existing) + per-asset separation |
| SC-24: High-confidence stale silo signal vs. fresh market data | Staleness check in the silo AIM. If `now() - timestamp > staleness_limit` → AIM outputs 1.0 (neutral), ignoring the stale signal. Fresh market data dominates. This is enforced at the AIM level before DMA even sees it. | Silo AIM staleness check (Section 3.5.2) |

### Unprecedented / Novel Situations (SC-25 through SC-32)

| Scenario | Resolution | Module |
|----------|-----------|--------|
| SC-25: New asset class, no history | Cold-start protocol (Part 6). P1/P2 must complete before Captain trades it. During P1/P2 validation, Captain has no signal for this asset. After validation → normal warm-up. | Warm-Up Policy (existing Section 8) |
| SC-26: Market structure change (24/7 trading) | Session definitions in P3-D00 are configurable per asset. Adding "24/7" means adding more session evaluation points. Online evaluator handles multiple sessions already (NY/LON/APAC). Add sessions. | P3-D00 session config + Online evaluator (existing) |
| SC-27: Strategy class banned by regulation | Set `status = ARCHIVED` in P3-D23 (strategy_type_register). All signals for that strategy_type are immediately halted. Existing positions are closed per exit rules. Capital freed for other strategies. | Strategy Type Registry + Tiered Autonomy |
| SC-28: AI agents trading the same patterns (alpha decay) | BOCPD detects decay in strategy performance (win rate declining, payoff ratio shifting). Normal Level 2/3 response: reduce sizing → halt signals → P1/P2 re-run. The CAUSE of the decay doesn't matter to the system — it detects the EFFECT. | BOCPD/CUSUM (existing) |
| SC-29: Silo signal surpasses price-based strategies | DMA naturally increases the silo-backed AIM's weight as it outperforms. If the AIM's weight exceeds the dominance threshold (0.30), Offline Block 9 flags it for human review. This is correct — if a single AIM dominates, there's concentration risk in intelligence sources. | DMA + System Health Diagnostic (existing Offline Block 9) |
| SC-30: Quantum competitor neutralises advantage | Alpha decay detected by BOCPD. Same as SC-28 — the system responds to the effect, not the cause. | BOCPD/CUSUM (existing) |
| SC-31: Infrastructure event knocks out data feeds | Circuit breaker + graceful degradation. Multiple DATA_HOLD → circuit breaker activates. Individual data loss → affected AIM outputs 1.0 (neutral). | Circuit Breaker + AIM graceful degradation (existing) |
| SC-32: Strategy alpha is regulatory grey area | Set strategy status to HALTED in P3-D23. ADMIN reviews. If cleared → resume. If not → ARCHIVE. Meanwhile, positions are closed per exit rules. The system can halt and resume any individual strategy type without affecting others. | Strategy Type Registry + ADMIN workflow |

---

# PART 5 — EXECUTION ABSTRACTION LAYER

## 5.1 Current State (V1)

Captain Command Block 3 has an API adapter interface:
```
APIAdapter:
    connect() → status
    send_signal() → order_id
    receive_fill() → fill_price, fill_time
    get_account_status() → balance, equity, drawdown
    disconnect() → void
```

This handles standard broker/prop firm connections. V3+ extends this to handle additional execution mechanisms from the taxonomy (Part 5).

## 5.2 Venue Abstraction

| Venue Type | V3+ Support Level | Implementation |
|------------|-------------------|----------------|
| Lit exchanges (CME, NYSE, etc.) | FULL — via existing broker API adapters | No change |
| Dark pools | FUTURE — requires DMA broker connectivity | New adapter type when needed |
| OTC bilateral | FUTURE — requires counterparty management | New adapter type + counterparty registry |
| DEX (decentralized exchanges) | FUTURE — requires smart contract interaction | New adapter type + wallet management |
| RFQ platforms | FUTURE — requires quote negotiation protocol | New adapter type |

**For Nomaan:** Each venue type is a new Python class inheriting from `APIAdapter`. The interface doesn't change — only the internal implementation differs. A DEX adapter would use Web3 libraries internally but still expose `send_signal()` → `order_id` and `receive_fill()` → `fill_price`.

## 5.3 Execution Algorithm Integration

V1 sends simple signals (direction, size, TP, SL). V3+ may need smarter execution:

| Execution Algo | When Needed | Implementation |
|----------------|-------------|----------------|
| Simple (market/limit) | Current strategies, small positions | V1 adapter, no change |
| TWAP/VWAP | Large positions (multiple contracts), prop account scaling | New execution module in Command |
| Iceberg | Large positions where showing full size moves the market | Adapter-level, broker supports |
| Smart order routing | Multi-venue, best execution obligations | FUTURE — requires DMA connectivity |

## 5.4 Tax-Aware Lot Selection (Deferred)

When closing partial positions in taxable accounts (not prop firm accounts), the system should select which tax lots to close based on tax impact. Three methods:
- **FIFO** (First In, First Out) — default, simplest, required by some jurisdictions
- **LIFO** (Last In, First Out) — may minimize short-term gains in some cases
- **Specific identification** — select the lot that minimizes tax liability

**Status: DEFERRED.** Not relevant for current prop firm accounts (Topstep, IBKR) where tax lots don't affect account-level P&L constraints. Implement when taxable personal accounts are added. The implementation is a Command Block 3 execution detail — no architectural change needed, just a lot selector added to the position closing function. (Addresses L-14 and E-10.)

**[RESEARCH REQUIRED: Optimal Execution for Futures Strategies]**
At current scale (1-5 contracts ES), execution is trivial — market orders fill instantly with minimal slippage. But if position sizes grow (prop account scaling, multi-asset), execution quality matters. The question: **at what position size does execution algorithm selection materially impact PnL on ES, CL, and NQ?** This determines when to invest in smart execution vs. staying with simple orders.

**Research approach:** Review Almgren & Chriss (2001) optimal execution framework. Compute the market impact threshold for ES/CL/NQ at various contract sizes. If all current strategies stay below this threshold, execution optimisation is deferred.

---

# PART 6 — DATA INTEGRATION FRAMEWORK

## 6.1 Existing Data Path (V1)

```
Market data → QC data feeds → Online Block 1 → AIMs + strategy evaluation
Alternative data → REST/FILE adapters → AIM-04 to AIM-15
```

## 6.2 V3+ Extended Data Path

```
Market data → QC data feeds / broker API → Online Block 1 → strategy evaluation
                                              ↓
Silo outputs → REST/WebSocket adapters → Silo AIM translator → AIM aggregation
                                              ↓
Alternative data → REST/FILE adapters → Existing AIMs → AIM aggregation
                                              ↓
Event data → Redis pub/sub → EventEvaluator → event-driven strategies
```

**New data types requiring new adapters:**

| Data Type | Taxonomy Ref | Adapter Type | Frequency | Notes |
|-----------|-------------|-------------|-----------|-------|
| Silo signals | Part 6 | REST or WebSocket | Varies by silo | SiloSignal schema |
| Options chain (extended) | Part 3.1 | REST | Pre-session + intraday | For 0DTE strategies: full Greeks surface |
| On-chain data | Part 3.10 | WebSocket | Streaming | For crypto strategies |
| Prediction market | Part 2.10 | REST | Hourly-daily | For event-driven strategies |
| Economic nowcasting | Part 3.4 | REST | Daily | From macro silo |
| Satellite imagery scores | Part 3.6 | REST | Daily-weekly | From satellite silo |
| Geopolitical risk scores | Part 3.5 | REST | Daily | From geopolitical silo |

**For Nomaan:** Each new data type is a new entry in P3-D00's `data_sources` map per asset. The adapter types (REST, WebSocket, FILE) already exist. New data types require:
1. A schema definition (what fields the response contains)
2. A validation function (does the response match the schema)
3. A routing rule (which AIM or evaluator consumes this data)

These are config-driven, not code-driven. Nomaan writes the adapter config, the data ingestion framework handles the rest.

## 6.3 Data Quality Framework

**[RESEARCH REQUIRED: Alternative Data Quality Metrics]**
Market data quality is well-understood (completeness, timeliness, accuracy). Alternative data from silos has different quality dimensions:

1. **Coverage** — does the silo cover the asset we're trading? (A corn crop model doesn't help with ES)
2. **Latency** — how old is the signal by the time Captain receives it?
3. **Predictive decay** — how quickly does the signal's predictive power fade?
4. **Revisions** — does the silo revise historical signals? (Many macro data sources revise)
5. **Survivorship in the signal** — was the model trained on data that includes look-ahead bias?

**Research approach:** Review Lopez de Prado (2018) on alternative data quality assessment. Develop a data quality scorecard for each silo that feeds into the DMA meta-learning as a prior (start with higher skepticism for low-quality data sources).

---

# PART 7 — INSTRUMENT UNIVERSE EXTENSION

## 7.1 Current State

V1 trades ES E-mini futures only. The architecture supports adding assets via the onboarding workflow (Architecture Section 15.2).

## 7.2 Instrument Type Support Matrix

The taxonomy lists ~120 instrument types across 11 categories. Here is the architectural support level:

| Category | Taxonomy Ref | V3+ Support | What's Needed |
|----------|-------------|-------------|---------------|
| **Equity futures** (ES, NQ, YM, RTY) | 2.2 | READY | Onboarding workflow only — same instrument type as ES |
| **Commodity futures** (CL, NG, GC, SI, HG, ZC, ZS, ZW) | 2.4 | READY | Different session hours, different point values. Config per asset in P3-D00. Roll calendars vary by commodity. |
| **FX futures** (6E, 6J, 6B, 6A) | 2.5 | READY | Same mechanism as equity futures |
| **Interest rate futures** (ZB, ZN, ZF, ZT, GE) | 2.1 | READY | Different quoting conventions (ticks in 32nds for bonds). Adapter needs conversion. |
| **Micro futures** (MES, MNQ, MCL) | 2.2 | READY | Smaller point values, lower margin. Config in P3-D00. |
| **Equity options** | 2.2 | FUTURE | Requires Greeks computation, options-specific P1 validation, multi-leg entry. **[RESEARCH REQUIRED]** — options strategy validation through P1 (different statistical framework than directional futures). |
| **0DTE options** | 2.2 | FUTURE | Same as equity options plus intraday theta decay modeling. **[RESEARCH REQUIRED]** — real-time Greeks computation, gamma risk management for 0DTE positions. |
| **Crypto spot/futures** | 2.6 | FUTURE | Requires DEX adapter or crypto exchange adapter. 24/7 session hours. **[RESEARCH REQUIRED]** — crypto market microstructure for ORB-type strategies (24/7 market has no "opening range" in the traditional sense). |
| **ETFs** | 2.1 | FUTURE | Requires equity broker adapter. Different margin rules, different settlement (T+1). |
| **Individual equities** | 2.1 | FUTURE | Same as ETFs but with universe management (stock selection). **[RESEARCH REQUIRED]** — stock universe construction and maintenance for systematic strategies. |
| **OTC derivatives** | 2.3 | DEFERRED | Fundamentally different execution model. Requires counterparty management, ISDA agreements. Not relevant at current scale. |
| **Real estate / alternatives** | 2.7 | DEFERRED | Different asset class entirely. Accommodated structurally but not implemented. |
| **Digital assets (DeFi, NFTs)** | 2.6 | DEFERRED | Requires blockchain integration. Accommodated structurally. |
| **Environmental instruments** | 2.8 | DEFERRED | Carbon credits etc. Low liquidity, specialised exchanges. |
| **Insurance-linked** | 2.9 | DEFERRED | Cat bonds etc. Completely different risk framework. |
| **Exotic / frontier** | 2.10 | DEFERRED | Prediction markets, compute futures, etc. Accommodated structurally. |
| **Synthetic / constructed** | 2.11 | DEFERRED | Custom baskets, synthetic positions. Accommodated structurally. |

**For Nomaan:** The onboarding workflow (Architecture Section 15.2) handles instrument expansion. Each new instrument type may need:
1. A new entry in P3-D00 with instrument-specific config (point_value, tick_size, margin, session_hours)
2. P1/P2 validation runs for that instrument
3. Potentially a new data source adapter if the broker doesn't support that instrument type

No changes to Captain's core logic. The strategy-agnostic design handles different instruments through configuration, not code changes.

---

# PART 8 — MODEL METHODOLOGY PLUGGABILITY

## 8.1 Current Models in V1

| Model | Used Where | Purpose |
|-------|-----------|---------|
| XGBoost | Program 2 Block 3 | Regime classification |
| Logistic Regression | Program 2 Block 3 (fallback) | Regime classification |
| EWMA | Program 3 Offline Block 8 | Win rate / payoff ratio tracking |
| DMA (Dynamic Model Averaging) | Program 3 Offline Block 1 | AIM meta-learning |
| MoE (Mixture of Experts) | Program 3 Online Block 3 | AIM aggregation gating |
| BOCPD (Bayesian Online Change Point Detection) | Program 3 Offline Block 2 | Decay detection |
| CUSUM | Program 3 Offline Block 2 | Drift detection |
| Kelly criterion | Program 3 Offline Block 8 / Online Block 4 | Position sizing |

## 8.2 Model Methodology Extension Points

The taxonomy identifies 13 methodology families (~150 distinct methods). The system does not need to implement all of them. It needs to ensure that any model can be plugged into the correct slot:

| Slot | Interface | Current Model | Can Be Replaced With |
|------|-----------|---------------|---------------------|
| Regime classification | `classify(features) → {regime: label, probability: float}` | XGBoost | Any classifier: Random Forest, LSTM, HMM, Transformer, GMM, etc. |
| AIM model | `predict(features) → modifier(0.5-1.5)` | Various per AIM | Any model that outputs a bounded continuous value |
| AIM meta-learning | `update_weights(outcomes) → weight_vector` | DMA | Bayesian Model Averaging, Thompson Sampling, EXP3, softmax bandit |
| Decay detection | `detect(stream) → changepoint_probability` | BOCPD | CUSUM (already dual), PELT, kernel methods, neural CPD |
| Position sizing | `size(edge, odds, constraints) → fraction` | Kelly | Risk parity, equal weight, volatility targeting, CVaR optimisation |
| Silo models | `process(raw_data) → SiloSignal` | N/A (silos are external) | Any model — the system doesn't care what runs inside a silo |

**For Nomaan:** Model replacement is a configuration change + new model class. Example: replacing XGBoost regime classifier with an LSTM:
1. Write `LSTMRegimeClassifier` class implementing `classify(features) → {regime, probability}`
2. Register it in the regime model config
3. Run P2 validation with the new classifier
4. If it passes → deploy

No changes to Captain's Online or Offline blocks. They consume the interface, not the implementation.

**[RESEARCH REQUIRED: Model Selection for Regime Classification]**
The current XGBoost regime classifier was chosen pragmatically. Is it optimal? Literature suggests:
- HMMs are the standard for financial regime detection (Hamilton, 1989)
- Transformer architectures show promise for time-series regime detection (recent, limited evidence)
- Gaussian mixture models with time-varying parameters (flexible but overfitting-prone)

**Research approach:** Compare XGBoost, HMM, and LSTM regime classifiers on the same sample using P2's validation framework. Measure: classification accuracy, transition detection speed, false positive rate, computational cost. The winner replaces XGBoost in P2 Block 3.

---

# PART 9 — REGULATORY ADAPTATION LAYER

## 9.1 Current State

Architecture Section 18 defines the current regulatory position (NOT algorithmic trading, compliance gate for future auto-execution). This is sufficient for V1.

## 9.2 V3+ Regulatory Considerations

| Change | Regulatory Impact | Architectural Response |
|--------|-------------------|----------------------|
| Multi-asset (adding NQ, CL to ES) | No change — same FCM relationship, same CFTC position limits | Add per-asset position limits to P3-D00 |
| Options strategies (0DTE) | FINRA/SEC jurisdiction if equity options via broker. Different from CFTC futures. | Separate compliance gate per instrument class in Command Block 3.4 |
| Crypto strategies | Varies wildly by jurisdiction. US: CFTC for futures, SEC for spot (pending). UK: FCA registration. | Jurisdiction-specific compliance flag per asset in P3-D00 |
| Automated execution (API trading) | Triggers full RTS 6 regime (11 requirements per Architecture Section 18.2) | Existing compliance gate handles this. No V3+ change needed. |
| Multi-user with external traders | Potential investment advisor / fund manager registration depending on fee structure | Legal review before V2 multi-user launch |
| Cross-border trading | MiFID II passporting (EU), equivalence (UK-EU), bilateral agreements | Per-jurisdiction flags in P3-D00 |

**[RESEARCH REQUIRED: Regulatory Classification for Multi-Strategy + Alternative Data]**
Using satellite silo data (satellite imagery, weather models) to generate trading signals may trigger additional regulatory considerations:
1. Could satellite-derived signals constitute "inside information" under MAR? (Likely no — satellite data is publicly acquirable. But untested in court.)
2. Do alternative data usage disclosures apply? (ESMA has issued guidance on "algorithmic data sourcing" but it's not yet codified.)
3. If the system uses NLP to process central bank communications before they're publicly released (e.g., early text leaks), that IS market abuse. The system must have a data source legitimacy check.

**Research approach:** Review ESMA guidance on alternative data in algorithmic trading. Review SEC guidance on satellite imagery and web scraping for investment decisions (2020 no-action letters). Document a data source legitimacy policy.

---

# PART 10 — COLD-START, ONBOARDING & LIFECYCLE

## 10.1 New Strategy Type Onboarding

| Step | Action | Duration | Dependencies |
|------|--------|----------|-------------|
| 1 | Isaac identifies new strategy type through research | Varies | Research output |
| 2 | Isaac documents strategy as experiment proposal | 1-2 days | Experiment Design skill |
| 3 | Nomaan implements strategy in QC (P1 format) | 1-2 weeks | Strategy spec |
| 4 | P1 validation on Sample 1 → OO scores | Hours (compute) | P1 pipeline |
| 5 | P2 regime-conditioned selection | Hours (compute) | P2 pipeline |
| 6 | Register in P3-D23 (strategy_type_register) | Minutes | P1/P2 outputs |
| 7 | Captain warm-up (20+ trades with strategy data) | Weeks-months (depends on trade frequency) | Historical data from P1/P2 |
| 8 | Strategy generates live signals | Ongoing | Warm-up complete |

## 10.2 New Satellite Silo Onboarding

| Step | Action | Duration | Dependencies |
|------|--------|----------|-------------|
| 1 | Isaac identifies data source through research | Varies | Research output |
| 2 | Silo developer builds the silo program | Weeks-months | Domain expertise |
| 3 | Silo implements SiloSignal output schema | Days | Schema spec |
| 4 | Silo deployed on independent infrastructure | Days | Infrastructure |
| 5 | Nomaan creates AIM-N class + adapter config | 1-2 days | Silo endpoint |
| 6 | AIM-N enters WARM_UP (modifier = 1.0, no influence) | Automatic | Config |
| 7 | DMA begins learning AIM-N weight after 50 trades | Weeks-months | Trade volume |
| 8 | AIM-N contributes to signals (if weight > threshold) | Ongoing | DMA convergence |

**[RESEARCH REQUIRED: Warm-Up Acceleration for New Silos]**
50 trades may take weeks or months to accumulate. During this time, the silo has no influence even if it's producing excellent signals. Can we accelerate warm-up using historical data?

**Research approach:** This maps to Edge Improvement Plan Opportunity #4 (Warm-Up Acceleration via Historical Bootstrapping). Review how to backfill silo signals against historical market data to pre-train DMA weights. Risk: look-ahead bias if the silo model was trained on data that overlaps with the backfill period. Need a clean out-of-sample protocol.

## 10.3 Strategy Lifecycle States

```
PROPOSED → VALIDATING → WARM_UP → ACTIVE → DECAYING → HALTED → ARCHIVED
                                     ↑                    │
                                     └────── RE-VALIDATE ──┘
```

| State | Description | Signal Generation |
|-------|-------------|-------------------|
| PROPOSED | Strategy identified, not yet validated | None |
| VALIDATING | Running through P1/P2 | None |
| WARM_UP | P1/P2 passed, accumulating EWMA/BOCPD baseline | None (modifier = 1.0) |
| ACTIVE | Generating signals | Yes |
| DECAYING | BOCPD Level 2 detected | Yes, with reduced sizing |
| HALTED | BOCPD Level 3 sustained | None — awaiting P1/P2 re-run |
| ARCHIVED | Strategy retired (0-weighted, no computation cost) | None |

## 10.4 New Asset Onboarding

The existing onboarding workflow (Architecture Section 15.2) handles this. V3+ adds:
- Step 0 (new): Check P3-D23 for which strategy types are compatible with this asset type
- Step 1 (modified): Run P1/P2 for each compatible strategy type, not just one
- Step 5 (modified): Warm-up is per (asset, strategy_type), not just per asset

---

# PART 11 — GRACEFUL DEGRADATION & FAULT TOLERANCE

## 11.1 Failure Hierarchy

V1 already defines graceful degradation for individual component failures (Architecture Section 10). V3+ extends this to handle multi-component and silo failures:

| Failure | V1 Response | V3+ Extension |
|---------|-------------|---------------|
| Single AIM failure | Modifier = 1.0, others continue | Same — applies to silo-backed AIMs identically |
| All AIMs fail | Base Kelly, no modifiers | Same |
| Single silo offline | N/A | AIM-N = 1.0 (neutral). Other silos and AIMs continue. |
| All silos offline | N/A | All silo-backed AIMs = 1.0. System operates on market-data-only AIMs (AIM-01 to AIM-15). Performance may degrade but system continues. |
| Arbitration engine failure | N/A | Fall back to V1 behaviour: single-strategy per asset, Block 5 trade selection with correlation adjustment |
| ContinuousEvaluator failure | N/A | Only session-open signals generated. Continuous strategies miss intraday opportunities but no incorrect signals. |
| EventEvaluator failure | N/A | Event-driven strategies inactive. Session-open and continuous strategies unaffected. |
| Strategy type registry (P3-D23) corrupt | N/A | Fall back to default strategy type ("PRIMARY") for all assets. Equivalent to V1 behaviour. |

**Design principle:** Every V3+ addition degrades to V1 behaviour on failure. V1 is always the safe fallback.

---

# PART 12 — CONSOLIDATED RESEARCH REQUIREMENT REGISTER

Every **[RESEARCH REQUIRED]** flag from this document, consolidated for reference:

| # | Topic | Where in This Doc | What's Needed | Priority | Estimated Effort |
|---|-------|-------------------|--------------|----------|-----------------|
| RR-01 | Multi-Horizon Kelly Sizing | Part 2.3 | Framework for optimal capital allocation across strategies with different turnover rates. Literature: Thorp (2006), MacLean-Ziemba (2011), Merton portfolio problem. | HIGH — blocks multi-strategy capital allocation | 2-3 papers + experiment proposal |
| RR-02 | Cross-Frequency Correlation Estimation | Part 2.3 | Method for computing correlation between return series at different sampling rates. Literature: MF-VAR, MIDAS, Hayashi-Yoshida estimator. | HIGH — blocks cross-strategy risk aggregation | 1-2 papers + empirical test |
| RR-03 | Continuous Evaluation Signal Quality Calibration | Part 2.4 | Quality gate parameters for continuous (intraday) signals vs. session-open signals. Requires at least one continuous strategy validated through P1. | MEDIUM — blocks continuous strategy deployment | Empirical analysis after P1 validation |
| RR-04 | Event-Driven Strategy Validation Through P1 | Part 2.4 | Modified P1 validation for small-sample, clustered trade distributions (e.g., 8 FOMC trades/year). Literature: White's Reality Check, Hansen's SPA test. | MEDIUM — blocks event-driven strategy deployment | 2-3 papers + P1 methodology extension |
| RR-05 | Opposing Signal Aggregation | Part 4.3 | How to combine conflicting directional signals from strategies with different time horizons. Literature: forecast combination (Timmermann 2006). | MEDIUM — affects conflict resolution quality | 1-2 papers |
| RR-06 | Opportunity Cost Estimation | Part 4.3 | Model for estimating expected remaining return of an open position (for reallocation decisions). Literature: optimal stopping theory (Shiryaev). | MEDIUM — affects reallocation quality | 1-2 papers + heuristic development |
| RR-07 | Capital Lockup Penalty Function | Part 4.4 | Penalty function for strategies that lock capital for extended periods. Literature: real options theory. | LOW — can start with simple linear penalty | 1 paper + calibration |
| RR-08 | Cross-Strategy Risk Aggregation | Part 4.5 | Portfolio-level VaR across strategies with heterogeneous holding periods and potentially non-linear instruments. Literature: Christoffersen (2012), RiskMetrics. | HIGH — blocks portfolio-level risk management | 3-4 papers + implementation |
| RR-09 | Optimal Execution for Futures | Part 5.3 | Market impact thresholds for ES/CL/NQ at various contract sizes. Literature: Almgren & Chriss (2001). | LOW — only relevant at larger scale | 1 paper + empirical test |
| RR-10 | Cross-Domain Confidence Calibration | Part 3.4 | Calibrating confidence scores from heterogeneous silo domains. Literature: Gneiting & Raftery (2007), Kuleshov (2018). | MEDIUM — affects silo integration quality | 2 papers + calibration methodology |
| RR-11 | Geopolitical Risk Signal Value | Part 3.6 | Predictive power of GPR indices for intraday futures trading. | LOW — geopolitical silo is MEDIUM priority | Literature scan |
| RR-12 | Weather → Commodity Price Transmission | Part 3.6 | Lag structure of weather signals on commodity futures prices. | LOW — weather silo is MEDIUM priority | Literature scan |
| RR-13 | Satellite Imagery Alpha in Futures | Part 3.6 | Applicability of satellite-derived signals (storage fills, crop health) to futures markets vs. equities. | LOW — satellite silo is MEDIUM priority | Literature scan |
| RR-14 | Alternative Data Quality Metrics | Part 6.3 | Data quality scorecard for alternative/silo data sources. Literature: Lopez de Prado (2018). | MEDIUM — needed before any silo goes live | 1 paper + framework development |
| RR-15 | Options Strategy Validation Through P1 | Part 7.2 | P1 validation methodology for options strategies (Greeks-based, non-linear payoffs). Different statistical framework than directional futures. | MEDIUM — blocks options strategies | 2-3 papers + P1 methodology extension |
| RR-16 | Crypto Market Microstructure for ORB | Part 7.2 | Whether opening range breakout concepts apply to 24/7 crypto markets (no traditional "opening range"). | LOW — crypto is FUTURE priority | Literature scan |
| RR-17 | Model Selection for Regime Classification | Part 8.2 | Comparative evaluation of XGBoost vs. HMM vs. LSTM for financial regime detection. | MEDIUM — potential P2 improvement | 2-3 papers + empirical comparison |
| RR-18 | Regulatory Classification for Alt Data | Part 9.2 | Legal review of alternative data usage under MAR, ESMA guidance, SEC no-action letters. | MEDIUM — needed before silo deployment | Legal/regulatory review |
| RR-19 | Warm-Up Acceleration for New Silos | Part 10.2 | Historical backfill of silo signals for pre-training DMA weights without look-ahead bias. Maps to Edge Improvement Plan Opportunity #4. | MEDIUM — improves silo onboarding speed | Cross-reference with EIP #4 |
| RR-20 | Portfolio Greeks Aggregation | Part 4.7 (SC-17) | Aggregating options Greeks with futures delta for portfolio-level net exposure. | MEDIUM — blocks options + futures portfolio | Standard options risk analytics |
| RR-21 | Signal-Level Correlation Estimation | Part 4.7 (SC-19) | Estimating correlation between signals (not just assets) from different strategies. | LOW — can start with asset-level proxy | Novel methodology needed |
| RR-22 | Hedging Value Computation | Part 4.4 | How to quantify portfolio risk reduction from a hedging position and convert to arbitration_score-compatible units. Literature: Euler decomposition (Tasche 1999), marginal risk contribution (McNeil, Frey & Embrechts 2005). | MEDIUM — needed when options or paired strategies added | 1-2 papers + implementation |
| RR-23 | Optimal Capital Reservation Ratio | Part 4.4 | What percentage of capital to reserve for predicted future catalysts. Literature: Miller-Orr (1966) cash management, inventory theory. | LOW — start with fixed 10% default and refine | 1 paper + empirical calibration |

---

# PART 13 — IMPLEMENTATION ROADMAP

## 13.1 Phase Sequencing

The upgrade is not one big deployment. It's a sequence of phases, each building on the last:

| Phase | What Gets Added | Prerequisites | Estimated Dev Effort |
|-------|----------------|---------------|---------------------|
| **Phase 0 (Current)** | V1 system deployed and operational | Current build (Nomaan) | In progress |
| **Phase 1** | Multi-asset expansion (NQ, CL alongside ES) | V1 operational | LOW — onboarding workflow only, no code changes |
| **Phase 2** | Strategy Type Registry (P3-D23) + multi-strategy data model extensions | V1 operational | MEDIUM — new dataset, field additions to P3-D03/D04/D05/D12 |
| **Phase 3** | Capital Arbitration Engine (basic — expected value ranking + conflict resolution) | Phase 2 complete | MEDIUM — new module alongside Block 5 |
| **Phase 4** | ContinuousEvaluator + EventEvaluator | Phase 2 complete | MEDIUM — new modules in Online |
| **Phase 5** | First satellite silo integration (NLP/Sentiment or Macro Nowcasting) | Phase 2 complete + silo built | MEDIUM — new AIM class + adapter config |
| **Phase 6** | Portfolio-level risk aggregation | Phase 3 complete + RR-08 research | HIGH — requires research completion |
| **Phase 7** | Multi-horizon Kelly (cross-strategy sizing) | Phase 3 complete + RR-01/RR-02 research | HIGH — requires research completion |
| **Phase 8** | Options strategy support (0DTE) | Phase 4 complete + RR-15 research | HIGH — requires research + new P1 validation |
| **Phase 9** | Additional silo integrations | Phase 5 complete + per-silo research | MEDIUM per silo |
| **Phase 10** | Advanced execution (TWAP/VWAP, smart routing) | Phase 6 complete + RR-09 research | LOW-MEDIUM — only if scale demands |

## 13.2 Research Dependencies

```
Research required BEFORE implementation:

Phase 3 (basic arbitration):  None — can use heuristic ranking
Phase 4 (continuous eval):    RR-03 (quality calibration) — can defer, use session-open calibration initially
Phase 5 (first silo):         RR-10 (confidence calibration) — can defer, let DMA learn
Phase 6 (risk aggregation):   RR-08 (REQUIRED — no safe heuristic for multi-horizon VaR)
Phase 7 (multi-horizon Kelly): RR-01, RR-02 (REQUIRED — no safe heuristic for multi-frequency Kelly)
Phase 8 (options):            RR-15, RR-20 (REQUIRED — options risk is non-linear, can't approximate)
```

**Phases 1-5 can proceed without completing any research.** Heuristic fallbacks exist for early phases. Phases 6-8 are research-gated — do not proceed without completing the flagged research items.

## 13.3 What Isaac Should Research First

Given the phase sequencing, the highest-priority research items are:

1. **RR-01 (Multi-Horizon Kelly)** and **RR-02 (Cross-Frequency Correlation)** — these gate Phase 7, which is the critical upgrade for multi-strategy capital allocation. Without this, the system can run multiple strategies but can't optimally size across them.

2. **RR-08 (Cross-Strategy Risk Aggregation)** — this gates Phase 6, which is portfolio-level risk management. Without this, the system uses a crude portfolio drawdown limit. Acceptable but not optimal.

3. **RR-17 (Regime Classification Model Selection)** — this is a potential improvement to the existing P2 pipeline. Can be researched in parallel with Phases 1-3.

Everything else (RR-03 through RR-07, RR-09 through RR-16, RR-18 through RR-23) can be researched when the relevant phase approaches.

---

# APPENDIX A — TAXONOMY COVERAGE MATRIX

Confirming that all 12 parts of the Exhaustive Strategy Taxonomy are architecturally addressed:

| Taxonomy Part | Coverage in This Plan | Resolution |
|---------------|----------------------|------------|
| Part 1: Strategy Classes | Part 2 (Strategy Abstraction Layer) | All 9 holding period tiers mapped. Active/Ready/Future/Deferred status per tier. |
| Part 2: Asset/Instrument Universe | Part 7 (Instrument Universe Extension) | All 11 categories mapped. Support level per category. |
| Part 3: Data/Signal Sources | Part 6 (Data Integration Framework) + Part 3 (Satellite Silos) | All 11 domains covered via silo architecture or existing adapters. |
| Part 4: Model/Methodology | Part 8 (Model Methodology Pluggability) | All 13 families accommodated via pluggable interfaces. |
| Part 5: Execution/Infrastructure | Part 5 (Execution Abstraction Layer) | All 5 dimensions mapped. Adapter-based extension. |
| Part 6: Satellite Silos | Part 3 (Satellite Silo Integration) | All 11 silo domains specified with AIM mapping and lifecycle. |
| Part 7: Capital/Portfolio States | Part 4 (Capital Arbitration Engine) | All 60+ states addressed: deployment states via arbitration Steps 1-6 (incl. capital reservation for S-15, FX cost for S-12, jurisdiction tagging for S-13); signal conflicts via pre-filter (C-13 expiry) + Steps 1-3 (C-03/04/10/11/12); liquidation states via Step 5 (incl. re-entry probability for L-08/09/10, tax lot selection deferred for L-14); risk states via Step 3 + circuit breaker + basis monitor (R-13); arbitration states via Steps 2-4 + hedging_value (A-09); external states via existing V1 error handling. |
| Part 8: Conflict Scenarios | Part 4.7 | All 32 scenarios resolved with specific module assignment. |
| Part 9: Regulatory/Jurisdictional | Part 9 (Regulatory Adaptation Layer) | Per-jurisdiction flags, compliance gates, data legitimacy policy. |
| Part 10: Frontier/Speculative | Parts 2, 7 (DEFERRED status) | Structurally accommodated — interfaces defined, implementation deferred. |
| Part 11: Summary Statistics | This appendix | All 750+ items accounted for. |
| Part 12: Architectural Implications | Part 1 (Philosophy) | All 10 implications operationalised. |

---

*Document generated 2026-03-09. Research document for Isaac. Not a specification for Nomaan until individual phases are approved and research requirements are met.*
