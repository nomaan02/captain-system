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

        # F4 guard: TP must NOT have been attempted after SL-fail flatten.
        # (Pre-F4 this asserted tp_order_id == "TP-001"; the guard now
        # short-circuits the TP block, leaving tp_order_id None and
        # place_limit_order never called.)
        assert result.get("tp_order_id") is None
        assert result.get("tp_failed") is None
        adapter._client.place_limit_order.assert_not_called()

        # Position was flattened via close_position
        adapter._client.close_position.assert_called_once()

        # CRITICAL alert published to CH_ALERTS (SL only — no TP alert)
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
        # No spurious TP_PLACEMENT_FAILED alert
        event_types = {json.loads(c[0][1])["event_type"] for c in alert_calls}
        assert "TP_PLACEMENT_FAILED" not in event_types

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


class TestSLFailureSkipsTPAttempt:
    """When SL fails, the F4 guard short-circuits the TP block entirely.
    Only the SL CRITICAL alert is published; no TP alert, no tp_failed flag."""

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_sl_fail_skips_tp_so_only_sl_alert_published(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        """Pre-F4 behaviour: both SL and TP would fail → 2 alerts.
        Post-F4 behaviour: SL fails → guard fires → TP never attempted → 1 alert."""
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-004",
        }
        adapter._client.place_stop_order.return_value = {
            "success": False,
            "errorMessage": "rate limit",
        }
        # place_limit_order return value is irrelevant — it must not be called

        result = adapter.send_signal(_base_order())

        assert result["sl_failed"] is True
        assert result["sl_order_id"] is None
        assert result["tp_order_id"] is None
        # tp_failed is NOT set (TP block was never entered)
        assert result.get("tp_failed") is None
        adapter._client.place_limit_order.assert_not_called()

        # Only the SL CRITICAL alert is published
        publish_calls = redis_mock.publish.call_args_list
        alert_calls = [
            c for c in publish_calls
            if c[0][0] == "captain:alerts"
        ]
        event_types = {json.loads(c[0][1])["event_type"] for c in alert_calls}
        assert "SL_PLACEMENT_FAILED" in event_types
        assert "TP_PLACEMENT_FAILED" not in event_types
        priorities = {json.loads(c[0][1])["priority"] for c in alert_calls}
        assert "CRITICAL" in priorities
        assert "HIGH" not in priorities  # no TP HIGH alert


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

    @patch("captain_command.blocks.b3_api_adapter.get_tick_size",
           return_value=0.25)
    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_bracket_pushes_pending_to_redis(
        self, _mock_gate, _mock_compliance, _mock_resolve, _mock_tick,
        redis_mock,
    ):
        """Successful bracket: HSET called on bracket:pending:{account_id} with entry_oid field."""
        adapter = _make_adapter()
        adapter._client.place_bracket_order.return_value = {
            "success": True,
            "orderId": "BRK-PEND",
        }

        order = _base_order(
            entry_price=5500.0, sl=5490.0, tp=5520.0,
            signal_id="SIG-TESTPEND",
        )
        result = adapter.send_signal(order)

        assert result["status"] == "PLACED"
        assert result["sl_order_id"] == "BRACKET"

        # HSET must have been called with bracket:pending:{account_id}
        hset_calls = redis_mock.hset.call_args_list
        assert len(hset_calls) >= 1
        pending_calls = [
            c for c in hset_calls
            if str(c[0][0]).startswith("bracket:pending:")
        ]
        assert len(pending_calls) == 1, (
            f"Expected exactly 1 bracket:pending HSET call, got {hset_calls}"
        )
        _key, field, value_json = pending_calls[0][0]
        assert field == "BRK-PEND"
        payload = json.loads(value_json)
        assert payload["signal_id"] == "SIG-TESTPEND"
        assert payload["asset"] == "ES"
        assert payload["side"] == "BUY"
        assert "timestamp" in payload

        # EXPIRE must also be called on the same key
        expire_calls = redis_mock.expire.call_args_list
        pending_expire_calls = [
            c for c in expire_calls
            if str(c[0][0]).startswith("bracket:pending:")
        ]
        assert len(pending_expire_calls) == 1
        ttl = pending_expire_calls[0][0][1]
        assert ttl == 10


# ---------------------------------------------------------------------------
# F4 orphan-TP guard tests
# Ref: BATCH_2_F4_ORPHAN_TP.md; audit §1 row #4 (2026-05-18 order
#      2994362566, limit BUY @ 60665, placed 23:08:07, cancelled 23:22:43).
# ---------------------------------------------------------------------------


class TestFallbackTPGuardF4:
    """Fallback TP must be skipped when the SL attempt failed and the
    position has already been flattened or is emergency-unprotected.
    When SL succeeded or sl_price is None the TP block still runs."""

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_fallback_tp_skipped_when_sl_failed_and_flattened(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        """SL fails → close_position succeeds → status FLATTENED_SL_FAIL.
        TP must NOT be attempted (orphan TP guard, F4)."""
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-F4-1",
        }
        adapter._client.place_stop_order.return_value = {
            "success": False,
            "errorMessage": "Order price is outside allowed range",
        }
        # close_position succeeds (default MagicMock return — no raise)

        result = adapter.send_signal(_base_order())

        # Status reflects flatten-after-SL-fail
        assert result["status"] == "FLATTENED_SL_FAIL"
        assert result["entry_order_id"] == "ENTRY-F4-1"
        assert result.get("sl_failed") is True
        assert result["sl_order_id"] is None

        # TP block must not have run
        assert result.get("tp_order_id") is None
        assert result.get("tp_failed") is None
        assert result.get("tp_error") is None
        adapter._client.place_limit_order.assert_not_called()

        # Flatten was still called (regression: existing behaviour preserved)
        adapter._client.close_position.assert_called_once()

        # SL CRITICAL alert still published; no TP alert
        publish_calls = redis_mock.publish.call_args_list
        alerts = [c for c in publish_calls if c[0][0] == "captain:alerts"]
        event_types = {json.loads(c[0][1])["event_type"] for c in alerts}
        assert "SL_PLACEMENT_FAILED" in event_types
        assert "TP_PLACEMENT_FAILED" not in event_types

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_fallback_tp_skipped_when_emergency_unprotected(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        """SL fails → close_position also raises → status EMERGENCY_UNPROTECTED.
        TP must NOT be attempted (orphan TP guard, F4)."""
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-F4-2",
        }
        adapter._client.place_stop_order.return_value = {
            "success": False,
            "errorMessage": "rate limit",
        }
        adapter._client.close_position.side_effect = Exception(
            "simulated flatten failure"
        )

        result = adapter.send_signal(_base_order())

        assert result["status"] == "EMERGENCY_UNPROTECTED"
        assert result.get("sl_failed") is True
        assert result.get("tp_order_id") is None
        assert result.get("tp_failed") is None
        adapter._client.place_limit_order.assert_not_called()

        # Both SL-fail and FLATTEN_FAILED EMERGENCY alerts still published
        publish_calls = redis_mock.publish.call_args_list
        alerts = [c for c in publish_calls if c[0][0] == "captain:alerts"]
        event_types = {json.loads(c[0][1])["event_type"] for c in alerts}
        assert "SL_PLACEMENT_FAILED" in event_types
        assert "FLATTEN_FAILED" in event_types
        assert "TP_PLACEMENT_FAILED" not in event_types

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_fallback_tp_placed_when_sl_succeeded(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        """Regression: SL succeeds → guard must NOT fire → TP placed normally."""
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-F4-3",
        }
        adapter._client.place_stop_order.return_value = {
            "success": True,
            "orderId": "SL-F4-3",
        }
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-F4-3",
        }

        result = adapter.send_signal(_base_order())

        assert result["status"] == "PLACED"
        assert result["sl_order_id"] == "SL-F4-3"
        assert result["tp_order_id"] == "TP-F4-3"  # TP placed — guard didn't fire
        assert result.get("sl_failed") is None
        assert result.get("tp_failed") is None
        adapter._client.close_position.assert_not_called()
        adapter._client.place_limit_order.assert_called_once()

    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_fallback_tp_placed_when_sl_price_is_none(
        self, _mock_gate, _mock_compliance, _mock_resolve, redis_mock,
    ):
        """When sl_price is None the SL block is never entered; sl_failed is
        never set; the guard must NOT fire and TP must still be placed.
        Preserves the audit hard-rule: 'if sl_price is None, TP block must
        still run as before'."""
        adapter = _make_adapter()

        adapter._client.place_market_order.return_value = {
            "success": True,
            "orderId": "ENTRY-F4-4",
        }
        adapter._client.place_limit_order.return_value = {
            "success": True,
            "orderId": "TP-F4-4",
        }

        result = adapter.send_signal(_base_order(sl=None))

        assert result["status"] == "PLACED"
        assert result["sl_order_id"] is None   # never set — SL block skipped
        assert result["tp_order_id"] == "TP-F4-4"
        assert result.get("sl_failed") is None  # key absent — confirms 'is True' precision
        adapter._client.place_stop_order.assert_not_called()
        adapter._client.close_position.assert_not_called()
        adapter._client.place_limit_order.assert_called_once()

    @patch("captain_command.blocks.b3_api_adapter.get_tick_size",
           return_value=0.25)
    @patch("captain_command.blocks.b3_api_adapter.resolve_contract_id",
           return_value="CON.F.US.EP.M26")
    @patch("captain_command.blocks.b3_api_adapter.compliance_check",
           return_value={"approved": True})
    @patch("captain_command.blocks.b3_api_adapter.check_compliance_gate",
           return_value={"execution_mode": "AUTO", "allowed": True})
    def test_bracket_path_unaffected_by_f4_guard(
        self, _mock_gate, _mock_compliance, _mock_resolve, _mock_tick,
        redis_mock,
    ):
        """Bracket success path returns before the fallback flow; neither the
        fallback SL, flatten, nor the F4 TP guard are reached."""
        adapter = _make_adapter()
        adapter._client.place_bracket_order.return_value = {
            "success": True,
            "orderId": "BRK-F4",
        }

        result = adapter.send_signal(_base_order(entry_price=5500.0, sl=5490.0, tp=5520.0))

        assert result["status"] == "PLACED"
        assert result["bracket"] is True
        assert result["sl_order_id"] == "BRACKET"
        assert result["tp_order_id"] == "BRACKET"
        # None of the separate-order helpers were called
        adapter._client.place_market_order.assert_not_called()
        adapter._client.place_stop_order.assert_not_called()
        adapter._client.place_limit_order.assert_not_called()
        adapter._client.close_position.assert_not_called()
