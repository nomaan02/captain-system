# Captain System — Auxiliary Intelligence Module (AIM) Registry

**Created:** 2026-03-01
**Status:** Living document — updated as modules are researched and built
**Purpose:** Complete specification of all AIM modules, Captain meta-learning, and discretionary reporting outputs
**Companion:** `CaptainNotes.md`, `AIM_Research_Notes.md`, `GUI_Notes.md`

---

# PART A — AIM FRAMEWORK ARCHITECTURE

## A1. What AIMs Are

Auxiliary Intelligence Modules are **trainable, continuously learning sub-models** embedded in the Captain system. Each AIM consumes a specific data source that Programs 1/2 do not use, builds an internal model of how that data relates to strategy performance, and outputs a **confidence modifier** adjusting the Captain's sizing decisions.

AIMs do NOT override strategy direction. They adjust **how aggressively** the Captain deploys the validated strategy on a given day.

## A2. AIM Output Interface

```
AIM_output:
    modifier        : float ∈ [FLOOR, CEILING]    (default: 1.0 = neutral)
    confidence      : float ∈ [0, 1]
    reason_tag      : string
    timestamp       : datetime

Default bounds: FLOOR = 0.5, CEILING = 1.5 (configurable per AIM)
```

Captain aggregation:
```
AIM_aggregate = Π (AIM_i.modifier ^ AIM_meta_weight_i)    for all active AIMs
Kelly_adjusted = Kelly_base × AIM_aggregate
```

## A3. AIM Lifecycle States

```
INSTALLED → COLLECTING → WARM-UP → ELIGIBLE → ACTIVE → (SUPPRESSED if ineffective)
```

- **INSTALLED:** Code exists, no data connection
- **COLLECTING:** Data pipeline active, raw data accumulating
- **WARM-UP:** Training in progress, minimum threshold partially met
- **ELIGIBLE:** Warm-up complete, outputs locked at neutral (1.0)
- **ACTIVE:** User activated via GUI — modifier flows into Captain decisions
- **SUPPRESSED:** Captain meta-learning drove weight to ~0. Still learning. Can recover automatically

## A4. GUI Warm-Up Display

Each AIM shows in GUI sub-panel: status badge, progress bar (observations / required), sub-event warm-up where applicable, estimated completion date, Activate/Deactivate/Force Override controls.

---

# PART B — CAPTAIN META-LEARNING (AIM Weight Management)

## B1. Mechanism

```
AIM_effectiveness_update(AIM_i, trade_outcome):

    modifier_i = AIM_i.modifier at time of trade signal
    trade_pnl  = actual trade PnL

    IF modifier_i > 1.0:
        reward = +1 if trade_pnl > 0, else -1
    IF modifier_i < 1.0:
        reward = +1 if trade_pnl < 0 (correctly reduced), else -1
    IF modifier_i == 1.0:
        reward = 0

    effectiveness_i = EWMA(reward, decay=100 trades)

    IF effectiveness_i > 0:
        AIM_meta_weight_i = min(1.0, effectiveness_i × scale_factor)
    ELSE:
        AIM_meta_weight_i = max(0.0, effectiveness_i × scale_factor)
        IF AIM_meta_weight_i == 0: STATUS = SUPPRESSED

    Minimum evaluation period: 50 trades before meta-weight adjusts from 1.0
```

## B2. Suppression and Recovery

- Suppressed AIM continues collecting data and training
- Recovery automatic: meta-weight drifts back up if new outcomes show AIM is now accurate
- All suppression/recovery events logged for RPT-04 AIM Effectiveness Report
- Human override available via GUI (does not affect meta-learning — effectiveness score continues)

---

# PART C — COMPLETE AIM REGISTRY

## Category 1: Options-Derived Intelligence

### AIM-01: Volatility Risk Premium Monitor
| Property | Value |
|----------|-------|
| Data source | ATM implied volatility for ES/NQ/CL options (daily, pre-open) |
| Combined with | RV from P2-D01 |
| What it learns | IV/RV ratio relationship to ORB performance. When IV >> RV, predicts larger range or mean-reversion — model learns which |
| Warm-up | 120 trading days |
| Data cost | Moderate (CBOE or broker API) |
| Research needed | Yes |
| Priority | Tier 2 |
| Status | PROPOSED — research pending |

### AIM-02: Options Skew & Positioning Analyzer
| Property | Value |
|----------|-------|
| Data source | 25-delta risk reversal, put-call OI ratio, large block option trades |
| What it learns | Whether extreme skew predicts ORB directional accuracy or failure |
| Modifier direction | Direction-specific |
| Warm-up | 120 trading days |
| Data cost | Moderate to high |
| Research needed | Yes |
| Priority | Tier 3 |
| Status | PROPOSED — research pending |

### AIM-03: Gamma Exposure (GEX) Estimator
| Property | Value |
|----------|-------|
| Data source | Open interest by strike, estimated dealer positioning |
| What it learns | Dealer short gamma → ranges expand (good for ORB). Long gamma → ranges compress |
| Warm-up | 250 trading days |
| Data cost | High (SpotGamma, Squeezemetrics) |
| Research needed | Yes |
| Priority | Tier 3 |
| Status | PROPOSED — research pending |

---

## Category 2: Market Microstructure Intelligence

### AIM-04: Pre-Market & Overnight Session Analyzer
| Property | Value |
|----------|-------|
| Data source | Globex overnight volume, overnight range, gap size, European session direction, overnight 10Y Treasury yield change, overnight DXY movement |
| What it learns | Whether overnight/pre-market characteristics predict ORB performance |
| Sub-components | Gap size model, overnight volume model, European session model, overnight rates/dollar model |
| Warm-up | 60 trading days |
| Data cost | Low (Globex + free macro sources) |
| Research needed | Optional |
| Priority | Tier 1 |
| Status | PROPOSED — research pending |

### AIM-05: Order Book Depth/Imbalance at Open
| Property | Value |
|----------|-------|
| Data source | Level 2 order book snapshots at market open |
| Warm-up | 120 trading days |
| Data cost | Moderate |
| Priority | Tier 3 |
| Status | DEFERRED — requires near-real-time infrastructure |

---

## Category 3: Macro & Event Intelligence

### AIM-06: Economic Calendar Impact Model
| Property | Value |
|----------|-------|
| Data source | Historical event calendar (FOMC, NFP, CPI, PMI, ISM, retail sales, jobless claims, Treasury auctions, OPEC meetings), event outcomes, per-asset ORB performance on event days |
| What it learns | Per-event, per-asset conditional performance model. NOT a binary filter. Builds event × asset → performance adjustment matrix |
| Cascading | When AIM-01 active: learns how IV changes before events and how this compounds. When AIM-10 active: separates event × day-of-week interactions |
| Warm-up | ~2 years (FOMC: 16 meetings; NFP: 24 releases). Per-event warm-up shown separately in GUI |
| Data cost | Free |
| Research needed | Optional |
| Priority | Tier 1 |
| Status | PROPOSED — research pending |

### AIM-07: Commitments of Traders (COT) Positioning
| Property | Value |
|----------|-------|
| Data source | Weekly CFTC COT reports: commercial, non-commercial, managed money for ES/NQ/CL |
| What it learns | Whether extreme institutional positioning predicts ORB regime shifts |
| Update frequency | Weekly |
| Warm-up | 52 releases (~1 year) |
| Data cost | Free (CFTC public) |
| Research needed | Moderate |
| Priority | Tier 3 |
| Status | PROPOSED — research pending |

---

## Category 4: Cross-Asset Intelligence

### AIM-08: Dynamic Cross-Asset Correlation Monitor
| Property | Value |
|----------|-------|
| Data source | Daily/intraday returns for ES, NQ, CL + DXY, 10Y yield, USD/CAD |
| What it learns | Time-varying correlation. ES/NQ decoupling = regime change. CL decoupling = macro shift. How correlation regimes affect multi-asset ORB performance |
| Architecture | TV-GARCH (Paper 14) for long-run variance + DCC for short-run + RS Copula (Paper 18) for tail dependence |
| Modifier direction | High correlation → concentrate on highest-edge asset. Low correlation → spread capital |
| Warm-up | 120 trading days |
| Data cost | Free |
| Research coverage | STRONG — Papers 14 and 18 |
| Priority | Tier 1 |
| Status | PROPOSED — papers held |

### AIM-09: Spatio-Temporal Cross-Asset Signal
| Property | Value |
|----------|-------|
| Data source | MACD features (12/26/9) from all traded assets |
| What it learns | Whether cross-asset momentum predicts individual ORB outcomes. SLP (Paper 19) |
| Modifier direction | All assets agree → modifier > 1.0. Signals conflict → modifier < 1.0 |
| Warm-up | 60 trading days |
| Data cost | Free |
| Research coverage | STRONG — Paper 19 |
| Priority | Tier 2 |
| Status | PROPOSED — paper held |

---

## Category 5: Temporal & Calendar Intelligence

### AIM-10: Calendar Effect Model
| Property | Value |
|----------|-------|
| Data source | Historical trade outcomes tagged by day-of-week, week-of-month, month-of-year, OPEX proximity, futures rollover period, holiday proximity |
| Sub-components | Day-of-week, OPEX, month-of-year seasonality, rollover period — all per asset |
| Warm-up | Day-of-week: 120 days. Seasonality: 500 days. OPEX: 12 expirations |
| Data cost | Free |
| Research needed | Minimal |
| Priority | Tier 2 |
| Status | PROPOSED — research pending |

---

## Category 6: Internal Performance Meta-Intelligence

### AIM-11: Regime Transition Early Warning
| Property | Value |
|----------|-------|
| Data source | P2 regime model state, VIX term structure slope (front vs. second month contango/backwardation), credit spreads, AIM-08 correlation shifts, rate of change of σ_t from P2-D01 |
| What it learns | Whether regime transitions can be detected EARLIER than Pettersson (which lags due to EWMA). VIX term structure inversion while Pettersson shows LOW = strong leading signal |
| Modifier direction | Impending regime change → modifier < 1.0 (pre-emptive sizing reduction) |
| Warm-up | 120 trading days |
| Data cost | Low |
| Research coverage | Covered — Papers 4, 10, 11 + supplementary search for leading indicators |
| Priority | Tier 1 |
| Status | PROPOSED — supplementary research pending |

### AIM-12: Dynamic Slippage & Cost Estimator
| Property | Value |
|----------|-------|
| Data source | Actual fill prices vs. theoretical, time-of-day spread patterns, event-day cost inflation, live bid-ask at open |
| What it learns | Condition-specific cost estimates. Learns "On FOMC days ES slippage is 2× normal" |
| Effect | Provides more accurate cost input to Kelly formula. Higher costs → lower net edge → naturally smaller Kelly size |
| Warm-up | 50 live trades |
| Data cost | Free (internal execution data + live spread) |
| Research needed | Yes (architecture informed by research) |
| Priority | Tier 1 |
| Status | PROPOSED — research pending |

---

## Category 7: Automated Strategy Lifecycle Management

### AIM-13: Strategy Parameter Sensitivity Scanner
| Property | Value |
|----------|-------|
| What it does | Monthly: runs perturbations of locked strategy parameters (SL ±10%, TP ±10%, OR window ±5 min) through lightweight Program 1 validation |
| Output | ROBUST / FRAGILE flag + sensitivity heatmap |
| Modifier | FRAGILE → modifier < 1.0. ROBUST → 1.0 |
| Constraint | Narrow pre-defined range only. NEVER generates new models — that is Program 1's job |
| Warm-up | None — runs on historical data immediately |
| Data cost | Free |
| Research needed | Yes (robustness metric selection) |
| Priority | Tier 2 |
| Status | PROPOSED — research pending |

### AIM-14: Model Universe Auto-Expansion Monitor
| Property | Value |
|----------|-------|
| What it does | On Level 3 trigger: generates small candidate model set by systematically varying failed strategy parameters within narrow search grid. Feeds expanded set to Programs 1/2 re-run |
| Constraint | Narrow pre-defined grid. All candidates go through FULL Program 1/2 validation — no shortcuts |
| Warm-up | None — on-demand |
| Data cost | Free |
| Research needed | Yes (overfitting control for automated search) |
| Priority | Tier 2 |
| Status | PROPOSED — research pending |

---

## Category 8: Real-Time Session Intelligence

### AIM-15: Opening Session Volume Quality Monitor
| Property | Value |
|----------|-------|
| Data source | Volume during 15-minute OR formation vs. historical average for same window |
| What it learns | Relative volume during OR formation and breakout success rate. High relative volume = high conviction breakout. Low volume = low conviction |
| Key insight | Available AT decision time. Real-time but uses existing 15-sec bar data from P1 |
| Modifier | High relative volume → > 1.0. Low volume → < 1.0 |
| Warm-up | 60 trading days |
| Data cost | Free |
| Research needed | Minimal |
| Priority | Tier 1 |
| Status | PROPOSED — research pending |

---

# PART D — REJECTED MODULES

| Module | Reason |
|--------|--------|
| News/Social Sentiment NLP | Pre-market price action captures news faster. Too noisy |
| Dark Pool / Off-Exchange | Equity-specific, not applicable to CME futures |
| Central Bank Communication Sentiment | Too few observations/year. Too noisy. Captured by AIM-06 |
| ETF Flow Data (SPY/QQQ) | End-of-day or lagged. Pre-market price action captures faster |
| Market Breadth (advance/decline) | Partially in AIM-04/08. Not directly actionable for ORB |
| VWAP/TWAP Execution Algorithms | Not an AIM. At 1–5 contracts, market impact negligible and ORB needs immediate entry. Future scaling feature for Captain (Command) execution layer. Execution quality benchmarking covered by AIM-12 |

---

# PART E — CASCADING DEPENDENCIES

```
AIM-06 (Economic Calendar) + AIM-10 (Calendar) → AIM-01 (IV/RV) → Captain sizing

AIM-08 (Correlation) → AIM-09 (Spatio-Temporal) → Captain asset allocation
AIM-08 + P2 regime model → AIM-11 (Regime Warning) → Captain pre-emptive sizing

AIM-06 (event cost inflation) → AIM-12 (Costs) → Captain Kelly formula
AIM-04 (pre-market volume context) → AIM-15 (Volume Quality) → Captain signal confidence
AIM-13 (FRAGILE flag) + decay → AIM-14 (Auto-Expansion) → P1/P2 re-run
```

---

# PART F — PRIORITY TIERS

## Tier 1 — Build First

| AIM | Warm-Up | Data Cost | Research |
|-----|---------|-----------|----------|
| AIM-04 Pre-Market | ~3 months | Free | Optional |
| AIM-06 Economic Calendar | ~2 years (collecting from day 1) | Free | Optional |
| AIM-08 Cross-Asset Correlation | ~6 months | Free | Done |
| AIM-11 Regime Early Warning | ~6 months | Low | Done + supplementary |
| AIM-12 Dynamic Costs | ~50 trades | Free | Yes |
| AIM-15 Volume Quality | ~3 months | Free | Minimal |

## Tier 2 — Build Second

| AIM | Warm-Up | Data Cost | Research |
|-----|---------|-----------|----------|
| AIM-01 IV/RV | ~6 months | Moderate | Yes |
| AIM-09 Spatio-Temporal | ~3 months | Free | Done |
| AIM-10 Calendar Effects | ~2 years | Free | Minimal |
| AIM-13 Sensitivity Scanner | Immediate | Free | Yes |
| AIM-14 Auto-Expansion | On demand | Free | Yes |

## Tier 3 — Build Later

| AIM | Warm-Up | Data Cost | Research |
|-----|---------|-----------|----------|
| AIM-02 Options Skew | ~6 months | Moderate–High | Yes |
| AIM-03 GEX | ~1 year | High | Yes |
| AIM-07 COT | ~1 year | Free | Moderate |
| AIM-05 Order Book | ~6 months | Moderate | Yes (DEFERRED) |

---

# PART G — RESEARCH STATUS

| AIM | Papers Held | Research Prompt | Search Status |
|-----|------------|-----------------|---------------|
| AIM-01 | None | Generated | Papers collected — screening pending |
| AIM-02 | None | Generated | Papers collected — screening pending |
| AIM-03 | None | Generated | Papers collected — screening pending |
| AIM-04 | None | Generated | Papers collected — screening pending |
| AIM-05 | None | Generated | DEFERRED |
| AIM-06 | None | Generated | Papers collected — screening pending |
| AIM-07 | None | Generated | Papers collected — screening pending |
| AIM-08 | Papers 14, 18 | Generated (supplementary) | Papers collected — screening pending |
| AIM-09 | Paper 19 | Generated (supplementary) | Papers collected — screening pending |
| AIM-10 | None (well-studied) | Generated | Papers collected — screening pending |
| AIM-11 | Papers 4, 10, 11 | Generated (supplementary) | Papers collected — screening pending |
| AIM-12 | None | Generated | Papers collected — screening pending |
| AIM-13 | None | Generated | Papers collected — screening pending |
| AIM-14 | None | Generated | Papers collected — screening pending |
| AIM-15 | None (well-established) | Generated | Papers collected — screening pending |

All 15 AIM research prompts generated. All 15 paper sets collected. All 15 accepted into registry — Captain meta-learning handles effectiveness, not pre-build rejection.

Full screening and extraction tracked in `AIM_Research_Notes.md`.

---

# PART H — DISCRETIONARY REPORTING OUTPUTS

| Report | Frequency | Purpose |
|--------|-----------|---------|
| RPT-01 Daily Signal | Pre-open daily | Primary trade decision document. Direction, size, confidence, all AIM modifiers, Kelly base vs. adjusted, TSM status |
| RPT-02 Weekly Performance | Weekly | Win/loss by asset, actual vs. predicted edge, AIM contribution breakdown, cost analysis |
| RPT-03 Monthly Health | Monthly | SPRT/CUSUM state, AIM-13 sensitivity results, AIM warm-up progress, AIM meta-weights, TSM tracking |
| RPT-04 AIM Effectiveness | Monthly / on demand | Per AIM: modifier accuracy, PnL by modifier direction, meta-weight trajectory, suppression events |
| RPT-05 Injection Comparison | On new P1/P2 run | Current vs. proposed strategy side-by-side. AIM-contextualised expected performance. Adopt/Parallel Track/Reject recommendation |
| RPT-06 Regime Transition | Event-triggered | Detection method, transition direction, impact on edge, AIM states, historical similar transitions |
| RPT-07 TSM Compliance | Daily (prop firms) | Drawdown vs. MDD, pass probability, risk budget consumed, days remaining, sizing recommendations |
| RPT-08 Probability Accuracy | Monthly | Regime probability calibration chart. Expected vs. actual edge by decile. Over/under-confidence flags |
| RPT-09 Decision Change Impact | On demand | Parameter change context, counterfactual analysis, before/after comparison |
| RPT-10 Annual Review | Annually | Full-year performance, AIM value-add analysis, decay events, injection history, capital curve with annotations |

---

# PART I — OPEN ITEMS

- [ ] Confirm AIM modifier bounds (FLOOR/CEILING) — suggested 0.5/1.5
- [ ] Confirm meta-learning EWMA decay rate — suggested 100 trades
- [ ] Confirm minimum evaluation period — suggested 50 trades
- [ ] Define AIM-14 search grid bounds per strategy parameter
- [ ] Parallel tracking period — suggested 20 trading days
- [ ] Transition phasing window — suggested 10 trading days
- [x] All 15 AIM research prompts generated
- [x] All 15 AIMs accepted into registry
- [ ] Paper screening (all 15 AIMs + 6 system topics) — NEXT STEP in new chat

---

# DATA SOURCE MAPPING

Each AIM's data comes from one of two sources: **external** (via P3-D00.data_sources adapters) or **internal** (from Captain's own data stores or computed at runtime).

| AIM | Data Source Type | External Adapter (P3-D00) | Internal Source | Notes |
|-----|-----------------|--------------------------|-----------------|-------|
| AIM-01 (VRP) | External + Internal | options_chain (IV_ATM) | P2-D01 (RV from EWMA) | IV from options adapter; RV from P2 pipeline output |
| AIM-02 (Options Flow) | External | options_chain (PUT_CALL_RATIO, SKEW) | — | |
| AIM-03 (GEX) | External | options_chain (GEX) | — | |
| AIM-04 (IVTS) | External | vix_feed (VIX_CLOSE, VXV_CLOSE) | — | |
| AIM-05 (Deferred) | N/A | — | — | DEFERRED stub — returns 1.0. No data needed. |
| AIM-06 (Events) | External | economic_calendar | — | |
| AIM-07 (COT) | External | cot_data (SMI_POLARITY, SPECULATOR_Z) | — | |
| AIM-08 (Correlation) | External | cross_asset_prices | P3-D07 (correlation matrices) | Prices from external; correlation model trained internally |
| AIM-09 (Momentum) | External | cross_asset_prices | — | |
| AIM-10 (Seasonality) | Internal | — | Calendar (day of week, OPEX dates), price_feed (DOW patterns) | No external adapter needed — uses system calendar + price_feed |
| AIM-11 (Regime Warning) | External + Internal | vix_feed (VIX), macro_data (credit spreads) | P2 regime classification | VIX from external; regime state from P2 pipeline |
| AIM-12 (Dynamic Costs) | Internal | — | P3-D03 (execution history), price_feed (live spread) | Spread from price_feed; slippage/commission from trade outcomes |
| AIM-13 (Sensitivity) | Internal | — | P3-D13 (Offline Block 5 sensitivity scan output) | No external data — reads Offline diagnostic results |
| AIM-14 (Auto-Expansion) | Internal | — | P3-D04 (decay events), P1/P2 pipeline | Triggers P1/P2 re-run. Not a modifier AIM — returns 1.0. |
| AIM-15 (Volume) | External | price_feed (intraday volume bars) | — | Volume from price_feed adapter during OR formation period |

**AIM-01 threshold clarification:** Part J thresholds are the authoritative specification values. VRP is computed as `E[RV] - IV`. Positive VRP means the market is underpricing realised volatility relative to implied — this indicates favorable breakout conditions. Thresholds: `vrp_z > 1.5 → 1.15` (size up — strong VRP signal), `vrp_z > 0.5 → 1.05` (mild), `vrp_z < -1.0 → 0.85` (size down — IV expensive, breakouts less likely). Note: AIM_Research_Notes.md contains early draft thresholds that were refined during Part J pseudocode generation. Part J is authoritative.

---

# ACCURACY VERIFICATION CHECKLIST

| Check | Status |
|-------|--------|
| AIM Framework Architecture | ✓ |
| Captain Meta-Learning (effectiveness, suppression, recovery, override) | ✓ |
| 15 AIMs registered with full specifications | ✓ |
| 6 rejected modules with justifications (incl. VWAP/TWAP) | ✓ |
| Cascading dependency map | ✓ |
| 3 priority tiers | ✓ |
| Research status per AIM | ✓ |
| 10 discretionary reports | ✓ |
| GUI warm-up display design | ✓ |
| AIM lifecycle states | ✓ |
| Per-AIM compute_aim_modifier() pseudocode (Part J) | ✓ |

---

# PART J — PER-AIM MODIFIER COMPUTATION PSEUDOCODE

All modifier functions return `AIM_output` (see Part A2). Every modifier is clamped to [FLOOR=0.5, CEILING=1.5] after computation. Research grounding for each formula is in `AIM_Research_Notes.md` Design Conclusions sections. All z-scores use trailing windows specified per AIM; `z_score(value, window)` = `(value - mean(window)) / std(window)`.

## J1. AIM-01: Volatility Risk Premium Monitor

```
FUNCTION compute_aim_modifier_01(features, asset):
    # Inputs: ATM implied volatility, realised volatility from P2-D01
    # Research: Papers 34, 35, 40 (AIM_Research_Notes.md AIM-01)

    IF features[asset].vrp is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "VRP_DATA_MISSING"}

    vrp = features[asset].vrp                    # E[RV] - IV (positive = IV cheap)
    vrp_z = z_score(vrp, trailing_120d_vrp[asset])

    IF vrp_z > 1.5:
        base = 1.15    # IV very cheap relative to RV — larger moves expected, ORB favourable
        reason = "VRP_HIGH_POSITIVE"
    ELIF vrp_z > 0.5:
        base = 1.05
        reason = "VRP_MODERATE_POSITIVE"
    ELIF vrp_z < -1.0:
        base = 0.85    # IV expensive — range compression expected, ORB less reliable
        reason = "VRP_NEGATIVE"
    ELSE:
        base = 1.0
        reason = "VRP_NEUTRAL"

    # Overnight VRP refinement
    IF features[asset].vrp_overnight is not None:
        overnight_z = z_score(features[asset].vrp_overnight, trailing_60d_overnight_vrp[asset])
        IF overnight_z > 1.0 AND base >= 1.0:
            base = min(base + 0.05, 1.5)
            reason += "+OVERNIGHT_ELEVATED"

    confidence = min(abs(vrp_z) / 2.0, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J2. AIM-02: Options Skew & Positioning Analyzer

```
FUNCTION compute_aim_modifier_02(features, asset):
    # Inputs: put-call ratio, DOTM-OTM put IV spread
    # Research: Papers 46, 47, 48, 49 (AIM_Research_Notes.md AIM-02)
    # Direction-specific: modifies sizing, NOT direction

    IF features[asset].pcr is None AND features[asset].put_skew is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "SKEW_DATA_MISSING"}

    pcr_z = z_score(features[asset].pcr, trailing_60d_pcr[asset]) IF features[asset].pcr ELSE 0
    skew_z = z_score(features[asset].put_skew, trailing_60d_skew[asset]) IF features[asset].put_skew ELSE 0

    combined = 0.6 * pcr_z + 0.4 * skew_z

    IF combined > 1.5:
        base = 0.75     # Extreme bearish positioning — high crash risk, reduce sizing
        reason = "SKEW_EXTREME_BEARISH"
    ELIF combined > 0.5:
        base = 0.90
        reason = "SKEW_ELEVATED_BEARISH"
    ELIF combined < -1.0:
        base = 1.10     # Complacent positioning — low risk perception, sizing up
        reason = "SKEW_COMPLACENT"
    ELSE:
        base = 1.0
        reason = "SKEW_NEUTRAL"

    confidence = min(abs(combined) / 2.0, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J3. AIM-03: Gamma Exposure (GEX) Estimator

```
FUNCTION compute_aim_modifier_03(features, asset):
    # Inputs: dealer net gamma, expiration calendar
    # Research: Papers 52, 53, 57, 58, 60 (AIM_Research_Notes.md AIM-03)

    IF features[asset].gex is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "GEX_DATA_MISSING"}

    gex_z = z_score(features[asset].gex, trailing_60d_gex[asset])

    IF gex_z < -1.0:
        base = 0.85     # Negative gamma — amplification regime, higher vol, flash risk
        reason = "GEX_NEGATIVE_GAMMA"
    ELIF gex_z > 1.0:
        base = 1.10     # Positive gamma — dampening, more predictable breakouts
        reason = "GEX_POSITIVE_GAMMA"
    ELSE:
        base = 1.0
        reason = "GEX_NEUTRAL"

    # Expiration overlay (Paper 60: pinning near ATM on expiry)
    IF is_expiration_day(today, asset):
        base *= 0.95
        reason += "+EXPIRATION_DAY"
    IF is_triple_witching(today):
        base *= 0.90
        reason += "+TRIPLE_WITCHING"

    confidence = min(abs(gex_z) / 1.5, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J4. AIM-04: Pre-Market & Overnight Session Analyzer

```
FUNCTION compute_aim_modifier_04(features, asset):
    # Inputs: IVTS (VIX/VXV), overnight gap size
    # Research: Papers 61, 65, 67 (AIM_Research_Notes.md AIM-04)
    # Paper 67: IVTS is THE validated regime filter for ORB on ES

    ivts = features[asset].ivts   # VIX_close_yesterday / VXV_close_yesterday

    IF ivts is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "IVTS_DATA_MISSING"}

    # Primary: IVTS regime filter (Paper 67 — critical for MOST)
    IF ivts > 1.0:
        base = 0.65     # Turmoil — inverted term structure, ORB unreliable
        reason = "IVTS_TURMOIL"
    ELIF ivts >= 0.93:
        base = 1.10     # Optimal zone — elevated but contained vol
        reason = "IVTS_OPTIMAL"
    ELSE:
        base = 0.80     # Quiet — low vol, small ranges, ORB less profitable
        reason = "IVTS_QUIET"

    # Secondary: overnight gap extremity (Papers 61, 66)
    gap_z = z_score(abs(features[asset].overnight_return), trailing_60d_gaps[asset])
    IF gap_z > 2.0:
        base *= 0.85    # Extreme gap — reversal risk
        reason += "+EXTREME_GAP"

    confidence = 0.9 IF ivts > 1.0 OR ivts < 0.93 ELSE 0.6

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J5. AIM-05: Order Book Depth/Imbalance at Open

```
FUNCTION compute_aim_modifier_05(features, asset):
    # DEFERRED — requires L2 data infrastructure
    # When activated: book imbalance + multi-level OFI at open
    # Research: Papers 74, 78, 80 (AIM_Research_Notes.md AIM-05)

    RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "AIM05_DEFERRED"}
```

## J6. AIM-06: Economic Calendar Impact Model

```
FUNCTION compute_aim_modifier_06(features, asset):
    # Inputs: economic calendar, event proximity to ORB
    # Research: Papers 82, 87, 88, 90 (AIM_Research_Notes.md AIM-06)

    events = features[asset].events_today
    proximity_min = features[asset].event_proximity   # minutes to nearest event from session open

    IF events is None OR len(events) == 0:
        RETURN {modifier: 1.0, confidence: 0.5, reason_tag: "EVENT_FREE_DAY"}

    # Classify highest-tier event today
    highest_tier = min(event.tier for event in events)  # Tier 1 = highest impact

    # Proximity to ORB window (within ±30 min of session open)
    near_orb = (proximity_min is not None AND abs(proximity_min) <= 30)

    IF highest_tier == 1 AND near_orb:
        base = 0.70     # Tier 1 (NFP/FOMC) near ORB — extreme uncertainty
        reason = "TIER1_NEAR_ORB"
    ELIF highest_tier == 1 AND NOT near_orb:
        base = 1.05     # Tier 1 later — market usually stabilises by ORB
        reason = "TIER1_LATER"
    ELIF highest_tier == 2 AND near_orb:
        base = 0.85     # Tier 2 (CPI/GDP) near ORB
        reason = "TIER2_NEAR_ORB"
    ELIF highest_tier == 2:
        base = 0.95
        reason = "TIER2_LATER"
    ELSE:
        base = 1.0
        reason = "TIER3_OR_LOWER"

    # EIA for CL (Paper 62: shifts momentum signal)
    IF asset == "CL" AND any(e.name == "EIA_PETROLEUM" for e in events):
        base *= 0.90
        reason += "+EIA_CL"

    # FOMC cross-asset reduction (Paper 89: FOMC affects ES + CL simultaneously)
    IF any(e.name == "FOMC" for e in events):
        base *= 0.85
        reason += "+FOMC_CROSS_ASSET"

    confidence = 0.8 IF highest_tier <= 2 ELSE 0.4

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J7. AIM-07: Commitments of Traders (COT) Positioning

```
FUNCTION compute_aim_modifier_07(features, asset):
    # Inputs: COT SMI polarity, speculator z-score (weekly data, 3-day lag)
    # Research: Papers 91, 95, 98 (AIM_Research_Notes.md AIM-07)

    smi = features[asset].cot_smi               # +1 (institutional bullish) / -1 (bearish) / 0 (neutral)
    spec_z = features[asset].cot_speculator_z    # speculator positioning z-score

    IF smi is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "COT_DATA_MISSING"}

    # Primary: SMI direction (Paper 98: cross-asset relative sentiment)
    IF smi > 0:
        base = 1.05
        reason = "SMI_POSITIVE"
    ELIF smi < 0:
        base = 0.90
        reason = "SMI_NEGATIVE"
    ELSE:
        base = 1.0
        reason = "SMI_NEUTRAL"

    # Secondary: extreme speculator positioning (Paper 95: extremes most reliable)
    IF spec_z is not None:
        IF spec_z > 1.5:
            base *= 0.95    # Crowded long — contrarian caution
            reason += "+SPEC_CROWDED_LONG"
        ELIF spec_z < -1.5:
            base *= 1.10    # Extreme short — contrarian bullish
            reason += "+SPEC_EXTREME_SHORT"

    confidence = 0.5  # COT is weekly, lagged — inherently lower confidence for intraday

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J8. AIM-08: Dynamic Cross-Asset Correlation Monitor

```
FUNCTION compute_aim_modifier_08(features, asset):
    # Inputs: rolling 20d pairwise correlation, z-scored vs 252d baseline
    # Research: Papers 14, 18, 102, 103, 108 (AIM_Research_Notes.md AIM-08)

    corr_z = features[asset].correlation_z   # z-score of ES-CL 20d rolling corr vs 252d

    IF corr_z is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "CORR_DATA_MISSING"}

    IF corr_z > 1.5:
        base = 0.80     # Stress regime — high cross-asset correlation (Paper 102)
        reason = "CORR_STRESS"
    ELIF corr_z > 0.5:
        base = 0.90     # Elevated correlation
        reason = "CORR_ELEVATED"
    ELIF corr_z < -0.5:
        base = 1.05     # Decoupled — diversification benefit
        reason = "CORR_DECOUPLED"
    ELSE:
        base = 1.0
        reason = "CORR_NORMAL"

    confidence = min(abs(corr_z) / 2.0, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J9. AIM-09: Spatio-Temporal Cross-Asset Signal

```
FUNCTION compute_aim_modifier_09(features, asset):
    # Inputs: cross-asset MACD momentum agreement
    # Research: Papers 19, 111, 116 (AIM_Research_Notes.md AIM-09)

    momentum = features[asset].cross_momentum   # aggregate cross-asset signal

    IF momentum is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "MOMENTUM_DATA_MISSING"}

    # Strategy direction from locked strategy
    strategy_direction = get_strategy_direction(asset, features)  # LONG or SHORT

    IF momentum > 0 AND strategy_direction == "LONG":
        base = 1.10     # Cross-asset momentum agrees with long signal
        reason = "MOMENTUM_AGREES_LONG"
    ELIF momentum < 0 AND strategy_direction == "SHORT":
        base = 1.10     # Cross-asset momentum agrees with short signal
        reason = "MOMENTUM_AGREES_SHORT"
    ELIF momentum * (1 IF strategy_direction == "LONG" ELSE -1) < 0:
        base = 0.85     # Cross-asset momentum disagrees
        reason = "MOMENTUM_DISAGREES"
    ELSE:
        base = 1.0
        reason = "MOMENTUM_NEUTRAL"

    confidence = min(abs(momentum) / 0.02, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J10. AIM-10: Calendar Effect Model

```
FUNCTION compute_aim_modifier_10(features, asset):
    # Inputs: OPEX proximity, day of week, regime state
    # Research: Papers 121, 124, 125, 128, 129 (AIM_Research_Notes.md AIM-10)

    base = 1.0
    reason = "CALENDAR_NEUTRAL"

    # OPEX window: 3rd Friday ±2 trading days (Paper 129: ~2% IV swing)
    IF features[asset].is_opex_window:
        base *= 0.95
        reason = "OPEX_WINDOW"

    # DOW effect is regime-conditioned (Paper 121: positive in low-vol, NEGATIVE in high-vol)
    regime = get_current_regime(asset)
    IF regime == "HIGH_VOL":
        base *= 0.97
        reason += "+HIGHVOL_DOW"

    confidence = 0.3  # Calendar effects are weak signals — low standalone conviction

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J11. AIM-11: Regime Transition Early Warning

```
FUNCTION compute_aim_modifier_11(features, asset):
    # Inputs: VIX z-score, VIX daily change z-score, CL basis (for CL only)
    # Research: Papers 131, 134, 136, 139 (AIM_Research_Notes.md AIM-11)

    vix_z = features[asset].vix_z                      # VIX vs 252d trailing
    vix_change_z = features[asset].vix_daily_change_z  # abs(VIX change) vs 60d trailing

    IF vix_z is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "VIX_DATA_MISSING"}

    # Primary: VIX level z-score (Paper 136: lagged VIX predicts transition probability)
    IF vix_z > 1.5:
        base = 0.75     # VIX very elevated — stress regime likely
        reason = "VIX_EXTREME"
    ELIF vix_z > 0.5:
        base = 0.90     # VIX elevated
        reason = "VIX_ELEVATED"
    ELIF vix_z < -0.5:
        base = 1.05     # VIX low — calm regime, favourable for ORB
        reason = "VIX_LOW"
    ELSE:
        base = 1.0
        reason = "VIX_NORMAL"

    # Secondary: rapid VIX change (transition in progress)
    IF vix_change_z is not None AND vix_change_z > 2.0:
        base *= 0.85
        reason += "+VIX_SPIKE"

    # CL-specific: basis-driven transition (Paper 139)
    IF asset == "CL" AND features[asset].cl_basis is not None:
        IF features[asset].cl_basis < 0 AND vix_z > 0.5:
            base *= 0.90   # Backwardation + stress — high-vol persists
            reason += "+CL_BACKWARDATION_STRESS"

    confidence = min(abs(vix_z) / 2.0, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J12. AIM-12: Dynamic Slippage & Cost Estimator

```
FUNCTION compute_aim_modifier_12(features, asset):
    # Inputs: current spread z-score, vol z-score
    # Research: Papers 140, 142, 147 (AIM_Research_Notes.md AIM-12)
    # Effect: higher costs → lower net edge → naturally smaller Kelly

    spread_z = features[asset].spread_z   # current spread vs 60d trailing open spreads

    IF spread_z is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "SPREAD_DATA_MISSING"}

    vol_z = features[asset].vix_z IF features[asset].vix_z ELSE 0

    # Spread-based cost adjustment
    IF spread_z > 1.5 OR vol_z > 1.5:
        base = 0.85     # Wide spreads or high vol — costs elevated
        reason = "COST_HIGH"
    ELIF spread_z > 0.5 OR vol_z > 0.5:
        base = 0.95
        reason = "COST_ELEVATED"
    ELIF spread_z < -0.5 AND vol_z < -0.5:
        base = 1.05     # Tight spreads + low vol — low cost environment
        reason = "COST_LOW"
    ELSE:
        base = 1.0
        reason = "COST_NORMAL"

    # Systematic trader penalty (Paper 147: 2x slippage for systematic)
    base *= 0.95
    reason += "+SYSTEMATIC_PENALTY"

    confidence = min(abs(spread_z) / 2.0, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J13. AIM-13: Strategy Parameter Sensitivity Scanner

```
FUNCTION compute_aim_modifier_13(features, asset):
    # Inputs: latest sensitivity scan results from P3-D13
    # Research: Papers 150, 151, 152 (AIM_Research_Notes.md AIM-13)
    # Computation: runs MONTHLY in Offline Block 5. Online reads cached result.

    scan = P3-D13[asset]

    IF scan is None OR scan.robustness_status is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "SENSITIVITY_NO_SCAN"}

    IF scan.robustness_status == "FRAGILE":
        base = 0.85
        reason = "STRATEGY_FRAGILE"
    ELSE:
        base = 1.0
        reason = "STRATEGY_ROBUST"

    confidence = 0.7 IF scan.pbo is not None ELSE 0.3

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J14. AIM-14: Model Universe Auto-Expansion Monitor

```
FUNCTION compute_aim_modifier_14(features, asset):
    # AIM-14 is NOT a modifier AIM. It triggers P1/P2 re-runs on Level 3 decay.
    # Research: Papers 161, 162, 163, 164, 165 (AIM_Research_Notes.md AIM-14)
    # See Offline Block 6 (P3-PG-13) for operational pseudocode.

    RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "AIM14_NOT_MODIFIER"}
```

## J15. AIM-15: Opening Session Volume Quality Monitor

```
FUNCTION compute_aim_modifier_15(features, asset):
    # Inputs: opening volume ratio (OR formation period vs 20d avg for same window)
    # Research: Papers 168, 175, 176 (AIM_Research_Notes.md AIM-15)
    # Paper 176: Sharpe 2.81 with volume filtering vs much lower without

    vol_ratio = features[asset].opening_volume_ratio

    IF vol_ratio is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "VOLUME_DATA_MISSING"}

    # Temporal: relative volume at open
    IF vol_ratio > 1.5:
        base = 1.15     # Very high volume — high conviction breakout (Paper 175)
        reason = "VOLUME_VERY_HIGH"
    ELIF vol_ratio > 1.0:
        base = 1.05     # Above average — good participation
        reason = "VOLUME_ABOVE_AVG"
    ELIF vol_ratio < 0.7:
        base = 0.80     # Low volume — low conviction, ORB less reliable
        reason = "VOLUME_LOW"
    ELSE:
        base = 1.0
        reason = "VOLUME_NORMAL"

    confidence = min(abs(vol_ratio - 1.0) / 0.5, 1.0)

    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

## J16. Master Dispatch Function

```
FUNCTION compute_aim_modifier(aim_id, features, asset):
    # Called by Online Block 3 for each active AIM
    # aim_id: integer 1-15 (Online Block 3 passes "AIM-01" string;
    #         extract numeric id: aim_id = int(aim_string.split("-")[1]))
    # Dispatches to the per-AIM function

    DISPATCH = {
        1:  compute_aim_modifier_01,
        2:  compute_aim_modifier_02,
        3:  compute_aim_modifier_03,
        4:  compute_aim_modifier_04,
        5:  compute_aim_modifier_05,
        6:  compute_aim_modifier_06,
        7:  compute_aim_modifier_07,
        8:  compute_aim_modifier_08,
        9:  compute_aim_modifier_09,
        10: compute_aim_modifier_10,
        11: compute_aim_modifier_11,
        12: compute_aim_modifier_12,
        13: compute_aim_modifier_13,
        14: compute_aim_modifier_14,
        15: compute_aim_modifier_15
    }

    IF aim_id NOT IN DISPATCH:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "UNKNOWN_AIM"}

    TRY:
        result = DISPATCH[aim_id](features, asset)
    EXCEPT Exception as e:
        LOG "AIM-{aim_id} modifier computation failed for {asset}: {e}"
        result = {modifier: 1.0, confidence: 0.0, reason_tag: "AIM{aim_id}_ERROR"}

    RETURN result

FUNCTION compute_aim_confidence(aim_id, features, asset):
    # Convenience wrapper — extracts confidence from modifier result
    result = compute_aim_modifier(aim_id, features, asset)
    RETURN result.confidence

FUNCTION generate_reason_tag(aim_id, features, asset):
    # Convenience wrapper — extracts reason_tag from modifier result
    result = compute_aim_modifier(aim_id, features, asset)
    RETURN result.reason_tag
```

---

*Updated as Captain specification evolves and AIMs are researched and built.*
