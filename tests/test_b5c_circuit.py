# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 18-24: Circuit Breaker (ON-B5C) regression tests.

Tests the 7-layer circuit breaker per Topstep_Optimisation_Functions.md:
  L0: Scaling cap (XFA only)
  L1: Preemptive hard halt — abs(L_t) + rho_j >= c * e * A
  L2: Budget — n_t >= N (total trades today)
  L3: Per-basket conditional expectancy
  L4: Correlation-adjusted Sharpe
  L5: VIX/DATA_HOLD session halt
  L6: Manual override
"""

import json
from unittest.mock import patch

import pytest

from captain_online.blocks.b5c_circuit_breaker import (
    run_circuit_breaker_screen,
    _layer0_scaling_cap,
    _layer1_preemptive_halt,
    _layer2_budget,
    _layer3_basket_expectancy,
    _layer4_correlation_sharpe,
    _check_all_layers,
)
from tests.fixtures.user_fixtures import make_tsm_configs


# ---------------------------------------------------------------------------
# Mock data loaders
# ---------------------------------------------------------------------------

def _mock_load_cb_params_clean(accounts, model_m=None):
    """CB params with no triggers (p_value > 0.05 -> beta_b effectively 0)."""
    return {
        ac: {
            "beta_b": 0.0, "r_bar": 50.0, "sigma": 100.0,
            "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5,
        }
        for ac in accounts
    }


def _mock_load_intraday_clean(accounts):
    """Clean intraday state — no losses."""
    return {ac: {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}} for ac in accounts}


def _mock_load_cb_params_l3_breach(accounts, model_m=None):
    """CB params where L3 (basket expectancy) will trigger with sufficient L_b."""
    return {
        ac: {
            "beta_b": 0.01, "r_bar": 10.0, "sigma": 100.0,
            "rho_bar": 0.15, "n_observations": 200, "p_value": 0.01,
        }
        for ac in accounts
    }


def _mock_load_intraday_l1_breach(accounts):
    """Intraday state with large daily loss for L1 preemptive halt."""
    return {ac: {"l_t": -600.0, "n_t": 1, "l_b": {}, "n_b": {}} for ac in accounts}


def _mock_load_intraday_l2_breach(accounts):
    """Intraday state with large losses to exhaust dollar budget."""
    return {ac: {"l_t": -1400.0, "n_t": 5, "l_b": {}, "n_b": {}} for ac in accounts}


def _mock_load_intraday_l3_breach(accounts):
    """Intraday state with basket loss driving mu_b <= 0."""
    # r_bar=10, beta_b=0.01, L_b=-1500 -> mu_b = 10 + 0.01*(-1500) = -5 <= 0
    return {ac: {"l_t": -1500.0, "n_t": 5, "l_b": {"4": -1500.0}, "n_b": {"4": 5}} for ac in accounts}


def _make_topstep_tsm(accounts, **overrides):
    """TSM with topstep_params populated for CB layers."""
    base_params = {
        "p": 0.005,
        "e": 0.01,
        "c": 0.5,
        "lambda": 0,
    }
    base_params.update(overrides.pop("topstep_params_overrides", {}))
    return make_tsm_configs(
        accounts,
        current_balance=150_000.0,
        topstep_optimisation=True,
        topstep_params=json.dumps(base_params),
        **overrides,
    )


# ---------------------------------------------------------------------------
# Scenario 18: All layers pass
# ---------------------------------------------------------------------------

class TestAllLayersPass:
    """Scenario 18: All CB layers pass -> no blocks."""

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_no_blocks(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        tsm = _make_topstep_tsm(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["ES"],
            final_contracts={"ES": {"acc_eval_1": 3}},
            account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
            sl_distance=4.0,
            point_value=50.0,
        )

        assert "ES" in result["recommended_trades"]
        assert result["final_contracts"]["ES"]["acc_eval_1"] == 3
        assert result["account_recommendation"]["ES"]["acc_eval_1"] == "TRADE"


# ---------------------------------------------------------------------------
# Scenario 19: L0 Scaling Cap (XFA only)
# ---------------------------------------------------------------------------

class TestL0ScalingCap:
    """Layer 0: Scaling cap blocks when open + proposed > tier cap."""

    def test_scaling_cap_blocks(self):
        tsm = {
            "scaling_plan_active": True,
            "scaling_tier_micros": 30,
        }
        open_positions = [{"account": "xfa_1", "contracts": 25}]
        reason = _layer0_scaling_cap(tsm, proposed_contracts=10, open_positions=open_positions, ac_id="xfa_1")
        assert reason is not None
        assert "L0" in reason
        assert "scaling cap" in reason

    def test_scaling_cap_passes(self):
        tsm = {
            "scaling_plan_active": True,
            "scaling_tier_micros": 30,
        }
        open_positions = [{"account": "xfa_1", "contracts": 10}]
        reason = _layer0_scaling_cap(tsm, proposed_contracts=10, open_positions=open_positions, ac_id="xfa_1")
        assert reason is None

    def test_live_account_skips_scaling(self):
        """Live accounts have no scaling plan — always passes."""
        tsm = {"scaling_plan_active": False}
        reason = _layer0_scaling_cap(tsm, proposed_contracts=100)
        assert reason is None


# ---------------------------------------------------------------------------
# Phase 4 (F-09): Layer 0 via open_positions kwarg
# ---------------------------------------------------------------------------

class TestL0ScalingCapViaOpenPositions:
    """Layer 0 uses open_positions list, not tsm.current_open_micros."""

    def test_blocks_when_open_positions_exceed_tier(self):
        """Positions for ac_id=A1 total 25; proposed 10 -> 35 > tier 30 -> BLOCKED."""
        tsm = {"scaling_plan_active": True, "scaling_tier_micros": 30}
        open_positions = [
            {"account": "A1", "contracts": 15},
            {"account": "A1", "contracts": 10},
            {"account": "A2", "contracts": 100},  # Different account — must NOT count
        ]
        reason = _layer0_scaling_cap(tsm, proposed_contracts=10, open_positions=open_positions, ac_id="A1")
        assert reason is not None
        assert "L0" in reason

    def test_only_counts_matching_account(self):
        """Other accounts' positions do not count toward this account's cap."""
        tsm = {"scaling_plan_active": True, "scaling_tier_micros": 30}
        open_positions = [{"account": "OTHER", "contracts": 999}]
        reason = _layer0_scaling_cap(tsm, proposed_contracts=10, open_positions=open_positions, ac_id="A1")
        assert reason is None  # 0 + 10 <= 30

    def test_empty_positions_passes(self):
        """No open positions -> 0 open micros -> not blocked (below tier)."""
        tsm = {"scaling_plan_active": True, "scaling_tier_micros": 30}
        reason = _layer0_scaling_cap(tsm, proposed_contracts=10, open_positions=[], ac_id="A1")
        assert reason is None

    def test_none_positions_passes(self):
        """open_positions=None treated as empty list."""
        tsm = {"scaling_plan_active": True, "scaling_tier_micros": 30}
        reason = _layer0_scaling_cap(tsm, proposed_contracts=10, open_positions=None, ac_id="A1")
        assert reason is None

    def test_live_account_not_blocked_by_open_positions(self):
        """Eval/Live accounts (scaling_plan_active=False) skip L0 entirely."""
        tsm = {"scaling_plan_active": False}
        open_positions = [{"account": "A1", "contracts": 100}]
        reason = _layer0_scaling_cap(tsm, proposed_contracts=100, open_positions=open_positions, ac_id="A1")
        assert reason is None

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=lambda accounts, model_m=None: {ac: {"beta_b": 0.0, "r_bar": 50.0, "sigma": 100.0, "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5} for ac in accounts})
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=lambda accounts: {ac: {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}} for ac in accounts})
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_run_circuit_breaker_screen_blocks_via_open_positions(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        """Integration: run_circuit_breaker_screen respects open_positions for L0."""
        tsm = make_tsm_configs(
            ["xfa_acc"],
            current_balance=150_000.0,
            topstep_optimisation=True,
            scaling_plan_active=True,
            scaling_tier_micros=30,
            topstep_params=json.dumps({"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0}),
        )
        open_positions = [{"account": "xfa_acc", "contracts": 25}]
        result = run_circuit_breaker_screen(
            recommended_trades=["MNQ"],
            final_contracts={"MNQ": {"xfa_acc": 10}},
            account_recommendation={"MNQ": {"xfa_acc": "TRADE"}},
            account_skip_reason={"MNQ": {"xfa_acc": None}},
            accounts=["xfa_acc"],
            tsm_configs=tsm,
            session_id=1,
            open_positions=open_positions,
        )
        # 25 open + 10 proposed = 35 > tier cap 30 -> BLOCKED
        assert "MNQ" not in result["recommended_trades"]
        assert result["account_recommendation"]["MNQ"]["xfa_acc"] == "BLOCKED"

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=lambda accounts, model_m=None: {ac: {"beta_b": 0.0, "r_bar": 50.0, "sigma": 100.0, "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5} for ac in accounts})
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=lambda accounts: {ac: {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}} for ac in accounts})
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_eval_account_not_blocked_by_open_positions(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        """Integration (plan check): Eval account 20319784 (scaling_plan_active=False) unaffected by L0.

        Uses tiny sl_distance/point_value (rho_j ≈ 0.5) so L1/L2 don't trigger,
        leaving L0 as the only candidate blocker — which must skip for eval accounts.
        """
        tsm = make_tsm_configs(
            ["20319784"],
            current_balance=150_000.0,
            topstep_optimisation=True,
            topstep_params=json.dumps({"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0}),
        )
        # No scaling_plan_active=True -> L0 always skips regardless of open positions
        open_positions = [{"account": "20319784", "contracts": 999}]
        result = run_circuit_breaker_screen(
            recommended_trades=["MNQ"],
            final_contracts={"MNQ": {"20319784": 5}},
            account_recommendation={"MNQ": {"20319784": "TRADE"}},
            account_skip_reason={"MNQ": {"20319784": None}},
            accounts=["20319784"],
            tsm_configs=tsm,
            session_id=1,
            open_positions=open_positions,
            sl_distance=0.1,   # tiny rho_j (~0.5) so L1/L2 don't fire
            point_value=1.0,
        )
        # Eval account skips L0 -> all other layers pass with clean intraday state
        assert "MNQ" in result["recommended_trades"]


# ---------------------------------------------------------------------------
# Scenario 20: L1 Preemptive Hard Halt
# ---------------------------------------------------------------------------

class TestL1PreemptiveHalt:
    """Layer 1: abs(L_t) + rho_j >= c * e * A -> BLOCKED."""

    def test_preemptive_halt_blocks(self):
        """Spec example: L_t=-495, rho_j=495, L_halt=750 -> 990 >= 750 -> BLOCKED."""
        tsm = {
            "current_balance": 150_000.0,
            "topstep_params": json.dumps({"c": 0.5, "e": 0.01}),
        }
        intraday = {"l_t": -495.0}
        # rho_j = contracts * (SL * pv + fee) = 7 * (1.0 * 70.0 + 0.74) = 495.18
        rho_j = 495.0
        reason = _layer1_preemptive_halt(intraday, tsm, rho_j)
        assert reason is not None
        assert "L1" in reason
        # L_halt = 0.5 * 0.01 * 150000 = 750
        # |L_t| + rho_j = 495 + 495 = 990 >= 750

    def test_preemptive_halt_passes(self):
        """Small loss + small risk -> passes."""
        tsm = {
            "current_balance": 150_000.0,
            "topstep_params": json.dumps({"c": 0.5, "e": 0.01}),
        }
        intraday = {"l_t": -100.0}
        rho_j = 200.0  # |L_t| + rho_j = 300 < 750
        reason = _layer1_preemptive_halt(intraday, tsm, rho_j)
        assert reason is None

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_l1_breach)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_l1_integration_blocks(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        """Integration: L_t=-600, 3 contracts * (4*50+0) = 600, total=1200 >= 750."""
        tsm = _make_topstep_tsm(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["ES"],
            final_contracts={"ES": {"acc_eval_1": 3}},
            account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
            sl_distance=4.0,
            point_value=50.0,
            fee_per_trade=0.0,
        )

        assert result["account_recommendation"]["ES"]["acc_eval_1"] == "BLOCKED"
        assert result["final_contracts"]["ES"]["acc_eval_1"] == 0
        assert "Circuit breaker" in result["account_skip_reason"]["ES"]["acc_eval_1"]
        assert "L1" in result["account_skip_reason"]["ES"]["acc_eval_1"]


# ---------------------------------------------------------------------------
# Scenario 21: L2 Budget Exhausted
# ---------------------------------------------------------------------------

class TestL2Budget:
    """Layer 2: remaining_budget = E - |L_t|; IF remaining < rho_j -> BLOCKED."""

    def test_budget_exhausted(self):
        """Large losses consumed the dollar budget."""
        tsm = {
            "current_balance": 150_000.0,
            "topstep_params": json.dumps({"e": 0.01}),
        }
        # E = 0.01 * 150000 = 1500, |L_t| = 1400, remaining = 100 < rho_j=200
        intraday = {"l_t": -1400.0}
        reason = _layer2_budget(intraday, tsm, rho_j=200.0)
        assert reason is not None
        assert "L2" in reason
        assert "budget" in reason

    def test_budget_available(self):
        """No losses, plenty of dollar budget remaining."""
        tsm = {
            "current_balance": 150_000.0,
            "topstep_params": json.dumps({"e": 0.01}),
        }
        # E = 1500, |L_t| = 0, remaining = 1500 > rho_j=200
        intraday = {"l_t": 0.0}
        reason = _layer2_budget(intraday, tsm, rho_j=200.0)
        assert reason is None

    def test_budget_exact_boundary(self):
        """rho_j exceeds remaining by $1 -> BLOCKED."""
        tsm = {
            "current_balance": 150_000.0,
            "topstep_params": json.dumps({"e": 0.01}),
        }
        # E = 1500, |L_t| = 1301, remaining = 199 < rho_j=200
        intraday = {"l_t": -1301.0}
        reason = _layer2_budget(intraday, tsm, rho_j=200.0)
        assert reason is not None
        assert "L2" in reason

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_l2_breach)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_l2_integration_blocks(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        tsm = _make_topstep_tsm(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["ES"],
            final_contracts={"ES": {"acc_eval_1": 1}},
            account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
            sl_distance=4.0,
            point_value=50.0,
        )

        assert result["account_recommendation"]["ES"]["acc_eval_1"] == "BLOCKED"
        assert "Circuit breaker" in result["account_skip_reason"]["ES"]["acc_eval_1"]


# ---------------------------------------------------------------------------
# Scenario 22: L3 Basket Expectancy
# ---------------------------------------------------------------------------

class TestL3BasketExpectancy:
    """Layer 3: mu_b = r_bar + beta_b * L_b <= 0 -> BLOCKED."""

    def test_negative_expectancy_blocks(self):
        """r_bar=10, beta_b=0.01, L_b=-1500 -> mu_b = 10 + 0.01*(-1500) = -5 <= 0."""
        cb = {"r_bar": 10.0, "beta_b": 0.01, "p_value": 0.01, "n_observations": 200}
        intraday = {"l_b": {"4": -1500.0}}
        reason = _layer3_basket_expectancy(cb, intraday, model_m="4")
        assert reason is not None
        assert "L3" in reason
        assert "expectancy" in reason

    def test_positive_expectancy_passes(self):
        """r_bar=50, beta_b=0.01, L_b=-100 -> mu_b = 50 + 0.01*(-100) = 49 > 0."""
        cb = {"r_bar": 50.0, "beta_b": 0.01, "p_value": 0.01, "n_observations": 200}
        intraday = {"l_b": {"4": -100.0}}
        reason = _layer3_basket_expectancy(cb, intraday, model_m="4")
        assert reason is None

    def test_cold_start_skips(self):
        """beta_b insignificant (p > 0.05) -> beta_b forced to 0 -> mu_b = r_bar > 0."""
        cb = {"r_bar": 50.0, "beta_b": 0.5, "p_value": 0.5, "n_observations": 200}
        intraday = {"l_b": {"4": -1000.0}}
        reason = _layer3_basket_expectancy(cb, intraday, model_m="4")
        assert reason is None  # beta_b zeroed due to insignificance

    def test_no_params_skips(self):
        """No CB params -> cold start -> skip."""
        reason = _layer3_basket_expectancy(None, {"l_b": {}}, model_m="4")
        assert reason is None

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_l3_breach)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_l3_breach)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_l3_integration_blocks(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        tsm = _make_topstep_tsm(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["ES"],
            final_contracts={"ES": {"acc_eval_1": 1}},
            account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
            sl_distance=4.0,
            point_value=50.0,
            model_m="4",
        )

        assert result["account_recommendation"]["ES"]["acc_eval_1"] == "BLOCKED"
        assert "Circuit breaker" in result["account_skip_reason"]["ES"]["acc_eval_1"]


# ---------------------------------------------------------------------------
# Scenario 23: L4 Correlation-Adjusted Sharpe
# ---------------------------------------------------------------------------

class TestL4CorrelationSharpe:
    """Layer 4: rolling_basket_sharpe(lookback=60d) <= lambda -> BLOCKED."""

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns")
    def test_sharpe_below_threshold_blocks(self, mock_returns):
        """Rolling Sharpe from trade history below lambda -> BLOCKED."""
        # mean ~= 1, sigma ~= 7.3 -> S ~= 0.14 < 0.5
        mock_returns.return_value = [1, -9, 11, 1, -9, 11, 1, -9, 11, 1]
        tsm = {"topstep_params": json.dumps({"lambda": 0.5})}
        reason = _layer4_correlation_sharpe(None, {}, tsm, model_m=None)
        assert reason is not None
        assert "L4" in reason
        assert "Sharpe" in reason

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns")
    def test_sharpe_above_threshold_passes(self, mock_returns):
        """Positive Sharpe above lambda=0 -> passes."""
        mock_returns.return_value = [10, 12, 8, 11, 9, 10, 12, 8, 11, 9]
        tsm = {"topstep_params": json.dumps({"lambda": 0})}
        reason = _layer4_correlation_sharpe(None, {}, tsm, model_m=None)
        assert reason is None

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns")
    def test_cold_start_passes(self, mock_returns):
        """Fewer than 10 trades -> skip (insufficient data)."""
        mock_returns.return_value = [10, 12, 8]
        tsm = {"topstep_params": json.dumps({"lambda": 0.5})}
        reason = _layer4_correlation_sharpe(None, {}, tsm, model_m=None)
        assert reason is None


# ---------------------------------------------------------------------------
# Phase 6 (F-12): Per-asset CB resolution via locked_strategies + assets_detail
# ---------------------------------------------------------------------------

class TestPerAssetResolutionViaLockedStrategies:
    """Verify B5C honours per-asset point_value + sl_multiple instead of
    the scalar sl_distance/point_value defaults.

    Regression: before Phase 2, MNQ (point_value=2.0) was sized against the
    default point_value=50.0, inflating rho_j ~25x and tripping L1 spuriously.
    """

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_mnq_pv_2_does_not_trip_l1(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        """MNQ (pv=2.0) sized correctly: rho_j=$120, L_halt=$750 -> PASSES.

        Without per-asset resolution, default pv=50.0 would yield
        rho_j = 15 * (4 * 50) = $3000 >> $750 -> spurious L1 BLOCK.
        """
        tsm = _make_topstep_tsm(["acc_eval_1"])
        # threshold=4.0 ensures resolve_sizing_sl returns 4.0 even when
        # the historical OR range lookup is unavailable in test env.
        locked_strategies = {"MNQ": {"sl_multiple": 0.10, "threshold": 4.0}}
        assets_detail = {"MNQ": {"point_value": 2.0}}

        result = run_circuit_breaker_screen(
            recommended_trades=["MNQ"],
            final_contracts={"MNQ": {"acc_eval_1": 15}},
            account_recommendation={"MNQ": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"MNQ": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
            sl_distance=4.0,    # scalar defaults — should NOT be used for MNQ
            point_value=50.0,   # scalar defaults — should NOT be used for MNQ
            locked_strategies=locked_strategies,
            assets_detail=assets_detail,
        )

        # rho_j = 15 * (4.0 * 2.0 + 0) = $120 < L_halt=$750 -> PASS
        assert "MNQ" in result["recommended_trades"]
        assert result["account_recommendation"]["MNQ"]["acc_eval_1"] == "TRADE"
        assert result["final_contracts"]["MNQ"]["acc_eval_1"] == 15

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_scalar_default_would_trip_l1_proves_resolution_matters(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        """Control: same setup but WITHOUT locked_strategies/assets_detail.

        Demonstrates the bug Phase 2 fixed — without per-asset resolution,
        the default pv=50.0 inflates rho_j and L1 trips spuriously.
        """
        tsm = _make_topstep_tsm(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["MNQ"],
            final_contracts={"MNQ": {"acc_eval_1": 15}},
            account_recommendation={"MNQ": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"MNQ": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
            sl_distance=4.0,
            point_value=50.0,
            # locked_strategies / assets_detail intentionally omitted
        )

        # rho_j = 15 * (4 * 50) = $3000 >> L_halt=$750 -> BLOCKED at L1
        assert result["account_recommendation"]["MNQ"]["acc_eval_1"] == "BLOCKED"
        assert "L1" in result["account_skip_reason"]["MNQ"]["acc_eval_1"]


# ---------------------------------------------------------------------------
# Scenario 24: Non-Topstep bypass
# ---------------------------------------------------------------------------

class TestNonTopstepBypass:
    """Non-Topstep accounts should bypass CB entirely."""

    @patch("captain_online.blocks.b5c_circuit_breaker._get_rolling_trade_returns", return_value=[10, 12, 8, 11, 9, 10, 12, 8, 11, 9])
    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params", side_effect=_mock_load_cb_params_clean)
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state", side_effect=_mock_load_intraday_l1_breach)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_non_topstep_bypasses(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb, mock_returns):
        """Account without topstep_optimisation should not be blocked."""
        tsm = make_tsm_configs(["acc_1"], topstep_optimisation=False)
        result = run_circuit_breaker_screen(
            recommended_trades=["ES"],
            final_contracts={"ES": {"acc_1": 3}},
            account_recommendation={"ES": {"acc_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_1": None}},
            accounts=["acc_1"],
            tsm_configs=tsm,
            session_id=1,
        )

        assert "ES" in result["recommended_trades"]
        assert result["account_recommendation"]["ES"]["acc_1"] == "TRADE"
