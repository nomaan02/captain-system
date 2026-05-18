"""External-close integration test: UserStream size=0 mid-trail.

When the broker reports a position size=0 (manual close, OCO leg fired,
margin call), captain-online's UserStream handler removes the position
from ``captain:open_positions`` and from ``self.open_positions``. The
trail loop then sees zero NKD positions and emits zero modifies — even
if subsequent polls fire.

The scan_nkd_trails contract is "operate on what you're given" — it does
NOT discover or remove positions itself. This test confirms the trail
behaves correctly when the caller (orchestrator) has already dropped the
position from its open list.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from captain_online.blocks import b7b_nkd_trail
from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails

NKD_POINT_VALUE = Decimal("5")


def _mark(pnl_dollars, entry=38000, contracts=1):
    return Decimal(str(entry)) + Decimal(str(pnl_dollars)) / (
        NKD_POINT_VALUE * Decimal(contracts))


def _position(signal_id="SIG-EXTCLOSE001"):
    return {
        "signal_id": signal_id, "user_id": "primary_user", "asset": "NKD",
        "direction": 1, "entry_price": Decimal("38000"),
        "contracts": 1, "tp_level": Decimal("38890"),
        "sl_level": Decimal("37650"),
        "point_value": NKD_POINT_VALUE,
        "account": "21855714", "session": 3,
        "bracket": True, "entry_order_id": "ENT-EXTCLOSE",
        "sl_order_id": 555_001, "tp_order_id": 555_002,
        "is_nkd_trail": True, "tp_dollars": Decimal("4450"),
        "snapped_d_init": Decimal("1750"),
        "jitter_x": None, "jitter_y": None, "jitter_j": None,
        "current_phase": None, "current_buffer": None,
        "current_stop_price": None, "modify_seq": 0,
    }


@pytest.fixture(autouse=True)
def _reset():
    b7b_nkd_trail._reset_state_for_tests()
    yield
    b7b_nkd_trail._reset_state_for_tests()


def _scan(positions, client, quote_price=None):
    if quote_price is None:
        quote_price = _mark(Decimal("2000"))
    return scan_nkd_trails(
        open_positions=positions, client=client, redis_client=None,
        quote_lookup=lambda _a, _c: (quote_price, 0.0),
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )


def test_empty_open_positions_emits_no_broker_calls():
    """No open positions → no modifies, no errors."""
    client = MagicMock()
    diag = _scan([], client=client)
    assert diag == []
    client.modify_order.assert_not_called()


def test_position_dropped_between_polls_emits_no_modify_after_drop():
    """Simulates orchestrator removing the position after UserStream size=0.

    Poll 1: position in list → modify fires.
    Poll 2: position removed (size=0) → empty list → no modify.
    """
    pos = _position()
    client = MagicMock()
    client.modify_order.return_value = {"success": True}

    # Poll 1: normal operation
    _scan([pos], client=client)
    assert client.modify_order.call_count == 1

    # Poll 2: orchestrator has dropped the position (e.g. UserStream got
    # size=0). scan_nkd_trails is called with the empty list.
    client.modify_order.reset_mock()
    _scan([], client=client)
    client.modify_order.assert_not_called()


def test_prev_pnl_purged_when_signal_no_longer_open():
    """Module-level prev_pnl cache should be purged for signals no longer
    in the open set, so a re-opened signal_id doesn't carry stale state."""
    pos = _position(signal_id="SIG-ORIG001")
    client = MagicMock()
    client.modify_order.return_value = {"success": True}

    # Poll 1: stage prev_pnl in the module cache
    _scan([pos], client=client)
    sig_id = "SIG-ORIG001"
    # Verify it's in the cache
    assert sig_id in b7b_nkd_trail._PREV_PNL_BY_SIGNAL

    # Poll 2: empty open_positions → purge happens
    _scan([], client=client)
    assert sig_id not in b7b_nkd_trail._PREV_PNL_BY_SIGNAL


def test_non_nkd_position_in_list_is_silently_skipped():
    """A non-NKD position in the same list (different asset) doesn't trigger
    the trail block — only `is_nkd_trail` positions are processed."""
    pos_nkd = _position(signal_id="SIG-NKD001")
    pos_es = {
        "signal_id": "SIG-ES001", "user_id": "primary_user", "asset": "ES",
        "direction": 1, "entry_price": Decimal("4500"),
        "contracts": 1, "tp_level": Decimal("4515"),
        "sl_level": Decimal("4490"),
        "account": "21855714",
        "bracket": True, "sl_order_id": 444_001, "tp_order_id": 444_002,
        "is_nkd_trail": False,  # explicitly NOT a trail
    }
    client = MagicMock()
    client.modify_order.return_value = {"success": True}
    diag = _scan([pos_nkd, pos_es], client=client)

    # Only one diagnostic row (for the NKD position)
    assert len(diag) == 1
    assert diag[0]["signal_id"] == "SIG-NKD001"
    # Only one broker call
    assert client.modify_order.call_count == 1
    # The ES position has not been mutated
    assert "current_phase" not in pos_es or pos_es.get("current_phase") is None
