# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 4-6: AIM Aggregation (ON-B3) regression tests."""

from unittest.mock import patch

import pytest

from captain_online.blocks.b3_aim_aggregation import (
    run_aim_aggregation, MODIFIER_FLOOR, MODIFIER_CEILING,
)
from tests.fixtures.synthetic_data import make_features
from tests.fixtures.aim_fixtures import (
    make_aim_states_all_active, make_aim_states_all_suppressed,
    make_aim_states_mixed, make_aim_weights, make_aim_weights_none_included,
)

# Known modifier values to return from compute_aim_modifier mock
KNOWN_MODIFIERS = {
    1: 1.10,   # VRP
    2: 0.90,   # Skew
    3: 1.20,   # GEX
    6: 1.00,   # Econ calendar
    7: 0.95,   # COT
    8: 1.05,   # Cross-asset corr
    9: 1.00,   # Cross-asset momentum
    10: 1.00,  # Calendar effects
    11: 0.90,  # Regime warning
    12: 1.00,  # Dynamic costs
    13: 0.85,  # Sensitivity
    15: 1.15,  # Opening volume
    16: 1.05,  # HMM opportunity
}


def _mock_compute_aim_modifier(aim_id, features, asset_id, state):
    """Return known modifier values for testing."""
    return {
        "modifier": KNOWN_MODIFIERS.get(aim_id, 1.0),
        "confidence": 0.8,
        "reason_tag": f"TEST_AIM_{aim_id}",
    }


class TestAllAimsActive:
    """Scenario 4: All Tier-1 AIMs active with known modifiers."""

    @patch(
        "captain_online.blocks.b3_aim_aggregation.compute_aim_modifier",
        side_effect=_mock_compute_aim_modifier,
    )
    def test_combined_modifier_in_bounds(self, mock_cam):
        aim_ids = list(KNOWN_MODIFIERS.keys())
        aim_states = make_aim_states_all_active("ES", aim_ids)
        aim_weights = make_aim_weights("ES", aim_ids, uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert MODIFIER_FLOOR <= cm <= MODIFIER_CEILING
        assert "aim_breakdown" in result
        assert "ES" in result["aim_breakdown"]

    @patch(
        "captain_online.blocks.b3_aim_aggregation.compute_aim_modifier",
        side_effect=_mock_compute_aim_modifier,
    )
    def test_weighted_average_correctness(self, mock_cam):
        """Verify combined modifier is weighted average of individual modifiers."""
        aim_ids = list(KNOWN_MODIFIERS.keys())
        aim_states = make_aim_states_all_active("ES", aim_ids)
        aim_weights = make_aim_weights("ES", aim_ids, uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        # With uniform weights, combined should be close to simple average
        expected_avg = sum(KNOWN_MODIFIERS.values()) / len(KNOWN_MODIFIERS)
        cm = result["combined_modifier"]["ES"]
        # Clamped to [0.5, 1.5], so check within tolerance after clamping
        clamped = max(MODIFIER_FLOOR, min(MODIFIER_CEILING, expected_avg))
        assert abs(cm - clamped) < 0.01


class TestAllAimsSuppressed:
    """Scenario 5: All AIMs suppressed -> combined_modifier = 1.0 (neutral)."""

    def test_no_active_aims(self):
        aim_states = make_aim_states_all_suppressed("ES")
        aim_weights = make_aim_weights("ES")
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        # No active AIMs means no modifiers applied -> 1.0 default
        cm = result["combined_modifier"]["ES"]
        assert cm == 1.0

    def test_none_included(self):
        """All inclusion_flag=False -> 1.0 neutral."""
        aim_states = make_aim_states_all_active("ES")
        aim_weights = make_aim_weights_none_included("ES")
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)
        cm = result["combined_modifier"]["ES"]
        assert cm == 1.0


class TestMixedActiveAims:
    """Scenario 6: Mix of ACTIVE and SUPPRESSED AIMs."""

    @patch(
        "captain_online.blocks.b3_aim_aggregation.compute_aim_modifier",
        side_effect=_mock_compute_aim_modifier,
    )
    def test_only_active_contribute(self, mock_cam):
        aim_states = make_aim_states_mixed("ES")  # 1,2,3 active; rest suppressed
        # Give active AIMs weights that sum to 1
        aim_weights = make_aim_weights(
            "ES",
            aim_ids=[1, 2, 3],
            custom_weights={1: 0.33, 2: 0.33, 3: 0.34},
        )
        # Add suppressed AIMs to weights too (they should be ignored)
        for aid in [6, 7, 8, 9, 10, 11, 12, 13, 15, 16]:
            aim_weights[("ES", aid)] = {
                "inclusion_probability": 0.05,
                "inclusion_flag": True,
                "recent_effectiveness": 0.0,
                "days_below_threshold": 0,
            }

        features = make_features("ES")
        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert MODIFIER_FLOOR <= cm <= MODIFIER_CEILING

        # Only AIMs 1,2,3 should appear in breakdown
        breakdown = result["aim_breakdown"]["ES"]
        active_aim_ids = {k for k in breakdown.keys() if isinstance(k, int)}
        # The suppressed AIMs should not be in breakdown
        for aid in [6, 7, 8, 9, 10, 11, 12, 13, 15, 16]:
            assert aid not in active_aim_ids or breakdown.get(aid, {}).get("modifier") is None
