# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""AIM-13 Sensitivity Scanner — P3-PG-12 (Task 2.5 / OFF lines 504-558).

Monthly automated scan: perturb locked strategy parameters, assess robustness.

Perturbation grid: [-20%, -10%, -5%, 0, +5%, +10%, +20%] per parameter.
Stability: CV of Sharpe across grid.
Anti-overfitting: PBO (CSCV S=8), DSR.
FRAGILE if >= 2 flags (sharpe_stability > 0.5, pbo > 0.5, dsr < 0.5).
On FRAGILE: AIM-13 modifier -> 0.85.

Reads: P3-D00, P3-D01, P3-D03
Writes: P3-D13 (scan results), P3-D01 (AIM-13 modifier)
"""

import json
import math
import logging
from datetime import datetime

import numpy as np

from shared.constants import now_et
from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# Perturbation deltas
PERTURBATION_DELTAS = [-0.20, -0.10, -0.05, 0.0, +0.05, +0.10, +0.20]

# FRAGILE thresholds
SHARPE_STABILITY_THRESHOLD = 0.5
PBO_THRESHOLD = 0.5
DSR_THRESHOLD = 0.5
MIN_FLAGS_FOR_FRAGILE = 2

# AIM-13 modifier when FRAGILE
FRAGILE_MODIFIER = 0.85

# PBO splits
CSCV_SPLITS = 8


def _compute_sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    std = arr.std()
    if std < 1e-10:
        return 0.0
    return float(arr.mean() / std * math.sqrt(252))


def _compute_pbo(returns: list[float], S: int = CSCV_SPLITS) -> float:
    """PBO via full CSCV (Paper 152). Delegates to shared.statistics."""
    from shared.statistics import compute_pbo
    return compute_pbo(returns, S)


def _compute_dsr(sharpe: float, n_trials: int, skew: float,
                  kurtosis: float, T: int) -> float:
    """DSR (Paper 150). Delegates to shared.statistics."""
    from shared.statistics import compute_dsr
    return compute_dsr(sharpe, n_trials, skew, kurtosis, T)


def _backtest_perturbed(asset_id: str, base_returns: list[float], delta: float,
                         locked_strategy: dict | None = None) -> list[float]:
    """Simulate perturbed strategy returns via signal replay.

    Loads replay context, applies delta perturbation to the locked strategy's
    SL and TP multipliers, then runs SignalReplayEngine.strategy_replay()
    to produce daily P&L under the perturbed parameters.

    Falls back to the original scaling approach (r * (1 + delta)) when
    replay context cannot be loaded (e.g. no P2 data files on disk).

    Args:
        asset_id: Asset to replay
        base_returns: Original daily returns (used as fallback)
        delta: Perturbation fraction (e.g. -0.10 = -10%)
        locked_strategy: Optional pre-loaded locked strategy dict.
            If None, loaded from replay context.

    Returns:
        List of daily P&L values under the perturbed parameters.
    """
    try:
        from shared.signal_replay import SignalReplayEngine

        ctx = SignalReplayEngine.load_replay_context(asset_id)
        trades = ctx["trades"]
        regime_labels = ctx["regime_labels"]
        aim_weights = ctx["aim_weights"]
        kelly_params = ctx["kelly_params"]

        if not trades:
            logger.warning("_backtest_perturbed: no trades loaded for %s, "
                           "falling back to scaling", asset_id)
            return [r * (1 + delta) for r in base_returns]

        strategy = locked_strategy or ctx.get("locked_strategy", {})

        # Extract base SL/TP multipliers from locked strategy
        base_sl = strategy.get("sl_multiplier",
                  strategy.get("sl_multiple", 1.0))
        base_tp = strategy.get("tp_multiplier",
                  strategy.get("tp_multiple", 2.0))

        # Perturb both SL and TP by delta
        perturbed_params = {
            "sl_multiplier": base_sl * (1 + delta),
            "tp_multiplier": base_tp * (1 + delta),
        }

        engine = SignalReplayEngine(asset=asset_id)
        replayed_trades = engine.strategy_replay(
            trades=trades,
            regime_labels=regime_labels,
            aim_weights=aim_weights,
            kelly_params=kelly_params,
            strategy_params=perturbed_params,
        )

        # Aggregate to daily P&L
        by_day: dict[str, float] = {}
        for t in replayed_trades:
            day = t.get("day", "unknown")
            by_day[day] = by_day.get(day, 0.0) + t.get("pnl", 0.0)

        daily_pnl = [by_day[d] for d in sorted(by_day)]

        if not daily_pnl:
            logger.warning("_backtest_perturbed: replay produced no daily P&L "
                           "for %s delta=%.2f, falling back", asset_id, delta)
            return [r * (1 + delta) for r in base_returns]

        return daily_pnl

    except Exception as exc:
        logger.warning("_backtest_perturbed: replay failed for %s (delta=%.2f): "
                       "%s — falling back to scaling", asset_id, delta, exc)
        return [r * (1 + delta) for r in base_returns]


def run_sensitivity_scan(asset_id: str, base_returns: list[float],
                          num_parameters: int = 4,
                          penalty_coefficient: float = 0.01) -> dict:
    """Execute P3-PG-12: monthly sensitivity scan.

    Args:
        asset_id: Asset to scan
        base_returns: Recent OOS daily returns for the locked strategy
        num_parameters: Number of strategy parameters
        penalty_coefficient: Complexity penalty per parameter

    Returns:
        Scan result dict with robustness_status
    """
    if len(base_returns) < 30:
        logger.warning("Sensitivity scan %s: insufficient data (%d < 30)", asset_id, len(base_returns))
        return {"robustness_status": "INSUFFICIENT_DATA", "asset_id": asset_id}

    # Run perturbation grid
    sharpe_values = []
    grid_results = []

    for delta in PERTURBATION_DELTAS:
        perturbed = _backtest_perturbed(asset_id, base_returns, delta)
        sharpe = _compute_sharpe(perturbed)
        sharpe_values.append(sharpe)
        grid_results.append({"delta": delta, "sharpe": sharpe})

    # Sharpe stability (CV)
    arr = np.array(sharpe_values)
    mean_sharpe = arr.mean()
    std_sharpe = arr.std()
    sharpe_stability = float(std_sharpe / max(abs(mean_sharpe), 1e-10))

    # PBO
    pbo = _compute_pbo(base_returns)

    # DSR
    skew = float(np.mean((arr - arr.mean()) ** 3) / max(arr.std() ** 3, 1e-10)) if arr.std() > 0 else 0.0
    kurt = float(np.mean((arr - arr.mean()) ** 4) / max(arr.std() ** 4, 1e-10)) if arr.std() > 0 else 3.0
    dsr = _compute_dsr(max(sharpe_values), len(PERTURBATION_DELTAS), skew, kurt, len(base_returns))

    # Complexity penalty
    complexity_penalty = num_parameters * penalty_coefficient
    adjusted_sharpe = max(sharpe_values) - complexity_penalty

    # Flags
    flags = []
    if sharpe_stability > SHARPE_STABILITY_THRESHOLD:
        flags.append("PARAMETER_SENSITIVE")
    if pbo > PBO_THRESHOLD:
        flags.append("OVERFIT")
    if dsr < DSR_THRESHOLD:
        flags.append("INSIGNIFICANT")

    robustness_status = "FRAGILE" if len(flags) >= MIN_FLAGS_FOR_FRAGILE else "ROBUST"

    result = {
        "asset_id": asset_id,
        "sharpe_stability": sharpe_stability,
        "pbo": pbo,
        "dsr": dsr,
        "adjusted_sharpe": adjusted_sharpe,
        "robustness_status": robustness_status,
        "flags": flags,
        "perturbation_grid_results": grid_results,
        "scan_date": now_et().isoformat(),
    }

    # Store in P3-D13
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d13_sensitivity_scan_results
               (asset_id, sharpe_stability, pbo, dsr, adjusted_sharpe,
                robustness_status, flags, perturbation_grid_results, scan_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (asset_id, sharpe_stability, pbo, dsr, adjusted_sharpe,
             robustness_status, json.dumps(flags), json.dumps(grid_results)),
        )

    # If FRAGILE, reduce AIM-13 modifier
    if robustness_status == "FRAGILE":
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d01_aim_model_states
                   (aim_id, asset_id, status, current_modifier, last_updated)
                   VALUES (%s, %s, 'ACTIVE', %s, now())""",
                (13, asset_id, FRAGILE_MODIFIER),
            )
        logger.warning("Sensitivity scan %s: FRAGILE (%s) — AIM-13 modifier -> %.2f",
                       asset_id, flags, FRAGILE_MODIFIER)
    else:
        logger.info("Sensitivity scan %s: ROBUST (stability=%.3f, pbo=%.3f, dsr=%.3f)",
                     asset_id, sharpe_stability, pbo, dsr)

    return result
