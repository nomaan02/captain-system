# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B3: AIM Aggregation (MoE/DMA) — P3-PG-23 (Task 3.3 / ON lines 660-706).

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
  AIM-16: HMM Opportunity — modifier from Offline B1 (HMM state)

Reads: P3-D01 (aim_states), P3-D02 (aim_weights), features (from B1)
Writes: nothing (pure computation)
"""

import logging

logger = logging.getLogger(__name__)

# Modifier bounds
MODIFIER_FLOOR = 0.5
MODIFIER_CEILING = 1.5


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

    for asset_id in active_assets:
        aim_outputs = {}

        for aim_id in range(1, 17):
            # Check AIM status
            key = (asset_id, aim_id)
            state = aim_states.get("by_asset_aim", {}).get(key)
            if state is None or state["status"] != "ACTIVE":
                continue

            # Check DMA inclusion flag
            weight_data = aim_weights.get(key)
            if weight_data is None or not weight_data.get("inclusion_flag", True):
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

        aim_breakdown[asset_id] = aim_outputs

    active_count = sum(1 for ab in aim_breakdown.values() if ab)
    logger.info("ON-B3: AIM aggregation complete for %d assets (%d with active AIMs)",
                len(active_assets), active_count)

    return {
        "combined_modifier": combined_modifier,
        "aim_breakdown": aim_breakdown,
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
        7: _aim07_cot,
        8: _aim08_correlation,
        9: _aim09_momentum,
        10: _aim10_calendar_effects,
        11: _aim11_regime_warning,
        12: _aim12_costs,
        13: _aim13_sensitivity,
        14: _aim14_expansion,
        15: _aim15_volume,
        16: _aim16_hmm,
    }

    handler = dispatch.get(aim_id)
    if handler is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "NO_HANDLER"}

    try:
        return handler(f, state)
    except Exception as e:
        logger.error("ON-B3: AIM-%02d modifier computation failed for %s: %s", aim_id, asset_id, e)
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "ERROR"}


def _aim01_vrp(f: dict, state: dict) -> dict:
    """AIM-01: VRP modifier. Positive VRP (IV cheap) → boost; negative → reduce."""
    vrp = f.get("vrp")
    if vrp is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VRP_MISSING"}

    if vrp > 0.02:
        return {"modifier": 1.15, "confidence": 0.8, "reason_tag": "VRP_POSITIVE_STRONG"}
    elif vrp > 0:
        return {"modifier": 1.05, "confidence": 0.6, "reason_tag": "VRP_POSITIVE_WEAK"}
    elif vrp > -0.02:
        return {"modifier": 0.95, "confidence": 0.6, "reason_tag": "VRP_NEGATIVE_WEAK"}
    else:
        return {"modifier": 0.85, "confidence": 0.8, "reason_tag": "VRP_NEGATIVE_STRONG"}


def _aim02_skew(f: dict, state: dict) -> dict:
    """AIM-02: Options skew. High PCR + steep skew → bearish caution."""
    pcr = f.get("pcr")
    put_skew = f.get("put_skew")

    if pcr is None and put_skew is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "SKEW_MISSING"}

    modifier = 1.0
    tag = "SKEW_NEUTRAL"

    if pcr is not None:
        if pcr > 1.5:
            modifier -= 0.10
            tag = "PCR_HIGH"
        elif pcr < 0.7:
            modifier += 0.05
            tag = "PCR_LOW"

    if put_skew is not None:
        if put_skew > 0.05:
            modifier -= 0.05
            tag = "SKEW_STEEP" if tag == "SKEW_NEUTRAL" else tag + "_STEEP"

    return {"modifier": modifier, "confidence": 0.6, "reason_tag": tag}


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

    IVTS < 1 → contango (normal), IVTS > 1 → backwardation (stress).
    """
    ivts = f.get("ivts")
    if ivts is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "IVTS_MISSING"}

    if ivts > 1.10:
        return {"modifier": 0.70, "confidence": 0.9, "reason_tag": "IVTS_BACKWARDATION_SEVERE"}
    elif ivts > 1.0:
        return {"modifier": 0.85, "confidence": 0.7, "reason_tag": "IVTS_BACKWARDATION"}
    elif ivts < 0.85:
        return {"modifier": 1.10, "confidence": 0.6, "reason_tag": "IVTS_CONTANGO_DEEP"}
    else:
        return {"modifier": 1.0, "confidence": 0.5, "reason_tag": "IVTS_NORMAL"}


def _aim06_calendar(f: dict, state: dict) -> dict:
    """AIM-06: Economic calendar. Events nearby → reduce sizing."""
    event_proximity = f.get("event_proximity")
    events = f.get("events_today", [])

    if event_proximity is None or not events:
        return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "NO_EVENTS"}

    # Find highest-tier event
    max_tier = min((e.get("tier", 4) for e in events), default=4)

    # Proximity effect: closer events have bigger impact
    abs_proximity = abs(event_proximity) if event_proximity else 999

    if max_tier <= 1 and abs_proximity < 30:
        # Major event (NFP/FOMC) within 30 min
        return {"modifier": 0.60, "confidence": 0.9, "reason_tag": "MAJOR_EVENT_IMMINENT"}
    elif max_tier <= 1 and abs_proximity < 120:
        return {"modifier": 0.80, "confidence": 0.7, "reason_tag": "MAJOR_EVENT_NEAR"}
    elif max_tier <= 2 and abs_proximity < 30:
        return {"modifier": 0.85, "confidence": 0.6, "reason_tag": "MID_EVENT_IMMINENT"}
    elif max_tier <= 2:
        return {"modifier": 0.95, "confidence": 0.4, "reason_tag": "MID_EVENT_TODAY"}
    else:
        return {"modifier": 1.0, "confidence": 0.3, "reason_tag": "LOW_EVENTS_ONLY"}


def _aim07_cot(f: dict, state: dict) -> dict:
    """AIM-07: COT positioning. SMI alignment with strategy direction."""
    smi = f.get("cot_smi")
    spec_z = f.get("cot_speculator_z")

    if smi is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "COT_MISSING"}

    # Positive SMI (institutional net long) → bullish alignment
    modifier = 1.0
    if smi == 1:
        modifier = 1.05
        tag = "COT_INSTITUTIONAL_LONG"
    elif smi == -1:
        modifier = 0.95
        tag = "COT_INSTITUTIONAL_SHORT"
    else:
        tag = "COT_NEUTRAL"

    # Extreme speculator positioning adds caution
    if spec_z is not None and abs(spec_z) > 2.0:
        modifier -= 0.05
        tag += "_EXTREME_SPEC"

    return {"modifier": modifier, "confidence": 0.5, "reason_tag": tag}


def _aim08_correlation(f: dict, state: dict) -> dict:
    """AIM-08: Cross-asset correlation. High correlation z → reduce diversification benefit."""
    corr_z = f.get("correlation_z")

    if corr_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "CORR_MISSING"}

    if corr_z > 2.0:
        return {"modifier": 0.85, "confidence": 0.7, "reason_tag": "CORR_EXTREME_HIGH"}
    elif corr_z < -2.0:
        return {"modifier": 1.10, "confidence": 0.7, "reason_tag": "CORR_EXTREME_LOW"}
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
    """AIM-10: Calendar effects. OPEX window + day-of-week patterns."""
    is_opex = f.get("is_opex_window", False)
    dow = f.get("day_of_week")

    modifier = 1.0
    tag = "CALENDAR_NORMAL"

    if is_opex:
        modifier *= 0.90
        tag = "OPEX_WINDOW"

    # Monday/Friday tend to have different vol profiles
    if dow == 0:  # Monday
        modifier *= 0.95
        tag = "MONDAY" if tag == "CALENDAR_NORMAL" else tag + "_MONDAY"
    elif dow == 4:  # Friday
        modifier *= 0.95
        tag = "FRIDAY" if tag == "CALENDAR_NORMAL" else tag + "_FRIDAY"

    return {"modifier": modifier, "confidence": 0.4, "reason_tag": tag}


def _aim11_regime_warning(f: dict, state: dict) -> dict:
    """AIM-11: Regime warning. VIX z-score signals regime stress."""
    vix_z = f.get("vix_z")
    vix_change_z = f.get("vix_daily_change_z")

    if vix_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VIX_MISSING"}

    modifier = 1.0
    tag = "VIX_NORMAL"

    if vix_z > 2.0:
        modifier = 0.70
        tag = "VIX_EXTREME_HIGH"
    elif vix_z > 1.0:
        modifier = 0.85
        tag = "VIX_ELEVATED"
    elif vix_z < -1.0:
        modifier = 1.10
        tag = "VIX_DEPRESSED"

    # VIX spike adds urgency
    if vix_change_z is not None and vix_change_z > 2.0:
        modifier *= 0.90
        tag += "_SPIKE"

    return {"modifier": modifier, "confidence": 0.8, "reason_tag": tag}


def _aim12_costs(f: dict, state: dict) -> dict:
    """AIM-12: Dynamic costs. Wide spreads → reduce sizing."""
    spread_z = f.get("spread_z")

    if spread_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "SPREAD_MISSING"}

    if spread_z > 2.0:
        return {"modifier": 0.80, "confidence": 0.8, "reason_tag": "SPREAD_WIDE"}
    elif spread_z > 1.0:
        return {"modifier": 0.90, "confidence": 0.6, "reason_tag": "SPREAD_ABOVE_NORMAL"}
    elif spread_z < -1.0:
        return {"modifier": 1.05, "confidence": 0.5, "reason_tag": "SPREAD_TIGHT"}
    else:
        return {"modifier": 1.0, "confidence": 0.4, "reason_tag": "SPREAD_NORMAL"}


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
    """AIM-15: Opening volume. Unusual volume ratio → adjust."""
    vol_ratio = f.get("opening_volume_ratio")

    if vol_ratio is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VOLUME_MISSING"}

    if vol_ratio > 3.0:
        return {"modifier": 1.15, "confidence": 0.7, "reason_tag": "VOLUME_SURGE"}
    elif vol_ratio > 1.5:
        return {"modifier": 1.05, "confidence": 0.5, "reason_tag": "VOLUME_ABOVE_AVG"}
    elif vol_ratio < 0.3:
        return {"modifier": 0.80, "confidence": 0.7, "reason_tag": "VOLUME_VERY_LOW"}
    elif vol_ratio < 0.7:
        return {"modifier": 0.90, "confidence": 0.5, "reason_tag": "VOLUME_BELOW_AVG"}
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


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _clamp(value: float, floor: float, ceiling: float) -> float:
    """Clamp value to [floor, ceiling]."""
    return max(floor, min(ceiling, value))
