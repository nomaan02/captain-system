"""Shared hmm_online_inference utilities."""

import numpy as np

from shared.hmm_online_inference import (
    emission_likelihoods,
    filtered_update,
    probs_to_ny_lon_apac,
    smooth_probability_vector,
)


def test_smoothing_changes_vector():
    a = np.array([0.9, 0.05, 0.05])
    p = np.array([1.0 / 3] * 3)
    sn = smooth_probability_vector(a, p, smoothing=0.3)
    assert np.isclose(sn.sum(), 1.0)
    assert np.any(sn != a)


def test_session_weights_normalized_and_floor():
    w = probs_to_ny_lon_apac(np.array([0.2, 0.25, 0.55]))
    assert isinstance(w["NY"], float)
    s = sum(w.values())
    assert abs(s - 1.0) < 1e-6
    assert min(w.values()) >= 0.05 - 1e-9


def test_forward_preserves_probability_mass():
    pi = np.array([1.0 / 3, 1.0 / 3, 1.0 / 3])
    A = np.ones((3, 3)) / 3
    x = np.zeros(7)
    mu = np.zeros((3, 7))
    sg = np.ones((3, 7))
    lk = emission_likelihoods(x + 1.0, mu, sg)
    out = filtered_update(pi, A, lk)
    assert np.isclose(out.sum(), 1.0)
