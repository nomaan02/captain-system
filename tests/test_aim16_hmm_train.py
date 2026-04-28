"""AIM-16 HMM training invariants."""

import pytest

pytest.importorskip("hmmlearn")

import numpy as np

from captain_offline.blocks.b1_aim16_hmm import train_aim16_hmm

N_FEATURES = 7


def test_train_returns_hmm_params_with_valid_transition_rows():
    rng = np.random.default_rng(42)
    T = 241
    obs = rng.standard_normal(size=(T, 7))
    pn = rng.standard_normal(size=(T,))
    st = train_aim16_hmm(obs, pn, n_trading_days=60)
    hp = st["hmm_params"]
    assert hp is not None
    A = np.array(hp["A"])
    np.testing.assert_allclose(A.sum(axis=1), np.ones(A.shape[0]), atol=3e-3)
    sig = np.array(hp["sigma"])
    assert sig.shape[0] == 3 and sig.shape[-1] == N_FEATURES
