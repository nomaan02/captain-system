"""Tests for C4/C15 — NKD locked_strategy trail-control fields in bootstrap_production.py.

Verifies that:
1. P2_STRATEGIES["NKD"] contains all 8 trail-control keys with correct values (C15 spec).
2. _build_locked_strategy("NKD") serialises a JSON string that includes all 8 keys.
3. Other assets (e.g. ES) are NOT affected — their strategies have no trail keys.

These tests parse module constants and the pure _build_locked_strategy function
directly; no DB connection required.
"""

import json
import pytest

from scripts.bootstrap_production import P2_STRATEGIES, _build_locked_strategy

EXPECTED_NKD_TRAIL_KEYS = {
    "tp_dollars": 4450,
    "is_nkd_trail": True,
    "trail_step_dollars": 500,
    "sl_dollars_fixed": 1025,
    "trail_phase_b_start_dollars": 2000,
    "trail_phase_b_buffer_dollars": 1000,
    "trail_phase_c_start_dollars": 3000,
    "trail_phase_c_buffer_dollars": 450,
}


class TestP2StrategiesNKDTrailFields:
    """P2_STRATEGIES constant has the correct NKD trail-control entries."""

    def test_nkd_tp_dollars(self):
        assert P2_STRATEGIES["NKD"]["tp_dollars"] == 4450

    def test_nkd_is_nkd_trail(self):
        assert P2_STRATEGIES["NKD"]["is_nkd_trail"] is True

    def test_nkd_trail_step_dollars(self):
        assert P2_STRATEGIES["NKD"]["trail_step_dollars"] == 500

    def test_nkd_trail_phase_b_start_dollars(self):
        assert P2_STRATEGIES["NKD"]["trail_phase_b_start_dollars"] == 2000

    def test_nkd_trail_phase_c_start_dollars(self):
        assert P2_STRATEGIES["NKD"]["trail_phase_c_start_dollars"] == 3000

    def test_nkd_trail_phase_c_buffer_dollars(self):
        assert P2_STRATEGIES["NKD"]["trail_phase_c_buffer_dollars"] == 450

    def test_all_eight_keys_present(self):
        for k, v in EXPECTED_NKD_TRAIL_KEYS.items():
            assert P2_STRATEGIES["NKD"][k] == v, f"Mismatch on key {k!r}"

    def test_existing_p2_keys_unchanged(self):
        """Core P2 keys (m, k, OO, regime_class) are not altered."""
        nkd = P2_STRATEGIES["NKD"]
        assert nkd["m"] == 6
        assert nkd["k"] == 6
        assert nkd["OO"] == pytest.approx(0.8533)
        assert nkd["regime_class"] == "REGIME_NEUTRAL"


class TestBuildLockedStrategyNKD:
    """_build_locked_strategy("NKD") produces JSON with all trail-control keys."""

    def setup_method(self):
        self.locked_json = _build_locked_strategy("NKD")
        self.locked = json.loads(self.locked_json)

    def test_returns_valid_json(self):
        assert isinstance(self.locked, dict)

    def test_all_eight_trail_keys_in_json(self):
        for k, v in EXPECTED_NKD_TRAIL_KEYS.items():
            assert k in self.locked, f"Missing key {k!r} in locked_strategy JSON"
            assert self.locked[k] == v, f"Wrong value for {k!r}: {self.locked[k]!r}"

    def test_existing_strategy_fields_preserved(self):
        """tp_multiple and sl_multiple are still present for fallback semantics."""
        assert "tp_multiple" in self.locked
        assert "sl_multiple" in self.locked
        assert self.locked["tp_multiple"] == pytest.approx(0.70)
        assert self.locked["sl_multiple"] == pytest.approx(0.35)

    def test_sl_dollars_fixed_in_locked_strategy(self):
        assert self.locked["sl_dollars_fixed"] == 1025

    def test_trail_phase_b_buffer_in_locked_strategy(self):
        assert self.locked["trail_phase_b_buffer_dollars"] == 1000

    def test_trail_phase_b_start_is_2000(self):
        assert self.locked["trail_phase_b_start_dollars"] == 2000

    def test_trail_phase_c_start_is_3000(self):
        assert self.locked["trail_phase_c_start_dollars"] == 3000


class TestBuildLockedStrategyOtherAssets:
    """Other assets must NOT gain NKD trail fields."""

    @pytest.mark.parametrize("asset_id", ["ES", "MES", "NQ", "MGC", "MYM", "ZB"])
    def test_no_trail_keys_for_non_nkd(self, asset_id):
        locked = json.loads(_build_locked_strategy(asset_id))
        for k in EXPECTED_NKD_TRAIL_KEYS:
            assert k not in locked, (
                f"Asset {asset_id} should not have trail key {k!r} in locked_strategy"
            )
