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

# Top-level import ensures `captain_command.blocks.b3_api_adapter` is registered
# as an attribute on the `captain_command.blocks` package at collection time.
# Required because the @patch("captain_command.blocks.b3_api_adapter.<symbol>", ...)
# decorators below resolve the dotted target via getattr-walks (e.g. via
# pkgutil.resolve_name on some pytest/plugin combos), which do NOT auto-import
# submodules on AttributeError the way unittest.mock._importer does. Without
# this top-level import the tests error out on tower environments with:
#   AttributeError: module 'captain_command.blocks' has no attribute 'b3_api_adapter'
from captain_command.blocks.b3_api_adapter import TopstepXAdapter  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter():
    """Create a TopstepXAdapter with a mocked client, bypassing __init__."""
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

        # SL failure triggers automatic flatten — status reflects that
        assert result["status"] == "FLATTENED_SL_FAIL"
        assert result["entry_order_id"] == "ENTRY-001"

        # SL failure flags present
        assert result.get("sl_failed") is True
        assert "rate limit" in result.get("sl_error", "")

        # SL order ID should remain None (never set)
        assert result["sl_order_id"] is None

        # TP should succeed normally
        assert result["tp_order_id"] == "TP-001"
        assert result.get("tp_failed") is None

        # Position was flattened via close_position
        adapter._client.close_position.assert_called_once()

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

        # Verify cancel was never called — we flatten, not cancel
        adapter._client.cancel_order.assert_not_called()
        # Position was flattened after SL failure
        adapter._client.close_position.assert_called_once()
        assert result["entry_order_id"] == "ENTRY-002"
        assert result["status"] == "FLATTENED_SL_FAIL"


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


# ---------------------------------------------------------------------------
# Bracket order tests
# ---------------------------------------------------------------------------

class TestBracketOrder:
    """Native bracket order — single API call with atomic SL+TP."""

    @patch("captain_command.blocks.b3_api_adapter.get_tick_size",
           return_value=0.25)
    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_bracket_success(
        self, _mock_gate, _mock_compliance, _mock_resolve, _mock_tick,
        redis_mock,
    ):
        """Bracket order succeeds — no separate SL/TP calls."""
        adapter = _make_adapter()
        adapter._client.place_bracket_order.return_value = {
            "success": True,
            "orderId": "BRK-001",
        }

        order = _base_order(entry_price=5500.0, sl=5490.0, tp=5520.0)
        result = adapter.send_signal(order)

        assert result["status"] == "PLACED"
        assert result["entry_order_id"] == "BRK-001"
        assert result["bracket"] is True
        assert result["sl_order_id"] == "BRACKET"
        assert result["tp_order_id"] == "BRACKET"

        # Bracket used tick offsets: SL=40 ticks (10/0.25), TP=80 ticks (20/0.25)
        adapter._client.place_bracket_order.assert_called_once()
        call_kwargs = adapter._client.place_bracket_order.call_args
        assert call_kwargs[1]["sl_ticks"] == 40   # (5500-5490)/0.25
        assert call_kwargs[1]["tp_ticks"] == 80   # (5520-5500)/0.25

        # No separate SL/TP orders placed
        adapter._client.place_market_order.assert_not_called()
        adapter._client.place_stop_order.assert_not_called()
        adapter._client.place_limit_order.assert_not_called()

    @patch("captain_command.blocks.b3_api_adapter.get_tick_size",
           return_value=5.0)
    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.NKD.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_bracket_nkd_tick_calculation(
        self, _mock_gate, _mock_compliance, _mock_resolve, _mock_tick,
        redis_mock,
    ):
        """NKD tick size is 5 — verify tick math."""
        adapter = _make_adapter()
        adapter._client.place_bracket_order.return_value = {
            "success": True,
            "orderId": "BRK-NKD",
        }

        # NKD: entry ~38000, SL 50 points away = 10 ticks, TP 100 points = 20 ticks
        order = _base_order(
            asset="NKD", entry_price=38000.0, sl=37950.0, tp=38100.0,
        )
        result = adapter.send_signal(order)

        assert result["bracket"] is True
        call_kwargs = adapter._client.place_bracket_order.call_args
        assert call_kwargs[1]["sl_ticks"] == 10   # (38000-37950)/5
        assert call_kwargs[1]["tp_ticks"] == 20   # (38100-38000)/5

    @patch("captain_command.blocks.b3_api_adapter.get_tick_size",
           return_value=0.25)
    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_bracket_fails_falls_back_to_separate(
        self, _mock_gate, _mock_compliance, _mock_resolve, _mock_tick,
        redis_mock,
    ):
        """Bracket fails — falls back to separate entry + SL + TP."""
        adapter = _make_adapter()
        adapter._client.place_bracket_order.return_value = {
            "success": False,
            "errorMessage": "bracket not supported",
        }
        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-FB",
        }
        adapter._client.place_stop_order.return_value = {
            "success": True,
            "orderId": "SL-FB",
        }
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-FB",
        }

        order = _base_order(entry_price=5500.0, sl=5490.0, tp=5520.0)
        result = adapter.send_signal(order)

        # Bracket was attempted then fell back
        adapter._client.place_bracket_order.assert_called_once()
        adapter._client.place_market_order.assert_called_once()
        adapter._client.place_stop_order.assert_called_once()
        adapter._client.place_limit_order.assert_called_once()

        assert result["status"] == "PLACED"
        assert result["entry_order_id"] == "ENTRY-FB"
        assert result["sl_order_id"] == "SL-FB"
        assert result["tp_order_id"] == "TP-FB"
        assert result.get("bracket") is None

    @patch("captain_command.blocks.b3_api_adapter.get_tick_size",
           return_value=0.25)
    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_no_entry_price_skips_bracket(
        self, _mock_gate, _mock_compliance, _mock_resolve, _mock_tick,
        redis_mock,
    ):
        """No entry_price in order — bracket skipped, goes straight to separate."""
        adapter = _make_adapter()
        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-NE",
        }
        adapter._client.place_stop_order.return_value = {
            "success": True,
            "orderId": "SL-NE",
        }
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-NE",
        }

        # No entry_price — bracket not attempted
        order = _base_order()
        result = adapter.send_signal(order)

        adapter._client.place_bracket_order.assert_not_called()
        adapter._client.place_market_order.assert_called_once()
        assert result["status"] == "PLACED"
        assert result.get("bracket") is None
