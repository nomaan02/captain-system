# DMA/MoE Meta-Learning Implementation Guide — AIM Aggregation

**Purpose:** Implementation guide for Nomaan covering the Dynamic Model Averaging (DMA) and Mixture-of-Experts (MoE) system that learns which AIMs to trust and how to combine their outputs.
**Spec reference:** `Program3_Offline.md` Block 1 (P3-PG-01 through P3-PG-04), `Program3_Online.md` Block 3 (P3-PG-23)
**Research basis:** Papers 187 (DMA with forgetting factors), 189 (AREBA rare event preservation), 190 (HDWM heterogeneous ensembles), 191 (AutoEncoder + ADWIN drift detection), 209 (equal weight initialisation), 211 (MoE selective gating)

---

## 1. WHAT THE META-LEARNING SYSTEM DOES

The Captain has 15 Auxiliary Intelligence Modules (AIMs). Each AIM produces a "modifier" — a multiplier that says "conditions are favourable (>1.0)" or "unfavourable (<1.0)" for a particular trade.

The meta-learning system answers: **"How much should we trust each AIM's opinion today?"**

It learns this from trade outcomes. If AIM-01 said "size up" and the trade was profitable, AIM-01's weight increases. If it said "size up" and the trade lost money, its weight decreases. The system adapts automatically — no manual tuning of AIM weights.

---

## 2. ARCHITECTURE OVERVIEW

```
15 AIMs → [DMA Inclusion Probabilities] → [MoE Gating] → combined_modifier
              ↑ learns from trade outcomes         ↑ learns from trade outcomes
              (Offline Block 1)                    (Online Block 3)
```

**Two-layer architecture:**
- **DMA (Offline, P3-PG-02):** Learns long-term inclusion probabilities — which AIMs are generally useful. Updates after each trade outcome. Slow-moving.
- **MoE Gating (Online, P3-PG-23):** Combines AIM modifiers for the current session evaluation using DMA weights. Fast.

**HDWM (Offline, P3-PG-03):** Ensures diversity — prevents DMA from killing all AIMs of a particular type.

**Drift Detection (Offline, P3-PG-04):** Detects when an AIM's input data distribution has shifted, triggering a temporary weight reduction and flagging for retraining.

---

## 3. DMA — DYNAMIC MODEL AVERAGING (Offline)

### 3.1 Core Update (P3-PG-02)

After each trade outcome, update every active AIM's inclusion probability:

```python
def update_dma(
    trade_outcome: TradeOutcome,
    aim_states: dict,     # P3-D01
    meta_weights: dict,   # P3-D02
    ewma_states: dict,    # P3-D05
    forgetting_factor: float = 0.99  # OPEN PARAMETER
):
    """
    DMA with forgetting factor (Paper 187):
    - Each AIM has an inclusion probability in [0, 1]
    - After each trade, probabilities are updated based on how well
      each AIM's prediction aligned with the outcome
    - Forgetting factor controls adaptation speed:
      0.99 = slow (remembers ~100 trades)
      0.95 = fast (remembers ~20 trades)
    """
    
    asset = trade_outcome.asset
    regime = trade_outcome.regime_state
    pnl_pc = trade_outcome.pnl / max(trade_outcome.contracts, 1)
    
    raw_probs = {}
    
    for aim_id in get_active_aims():
        # Step 1: Get what this AIM predicted at trade time
        modifier = get_aim_modifier_at_trade_time(aim_id, trade_outcome.timestamp)
        
        # Step 2: Compute likelihood — how well did the prediction match reality?
        likelihood = compute_magnitude_weighted_likelihood(
            modifier, pnl_pc, ewma_states[asset][regime]
        )
        
        # Step 3: Apply forgetting factor and likelihood
        # P(AIM_a | data) ∝ P(AIM_a | data_{t-1})^λ × P(x_t | AIM_a)
        raw_probs[aim_id] = meta_weights[aim_id].inclusion_probability ** forgetting_factor * likelihood
    
    # Step 4: Normalise
    total = sum(raw_probs.values())
    for aim_id in raw_probs:
        meta_weights[aim_id].inclusion_probability = raw_probs[aim_id] / total
        meta_weights[aim_id].inclusion_flag = (
            meta_weights[aim_id].inclusion_probability > INCLUSION_THRESHOLD
        )
```

### 3.2 Magnitude-Weighted Likelihood (SPEC-A9)

Standard DMA treats all correct/incorrect predictions equally. SPEC-A9 makes the update proportional to how much money was made or lost:

```python
def compute_magnitude_weighted_likelihood(
    modifier: float,
    pnl_per_contract: float,
    ewma_state  # for normalisation
) -> float:
    """
    If AIM said "size up" (modifier > 1.0):
      - Big win → high likelihood (AIM was right AND it mattered)
      - Small win → moderate likelihood
      - Loss → low likelihood (AIM was wrong)
    
    If AIM said "size down" (modifier < 1.0):
      - Big loss → high likelihood (AIM correctly flagged danger)
      - Small loss → moderate likelihood
      - Win → low likelihood (AIM missed a good trade)
    
    z-score normalisation prevents outlier trades from dominating.
    """
    if modifier > 1.0:
        if pnl_per_contract > 0:
            z = min(pnl_per_contract / max(ewma_state.avg_win, 0.01), 3.0)
            return 0.5 + 0.5 * z / 3.0  # range: [0.5, 1.0]
        else:
            z = min(abs(pnl_per_contract) / max(ewma_state.avg_loss, 0.01), 3.0)
            return 0.5 - 0.5 * z / 3.0  # range: [0.0, 0.5]
    
    elif modifier < 1.0:
        if pnl_per_contract < 0:
            z = min(abs(pnl_per_contract) / max(ewma_state.avg_loss, 0.01), 3.0)
            return 0.5 + 0.5 * z / 3.0
        else:
            z = min(pnl_per_contract / max(ewma_state.avg_win, 0.01), 3.0)
            return 0.5 - 0.5 * z / 3.0
    
    else:
        return 0.5  # neutral — no prediction to evaluate
```

---

## 4. MoE GATING — ONLINE AGGREGATION (Block 3)

### 4.1 Combined Modifier Computation (P3-PG-23)

At each session evaluation, combine all AIM modifiers into a single number:

```python
def compute_combined_modifier(
    aim_states: dict,       # P3-D01 (current modifier per AIM per asset)
    meta_weights: dict,     # P3-D02 (DMA inclusion probabilities)
    asset: str,
    modifier_floor: float = 0.5,
    modifier_ceiling: float = 1.5
) -> tuple[float, dict]:
    """
    Returns:
    - combined_modifier: single float in [0.5, 1.5]
    - aim_breakdown: dict of {aim_id: (modifier, weight, contribution)}
    """
    weighted_sum = 0.0
    weight_sum = 0.0
    breakdown = {}
    
    for aim_id in get_active_aims():
        if not meta_weights[aim_id].inclusion_flag:
            continue  # DMA suppressed this AIM
        
        modifier = aim_states[aim_id].get_modifier(asset)
        weight = meta_weights[aim_id].inclusion_probability
        
        contribution = modifier * weight
        weighted_sum += contribution
        weight_sum += weight
        
        breakdown[aim_id] = {
            "modifier": modifier,
            "weight": weight,
            "contribution": contribution
        }
    
    if weight_sum > 0:
        combined = weighted_sum / weight_sum
    else:
        combined = 1.0  # no active AIMs — neutral
    
    # Bound to prevent extreme sizing
    combined = max(modifier_floor, min(modifier_ceiling, combined))
    
    return combined, breakdown
```

---

## 5. HDWM DIVERSITY MAINTENANCE (Offline)

### 5.1 Weekly Diversity Check (P3-PG-03)

Prevents DMA from suppressing all AIMs of a particular type, which would leave the system blind to an entire category of information:

```python
SEED_TYPES = {
    "options":       [1, 2, 3],       # AIM-01, 02, 03
    "microstructure": [4, 5, 15],     # AIM-04, 05, 15
    "macro_event":   [6, 7],          # AIM-06, 07
    "cross_asset":   [8, 9],          # AIM-08, 09
    "temporal":      [10, 11],        # AIM-10, 11
    "internal":      [12, 13, 14]     # AIM-12, 13, 14
}

def diversity_check(aim_states, meta_weights):
    for type_name, aim_ids in SEED_TYPES.items():
        active_in_type = [a for a in aim_ids if aim_states[a].status == "ACTIVE"]
        
        if len(active_in_type) == 0:
            # All AIMs of this type suppressed — force one back
            best = max(aim_ids, key=lambda a: meta_weights[a].recent_effectiveness)
            aim_states[best].status = "ACTIVE"
            meta_weights[best].inclusion_probability = 1.0 / count_active_aims()
            log(f"HDWM diversity recovery: reactivated AIM-{best} as seed for {type_name}")
```

---

## 6. DRIFT DETECTION (Offline)

### 6.1 Per-AIM Drift Monitoring (P3-PG-04)

Each active AIM has an AutoEncoder trained on its input feature distribution. Daily, the AutoEncoder reconstructs today's features. If reconstruction error suddenly increases, the input distribution has shifted — the AIM's model may be stale.

```python
def check_aim_drift(aim_id, today_features, autoencoder, adwin_state, meta_weights):
    """
    AutoEncoder: trained on historical feature values during AIM training.
    Reconstruction error = how different today's features are from training data.
    ADWIN: monitors the reconstruction error stream for structural change.
    """
    reconstruction_error = autoencoder[aim_id].reconstruct_error(today_features)
    
    adwin_state[aim_id].add(reconstruction_error)
    
    if adwin_state[aim_id].detected_change():
        log(f"Concept drift detected in AIM-{aim_id}")
        # Temporarily reduce weight
        meta_weights[aim_id].inclusion_probability *= 0.5
        renormalise(meta_weights)
        # Flag for retraining at next scheduled cycle
        aim_states[aim_id].needs_retrain = True
```

---

## 7. AIM LIFECYCLE

Each AIM goes through these states:

```
INSTALLED → BOOTSTRAPPED → ACTIVE → (SUPPRESSED ↔ ACTIVE)
```

| State | Meaning | Modifier | Weight |
|-------|---------|----------|--------|
| INSTALLED | AIM registered but no data yet | 1.0 (neutral) | 0 (excluded from aggregation) |
| BOOTSTRAPPED | Initialised from historical data, accumulating live data | 1.0 (neutral) | Equal share (1/N) |
| ACTIVE | Producing live predictions, learning from outcomes | Computed | DMA-learned |
| SUPPRESSED | DMA weight below threshold | 1.0 (forced neutral) | <threshold |

**Initialisation (Paper 209):** All AIMs start with equal weights: `1 / num_active_aims`. DMA learns the actual weights over time. This prevents arbitrary initial weighting from distorting early trading.

---

## 8. DATA STORES

| Store | What It Holds | Updated By |
|-------|-------------|-----------|
| P3-D01 | Per-AIM: status, trained model, current modifier per asset, last retrained date, warm-up progress | Offline Block 1 (training), Online Block 1 (feature computation) |
| P3-D02 | Per-AIM: inclusion_probability, inclusion_flag, days_below_threshold, recent_effectiveness | Offline Block 1 (DMA update P3-PG-02) |
| P3-D04.adwin | Per-AIM: ADWIN states for drift detection | Offline Block 1 (drift detector P3-PG-04) |

---

## 9. KEY PARAMETERS

| Parameter | Default | Location | Tuning |
|-----------|---------|----------|--------|
| Forgetting factor (λ) | 0.99 | P3-D17.system_params | Higher = slower adaptation. 0.95–0.99 range. |
| Inclusion threshold | 0.02 | P3-D17.system_params | Below this, AIM is suppressed (inclusion_flag=False). With 6 AIMs at equal start ~0.167, 0.02 gates at ~12% of initial weight. |
| Modifier floor | 0.5 | Architecture Section 9 | Prevents AIMs from zeroing out position |
| Modifier ceiling | 1.5 | Architecture Section 9 | Prevents AIMs from doubling position |
| HDWM diversity check | Weekly | Offline orchestrator | Ensures at least 1 AIM per type is active |
| Drift detection (ADWIN) | Daily | Offline orchestrator | Uses default ADWIN parameters |

---

## 10. COMPLETE FLOW — TRADE LIFECYCLE

```
1. Trade outcome logged to P3-D03
          ↓
2. Offline Block 1: DMA update (P3-PG-02)
   - For each AIM: compute likelihood, update inclusion_probability
   - SPEC-A9: magnitude-weighted likelihood
          ↓
3. Offline Block 1: Drift check (P3-PG-04, daily)
   - AutoEncoder + ADWIN per AIM
   - If drift: reduce weight, flag for retrain
          ↓
4. Offline Block 1: Diversity check (P3-PG-03, weekly)
   - HDWM ensures no type goes to zero
          ↓
5. Next session: Online Block 1 loads AIM states + DMA weights
          ↓
6. Online Block 1: Each AIM computes its modifier from current data
          ↓
7. Online Block 3: MoE aggregation
   - combined_modifier = weighted_sum(modifier × DMA_weight) / sum(DMA_weights)
   - Bounded to [0.5, 1.5]
          ↓
8. Online Block 4: combined_modifier multiplied into Kelly fraction
```

---

## 11. COMMON PITFALLS

1. **Not normalising after every DMA update.** Inclusion probabilities must sum to 1.0 across all active AIMs. If you forget to normalise, probabilities drift and the combined modifier becomes meaningless.

2. **Using AIM modifiers from current time for DMA update.** The DMA update must use the modifier that was active at the time of the trade, not the current modifier. Store `aim_breakdown_at_entry` in P3-D03 for exactly this purpose.

3. **Killing an AIM permanently.** DMA can reduce weights to near-zero, but HDWM ensures at least one AIM per type stays active. Never delete an AIM from the registry — set status to SUPPRESSED.

4. **Forgetting factor too low.** λ < 0.95 causes the system to "forget" too quickly and chase noise. The default 0.99 means roughly 100 trades of effective memory. For 1-3 trades/day, that's 1-3 months of learning.

5. **Not handling the cold start.** Before any trade outcomes, all AIMs have equal weights. The first ~50 trades are the learning phase. Combined modifier will be near 1.0 during this period (which is correct — the system doesn't know enough to deviate from neutral).

---

## 12. PYTHON LIBRARIES

- No external DMA library needed — implement from above (~50 lines)
- `river` or `skmultiflow` for ADWIN drift detection (or implement from paper)
- `scikit-learn` or `tensorflow` for AutoEncoder (simple feedforward, ~3 layers)
- `numpy` for array normalisation

---

*This guide supplements the pseudocode in `Program3_Offline.md` Block 1 and `Program3_Online.md` Block 3. For the full system context, see `Program3_Architecture.md`. For AIM specifications, see `AIMRegistry.md`.*
