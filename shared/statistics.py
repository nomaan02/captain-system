"""Shared statistical functions for anti-overfitting validation.

Implements:
  - compute_pbo: Probability of Backtest Overfitting via CSCV (Paper 152)
  - compute_dsr: Deflated Sharpe Ratio (Paper 150)
  - get_ewma_for_regime: EWMA state lookup with session fallback

These are used by B3 (pseudotrader), B4 (Kelly), B5 (trade selection/sensitivity),
B6 (signal output/auto-expansion).
"""

import math
import logging
from itertools import combinations

import numpy as np

logger = logging.getLogger(__name__)


def get_ewma_for_regime(asset_id: str, regime: str, ewma_states: dict, session_id: int) -> dict | None:
    """Get EWMA state for asset/regime, with fallback to any session.

    Lookup order: exact (asset_id, regime, session_id) key first,
    then any entry matching (asset_id, regime) regardless of session.
    """
    key = (asset_id, regime, session_id)
    entry = ewma_states.get(key)
    if entry:
        return entry
    for k, v in ewma_states.items():
        if k[0] == asset_id and k[1] == regime:
            return v
    return None


def _sharpe_on_returns(returns: np.ndarray) -> float:
    """Compute Sharpe ratio (non-annualised) from a return array."""
    if len(returns) < 2:
        return 0.0
    std = returns.std()
    if std < 1e-10:
        return 0.0
    return float(returns.mean() / std)


def compute_pbo(returns: list[float], S: int = 16) -> float:
    """Probability of Backtest Overfitting via CSCV (Paper 152).

    For a single strategy, CSCV tests whether the strategy's performance
    is consistent across different IS/OOS splits of the data:

    1. Split return series into S equal sub-groups
    2. Form all C(S, S/2) combinations as IS/OOS splits
    3. For each split, compute Sharpe on IS and OOS halves
    4. PBO = fraction of splits where IS Sharpe > 0 but OOS Sharpe <= 0
       (strategy looks good in-sample but fails out-of-sample)

    A strategy with genuine edge shows PBO < 0.5 (IS-positive implies
    OOS-positive more often than not). An overfit strategy shows PBO > 0.5.

    Args:
        returns: List of strategy returns (daily P&L or per-contract returns)
        S: Number of sub-groups (default 16 per Paper 152). Must be even.

    Returns:
        PBO in [0, 1]. Lower is better. < 0.5 suggests strategy is not overfit.
    """
    arr = np.array(returns)
    n = len(arr)

    if S % 2 != 0:
        S = S - 1  # force even

    if n < S * 2:
        return 0.5  # insufficient data for meaningful CSCV

    # Step 1: Split into S equal sub-groups
    group_size = n // S
    groups = [arr[i * group_size:(i + 1) * group_size] for i in range(S)]

    half = S // 2
    indices = list(range(S))

    # Step 2: Enumerate all C(S, S/2) combinations
    # For S=16, C(16,8) = 12,870 — feasible
    combos = list(combinations(indices, half))
    n_combos = len(combos)

    if n_combos > 50000:
        # For very large S, subsample to keep computation tractable
        rng = np.random.default_rng(42)
        combo_indices = rng.choice(n_combos, size=50000, replace=False)
        combos = [combos[i] for i in combo_indices]
        n_combos = len(combos)

    # Step 3: For each combo, compute IS and OOS Sharpe
    # Due to CSCV symmetry, each combo (A, B) has twin (B, A).
    # We only need to evaluate half the combos — the other half
    # is the mirror. We process all for correctness.
    n_is_positive = 0
    n_overfit = 0

    for is_indices in combos:
        oos_indices = tuple(i for i in indices if i not in is_indices)

        is_data = np.concatenate([groups[i] for i in is_indices])
        oos_data = np.concatenate([groups[i] for i in oos_indices])

        is_sharpe = _sharpe_on_returns(is_data)
        oos_sharpe = _sharpe_on_returns(oos_data)

        # Only count splits where IS looks positive (strategy appears profitable)
        if is_sharpe > 0:
            n_is_positive += 1
            # Overfit = looks good IS but fails OOS
            if oos_sharpe <= 0:
                n_overfit += 1

    if n_is_positive == 0:
        # Strategy never looks good even in-sample — PBO is moot
        return 0.5

    pbo = n_overfit / n_is_positive

    return float(pbo)


def compute_dsr(sharpe: float, n_trials: int, skew: float,
                kurtosis: float, T: int) -> float:
    """Deflated Sharpe Ratio (Paper 150).

    Adjusts Sharpe for multiple testing, skewness, and kurtosis.

    Args:
        sharpe: Observed Sharpe ratio
        n_trials: Number of strategy configurations tested
        skew: Skewness of returns
        kurtosis: Kurtosis of returns
        T: Number of observations (trade count or days)

    Returns:
        DSR probability in [0, 1]. Higher is better. > 0.5 suggests genuine edge.
    """
    if T < 2 or n_trials < 1:
        return 0.0

    from scipy import stats as sp_stats

    # Expected maximum Sharpe from n_trials under the null
    e_max_sharpe = sp_stats.norm.ppf(1 - 1.0 / max(n_trials, 2)) if n_trials > 1 else 0.0

    # Adjusted standard error incorporating higher moments
    se_sq = (1 - skew * sharpe + (kurtosis - 1) / 4.0 * sharpe ** 2) / T
    if se_sq <= 0:
        return 0.0
    se = math.sqrt(se_sq)

    if se < 1e-10:
        return 0.0

    # DSR = P(observed sharpe > E[max sharpe under null])
    z = (sharpe - e_max_sharpe) / se
    return float(sp_stats.norm.cdf(z))
