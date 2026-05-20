"""Q2-B-strict B5 trade selection NKD bypass tests.

NKD must always end up in ``selected_trades`` regardless of expected_edge,
correlation filter, or ``max_simultaneous_positions``.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from captain_online.blocks.b5_trade_selection import run_trade_selection


def _silo(max_pos=5, accounts=None):
    return {
        "user_id": "test_user",
        "accounts": json.dumps(accounts or ["acct_1"]),
        "max_simultaneous_positions": max_pos,
        "correlation_threshold": 0.7,
    }


def test_b5_nkd_always_selected_even_with_zero_edge():
    """NKD with zero EWMA edge still ends up in selected_trades."""
    result = run_trade_selection(
        active_assets=["NKD"],
        final_contracts={"NKD": {"acct_1": 1}},
        account_recommendation={"NKD": {"acct_1": "TRADE"}},
        account_skip_reason={"NKD": {"acct_1": None}},
        ewma_states={},  # no EWMA → expected_edge = 0
        regime_probs={"NKD": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
        user_silo=_silo(),
        session_id=3,
    )
    assert "NKD" in result["selected_trades"], (
        "Vanilla selection requires expected_edge > 0 — NKD with empty EWMA "
        "would fail that gate; the bypass must override it."
    )
    assert result["final_contracts"]["NKD"]["acct_1"] == 1
    assert result["account_recommendation"]["NKD"]["acct_1"] == "TRADE"


def test_b5_nkd_restored_when_max_pos_would_drop_it():
    """max_simultaneous_positions=1 + higher-scoring ES would normally drop NKD;
    bypass must restore NKD contracts AND add it back to selected_trades."""
    with patch(
        "captain_online.blocks.b5_trade_selection._load_correlation_matrix",
        return_value=None,
    ):
        result = run_trade_selection(
            active_assets=["ES", "NKD"],
            final_contracts={
                "ES": {"acct_1": 5},
                "NKD": {"acct_1": 1},
            },
            account_recommendation={
                "ES": {"acct_1": "TRADE"},
                "NKD": {"acct_1": "TRADE"},
            },
            account_skip_reason={
                "ES": {"acct_1": None},
                "NKD": {"acct_1": None},
            },
            ewma_states={
                "ES": {"LOW_VOL": {"win_rate": 0.6, "avg_win": 200.0,
                                   "avg_loss": 100.0}},
                # NKD has no EWMA on purpose — would score 0.
            },
            regime_probs={
                "ES": {"LOW_VOL": 0.7, "HIGH_VOL": 0.3},
                "NKD": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5},
            },
            user_silo=_silo(max_pos=1),  # only top-scored asset survives
            session_id=3,
        )

    # ES has positive edge, NKD has 0; without bypass NKD would be dropped.
    assert "NKD" in result["selected_trades"], "NKD bypass must add NKD back."
    assert result["final_contracts"]["NKD"]["acct_1"] >= 1, (
        "NKD bypass must restore contracts after max_pos zeroed them."
    )
    assert result["account_recommendation"]["NKD"]["acct_1"] == "TRADE"
