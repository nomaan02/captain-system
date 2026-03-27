# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 13-14: Trade Selection (ON-B5) regression tests."""

from unittest.mock import patch, MagicMock

import pytest

from captain_online.blocks.b5_trade_selection import run_trade_selection
from tests.fixtures.synthetic_data import make_ewma_states
from tests.fixtures.user_fixtures import make_user_silo


def _make_two_asset_ewma(correlated=False):
    """EWMA states for ES and NQ."""
    es_ewma = {
        ("ES", "LOW_VOL", 1): {"win_rate": 0.55, "avg_win": 200.0, "avg_loss": 100.0, "n_trades": 50},
    }
    nq_ewma = {
        ("NQ", "LOW_VOL", 1): {"win_rate": 0.50, "avg_win": 150.0, "avg_loss": 120.0, "n_trades": 30},
    }
    return {**es_ewma, **nq_ewma}


def _make_two_asset_contracts():
    return {
        "ES": {"acc_eval_1": 3},
        "NQ": {"acc_eval_1": 2},
    }


def _make_two_asset_recs():
    return {
        "ES": {"acc_eval_1": "TRADE"},
        "NQ": {"acc_eval_1": "TRADE"},
    }


def _make_two_asset_reasons():
    return {
        "ES": {"acc_eval_1": None},
        "NQ": {"acc_eval_1": None},
    }


class TestUncorrelatedAssets:
    """Scenario 13: Two uncorrelated assets -> both selected."""

    @patch("captain_online.blocks.b5_trade_selection._load_correlation_matrix")
    @patch("captain_online.blocks.b5_trade_selection._get_correlation", return_value=0.3)
    def test_both_selected(self, mock_corr, mock_matrix):
        mock_matrix.return_value = {}

        result = run_trade_selection(
            active_assets=["ES", "NQ"],
            final_contracts=_make_two_asset_contracts(),
            account_recommendation=_make_two_asset_recs(),
            account_skip_reason=_make_two_asset_reasons(),
            ewma_states=_make_two_asset_ewma(),
            regime_probs={"ES": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4}, "NQ": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
            user_silo=make_user_silo(accounts=["acc_eval_1"]),
            session_id=1,
        )

        # Both assets should remain in selected_trades
        selected = result["selected_trades"]
        assert "ES" in selected
        assert "NQ" in selected
        # Contracts unchanged
        assert result["final_contracts"]["ES"]["acc_eval_1"] == 3
        assert result["final_contracts"]["NQ"]["acc_eval_1"] == 2


class TestCorrelatedAssets:
    """Scenario 14: Two correlated assets (>0.7) -> lower-scoring reduced."""

    @patch("captain_online.blocks.b5_trade_selection._load_correlation_matrix")
    @patch("captain_online.blocks.b5_trade_selection._get_correlation", return_value=0.85)
    def test_lower_scoring_reduced(self, mock_corr, mock_matrix):
        mock_matrix.return_value = {}

        result = run_trade_selection(
            active_assets=["ES", "NQ"],
            final_contracts=_make_two_asset_contracts(),
            account_recommendation=_make_two_asset_recs(),
            account_skip_reason=_make_two_asset_reasons(),
            ewma_states=_make_two_asset_ewma(),
            regime_probs={"ES": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4}, "NQ": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
            user_silo=make_user_silo(accounts=["acc_eval_1"]),
            session_id=1,
        )

        # ES has higher edge (0.55*200 - 0.45*100 = 65) vs NQ (0.50*150 - 0.50*120 = 15)
        # NQ (lower score) should have contracts reduced (halved)
        nq_contracts = result["final_contracts"]["NQ"]["acc_eval_1"]
        assert nq_contracts <= 1  # Was 2, halved to 1
