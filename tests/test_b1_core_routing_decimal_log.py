"""Regression test for b1_core_routing._log_signal_received Decimal serialisation.

Failure mode (2026-05-05 LON open, MGC SIG-66D2424516E4):
    [COMMAND] ERROR captain_command.blocks.b1_core_routing:
        Failed to log signal SIG-66D2424516E4: Object of type Decimal is
        not JSON serializable

Cause: signal dict contains Decimal values (entry_price, tp_level, sl_level,
quality_score, size) post Phase A migration. json.dumps does not handle
Decimal. dumps_decimal does.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from shared.decimal_json import loads_decimal


def _decimal_signal() -> dict:
    """Mirror the runtime payload shape from b6_signal_output."""
    return {
        "signal_id": "SIG-DECIMAL-TEST",
        "user_id": "primary_user",
        "asset": "MGC",
        "direction": "BUY",
        "size": 5,
        "tp_level": Decimal("4568.5"),
        "sl_level": Decimal("4561.6"),
        "_context": {
            "entry_price": Decimal("4563.9"),
            "confidence_tier": "MEDIUM",
            "quality_score": Decimal("0.82"),
        },
    }


def test_log_signal_received_does_not_typeerror_on_decimal_signal(monkeypatch):
    """The failure mode that lost SIG-66D2424516E4's audit row this morning."""
    from captain_command.blocks import b1_core_routing

    captured = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(b1_core_routing, "get_cursor", lambda: _FakeCursor())

    signal = _decimal_signal()
    b1_core_routing._log_signal_received(
        signal["signal_id"], signal["user_id"], signal,
    )

    assert "params" in captured, (
        "INSERT was never executed — _log_signal_received fell into the "
        "bare-except branch (likely a TypeError on Decimal serialisation)."
    )
    details_json = captured["params"][5]
    parsed = loads_decimal(details_json)
    assert parsed["entry_price"] == Decimal("4563.9")
    assert parsed["tp_level"] == Decimal("4568.5")
    assert parsed["sl_level"] == Decimal("4561.6")
    assert parsed["quality_score"] == Decimal("0.82")
    assert parsed["size"] == Decimal("5")  # int -> Decimal via loads_decimal default


def test_log_trade_confirmation_does_not_typeerror_on_decimal_actual_entry(monkeypatch):
    """Same risk pattern at the second hot path (line 477)."""
    from captain_command.blocks import b1_core_routing

    captured = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["params"] = params

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(b1_core_routing, "get_cursor", lambda: _FakeCursor())

    data = {
        "asset": "MES",
        "account_id": "21855714",
        "contracts": 5,
        "actual_entry_price": Decimal("5825.50"),
    }
    b1_core_routing._log_trade_confirmation("SIG-TEST", "primary_user", "TAKEN", data)

    assert "params" in captured, "INSERT path did not execute — Decimal regressed."
    parsed = loads_decimal(captured["params"][5])
    assert parsed["actual_entry_price"] == Decimal("5825.50")


def test_route_command_taken_preserves_nkd_trail_fields(monkeypatch):
    """Audit F3 fix: the manual GUI TAKEN path must forward all 6 NKD
    trail-control fields onto STREAM_COMMANDS so b7b_nkd_trail engages
    even when a NKD signal is taken manually via the GUI (not auto-execute).
    See REJECTED_ORDERS_AUDIT.md §0 F3, §7 Option B.
    """
    from captain_command.blocks import b1_core_routing

    captured: dict = {}

    def _fake_publish(stream, data):
        captured["stream"] = stream
        captured["data"] = data
        return "1-0"

    monkeypatch.setattr(b1_core_routing, "publish_to_stream", _fake_publish)
    monkeypatch.setattr(
        b1_core_routing, "_log_trade_confirmation",
        lambda *_args, **_kw: None,
    )

    data = {
        "type": "TAKEN_SKIPPED",
        "action": "TAKEN",
        "signal_id": "SIG-NKD-MANUAL-001",
        "user_id": "primary_user",
        "asset": "NKD",
        "direction": -1,
        "actual_entry_price": 61600,
        "entry_price": 61570,
        "contracts": 1,
        "tp_level": 60680,
        "sl_level": 61805,
        "account_id": "21855714",
        "session": 3,
        "bracket": True,
        "entry_order_id": "ENT-NKD-001",
        "is_nkd_trail": True,
        "tp_dollars": 4450,
        "snapped_d_init": 1025.0,
        "jitter_x": 0.5,
        "jitter_y": 1,
        "jitter_j": 10.0,
    }
    b1_core_routing.route_command(data, gui_push_fn=lambda *_a, **_kw: None)

    assert "data" in captured, "publish_to_stream was never called"
    msg = captured["data"]
    assert msg["type"] == "TAKEN_SKIPPED"
    assert msg["action"] == "TAKEN"
    assert msg["asset"] == "NKD"
    assert msg["is_nkd_trail"] is True
    assert msg["tp_dollars"] == 4450
    assert msg["snapped_d_init"] == 1025.0
    assert msg["jitter_x"] == 0.5
    assert msg["jitter_y"] == 1
    assert msg["jitter_j"] == 10.0


def test_route_command_taken_non_nkd_signal_has_none_nkd_keys(monkeypatch):
    """Defensive: GUI clients that do not yet ship the 6 NKD keys must not
    cause KeyError or change behaviour for ES/MES/etc. — the 6 keys default
    to None on STREAM_COMMANDS, and downstream _handle_taken_skipped will
    coerce them harmlessly.
    """
    from captain_command.blocks import b1_core_routing

    captured: dict = {}

    def _fake_publish(stream, data):
        captured["data"] = data
        return "1-0"

    monkeypatch.setattr(b1_core_routing, "publish_to_stream", _fake_publish)
    monkeypatch.setattr(
        b1_core_routing, "_log_trade_confirmation",
        lambda *_args, **_kw: None,
    )

    data = {
        "type": "TAKEN_SKIPPED",
        "action": "TAKEN",
        "signal_id": "SIG-ES-MANUAL-001",
        "user_id": "primary_user",
        "asset": "ES",
        "direction": 1,
        "contracts": 2,
        "tp_level": 6443.20,
        "sl_level": 6460.53,
        "account_id": "20319784",
    }
    b1_core_routing.route_command(data, gui_push_fn=lambda *_a, **_kw: None)

    msg = captured["data"]
    assert msg["asset"] == "ES"
    assert msg["is_nkd_trail"] is None
    assert msg["tp_dollars"] is None
    assert msg["snapped_d_init"] is None
    assert msg["jitter_x"] is None
    assert msg["jitter_y"] is None
    assert msg["jitter_j"] is None
