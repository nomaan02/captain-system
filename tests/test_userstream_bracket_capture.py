# region imports
from AlgorithmImports import *
# endregion
"""Tests for R1: UserStream bracket child-order capture (C5 of NKD pivot plan).

Covers _try_capture_bracket_child in captain-online/captain_online/main.py and
the staged-children consumption in OnlineOrchestrator._handle_taken_skipped in
captain-online/captain_online/blocks/orchestrator.py.

Refs: NKD_PIVOT_AUDIT.md §5.1, PLAN.md §C5
"""

import json
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from captain_online.main import _try_capture_bracket_child, _REDIS_KEY_OPEN_POSITIONS
from captain_online.blocks.orchestrator import OnlineOrchestrator, REDIS_KEY_OPEN_POSITIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCT = 21855714
_ENTRY_OID = "9001"
_SIG_ID = "SIG-ABCD12345678"
_ET = ZoneInfo("America/New_York")


def _make_redis(positions: dict | None = None, pending: dict | None = None):
    """Build a minimal mock Redis client pre-loaded with fixture data.

    positions  : {signal_id: json_str} for captain:open_positions hash
    pending    : {entry_oid_str: json_str} for bracket:pending:{acct} hash
    """
    mock = MagicMock()

    pos_store: dict[str, str] = positions or {}
    pending_store: dict[str, str] = pending or {}
    children_store: dict[str, str] = {}

    def hgetall(key):
        if key == f"bracket:pending:{_ACCT}":
            return dict(pending_store)
        return {}

    def hget(key, field):
        if key == REDIS_KEY_OPEN_POSITIONS:
            return pos_store.get(field)
        return None

    def hset(key, field, value):
        if key == REDIS_KEY_OPEN_POSITIONS:
            pos_store[field] = value
        return 1

    def hdel(key, field):
        if key == f"bracket:pending:{_ACCT}":
            pending_store.pop(str(field), None)
        return 1

    def get(key):
        return children_store.get(key)

    def set_(key, value, ex=None):
        children_store[key] = value
        return True

    def delete(key):
        children_store.pop(key, None)
        return 1

    mock.hgetall.side_effect = hgetall
    mock.hget.side_effect = hget
    mock.hset.side_effect = hset
    mock.hdel.side_effect = hdel
    mock.get.side_effect = get
    mock.set.side_effect = set_
    mock.delete.side_effect = delete

    # Expose the stores so tests can inspect them directly
    mock._pos_store = pos_store
    mock._pending_store = pending_store
    mock._children_store = children_store

    return mock


def _pending_entry(side="BUY"):
    return json.dumps({
        "signal_id": _SIG_ID,
        "asset": "ES",
        "side": side,
        "timestamp": 1716048000000,
    })


def _open_position(sl="BRACKET", tp="BRACKET"):
    return json.dumps({
        "signal_id": _SIG_ID,
        "asset": "ES",
        "direction": 1,
        "bracket": True,
        "entry_order_id": _ENTRY_OID,
        "sl_order_id": sl,
        "tp_order_id": tp,
        "entry_time": "2026-05-18T09:30:00",
        "contracts": 1,
    })


# ---------------------------------------------------------------------------
# 1. Happy-path: SL then TP captured and written to open_positions
# ---------------------------------------------------------------------------

class TestCaptureLongSlThenTp:
    """Feed STOP then LIMIT child orders for a BUY entry; assert real IDs stored."""

    def test_capture_long_sl(self):
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        positions = {_SIG_ID: _open_position()}
        rc = _make_redis(positions=positions, pending=pending)

        stop_order = {
            "accountId": _ACCT,
            "id": 9101,
            "type": 4,   # STOP → SL
            "side": 1,   # Sell (opposite of BUY entry)
            "status": 1,
        }
        matched = _try_capture_bracket_child(stop_order, _ACCT, rc)

        assert matched is True
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == "9101"
        assert pos["tp_order_id"] == "BRACKET"  # Not yet resolved

    def test_capture_long_tp(self):
        sl_id = "9101"
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        positions = {_SIG_ID: _open_position(sl=sl_id)}
        rc = _make_redis(positions=positions, pending=pending)

        limit_order = {
            "accountId": _ACCT,
            "id": 9102,
            "type": 1,   # LIMIT → TP
            "side": 1,   # Sell (opposite of BUY entry)
            "status": 1,
        }
        matched = _try_capture_bracket_child(limit_order, _ACCT, rc)

        assert matched is True
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == sl_id
        assert pos["tp_order_id"] == "9102"

    def test_pending_cleared_when_both_children_captured(self):
        """pending entry is HDEL'd once both SL and TP are resolved."""
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        positions = {_SIG_ID: _open_position(sl="9101")}  # SL already set
        rc = _make_redis(positions=positions, pending=pending)

        limit_order = {
            "accountId": _ACCT,
            "id": 9102,
            "type": 1,
            "side": 1,
            "status": 1,
        }
        _try_capture_bracket_child(limit_order, _ACCT, rc)

        assert _ENTRY_OID not in rc._pending_store

    def test_capture_short_sl_and_tp(self):
        """SELL entry: child orders have BUY side (side=0)."""
        pending = {_ENTRY_OID: _pending_entry("SELL")}
        positions = {_SIG_ID: _open_position()}
        rc = _make_redis(positions=positions, pending=pending)

        stop_order = {
            "accountId": _ACCT,
            "id": 9201,
            "type": 4,   # STOP → SL
            "side": 0,   # Buy (opposite of SELL entry)
            "status": 1,
        }
        matched = _try_capture_bracket_child(stop_order, _ACCT, rc)

        assert matched is True
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == "9201"


# ---------------------------------------------------------------------------
# 2. Race: bracket children arrive BEFORE TAKEN processed
# ---------------------------------------------------------------------------

class TestCaptureRaceOrderBeforePosition:
    """Children arrive before TAKEN; IDs staged in bracket:children:{acct}:{entry}."""

    def test_sl_staged_when_position_absent(self):
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        rc = _make_redis(positions={}, pending=pending)  # No position yet

        stop_order = {
            "accountId": _ACCT,
            "id": 9301,
            "type": 4,
            "side": 1,
            "status": 1,
        }
        matched = _try_capture_bracket_child(stop_order, _ACCT, rc)

        assert matched is True
        children_key = f"bracket:children:{_ACCT}:{_ENTRY_OID}"
        staged_raw = rc._children_store.get(children_key)
        assert staged_raw is not None
        staged = json.loads(staged_raw)
        assert staged["sl_order_id"] == "9301"
        assert "tp_order_id" not in staged

    def test_tp_staged_when_position_absent(self):
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        rc = _make_redis(positions={}, pending=pending)

        limit_order = {
            "accountId": _ACCT,
            "id": 9302,
            "type": 1,
            "side": 1,
            "status": 1,
        }
        _try_capture_bracket_child(limit_order, _ACCT, rc)

        children_key = f"bracket:children:{_ACCT}:{_ENTRY_OID}"
        staged = json.loads(rc._children_store[children_key])
        assert staged["tp_order_id"] == "9302"

    def test_handle_taken_skipped_applies_staged_ids(self):
        """_handle_taken_skipped reads bracket:children and replaces BRACKET sentinel."""
        children_key = f"bracket:children:{_ACCT}:{_ENTRY_OID}"
        staged_children = json.dumps({
            "sl_order_id": "9401",
            "tp_order_id": "9402",
        })

        # Build a mock Redis that returns staged children on .get()
        rc = MagicMock()
        rc.hset = MagicMock(return_value=1)
        rc.get = MagicMock(return_value=staged_children)
        rc.delete = MagicMock(return_value=1)

        orch = OnlineOrchestrator()

        taken_data = {
            "action": "TAKEN",
            "signal_id": _SIG_ID,
            "user_id": "primary_user",
            "asset": "ES",
            "direction": "BUY",
            "entry_price": "5500.00",
            "actual_entry_price": "5500.50",
            "contracts": 1,
            "tp_level": "5520.00",
            "sl_level": "5490.00",
            "point_value": "50",
            "risk_amount": "500",
            "account_id": _ACCT,
            "session": "NY",
            "regime_state": "TREND",
            "combined_modifier": "1.0",
            "aim_breakdown": "{}",
            "tsm_id": "TSM-001",
            "bracket": True,
            "entry_order_id": _ENTRY_OID,
            "sl_order_id": "BRACKET",
            "tp_order_id": "BRACKET",
        }

        with patch(
            "captain_online.blocks.orchestrator.get_redis_client",
            return_value=rc,
        ):
            orch._handle_taken_skipped(taken_data)

        # Staged children must be applied to the in-memory position
        assert len(orch.open_positions) == 1
        pos = orch.open_positions[0]
        assert pos["sl_order_id"] == "9401"
        assert pos["tp_order_id"] == "9402"

        # bracket:children key must be deleted after consumption
        rc.delete.assert_called_once_with(children_key)

    def test_handle_taken_skipped_partial_staged_ids(self):
        """Only sl staged; tp_order_id remains BRACKET in the position."""
        children_key = f"bracket:children:{_ACCT}:{_ENTRY_OID}"
        staged_children = json.dumps({"sl_order_id": "9501"})  # Only SL staged

        rc = MagicMock()
        rc.hset = MagicMock(return_value=1)
        rc.get = MagicMock(return_value=staged_children)
        rc.delete = MagicMock(return_value=1)

        orch = OnlineOrchestrator()

        taken_data = {
            "action": "TAKEN",
            "signal_id": _SIG_ID,
            "user_id": "primary_user",
            "asset": "NKD",
            "direction": "SELL",
            "entry_price": "38000",
            "contracts": 1,
            "tp_level": "37900",
            "sl_level": "38050",
            "point_value": "5",
            "risk_amount": "250",
            "account_id": _ACCT,
            "session": "APAC",
            "bracket": True,
            "entry_order_id": _ENTRY_OID,
            "sl_order_id": "BRACKET",
            "tp_order_id": "BRACKET",
        }

        with patch(
            "captain_online.blocks.orchestrator.get_redis_client",
            return_value=rc,
        ):
            orch._handle_taken_skipped(taken_data)

        pos = orch.open_positions[0]
        assert pos["sl_order_id"] == "9501"
        assert pos["tp_order_id"] == "BRACKET"  # Not staged — still sentinel


# ---------------------------------------------------------------------------
# 3. Timeout / stale pending
# ---------------------------------------------------------------------------

class TestCaptureTimeoutPurgesStale:
    """After TTL expiry the pending entry is gone; no mutation of open_positions."""

    def test_no_match_when_pending_empty(self):
        """Simulates post-TTL state: hgetall returns empty dict."""
        positions = {_SIG_ID: _open_position()}
        rc = _make_redis(positions=positions, pending={})  # TTL expired — empty

        stop_order = {
            "accountId": _ACCT,
            "id": 9601,
            "type": 4,
            "side": 1,
            "status": 1,
        }
        matched = _try_capture_bracket_child(stop_order, _ACCT, rc)

        assert matched is False
        # Position must be untouched
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == "BRACKET"

    def test_no_match_when_pending_hgetall_raises(self):
        """Redis error in hgetall → returns False, no exception propagates."""
        rc = MagicMock()
        rc.hgetall.side_effect = Exception("Redis timeout")

        stop_order = {
            "accountId": _ACCT,
            "id": 9602,
            "type": 4,
            "side": 1,
        }
        # Must not raise
        result = _try_capture_bracket_child(stop_order, _ACCT, rc)
        assert result is False


# ---------------------------------------------------------------------------
# 4. Non-bracket orders must not mutate open_positions
# ---------------------------------------------------------------------------

class TestNonBracketOrdersPassThrough:
    """Unrelated orders must not modify any position in captain:open_positions."""

    def test_market_order_ignored(self):
        """type=2 (Market) orders are skipped — not SL/TP children."""
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        positions = {_SIG_ID: _open_position()}
        rc = _make_redis(positions=positions, pending=pending)

        market_order = {
            "accountId": _ACCT,
            "id": 9701,
            "type": 2,   # Market — should be ignored
            "side": 0,
            "status": 1,
        }
        matched = _try_capture_bracket_child(market_order, _ACCT, rc)

        assert matched is False
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == "BRACKET"

    def test_wrong_account_ignored(self):
        """Order for a different account must not touch our positions."""
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        positions = {_SIG_ID: _open_position()}
        rc = _make_redis(positions=positions, pending=pending)

        stop_order = {
            "accountId": 99999,  # Different account
            "id": 9801,
            "type": 4,
            "side": 1,
            "status": 1,
        }
        matched = _try_capture_bracket_child(stop_order, _ACCT, rc)

        assert matched is False
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == "BRACKET"

    def test_wrong_side_ignored(self):
        """BUY entry child orders must have side=1 (Sell); side=0 is skipped."""
        pending = {_ENTRY_OID: _pending_entry("BUY")}
        positions = {_SIG_ID: _open_position()}
        rc = _make_redis(positions=positions, pending=pending)

        wrong_side_stop = {
            "accountId": _ACCT,
            "id": 9802,
            "type": 4,
            "side": 0,   # Buy side — wrong for a BUY entry
            "status": 1,
        }
        matched = _try_capture_bracket_child(wrong_side_stop, _ACCT, rc)

        assert matched is False
        pos = json.loads(rc._pos_store[_SIG_ID])
        assert pos["sl_order_id"] == "BRACKET"
