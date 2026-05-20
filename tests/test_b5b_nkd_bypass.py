"""Q2-B-strict B5B quality gate NKD bypass tests."""
from __future__ import annotations

from unittest.mock import patch

from captain_online.blocks.b5b_quality_gate import run_quality_gate


def test_b5b_nkd_always_recommended_with_zero_edge():
    """NKD with zero edge / low modifier still passes the quality gate."""
    with patch(
        "captain_online.blocks.b5b_quality_gate._load_system_param",
        side_effect=lambda key, default: default,
    ), patch(
        "captain_online.blocks.b5b_quality_gate._log_quality_results",
        return_value=None,
    ), patch(
        "captain_online.blocks.b5b_quality_gate._get_trade_count",
        return_value=0,
    ):
        result = run_quality_gate(
            selected_trades=["NKD"],
            expected_edge={"NKD": 0.0},  # would fail vanilla quality gate
            combined_modifier={"NKD": 0.01},  # also would fail
            regime_probs={"NKD": {}},
            user_silo={"user_id": "test_user"},
            session_id=3,
            final_contracts={"NKD": {"acct_1": 1}},
        )

    assert "NKD" in result["recommended_trades"], (
        "NKD bypass must add NKD to recommended_trades regardless of "
        "edge or modifier."
    )
    assert "NKD" not in result["available_not_recommended"]
    assert result["quality_results"]["NKD"]["passes_gate"] is True
    assert result["quality_results"]["NKD"]["reason"] == "NKD_BYPASS"
