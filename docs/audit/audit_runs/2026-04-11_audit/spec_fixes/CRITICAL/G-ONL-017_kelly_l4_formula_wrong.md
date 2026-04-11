# G-ONL-017 — Kelly L4 Robust Fallback Formula Algebraically Wrong

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Online |
| **Block** | B4 Kelly Sizing |
| **Spec Reference** | Doc 33 PG-24 L4, Doc 21 Part 3 |
| **File(s)** | `captain-online/captain_online/blocks/b4_kelly_sizing.py` |
| **Fixed In** | Session 0.1, commit `3a474ba` |

## What Was Wrong (Before)

The spec requires:
```
f_robust = mu / (mu² + var)  IF mu > 0  ELSE 0
```

A standard mean-variance Kelly approximation that fires when `regime_uncertain[u]` is true.

The code delegated to `compute_robust_kelly` in `b1_features.py:468-481`, which computed return bounds `(mu - 1.5*sigma, mu + 1.5*sigma)` then `f_robust = lower / (upper * lower)`. This simplifies algebraically to `1/upper` — a distributional-robust min-max approach that is an **entirely different formula**.

**Numerical impact**: For typical values `mu=0.02, sigma=0.05`:
- Spec formula: `f_robust = 0.02 / (0.0004 + 0.0025) = 6.9`
- Code formula: `1 / (0.02 + 0.075) = 10.5` — a **52% oversize**

During regime uncertainty (the exact scenario where conservative sizing matters most), positions were being oversized by ~50%.

## What Was Fixed (After)

Replaced the delegation to `b1_features.py` with an inline computation matching the spec exactly:

```python
mu = avg_win * wr - avg_loss * (1 - wr)
var = avg_win ** 2 * wr + avg_loss ** 2 * (1 - wr) - mu ** 2
f_robust = mu / (mu ** 2 + var) if mu > 0 and (mu ** 2 + var) > 0 else 0.0
adjusted_kelly = min(adjusted_kelly, f_robust)
```

The fix also adds a zero-denominator guard `(mu ** 2 + var) > 0` beyond the bare spec as a defensive measure. The result is applied as `min(adjusted_kelly, f_robust)` — the robust formula acts as a **ceiling** on the Kelly fraction during uncertain regimes, never increasing it.

## Overall Feature: Kelly Criterion Sizing Pipeline (B4)

B4 is the position sizing engine. It operates in 7 layers:
- **L1-L3**: Blended Kelly across regimes, weighted by regime probabilities from B2
- **L4 (this fix)**: Robust fallback — caps the Kelly fraction when the regime detector reports uncertainty
- **L5**: AIM modifier — scales position by combined AIM score
- **L6**: User-level Kelly ceiling
- **L7**: Per-account contract sizing (dollars to contracts via tick value)

The L4 robust fallback is the system's defence against regime misclassification. When the regime probability is ambiguous (neither clearly LOW_VOL nor HIGH_VOL), L4 applies a conservative cap derived from mean-variance analysis. Getting this formula wrong directly oversizes positions in the most uncertain market conditions.
