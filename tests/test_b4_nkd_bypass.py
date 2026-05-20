"""Q2-B-strict B4 Kelly sizing NKD bypass tests.

Audit: docs2/quick-fixes/NKD_Pivot/day_3/PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md §2 Q2

NKD signals must bypass Kelly math entirely — force 1 contract per active
account regardless of EWMA / regime probs / Kelly params / AIM modifier.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing


def _minimal_user_silo(accounts=None):
    return {
        "user_id": "test_user",
        "accounts": json.dumps(accounts or ["acct_1", "acct_2"]),
        "starting_capital": 150000,
        "total_capital": 150000,
        "user_kelly_ceiling": 1.0,
        "max_simultaneous_positions": 5,
    }


def _minimal_kelly_params(asset):
    return {
        asset: {
            "LOW_VOL": {"kelly_full": 0.10, "shrinkage": 1.0},
            "HIGH_VOL": {"kelly_full": 0.05, "shrinkage": 1.0},
        }
    }


def _minimal_tsm_configs(accounts):
    """Minimal TSM that would normally let trades through; bypass should
    not consult it for NKD."""
    return {
        ac: {
            "classification": {"category": "BROKER_RETAIL"},
            "risk_goal": "GROW_CAPITAL",
            "instrument_permissions": [],  # empty = all instruments allowed
            "topstep_optimisation": False,
            "current_open_micros": 0,
        }
        for ac in accounts
    }


# Patch _load_system_param so the silo-drawdown check returns its default
# without touching QuestDB.
@pytest.fixture
def _patch_system_param():
    with patch(
        "captain_online.blocks.b4_kelly_sizing._load_system_param",
        side_effect=lambda key, default: default,
    ):
        yield


def test_kelly_nkd_forces_one_contract_regardless_of_params(_patch_system_param):
    """NKD with terrible Kelly params still gets contracts=1 per account."""
    accounts = ["acct_1", "acct_2", "acct_3"]
    result = run_kelly_sizing(
        active_assets=["NKD"],
        regime_probs={"NKD": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
        regime_uncertain={"NKD": True},  # would normally invoke robust fallback
        combined_modifier={"NKD": 0.01},  # very low modifier — would size to 0
        kelly_params=_minimal_kelly_params("NKD"),
        ewma_states={"NKD": {"LOW_VOL": {"win_rate": 0.1, "avg_win": 1.0,
                                          "avg_loss": 100.0}}},
        tsm_configs=_minimal_tsm_configs(accounts),
        sizing_overrides={},
        user_silo=_minimal_user_silo(accounts),
        locked_strategies={"NKD": {"is_nkd_trail": True, "sl_dollars_fixed": 1025}},
        assets_detail={"NKD": {"point_value": 5.0}},
        session_id=3,
    )

    assert result is not None
    assert result["silo_blocked"] is False
    for ac in accounts:
        assert result["final_contracts"]["NKD"][ac] == 1, (
            f"NKD bypass should force contracts=1 on {ac}, "
            f"got {result['final_contracts']['NKD'][ac]}"
        )
        assert result["account_recommendation"]["NKD"][ac] == "TRADE"
        assert result["account_skip_reason"]["NKD"][ac] is None


def test_kelly_nkd_bypass_does_not_consult_tsm(_patch_system_param):
    """Bypass should fire even if NKD is NOT in instrument_permissions —
    proves Kelly never reads TSM for NKD."""
    accounts = ["acct_1"]
    tsm_no_nkd = _minimal_tsm_configs(accounts)
    # Restrict permissions to ES only — would normally skip NKD.
    tsm_no_nkd["acct_1"]["instrument_permissions"] = ["ES"]

    result = run_kelly_sizing(
        active_assets=["NKD"],
        regime_probs={"NKD": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
        regime_uncertain={"NKD": False},
        combined_modifier={"NKD": 1.0},
        kelly_params=_minimal_kelly_params("NKD"),
        ewma_states={},
        tsm_configs=tsm_no_nkd,
        sizing_overrides={},
        user_silo=_minimal_user_silo(accounts),
        locked_strategies={"NKD": {"is_nkd_trail": True}},
        assets_detail={"NKD": {"point_value": 5.0}},
        session_id=3,
    )

    assert result["final_contracts"]["NKD"]["acct_1"] == 1, (
        "NKD bypass must short-circuit before the TSM permissions check."
    )


def test_kelly_silo_drawdown_still_blocks_nkd(_patch_system_param):
    """Silo drawdown is at the silo level (outside the per-asset loop) — it
    MUST still block NKD as a hard safety stop. NKD bypass only skips Kelly
    math; it does not override silo-level safety rails."""
    user_silo = _minimal_user_silo(["acct_1"])
    user_silo["total_capital"] = 50000  # 66% drawdown → silo blocked

    with patch(
        "captain_online.blocks.b4_kelly_sizing._load_system_param",
        side_effect=lambda key, default: 0.30 if "drawdown" in key else default,
    ):
        result = run_kelly_sizing(
            active_assets=["NKD"],
            regime_probs={"NKD": {"LOW_VOL": 0.5}},
            regime_uncertain={"NKD": False},
            combined_modifier={"NKD": 1.0},
            kelly_params=_minimal_kelly_params("NKD"),
            ewma_states={},
            tsm_configs=_minimal_tsm_configs(["acct_1"]),
            sizing_overrides={},
            user_silo=user_silo,
            locked_strategies={"NKD": {"is_nkd_trail": True}},
            assets_detail={"NKD": {"point_value": 5.0}},
            session_id=3,
        )

    assert result["silo_blocked"] is True
    assert result["final_contracts"]["NKD"]["acct_1"] == 0, (
        "Silo-drawdown safety rail must still flatten NKD even though "
        "the Q2-B-strict bypass exempts it from Kelly math."
    )
