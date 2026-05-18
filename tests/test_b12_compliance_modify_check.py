"""Tests for C8 — compliance_modify_check wrapper in b12_compliance_gate.py.

compliance_modify_check(account_id, asset, execution_mode) gates /Order/modify
calls issued by the NKD trailing-stop loop. It returns (allowed, reason).

Key behaviours:
- AUTO mode + permitted asset  → (True, None)
- MANUAL mode                  → (False, reason_str)
- Asset removed from D00       → (False, reason_str)
- TSM lookup failure           → (True, None)  [non-blocking default]
"""

from unittest.mock import patch, MagicMock
import pytest

from captain_command.blocks.b12_compliance_gate import compliance_modify_check


def _make_tsm(max_contracts=10, fee_instrument=None):
    """Minimal TSM dict for compliance checks."""
    tsm = {"max_contracts": max_contracts}
    if fee_instrument:
        tsm["fee_schedule"] = {"fees_by_instrument": {fee_instrument: 5.0}}
    return tsm


class TestAutoModePermittedAsset:
    """AUTO mode with a permitted asset should return (True, None)."""

    @patch("captain_command.blocks.b12_compliance_gate._get_account_tsm")
    @patch("captain_command.blocks.b12_compliance_gate._get_active_assets", return_value=["NKD", "ES"])
    def test_auto_mode_nkd_permitted_returns_true(self, mock_assets, mock_tsm):
        mock_tsm.return_value = _make_tsm()
        allowed, reason = compliance_modify_check("21855714", "NKD", "AUTO")
        assert allowed is True
        assert reason is None

    @patch("captain_command.blocks.b12_compliance_gate._get_account_tsm")
    @patch("captain_command.blocks.b12_compliance_gate._get_active_assets", return_value=None)
    def test_auto_mode_no_active_assets_list_permits_all(self, mock_assets, mock_tsm):
        """When active_assets is None (not yet loaded), instrument_permitted returns True."""
        mock_tsm.return_value = _make_tsm()
        allowed, reason = compliance_modify_check("21855714", "NKD", "AUTO")
        assert allowed is True
        assert reason is None


class TestManualMode:
    """MANUAL execution_mode always blocks modify regardless of asset status."""

    def test_manual_mode_returns_false_with_reason(self):
        allowed, reason = compliance_modify_check("21855714", "NKD", "MANUAL")
        assert allowed is False
        assert reason is not None
        assert "MANUAL" in reason or "execution_mode" in reason

    def test_unknown_mode_treated_as_non_auto(self):
        allowed, reason = compliance_modify_check("21855714", "NKD", "UNKNOWN")
        assert allowed is False
        assert reason is not None


class TestInstrumentNotPermitted:
    """When the asset is removed from D00 active universe, modify is blocked."""

    @patch("captain_command.blocks.b12_compliance_gate._get_account_tsm")
    @patch("captain_command.blocks.b12_compliance_gate._get_active_assets", return_value=["ES", "MES"])
    def test_nkd_removed_from_d00_returns_false(self, mock_assets, mock_tsm):
        """NKD not in active_assets → instrument_permitted returns False → block."""
        mock_tsm.return_value = _make_tsm()
        allowed, reason = compliance_modify_check("21855714", "NKD", "AUTO")
        assert allowed is False
        assert reason is not None
        assert "NKD" in reason or "permitted" in reason.lower()

    @patch("captain_command.blocks.b12_compliance_gate._get_account_tsm")
    @patch("captain_command.blocks.b12_compliance_gate._get_active_assets", return_value=["NKD"])
    def test_fee_schedule_excludes_nkd_blocks(self, mock_assets, mock_tsm):
        """Asset in active_assets but excluded from fee_schedule → blocked."""
        mock_tsm.return_value = _make_tsm(fee_instrument="ES")  # NKD not in fee_schedule
        allowed, reason = compliance_modify_check("21855714", "NKD", "AUTO")
        assert allowed is False


class TestTsmLookupFailure:
    """If TSM lookup fails (returns None), default to ALLOW (non-blocking)."""

    @patch("captain_command.blocks.b12_compliance_gate._get_account_tsm", return_value=None)
    def test_tsm_none_defaults_to_allow(self, mock_tsm):
        allowed, reason = compliance_modify_check("21855714", "NKD", "AUTO")
        assert allowed is True
        assert reason is None


class TestNKDComplianceLockdownIntegration:
    """End-to-end: execution_mode flip to MANUAL halts trail modify (does NOT close)."""

    def test_auto_to_manual_transition_blocks_subsequent_calls(self):
        """Calling with MANUAL mode after AUTO mode correctly returns False."""
        # Simulate: first call AUTO, second call MANUAL (mode flipped by operator)
        with (
            patch("captain_command.blocks.b12_compliance_gate._get_account_tsm") as m_tsm,
            patch("captain_command.blocks.b12_compliance_gate._get_active_assets", return_value=["NKD"]),
        ):
            m_tsm.return_value = _make_tsm()
            allowed1, _ = compliance_modify_check("21855714", "NKD", "AUTO")
            assert allowed1 is True

        # Operator switches to MANUAL mid-position
        allowed2, reason2 = compliance_modify_check("21855714", "NKD", "MANUAL")
        assert allowed2 is False
        assert reason2 is not None
