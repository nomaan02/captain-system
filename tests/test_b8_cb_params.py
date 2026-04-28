"""Tests for P3-PG-16C circuit breaker params (b8_cb_params)."""

from datetime import datetime
from unittest import mock

import numpy as np

from captain_offline.blocks.b8_cb_params import (
    _build_regression_arrays,
    _ols_regression,
    estimate_cb_params,
)


def test_running_loss_accumulates_cross_day():
    trades = [
        {"pnl": 10, "contracts": 1, "ts": datetime(2026, 1, 1, 10, 0)},
        {"pnl": -20, "contracts": 1, "ts": datetime(2026, 1, 1, 11, 0)},
        {"pnl": 5, "contracts": 1, "ts": datetime(2026, 1, 2, 10, 0)},
        {"pnl": -15, "contracts": 1, "ts": datetime(2026, 1, 2, 11, 0)},
    ]
    x_vals, _y = _build_regression_arrays(trades)
    assert x_vals == [0.0, 0.0, 20.0, 20.0]


def test_running_loss_ignores_profits():
    trades = [
        {"pnl": 50, "contracts": 1, "ts": datetime(2026, 1, 1, 9, 0)},
        {"pnl": 50, "contracts": 1, "ts": datetime(2026, 1, 1, 10, 0)},
        {"pnl": -30, "contracts": 1, "ts": datetime(2026, 1, 1, 11, 0)},
    ]
    x_vals, _y = _build_regression_arrays(trades)
    assert x_vals == [0.0, 0.0, 0.0]


def test_r_bar_is_unconditional_mean():
    x = np.array([0.0, 10.0, 20.0, 30.0])
    y = np.array([2.0, 4.0, 3.0, 5.0])
    result = _ols_regression(x, y)
    expected_r_bar = float(np.mean(y))
    assert abs(result["r_bar"] - expected_r_bar) < 1e-9


def test_r_bar_not_ols_intercept():
    x = np.array([0.0, 10.0, 20.0, 30.0])
    y = np.array([2.0, 4.0, 3.0, 5.0])
    result = _ols_regression(x, y)
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    beta = result["beta_b"]
    ols_intercept = y_mean - beta * x_mean
    assert abs(result["r_bar"] - y_mean) < 1e-9
    assert abs(result["r_bar"] - ols_intercept) > 1e-6


def test_p_value_gate_absent():
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    y = np.array([0.1, 0.2, 0.15, 0.3, 0.25, 0.35, 0.2, 0.4, 0.3, 0.45])
    result = _ols_regression(x, y)
    assert abs(result["beta_b"]) > 1e-6


def test_n_lt_10_still_triggers_early_return():
    some_ts = datetime(2026, 1, 1, 12, 0)
    with mock.patch(
        "captain_offline.blocks.b8_cb_params._load_trades_by_account_model",
        return_value=[{"pnl": 10, "contracts": 1, "ts": some_ts}] * 5,
    ):
        with mock.patch("captain_offline.blocks.b8_cb_params._save_params") as saved:
            estimate_cb_params("acc1", 7)
    saved_params = saved.call_args[0][2]
    assert saved_params["beta_b"] == 0.0
    assert saved_params["cold_start"] is True


def test_cold_start_true_for_n_lt_100():
    some_ts = datetime(2026, 1, 1, 12, 0)
    trades_50 = [{"pnl": (i % 2 - 0.3) * 10, "contracts": 1, "ts": some_ts} for i in range(50)]
    with mock.patch(
        "captain_offline.blocks.b8_cb_params._load_trades_by_account_model",
        return_value=trades_50,
    ):
        with mock.patch("captain_offline.blocks.b8_cb_params._save_params") as saved:
            estimate_cb_params("acc1", 7)
    saved_params = saved.call_args[0][2]
    assert saved_params["cold_start"] is True


def test_cold_start_false_for_n_ge_100():
    some_ts = datetime(2026, 1, 1, 12, 0)
    trades_120 = [{"pnl": (i % 2 - 0.3) * 10, "contracts": 1, "ts": some_ts} for i in range(120)]
    with mock.patch(
        "captain_offline.blocks.b8_cb_params._load_trades_by_account_model",
        return_value=trades_120,
    ):
        with mock.patch("captain_offline.blocks.b8_cb_params._save_params") as saved:
            estimate_cb_params("acc1", 7)
    saved_params = saved.call_args[0][2]
    assert saved_params["cold_start"] is False
