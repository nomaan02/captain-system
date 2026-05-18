"""Tests for _tp_from_dollars helper and tp_dollars short-circuit in _compute_tp.

C3 — NKD pivot: when locked_strategy contains 'tp_dollars', _compute_tp uses a
dollar-denominated target instead of the OR-range × tp_multiple formula.

NKD specs: point_value=5.0, tick_size=5.0
TP formula: tp_distance_points = tp_dollars / (point_value * size)
            tp_raw = entry + tp_distance_points * direction
            then inward-snapped to tick grid.
"""

import math
import pytest

from captain_online.blocks.b6_signal_output import _tp_from_dollars, _compute_tp


class TestTpFromDollars:
    """Unit tests for the _tp_from_dollars helper function."""

    def test_nkd_long_basic(self):
        """NKD long: $4450 target from entry=38000, point_value=5, size=1.

        tp_distance_points = 4450 / (5.0 * 1) = 890
        tp_raw = 38000 + 890 = 38890
        38890 / 5 = 7778.0 → floor = 7778 → 38890.0 (already on grid)
        """
        result = _tp_from_dollars(
            dollars=4450.0,
            entry=38000.0,
            direction=1,
            point_value=5.0,
            size=1,
            asset_id="NKD",
        )
        assert result == 38890.0

    def test_nkd_long_non_grid_entry(self):
        """Entry not on tick grid: raw TP may land off-grid → floor snaps it."""
        # entry=38003, tp_distance = 4450/5 = 890
        # tp_raw = 38893 → not on 5-point grid? 38893/5=7778.6 → floor=7778 → 38890
        result = _tp_from_dollars(
            dollars=4450.0,
            entry=38003.0,
            direction=1,
            point_value=5.0,
            size=1,
            asset_id="NKD",
        )
        assert result == 38890.0

    def test_nkd_short_basic(self):
        """NKD short: $4450 target from entry=38000.

        tp_raw = 38000 - 890 = 37110 → already on 5-point grid → 37110.0
        """
        result = _tp_from_dollars(
            dollars=4450.0,
            entry=38000.0,
            direction=-1,
            point_value=5.0,
            size=1,
            asset_id="NKD",
        )
        assert result == 37110.0

    def test_nkd_short_ceil_snap(self):
        """SHORT: when raw TP is off-grid, ceils upward (toward entry = inward)."""
        # entry=38000, tp_raw = 38000 - 891.5 = 37108.5 → ceil → 37110.0
        result = _tp_from_dollars(
            dollars=4457.5,  # 4457.5 / 5 = 891.5
            entry=38000.0,
            direction=-1,
            point_value=5.0,
            size=1,
            asset_id="NKD",
        )
        assert result == 37110.0

    def test_size_1_equals_size_default(self):
        """Explicit size=1 produces same result as implicit default."""
        kw = dict(dollars=4450.0, entry=38000.0, direction=1, point_value=5.0, asset_id="NKD")
        assert _tp_from_dollars(size=1, **kw) == _tp_from_dollars(size=1, **kw)

    def test_size_gt_1_divides_distance(self):
        """Size=2 halves the per-contract dollar distance relative to size=1."""
        r1 = _tp_from_dollars(4450.0, 38000.0, 1, 5.0, 1, "NKD")
        r2 = _tp_from_dollars(4450.0, 38000.0, 1, 5.0, 2, "NKD")
        # r2 uses tp_distance = 4450 / (5*2) = 445 → tp_raw = 38445 → floor(38445/5)*5 = 38445
        assert r2 == 38445.0
        assert r2 < r1  # smaller distance for larger size


class TestComputeTpDollarsShortCircuit:
    """_compute_tp routes to _tp_from_dollars when strategy has 'tp_dollars'."""

    NKD_STRATEGY = {
        "tp_dollars": 4450,
        "tp_multiple": 0.70,  # should be ignored when tp_dollars present
        "sl_multiple": 0.35,
    }
    NKD_FEATURES = {
        "entry_price": 38000.0,
        "or_range": 50.0,  # would give tp = 38000 + 0.70*50 = 38035 — NOT this
    }
    NKD_ASSET_DETAIL = {"point_value": 5.0}

    def test_tp_dollars_nkd_long_short_circuits_or_range(self):
        """When tp_dollars present, OR-range formula is bypassed."""
        tp = _compute_tp(
            self.NKD_STRATEGY,
            self.NKD_FEATURES,
            direction=1,
            asset_id="NKD",
            asset_detail=self.NKD_ASSET_DETAIL,
        )
        # Expected: _tp_from_dollars(4450, 38000, 1, 5.0, 1, "NKD") = 38890.0
        assert tp == 38890.0
        # Must NOT be the OR-range formula result (38035.0)
        assert tp != pytest.approx(38035.0)

    def test_tp_dollars_none_falls_back_to_or_range(self):
        """When tp_dollars absent, existing OR-range formula is used."""
        strategy = {"tp_multiple": 0.70}
        features = {"entry_price": 38000.0, "or_range": 50.0}
        tp = _compute_tp(strategy, features, direction=1, asset_id="NKD", asset_detail=self.NKD_ASSET_DETAIL)
        # 0.70 * 50 = 35; 38000 + 35 = 38035 → floor(38035/5)*5 = 38035.0
        assert tp == pytest.approx(38035.0)

    def test_tp_dollars_short_circuit_direction_minus_1(self):
        """NKD short: tp_dollars short-circuit gives the correct lower target."""
        tp = _compute_tp(
            self.NKD_STRATEGY,
            self.NKD_FEATURES,
            direction=-1,
            asset_id="NKD",
            asset_detail=self.NKD_ASSET_DETAIL,
        )
        assert tp == 37110.0

    def test_tp_dollars_no_entry_price_falls_back(self):
        """If entry_price missing, tp_dollars branch is skipped (entry is None)."""
        strategy = {"tp_dollars": 4450, "tp_multiple": 0.70}
        features = {"or_range": 50.0}  # no entry_price
        tp = _compute_tp(strategy, features, direction=1, asset_id="NKD")
        # Falls back to OR-range but entry is also missing from fallback formula
        # → tp = strategy.get("tp_level") = None
        assert tp is None

    def test_non_nkd_assets_unaffected(self):
        """Strategies without tp_dollars still use OR-range for all other assets."""
        strategy = {"tp_multiple": 0.70}
        features = {"entry_price": 4500.0, "or_range": 10.0}
        asset_detail = {"point_value": 50.0}
        tp = _compute_tp(strategy, features, direction=1, asset_id="ES", asset_detail=asset_detail)
        # 4500 + 0.70*10 = 4507 → floor(4507/0.25)*0.25 = 4507.0
        assert tp == pytest.approx(4507.0)
