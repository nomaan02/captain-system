# region imports
from AlgorithmImports import *
# endregion
"""Tests for W3: SL/TP order failure detection in B3 API Adapter.

Verifies that failed SL/TP placements after a successful market entry:
- Set sl_failed / tp_failed flags in the result dict
- Include error messages from the API response
- Publish CRITICAL alert on SL failure
- Publish HIGH alert on TP failure
- Do NOT cancel the entry order
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter():
    """Create a TopstepXAdapter with a mocked client, bypassing __init__."""
    from captain_command.blocks.b3_api_adapter import TopstepXAdapter

    adapter = object.__new__(TopstepXAdapter)
    adapter._client = MagicMock()
    adapter._account_id = "20319811"
    adapter._connected = True
    adapter._vault_key_name = "test"
    adapter._contract_id = "CON.F.US.EP.M26"
    return adapter


def _base_order(**overrides):
    """Return a minimal valid order dict."""
    order = {
        "asset": "ES",
        "direction": "BUY",
        "size": 1,
        "sl": 5000.0,
        "tp": 5100.0,
    }
    order.update(overrides)
    return order


@pytest.fixture
def redis_mock():
    """Provide a fresh Redis mock patched at the b3_api_adapter module level."""
    mock_client = MagicMock()
    mock_client.publish = MagicMock(return_value=1)
    mock_fn = MagicMock(return_value=mock_client)
    with patch("captain_command.blocks.b3_api_adapter.get_redis_client", mock_fn):
        yield mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSLPlacementFailure:
    """SL placement fails after successful entry -- CRITICAL alert expected."""

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_sl_failure_sets_flags_and_alerts(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        adapter = _make_adapter()

        # Entry succeeds
        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-001",
        }
        # SL fails
        adapter._client.place_stop_order.return_value = {
            "success": False,
            "errorMessage": "rate limit",
        }
        # TP succeeds
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-001",
        }

        result = adapter.send_signal(_base_order())

        # Entry should still be reported as PLACED
        assert result["status"] == "PLACED"
        assert result["entry_order_id"] == "ENTRY-001"

        # SL failure flags present
        assert result.get("sl_failed") is True
        assert "rate limit" in result.get("sl_error", "")

        # SL order ID should remain None (never set)
        assert result["sl_order_id"] is None

        # TP should succeed normally
        assert result["tp_order_id"] == "TP-001"
        assert result.get("tp_failed") is None

        # CRITICAL alert published to CH_ALERTS
        publish_calls = redis_mock.publish.call_args_list
        alert_calls = [
            c for c in publish_calls
            if c[0][0] == "captain:alerts"
        ]
        assert len(alert_calls) >= 1
        alert_payload = json.loads(alert_calls[0][0][1])
        assert alert_payload["priority"] == "CRITICAL"
        assert alert_payload["event_type"] == "SL_PLACEMENT_FAILED"
        assert "UNPROTECTED" in alert_payload["message"]

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_sl_failure_does_not_cancel_entry(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        """Entry order must NOT be cancelled when SL fails."""
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-002",
        }
        adapter._client.place_stop_order.return_value = {
            "success": False,
            "errorMessage": "server error",
        }
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-002",
        }

        result = adapter.send_signal(_base_order())

        # Verify cancel was never called
        adapter._client.cancel_order.assert_not_called()
        # Position entry is still reported
        assert result["entry_order_id"] == "ENTRY-002"
        assert result["status"] == "PLACED"


class TestTPPlacementFailure:
    """TP placement fails after successful entry + SL -- WARNING alert."""

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_tp_failure_sets_flags_and_alerts(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-003",
        }
        # SL succeeds
        adapter._client.place_stop_order.return_value = {
            "success": True,
            "orderId": "SL-003",
        }
        # TP fails
        adapter._client.place_limit_order.return_value = {
            "success": False,
            "errorMessage": "insufficient margin",
        }

        result = adapter.send_signal(_base_order())

        assert result["status"] == "PLACED"
        assert result["sl_order_id"] == "SL-003"
        assert result.get("sl_failed") is None

        # TP failure flags present
        assert result.get("tp_failed") is True
        assert "insufficient margin" in result.get("tp_error", "")
        assert result["tp_order_id"] is None

        # HIGH alert published to CH_ALERTS
        publish_calls = redis_mock.publish.call_args_list
        alert_calls = [
            c for c in publish_calls
            if c[0][0] == "captain:alerts"
        ]
        assert len(alert_calls) >= 1
        alert_payload = json.loads(alert_calls[0][0][1])
        assert alert_payload["priority"] == "HIGH"
        assert alert_payload["event_type"] == "TP_PLACEMENT_FAILED"


class TestBothSLAndTPFailure:
    """Both SL and TP fail -- both flags set, both alerts published."""

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_both_failures(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-004",
        }
        adapter._client.place_stop_order.return_value = {
            "success": False,
            "errorMessage": "rate limit",
        }
        adapter._client.place_limit_order.return_value = {
            "success": False,
            "errorMessage": "rate limit",
        }

        result = adapter.send_signal(_base_order())

        assert result["sl_failed"] is True
        assert result["tp_failed"] is True
        assert result["sl_order_id"] is None
        assert result["tp_order_id"] is None

        # Two alerts published
        publish_calls = redis_mock.publish.call_args_list
        alert_calls = [
            c for c in publish_calls
            if c[0][0] == "captain:alerts"
        ]
        assert len(alert_calls) == 2

        priorities = {json.loads(c[0][1])["priority"] for c in alert_calls}
        assert "CRITICAL" in priorities  # SL failure
        assert "HIGH" in priorities      # TP failure


class TestSuccessfulSLTPPlacement:
    """Happy path -- both SL and TP succeed, no failure flags."""

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_success_no_failure_flags(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-005",
        }
        adapter._client.place_stop_order.return_value = {
            "success": True,
            "orderId": "SL-005",
        }
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-005",
        }

        result = adapter.send_signal(_base_order())

        assert result["status"] == "PLACED"
        assert result["entry_order_id"] == "ENTRY-005"
        assert result["sl_order_id"] == "SL-005"
        assert result["tp_order_id"] == "TP-005"
        assert result.get("sl_failed") is None
        assert result.get("tp_failed") is None

        # No alerts published to CH_ALERTS for SL/TP failures
        publish_calls = redis_mock.publish.call_args_list
        alert_calls = [
            c for c in publish_calls
            if c[0][0] == "captain:alerts"
            and ("SL_PLACEMENT_FAILED" in c[0][1]
                 or "TP_PLACEMENT_FAILED" in c[0][1])
        ]
        assert len(alert_calls) == 0
