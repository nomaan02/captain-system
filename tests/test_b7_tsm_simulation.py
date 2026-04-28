"""Tests for P3-PG-14 TSM Monte Carlo (b7_tsm_simulation)."""

from unittest import mock

from captain_offline.blocks.b7_tsm_simulation import (
    _simulate_one_path,
    run_tsm_simulation,
)


def test_simulate_one_path_mdd_breach_checked_per_trade():
    result = _simulate_one_path(
        trade_returns=[100, 100, -250],
        remaining_days=1,
        starting_balance=1000,
        max_drawdown_limit=200,
        max_daily_loss=None,
        profit_target=None,
    )
    assert result["passed"] is False


def test_simulate_one_path_mll_checked_on_daily_aggregate():
    result = _simulate_one_path(
        trade_returns=[-80, -80],
        remaining_days=1,
        starting_balance=1000,
        max_drawdown_limit=None,
        max_daily_loss=150,
        profit_target=None,
    )
    assert result["passed"] is False


def test_simulate_one_path_block_size_is_3_to_7():
    with mock.patch("random.choice", return_value=5) as m:
        _simulate_one_path([1.0] * 20, 3, 1000, None, None, None)
    assert m.call_count == 3


def test_null_pass_probability_for_unconstrained_account():
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": None,
        "max_daily_loss": None,
        "profit_target": None,
        "risk_goal": "GROW_CAPITAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._write_pass_probability") as w:
        result = run_tsm_simulation("acc1", list(range(20)), tsm_config)
    assert result["pass_probability"] is None
    w.assert_called_once_with("acc1", None, None, "GROW_CAPITAL")
    assert result["alert"] is None


def test_sizing_override_scales_returns_before_mc():
    trade_returns = [200.0] * 50
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": 50000,
        "max_daily_loss": 5000,
        "profit_target": 10000,
        "risk_goal": "PASS_EVAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation.N_PATHS", 8), mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._write_pass_probability",
    ), mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._generate_rpt07",
    ), mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._simulate_one_path",
        wraps=_simulate_one_path,
    ) as wrapped:
        run_tsm_simulation("acc1", trade_returns, tsm_config, sizing_override=0.5)
    first_call_returns = wrapped.call_args_list[0][0][0]
    assert all(abs(r - 100.0) < 1e-9 for r in first_call_returns)


def test_sizing_override_default_1_no_scaling():
    trade_returns = [50.0] * 20
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": None,
        "max_daily_loss": None,
        "profit_target": None,
        "risk_goal": "GROW_CAPITAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._write_pass_probability"), mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._generate_rpt07",
    ):
        result = run_tsm_simulation("acc1", trade_returns, tsm_config, sizing_override=1.0)
    assert result["pass_probability"] is None


def test_rpt07_generated_after_simulation():
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": 50000,
        "max_daily_loss": 3000,
        "profit_target": 10000,
        "risk_goal": "PASS_EVAL",
    }
    trade_returns = [100.0] * 30
    with mock.patch("captain_offline.blocks.b7_tsm_simulation.N_PATHS", 12), mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._generate_rpt07",
    ) as gen, mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._write_pass_probability",
    ):
        result = run_tsm_simulation("acc1", trade_returns, tsm_config)
    gen.assert_called_once()
    call_args = gen.call_args[0]
    assert call_args[0] == "acc1"
    assert call_args[3] == "PASS_EVAL"
    assert result["risk_goal"] == "PASS_EVAL"


def test_rpt07_generated_for_unconstrained_account():
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": None,
        "max_daily_loss": None,
        "profit_target": None,
        "risk_goal": "GROW_CAPITAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._generate_rpt07") as gen, mock.patch(
        "captain_offline.blocks.b7_tsm_simulation._write_pass_probability",
    ):
        run_tsm_simulation("acc1", list(range(20)), tsm_config)
    gen.assert_called_once()
    assert gen.call_args[0][1] is None
