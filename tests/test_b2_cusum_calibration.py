# region imports
from AlgorithmImports import *
# endregion
"""F-49: CUSUM bootstrap calibration — literal nested j loop (Q-29)."""

import inspect
import random
from unittest.mock import patch

import numpy as np
import pytest

from captain_offline.blocks.b2_cusum import (
    MAX_SPRINT,
    calibrate_cusum_limits,
    compute_cusum_conditional_on_sprint,
)


def test_compute_conditional_empty_resample():
    assert compute_cusum_conditional_on_sprint([], 1, 0.5) == []


def test_compute_conditional_monotone_positive_series():
    """All-positive drift: sprint grows j steps with cumulative magnitude."""
    r = [1.0, 1.0, 1.0]
    assert compute_cusum_conditional_on_sprint(r, 1, 0.0) == [1.0]
    assert compute_cusum_conditional_on_sprint(r, 2, 0.0) == [2.0]
    assert compute_cusum_conditional_on_sprint(r, 3, 0.0) == [3.0]
    assert compute_cusum_conditional_on_sprint(r, 4, 0.0) == []


def test_compute_conditional_reset_trajectory_locked():
    """Hand-checked trajectory [1,-1,1], allowance 0."""
    r = [1.0, -1.0, 1.0]
    assert compute_cusum_conditional_on_sprint(r, 1, 0.0) == [1.0]
    assert compute_cusum_conditional_on_sprint(r, 2, 0.0) == [1.0]
    assert compute_cusum_conditional_on_sprint(r, 3, 0.0) == [1.0]


def test_conditional_multiple_hits_same_sprint_length():
    """Regression guard: nested conditional can record j multiple times per resample."""
    r = [2.0, -0.5, 2.0]
    k = 1.0
    assert compute_cusum_conditional_on_sprint(r, 1, k) == [1.0, 1.0]


def test_compute_cusum_conditional_source_no_vectorised_shortcuts():
    src = inspect.getsource(compute_cusum_conditional_on_sprint)
    for bad in ("np.cumsum", "np.maximum.accumulate", "scipy", "np.where"):
        assert bad not in src


def test_calibrate_returns_monotoneish_limits():
    random.seed(42)
    np.random.seed(42)
    series = [float(np.random.randn()) for _ in range(100)]
    limits = calibrate_cusum_limits(series, B=200, arl_0=50)
    assert isinstance(limits, dict)
    assert len(limits) > 0
    for j, h in limits.items():
        assert isinstance(j, int)
        assert 1 <= j <= MAX_SPRINT
        assert h >= 0.0
    keys = sorted(limits.keys())
    for a, b in zip(keys, keys[1:]):
        if b == a + 1:
            # stochastic bootstrap: allow modest per-step dips between adjacent j
            assert limits[b] >= limits[a] * 0.75 - 1e-6


@patch("captain_offline.blocks.b2_cusum.logger")
def test_calibrate_logs_sprint_summary(mock_logger):
    random.seed(0)
    np.random.seed(0)
    series = [float(np.random.randn()) for _ in range(100)]
    calibrate_cusum_limits(series, B=30, arl_0=50)
    mock_logger.info.assert_called()
    msg = mock_logger.info.call_args[0][0]
    assert "CUSUM calibration" in msg
    assert "MAX_SPRINT" in msg
