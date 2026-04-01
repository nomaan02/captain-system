# region imports
from AlgorithmImports import *
# endregion
"""Scenario 24: End-to-End Pipeline regression test.

Tests the full Online signal pipeline: B2 -> B3 -> B4 -> B5 -> B5B -> B5C -> B6
with synthetic data, verifying a signal is generated end-to-end.
"""

from unittest.mock import patch, MagicMock

import pytest

from captain_online.blocks.b2_regime_probability import run_regime_probability
from shared.aim_compute import run_aim_aggregation
from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
from captain_online.blocks.b5_trade_selection import run_trade_selection
from captain_online.blocks.b5b_quality_gate import run_quality_gate
from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen
from captain_online.blocks.b6_signal_output import run_signal_output

from tests.fixtures.synthetic_data import (
    make_features, make_regime_model_neutral, make_ewma_states,
    make_kelly_params, make_assets_detail, make_locked_strategy,
)
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_configs
from tests.fixtures.aim_fixtures import make_aim_states_all_active, make_aim_weights


def _mock_compute_aim_modifier(aim_id, features, asset_id, state):
    return {"modifier": 1.0, "confidence": 0.8, "reason_tag": f"TEST_{aim_id}"}


class TestFullPipelineE2E:
    """Scenario 24: Full B2->B3->B4->B5->B5B->B5C->B6 pipeline."""

    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params",
           return_value={"acc_eval_1": {"beta_b": 0.0, "r_bar": 50.0, "sigma": 10.0, "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5}})
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state",
           return_value={"acc_eval_1": {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}}})
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    @patch("captain_online.blocks.b5b_quality_gate._load_system_param",
           side_effect=lambda k, d: {"quality_hard_floor": 0.003, "quality_ceiling": 0.010}.get(k, d))
    @patch("captain_online.blocks.b5b_quality_gate._get_trade_count", return_value=100)
    @patch("captain_online.blocks.b5b_quality_gate._log_quality_results")
    @patch("captain_online.blocks.b5_trade_selection._load_correlation_matrix", return_value={})
    @patch("captain_online.blocks.b5_trade_selection._get_correlation", return_value=0.0)
    @patch("shared.aim_compute.compute_aim_modifier",
           side_effect=_mock_compute_aim_modifier)
    @patch("captain_online.blocks.b6_signal_output._publish_signals")
    @patch("captain_online.blocks.b6_signal_output._log_signal_output")
    @patch("captain_online.blocks.b6_signal_output._load_system_param",
           side_effect=lambda k, d: d)
    @patch("captain_online.blocks.b6_signal_output._get_daily_pnl", return_value=0.0)
    def test_signal_generated_e2e(
        self, mock_pnl, mock_b6_param, mock_b6_log, mock_b6_pub,
        mock_aim, mock_corr, mock_corr_mat, mock_qlog, mock_tc,
        mock_qparam, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb,
    ):
        # Setup
        features = make_features("ES")
        models = make_regime_model_neutral("ES")
        aim_ids = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
        aim_states = make_aim_states_all_active("ES", aim_ids)
        aim_weights = make_aim_weights("ES", aim_ids)
        # Provide EWMA/Kelly for BOTH regimes so B5 lookup works regardless of argmax
        ewma_low = make_ewma_states("ES", win_rate=0.55, avg_win=200.0, avg_loss=100.0, regime="LOW_VOL")
        ewma_high = make_ewma_states("ES", win_rate=0.55, avg_win=200.0, avg_loss=100.0, regime="HIGH_VOL")
        ewma = {**ewma_low, **ewma_high}
        kelly_low = make_kelly_params("ES", kelly_full=0.10, regime="LOW_VOL")
        kelly_high = make_kelly_params("ES", kelly_full=0.10, regime="HIGH_VOL")
        kelly = {**kelly_low, **kelly_high}
        user_silo = make_user_silo(accounts=["acc_eval_1"])
        tsm = make_tsm_configs(["acc_eval_1"])
        strategy = make_locked_strategy("ES")
        detail = make_assets_detail("ES")

        # B2: Regime
        b2_result = run_regime_probability(["ES"], features, models)
        assert "regime_probs" in b2_result
        regime_probs = b2_result["regime_probs"]
        regime_uncertain = b2_result["regime_uncertain"]

        # B3: AIM Aggregation
        b3_result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)
        assert "combined_modifier" in b3_result
        combined_modifier = b3_result["combined_modifier"]
        aim_breakdown = b3_result["aim_breakdown"]

        # B4: Kelly Sizing
        b4_result = run_kelly_sizing(
            active_assets=["ES"],
            regime_probs=regime_probs,
            regime_uncertain=regime_uncertain,
            combined_modifier=combined_modifier,
            kelly_params=kelly,
            ewma_states=ewma,
            tsm_configs=tsm,
            sizing_overrides={},
            user_silo=user_silo,
            locked_strategies=strategy,
            assets_detail=detail,
            session_id=1,
        )
        assert b4_result is not None
        assert b4_result["silo_blocked"] is False
        final_contracts = b4_result["final_contracts"]
        account_rec = b4_result["account_recommendation"]
        account_skip = b4_result["account_skip_reason"]

        # B5: Trade Selection
        b5_result = run_trade_selection(
            active_assets=["ES"],
            final_contracts=final_contracts,
            account_recommendation=account_rec,
            account_skip_reason=account_skip,
            ewma_states=ewma,
            regime_probs=regime_probs,
            user_silo=user_silo,
            session_id=1,
        )
        selected_trades = b5_result["selected_trades"]
        expected_edge = b5_result["expected_edge"]
        final_contracts = b5_result["final_contracts"]
        account_rec = b5_result["account_recommendation"]
        account_skip = b5_result["account_skip_reason"]

        # B5B: Quality Gate
        b5b_result = run_quality_gate(
            selected_trades=selected_trades,
            expected_edge=expected_edge,
            combined_modifier=combined_modifier,
            regime_probs=regime_probs,
            user_silo=user_silo,
            session_id=1,
        )
        recommended = b5b_result["recommended_trades"]
        available_nr = b5b_result["available_not_recommended"]
        quality_results = b5b_result["quality_results"]

        # B5C: Circuit Breaker
        b5c_result = run_circuit_breaker_screen(
            recommended_trades=recommended,
            final_contracts=final_contracts,
            account_recommendation=account_rec,
            account_skip_reason=account_skip,
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
        )
        recommended = b5c_result["recommended_trades"]
        final_contracts = b5c_result["final_contracts"]
        account_rec = b5c_result["account_recommendation"]
        account_skip = b5c_result["account_skip_reason"]

        # B6: Signal Output
        b6_result = run_signal_output(
            recommended_trades=recommended,
            available_not_recommended=available_nr,
            quality_results=quality_results,
            final_contracts=final_contracts,
            account_recommendation=account_rec,
            account_skip_reason=account_skip,
            features=features,
            ewma_states=ewma,
            aim_breakdown=aim_breakdown,
            combined_modifier=combined_modifier,
            regime_probs=regime_probs,
            expected_edge=expected_edge,
            locked_strategies=strategy,
            tsm_configs=tsm,
            user_silo=user_silo,
            assets_detail=detail,
            session_id=1,
        )

        # ASSERTIONS: Signal was generated
        signals = b6_result["signals"]
        assert len(signals) >= 1, "Expected at least 1 signal from E2E pipeline"

        signal = signals[0]
        assert signal["asset"] == "ES"
        assert signal["user_id"] == "primary_user"
        assert signal["signal_id"].startswith("SIG-")
        assert signal["confidence_tier"] in ("HIGH", "MEDIUM", "LOW")
        assert "per_account" in signal
        assert "acc_eval_1" in signal["per_account"]

        # Redis publish was called
        mock_b6_pub.assert_called_once()
