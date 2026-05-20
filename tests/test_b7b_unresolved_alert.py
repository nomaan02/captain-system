"""Q3-(3) B7B CRITICAL unresolved-SL alert tests (tests 20-23).

After 6 polls with sl_order_id still unresolved, _scan_one_trail publishes
a CRITICAL NKD_TRAIL_SL_UNRESOLVED alert exactly once per position lifetime.

Tower-safe: no pysignalr, scipy, or numpy deps.
"""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock

from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails
from shared.redis_client import CH_ALERTS

_NKD_POINT_VALUE = Decimal("5")


def _make_pos(sl_order_id="BRACKET", unresolved_poll_count=0,
              unresolved_alert_published=False):
    return {
        "signal_id": "SIG-ALERT-001",
        "user_id": "primary_user",
        "asset": "NKD",
        "direction": 1,
        "entry_price": Decimal("38000"),
        "contracts": 1,
        "account": "21855714",
        "entry_order_id": "ENT-202",
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
        "unresolved_alert_published": unresolved_alert_published,
    }


def _make_redis():
    """Redis mock that silently accepts hget (returns None → mirror skips)."""
    rc = MagicMock()
    rc.hget.return_value = None
    return rc


def _make_client(orders=None, raises=False):
    client = MagicMock()
    if raises:
        client.search_open_orders.side_effect = ConnectionError("timeout")
    else:
        client.search_open_orders.return_value = orders or []
    client.modify_order.return_value = {"success": True}
    return client


def _run_scan(pos, client=None, redis_client=None):
    if client is None:
        client = _make_client()
    if redis_client is None:
        redis_client = _make_redis()
    scan_nkd_trails(
        open_positions=[pos],
        client=client,
        redis_client=redis_client,
        quote_lookup=lambda asset, contract_id: (Decimal("38100"), 0.0),
        persist_d34=lambda row: None,
        compliance_modify_check=lambda *_: (True, None),
        parity_env="0",
    )


def _find_alert(redis_mock, event_type):
    """Return list of alert payloads matching event_type from redis.publish calls."""
    found = []
    for call_args in redis_mock.publish.call_args_list:
        payload_str = call_args[0][1]
        try:
            payload = json.loads(payload_str)
            if payload.get("event_type") == event_type:
                found.append(payload)
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
    return found


def test_unresolved_alert_fires_at_6_polls():
    """6 consecutive polls with BRACKET + no searchOpen match → CRITICAL alert published
    with event_type NKD_TRAIL_SL_UNRESOLVED and all 6 required fields."""
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=5)
    mock_redis = _make_redis()
    client = _make_client(orders=[])  # no match

    _run_scan(pos, client=client, redis_client=mock_redis)

    # count must be 6 after this poll
    assert pos.get("unresolved_poll_count") == 6, (
        f"Expected count=6; got {pos.get('unresolved_poll_count')}"
    )
    alerts = _find_alert(mock_redis, "NKD_TRAIL_SL_UNRESOLVED")
    assert len(alerts) == 1, (
        f"Expected exactly 1 NKD_TRAIL_SL_UNRESOLVED alert; got {len(alerts)}"
    )
    payload = alerts[0]
    assert payload.get("priority") == "CRITICAL"
    # _emit_alert merges extra dict into the root payload (no nested "data" key).
    # Verify all 6 required fields per audit Q3-(3).
    for field in ("position_id", "account_id", "entry_order_id",
                  "unresolved_poll_count", "time_unresolved_seconds", "pnl_dollars"):
        assert field in payload, f"Required field {field!r} missing from alert payload"
    assert payload["unresolved_poll_count"] == 6
    assert payload["time_unresolved_seconds"] == 60
    assert pos.get("unresolved_alert_published") is True


def test_unresolved_alert_does_not_repeat():
    """Alert publishes once; subsequent polls with the flag set do NOT republish."""
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=6,
                    unresolved_alert_published=True)
    mock_redis = _make_redis()
    client = _make_client(orders=[])

    # Run two more polls — alert must not fire again
    _run_scan(pos, client=client, redis_client=mock_redis)
    _run_scan(pos, client=client, redis_client=mock_redis)

    alerts = _find_alert(mock_redis, "NKD_TRAIL_SL_UNRESOLVED")
    assert len(alerts) == 0, (
        f"Alert must not repeat after unresolved_alert_published=True; got {len(alerts)}"
    )


def test_unresolved_resolves_after_alert():
    """After alert fired, searchOpen finds match → resolved, poll_count reset, no duplicate alert."""
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=6,
                    unresolved_alert_published=True)

    orders = [
        {"id": 999001, "type": 4, "side": 1, "contractId": None, "parentId": "ENT-202"},
    ]
    client = _make_client(orders=orders)
    mock_redis = _make_redis()

    _run_scan(pos, client=client, redis_client=mock_redis)

    assert pos["sl_order_id"] == "999001", (
        "sl_order_id must resolve via searchOpen even after alert was published"
    )
    assert pos.get("unresolved_poll_count") == 0, (
        "unresolved_poll_count must reset to 0 after resolution"
    )
    # The flag is reset too so operator knows the situation self-healed
    assert pos.get("unresolved_alert_published") is False, (
        "unresolved_alert_published must reset to False after sl resolution"
    )
    # No duplicate alert published in this poll
    alerts = _find_alert(mock_redis, "NKD_TRAIL_SL_UNRESOLVED")
    assert len(alerts) == 0, (
        f"No new alert should fire in the resolving poll; got {len(alerts)}"
    )


def test_unresolved_state_persists_across_restart():
    """unresolved_poll_count and unresolved_alert_published are written to Redis mirror.

    _mirror_position_to_redis is called only when the scan COMPLETES (sl resolved).
    We simulate a position that was previously unresolved (count=6, alert published)
    but now has a real sl_order_id. After the scan, the mirror must include both
    new fields so a process restart sees the saved state.
    """
    import json as _json

    # Position was previously unresolved but is now resolved (sl_order_id set).
    pos = _make_pos(sl_order_id="BRACKET", unresolved_poll_count=5,
                    unresolved_alert_published=False)
    # Simulate searchOpen resolving it on this poll (count=6 >= 3, searchOpen fires).
    orders = [
        {"id": 777001, "type": 4, "side": 1, "contractId": None, "parentId": "ENT-202"},
    ]

    # Build a redis mock that captures hset and returns existing position on hget.
    captured_writes: dict = {}

    def _fake_hset(redis_key, field, value):
        captured_writes[field] = value

    mock_redis = MagicMock()
    existing_data = {
        **{k: str(v) if isinstance(v, Decimal) else v for k, v in pos.items()},
    }
    mock_redis.hget.return_value = _json.dumps(existing_data, default=str).encode()
    mock_redis.hset.side_effect = _fake_hset

    client = _make_client(orders=orders)

    _run_scan(pos, client=client, redis_client=mock_redis)

    # After searchOpen resolution the scan completes and mirror is written.
    assert mock_redis.hset.called, (
        "_mirror_position_to_redis must call redis.hset after sl_order_id is resolved"
    )
    sig_id = pos["signal_id"]
    written_raw = captured_writes.get(sig_id)
    assert written_raw is not None, f"No hset for signal_id={sig_id!r}"
    written = _json.loads(written_raw if isinstance(written_raw, str)
                          else written_raw.decode())
    assert "unresolved_poll_count" in written, (
        "unresolved_poll_count must be persisted to Redis mirror"
    )
    assert "unresolved_alert_published" in written, (
        "unresolved_alert_published must be persisted to Redis mirror"
    )
    # After resolution the count resets to 0.
    assert written["unresolved_poll_count"] == 0
