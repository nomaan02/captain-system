# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 15-17: Quality Gate (ON-B5B) regression tests."""

from unittest.mock import patch

import pytest

from captain_online.blocks.b5b_quality_gate import run_quality_gate
from tests.fixtures.user_fixtures import make_user_silo


def _mock_load_param(key, default):
    """Return known quality thresholds."""
    params = {"quality_hard_floor": 0.003, "quality_ceiling": 0.010}
    return params.get(key, default)


def _mock_trade_count(asset_id):
    """Return enough trades for full maturity."""
    return 100  # data_maturity = min(1.0, 100/50) = 1.0


class TestQualityAboveCeiling:
    """Scenario 15: quality_score > ceiling -> passes, multiplier=1.0."""

    @patch("captain_online.blocks.b5b_quality_gate._load_system_param", side_effect=_mock_load_param)
    @patch("captain_online.blocks.b5b_quality_gate._get_trade_count", side_effect=_mock_trade_count)
    @patch("captain_online.blocks.b5b_quality_gate._log_quality_results")
    def test_above_ceiling(self, mock_log, mock_tc, mock_param):
        result = run_quality_gate(
            selected_trades=["ES"],
            expected_edge={"ES": 0.020},  # edge=0.020 * mod=1.0 * maturity=1.0 = 0.020 > 0.010
            combined_modifier={"ES": 1.0},
            regime_probs={"ES": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4}},
            user_silo=make_user_silo(),
            session_id=1,
        )

        assert "ES" in result["recommended_trades"]
        assert len(result["available_not_recommended"]) == 0
        qr = result["quality_results"]["ES"]
        assert qr["passes_gate"] is True
        assert qr["quality_multiplier"] == 1.0


class TestQualityBetweenFloorAndCeiling:
    """Scenario 16: floor < quality_score < ceiling -> passes, graduated multiplier."""

    @patch("captain_online.blocks.b5b_quality_gate._load_system_param", side_effect=_mock_load_param)
    @patch("captain_online.blocks.b5b_quality_gate._get_trade_count", side_effect=_mock_trade_count)
    @patch("captain_online.blocks.b5b_quality_gate._log_quality_results")
    def test_between_floor_ceiling(self, mock_log, mock_tc, mock_param):
        result = run_quality_gate(
            selected_trades=["ES"],
            expected_edge={"ES": 0.006},  # 0.006 * 1.0 * 1.0 = 0.006, between 0.003 and 0.010
            combined_modifier={"ES": 1.0},
            regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
            user_silo=make_user_silo(),
            session_id=1,
        )

        assert "ES" in result["recommended_trades"]
        qr = result["quality_results"]["ES"]
        assert qr["passes_gate"] is True
        # quality_multiplier = 0.006 / 0.010 = 0.6
        assert abs(qr["quality_multiplier"] - 0.6) < 0.01


class TestQualityBelowFloor:
    """Scenario 17: quality_score < hard_floor -> filtered out."""

    @patch("captain_online.blocks.b5b_quality_gate._load_system_param", side_effect=_mock_load_param)
    @patch("captain_online.blocks.b5b_quality_gate._get_trade_count", side_effect=_mock_trade_count)
    @patch("captain_online.blocks.b5b_quality_gate._log_quality_results")
    def test_below_floor(self, mock_log, mock_tc, mock_param):
        result = run_quality_gate(
            selected_trades=["ES"],
            expected_edge={"ES": 0.001},  # 0.001 * 1.0 * 1.0 = 0.001 < 0.003
            combined_modifier={"ES": 1.0},
            regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
            user_silo=make_user_silo(),
            session_id=1,
        )

        assert len(result["recommended_trades"]) == 0
        assert "ES" in result["available_not_recommended"]
        qr = result["quality_results"]["ES"]
        assert qr["passes_gate"] is False
        assert qr["quality_multiplier"] == 0.0
