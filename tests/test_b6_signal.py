# region imports
from AlgorithmImports import *
# endregion
"""Scenario 21: Signal Output (ON-B6) regression tests."""

from unittest.mock import patch, MagicMock

import pytest

from captain_online.blocks.b6_signal_output import (
    run_signal_output, _classify_confidence, _determine_direction,
    _compute_tp, _compute_sl,
)
from tests.fixtures.synthetic_data import (
    make_features, make_ewma_states, make_assets_detail, make_locked_strategy,
)
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_configs


REQUIRED_SIGNAL_FIELDS = [
    "signal_id", "user_id", "asset", "session", "timestamp",
    "direction", "tp_level", "sl_level", "sl_method", "entry_conditions",
    "per_account", "aim_breakdown", "combined_modifier", "regime_state",
    "regime_probs", "expected_edge", "win_rate", "payoff_ratio",
    "user_total_capital", "user_daily_pnl",
    "quality_score", "quality_multiplier", "data_maturity",
    "confidence_tier",
]


class TestSignalStructure:
    """Scenario 21: Full signal has all required fields."""

    @patch("captain_online.blocks.b6_signal_output._publish_signals")
    @patch("captain_online.blocks.b6_signal_output._log_signal_output")
    @patch("captain_online.blocks.b6_signal_output._load_system_param", side_effect=lambda k, d: d)
    @patch("captain_online.blocks.b6_signal_output._get_daily_pnl", return_value=0.0)
    def test_all_fields_present(self, mock_pnl, mock_param, mock_log, mock_pub):
        result = run_signal_output(
            recommended_trades=["ES"],
            available_not_recommended=[],
            quality_results={"ES": {"quality_score": 0.015, "quality_multiplier": 1.0, "data_maturity": 1.0}},
            final_contracts={"ES": {"acc_eval_1": 2}},
            account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_eval_1": None}},
            features=make_features("ES"),
            ewma_states=make_ewma_states("ES"),
            aim_breakdown={"ES": {1: {"modifier": 1.1}}},
            combined_modifier={"ES": 1.05},
            regime_probs={"ES": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4}},
            expected_edge={"ES": 0.02},
            locked_strategies=make_locked_strategy("ES"),
            tsm_configs=make_tsm_configs(["acc_eval_1"]),
            user_silo=make_user_silo(accounts=["acc_eval_1"]),
            assets_detail=make_assets_detail("ES"),
            session_id=1,
        )

        assert len(result["signals"]) == 1
        signal = result["signals"][0]

        for field in REQUIRED_SIGNAL_FIELDS:
            assert field in signal, f"Missing required field: {field}"

        assert signal["asset"] == "ES"
        assert signal["user_id"] == "primary_user"
        assert signal["session"] == 1
        assert signal["signal_id"].startswith("SIG-")

        # Per-account breakdown present
        assert "acc_eval_1" in signal["per_account"]
        pa = signal["per_account"]["acc_eval_1"]
        assert pa["contracts"] == 2
        assert pa["recommendation"] == "TRADE"

    @patch("captain_online.blocks.b6_signal_output._publish_signals")
    @patch("captain_online.blocks.b6_signal_output._log_signal_output")
    @patch("captain_online.blocks.b6_signal_output._load_system_param", side_effect=lambda k, d: d)
    @patch("captain_online.blocks.b6_signal_output._get_daily_pnl", return_value=0.0)
    def test_below_threshold_transparency(self, mock_pnl, mock_param, mock_log, mock_pub):
        result = run_signal_output(
            recommended_trades=[],
            available_not_recommended=["NQ"],
            quality_results={"NQ": {"quality_score": 0.001, "quality_multiplier": 0.0, "data_maturity": 0.5}},
            final_contracts={},
            account_recommendation={},
            account_skip_reason={},
            features=make_features("NQ"),
            ewma_states={},
            aim_breakdown={},
            combined_modifier={},
            regime_probs={},
            expected_edge={"NQ": 0.001},
            locked_strategies={},
            tsm_configs={},
            user_silo=make_user_silo(),
            assets_detail={},
            session_id=1,
        )

        assert len(result["signals"]) == 0
        assert len(result["below_threshold"]) == 1
        assert result["below_threshold"][0]["asset"] == "NQ"


class TestConfidenceClassification:
    """Unit tests for confidence tier logic."""

    def test_high_confidence(self):
        assert _classify_confidence(0.015, 1.2, 0.010, 0.003) == "HIGH"

    def test_medium_confidence(self):
        assert _classify_confidence(0.005, 0.9, 0.010, 0.003) == "MEDIUM"

    def test_low_confidence(self):
        assert _classify_confidence(0.001, 0.8, 0.010, 0.003) == "LOW"


class TestTPSLComputation:
    """TP/SL helpers."""

    def test_tp_long(self):
        strategy = {"tp_multiple": 2.0}
        features = {"or_range": 5.0, "entry_price": 5000.0}
        tp = _compute_tp(strategy, features, 1)
        assert tp == 5010.0  # 5000 + 2*5

    def test_sl_long(self):
        strategy = {"sl_multiple": 1.0}
        features = {"or_range": 5.0, "entry_price": 5000.0}
        sl = _compute_sl(strategy, features, 1)
        assert sl == 4995.0  # 5000 - 1*5
