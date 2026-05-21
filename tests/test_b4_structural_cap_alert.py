# region imports
from AlgorithmImports import *
# endregion
"""Tests for STRUCTURAL_CAP_BLOCK alert (Bug-B, invariant I-5).

Marked xfail until Step 5 implements the CH_ALERTS publish in run_kelly_sizing.
After Step 5, remove the xfail mark and the tests should pass.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call

from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
from tests.fixtures.synthetic_data import (
    make_assets_detail,
    make_locked_strategy,
)
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_config


# ---------------------------------------------------------------------------
# NQ-shaped fixture: positive Kelly, tsm_cap=0 (Bug-B scenario)
# ---------------------------------------------------------------------------

def _make_nq_kelly_params():
    """NQ: kelly=0.0724 across all cells (positive edge)."""
    params = {}
    for regime in ("LOW_VOL", "HIGH_VOL"):
        for session in (1, 2, 3):
            params[("NQ", regime, session)] = {
                "kelly_full": 0.0724,
                "shrinkage_factor": 0.85,
            }
    return params


def _make_nq_ewma():
    """NQ EWMA states reflecting the 2026-05-21 log."""
    states = {}
    for regime in ("LOW_VOL", "HIGH_VOL"):
        for session in (1, 2, 3):
            states[("NQ", regime, session)] = {
                "win_rate": 0.55,
                "avg_win": 200.0,
                "avg_loss": 100.0,
                "n_trades": 20,
            }
    return states


def _make_nq_tsm_cap_zero(account_id: str = "acc_1"):
    """TSM where max_by_mdd=0 (NQ risk/contract $400 > daily budget $250).

    remaining_mdd=5000, budget_divisor=20 → daily_budget=250
    NQ: sl=20pts * point_value=$20 = $400/contract → floor(250/400)=0
    """
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
        topstep_optimisation=False,
        # No evaluation_end_date → budget_divisor=20 (default)
    )


def _make_nq_assets_detail():
    """NQ asset detail: point_value=20, sl implicit from strategy."""
    from decimal import Decimal
    return {
        "NQ": {
            "point_value": Decimal("20"),
            "tick_size": Decimal("0.25"),
            "margin_per_contract": Decimal("17600"),
        }
    }


def _make_nq_locked_strategy():
    """NQ locked strategy with sl_distance=20 (sl*pv = $400/contract)."""
    return {
        "NQ": {
            "threshold": 20.0,
            "sl_multiple": 1.0,
            "tp_multiple": 2.0,
            "default_direction": 1,
            "sl_method": "OR_RANGE",
            "entry_conditions": {"breakout": True},
        }
    }


# ---------------------------------------------------------------------------
# Tests (xfail until Step 5 implements the alert)
# ---------------------------------------------------------------------------

class TestStructuralCapBlockAlert:
    """NQ scenario: blended_kelly > 0 AND tsm_cap = 0 should fire CRITICAL alert."""

    def test_structural_cap_block_alert_fires_when_kelly_positive_tsm_zero(self):
        """blended_kelly > 0 AND tsm_cap = 0 → CH_ALERTS publish with type=STRUCTURAL_CAP_BLOCK."""
        mock_redis = MagicMock()

        with (
            patch(
                "captain_online.blocks.b4_kelly_sizing._load_system_param",
                side_effect=lambda key, default: 20 if key == "tsm_budget_divisor_default" else default,
            ),
            patch(
                "captain_online.blocks.b4_kelly_sizing.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            result = run_kelly_sizing(
                active_assets=["NQ"],
                regime_probs={"NQ": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"NQ": False},
                combined_modifier={"NQ": 1.0},
                kelly_params=_make_nq_kelly_params(),
                ewma_states=_make_nq_ewma(),
                tsm_configs={"acc_1": _make_nq_tsm_cap_zero()},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=_make_nq_locked_strategy(),
                assets_detail=_make_nq_assets_detail(),
                session_id=1,
            )

        # NQ should still be 0 contracts (Bug-B; caps remain unchanged)
        assert result["final_contracts"]["NQ"]["acc_1"] == 0

        # Alert should have fired once for NQ
        assert mock_redis.publish.called, "Expected CH_ALERTS publish but none fired"
        published_calls = [
            json.loads(c.args[1]) for c in mock_redis.publish.call_args_list
        ]
        cap_blocks = [p for p in published_calls if p.get("type") == "STRUCTURAL_CAP_BLOCK"]
        assert len(cap_blocks) == 1, f"Expected 1 STRUCTURAL_CAP_BLOCK alert, got {len(cap_blocks)}"
        alert = cap_blocks[0]
        assert alert["asset"] == "NQ"
        assert alert["priority"] == "HIGH"
        assert alert["blended_kelly"] > 0

    def test_no_alert_when_kelly_zero(self):
        """blended_kelly == 0 → no STRUCTURAL_CAP_BLOCK alert."""
        mock_redis = MagicMock()
        zero_kelly = {
            ("NQ", regime, session): {"kelly_full": 0.0, "shrinkage_factor": 0.3}
            for regime in ("LOW_VOL", "HIGH_VOL")
            for session in (1, 2, 3)
        }

        with (
            patch(
                "captain_online.blocks.b4_kelly_sizing._load_system_param",
                side_effect=lambda key, default: 20 if key == "tsm_budget_divisor_default" else default,
            ),
            patch(
                "captain_online.blocks.b4_kelly_sizing.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            run_kelly_sizing(
                active_assets=["NQ"],
                regime_probs={"NQ": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
                regime_uncertain={"NQ": False},
                combined_modifier={"NQ": 1.0},
                kelly_params=zero_kelly,
                ewma_states=_make_nq_ewma(),
                tsm_configs={"acc_1": _make_nq_tsm_cap_zero()},
                sizing_overrides={},
                user_silo=make_user_silo(accounts=["acc_1"]),
                locked_strategies=_make_nq_locked_strategy(),
                assets_detail=_make_nq_assets_detail(),
                session_id=1,
            )

        published_calls = [
            json.loads(c.args[1]) for c in mock_redis.publish.call_args_list
            if len(c.args) >= 2
        ]
        cap_blocks = [p for p in published_calls if p.get("type") == "STRUCTURAL_CAP_BLOCK"]
        assert len(cap_blocks) == 0, "No STRUCTURAL_CAP_BLOCK expected when kelly=0"
