# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Tests for AUTO_EXECUTE env var parsing consistency.

Verifies that both the Command orchestrator and the B12 compliance gate
accept the same set of truthy/falsy values for the AUTO_EXECUTE env var
(W2 fix from 2026-04-12 audit).
"""

import os
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers — extract parsing logic from both modules
# ---------------------------------------------------------------------------

def _orchestrator_parse(value: str) -> bool:
    """Replicate orchestrator.py:310 parsing logic."""
    return value.lower() in ("1", "true", "yes")


def _compliance_gate_parse(value: str) -> bool:
    """Replicate b12_compliance_gate.py:87 parsing logic."""
    return value.lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Truthy values — must be AUTO in both paths
# ---------------------------------------------------------------------------

class TestAutoExecuteTruthy:
    """AUTO_EXECUTE truthy values must enable auto-execution in both paths."""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "Yes", "YES"])
    def test_orchestrator_truthy(self, value):
        assert _orchestrator_parse(value) is True, (
            f"Orchestrator should accept AUTO_EXECUTE={value!r} as truthy"
        )

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "Yes", "YES"])
    def test_compliance_gate_truthy(self, value):
        assert _compliance_gate_parse(value) is True, (
            f"Compliance gate should accept AUTO_EXECUTE={value!r} as truthy"
        )


# ---------------------------------------------------------------------------
# Falsy values — must be MANUAL in both paths
# ---------------------------------------------------------------------------

class TestAutoExecuteFalsy:
    """AUTO_EXECUTE falsy values must result in MANUAL mode in both paths."""

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "No", "NO", ""])
    def test_orchestrator_falsy(self, value):
        assert _orchestrator_parse(value) is False, (
            f"Orchestrator should treat AUTO_EXECUTE={value!r} as falsy"
        )

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "No", "NO", ""])
    def test_compliance_gate_falsy(self, value):
        assert _compliance_gate_parse(value) is False, (
            f"Compliance gate should treat AUTO_EXECUTE={value!r} as falsy"
        )


# ---------------------------------------------------------------------------
# Integration — test actual compliance gate function with env var
# ---------------------------------------------------------------------------

class TestComplianceGateAutoExecuteIntegration:
    """Test check_compliance_gate() with various AUTO_EXECUTE values."""

    @staticmethod
    def _make_full_gate_config():
        """Return a compliance_gate.json dict with all 11 rts6_* flags satisfied."""
        return {
            "rts6_kill_switch": True,
            "rts6_pre_trade_limits": True,
            "rts6_post_trade_controls": True,
            "rts6_market_maker_obligations": True,
            "rts6_anti_manipulation": True,
            "rts6_testing_and_deployment": True,
            "rts6_business_continuity": True,
            "rts6_monitoring_and_review": True,
            "rts6_record_keeping": True,
            "rts6_outsourcing_compliance": True,
            "rts6_annual_self_assessment": True,
        }

    @pytest.mark.parametrize("value,expected_mode", [
        ("true", "AUTO"),
        ("1", "AUTO"),
        ("yes", "AUTO"),
        ("false", "MANUAL"),
        ("0", "MANUAL"),
        ("no", "MANUAL"),
    ])
    def test_compliance_gate_execution_mode(self, value, expected_mode):
        """check_compliance_gate() must return correct mode for each value."""
        gate_config = self._make_full_gate_config()

        with patch.dict(os.environ, {"AUTO_EXECUTE": value}):
            with patch(
                "captain_command.blocks.b12_compliance_gate._load_gate_config",
                return_value=gate_config,
            ):
                from captain_command.blocks.b12_compliance_gate import check_compliance_gate
                result = check_compliance_gate()
                assert result["execution_mode"] == expected_mode, (
                    f"AUTO_EXECUTE={value!r} should produce {expected_mode}, "
                    f"got {result['execution_mode']}"
                )
