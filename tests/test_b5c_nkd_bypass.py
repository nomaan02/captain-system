"""Q2-B-strict B5C circuit breaker NKD bypass tests.

NKD bypasses all CB layers (VIX, Sharpe floor, cold-start, manual halt).
The recommendation/contract state from B4/B5/B5B flows through unchanged.
"""
from __future__ import annotations

from unittest.mock import patch

from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen


def _tsm_with_cb_tripped(account):
    """A TSM config that would normally block trades — topstep_optimisation
    on and parameters that would trip Layer 1/2/4."""
    return {
        account: {
            "topstep_optimisation": True,
            "topstep_params": {
                "vix_cb_threshold": 1.0,  # almost any VIX trips
                "lambda_floor": 999.0,
            },
            "classification": {"category": "EVAL"},
            "current_open_micros": 0,
            "starting_capital": 150000,
        }
    }


def test_b5c_nkd_bypasses_all_layers():
    """NKD must pass through with recommendation TRADE even when CB params
    would normally block it."""
    accounts = ["acct_1"]
    final_contracts = {"NKD": {"acct_1": 1}}
    rec_in = {"NKD": {"acct_1": "TRADE"}}
    reason_in = {"NKD": {"acct_1": None}}

    with patch(
        "captain_online.blocks.b5c_circuit_breaker._load_cb_params",
        return_value={ac: {"beta_b": 0.0, "L_star": 1000.0,
                            "rho_j_threshold": 0.5} for ac in accounts},
    ), patch(
        "captain_online.blocks.b5c_circuit_breaker._load_intraday_state",
        return_value={ac: {} for ac in accounts},
    ):
        result = run_circuit_breaker_screen(
            recommended_trades=["NKD"],
            final_contracts=final_contracts,
            account_recommendation=rec_in,
            account_skip_reason=reason_in,
            accounts=accounts,
            tsm_configs=_tsm_with_cb_tripped("acct_1"),
            session_id=3,
            sl_distance=125.0,
            point_value=5.0,
            fee_per_trade=4.0,
            locked_strategies={"NKD": {"is_nkd_trail": True,
                                       "sl_dollars_fixed": 1025}},
            assets_detail={"NKD": {"point_value": 5.0}},
            open_positions=[],
        )

    # The bypass uses `continue`, so the existing TRADE recommendation
    # passes through untouched.
    assert result["account_recommendation"]["NKD"]["acct_1"] == "TRADE", (
        "NKD bypass must leave account_recommendation as TRADE."
    )
    assert result["final_contracts"]["NKD"]["acct_1"] == 1
