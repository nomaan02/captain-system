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

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# HMM parameters
N_STATES = 3
N_FEATURES = 7
TRAINING_WINDOW_DAYS = 60
SESSIONS_PER_DAY = 4  # APAC, LONDON, NY_PRE, NY_OPEN
MAX_EM_ITERATIONS = 100
CONVERGENCE_THRESHOLD = 1e-6
SMOOTHING_ALPHA = 0.3
FLOOR_PER_SESSION = 0.05

# Cold start thresholds
COLD_START_DISABLE_DAYS = 20
COLD_START_BLEND_DAYS = 60

STATE_NAMES = {0: "LOW_OPP", 1: "NORMAL", 2: "HIGH_OPP"}


def _initialize_from_labels(observations: np.ndarray, labels: np.ndarray) -> dict:
    """Initialize HMM parameters from supervised labels.

    Labels derived from realized PnL percentiles:
        >75th -> HIGH_OPP, <25th -> LOW_OPP, else -> NORMAL
    """
    pi = np.zeros(N_STATES)
    mu = np.zeros((N_STATES, N_FEATURES))
    sigma = np.zeros((N_STATES, N_FEATURES))

    for k in range(N_STATES):
        mask = labels == k
        count = mask.sum()
        pi[k] = count / len(labels) if len(labels) > 0 else 1.0 / N_STATES

        if count > 1:
            mu[k] = observations[mask].mean(axis=0)
            sigma[k] = observations[mask].var(axis=0) + 1e-6
        else:
            mu[k] = observations.mean(axis=0)
            sigma[k] = observations.var(axis=0) + 1e-6

    # Uniform transition matrix as starting point
    A = np.full((N_STATES, N_STATES), 1.0 / N_STATES)

    return {"pi": pi, "A": A, "mu": mu, "sigma": sigma}


def _gaussian_emission(obs: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
    """Compute diagonal Gaussian emission probability."""
    d = len(obs)
    diff = obs - mu
    exponent = -0.5 * np.sum(diff ** 2 / sigma)
    norm = np.sqrt((2 * np.pi) ** d * np.prod(sigma))
    return max(np.exp(exponent) / norm, 1e-300)


def _baum_welch(observations: np.ndarray, params: dict) -> dict:
    """Run Baum-Welch EM algorithm for HMM parameter estimation.

    Args:
        observations: (T, N_FEATURES) array of session observations
        params: Initial parameters dict with pi, A, mu, sigma

    Returns:
        Updated parameters dict
    """
    T = len(observations)
    pi = params["pi"].copy()
    A = params["A"].copy()
    mu = params["mu"].copy()
    sigma = params["sigma"].copy()

    for iteration in range(MAX_EM_ITERATIONS):
        # E-step: Forward-Backward
        # Forward
        alpha = np.zeros((T, N_STATES))
        for k in range(N_STATES):
            alpha[0, k] = pi[k] * _gaussian_emission(observations[0], mu[k], sigma[k])
        alpha[0] /= max(alpha[0].sum(), 1e-300)

        for t in range(1, T):
            for k in range(N_STATES):
                alpha[t, k] = sum(
                    alpha[t - 1, j] * A[j, k] for j in range(N_STATES)
                ) * _gaussian_emission(observations[t], mu[k], sigma[k])
            s = alpha[t].sum()
            if s > 0:
                alpha[t] /= s

        # Backward
        beta = np.zeros((T, N_STATES))
        beta[T - 1] = 1.0

        for t in range(T - 2, -1, -1):
            for k in range(N_STATES):
                beta[t, k] = sum(
                    A[k, j] * _gaussian_emission(observations[t + 1], mu[j], sigma[j]) * beta[t + 1, j]
                    for j in range(N_STATES)
                )
            s = beta[t].sum()
            if s > 0:
                beta[t] /= s

        # Posterior (gamma)
        gamma = alpha * beta
        for t in range(T):
            s = gamma[t].sum()
            if s > 0:
                gamma[t] /= s

        # Xi (transition posterior)
        xi = np.zeros((T - 1, N_STATES, N_STATES))
        for t in range(T - 1):
            for i in range(N_STATES):
                for j in range(N_STATES):
                    xi[t, i, j] = (
                        alpha[t, i] * A[i, j]
                        * _gaussian_emission(observations[t + 1], mu[j], sigma[j])
                        * beta[t + 1, j]
                    )
            s = xi[t].sum()
            if s > 0:
                xi[t] /= s

        # M-step
        pi_new = gamma[0]

        A_new = np.zeros((N_STATES, N_STATES))
        for i in range(N_STATES):
            denom = gamma[:-1, i].sum()
            if denom > 0:
                for j in range(N_STATES):
                    A_new[i, j] = xi[:, i, j].sum() / denom
            else:
                A_new[i] = 1.0 / N_STATES

        mu_new = np.zeros_like(mu)
        sigma_new = np.zeros_like(sigma)
        for k in range(N_STATES):
            weight = gamma[:, k]
            denom = weight.sum()
            if denom > 0:
                mu_new[k] = (weight[:, None] * observations).sum(axis=0) / denom
                diff = observations - mu_new[k]
                sigma_new[k] = (weight[:, None] * diff ** 2).sum(axis=0) / denom + 1e-6
            else:
                mu_new[k] = mu[k]
                sigma_new[k] = sigma[k]

        # Check convergence
        delta = np.max(np.abs(mu_new - mu))
        pi, A, mu, sigma = pi_new, A_new, mu_new, sigma_new

        if delta < CONVERGENCE_THRESHOLD:
            logger.debug("Baum-Welch converged at iteration %d (delta=%.2e)", iteration, delta)
            break

    return {"pi": pi, "A": A, "mu": mu, "sigma": sigma}


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
            "training_window": TRAINING_WINDOW_DAYS,
            "n_observations": T,
            "cold_start": True,
        }

    # Initialize from supervised labels
    labels = _label_from_pnl(session_pnl)
    init_params = _initialize_from_labels(observations, labels)

    # Train with Baum-Welch
    trained_params = _baum_welch(observations, init_params)

    # Compute current state probabilities (last observation's gamma)
    # Forward pass on full sequence
    alpha_seq = np.zeros((T, N_STATES))
    for k in range(N_STATES):
        alpha_seq[0, k] = trained_params["pi"][k] * _gaussian_emission(
            observations[0], trained_params["mu"][k], trained_params["sigma"][k]
        )
    s = alpha_seq[0].sum()
    if s > 0:
        alpha_seq[0] /= s

    for t in range(1, T):
        for k in range(N_STATES):
            alpha_seq[t, k] = sum(
                alpha_seq[t - 1, j] * trained_params["A"][j, k]
                for j in range(N_STATES)
            ) * _gaussian_emission(observations[t], trained_params["mu"][k], trained_params["sigma"][k])
        s = alpha_seq[t].sum()
        if s > 0:
            alpha_seq[t] /= s

    current_state_probs = alpha_seq[-1].tolist()

    # Opportunity weights = P(HIGH_OPP) per session (simplified: use current state probs)
    # In production, forward-predict to each future session window
    opp_weight_raw = current_state_probs[2]  # P(HIGH_OPP)

    # Apply cold start blending (spec: 20-59 days -> 50/50 HMM vs equal weights)
    is_cold = n_trading_days < COLD_START_BLEND_DAYS
    if is_cold:
        # Blend HMM state probs 50/50 with uniform
        equal_probs = [1.0 / N_STATES] * N_STATES
        current_state_probs = [
            0.5 * hmm_p + 0.5 * eq_p
            for hmm_p, eq_p in zip(current_state_probs, equal_probs)
        ]

    result = {
        "hmm_params": {
            "pi": trained_params["pi"].tolist(),
            "A": trained_params["A"].tolist(),
            "mu": trained_params["mu"].tolist(),
            "sigma": trained_params["sigma"].tolist(),
        },
        "current_state_probs": current_state_probs,
        "opportunity_weights": {},  # populated by online inference
        "prior_alpha": {},
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
