"""Tests for shared.contract_resolver.tick_snap_outward (C2 — NKD pivot).

NKD tick_size is 5.0 per contract_ids.json. The helper rounds a raw stop
price OUTWARD (further from entry) so the stop is never tighter than intended.

LONG  (direction=1):  floor — stop goes DOWN  (e.g. 38022.5 → 38020.0)
SHORT (direction=-1): ceil  — stop goes UP    (e.g. 38022.5 → 38025.0)
"""

import pytest

from shared.contract_resolver import tick_snap_outward


class TestTickSnapOutwardNKD:
    """NKD has tick_size=5.0, so all results should be multiples of 5."""

    def test_long_floors_for_nkd(self):
        """LONG: 38022.5 floors down to the nearest 5-point boundary."""
        result = tick_snap_outward(38022.5, "NKD", 1)
        assert result == 38020.0

    def test_short_ceils_for_nkd(self):
        """SHORT: 38022.5 ceils up to the nearest 5-point boundary."""
        result = tick_snap_outward(38022.5, "NKD", -1)
        assert result == 38025.0

    def test_long_already_grid_aligned(self):
        """Price already on the grid — floor is a no-op."""
        result = tick_snap_outward(38020.0, "NKD", 1)
        assert result == 38020.0

    def test_short_already_grid_aligned(self):
        """Price already on the grid — ceil is a no-op."""
        result = tick_snap_outward(38025.0, "NKD", -1)
        assert result == 38025.0

    def test_long_just_above_grid(self):
        """38020.001 floors to 38020.0 for LONG."""
        result = tick_snap_outward(38020.001, "NKD", 1)
        assert result == 38020.0

    def test_short_just_below_grid(self):
        """38024.999 ceils to 38025.0 for SHORT."""
        result = tick_snap_outward(38024.999, "NKD", -1)
        assert result == 38025.0

    def test_outward_semantics_long_position(self):
        """For a LONG position, snapped stop must be <= raw stop (outward = lower)."""
        raw = 38027.3
        snapped = tick_snap_outward(raw, "NKD", 1)
        assert snapped <= raw

    def test_outward_semantics_short_position(self):
        """For a SHORT position, snapped stop must be >= raw stop (outward = higher)."""
        raw = 38022.7
        snapped = tick_snap_outward(raw, "NKD", -1)
        assert snapped >= raw


class TestTickSnapOutwardEdgeCases:
    """Direction validation and unknown-asset error handling."""

    def test_unknown_asset_raises_key_error(self):
        """Non-existent asset raises KeyError (mirrors contract_ids.json lookup)."""
        with pytest.raises(KeyError, match="FAKE_ASSET"):
            tick_snap_outward(100.0, "FAKE_ASSET", 1)

    def test_invalid_direction_raises_value_error(self):
        """direction=0 is not a valid trailing-stop direction."""
        with pytest.raises(ValueError, match="direction must be 1 or -1"):
            tick_snap_outward(38020.0, "NKD", 0)


class TestTickSnapOutwardOtherAssets:
    """Sanity checks on assets with finer tick sizes."""

    def test_es_long_quarter_point_floor(self):
        """ES tick_size=0.25; 4512.37 floors to 4512.25 for LONG."""
        result = tick_snap_outward(4512.37, "ES", 1)
        assert result == pytest.approx(4512.25, abs=1e-9)

    def test_es_short_quarter_point_ceil(self):
        """ES tick_size=0.25; 4512.37 ceils to 4512.50 for SHORT."""
        result = tick_snap_outward(4512.37, "ES", -1)
        assert result == pytest.approx(4512.50, abs=1e-9)
