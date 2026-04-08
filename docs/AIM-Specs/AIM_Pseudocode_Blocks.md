# AIM Pseudocode Blocks — P3-PG-24 through P3-PG-35

Generated from authoritative implementation in `b3_aim_aggregation.py` after Phase 2 reconciliation.
Code is the source of truth — these blocks document the now-correct logic for spec completeness.

**Finding:** F4.1 (12 of 16 AIMs lacked formal pseudocode)
**Authority:** Code post-Phase 2 alignment (DEC-01 through DEC-06)
**Modifier bounds:** FLOOR=0.5, CEILING=1.5 (all modifiers clamped)

---

## Aggregation: P3-PG-23 — MoE/DMA Weighted Combination

```
Input:  active_assets, features[asset], aim_states, aim_weights
Output: combined_modifier[asset], aim_breakdown[asset]

For each asset:
  1. For aim_id = 1..16:
     a. If aim_states[(asset, aim_id)].status != ACTIVE → skip
     b. If aim_weights[(asset, aim_id)].inclusion_flag == False → skip
     c. result = dispatch[aim_id](features[asset], state)
     d. modifier = clamp(result.modifier, 0.5, 1.5)
     e. Store {modifier, confidence, reason_tag, dma_weight}

  2. Weighted aggregation:
     total_weight = sum(dma_weight for active AIMs)
     combined = sum(modifier × dma_weight / total_weight)
     combined_modifier[asset] = clamp(combined, 0.5, 1.5)

  3. If no active AIMs → combined_modifier[asset] = 1.0
```

---

### P3-PG-24: AIM-01 Volatility Risk Premium (VRP) Modifier

```
Input:  features.vrp_overnight_z, features.day_of_week
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract vrp_z = features["vrp_overnight_z"]
2. If vrp_z is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "VRP_MISSING"}
3. Threshold logic (DEC-01 spec authoritative):
   - vrp_z > 1.5  → modifier=0.70, tag="VRP_HIGH_UNCERTAINTY"
   - vrp_z > 0.5  → modifier=0.85, tag="VRP_ELEVATED"
   - vrp_z < -1.0 → modifier=1.10, tag="VRP_LOW_UNCERTAINTY"
   - else          → modifier=1.00, tag="VRP_NEUTRAL"
4. Monday adjustment (AIM_Extractions.md:227):
   - If day_of_week == 0 (Monday) → modifier *= 0.95, tag += "_MONDAY"
5. Return {modifier, confidence, reason_tag}
```

**Spec ref:** AIM_Extractions.md:217-228
**Feature source:** `b1_features.py` — VRP z-score from trailing 60d overnight VRP values

---

### P3-PG-25: AIM-02 Options Skew Modifier

```
Input:  features.pcr_z, features.skew_z
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract pcr_z, skew_z from features
2. If both None → return {modifier: 1.0, confidence: 0.0, reason_tag: "SKEW_MISSING"}
3. Weighted combination:
   - Both available: combined = 0.6 × pcr_z + 0.4 × skew_z, confidence=0.7
   - Only pcr_z:    combined = pcr_z, confidence=0.5
   - Only skew_z:   combined = skew_z, confidence=0.4
4. Threshold logic (DEC-01 spec authoritative):
   - combined > 1.5  → modifier=0.75, tag="SKEW_FEAR_HIGH"
   - combined > 0.5  → modifier=0.90, tag="SKEW_FEAR_ELEVATED"
   - combined < -1.0 → modifier=1.10, tag="SKEW_BULLISH"
   - else             → modifier=1.00, tag="SKEW_NEUTRAL"
5. Return {modifier, confidence, reason_tag}
```

**Spec ref:** AIM_Extractions.md:470-481
**Feature source:** `b1_features.py` — PCR z-score (30d trailing), skew z-score (60d trailing)

---

### P3-PG-26: AIM-03 Gamma Exposure (GEX) Modifier

```
Input:  features.gex
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract gex = features["gex"]
2. If gex is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "GEX_MISSING"}
3. Direction logic (DEC-02 code authoritative):
   - gex > 0 → modifier=0.90, tag="GEX_POSITIVE_DAMPEN"
     (positive gamma dampens volatility → ORB breakout less likely to sustain)
   - gex ≤ 0 → modifier=1.10, tag="GEX_NEGATIVE_AMPLIFY"
     (negative gamma amplifies moves → ORB breakout more reliable)
4. Return {modifier, confidence: 0.7, reason_tag}
```

**Spec ref:** AIM_Extractions.md:731-744
**Decision:** DEC-02 (Code Authoritative) — positive=reduce for ORB breakout momentum

---

### P3-PG-27: AIM-04 IV Term Structure (IVTS) Modifier

```
Input:  features.ivts, features.overnight_return_z, features.is_eia_wednesday
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract ivts = features["ivts"]  (VIX/VXV ratio, inherently normalised)
2. If ivts is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "IVTS_MISSING"}
3. IVTS zone — merged 5-zone per DEC-03:
   - ivts > 1.10       → modifier=0.65, tag="IVTS_SEVERE_BACKWARDATION"
   - ivts > 1.00       → modifier=0.80, tag="IVTS_BACKWARDATION"
   - ivts >= 0.93      → modifier=1.10, tag="IVTS_OPTIMAL" (Paper 67 validated)
   - ivts >= 0.85      → modifier=0.90, tag="IVTS_QUIET"
   - ivts < 0.85       → modifier=0.80, tag="IVTS_DEEP_QUIET"
4. Overnight return gap overlay (F6.1):
   - overnight_return_z > 2.0 → modifier *= 0.85, tag += "_EXTREME_GAP"
   - overnight_return_z > 1.0 → modifier *= 0.95, tag += "_GAP"
5. CL EIA Wednesday overlay (F6.2):
   - If is_eia_wednesday == True → modifier *= 0.90, tag += "_EIA_WEDNESDAY"
6. Return {modifier, confidence, reason_tag}
```

**Spec ref:** AIM_Extractions.md:947-954
**Decision:** DEC-03 (Merged 5-zone, flagged for Isaac)
**Note:** IVTS is VIX/VXV — no z-score needed (inherently normalised ratio)

---

### P3-PG-28: AIM-06 Economic Calendar Modifier

```
Input:  features.event_proximity, features.events_today
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract event_proximity (minutes to nearest event), events_today (list)
2. If no events or proximity is None:
   → return {modifier: 1.0, confidence: 0.3, reason_tag: "NO_EVENTS"}
3. Find max_tier = min(event.tier for events_today)  (lower tier = higher impact)
4. abs_proximity = |event_proximity|
5. Decision tree:
   - Tier 1 AND abs_proximity < 30 → modifier=0.70, tag="MAJOR_EVENT_IMMINENT"
   - Tier 1 AND later in day        → modifier=1.05, tag="MAJOR_EVENT_PREMIUM"
     (Paper 88: pre-FOMC drift, ORB entry before event, exit before impact)
   - Tier 2 AND abs_proximity < 30 → modifier=0.85, tag="MID_EVENT_IMMINENT"
   - Tier 2 AND later in day        → modifier=0.95, tag="MID_EVENT_TODAY"
   - Tier 3+                         → modifier=1.00, tag="LOW_EVENTS_ONLY"
6. Return {modifier, confidence, reason_tag}
```

**Spec ref:** AIM_Extractions.md:1327-1343
**Decision:** F6.3 resolved — Tier 1 later-in-day = 1.05 boost (not 0.80 reduce)

---

### P3-PG-29: AIM-07 Commitment of Traders (COT) Modifier

```
Input:  features.cot_smi, features.cot_speculator_z
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract smi = features["cot_smi"], spec_z = features["cot_speculator_z"]
2. If smi is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "COT_MISSING"}
3. SMI polarity (institutional flow direction):
   - smi == +1 → smi_mod=1.05, tag="COT_INSTITUTIONAL_LONG"
   - smi == -1 → smi_mod=0.90, tag="COT_INSTITUTIONAL_SHORT"
   - else      → smi_mod=1.00, tag="COT_NEUTRAL"
4. Extreme positioning overlay (DEC-01 spec authoritative):
   - spec_z > 1.5  → extreme_mod=0.95, tag+="_CROWDED_LONG"
   - spec_z < -1.5 → extreme_mod=1.10, tag+="_CONTRARIAN"
   - else           → extreme_mod=1.00
5. modifier = smi_mod × extreme_mod
6. Return {modifier, confidence: 0.5, reason_tag}
```

**Spec ref:** AIM_Extractions.md:1541-1559

---

### P3-PG-30: AIM-08 Cross-Asset Correlation Modifier

```
Input:  features.correlation_z
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract corr_z = features["correlation_z"]
2. If corr_z is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "CORR_MISSING"}
3. 4-tier threshold logic (DEC-01 spec authoritative):
   - corr_z > 1.5  → modifier=0.80, tag="CORR_STRESS"
     (correlation spike = diversification collapsed, systemic risk)
   - corr_z > 0.5  → modifier=0.90, tag="CORR_ELEVATED"
   - corr_z < -0.5 → modifier=1.05, tag="CORR_LOW"
     (below-average correlation = diversification benefit strong)
   - else           → modifier=1.00, tag="CORR_NORMAL"
4. Return {modifier, confidence, reason_tag}
```

**Spec ref:** AIM_Extractions.md:1713-1725

---

### P3-PG-31: AIM-09 Cross-Asset Momentum Modifier

```
Input:  features.cross_momentum
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract momentum = features["cross_momentum"]
2. If momentum is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "MOMENTUM_MISSING"}
3. Threshold logic (aggregate MACD alignment score):
   - momentum > 0.5  → modifier=1.10, tag="MOMENTUM_STRONG_UP"
   - momentum < -0.5 → modifier=0.90, tag="MOMENTUM_STRONG_DOWN"
   - else              → modifier=1.00, tag="MOMENTUM_MIXED"
4. Return {modifier, confidence, reason_tag}
```

**Spec ref:** AIM_Extractions.md:1857-1870

---

### P3-PG-32: AIM-10 Calendar Effects Modifier

```
Input:  features.is_opex_window, features.day_of_week
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract is_opex = features["is_opex_window"]
2. If is_opex == True:
   → return {modifier: 0.95, confidence: 0.5, reason_tag: "OPEX_WINDOW"}
3. Else:
   → return {modifier: 1.0, confidence: 0.3, reason_tag: "CALENDAR_NORMAL"}

Note: Monday/Friday DOW adjustments REMOVED per DEC-04
(Paper 124: day-of-week effects have disappeared in modern markets)
```

**Spec ref:** AIM_Extractions.md:2064
**Decision:** DEC-04 — DOW effects removed, OPEX retained at 0.95

---

### P3-PG-33: AIM-11 Regime Warning Modifier

```
Input:  features.vix_z, features.vix_daily_change_z, features.cl_basis
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract vix_z = features["vix_z"]
2. If vix_z is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "VIX_MISSING"}
3. VIX level warning (DEC-01 spec authoritative):
   - vix_z > 1.5  → modifier=0.75, tag="VIX_HIGH_STRESS"
   - vix_z > 0.5  → modifier=0.90, tag="VIX_ELEVATED"
   - vix_z < -0.5 → modifier=1.05, tag="VIX_LOW_STRESS"
   - else          → modifier=1.00, tag="VIX_NORMAL"
4. VIX change overlay (regime transition detection):
   - vix_daily_change_z > 2.0 → modifier *= 0.85, tag += "_SPIKE"
5. CL basis overlay (F1.11: backwardation + elevated VIX = persistent stress):
   - cl_basis < -0.02 AND vix_z > 0.5 → modifier *= 0.90, tag += "_CL_BACKWARDATION"
6. Return {modifier, confidence: 0.8, reason_tag}
```

**Spec ref:** AIM_Extractions.md:2222-2246

---

### P3-PG-34: AIM-12 Dynamic Costs Modifier

```
Input:  features.spread_z, features.vol_z, features.vix_z
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract spread_z, vol_z from features
2. If both None → return {modifier: 1.0, confidence: 0.0, reason_tag: "COST_MISSING"}
3. Default missing signal to 0.0 (neutral for OR/AND logic)
4. Dual-signal threshold (DEC-01 spec authoritative):
   - spread_z > 1.5 OR vol_z > 1.5   → modifier=0.85, tag="COST_HIGH"
   - spread_z > 0.5 OR vol_z > 0.5   → modifier=0.95, tag="COST_ELEVATED"
   - spread_z < -0.5 AND vol_z < -0.5 → modifier=1.05, tag="COST_LOW"
   - else                              → modifier=1.00, tag="COST_NORMAL"
5. VIX overlay (high-vol day = worse fills on stops):
   - vix_z > 1.0 → modifier *= 0.95, tag += "_HIGHVOL"
6. Return {modifier, confidence: 0.6, reason_tag}
```

**Spec ref:** AIM_Extractions.md:2403-2425
**Note:** Uses OR for high-cost detection (either signal sufficient) but AND for low-cost (both must confirm)

---

### P3-PG-35: AIM-15 Opening Volume Modifier

```
Input:  features.opening_volume_ratio
Output: {modifier: float, confidence: float, reason_tag: str}

1. Extract vol_ratio = features["opening_volume_ratio"]
2. If vol_ratio is None → return {modifier: 1.0, confidence: 0.0, reason_tag: "VOLUME_MISSING"}
3. Threshold logic (DEC-01 spec authoritative, AIM_Extractions.md:2904-2913):
   - vol_ratio > 1.5 → modifier=1.15, tag="VOLUME_HIGH"
     (high conviction, strong ORB environment)
   - vol_ratio > 1.0 → modifier=1.05, tag="VOLUME_ABOVE_AVG"
   - vol_ratio < 0.7 → modifier=0.80, tag="VOLUME_LOW"
     (low conviction, ORB signal unreliable)
   - else             → modifier=1.00, tag="VOLUME_NORMAL"
4. Return {modifier, confidence, reason_tag}

Note: vol_ratio = volume_first_m_min(today) / avg(volume_first_m_min(last 20 sessions))
Phase A sets vol_ratio=None (neutral 1.0); Phase B recomputes after OR close (F5.2).
Historical baseline stored in P3-D29, bootstrapped from TopstepX 1-min bars.
```

**Spec ref:** AIM_Extractions.md:2904-2913
**Timing:** Two-phase evaluation (F5.2) — real data only after OR close

---

## AIMs with existing pseudocode (not repeated here)

| AIM | Block | Location |
|-----|-------|----------|
| AIM-13 Sensitivity | P3-PG-12 | Architecture §5 / `b5_sensitivity.py` |
| AIM-14 Auto-Expansion | P3-PG-13 | Architecture §5 / `b4_injection.py` |

## AIMs excluded

| AIM | Reason |
|-----|--------|
| AIM-05 | DEFERRED — no implementation |
| AIM-16 | Removed from B3 per DEC-06 — session budget in Block 5 (`b5_trade_selection.py`) |
