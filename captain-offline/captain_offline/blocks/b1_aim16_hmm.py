# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""AIM-16 HMM Opportunity Regime Training — P3-PG-01C (Task 2.1f).

Trains a 3-state Hidden Markov Model on session-level observations to
classify opportunity regimes: LOW_OPP, NORMAL, HIGH_OPP.

Hidden States (K=3):
    0: LOW_OPP  — few signals, low OO, choppy
    1: NORMAL   — average signal rate, moderate OO
    2: HIGH_OPP — many signals, high OO, trending

Observation Vector (z_w in R^7 per session window):
    1. n_signals, 2. mean_OO, 3. volume_z, 4. vix_level,
    5. prior_session_pnl, 6. cross_asset_corr, 7. day_of_week

Training: Baum-Welch EM on 60-day rolling window (240 session observations)
Cold start: <20d disabled, 20-59d blended 50/50, 60+ full HMM

Writes: P3-D26
"""

import json
import logging
import numpy as np
from hmmlearn.hmm import GaussianHMM

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# HMM parameters
N_STATES = 3
N_FEATURES = 7
TRAINING_WINDOW_DAYS = 60
SESSIONS_PER_DAY = 4  # APAC, LON, NY_PRE, NY_OPEN
MAX_EM_ITERATIONS = 100
CONVERGENCE_THRESHOLD = 1e-6
SMOOTHING_ALPHA = 0.3
FLOOR_PER_SESSION = 0.05
MIN_OBSERVATIONS = TRAINING_WINDOW_DAYS * SESSIONS_PER_DAY  # 240 (Doc 22 §6)

# Cold start thresholds
COLD_START_DISABLE_DAYS = 20
COLD_START_BLEND_DAYS = 60

STATE_NAMES = {0: "LOW_OPP", 1: "NORMAL", 2: "HIGH_OPP"}


def _label_from_pnl(pnl_values: np.ndarray) -> np.ndarray:
    """Assign supervised labels based on PnL percentiles."""
    p25 = np.percentile(pnl_values, 25)
    p75 = np.percentile(pnl_values, 75)
    labels = np.ones(len(pnl_values), dtype=int)  # default NORMAL
    labels[pnl_values > p75] = 2   # HIGH_OPP
    labels[pnl_values < p25] = 0   # LOW_OPP
    return labels


def train_aim16_hmm(observations: np.ndarray, session_pnl: np.ndarray,
                     n_trading_days: int) -> dict:
    """Train AIM-16 HMM and return state for P3-D26.

    Args:
        observations: (T, 7) array of session observation vectors
        session_pnl: (T,) array of per-session realized PnL
        n_trading_days: Number of trading days of data available

    Returns:
        Dict matching P3-D26 schema
    """
    T = len(observations)

    # Cold start check
    if n_trading_days < COLD_START_DISABLE_DAYS:
        logger.info("AIM-16 HMM: cold start (< %d days), disabled", COLD_START_DISABLE_DAYS)
        return {
            "hmm_params": None,
            "current_state_probs": [1.0 / N_STATES] * N_STATES,
            "opportunity_weights": {},  # equal weights applied by caller
            "prior_alpha": {},
            "smoothing_alpha": SMOOTHING_ALPHA,
            "training_window": TRAINING_WINDOW_DAYS,
            "n_observations": T,
            "cold_start": True,
        }

    # Enforce minimum observation count (Doc 22 §6: 240 obs per 60-day window)
    if T < MIN_OBSERVATIONS:
        logger.info("AIM-16 HMM: insufficient observations (%d < %d), cold-start output",
                     T, MIN_OBSERVATIONS)
        return {
            "hmm_params": None,
            "current_state_probs": [1.0 / N_STATES] * N_STATES,
            "opportunity_weights": {},
            "prior_alpha": {},
            "smoothing_alpha": SMOOTHING_ALPHA,
            "training_window": TRAINING_WINDOW_DAYS,
            "n_observations": T,
            "cold_start": True,
        }

    # Initialize means/covariances from supervised PnL labels
    labels = _label_from_pnl(session_pnl)
    init_means = np.zeros((N_STATES, N_FEATURES))
    init_covars = np.zeros((N_STATES, N_FEATURES))
    for k in range(N_STATES):
        mask = labels == k
        if mask.sum() > 1:
            init_means[k] = observations[mask].mean(axis=0)
            init_covars[k] = observations[mask].var(axis=0) + 1e-6
        else:
            init_means[k] = observations.mean(axis=0)
            init_covars[k] = observations.var(axis=0) + 1e-6

    # Train with hmmlearn GaussianHMM (diagonal covariance)
    model = GaussianHMM(
        n_components=N_STATES,
        covariance_type="diag",
        n_iter=MAX_EM_ITERATIONS,
        tol=CONVERGENCE_THRESHOLD,
        init_params="",  # we set params manually
    )
    model.startprob_ = np.full(N_STATES, 1.0 / N_STATES)
    model.transmat_ = np.full((N_STATES, N_STATES), 1.0 / N_STATES)
    model.means_ = init_means
    model.covars_ = init_covars
    model.fit(observations)

    # Current state probabilities from posterior on last observation
    state_probs = model.predict_proba(observations)
    current_state_probs = state_probs[-1].tolist()

    # Apply cold start blending (spec: 20-59 days -> 50/50 HMM vs equal weights)
    is_cold = n_trading_days < COLD_START_BLEND_DAYS
    if is_cold:
        equal_probs = [1.0 / N_STATES] * N_STATES
        current_state_probs = [
            0.5 * hmm_p + 0.5 * eq_p
            for hmm_p, eq_p in zip(current_state_probs, equal_probs)
        ]

    result = {
        "hmm_params": {
            "pi": model.startprob_.tolist(),
            "A": model.transmat_.tolist(),
            "mu": model.means_.tolist(),
            "sigma": model.covars_.tolist(),
        },
        "current_state_probs": current_state_probs,
        "opportunity_weights": {},  # populated by online inference
        "prior_alpha": {},
        "smoothing_alpha": SMOOTHING_ALPHA,
        "training_window": TRAINING_WINDOW_DAYS,
        "n_observations": T,
        "cold_start": is_cold,
    }

    return result


def save_hmm_state(state: dict):
    """Save HMM state to P3-D26."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d26_hmm_opportunity_state
               (hmm_params, current_state_probs, opportunity_weights,
                prior_alpha, last_trained, training_window, n_observations,
                cold_start, last_updated)
               VALUES (%s, %s, %s, %s, now(), %s, %s, %s, now())""",
            (
                json.dumps(state.get("hmm_params"), default=str) if state.get("hmm_params") else None,
                json.dumps(state["current_state_probs"]),
                json.dumps(state.get("opportunity_weights", {})),
                json.dumps(state.get("prior_alpha", {})),
                state["training_window"],
                state["n_observations"],
                state["cold_start"],
            ),
        )
    logger.info("AIM-16 HMM state saved to P3-D26 (cold_start=%s, n_obs=%d)",
                state["cold_start"], state["n_observations"])
