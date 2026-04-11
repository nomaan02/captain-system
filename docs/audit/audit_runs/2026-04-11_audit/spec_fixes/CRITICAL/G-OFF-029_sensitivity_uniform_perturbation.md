# G-OFF-029 — Sensitivity Scanner: Uniform Perturbation Instead of Per-Parameter

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Offline |
| **Block** | B5 Sensitivity Scanner |
| **Spec Reference** | Doc 32 PG-12 |
| **File(s)** | `captain-offline/captain_offline/blocks/b5_sensitivity.py` |
| **Fixed In** | Session 4.1, commit `4a7e258` |

## What Was Wrong (Before)

The spec requires a **per-parameter perturbation grid**:
```
FOR EACH param p IN base_params:
    FOR delta IN [-0.20, -0.10, -0.05, 0.0, +0.05, +0.10, +0.20]:
        perturbed[p] = base_params[p] * (1 + delta)
        # all other params stay at base values
```

This produces `N_params x 7` grid points (e.g., 2 params = 14 evaluations).

The code applied each delta **uniformly to ALL parameters simultaneously** — iterating 7 deltas and scaling every SL/TP multiplier at once. This produced only **7 grid points** regardless of parameter count.

**Impact**: Could not detect if a strategy was fragile to ONE specific parameter while robust to others. A strategy that collapses when `sl_multiplier` changes by 5% but is stable for `tp_multiplier` changes would incorrectly test as robust under uniform perturbation.

## What Was Fixed (After)

1. **Outer loop restructured** to iterate `for param_name in perturbable_params`, with inner loop `for delta in PERTURBATION_DELTAS`.

2. **`_backtest_perturbed()`** updated to accept a `param_name` argument — perturbs only that single parameter while holding all others at base values.

3. **Grid entries** now include `{"param": param_name, "delta": delta, "sharpe": sharpe}`, enabling per-parameter sensitivity analysis.

4. **PBO (Probability of Backtest Overfitting)** now computed on returns from the best-performing grid configuration instead of unperturbed base returns. `n_configs` uses `N_params x 7` for correct degrees of freedom.

5. **`perturbable_params`** built from `["sl_multiplier", "tp_multiplier"]` — extensible if additional parameters are added to the locked strategy.

## Overall Feature: Sensitivity Analysis (PG-12)

The sensitivity scanner runs periodically (monthly) to evaluate whether the locked strategy parameters are robust or brittle. It perturbs each parameter individually across a range of deltas, backtests each configuration, and computes Sharpe ratios. If performance degrades sharply for small perturbations of any single parameter, the strategy is flagged as fragile. The PBO statistic quantifies the risk that the strategy's apparent performance is an artifact of overfitting to historical data. Results feed into the version management system and inform whether parameter updates should proceed.
