# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 4-6: AIM Aggregation (ON-B3) regression tests."""

from unittest.mock import patch

import pytest

from shared.aim_compute import (
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
        "shared.aim_compute.compute_aim_modifier",
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
        "shared.aim_compute.compute_aim_modifier",
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
        "shared.aim_compute.compute_aim_modifier",
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


# =========================================================================
# F5.10 — Cold-start edge case tests (Phase 4 verification)
# =========================================================================


class TestColdStartFewActiveAims:
    """F5.10-A: Only 2-3 AIMs active (e.g., AIM-04 + AIM-15), rest neutral.

    Verifies combined modifier is reasonable and bounded when most AIMs
    are suppressed/warm-up, as happens during initial deployment.
    """

    @patch(
        "shared.aim_compute.compute_aim_modifier",
        side_effect=_mock_compute_aim_modifier,
    )
    def test_two_aims_active_combined_reasonable(self, mock_cam):
        """AIM-1 (1.10) + AIM-15 (1.15) only → weighted avg ≈ 1.125."""
        aim_states = make_aim_states_all_active("ES", aim_ids=[1, 15])
        aim_weights = make_aim_weights("ES", aim_ids=[1, 15], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert MODIFIER_FLOOR <= cm <= MODIFIER_CEILING
        # With uniform weights: (1.10 + 1.15) / 2 = 1.125
        expected = (KNOWN_MODIFIERS[1] + KNOWN_MODIFIERS[15]) / 2
        assert abs(cm - expected) < 0.01

    @patch(
        "shared.aim_compute.compute_aim_modifier",
        side_effect=_mock_compute_aim_modifier,
    )
    def test_three_aims_active_combined_in_bounds(self, mock_cam):
        """AIM-1 + AIM-11 + AIM-15 → weighted avg of 1.10, 0.90, 1.15."""
        aim_states = make_aim_states_all_active("ES", aim_ids=[1, 11, 15])
        aim_weights = make_aim_weights("ES", aim_ids=[1, 11, 15], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert MODIFIER_FLOOR <= cm <= MODIFIER_CEILING
        expected = (1.10 + 0.90 + 1.15) / 3  # ≈ 1.05
        assert abs(cm - expected) < 0.01

    @patch(
        "shared.aim_compute.compute_aim_modifier",
        side_effect=_mock_compute_aim_modifier,
    )
    def test_few_aims_breakdown_only_contains_active(self, mock_cam):
        """Only active AIMs appear in breakdown, rest absent."""
        aim_states = make_aim_states_all_active("ES", aim_ids=[1, 15])
        aim_weights = make_aim_weights("ES", aim_ids=[1, 15], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        breakdown = result["aim_breakdown"]["ES"]
        assert set(breakdown.keys()) == {1, 15}


class TestColdStartAllWarmUp:
    """F5.10-B: All AIMs in WARM_UP (no active AIMs).

    During initial cold-start, all AIMs may be warming up.
    Combined modifier MUST be 1.0 (neutral) — no AIM influence.
    """

    def test_all_warmup_returns_neutral(self):
        """Every AIM in WARM_UP → combined_modifier = 1.0."""
        all_aim_ids = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 15]
        by_asset_aim = {}
        for aid in all_aim_ids:
            by_asset_aim[("ES", aid)] = {
                "status": "WARM_UP",
                "warmup_progress": 0.3,
                "zero_weight_trades": 0,
            }
        aim_states = {"by_asset_aim": by_asset_aim, "global": {}}
        aim_weights = make_aim_weights("ES", aim_ids=all_aim_ids, uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        assert result["combined_modifier"]["ES"] == 1.0
        assert result["aim_breakdown"]["ES"] == {}

    def test_all_eligible_not_active_returns_neutral(self):
        """Every AIM in ELIGIBLE (passed feature gate, not yet user-activated) → 1.0."""
        all_aim_ids = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 15]
        by_asset_aim = {}
        for aid in all_aim_ids:
            by_asset_aim[("ES", aid)] = {
                "status": "ELIGIBLE",
                "warmup_progress": 1.0,
                "zero_weight_trades": 0,
            }
        aim_states = {"by_asset_aim": by_asset_aim, "global": {}}
        aim_weights = make_aim_weights("ES", aim_ids=all_aim_ids, uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        assert result["combined_modifier"]["ES"] == 1.0
        assert result["aim_breakdown"]["ES"] == {}


class TestColdStartSingleExtremeAim:
    """F5.10-C: Single AIM active with extreme modifier.

    When only one AIM is active, it dominates the combined modifier.
    Verify it's correctly propagated (not diluted) and still clamped.
    """

    @patch(
        "shared.aim_compute.compute_aim_modifier",
    )
    def test_single_aim_extreme_low(self, mock_cam):
        """One AIM returns 0.65 (IVTS severe backwardation) → dominates at 0.65."""
        mock_cam.return_value = {"modifier": 0.65, "confidence": 0.9, "reason_tag": "IVTS_SEVERE"}
        aim_states = make_aim_states_all_active("ES", aim_ids=[4])
        aim_weights = make_aim_weights("ES", aim_ids=[4], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert cm == 0.65  # Single AIM, 100% weight → its modifier is the combined

    @patch(
        "shared.aim_compute.compute_aim_modifier",
    )
    def test_single_aim_extreme_high(self, mock_cam):
        """One AIM returns 1.45 → dominates at 1.45 (within ceiling 1.5)."""
        mock_cam.return_value = {"modifier": 1.45, "confidence": 0.9, "reason_tag": "TEST_HIGH"}
        aim_states = make_aim_states_all_active("ES", aim_ids=[15])
        aim_weights = make_aim_weights("ES", aim_ids=[15], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert cm == 1.45

    @patch(
        "shared.aim_compute.compute_aim_modifier",
    )
    def test_single_aim_beyond_ceiling_clamped(self, mock_cam):
        """One AIM returns 1.80 → clamped to ceiling 1.5."""
        mock_cam.return_value = {"modifier": 1.80, "confidence": 0.9, "reason_tag": "TEST_EXTREME"}
        aim_states = make_aim_states_all_active("ES", aim_ids=[4])
        aim_weights = make_aim_weights("ES", aim_ids=[4], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert cm == MODIFIER_CEILING  # 1.5

    @patch(
        "shared.aim_compute.compute_aim_modifier",
    )
    def test_single_aim_below_floor_clamped(self, mock_cam):
        """One AIM returns 0.30 → clamped to floor 0.5."""
        mock_cam.return_value = {"modifier": 0.30, "confidence": 0.9, "reason_tag": "TEST_EXTREME_LOW"}
        aim_states = make_aim_states_all_active("ES", aim_ids=[4])
        aim_weights = make_aim_weights("ES", aim_ids=[4], uniform=True)
        features = make_features("ES")

        result = run_aim_aggregation(["ES"], features, aim_states, aim_weights)

        cm = result["combined_modifier"]["ES"]
        assert cm == MODIFIER_FLOOR  # 0.5
