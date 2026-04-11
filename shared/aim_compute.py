"""AIM computation logic — single source of truth for both live and replay.

Extracted from captain-online/captain_online/blocks/b3_aim_aggregation.py
so that captain-command (replay engine) can also compute AIM modifiers
without cross-container imports.

Aggregates 15 AIM modifiers via Mixture-of-Experts gating with DMA weights.

For each active asset:
  1. Collect outputs from all ACTIVE AIMs (status check + inclusion_flag)
  2. Compute each AIM modifier via compute_aim_modifier()
  3. Weighted aggregation using DMA inclusion probabilities
  4. Clamp combined_modifier to [0.5, 1.5]

AIM modifiers per AIMRegistry.md Part J:
  AIM-01: VRP — modifier based on VRP sign/magnitude
  AIM-02: Skew — modifier based on PCR / put spread
  AIM-03: GEX — modifier based on dealer gamma sign
  AIM-04: IVTS — modifier based on VIX term structure
  AIM-05: DEFERRED
  AIM-06: Economic Calendar — modifier based on event proximity/tier
  AIM-07: COT — modifier based on SMI polarity alignment with direction
  AIM-08: Cross-Asset Corr — modifier based on correlation z-score
  AIM-09: Cross-Asset Momentum — modifier based on momentum alignment
  AIM-10: Calendar Effects — modifier based on OPEX/day-of-week
  AIM-11: Regime Warning — modifier based on VIX z-score
  AIM-12: Dynamic Costs — modifier based on spread z-score
  AIM-13: Sensitivity — modifier from Offline B5 (fragile → 0.85)
  AIM-14: Auto-Expansion — always outputs 1.0
  AIM-15: Opening Volume — modifier based on volume ratio
  AIM-16: HMM Opportunity — REMOVED from B3 per DEC-06; now in Block 5 session budget

Reads: P3-D01 (aim_states), P3-D02 (aim_weights), features (from B1)
Writes: nothing (pure computation)
"""

import logging

logger = logging.getLogger(__name__)

# Modifier bounds
MODIFIER_FLOOR = 0.5
MODIFIER_CEILING = 1.5


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def z_score(value, trailing_series):
    """Standard z-score: (value - mean) / std. None if insufficient data.

    Pure-Python implementation (no numpy) so shared/ stays dependency-light.
    Logic is identical to b1_features.z_score().
    """
    if trailing_series is None or len(trailing_series) < 10:
        return None

    n = len(trailing_series)
    mu = sum(trailing_series) / n
    variance = sum((x - mu) ** 2 for x in trailing_series) / n
    sigma = variance ** 0.5

    if sigma == 0:
        return 0.0

    return (value - mu) / sigma


def _clamp(value: float, floor: float, ceiling: float) -> float:
    """Clamp value to [floor, ceiling]."""
    return max(floor, min(ceiling, value))


# ---------------------------------------------------------------------------
# MoE orchestrator
# ---------------------------------------------------------------------------

def run_aim_aggregation(
    active_assets: list[str],
    features: dict,
    aim_states: dict,
    aim_weights: dict,
) -> dict:
    """P3-PG-23: AIM aggregation via MoE/DMA.

    Args:
        active_assets: list of asset_id strings
        features: {asset_id: {feature_name: value}} from Block 1
        aim_states: from B1 loader (has "by_asset_aim" and "global" keys)
        aim_weights: {(asset_id, aim_id): {inclusion_probability, inclusion_flag, ...}}

    Returns:
        dict with:
          combined_modifier: {asset_id: float}  -- in [0.5, 1.5]
          aim_breakdown: {asset_id: {aim_id: {modifier, confidence, reason_tag, dma_weight}}}
    """
    combined_modifier = {}
    aim_breakdown = {}

    # AIM name lookup for readable logging
    _AIM_NAMES = {
        1: "VRP", 2: "Skew", 3: "GEX", 4: "IVTS", 5: "DEFERRED", 7: "DISABLED",
        6: "EconCal", 7: "COT", 8: "CrossCorr", 9: "CrossMom",
        10: "Calendar", 11: "RegimeWarn", 12: "DynCosts", 13: "Sensitivity",
        14: "AutoExpand", 15: "OpenVol", 16: "HMM",
    }

    for asset_id in active_assets:
        aim_outputs = {}
        skipped = []

        for aim_id in range(1, 17):
            aim_name = _AIM_NAMES.get(aim_id, f"AIM-{aim_id}")
            # Check AIM status
            key = (asset_id, aim_id)
            state = aim_states.get("by_asset_aim", {}).get(key)
            if state is None:
                skipped.append(f"{aim_id:02d}-{aim_name}:NO_STATE")
                continue
            if state["status"] != "ACTIVE":
                skipped.append(f"{aim_id:02d}-{aim_name}:{state['status']}")
                continue

            # Check DMA inclusion flag
            weight_data = aim_weights.get(key)
            if weight_data is None:
                skipped.append(f"{aim_id:02d}-{aim_name}:NO_WEIGHT")
                continue
            if not weight_data.get("inclusion_flag", True):
                skipped.append(f"{aim_id:02d}-{aim_name}:DMA_OFF")
                continue

            # Compute AIM modifier
            result = compute_aim_modifier(aim_id, features, asset_id, state)
            modifier = _clamp(result["modifier"], MODIFIER_FLOOR, MODIFIER_CEILING)

            aim_outputs[aim_id] = {
                "modifier": modifier,
                "confidence": result.get("confidence", 1.0),
                "reason_tag": result.get("reason_tag", ""),
                "dma_weight": weight_data.get("inclusion_probability", 1.0),
            }

        # Log per-asset AIM detail
        if aim_outputs:
            parts = [f"AIM-{k:02d}({_AIM_NAMES.get(k,'')})={v['modifier']:.3f}×{v['dma_weight']:.3f}"
                     for k, v in sorted(aim_outputs.items())]
            logger.info("AIM %s: %s", asset_id, " | ".join(parts))
        if skipped:
            logger.debug("AIM %s skipped: %s", asset_id, ", ".join(skipped))

        # Weighted aggregation
        if aim_outputs:
            total_weight = sum(a["dma_weight"] for a in aim_outputs.values())
            if total_weight > 0:
                weighted_sum = sum(
                    a["modifier"] * (a["dma_weight"] / total_weight)
                    for a in aim_outputs.values()
                )
                combined_modifier[asset_id] = _clamp(weighted_sum, MODIFIER_FLOOR, MODIFIER_CEILING)
            else:
                combined_modifier[asset_id] = 1.0
        else:
            combined_modifier[asset_id] = 1.0  # No active AIMs → neutral
            logger.warning("AIM %s: ALL skipped → combined=1.0 (neutral)", asset_id)

        aim_breakdown[asset_id] = aim_outputs

    active_count = sum(1 for ab in aim_breakdown.values() if ab)
    total_aim_count = sum(len(ab) for ab in aim_breakdown.values())
    logger.info("AIM aggregation: %d assets, %d with active AIMs, %d individual AIMs computed",
                len(active_assets), active_count, total_aim_count)

    # Load session_budget_weights from D26 (spec PG-23 §3: AIM-16 HMM budget)
    session_budget_weights = {}
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """SELECT opportunity_weights, n_observations, cold_start
                   FROM p3_d26_hmm_opportunity_state
                   ORDER BY last_updated DESC LIMIT 1"""
            )
            row = cur.fetchone()
        if row and row[0]:
            import json
            raw = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            n_obs = row[1] or 0
            cold_start = row[2] if row[2] is not None else True
            session_budget_weights = {
                "weights": raw if isinstance(raw, dict) else {},
                "n_observations": n_obs,
                "cold_start": cold_start,
            }
    except Exception as e:
        logger.debug("AIM: Could not load session_budget_weights from D26: %s", e)

    return {
        "combined_modifier": combined_modifier,
        "aim_breakdown": aim_breakdown,
        "session_budget_weights": session_budget_weights,
    }


# ---------------------------------------------------------------------------
# AIM modifier computation — per AIMRegistry.md Part J
# ---------------------------------------------------------------------------

def compute_aim_modifier(aim_id: int, features: dict, asset_id: str, state: dict) -> dict:
    """Compute the modifier for a specific AIM.

    Returns: {modifier: float, confidence: float, reason_tag: str}
    """
    f = features.get(asset_id, {})

    dispatch = {
        1: _aim01_vrp,
        2: _aim02_skew,
        3: _aim03_gex,
        4: _aim04_ivts,
        # 5: DEFERRED
        6: _aim06_calendar,
        # 7: DISABLED per DEC-08 — no CFTC COT data pipeline
        8: _aim08_correlation,
        9: _aim09_momentum,
        10: _aim10_calendar_effects,
        11: _aim11_regime_warning,
        12: _aim12_costs,
        13: _aim13_sensitivity,
        14: _aim14_expansion,
        15: _aim15_volume,
        16: _aim16_hmm,  # DEC-06 resolved: re-added — Online B3 needs HMM inference
    }

    handler = dispatch.get(aim_id)
    if handler is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "NO_HANDLER"}

    try:
        return handler(f, state)
    except Exception as e:
        logger.error("AIM-%02d modifier computation failed for %s: %s", aim_id, asset_id, e)
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "ERROR"}


# ---------------------------------------------------------------------------
# Individual AIM handler functions
# ---------------------------------------------------------------------------

def _aim01_vrp(f: dict, state: dict) -> dict:
    """AIM-01: VRP modifier — z-scored overnight VRP per AIM_Extractions.md:217-228.

    Thresholds (DEC-01 spec authoritative):
      z > +1.5 → 0.70  (high uncertainty, reduce sizing)
      z > +0.5 → 0.85
      z < -1.0 → 1.10  (low uncertainty, slight increase)
      else     → 1.00  (neutral)

    Monday adjustment (F1.2): modifier *= 0.95 on Monday mornings.
    """
    vrp_z = f.get("vrp_overnight_z")
    if vrp_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VRP_MISSING"}

    if vrp_z > 1.5:
        modifier = 0.70
        confidence = 0.8
        tag = "VRP_HIGH_UNCERTAINTY"
    elif vrp_z > 0.5:
        modifier = 0.85
        confidence = 0.7
        tag = "VRP_ELEVATED"
    elif vrp_z < -1.0:
        modifier = 1.10
        confidence = 0.6
        tag = "VRP_LOW_UNCERTAINTY"
    else:
        modifier = 1.0
        confidence = 0.5
        tag = "VRP_NEUTRAL"

    # Monday adjustment: weekend uncertainty accumulation (AIM_Extractions.md:227)
    dow = f.get("day_of_week")
    if dow == 0:  # Monday
        modifier *= 0.95
        tag += "_MONDAY"

    return {"modifier": modifier, "confidence": confidence, "reason_tag": tag}


def _aim02_skew(f: dict, state: dict) -> dict:
    """AIM-02: Skew — weighted z-score combination per AIM_Extractions.md:470-481.

    combined = 0.6 × z_score(PCR, 30d) + 0.4 × z_score(skew, 60d)

    Thresholds (DEC-01 spec authoritative):
      combined > +1.5 → 0.75  (heavy put buying + steep skew = high fear)
      combined > +0.5 → 0.90
      combined < -1.0 → 1.10  (call-heavy + flat skew = bullish)
      else            → 1.00
    """
    pcr_z = f.get("pcr_z")
    skew_z = f.get("skew_z")

    if pcr_z is None and skew_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "SKEW_MISSING"}

    # Weighted combination — degrade gracefully if one signal missing
    if pcr_z is not None and skew_z is not None:
        combined = 0.6 * pcr_z + 0.4 * skew_z
        confidence = 0.7
    elif pcr_z is not None:
        combined = pcr_z
        confidence = 0.5
    else:
        combined = skew_z
        confidence = 0.4

    if combined > 1.5:
        return {"modifier": 0.75, "confidence": confidence, "reason_tag": "SKEW_FEAR_HIGH"}
    elif combined > 0.5:
        return {"modifier": 0.90, "confidence": confidence, "reason_tag": "SKEW_FEAR_ELEVATED"}
    elif combined < -1.0:
        return {"modifier": 1.10, "confidence": confidence, "reason_tag": "SKEW_BULLISH"}
    else:
        return {"modifier": 1.0, "confidence": confidence, "reason_tag": "SKEW_NEUTRAL"}


def _aim03_gex(f: dict, state: dict) -> dict:
    """AIM-03: GEX. Positive gamma → dampening (reduce); negative → amplification."""
    gex = f.get("gex")
    if gex is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "GEX_MISSING"}

    # Normalise: positive gamma reduces vol, negative amplifies
    if gex > 0:
        return {"modifier": 0.90, "confidence": 0.7, "reason_tag": "GEX_POSITIVE_DAMPEN"}
    else:
        return {"modifier": 1.10, "confidence": 0.7, "reason_tag": "GEX_NEGATIVE_AMPLIFY"}


def _aim04_ivts(f: dict, state: dict) -> dict:
    """AIM-04: IVTS (CRITICAL regime filter).

    Merged 5-zone per DEC-03 (Paper 67 validated optimal zone):
      >1.10       → 0.65  severe backwardation (turmoil)
      (1.0, 1.10] → 0.80  backwardation
      [0.93, 1.0] → 1.10  optimal (Paper 67 validated)
      [0.85, 0.93)→ 0.90  quiet
      <0.85       → 0.80  deep quiet (costs dominate)

    Overnight return gap overlay (AIM_Extractions.md:947-952):
      overnight_z > 2.0 → ×0.85  (extreme gap, expect reversal/volatility)
      overnight_z > 1.0 → ×0.95
      else               → ×1.0

    IVTS = VIX/VXV — inherently normalised, no z-score needed.
    """
    ivts = f.get("ivts")
    if ivts is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "IVTS_MISSING"}

    # IVTS zone (primary)
    if ivts > 1.10:
        modifier = 0.65
        confidence = 0.9
        tag = "IVTS_SEVERE_BACKWARDATION"
    elif ivts > 1.0:
        modifier = 0.80
        confidence = 0.8
        tag = "IVTS_BACKWARDATION"
    elif ivts >= 0.93:
        modifier = 1.10
        confidence = 0.9
        tag = "IVTS_OPTIMAL"
    elif ivts >= 0.85:
        modifier = 0.90
        confidence = 0.6
        tag = "IVTS_QUIET"
    else:
        modifier = 0.80
        confidence = 0.6
        tag = "IVTS_DEEP_QUIET"

    # Overnight return gap overlay (spec: AIM_Extractions.md:947-952)
    overnight_z = f.get("overnight_return_z")
    if overnight_z is not None:
        if overnight_z > 2.0:
            modifier *= 0.85
            tag += "_EXTREME_GAP"
        elif overnight_z > 1.0:
            modifier *= 0.95
            tag += "_GAP"

    # CL EIA Wednesday overlay (spec: AIM_Extractions.md:954)
    if f.get("is_eia_wednesday"):
        modifier *= 0.90
        tag += "_EIA_WEDNESDAY"

    return {"modifier": modifier, "confidence": confidence, "reason_tag": tag}


def _aim06_calendar(f: dict, state: dict) -> dict:
    """AIM-06: Economic calendar — per AIM_Extractions.md:1327-1343.

    Tier 1 within ±30min → 0.70 (DEC-01 spec authoritative).
    Tier 1 later in day  → 1.05 (pre-announcement risk premium, Paper 88).
    Tier 2 within ±30min → 0.85 (matches spec).
    """
    event_proximity = f.get("event_proximity")
    events = f.get("events_today", [])

    if event_proximity is None or not events:
        return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "NO_EVENTS"}

    # Find highest-tier event
    max_tier = min((e.get("tier", 4) for e in events), default=4)

    # Proximity effect: closer events have bigger impact
    abs_proximity = abs(event_proximity) if event_proximity else 999

    if max_tier <= 1 and abs_proximity < 30:
        # Major event (NFP/FOMC) within 30 min — spec: 0.70
        return {"modifier": 0.70, "confidence": 0.9, "reason_tag": "MAJOR_EVENT_IMMINENT"}
    elif max_tier <= 1:
        # Tier 1 later in day — pre-announcement risk premium (spec: AIM_Extractions.md:1333-1334)
        return {"modifier": 1.05, "confidence": 0.6, "reason_tag": "MAJOR_EVENT_PREMIUM"}
    elif max_tier <= 2 and abs_proximity < 30:
        return {"modifier": 0.85, "confidence": 0.6, "reason_tag": "MID_EVENT_IMMINENT"}
    elif max_tier <= 2:
        return {"modifier": 0.95, "confidence": 0.4, "reason_tag": "MID_EVENT_TODAY"}
    else:
        return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "LOW_EVENTS_ONLY"}


def _aim07_cot(f: dict, state: dict) -> dict:
    """AIM-07: COT positioning — per AIM_Extractions.md:1541-1559.

    SMI polarity: POSITIVE→1.05, NEGATIVE→0.90.
    Extreme overlay (DEC-01 spec authoritative):
      spec_z > 1.5  → ×0.95 (crowded long, elevated risk)
      spec_z < -1.5 → ×1.10 (extreme bearishness, contrarian opportunity)
    modifier = smi_mod × extreme_mod
    """
    smi = f.get("cot_smi")
    spec_z = f.get("cot_speculator_z")

    if smi is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "COT_MISSING"}

    # SMI polarity (spec: lines 1547-1550)
    if smi == 1:
        smi_mod = 1.05
        tag = "COT_INSTITUTIONAL_LONG"
    elif smi == -1:
        smi_mod = 0.90
        tag = "COT_INSTITUTIONAL_SHORT"
    else:
        smi_mod = 1.0
        tag = "COT_NEUTRAL"

    # Extreme positioning overlay — direction-aware (spec: lines 1552-1557)
    extreme_mod = 1.0
    if spec_z is not None:
        if spec_z > 1.5:
            extreme_mod = 0.95
            tag += "_CROWDED_LONG"
        elif spec_z < -1.5:
            extreme_mod = 1.10
            tag += "_CONTRARIAN"

    modifier = smi_mod * extreme_mod
    return {"modifier": modifier, "confidence": 0.5, "reason_tag": tag}


def _aim08_correlation(f: dict, state: dict) -> dict:
    """AIM-08: Cross-asset correlation — 4-tier per AIM_Extractions.md:1713-1725.

    Thresholds (DEC-01 spec authoritative):
      corr_z > 1.5  → 0.80  (stress: correlation spike, diversification collapsed)
      corr_z > 0.5  → 0.90  (elevated, caution)
      corr_z < -0.5 → 1.05  (below average, diversification benefit strong)
      else          → 1.00
    """
    corr_z = f.get("correlation_z")

    if corr_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "CORR_MISSING"}

    if corr_z > 1.5:
        return {"modifier": 0.80, "confidence": 0.7, "reason_tag": "CORR_STRESS"}
    elif corr_z > 0.5:
        return {"modifier": 0.90, "confidence": 0.6, "reason_tag": "CORR_ELEVATED"}
    elif corr_z < -0.5:
        return {"modifier": 1.05, "confidence": 0.5, "reason_tag": "CORR_LOW"}
    else:
        return {"modifier": 1.0, "confidence": 0.4, "reason_tag": "CORR_NORMAL"}


def _aim09_momentum(f: dict, state: dict) -> dict:
    """AIM-09: Cross-asset momentum. Aggregate MACD alignment."""
    momentum = f.get("cross_momentum")

    if momentum is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "MOMENTUM_MISSING"}

    # Strong net positive → trend environment
    if momentum > 0.5:
        return {"modifier": 1.10, "confidence": 0.6, "reason_tag": "MOMENTUM_STRONG_UP"}
    elif momentum < -0.5:
        return {"modifier": 0.90, "confidence": 0.6, "reason_tag": "MOMENTUM_STRONG_DOWN"}
    else:
        return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "MOMENTUM_MIXED"}


def _aim10_calendar_effects(f: dict, state: dict) -> dict:
    """AIM-10: Calendar effects — per AIM_Extractions.md:2064 + DEC-04.

    OPEX window → 0.95 (spec; was 0.90 in code).
    Monday/Friday DOW adjustments REMOVED (DEC-04: Paper 124 shows DOW effects disappeared).
    """
    is_opex = f.get("is_opex_window", False)

    if is_opex:
        return {"modifier": 0.95, "confidence": 0.5, "reason_tag": "OPEX_WINDOW"}

    return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "CALENDAR_NORMAL"}


def _aim11_regime_warning(f: dict, state: dict) -> dict:
    """AIM-11: Regime warning — VIX z-score per AIM_Extractions.md:2222-2246.

    Thresholds (DEC-01 spec authoritative):
      VIX_z > 1.5  → 0.75  (high transition probability to stress)
      VIX_z > 0.5  → 0.90  (elevated)
      VIX_z < -0.5 → 1.05  (low stress probability)
      else         → 1.00

    VIX change overlay: VIX_change_z > 2.0 → ×0.85 (regime shift in progress).
    CL basis overlay (F1.11): basis < -0.02 AND VIX_z > 0.5 → ×0.90.
    """
    vix_z = f.get("vix_z")
    vix_change_z = f.get("vix_daily_change_z")

    if vix_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VIX_MISSING"}

    # VIX level warning
    if vix_z > 1.5:
        modifier = 0.75
        tag = "VIX_HIGH_STRESS"
    elif vix_z > 0.5:
        modifier = 0.90
        tag = "VIX_ELEVATED"
    elif vix_z < -0.5:
        modifier = 1.05
        tag = "VIX_LOW_STRESS"
    else:
        modifier = 1.0
        tag = "VIX_NORMAL"

    # VIX change overlay: regime transition in progress (spec: ×0.85)
    if vix_change_z is not None and vix_change_z > 2.0:
        modifier *= 0.85
        tag += "_SPIKE"

    # CL basis overlay (F1.11): backwardation + elevated VIX = persistent stress
    cl_basis = f.get("cl_basis")
    if cl_basis is not None and cl_basis < -0.02 and vix_z > 0.5:
        modifier *= 0.90
        tag += "_CL_BACKWARDATION"

    return {"modifier": modifier, "confidence": 0.8, "reason_tag": tag}


def _aim12_costs(f: dict, state: dict) -> dict:
    """AIM-12: Dynamic costs — per AIM_Extractions.md:2403-2425.

    Uses BOTH spread_z AND vol_z (OR for high cost, AND for low cost).
    Thresholds (DEC-01 spec authoritative):
      spread_z > 1.5 OR vol_z > 1.5  → 0.85
      spread_z > 0.5 OR vol_z > 0.5  → 0.95
      spread_z < -0.5 AND vol_z < -0.5 → 1.05
      else → 1.0
    VIX overlay: VIX_z > 1.0 → ×0.95.
    """
    spread_z = f.get("spread_z")
    vol_z = f.get("vol_z")

    if spread_z is None and vol_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "COST_MISSING"}

    # Default to 0 when one signal missing (neutral for OR/AND logic)
    sz = spread_z if spread_z is not None else 0.0
    vz = vol_z if vol_z is not None else 0.0

    if sz > 1.5 or vz > 1.5:
        modifier = 0.85
        tag = "COST_HIGH"
    elif sz > 0.5 or vz > 0.5:
        modifier = 0.95
        tag = "COST_ELEVATED"
    elif sz < -0.5 and vz < -0.5:
        modifier = 1.05
        tag = "COST_LOW"
    else:
        modifier = 1.0
        tag = "COST_NORMAL"

    # High-vol day overlay (spec: VIX_z > 1.0 → worse fills on stops)
    vix_z = f.get("vix_z")
    if vix_z is not None and vix_z > 1.0:
        modifier *= 0.95
        tag += "_HIGHVOL"

    return {"modifier": modifier, "confidence": 0.6, "reason_tag": tag}


def _aim13_sensitivity(f: dict, state: dict) -> dict:
    """AIM-13: Sensitivity (from Offline B5). FRAGILE → 0.85 modifier."""
    # Sensitivity result is in the AIM state's current_modifier from Offline
    current = state.get("current_modifier")
    if current is not None and isinstance(current, dict):
        modifier = current.get("modifier", 1.0)
        tag = current.get("reason_tag", "SENSITIVITY_FROM_OFFLINE")
        return {"modifier": modifier, "confidence": 0.7, "reason_tag": tag}

    return {"modifier": 1.0, "confidence": 0.5, "reason_tag": "SENSITIVITY_NORMAL"}


def _aim14_expansion(f: dict, state: dict) -> dict:
    """AIM-14: Auto-expansion. Always outputs 1.0 (informational only)."""
    return {"modifier": 1.0, "confidence": 1.0, "reason_tag": "EXPANSION_NEUTRAL"}


def _aim15_volume(f: dict, state: dict) -> dict:
    """AIM-15: Opening volume — per AIM_Extractions.md:2904-2913.

    Thresholds (DEC-01 spec authoritative):
      vol_ratio > 1.5 → 1.15  (high conviction, strong ORB environment)
      vol_ratio > 1.0 → 1.05  (above average, moderate confirmation)
      vol_ratio < 0.7 → 0.80  (low conviction, ORB signal unreliable)
      else            → 1.00
    """
    vol_ratio = f.get("opening_volume_ratio")

    if vol_ratio is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VOLUME_MISSING"}

    if vol_ratio > 1.5:
        return {"modifier": 1.15, "confidence": 0.7, "reason_tag": "VOLUME_HIGH"}
    elif vol_ratio > 1.0:
        return {"modifier": 1.05, "confidence": 0.5, "reason_tag": "VOLUME_ABOVE_AVG"}
    elif vol_ratio < 0.7:
        return {"modifier": 0.80, "confidence": 0.7, "reason_tag": "VOLUME_LOW"}
    else:
        return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "VOLUME_NORMAL"}


def _aim16_hmm(f: dict, state: dict) -> dict:
    """AIM-16: HMM Opportunity (from Offline B1 HMM training).

    Modifier is read from the AIM state — Offline computes the HMM-based
    opportunity weight and stores it as current_modifier.
    """
    current = state.get("current_modifier")
    if current is not None and isinstance(current, dict):
        modifier = current.get("modifier", 1.0)
        tag = current.get("reason_tag", "HMM_FROM_OFFLINE")
        return {"modifier": modifier, "confidence": 0.6, "reason_tag": tag}

    return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "HMM_NO_DATA"}
