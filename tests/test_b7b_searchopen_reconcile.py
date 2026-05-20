"""Q3-(2) B7B searchOpen reconciliation tests (tests 17-19).

After 3 unresolved polls of sl_order_id="BRACKET", _scan_one_trail calls
client.search_open_orders to recover the child order IDs.

Tower-safe: no pysignalr, scipy, or numpy deps.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails

_NKD_POINT_VALUE = Decimal("5")


def _make_pos(sl_order_id="BRACKET", unresolved_poll_count=0):
    return {
        "signal_id": "SIG-SREC-001",
        "user_id": "primary_user",
        "asset": "NKD",
        "direction": 1,
        "entry_price": Decimal("38000"),
        "contracts": 1,
        "account": "21855714",
        "entry_order_id": "ENT-101",
        "sl_order_id": sl_order_id,
        "tp_order_id": "BRACKET",
        "is_nkd_trail": True,
        "tp_dollars": Decimal("4450"),
        "snapped_d_init": Decimal("1025"),
        "jitter_j": Decimal("0"),
        "jitter_x": Decimal("0"),
        "jitter_y": 0,
        "current_phase": None,
        "current_buffer": None,
        "current_stop_price": None,
        "modify_seq": 0,
        "session": 3,
        "unresolved_poll_count": unresolved_poll_count,
        "unresolved_alert_published": False,
    }


def _run_scan(pos, client=None, redis_client=None):
    if client is None:
        client = MagicMock()
        client.modify_order.return_value = {"success": True}
    # PnL=500 → Phase A, mark = entry + 100 pts
    mark = Decimal("38100")
    scan_nkd_trails(
        open_positions=[pos],
        client=client,
        redis_client=redis_client,
        quote_lookup=lambda asset, contract_id: (mark, 0.0),
        persist_d34=lambda row: None,
        compliance_modify_check=lambda *_: (True, None),
        parity_env="0",
    )


def test_searchopen_reconcile_after_drop():
    """After 3 prior unresolved polls, searchOpen returns matching SL+TP →
    sl_order_id is resolved and unresolved_poll_count resets to 0.

    Poll 4 (unresolved_poll_count starts at 3, increments to 4 ≥ 3) is the
    first scan in this test; the mock returns matching children.
    """
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=3)

    # SL = type 4 (STOP), side=1 (SELL) for LONG; TP = type 1 (LIMIT), side=1 (SELL)
    orders = [
        {"id": 888001, "type": 4, "side": 1, "contractId": None, "parentId": "ENT-101"},
        {"id": 888002, "type": 1, "side": 1, "contractId": None, "parentId": "ENT-101"},
    ]
    client = MagicMock()
    client.search_open_orders.return_value = orders
    client.modify_order.return_value = {"success": True}

    _run_scan(pos, client=client)

    assert pos["sl_order_id"] == "888001", (
        f"sl_order_id must be resolved to '888001' via searchOpen; got {pos['sl_order_id']!r}"
    )
    assert pos["tp_order_id"] == "888002", (
        f"tp_order_id must be resolved to '888002' via searchOpen; got {pos['tp_order_id']!r}"
    )
    assert pos.get("unresolved_poll_count") == 0, (
        f"unresolved_poll_count must reset to 0 after SL resolution; got {pos.get('unresolved_poll_count')}"
    )
    assert client.search_open_orders.called, (
        "client.search_open_orders must be called when poll_count >= 3"
    )


def test_searchopen_no_match():
    """searchOpen returns empty list → unresolved_poll_count increments; no exception."""
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=3)

    client = MagicMock()
    client.search_open_orders.return_value = []
    client.modify_order.return_value = {"success": True}

    _run_scan(pos, client=client)

    assert pos.get("unresolved_poll_count") == 4, (
        f"unresolved_poll_count must increment to 4; got {pos.get('unresolved_poll_count')}"
    )
    assert pos["sl_order_id"] == "BRACKET", (
        "sl_order_id must remain BRACKET when no match found"
    )


def test_searchopen_exception_handled():
    """searchOpen raises ConnectionError → caught and logged; counter still increments."""
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=3)

    client = MagicMock()
    client.search_open_orders.side_effect = ConnectionError("network timeout")
    client.modify_order.return_value = {"success": True}

    _run_scan(pos, client=client)  # must not raise

    assert pos.get("unresolved_poll_count") == 4, (
        f"counter must increment even when searchOpen raises; got {pos.get('unresolved_poll_count')}"
    )
    assert pos["sl_order_id"] == "BRACKET", (
        "sl_order_id must remain BRACKET when searchOpen raises"
    )
    assert client.search_open_orders.called, (
        "search_open_orders must have been attempted"
    )
