---
tags:
  - captain-audit
  - P3-online
status: stub
---
# 08 — Kelly Sizing Pipeline
> Part 1 original document. Not yet transferred to this vault.

## Audit Resolutions

> [!note] 2026-04-11 Gap Analysis — CRITICAL fixes
> The following audit resolutions reference this specification:

- [[G-ONL-017_kelly_l4_formula_wrong|G-ONL-017 — Kelly L4 Formula Algebraically Wrong]] — CRITICAL RESOLVED
# Blended Kelly Implementation Guide — Position Sizing

**Purpose:** Implementation guide for Nomaan covering the multi-layer Kelly sizing system used across Captain (Offline) Block 8 and Captain (Online) Block 4.
**Spec reference:** `Program3_Offline.md` Block 8 (P3-PG-15), `Program3_Online.md` Block 4 (P3-PG-24)
**Research basis:** Papers 217 (Kelly shrinkage under parameter uncertainty), 218 (Distributionally Robust Kelly), 219 (Blended Kelly with regime weights)

---

## 1. THE SIZING PIPELINE

Position sizing flows through 7 layers. Each layer takes the output of the previous one and applies a further constraint or adjustment.

```
Layer 1: Regime-Conditional Kelly (Offline Block 8)
    → per-asset, per-regime, per-session Kelly fraction

Layer 2: Blended Kelly (Online Block 4)
    → weight Layer 1 values by regime probabilities

Layer 3: Parameter Uncertainty Shrinkage (Online Block 4)
    → reduce by shrinkage factor (increases as data accumulates)

Layer 4: Robust Kelly Fallback (Online Block 4)
    → if regime uncertain, take min(shrunk Kelly, robust Kelly)

Layer 5: AIM Modifier (Online Block 4)
    → multiply by combined_modifier from DMA/MoE aggregation

Layer 6: Account-Type Adjustment (Online Block 4)
    → scale by risk_goal (PASS_EVAL, GROW_CAPITAL, PRESERVE_CAPITAL)

Layer 7: TSM Hard Constraints (Online Block 4)
    → cap by MDD/MLL headroom, margin, contract limits
```

---

## 2. LAYER 1 — REGIME-CONDITIONAL KELLY (Offline)

**Where:** P3-PG-15 in `Program3_Offline.md` Block 8. Runs after each trade outcome.

### 2.1 EWMA Updates

The system maintains separate EWMA estimates for win rate, average win, and average loss. These are indexed by `[asset][regime][session]` — 6 cells per asset (2 regimes x 3 sessions).

```python
def update_ewma(state: EWMAState, trade: TradeOutcome, alpha: float):
    """
    state: P3-D05[asset][regime][session]
    alpha: adaptive decay factor from SPEC-A12 (see Section 2.2)
    """
    pnl_per_contract = trade.pnl / trade.contracts
    
    if pnl_per_contract > 0:
        # Winning trade
        state.win_rate = (1 - alpha) * state.win_rate + alpha * 1.0
        state.avg_win = (1 - alpha) * state.avg_win + alpha * pnl_per_contract
    else:
        # Losing trade
        state.win_rate = (1 - alpha) * state.win_rate + alpha * 0.0
        state.avg_loss = (1 - alpha) * state.avg_loss + alpha * abs(pnl_per_contract)
```

**Per-contract normalisation is critical.** Raw PnL includes sizing effects (how many contracts were traded). By dividing by contracts, we track the strategy's inherent edge independent of how aggressively it was sized. Without this, a period of large positions would distort the EWMA.

### 2.2 Adaptive Alpha (SPEC-A12)

The EWMA decay factor adapts based on BOCPD's changepoint probability:

```python
def compute_adaptive_alpha(cp_prob: float) -> float:
    """
    When the market is stable (low cp_prob), use a longer lookback (slower learning).
    When a changepoint is likely (high cp_prob), learn faster from recent data.
    """
    if cp_prob < 0.2:
        span = 30    # ~30 trades effective lookback
    elif cp_prob < 0.5:
        span = 20    # default
    elif cp_prob < 0.8:
        span = 12    # elevated instability
    else:
        span = 8     # near-changepoint — rapid adaptation
    
    return 2.0 / (span + 1)
```

### 2.3 Kelly Fraction Computation

```python
def compute_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Classic Kelly criterion for binary outcomes:
    f* = p - (1-p)/b
    where p = win rate, b = win/loss ratio
    """
    if avg_loss <= 0 or win_rate <= 0:
        return 0.0
    
    b = avg_win / avg_loss  # payoff ratio (dimensionless)
    kelly = win_rate - (1 - win_rate) / b
    return max(0.0, kelly)  # never negative (never short the bankroll)
```

This is computed per `[asset][regime][session]` and stored in P3-D12.

---

## 3. LAYER 2 — BLENDED KELLY (Online)

**Where:** P3-PG-24 in `Program3_Online.md` Block 4.

At each session evaluation, the regime classifier produces probabilities P(LOW_VOL) and P(HIGH_VOL). The blended Kelly is a probability-weighted average:

```python
def blended_kelly(kelly_params, regime_probs, asset, session):
    """
    Paper 219 (MacLean & Zhao): optimal fraction under regime uncertainty
    is the probability-weighted combination of regime-specific fractions.
    """
    blended = 0.0
    for regime in ["LOW_VOL", "HIGH_VOL"]:
        regime_kelly = kelly_params[asset][regime][session].kelly_full
        regime_weight = regime_probs[asset][regime]
        blended += regime_weight * regime_kelly
    
    return blended
```

**Why this works:** If the system is 70% confident it's in LOW_VOL (where Kelly = 0.08) and 30% in HIGH_VOL (where Kelly = 0.02), blended Kelly = 0.062. This is mathematically optimal under regime uncertainty — it doesn't overbet if the regime classification is wrong.

---

## 4. LAYER 3 — PARAMETER UNCERTAINTY SHRINKAGE

**Where:** Same block (P3-PG-24).

Kelly is optimal only if the parameters (win rate, payoff ratio) are known exactly. With finite data, they are estimated — and estimation error in Kelly consistently leads to overbetting.

```python
def apply_shrinkage(blended_kelly: float, shrinkage_factor: float) -> float:
    """
    Paper 217: shrinkage factor = max(0.3, 1.0 - estimation_variance)
    
    - With 20 trades: estimation_variance ~0.5, shrinkage ~0.5 → half Kelly
    - With 200 trades: estimation_variance ~0.1, shrinkage ~0.9 → near-full Kelly
    - Floor at 0.3 prevents zero sizing even with high uncertainty
    """
    return blended_kelly * shrinkage_factor
```

The shrinkage factor is computed in Offline Block 8 and stored in P3-D12. It improves (approaches 1.0) as the system accumulates more trades and the EWMA estimates stabilise.

---

## 5. LAYER 4 — ROBUST KELLY FALLBACK

**Where:** Same block, activated when `regime_uncertain[asset] == True` (max regime probability < 0.6).

```python
def compute_robust_kelly(ewma_states, asset):
    """
    Paper 218: Distributionally Robust Kelly.
    Solves for the Kelly fraction that maximises worst-case growth rate
    over a set of plausible return distributions.
    
    In practice: uses the moment constraints (mean, variance) from EWMA
    to define the uncertainty set, then finds the Kelly fraction that
    is optimal under the WORST distribution consistent with those moments.
    """
    # Moment constraints from EWMA
    mean_return = compute_expected_return(ewma_states[asset])
    var_return = compute_return_variance(ewma_states[asset])
    
    # Robust Kelly: f* = mean / (mean^2 + var)
    # This is the Markowitz-like solution that is always more conservative
    # than standard Kelly
    if mean_return <= 0:
        return 0.0
    
    robust_f = mean_return / (mean_return**2 + var_return)
    return max(0.0, robust_f)

def apply_robust_fallback(adjusted_kelly, robust_kelly, regime_uncertain):
    if regime_uncertain:
        return min(adjusted_kelly, robust_kelly)
    return adjusted_kelly
```

---

## 6. LAYER 5 — AIM MODIFIER

```python
def apply_aim_modifier(kelly: float, combined_modifier: float) -> float:
    """
    combined_modifier is the DMA/MoE-weighted aggregate of all 15 AIMs.
    Range: [0.5, 1.5] (bounded by Architecture spec).
    
    > 1.0: AIMs collectively say conditions are favourable → size up
    < 1.0: AIMs collectively say conditions are unfavourable → size down
    = 1.0: neutral (no AIM influence)
    """
    return kelly * combined_modifier
```

---

## 7. LAYER 6 — ACCOUNT-TYPE ADJUSTMENT

```python
def account_kelly_adjustment(kelly: float, risk_goal: str, pass_probability: float = None) -> float:
    if risk_goal == "PASS_EVAL":
        if pass_probability is not None and pass_probability < 0.5:
            return kelly * 0.5   # critically low pass prob
        elif pass_probability is not None and pass_probability < 0.7:
            return kelly * 0.7   # moderate pass prob
        else:
            return kelly * 0.85  # always slightly conservative for eval
    
    elif risk_goal == "PRESERVE_CAPITAL":
        return kelly * 0.5       # hard cap at half-Kelly
    
    elif risk_goal == "GROW_CAPITAL":
        return kelly             # full computed Kelly
    
    return kelly
```

---

## 8. LAYER 7 — TSM HARD CONSTRAINTS

The final Kelly fraction is converted to a contract count and capped by the TSM (Trading System Model) rules:

```python
def compute_final_contracts(
    account_kelly: float,
    account_capital: float,
    risk_per_contract: float,
    tsm: TSMConfig,
    sizing_override: float = 1.0
) -> int:
    """
    risk_per_contract: SL distance in dollars per contract (strategy_sl * point_value)
    sizing_override: from decay detector (Level 2 reduction, default 1.0)
    """
    # Kelly gives fraction of capital to risk
    risk_amount = account_capital * account_kelly * sizing_override
    
    # Convert to contracts
    raw_contracts = risk_amount / risk_per_contract if risk_per_contract > 0 else 0
    
    # TSM caps (prop firm: MDD/MLL headroom; broker: margin)
    if tsm.category in ["PROP_EVAL", "PROP_FUNDED", "PROP_SCALING"]:
        remaining_mdd = tsm.max_drawdown_limit - tsm.current_drawdown
        max_by_mdd = remaining_mdd / risk_per_contract if risk_per_contract > 0 else 0
        max_by_mll = (tsm.max_daily_loss - tsm.daily_loss_used) / risk_per_contract \
                     if tsm.max_daily_loss and risk_per_contract > 0 else 999
        tsm_cap = min(max_by_mdd, max_by_mll, tsm.max_contracts or 999)
    else:
        margin = tsm.margin_per_contract or get_default_margin(tsm.asset)
        buffer = tsm.margin_buffer_pct or 1.5
        tsm_cap = tsm.current_balance / (margin * buffer) if margin > 0 else 0
        if tsm.max_contracts:
            tsm_cap = min(tsm_cap, tsm.max_contracts)
    
    final = min(floor(raw_contracts), floor(tsm_cap))
    return max(0, final)
```

---

## 9. DATA FLOW SUMMARY

```
P3-D03 (trade outcomes)
    ↓ pnl_per_contract
P3-D05 [asset][regime][session] (EWMA states — Offline Block 8)
    ↓ win_rate, avg_win, avg_loss
P3-D12 [asset][regime][session] (Kelly params — Offline Block 8)
    ↓ kelly_full, shrinkage_factor
Online Block 4 (P3-PG-24)
    ↓ blended → shrunk → robust → AIM-modified → account-adjusted → TSM-capped
Signal output (contracts per account)
```

---

## 10. KEY PARAMETERS

| Parameter | Default | Location | Tuning |
|-----------|---------|----------|--------|
| EWMA adaptive span | 8–30 trades | Offline Block 8 | Driven by BOCPD cp_prob. Not manually tuned. |
| Shrinkage floor | 0.3 | Offline Block 8 | Prevents zero sizing. Lower = more aggressive with limited data. |
| AIM modifier bounds | [0.5, 1.5] | Architecture | Prevents AIMs from zeroing out or doubling position. |
| User Kelly ceiling | Configurable | P3-D16 | Per-user maximum Kelly fraction. Default: 0.25. |
| Regime uncertainty threshold | 0.6 | Online Block 2 | Below this triggers robust Kelly fallback. |

---

## 11. COMMON PITFALLS

1. **Using raw PnL instead of per-contract PnL for EWMA.** This is the most dangerous mistake. Raw PnL conflates sizing decisions with strategy edge. A strategy that made $500 on 5 contracts is identical in edge to one that made $100 on 1 contract. Always divide by contracts.

2. **Not separating win rate from payoff ratio.** A strategy can have a declining win rate but increasing average win (fewer but bigger winners). Kelly needs both tracked independently to size correctly.

3. **Applying Kelly to total capital instead of per-account capital.** Each account has its own capital pool (user silo architecture). Kelly fraction applies to the account's available capital, not the user's total.

4. **Forgetting to floor Kelly at 0.** Negative Kelly means the strategy has negative expected value — should never trade. The floor catches edge cases during warm-up.

5. **Not applying shrinkage.** Full Kelly with estimated parameters consistently overperforms in theory but blows up in practice. Shrinkage is not optional — it is a core part of the sizing system.

---

*This guide supplements the pseudocode in `Program3_Offline.md` Block 8 and `Program3_Online.md` Block 4. For the full system context, see `Program3_Architecture.md`.*