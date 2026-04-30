"""Phase 2 regression: b8_reconciliation handles Decimal/float mismatch + loud failure.

Two protections being verified:

1. The mismatch comparison `abs(broker_balance - system_balance) > 1.00`
   no longer trips TypeError when broker returns float (typical API
   response) and system_balance is Decimal (post-Phase-A D08).

2. The except path is no longer silent — it logs CRITICAL with full
   traceback and pushes a GUI alert so reconciliation failures surface
   before the next session.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def captured_gui():
    pushes = []
    def push(user_id, msg):
        pushes.append((user_id, msg))
    return push, pushes


class TestDecimalBoundaryMismatch:
    def test_broker_float_vs_decimal_system_balance_no_typeerror(
        self, captured_gui, monkeypatch
    ):
        """broker float + system Decimal → mismatch computed as Decimal, no error."""
        from captain_command.blocks import b8_reconciliation as b8

        push_fn, pushes = captured_gui
        monkeypatch.setattr(b8, "_update_account_balance", lambda ac_id, v: None)
        monkeypatch.setattr(b8, "_log_reconciliation",
                            lambda *args, **kwargs: None)

        broker_status = {"balance": 149_500.00}  # float (typical API)
        system = {"current_balance": Decimal("150000.00")}  # Decimal (Phase A)
        get_broker = lambda ac_id: broker_status

        b8._reconcile_api_account(
            ac_id="AC1", user_id="u1", ac=system,
            get_broker_status_fn=get_broker, gui_push_fn=push_fn,
        )

        assert len(pushes) == 1
        msg = pushes[0][1]
        assert msg["priority"] == "MEDIUM"
        assert msg["source"] == "RECONCILIATION"
        assert "$150,000.00" in msg["message"]
        assert "$149,500.00" in msg["message"]
        assert "$500.00" in msg["message"]

    def test_no_correction_when_within_one_dollar(self, captured_gui, monkeypatch):
        """Mismatch < $1.00 → no auto-correction, no GUI push."""
        from captain_command.blocks import b8_reconciliation as b8

        push_fn, pushes = captured_gui
        monkeypatch.setattr(b8, "_update_account_balance", lambda ac_id, v: None)
        monkeypatch.setattr(b8, "_log_reconciliation", lambda *a, **k: None)

        broker_status = {"balance": Decimal("150000.50")}
        system = {"current_balance": Decimal("150000.00")}
        get_broker = lambda ac_id: broker_status

        b8._reconcile_api_account(
            ac_id="AC1", user_id="u1", ac=system,
            get_broker_status_fn=get_broker, gui_push_fn=push_fn,
        )

        # No GUI push for the mismatch (< $1.00 threshold)
        assert len(pushes) == 0

    def test_none_broker_balance_returns_silently(self, captured_gui, monkeypatch):
        from captain_command.blocks import b8_reconciliation as b8
        push_fn, pushes = captured_gui
        broker_status = {"balance": None}
        system = {"current_balance": Decimal("150000.00")}
        get_broker = lambda ac_id: broker_status

        b8._reconcile_api_account(
            ac_id="AC1", user_id="u1", ac=system,
            get_broker_status_fn=get_broker, gui_push_fn=push_fn,
        )
        assert len(pushes) == 0


class TestLoudFailurePath:
    """The bare-except previously hid every reconciliation failure for weeks."""

    def test_broker_call_failure_logs_critical_and_alerts_gui(
        self, captured_gui, monkeypatch, caplog
    ):
        from captain_command.blocks import b8_reconciliation as b8

        push_fn, pushes = captured_gui
        def boom(ac_id):
            raise RuntimeError("broker API timeout")

        with caplog.at_level(logging.CRITICAL):
            b8._reconcile_api_account(
                ac_id="AC1", user_id="u1", ac={"current_balance": Decimal("150000.00")},
                get_broker_status_fn=boom, gui_push_fn=push_fn,
            )

        # CRITICAL log emitted
        critical_records = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert len(critical_records) >= 1
        assert "CRITICAL reconciliation failure" in critical_records[0].message
        assert "AC1" in critical_records[0].message

        # GUI alert pushed
        assert len(pushes) == 1
        alert = pushes[0][1]
        assert alert["priority"] == "CRITICAL"
        assert alert["source"] == "RECONCILIATION_FAILURE"
        assert "AC1" in alert["message"]

    def test_alert_push_failure_does_not_re_raise(
        self, monkeypatch, caplog
    ):
        from captain_command.blocks import b8_reconciliation as b8

        def boom(ac_id):
            raise RuntimeError("broker API timeout")
        def gui_explodes(user_id, msg):
            raise RuntimeError("GUI socket closed")

        with caplog.at_level(logging.ERROR):
            # Should not propagate either exception
            b8._reconcile_api_account(
                ac_id="AC1", user_id="u1", ac={"current_balance": Decimal("150000.00")},
                get_broker_status_fn=boom, gui_push_fn=gui_explodes,
            )
        # Both failures recorded
        assert any("CRITICAL reconciliation failure" in r.message for r in caplog.records)
        assert any("failed to push reconciliation-failure alert" in r.message for r in caplog.records)
