# region imports
from AlgorithmImports import *
# endregion
"""PRE-FIX / POST-FIX tests for B4 warm-up floor (W-C policy, Bug-A fix).

PRE-FIX test documents that with kelly=0 but otherwise-eligible caps an asset
gets 0 contracts today.  After Step 4 (W-C warm-up floor) this becomes 1
contract with recommendation TRADE_WARMUP.

All POST-FIX tests live in the same file; the PRE-FIX test is transitioned in
Step 4.4 by flipping the assertion from == 0 to == 1 and renaming.
"""

import pytest
from unittest.mock import patch

from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
from tests.fixtures.synthetic_data import (
    make_assets_detail,
    make_locked_strategy,
)
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_config


# ---------------------------------------------------------------------------
# Helpers: warm-up scenario fixtures
# ---------------------------------------------------------------------------

def _make_warmup_ewma(asset_id: str, n_trades: int = 5, session: int = 1):
    """EWMA state where n_trades is set but kelly would be zero (collapsed)."""
    states = {}
    for regime in ("LOW_VOL", "HIGH_VOL"):
        states[(asset_id, regime, session)] = {
            "win_rate": 0.5,
            "avg_win": 0.01,
            "avg_loss": 0.01,
            "n_trades": n_trades,
        }
    return states


def _make_zero_kelly_params(asset_id: str):
    """Kelly params where all cells have kelly_full=0 (collapsed EWMA)."""
    params = {}
    for regime in ("LOW_VOL", "HIGH_VOL"):
        for session in (1, 2, 3):
            params[(asset_id, regime, session)] = {
                "kelly_full": 0.0,
                "shrinkage_factor": 0.3,  # floor shrinkage — still results in 0*0.3=0
            }
    return params


def _make_large_cap_tsm(account_id: str = "acc_1"):
    """TSM with generous caps — tsm_cap ≥ 1, topstep_cap ≥ 1."""
    return make_tsm_config(
        account_id=account_id,
        category="PROP_EVAL",
        balance=150_000.0,
        max_drawdown_limit=5_000.0,
        current_drawdown=0.0,
        max_daily_loss=1_000.0,
        daily_loss_used=0.0,
        max_contracts=15,
        risk_goal="GROW_CAPITAL",
        topstep_optimisation=False,  # disable topstep cap so only tsm_cap applies
    )


# ---------------------------------------------------------------------------
# PRE-FIX test — documents the bug
# ---------------------------------------------------------------------------

class TestWarmupFloorPostFix:
    """After W-C warm-up floor: eligible asset with kelly=0 → 1 contract (TRADE_WARMUP)."""

    def test_eligible_asset_with_kelly_zero_returns_one_contract_post_fix(self):
        """POST-FIX (W-C): kelly=0 but eligible EWMA → 1 contract, TRADE_WARMUP.

        The asset has n_trades >= WARMUP_MIN_CELL_N and caps allow ≥1 contract,
        so the warm-up floor promotes it from 0 to 1.
        """
        with patch(
            "captain_online.blocks.b4_kelly_sizing._load_system_param",
            side_effect=lambda key, default: default,
        ):
            result = run_kelly_sizing(
                active_assets=["ES"],
                regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"ES": False},
                combined_modifier={"ES": 1.0},
                kelly_params=_make_zero_kelly_params("ES"),
                ewma_states=_make_warmup_ewma("ES", n_trades=5),
                tsm_configs={"acc_1": _make_large_cap_tsm()},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=make_locked_strategy("ES"),
                assets_detail=make_assets_detail("ES"),
                session_id=1,
            )

        contracts = result["final_contracts"]["ES"]["acc_1"]
        rec = result["account_recommendation"]["ES"]["acc_1"]
        # POST-FIX: warm-up floor promotes to 1 contract
        assert contracts == 1, f"Expected 1 contract (warmup floor), got {contracts}"
        assert rec == "TRADE_WARMUP", f"Expected TRADE_WARMUP recommendation, got {rec}"

    def test_warmup_floor_not_applied_when_n_below_min(self):
        """n_trades=2 < WARMUP_MIN_CELL_N=3 → ineligible → 0 contracts."""
        with patch(
            "captain_online.blocks.b4_kelly_sizing._load_system_param",
            side_effect=lambda key, default: default,
        ):
            result = run_kelly_sizing(
                active_assets=["ES"],
                regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"ES": False},
                combined_modifier={"ES": 1.0},
                kelly_params=_make_zero_kelly_params("ES"),
                ewma_states=_make_warmup_ewma("ES", n_trades=2),
                tsm_configs={"acc_1": _make_large_cap_tsm()},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=make_locked_strategy("ES"),
                assets_detail=make_assets_detail("ES"),
                session_id=1,
            )

        contracts = result["final_contracts"]["ES"]["acc_1"]
        assert contracts == 0, f"n_trades<3 should not get warmup floor, got {contracts}"

    def test_warmup_floor_not_applied_when_tsm_cap_zero(self):
        """tsm_cap=0 → floor does not apply even if eligible."""
        tsm_tight = make_tsm_config(
            account_id="acc_1",
            balance=150_000.0,
            max_drawdown_limit=100.0,  # remaining_mdd → very small daily budget
            current_drawdown=99.0,     # remaining = $1 → tsm_cap=0
            topstep_optimisation=False,
        )

        with patch(
            "captain_online.blocks.b4_kelly_sizing._load_system_param",
            side_effect=lambda key, default: 20 if key == "tsm_budget_divisor_default" else default,
        ):
            result = run_kelly_sizing(
                active_assets=["ES"],
                regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"ES": False},
                combined_modifier={"ES": 1.0},
                kelly_params=_make_zero_kelly_params("ES"),
                ewma_states=_make_warmup_ewma("ES", n_trades=10),
                tsm_configs={"acc_1": tsm_tight},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=make_locked_strategy("ES"),
                assets_detail=make_assets_detail("ES"),
                session_id=1,
            )

        contracts = result["final_contracts"]["ES"]["acc_1"]
        # tsm_cap=0 → floor does not promote; caps take priority
        assert contracts == 0, f"tsm_cap=0 should prevent warmup floor, got {contracts}"

    def test_warmup_floor_caps_at_one(self):
        """Sanity: floor is exactly 1 (not 2, 3, etc.), within the eligibility window."""
        with patch(
            "captain_online.blocks.b4_kelly_sizing._load_system_param",
            side_effect=lambda key, default: default,
        ):
            result = run_kelly_sizing(
                active_assets=["ES"],
                regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"ES": False},
                combined_modifier={"ES": 1.0},
                kelly_params=_make_zero_kelly_params("ES"),
                ewma_states=_make_warmup_ewma("ES", n_trades=20),  # within window (3-30)
                tsm_configs={"acc_1": _make_large_cap_tsm()},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=make_locked_strategy("ES"),
                assets_detail=make_assets_detail("ES"),
                session_id=1,
            )

        contracts = result["final_contracts"]["ES"]["acc_1"]
        assert contracts == 1, f"Warm-up floor must be exactly 1 contract, got {contracts}"

    def test_no_warmup_floor_when_kelly_already_positive(self):
        """When Kelly produces ≥1 contract, floor is a no-op."""
        from decimal import Decimal
        high_kelly_params = {
            ("ES", regime, session): {"kelly_full": 0.50, "shrinkage_factor": 0.85}
            for regime in ("LOW_VOL", "HIGH_VOL")
            for session in (1, 2, 3)
        }
        large_ewma = _make_warmup_ewma("ES", n_trades=5)
        for k in large_ewma:
            large_ewma[k].update({"win_rate": 0.60, "avg_win": 500.0, "avg_loss": 200.0})

        with patch(
            "captain_online.blocks.b4_kelly_sizing._load_system_param",
            side_effect=lambda key, default: default,
        ):
            result = run_kelly_sizing(
                active_assets=["ES"],
                regime_probs={"ES": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"ES": False},
                combined_modifier={"ES": 1.0},
                kelly_params=high_kelly_params,
                ewma_states=large_ewma,
                tsm_configs={"acc_1": _make_large_cap_tsm()},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=make_locked_strategy("ES"),
                assets_detail=make_assets_detail("ES"),
                session_id=1,
            )

        contracts = result["final_contracts"]["ES"]["acc_1"]
        rec = result["account_recommendation"]["ES"]["acc_1"]
        assert contracts >= 1
        assert rec == "TRADE", f"High-Kelly asset should get TRADE not {rec}"
