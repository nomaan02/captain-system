"""Stale-quote guard: quote_cache age > 30s aborts the modify pass.

NKD trail relies on a fresh broker mark to set the stop a fixed dollar
distance behind. If MarketStream has been silent for > 30 seconds (rapid-
fail CB tripped, WebSocket reconnect storm, market closed), the cached
``lastPrice`` no longer reflects the broker's real-time view and any
``/Order/modify`` placed against it would peg the stop at a stale price.

The trail block skips modify in this case AND publishes a CRITICAL alert
so the operator notices.

Spec: NKD_PIVOT_AUDIT.md §6.3.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from captain_online.blocks import b7b_nkd_trail
from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails

NKD_POINT_VALUE = Decimal("5")


def _mark(pnl_dollars, entry=38000):
    return Decimal(str(entry)) + Decimal(str(pnl_dollars)) / NKD_POINT_VALUE


def _position():
    return {
        "signal_id": "SIG-STALEQUOTE001", "user_id": "primary_user",
        "asset": "NKD", "direction": 1, "entry_price": Decimal("38000"),
        "contracts": 1, "tp_level": Decimal("38890"),
        "sl_level": Decimal("37650"),
        "point_value": NKD_POINT_VALUE,
        "account": "21855714", "session": 3,
        "bracket": True, "entry_order_id": "ENT-STALEQUOTE",
        "sl_order_id": 666_001, "tp_order_id": 666_002,
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


def test_quote_age_above_30s_skips_modify_and_emits_alert():
    pos = _position()
    client = MagicMock()
    client.modify_order.return_value = {"success": True}

    # Mock the redis_client so the CRITICAL alert publishes capturably
    redis_client = MagicMock()

    diag = scan_nkd_trails(
        open_positions=[pos], client=client, redis_client=redis_client,
        # quote_lookup reports age=45s (stale)
        quote_lookup=lambda _a, _c: (_mark(Decimal("2000")), 45.0),
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )

    # No broker call
    client.modify_order.assert_not_called()
    # Position state unchanged
    assert pos["current_stop_price"] is None
    assert pos["modify_seq"] == 0
    # Diagnostic row records the skip
    assert diag[0]["skip_reason"] == "stale_quote"
    # CRITICAL alert was published to captain:alerts
    redis_client.publish.assert_called_once()
    channel, payload = redis_client.publish.call_args[0]
    assert channel == "captain:alerts"
    import json as _json
    parsed = _json.loads(payload)
    assert parsed["priority"] == "CRITICAL"
    assert parsed["event_type"] == "NKD_TRAIL_STALE_QUOTE"


def test_quote_age_at_exactly_threshold_does_not_skip():
    """Threshold is strictly > 30s — exactly 30s still proceeds."""
    pos = _position()
    client = MagicMock()
    client.modify_order.return_value = {"success": True}

    scan_nkd_trails(
        open_positions=[pos], client=client, redis_client=None,
        quote_lookup=lambda _a, _c: (_mark(Decimal("2000")), 30.0),
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )
    client.modify_order.assert_called_once()


def test_quote_age_none_proceeds():
    """When age can't be parsed (no timestamp in cache), trail proceeds
    (the worst case is one stale-but-recent modify which the ratchet
    still prevents from harming)."""
    pos = _position()
    client = MagicMock()
    client.modify_order.return_value = {"success": True}
    scan_nkd_trails(
        open_positions=[pos], client=client, redis_client=None,
        quote_lookup=lambda _a, _c: (_mark(Decimal("2000")), None),
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )
    client.modify_order.assert_called_once()


def test_no_quote_at_all_skips_and_alerts():
    """When quote_lookup returns (None, _): treat as missing quote and skip."""
    pos = _position()
    client = MagicMock()
    redis_client = MagicMock()

    diag = scan_nkd_trails(
        open_positions=[pos], client=client, redis_client=redis_client,
        quote_lookup=lambda _a, _c: (None, None),
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )
    client.modify_order.assert_not_called()
    assert diag[0]["skip_reason"] == "no_quote"
    redis_client.publish.assert_called_once()
    import json as _json
    parsed = _json.loads(redis_client.publish.call_args[0][1])
    assert parsed["event_type"] == "NKD_TRAIL_NO_QUOTE"
