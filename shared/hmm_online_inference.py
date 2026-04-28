"""AIM-16 online HMM: forward-filter step + softmax session weights — numpy-only (doc 22 §7).

TVTP intentionally absent in v1 (Q-10 decision d).

[CONFIRM] smoothing α applied to inferred probability vector vs logits — here: vector exponential smooth.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np


def diag_gaussian_logpdf_row(x: np.ndarray, mu: np.ndarray, var: np.ndarray) -> float:
    """Log-density of diagonal multivariate Gaussian (single row). mu/var shape (d,)."""
    eps = 1e-12
    var_safe = np.maximum(var, eps)
    ld = np.sum(-0.5 * np.log(2 * np.pi * var_safe) - 0.5 * (x - mu) ** 2 / var_safe)
    return float(ld)


def emission_likelihoods(x: np.ndarray, means: np.ndarray, cov_diag: np.ndarray) -> np.ndarray:
    """P(x | state=k) proportional terms; shapes x (D,), means (K,D), cov_diag (K,D)."""
    x = np.asarray(x, dtype=float)
    ll = []
    for k in range(means.shape[0]):
        ll.append(np.exp(diag_gaussian_logpdf_row(x, means[k], cov_diag[k])))
    arr = np.array(ll)
    mx = np.max(arr)
    if mx <= 0:
        return np.ones(len(arr)) / len(arr)
    return arr / mx


def filtered_update(
    pi_last: np.ndarray,
    transition: np.ndarray,
    likelihoods_k: np.ndarray,
) -> np.ndarray:
    """One-time-step forward propagation: predictive * emission (normalized).
    pi_last: (K,) previous filtered distribution
    transition: row-stochastic (K,K) A[i,j]=P(j->i?) hmmlearn convention: row i = from i hmmlearn transmat_: transmat_[i,j] = P(from i -> j) — we'll use row-prev * A as standard HMM transpose — align with hmmlearn: forward uses row_stoch * from_state
    hmmlearn predicts next: pred[j] = sum_i pi[i]*A[i,j]
    """
    pi_prev = np.asarray(pi_last).reshape(-1)
    pred = pi_prev @ transition
    fused = pred * likelihoods_k
    s = fused.sum()
    if s <= 0:
        return np.ones_like(fused) / len(fused)
    return fused / s


def smooth_probability_vector(alpha: np.ndarray, prior: np.ndarray | None, smoothing: float = 0.3) -> np.ndarray:
    """Exponential smoothing on probability vector directly (CONFIRM semantics). beta=smoothing on new."""
    a = np.asarray(alpha, dtype=float)
    if prior is None or np.sum(prior) <= 0:
        return a / a.sum()
    p = np.asarray(prior, dtype=float)
    p /= p.sum()
    out = smoothing * a + (1.0 - smoothing) * p
    s = out.sum()
    return out / s


def probs_to_ny_lon_apac(
    smoothed_three_state: np.ndarray,
    *,
    floor: float = 0.05,
) -> dict[str, float]:
    """Map LOW/NORMAL/HIGH mass to NY/LON/APAC budget keys matching b5_trade_selection session_key."""
    p = np.asarray(smoothed_three_state, dtype=float)
    if p.ndim != 1 or p.shape[0] != 3:
        p = np.ones(3) / 3.0
    p /= p.sum() + 1e-18
    # Fixed linear map LOW_OPP pushes budget away from OPEN hours — doc 22 fixed map stub:
    logits = np.log(p + 1e-18) + np.array([-0.1, 0.05, -0.1])
    w = softmax(logits)
    w_max = np.maximum(w, floor)
    w_max /= w_max.sum()
    return {"NY": float(w_max[0]), "LON": float(w_max[1]), "APAC": float(w_max[2])}


def softmax(vec: np.ndarray) -> np.ndarray:
    z = vec - np.max(vec)
    e = np.exp(z)
    return e / e.sum()


def hmm_params_from_json(hmm_params_blob: Any) -> dict[str, Any] | None:
    """Parse hmm_params STRING from D26."""
    if hmm_params_blob is None:
        return None
    if isinstance(hmm_params_blob, dict):
        return hmm_params_blob
    try:
        return json.loads(hmm_params_blob)
    except (json.JSONDecodeError, TypeError):
        return None
