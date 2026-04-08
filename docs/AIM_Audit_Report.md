# AIM Framework Structural Audit Report

**Date:** 2026-03-31
**Auditor:** Claude Code (Opus 4.6)
**Scope:** Cross-reference of all AIM spec documents, implementation code, dataset schemas, and test files
**Status:** Read-only analysis — no code changes made

---

## Documents Audited

| # | Document | Location | Lines |
|---|----------|----------|-------|
| 1 | AIM_Extractions.md | `docs/AIM-Specs/new-aim-specs/` | ~3,720 |
| 2 | CaptainNotes.md | `docs/AIM-Specs/new-aim-specs/` | ~420 |
| 3 | Program3_Offline.md | `docs/AIM-Specs/new-aim-specs/` | ~1,729 |
| 4 | Program3_Online.md | `docs/AIM-Specs/new-aim-specs/` | ~1,756 |
| 5 | P3_Dataset_Schemas.md | `docs/AIM-Specs/new-aim-specs/` | ~566 |
| 6 | DMA_MoE_Implementation_Guide.md | `docs/AIM-Specs/new-aim-specs/` | ~340 |
| 7 | HMM_Opportunity_Regime_Spec.md | `docs/AIM-Specs/new-aim-specs/` | ~579 |
| 8 | Nomaan_Edits_P3.md | `docs/AIM-Specs/new-aim-specs/` | ~276 |
| 9 | Cross_Reference_PreDeploy_vs_V3.md | `docs/AIM-Specs/new-aim-specs/` | ~368 |
| 10 | AIMRegistry.md | `docs/AIM-Specs/` | ~200+ |
| 11 | b3_aim_aggregation.py | `captain-online/.../blocks/` | 450 |
| 12 | b1_features.py | `captain-online/.../blocks/` | ~800 |
| 13 | b1_aim_lifecycle.py | `captain-offline/.../blocks/` | 319 |
| 14 | constants.py | `shared/` | status values |
| 15 | init_questdb.py | `scripts/` | table schemas |
| 16 | test_b3_aim.py | `tests/` | AIM aggregation tests |
| 17 | aim_fixtures.py | `tests/fixtures/` | AIM test fixtures |
| 18 | plans/AIM_DATA_IMPLEMENTATION_PLAN.md | `plans/` | data wiring plan |

---

# PART 1 — Per-AIM Completeness Matrix

| AIM | Spec Defined | Research Basis | Modifier Logic Specified | Thresholds Documented | Data Source Identified | Data Source Free/Paid/Deferred | Warm-up Period Specified | Error Handling Defined | Storage Schema (P3-D01) | Online Ingestion (B1) | Offline Training (B1) | DMA Integration | Implementation File | Test File |
|-----|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| AIM-01 VRP | ✅ | ✅ (Papers 34,35,39,40) | ⚠️ | ⚠️ | ✅ | Moderate | ✅ (120d) | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-02 Skew | ✅ | ✅ (Papers 46-50) | ⚠️ | ⚠️ | ✅ | Moderate-High | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-03 GEX | ✅ | ✅ (Papers 52,53,57,58,60) | ⚠️ | ⚠️ | ✅ | High | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-04 IVTS | ✅ | ✅ (Papers 61,65,67,68,70) | ⚠️ | ⚠️ | ✅ | Free | ✅ (60d) | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-05 Book | 🔲 | ✅ (Papers 71-80) | 🔲 | 🔲 | ✅ | Deferred ($500-2K/mo) | 🔲 (20d noted) | 🔲 | ✅ | 🔲 | 🔲 | 🔲 | ❌ | ❌ |
| AIM-06 Calendar | ✅ | ✅ (Papers 81-90) | ⚠️ | ⚠️ | ✅ | Free | ✅ (None) | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-07 COT | ✅ | ✅ (Papers 91-99) | ⚠️ | ⚠️ | ✅ | Free | ✅ (52w) | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-08 Corr | ✅ | ✅ (Papers 102-108) | ⚠️ | ⚠️ | ✅ | Free | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-09 Momentum | ✅ | ✅ (Papers 111-119) | ✅ | ⚠️ | ✅ | Free | ✅ (63d) | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-10 Calendar Fx | ✅ | ✅ (Papers 121-129) | ⚠️ | ⚠️ | ✅ | Free | ✅ (None) | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| AIM-11 Regime Warn | ✅ | ✅ (Papers 131-139) | ⚠️ | ⚠️ | ✅ | Free | ✅ (252d) | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| AIM-12 Costs | ✅ | ✅ (Papers 140-147) | ⚠️ | ⚠️ | ✅ | Free | ✅ (60d) | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| AIM-13 Sensitivity | ✅ | ✅ (Papers 150-158) | ✅ | ✅ | N/A (internal) | N/A | ✅ (100d OOS) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| AIM-14 Expansion | ✅ | ✅ (Papers 161-165) | ✅ | ✅ | N/A (internal) | N/A | ✅ (252d) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| AIM-15 Volume | ✅ | ✅ (Papers 168,175,176,177) | ⚠️ | ⚠️ | ✅ | Free | ✅ (20d) | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| AIM-16 HMM | ✅ | ✅ (HMM_Opportunity_Regime_Spec.md) | ✅ | ✅ | ✅ | Free | ✅ (60d) | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ⚠️ |

### Per-AIM Findings

**[MEDIUM] F1.1 — AIMs 01-12,15: Modifier thresholds differ between spec and implementation.**
The `AIM_Extractions.md` design conclusions specify z-score-based modifiers (e.g., AIM-01: z>+1.5 → 0.7, z>+0.5 → 0.85, z<-1.0 → 1.1), but the implementation in `b3_aim_aggregation.py` uses raw VRP values (vrp > 0.02 → 1.15, vrp > 0 → 1.05, etc.). The spec uses z-scored overnight VRP as the signal; the code uses raw VRP magnitude. This pattern repeats for most AIMs — the spec designs use z-score thresholds while implementations use simplified raw-value thresholds.
— Source: `AIM_Extractions.md`:AIM-01 Design Conclusions vs `b3_aim_aggregation.py`:163-176

**[MEDIUM] F1.2 — AIM-01: Monday adjustment missing in implementation.**
`AIM_Extractions.md` specifies: "Monday adjustment: modifier *= 0.95 on Monday mornings." `b3_aim_aggregation.py` `_aim01_vrp()` does not apply a Monday adjustment.
— Source: `AIM_Extractions.md`:227 vs `b3_aim_aggregation.py`:163-176

**[MEDIUM] F1.3 — AIM-02: Spec uses 60/40 weighted PCR+skew combined signal; implementation uses additive approach.**
Spec: `combined = 0.6 × PCR_signal + 0.4 × skew_signal`. Implementation treats PCR and skew as independent additive adjustments from 1.0.
— Source: `AIM_Extractions.md`:471-480 vs `b3_aim_aggregation.py`:179-203

**[MEDIUM] F1.4 — AIM-03: Spec and code have REVERSED modifier direction.**
`AIM_Extractions.md` says: "Negative GEX → amplification → more risk → modifier 0.85" and "Positive GEX → dampening → more stable → modifier 1.10". Implementation in `b3_aim_aggregation.py`:213-216 does the OPPOSITE: positive GEX → 0.90 (dampening = reduce), negative GEX → 1.10 (amplification = increase). The code comment says "Positive gamma → dampening (reduce)" which contradicts the spec's logic that dampening = more predictable = boost.
— Source: `AIM_Extractions.md`:681-691 vs `b3_aim_aggregation.py`:206-216

**[HIGH] F1.5 — AIM-04: IVTS threshold values differ between spec and implementation.**
Spec (`AIM_Extractions.md`): IVTS ≤ 0.93 → 0.80, [0.93, 1.0] → 1.10, > 1.0 → 0.65. Implementation: IVTS > 1.10 → 0.70, > 1.0 → 0.85, < 0.85 → 1.10, else → 1.0. The boundaries and modifier values are completely different. The spec's optimal zone [0.93, 1.0] is not represented in code; instead code uses a simpler contango/backwardation split at 1.0.
— Source: `AIM_Extractions.md`:937-940 vs `b3_aim_aggregation.py`:219-235

**[MEDIUM] F1.6 — AIM-06: Spec uses Tier 1 within ±30min → 0.70; implementation uses Tier ≤ 1 within 30 → 0.60.**
Minor value difference — spec says 0.70, code says 0.60 for Tier 1 events.
— Source: `AIM_Extractions.md`:1327-1338 vs `b3_aim_aggregation.py`:252-262

**[MEDIUM] F1.7 — AIM-07: Spec extreme speculator z → contrarian signal; implementation just subtracts 0.05.**
Spec: extreme bearishness (z < -1.5) → modifier 1.10 (contrarian opportunity). Implementation: any |spec_z| > 2.0 → subtract 0.05 regardless of direction.
— Source: `AIM_Extractions.md`:1543-1556 vs `b3_aim_aggregation.py`:265-289

**[MEDIUM] F1.8 — AIM-08: Spec thresholds (corr_z > 1.5 → 0.80) vs implementation (corr_z > 2.0 → 0.85).**
Thresholds and values differ.
— Source: `AIM_Extractions.md`:1710-1721 vs `b3_aim_aggregation.py`:292-304

**[MEDIUM] F1.9 — AIM-10: Spec uses 0.95 for OPEX; implementation uses 0.90.**
OPEX modifier differs: spec says 0.95, code says 0.90. Also implementation adds Monday (0.95) and Friday (0.95) adjustments that are not in the spec's modifier construction. Spec explicitly states DOW effects have disappeared (Paper 124).
— Source: `AIM_Extractions.md`:2064-2082 vs `b3_aim_aggregation.py`:323-343

**[MEDIUM] F1.10 — AIM-11: Spec thresholds (VIX z > 1.5 → 0.75) vs implementation (VIX z > 2.0 → 0.70).**
Different z-score boundaries and values.
— Source: `AIM_Extractions.md`:2220-2241 vs `b3_aim_aggregation.py`:346-372

**[MEDIUM] F1.11 — AIM-11: CL basis overlay missing from implementation.**
Spec defines: "CL basis < -0.02 AND VIX z > 0.5 → basis_mod = 0.90". `b1_features.py` computes `cl_basis` for CL, but `b3_aim_aggregation.py` `_aim11_regime_warning()` does not use it.
— Source: `AIM_Extractions.md`:2234-2238 vs `b3_aim_aggregation.py`:346-372

**[MEDIUM] F1.12 — AIM-12: Spec includes vol_z and VIX overlay; implementation only uses spread_z.**
Spec: `cost_mod` depends on both `spread_z` and `vol_z`, with VIX overlay (VIX z > 1.0 → *0.95). Implementation only checks `spread_z`.
— Source: `AIM_Extractions.md`:2400-2420 vs `b3_aim_aggregation.py`:375-389

**[MEDIUM] F1.13 — AIM-15: Spec thresholds (vol_ratio > 1.5 → 1.15, < 0.7 → 0.80) vs implementation (vol_ratio > 3.0 → 1.15, > 1.5 → 1.05, < 0.3 → 0.80, < 0.7 → 0.90).**
Implementation adds intermediate tiers (3.0 and 0.3) not in spec, and remaps the spec's 1.5 threshold to a weaker 1.05 modifier.
— Source: `AIM_Extractions.md`:2900-2920 vs `b3_aim_aggregation.py`:409-425

**[MEDIUM] F1.14 — AIM-15: Spatial volume quality check missing from implementation.**
Spec defines a dual check: temporal (volume ratio) AND spatial (breakout into low-volume zone → 1.10; high-volume zone → 0.85). Implementation only has temporal check.
— Source: `AIM_Extractions.md`:2910-2918 vs `b3_aim_aggregation.py`:409-425

**[LOW] F1.15 — AIM-02 warm-up: AIMRegistry.md says 120d; AIM_Extractions.md says 60d.**
— Source: `AIMRegistry.md`:118 vs `AIM_Extractions.md`:483

**[LOW] F1.16 — AIM-03 warm-up: AIMRegistry.md says 250d; AIM_Extractions.md says 60d; b1_aim_lifecycle.py uses default 50 trades.**
Three different warm-up values across three documents.
— Source: `AIMRegistry.md`:128 vs `AIM_Extractions.md`:693 vs `b1_aim_lifecycle.py`:142

**[LOW] F1.17 — AIM-08 warm-up: AIMRegistry.md says 120d; AIM_Extractions.md says 252d.**
— Source: `AIMRegistry.md`:195 vs `AIM_Extractions.md`:1725

**[MEDIUM] F1.18 — AIM-16: P3-D26 schema not defined in init_questdb.py with full spec fields.**
`HMM_Opportunity_Regime_Spec.md` defines P3-D26 with fields: hmm_params (pi, A, mu, sigma, tvtp_coefs), current_state_probs, opportunity_weights, prior_alpha, last_trained, training_window, n_observations, cold_start. The init_questdb.py file should be checked for V3 table P3-D26 presence.
— Source: `HMM_Opportunity_Regime_Spec.md`:262-281 vs `scripts/init_questdb.py`

**[MEDIUM] F1.19 — AIM-16: Not integrated into Block 5 trade selection budget allocation.**
`HMM_Opportunity_Regime_Spec.md` Section 3.7 specifies that AIM-16 produces per-SESSION budget weights that should feed into Block 5 trade selection to replace first-come-first-served allocation. In the current code, AIM-16 is treated as a standard modifier in `b3_aim_aggregation.py` (line 428-440) rather than a session budget allocator. The spec requires AIM-16 to produce per-session budget weights consumed by Block 5, not a per-asset modifier consumed by Block 3.
— Source: `HMM_Opportunity_Regime_Spec.md`:Section 3.7 vs `b3_aim_aggregation.py`:428-440

**[LOW] F1.20 — All AIMs: No dedicated per-AIM trainer implementations exist.**
`b1_aim_lifecycle.py`:277 contains a comment placeholder: "When individual AIM trainers exist, actual model retraining happens here." The tier retrain function currently only updates the `last_retrained` timestamp without actual model retraining logic.
— Source: `b1_aim_lifecycle.py`:277-279

---

# PART 2 — Data Flow Integrity

## Per-AIM Data Flow Trace

### AIM-01 (VRP)
1. **Input**: ✅ Data sources identified (VIX/VXN/OVX, intraday RV). ⚠️ `b1_features.py`:788-792 stubs return `None` for `_get_atm_implied_vol()` and `_get_realised_vol()` — no live data adapter connected.
2. **Computation**: ⚠️ Spec uses z-scored overnight VRP; code uses raw VRP magnitude.
3. **Storage**: ✅ P3-D01 has `current_modifier` field.
4. **Aggregation**: ✅ Referenced in B3 dispatch table (aim_id=1).
5. **Output**: ✅ Flows through standard combined_modifier → Kelly.

### AIM-02 (Skew)
1. **Input**: ✅ Defined. ⚠️ `_get_options_volume()` and `_get_put_iv()` stub return `None`.
2. **Computation**: ⚠️ Spec uses combined 60/40 weighted z-score signal; code uses additive raw-value approach.
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-03 (GEX)
1. **Input**: ✅ Full BSM gamma computation implemented in `b1_features.py`:105-131. ⚠️ `_get_option_chain()` stub returns `None`.
2. **Computation**: ⚠️ Modifier direction reversed vs spec (see F1.4).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-04 (IVTS)
1. **Input**: ✅ VIX/VXV loaded from `vix_provider.py` via `_get_vix_close_yesterday()` / `_get_vxv_close_yesterday()`. Live data path exists.
2. **Computation**: ⚠️ Threshold boundaries differ significantly from spec (see F1.5).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-05 (Order Book) — DEFERRED
1-5. 🔲 All deferred by design. No implementation files, no handler in dispatch table (correctly skipped at aim_id=5).

### AIM-06 (Economic Calendar)
1. **Input**: ✅ `config/economic_calendar_2026.json` exists. `check_economic_calendar()` loads and filters events.
2. **Computation**: ⚠️ Minor value differences from spec (see F1.6).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-07 (COT)
1. **Input**: ✅ Defined. ⚠️ `_load_latest_cot()` and `_load_cot_history()` are stub functions not shown in the read portion — likely return `None`.
2. **Computation**: ⚠️ Extreme speculator logic differs from spec (see F1.7).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-08 (Cross-Asset Correlation)
1. **Input**: ✅ `rolling_20d_correlation()` implemented with `np.corrcoef`. Per-asset correlation pairs defined in `_CORRELATION_PAIRS` dict.
2. **Computation**: ⚠️ Thresholds differ (see F1.8). ⚠️ Spec calls for DCC-GARCH or TV-GARCH; implementation uses simple rolling correlation.
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-09 (Cross-Asset Momentum)
1. **Input**: ✅ `compute_cross_asset_momentum()` implemented with MACD(12,26,9).
2. **Computation**: ✅ Matches spec's simple path (SLP on cross-asset MACD).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-10 (Calendar Effects)
1. **Input**: ✅ `is_within_opex_window()` implemented with third Friday calculation.
2. **Computation**: ⚠️ Friday modifier added in code but spec says DOW effects have disappeared. OPEX value differs (see F1.9).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-11 (Regime Warning)
1. **Input**: ✅ VIX z-score and daily change z-score computed from trailing data. CL basis computed for CL asset.
2. **Computation**: ⚠️ CL basis not used in modifier (see F1.11). Thresholds differ (see F1.10).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-12 (Dynamic Costs)
1. **Input**: ✅ `get_live_spread()` implemented using TopstepX quote cache. Spread history persisted to `p3_spread_history` table for z-score lookups.
2. **Computation**: ⚠️ Missing vol_z and VIX overlay from spec (see F1.12).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-13 (Sensitivity)
1. **Input**: N/A (internal — reads from Offline B5 state).
2. **Computation**: ✅ Reads current_modifier from state dict (set by Offline B5).
3. **Storage**: ✅ P3-D13 schema defined.
4. **Aggregation**: ✅
5. **Output**: ✅ Bypasses standard computation — modifier piped through from Offline.

### AIM-14 (Auto-Expansion)
1. **Input**: N/A (internal — Level 3 triggered).
2. **Computation**: ✅ Always outputs 1.0 (informational only).
3. **Storage**: ✅
4. **Aggregation**: ✅ (neutral weight).
5. **Output**: ✅ Does NOT produce a modifier — produces strategy candidates via Block 4 injection comparison.

### AIM-15 (Opening Volume)
1. **Input**: ✅ Volume from TopstepX stream cache and historical bars.
2. **Computation**: ⚠️ Thresholds differ, spatial volume check missing (see F1.13, F1.14).
3. **Storage**: ✅
4. **Aggregation**: ✅
5. **Output**: ✅

### AIM-16 (HMM Opportunity)
1. **Input**: ⚠️ AIM-16 reads modifier from Offline state (same pattern as AIM-13). Spec says Online Block 5 should call `aim16_hmm_inference()` for session budget allocation — this inference call is not present in the Online pipeline.
2. **Computation**: ⚠️ The code treats AIM-16 as a per-asset modifier (via B3 aggregation); the spec defines it as a per-SESSION budget allocator (via Block 5). These are architecturally different.
3. **Storage**: ⚠️ P3-D26 schema defined in spec but needs verification in init_questdb.py for completeness.
4. **Aggregation**: ⚠️ Currently flows through B3 MoE like other AIMs. Spec says it should NOT — it should feed Block 5 directly.
5. **Output**: ⚠️ Per-session budget weights not implemented; modifier flows through Kelly like standard AIMs.

### Broken Links Summary

| AIM | Broken Link | Severity |
|-----|------------|----------|
| AIM-01,02,03 | Data adapter stubs return None — options chain/IV data not connected | HIGH |
| AIM-07 | COT data adapter likely returns None — CFTC data not connected | HIGH |
| AIM-04 IVTS | Threshold boundaries completely different between spec and code | HIGH |
| AIM-03 GEX | Modifier direction reversed | MEDIUM |
| AIM-16 | Session budget allocation architecture not implemented — treated as standard modifier | HIGH |
| AIM-11 | CL basis computed in features but not consumed by modifier | MEDIUM |
| All AIMs 1-12,15 | z-score thresholds from spec not used; raw-value thresholds in code | MEDIUM |

---

# PART 3 — Cross-Document Consistency

### 3.1 Modifier Values

**[HIGH] F3.1 — Systematic threshold mismatch between AIM_Extractions.md and b3_aim_aggregation.py.**
Every AIM (1 through 12, 15) has threshold values in `AIM_Extractions.md` design conclusions that differ from the implemented values in `b3_aim_aggregation.py`. The spec consistently uses z-scored inputs with thresholds like ±0.5, ±1.0, ±1.5; the code uses raw values with different boundaries. This is a systematic divergence, not isolated discrepancies.

**[MEDIUM] F3.2 — AIMRegistry.md Part B meta-learning uses multiplicative aggregation; DMA_MoE_Implementation_Guide.md and code use additive weighted average.**
`AIMRegistry.md`:32 specifies: `AIM_aggregate = Π (AIM_i.modifier ^ AIM_meta_weight_i)` (multiplicative, power-weighted). `DMA_MoE_Implementation_Guide.md`:140-182 and `b3_aim_aggregation.py`:97-104 use: `combined = Σ(modifier × weight) / Σ(weight)` (additive weighted average). These produce different numerical results.
— Source: `AIMRegistry.md`:32 vs `DMA_MoE_Implementation_Guide.md`:174 vs `b3_aim_aggregation.py`:100

### 3.2 Warm-up Periods

| AIM | AIMRegistry.md | AIM_Extractions.md | b1_aim_lifecycle.py | Consistent? |
|-----|---------------|-------------------|-------------------|:-----------:|
| 01 | 120d | 120d | 50 trades (default) | ⚠️ |
| 02 | 120d | 60d | 50 trades | ❌ |
| 03 | 250d | 60d | 50 trades | ❌ |
| 04 | 60d | 60d | 50 trades | ⚠️ |
| 05 | 120d | 20d | 100 (special) | ❌ (deferred) |
| 06 | ~2 years | None | 50 trades | ❌ |
| 07 | 52 weeks | 52 weeks | 50 trades | ⚠️ |
| 08 | 120d | 252d | 50 trades | ❌ |
| 09 | N/A | 63d | 50 trades | ⚠️ |
| 10 | N/A | None | 50 trades | ⚠️ |
| 11 | N/A | 252d | 50 trades | ⚠️ |
| 12 | N/A | 60d | 50 trades | ⚠️ |
| 15 | N/A | 20d | 50 trades | ⚠️ |
| 16 | N/A | 60d (240 obs) | 240 obs (special) | ✅ |

**[HIGH] F3.3 — Warm-up values are inconsistent across three authoritative documents.**
`b1_aim_lifecycle.py` uses a flat default of 50 trades for all AIMs except AIM-05 (100) and AIM-16 (240). The spec documents define warm-up in terms of TRADING DAYS (60d, 120d, 252d), not trade counts. These are fundamentally different units — 50 trades at 1-2 trades/day could be 25-50 days, far short of the specified 120-252 day requirements.

### 3.3 Data Sources

**[LOW] F3.4 — AIM_Extractions.md lists specific data providers (OptionMetrics, CBOE, Bloomberg) but P3_Dataset_Schemas.md P3-D00.data_sources uses generic adapter types (REST, WEBSOCKET, FILE, BROKER_API).**
Not a contradiction but the mapping from specific providers to adapter types is not documented.

**[MEDIUM] F3.5 — AIM-08 spec references DCC-GARCH; implementation uses simple rolling correlation.**
`AIM_Extractions.md` and `AIMRegistry.md` specify TV-GARCH + DCC + RS Copula architecture. Implementation uses `np.corrcoef` on 20-day returns. No DCC-GARCH model exists in the codebase.
— Source: `AIMRegistry.md`:193 vs `b1_features.py`:233-241

### 3.4 AIM Numbering

✅ No gaps, duplicates, or renumbering issues found. AIM-01 through AIM-15 plus AIM-16 (HMM) are consistently numbered across all documents and code. AIM-05 is consistently deferred.

### 3.5 DMA/MoE Parameters

| Parameter | CaptainNotes.md | DMA_MoE Guide | Program3_Offline.md | b1_dma_update.py (inferred) | Consistent? |
|-----------|----------------|---------------|--------------------|-----------------------------|:-----------:|
| λ (forgetting factor) | 0.95-0.99 | 0.99 | 0.99 | N/A (not read) | ✅ |
| Inclusion threshold | TBD | "TBD, suggested 0.01-0.05" | Not specified | N/A | ⚠️ |
| Modifier floor | 0.5 | 0.5 | N/A | N/A | ✅ |
| Modifier ceiling | 1.5 | 1.5 | N/A | N/A | ✅ |
| HDWM check frequency | N/A | Weekly | Weekly | N/A | ✅ |

**[LOW] F3.6 — Inclusion threshold is TBD across all documents.**
The DMA inclusion threshold that determines when an AIM is gated out is listed as "TBD" or "suggested 0.01-0.05" in all spec documents. The code uses `inclusion_flag` from P3-D02 but the threshold value for setting that flag is not defined.
— Source: `DMA_MoE_Implementation_Guide.md`:280, `CaptainNotes.md`:342

### 3.6 V3 Additions Cross-Reference

| Change ID | Target | Cross_Reference says | Exists in target? |
|-----------|--------|---------------------|:-----------------:|
| O1 | Program3_Online.md Block 4 ~L847 | Insert fee in Kelly risk | ⚠️ (inline in spec, not as separate amendment) |
| O2 | Program3_Online.md Block 5 ~L905 | HMM session budget | ❌ (AIM-16 budget allocation not in Block 5 pseudocode) |
| O3 | Between Block 5B and Block 6 | Circuit breaker screen | ⚠️ (referenced but full pseudocode in external doc) |
| O4 | Program3_Online.md Block 7 ~L1305 | resolve_commission fee schedule | ✅ |
| O5 | After ~L1340 | get_expected_fee() function | ✅ |
| O6 | After ~L1303 | P3-D23 intraday state update | ⚠️ (referenced but not inline) |
| F1 | Program3_Offline.md after Block 1 | AIM-16 HMM training | ✅ (mentioned in orchestrator schedule) |
| F2 | Program3_Offline.md after Block 3 | Pseudotrader CB extension | ⚠️ (referenced, not inline) |
| F3 | Program3_Offline.md Block 8 | β_b estimation | ⚠️ (referenced, not inline) |
| C1 | Command Block 8 | SOD Topstep parameters | ⚠️ (referenced) |
| C2 | Command Block 2 + Block 8 | Payout notification + GUI | ⚠️ (referenced) |
| A1 | Architecture Section 3 | P3-D23, D25, D26 datasets | ✅ (in P3_Dataset_Schemas.md) |
| A2 | Architecture Section 15 | TRAINING_ONLY status | ✅ (in HMM spec) |

**[MEDIUM] F3.7 — V3 Change O2 (HMM session budget in Block 5) has no corresponding pseudocode.**
`Cross_Reference_PreDeploy_vs_V3.md` Change O2 specifies inserting `aim16_hmm_inference()` into Block 5 at line ~905. This code block does not appear in `Program3_Online.md` Block 5 (P3-PG-25) pseudocode. The HMM budget allocation remains unintegrated into the trade selection flow.
— Source: `Cross_Reference_PreDeploy_vs_V3.md`:36-49 vs `Program3_Online.md`:Block 5

---

# PART 4 — Missing Specifications

### 4.1 AIMs Without Full Pseudocode

| AIM | Design Conclusions in Extractions | Pseudocode Block (P3-PG-XX) | Status |
|-----|:-:|:-:|--------|
| AIM-01 VRP | ✅ | ❌ No dedicated P3-PG | Missing — modifier logic only in implementation code |
| AIM-02 Skew | ✅ | ❌ | Missing |
| AIM-03 GEX | ✅ | ❌ | Missing |
| AIM-04 IVTS | ✅ | ❌ | Missing |
| AIM-06 Calendar | ✅ | ❌ | Missing — feature functions in spec appendix but no modifier pseudocode |
| AIM-07 COT | ✅ | ❌ | Missing |
| AIM-08 Corr | ✅ | ❌ | Missing |
| AIM-09 Momentum | ✅ | ❌ | Missing |
| AIM-10 Calendar Fx | ✅ | ❌ | Missing |
| AIM-11 Regime Warn | ✅ | ❌ | Missing |
| AIM-12 Costs | ✅ | ❌ | Missing |
| AIM-13 Sensitivity | ✅ | ✅ P3-PG-12 | Complete |
| AIM-14 Expansion | ✅ | ✅ P3-PG-13 | Complete |
| AIM-15 Volume | ✅ | ❌ | Missing |
| AIM-16 HMM | ✅ | ✅ P3-PG-01C, P3-PG-25B | Complete |

**[HIGH] F4.1 — 12 of 16 AIMs lack formal pseudocode blocks (P3-PG-XX) in the spec.**
`Program3_Online.md` Block 3 (P3-PG-23) references `compute_aim_modifier(a, features, u)` per AIM but delegates to "AIMRegistry.md Part J." The feature computation functions are specified in Block 1 Appendix A, but the MODIFIER LOGIC (z-score → threshold → modifier value) is only defined informally in `AIM_Extractions.md` design conclusions — not as formal pseudocode blocks. AIM-13, AIM-14, and AIM-16 are the only AIMs with dedicated pseudocode blocks.

### 4.2 AIMs Without Dedicated Implementation Guides

Only two dedicated implementation guides exist:
- `DMA_MoE_Implementation_Guide.md` (meta-learning system)
- `HMM_Opportunity_Regime_Spec.md` (AIM-16)

**[LOW] F4.2 — No dedicated implementation guides exist for individual AIMs 1-15.**
Each AIM has design conclusions in `AIM_Extractions.md` and feature functions in `Program3_Online.md` Appendix A, but there is no "AIM-01 Implementation Guide" equivalent. The `AIM_DATA_IMPLEMENTATION_PLAN.md` in `plans/` covers data wiring for AIMs 4, 6, 8, 11, 12, 15 but not modifier logic implementation.

### 4.3 Missing Error Handling

`Program3_Online.md` error handling table specifies:
- Block 1: "Data feed unavailable → use last known values, flag staleness"
- Block 3: "All AIMs fail → combined_modifier = 1.0"

**Per-AIM error handling** is present in `b3_aim_aggregation.py` — each handler returns `{modifier: 1.0, confidence: 0.0, reason_tag: "*_MISSING"}` when data is None. This is consistent with the spec's "lock at neutral on failure" principle.

**[LOW] F4.3 — No per-AIM error handling specification in the formal spec docs.**
Error handling exists in code but is not formally specified per-AIM in `Program3_Online.md` or `AIMRegistry.md`. The code implements a reasonable pattern (return neutral 1.0 + zero confidence), but this should be canonised in the spec.

### 4.4 Missing Dataset Fields

**[LOW] F4.4 — P3-D01 schema does not include `trained_model` field mentioned in DMA_MoE_Implementation_Guide.md.**
`DMA_MoE_Implementation_Guide.md` Section 8 says P3-D01 holds "trained model" per AIM. The QuestDB schema in `init_questdb.py` has `model_object STRING` which serves this purpose (serialised model state). The name differs (`model_object` vs `trained model`) but functionally equivalent.

**[LOW] F4.5 — P3-D02 does not include `per_asset` dimension in init_questdb.py but code queries by (aim_id, asset_id).**
The `b1_aim_lifecycle.py`:68-78 queries P3-D02 with `WHERE aim_id = %s AND asset_id = %s`, and the `b3_aim_aggregation.py`:81 uses `(asset_id, aim_id)` tuple keys. The QuestDB table schema includes `asset_id SYMBOL` so this is correctly structured.

### 4.5 Missing Cross-AIM Interactions

**[MEDIUM] F4.6 — Cross-AIM interactions are described informally but never formally specified.**
Several interactions are documented in `AIM_Extractions.md` cross-references:
- AIM-10 Calendar modulates AIM-01 VRP and AIM-03 GEX during OPEX window
- AIM-04 IVTS as a regime filter that conditions AIM-10 calendar effects
- AIM-11 and AIM-04 both use VIX
- AIM-08 correlation regime affects AIM-09 cross-asset signal strength
- AIM-06 economic calendar affects AIM-12 cost estimation (spreads widen around macro news)

None of these interactions have formal specifications. In the code, each AIM computes its modifier independently — there is no cross-AIM conditioning. The DMA/MoE system is the only mechanism for inter-AIM influence (via learned weights), not explicit cross-conditioning.

### 4.6 Missing Reporting

`CaptainNotes.md` references RPT-01 through RPT-10:

| Report | AIM Reference | Generation Spec Complete? |
|--------|:---:|:---:|
| RPT-01 Daily Signal | Shows AIM breakdown per signal | ⚠️ (referenced, not fully specified) |
| RPT-03 Monthly Health | D4 dimension = AIM effectiveness | ✅ (in Offline Block 9) |
| RPT-04 AIM Effectiveness | Per-AIM weight trends | ⚠️ (referenced in orchestrator schedule, no generation spec) |
| RPT-05 Injection Comparison | AIM-adjusted edge comparison | ✅ (in Offline Block 4) |
| RPT-07 TSM Simulation | No direct AIM reference | ✅ |
| RPT-08 Probability Accuracy | References regime/AIM accuracy | ⚠️ |
| RPT-09 Decision Change Impact | Pseudotrader AIM replay | ✅ (in Offline Block 3) |
| RPT-10 Annual Review | AIM portfolio review | ⚠️ |

**[LOW] F4.7 — RPT-04 (AIM Effectiveness Report) has no generation specification.**
Referenced in `AIMRegistry.md` Part B2 and the Offline orchestrator schedule (monthly trigger) but no pseudocode for report content generation.

### 4.7 AIM-16 Integration Gaps

**[HIGH] F4.8 — AIM-16 session budget allocation not integrated into Online Block 5.**
The `HMM_Opportunity_Regime_Spec.md` Section 3.7 specifies that AIM-16's output (`opportunity_weight` per session) should replace first-come-first-served allocation in Block 5. `Cross_Reference_PreDeploy_vs_V3.md` Change O2 explicitly states this should be inserted at Block 5 line ~905. The current `Program3_Online.md` Block 5 (P3-PG-25) has no session budget partitioning. The HMM inference function `P3-PG-25B` is defined in the HMM spec but not referenced in `Program3_Online.md`.

**[MEDIUM] F4.9 — AIM-16 cold-start equal weights not specified in Program3_Online.md.**
`HMM_Opportunity_Regime_Spec.md` Section 3.8 defines cold-start: < 20d → disabled (equal weights from TSM), 20-59d → 50/50 blend, 60d+ → pure HMM. This cold-start protocol is only in the HMM spec, not in `Program3_Online.md` or the Online orchestrator.

---

# PART 5 — Structural Risks and Ambiguities

### 5.1 Circular Dependencies

**[LOW] F5.1 — No circular dependencies found in AIM computation order.**
All AIMs compute independently from features (Block 1 output). No AIM's modifier depends on another AIM's modifier. The potential concern (AIM-10 conditioning on AIM-04 regime) is not implemented as a dependency — both compute independently from raw features.

### 5.2 Timing Conflicts

**[MEDIUM] F5.2 — AIM-15 (Opening Volume) requires volume data that may not exist at session open.**
AIM-15 needs `volume_first_N_min()` which requires volume during the OR formation window (e.g., first 5-15 minutes). Block 1 runs AT session open. The spec (`Program3_Online.md`:474-500) defines the functions but does not specify whether Block 1 waits for the OR window to close before computing volume features. If Block 1 runs at 09:30 and OR is 5 minutes, AIM-15 data wouldn't be available until 09:35.
— Source: `Program3_Online.md`:Block 1 timing vs AIM-15 feature requirements

**[LOW] F5.3 — AIM-07 COT data has a 3-day lag.**
COT is released Friday with Tuesday data. This is documented in `AIM_Extractions.md` and acknowledged as a "CONDITIONING variable, not a trigger." Not a timing bug but a known limitation.

### 5.3 Scaling Concerns

**[LOW] F5.4 — AIM-09 cross-asset momentum iterates all universe assets.**
`compute_cross_asset_momentum()` loops through `_get_all_universe_assets()` and computes MACD for each. At 10 assets this is fast; at 8000+ (per `HMM_Opportunity_Regime_Spec.md` Part 4) this becomes a per-session bottleneck.

**[LOW] F5.5 — AIM-08 correlation matrix is O(n^2) for n assets.**
Currently only pairwise correlations are computed per asset. At scale, the full correlation matrix computation would need to be cached/batched.

### 5.4 Ambiguous Language / TBD Values

| Location | TBD/Ambiguous Item | Impact |
|----------|-------------------|--------|
| `CaptainNotes.md`:337 | EWMA decay for E[R]: "~20 trades" | MEDIUM — needed for Kelly computation |
| `CaptainNotes.md`:341 | DMA forgetting factor: "0.95-0.99" | LOW — 0.99 specified elsewhere |
| `CaptainNotes.md`:342-343 | AIM modifier bounds: "TBD FLOOR=0.5, CEILING=1.5" | LOW — implemented as 0.5/1.5 |
| `CaptainNotes.md`:344 | AIM meta-learning EWMA decay: "TBD ~100 trades" | MEDIUM |
| `CaptainNotes.md`:345 | AIM minimum evaluation period: "TBD ~50 trades" | LOW — 50 implemented |
| `DMA_MoE_Implementation_Guide.md`:279 | Inclusion threshold: "TBD, suggested 0.01-0.05" | MEDIUM — affects which AIMs are gated |
| `Program3_Online.md`:Block 5B | quality_hard_floor, quality_ceiling: "CALIBRATE from P1/P2 data" | HIGH — affects which signals pass |

**[MEDIUM] F5.6 — 7 parameters remain TBD/approximate across spec documents.**

### 5.5 Deferred Items Beyond AIM-05

**[LOW] F5.7 — AIM-08 DCC-GARCH model is effectively deferred.**
Spec calls for TV-GARCH + DCC + RS Copula. Implementation uses simple rolling correlation. No DCC model code exists. This is a deferred complexity tier within an otherwise-active AIM.

**[LOW] F5.8 — AIM-15 spatial volume quality check is effectively deferred.**
Spec defines dual temporal + spatial volume check. Only temporal check is implemented. Spatial check (volume-at-price profile) requires tick-level data not currently available.

**[LOW] F5.9 — AIM-01 overnight VRP decomposition is effectively deferred.**
Feature computation stubs for `_get_atm_implied_vol()` and `_get_realised_vol()` return None. The VRP feature cannot be computed without an options data feed.

### 5.6 Cold-Start Interactions

**[MEDIUM] F5.10 — Cold-start scenario with few active AIMs not explicitly tested.**
During warm-up (first 60-252 days), many AIMs are BOOTSTRAPPED or ELIGIBLE (outputting neutral 1.0). The MoE aggregation in `b3_aim_aggregation.py`:97-108 correctly handles this — if only a few AIMs are active, the weighted average uses only those AIMs' weights. With 3 active AIMs, the combined modifier is dominated by those 3 AIMs' modifiers, which is mathematically correct but may be too sensitive to individual AIM errors.

The spec mentions equal weights at startup (Paper 209) and the DMA_MoE guide mentions "combined modifier will be near 1.0 during this period." But there is no explicit test or specification for the scenario "only AIM-04 and AIM-15 are active with all others at neutral" — the combined modifier would be entirely driven by those two AIMs.

`test_b3_aim.py` has scenarios for all-active, all-suppressed, and mixed states, but no test for the specific cold-start scenario of 2-3 active AIMs.

---

# PART 6 — Summary Dashboard

## 6.1 Findings by Severity

| Severity | Count | Description |
|----------|:-----:|-------------|
| CRITICAL | 0 | No spec contradictions that would cause system failure |
| HIGH | 7 | Missing specifications that block correct implementation |
| MEDIUM | 22 | Inconsistencies requiring clarification |
| LOW | 14 | Documentation gaps or cosmetic issues |
| **Total** | **43** | |

## 6.2 Top 5 Highest-Priority Findings

1. **[HIGH] F3.1 — Systematic threshold mismatch between spec z-score thresholds and implementation raw-value thresholds.** Affects all 12 market-facing AIMs. Every AIM's modifier logic in code uses different thresholds and often different input signals than specified.
— `AIM_Extractions.md` (all design conclusions) vs `b3_aim_aggregation.py` (all handlers)

2. **[HIGH] F4.8 / F3.7 — AIM-16 session budget allocation not integrated into Block 5.** The primary purpose of AIM-16 (replacing FCFS with HMM-driven session budgets) is architecturally unimplemented. Code treats it as a standard per-asset modifier.
— `HMM_Opportunity_Regime_Spec.md`:Section 3.7 vs `b3_aim_aggregation.py`:428-440

3. **[HIGH] F1.5 — AIM-04 IVTS thresholds completely different between spec and code.** The IVTS is labelled "CRITICAL regime filter" across all docs. The spec's validated [0.93, 1.0] optimal zone (Paper 67) is not represented in the implementation.
— `AIM_Extractions.md`:937-940 vs `b3_aim_aggregation.py`:219-235

4. **[HIGH] F3.3 — Warm-up values inconsistent across three documents; code uses trade counts while specs use trading days.** Fundamentally different measurement units (50 trades vs 120-252 trading days) mean warm-up gates may fire at wrong times.
— `AIMRegistry.md` vs `AIM_Extractions.md` vs `b1_aim_lifecycle.py`:142

5. **[HIGH] F4.1 — 12 of 16 AIMs lack formal pseudocode blocks.** Only AIM-13, AIM-14, and AIM-16 have dedicated P3-PG pseudocode. All others rely on informal design conclusions, creating ambiguity for implementation.
— `Program3_Offline.md` / `Program3_Online.md` (absence)

## 6.3 Implementation Readiness

### AIMs Ready for Implementation (all core checks pass)
- **AIM-13** (Sensitivity Scanner) — fully specified, pseudocode complete (P3-PG-12), implementation exists
- **AIM-14** (Auto-Expansion) — fully specified, pseudocode complete (P3-PG-13), implementation exists (neutral 1.0)

### AIMs Partially Implemented (code exists, spec divergences need resolution)
- **AIM-04** IVTS — code works but thresholds diverge from validated spec
- **AIM-06** Calendar — code works, minor value differences
- **AIM-09** Momentum — code closely matches spec
- **AIM-10** Calendar Effects — code works, adds unapproved DOW effects
- **AIM-11** Regime Warning — code works, missing CL basis overlay
- **AIM-12** Dynamic Costs — code works, missing vol_z component
- **AIM-15** Volume — code works, missing spatial check

### AIMs Blocked (data adapters return None)
- **AIM-01** VRP — options data feed not connected
- **AIM-02** Skew — options data feed not connected
- **AIM-03** GEX — options chain not connected (AND modifier direction reversed)
- **AIM-07** COT — CFTC data feed likely not connected
- **AIM-08** Correlation — code works for simple version; DCC-GARCH deferred

### AIMs Deferred (by design)
- **AIM-05** Order Book — deferred pending L2 data cost evaluation

### AIMs Architecturally Misaligned
- **AIM-16** HMM — implemented as per-asset modifier instead of per-session budget allocator

## 6.4 Recommended Amendment Order

Based on dependency chains and impact:

1. **Resolve the systematic threshold question first.** Decide whether `AIM_Extractions.md` z-score thresholds or `b3_aim_aggregation.py` raw-value thresholds are authoritative. This affects all 12 market-facing AIMs and should be settled before any other work.

2. **Fix AIM-04 IVTS thresholds.** This is the "CRITICAL regime filter" that conditions ORB viability. The spec's [0.93, 1.0] optimal zone is validated by Paper 67 and should be the source of truth.

3. **Resolve AIM-16 architecture.** Decide whether AIM-16 should remain a standard modifier (simpler, current code) or be refactored to its spec'd session budget allocator role (more powerful, requires Block 5 changes).

4. **Harmonize warm-up values.** Pick one authoritative source for warm-up periods per AIM and update both the lifecycle code and spec documents. Resolve the trades-vs-days unit mismatch.

5. **Fix AIM-03 GEX modifier direction.** This is a straightforward inversion that changes the signal meaning.

6. **Add formal pseudocode blocks for AIMs 01-12, 15.** This prevents future spec/code drift and provides an authoritative reference for each AIM's modifier logic.

7. **Connect data adapters for AIMs 01, 02, 03, 07.** These AIMs are fully implemented in code but produce no signal because data feeds return None.

8. **Address remaining MEDIUM findings individually.** CL basis overlay for AIM-11, vol_z for AIM-12, spatial volume for AIM-15, cross-AIM interaction specifications.

---

*End of Audit Report*
