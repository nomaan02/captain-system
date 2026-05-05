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
