# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Circuit Breaker Parameter Estimation — P3-PG-16C (Task 2.8c).

Estimates per-account per-model circuit breaker parameters:
  r_bar:  unconditional mean return per trade
  beta_b: loss-predictiveness coefficient (OLS: r_{j+1} on L_b)
  sigma:  per-trade return standard deviation
  rho_bar: average same-day trade correlation

beta_b ERRATA (Build Loop Prompt):
  beta_b > 0 -> positive serial correlation (losses predict losses -> shut basket)
  beta_b < 0 -> mean reversion (losses predict recovery -> keep open)

Significance gate: REMOVED (Q-33 — not in spec).
Cold start (n < 10): skip regression, use conservative defaults.
Cold start (n < 100): run regression but cold_start=True (layers 3-4 conservative).

Reads: P3-D03 (trade outcomes)
Writes: P3-D25 (circuit_breaker_params)
"""

import logging
import numpy as np
from collections import defaultdict

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

MIN_OBS_REGRESSION = 10   # Below this: skip regression, use conservative defaults
MIN_OBS_WARM = 100        # Below this: cold_start=True (layers 3-4 conservative)


def _load_trades_by_account_model(account_id: str, model_m: int) -> list[dict]:
    """Load trades grouped by day for a specific account and model."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT trade_id, pnl, contracts, ts
               FROM p3_d03_trade_outcome_log
               WHERE account_id = %s AND model_m = %s
               ORDER BY ts""",
            (account_id, model_m),
        )
        rows = cur.fetchall()
    return [
        {"trade_id": r[0], "pnl": r[1], "contracts": r[2], "ts": r[3]}
        for r in rows
    ]


def _ols_regression(x: np.ndarray, y: np.ndarray) -> dict:
    """Simple OLS regression: y = alpha + beta * x.

    Returns r_bar, beta, p_value, n_obs.
    """
    n = len(x)
    if n < 3:
        return {"r_bar": 0.0, "beta_b": 0.0, "p_value": 1.0, "n_obs": n}

    x_mean = np.mean(x)
    y_mean = np.mean(y)

    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)

    if ss_xx < 1e-10:
        return {"r_bar": float(y_mean), "beta_b": 0.0, "p_value": 1.0, "n_obs": n}

    beta = ss_xy / ss_xx
    alpha = y_mean - beta * x_mean

    # Residuals and standard error
    y_pred = alpha + beta * x
    residuals = y - y_pred
    sse = np.sum(residuals ** 2)
    mse = sse / (n - 2) if n > 2 else 1.0
    se_beta = np.sqrt(mse / ss_xx) if ss_xx > 0 else 1.0

    # t-statistic and p-value (two-sided)
    if se_beta > 0:
        t_stat = beta / se_beta
        # Approximate p-value using normal distribution (for large n)
        from scipy import stats
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 2))
    else:
        p_value = 1.0

    return {
        "r_bar": float(y_mean),   # Q-18: r_bar = mean(r_series) per spec doc 32 line 702
        "beta_b": float(beta),
        "p_value": float(p_value),
        "n_obs": n,
    }


def _compute_same_day_correlation(trades: list[dict]) -> float:
    """Compute average pairwise same-day trade return correlation.

    Groups trades by day, computes pairwise correlations within each day,
    then averages across days.
    """
    # Group by day
    by_day = defaultdict(list)
    for t in trades:
        if t["ts"]:
            day = str(t["ts"])[:10]  # YYYY-MM-DD
            if t["contracts"] and t["contracts"] > 0:
                by_day[day].append(t["pnl"] / t["contracts"])

    # Collect all same-day return pairs into two vectors for a single
    # Pearson correlation estimate.  np.corrcoef on 1-element arrays
    # (the previous code) always returns ±1/NaN — useless.
    vec_a, vec_b = [], []
    for day, returns in by_day.items():
        if len(returns) >= 2:
            for i in range(len(returns)):
                for j in range(i + 1, len(returns)):
                    vec_a.append(returns[i])
                    vec_b.append(returns[j])

    if len(vec_a) < 3:
        return 0.0

    corr = np.corrcoef(vec_a, vec_b)[0, 1]
    return float(corr) if not np.isnan(corr) else 0.0


def _build_regression_arrays(trades: list[dict]) -> tuple[list[float], list[float]]:
    """Build (L_b series, per-contract returns) for PG-16C OLS.

    Q-17: running_loss_at_trade_time — cross-day, loss-only accumulation.
    L_b = sum of abs(pnl_pc) for all prior trades where pnl_pc < 0.
    Trades must be sorted by ts (caller: _load_trades_by_account_model ORDER BY ts).
    """
    x_vals = []  # L_b at trade time (loss-only, unsigned, cross-day)
    y_vals = []  # per-contract return of this trade

    running_loss = 0.0
    for t in trades:
        pnl_pc = t["pnl"] / max(t["contracts"], 1)
        x_vals.append(running_loss)
        y_vals.append(pnl_pc)
        if pnl_pc < 0:
            running_loss += abs(pnl_pc)  # Q-17-ASSUMPTION: loss-only unsigned accumulation

    return x_vals, y_vals


def estimate_cb_params(account_id: str, model_m: int):
    """Execute P3-PG-16C: estimate circuit breaker parameters.

    Two-tier cold start (Doc 32 PG-16C):
      n < 10:  skip regression, use conservative defaults, cold_start=True
      10 <= n < 100: run regression, cold_start=True (layers 3-4 conservative)
      n >= 100: full estimation, cold_start=False

    Args:
        account_id: Account to estimate for
        model_m: Model/basket ID
    """
    trades = _load_trades_by_account_model(account_id, model_m)
    n = len(trades)

    if n < MIN_OBS_REGRESSION:
        # Tier 1: insufficient data — skip regression entirely
        logger.info("CB params skip for %s/m=%d: %d trades < %d min",
                     account_id, model_m, n, MIN_OBS_REGRESSION)
        _save_params(account_id, model_m, {
            "r_bar": 0.0, "beta_b": 0.0, "sigma": 0.0,
            "rho_bar": 0.0, "n_observations": n, "p_value": 1.0,
            "l_star": None, "cold_start": True,
        })
        return

    # Build regression dataset: L_b (loss-only cumulative) vs per-trade return
    x_vals, y_vals = _build_regression_arrays(trades)

    x_arr = np.array(x_vals)
    y_arr = np.array(y_vals)

    # OLS regression
    reg = _ols_regression(x_arr, y_arr)

    # Per-trade volatility
    all_returns = []
    for t in trades:
        if t["contracts"] and t["contracts"] > 0:
            all_returns.append(t["pnl"] / t["contracts"])
    sigma = float(np.std(all_returns)) if all_returns else 0.0

    # Same-day correlation
    rho_bar = _compute_same_day_correlation(trades)

    # L_star breakeven: mu_b = r_bar + beta_b * L_b = 0 => L* = -r_bar / beta_b
    # Only meaningful when beta_b < 0 (mean-reverting losses)
    beta_b = reg["beta_b"]
    if beta_b < 0:
        l_star = -reg["r_bar"] / beta_b
    else:
        l_star = None

    cold_start = n < MIN_OBS_WARM

    params = {
        "r_bar": reg["r_bar"],
        "beta_b": beta_b,
        "sigma": sigma,
        "rho_bar": rho_bar,
        "n_observations": reg["n_obs"],
        "p_value": reg["p_value"],
        "l_star": l_star,
        "cold_start": cold_start,
    }

    _save_params(account_id, model_m, params)

    logger.info("CB params estimated for %s/m=%d: r_bar=%.2f, beta_b=%.4f (p=%.3f), "
                "sigma=%.2f, rho_bar=%.3f, l_star=%s, cold_start=%s, n=%d",
                account_id, model_m, params["r_bar"], params["beta_b"],
                params["p_value"], params["sigma"], params["rho_bar"],
                params.get("l_star"), cold_start, params["n_observations"])


def _save_params(account_id: str, model_m: int, params: dict):
    """Save circuit breaker parameters to P3-D25."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d25_circuit_breaker_params
               (account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                n_observations, p_value, l_star, cold_start, last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (account_id, model_m, params["r_bar"], params["beta_b"],
             params["sigma"], params["rho_bar"],
             params["n_observations"], params["p_value"],
             params.get("l_star"), params.get("cold_start", True)),
        )
