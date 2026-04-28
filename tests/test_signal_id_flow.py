"""Phase 7 — Tests for signal_id flow B6 → Command → B7 → D03.

The orchestrator already persisted ``signal_id`` into the in-memory
position dict in earlier work; this batch adds the SignalSink seam
to B6 and threads ``signal_id`` into the D03 INSERT performed by B7.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from captain_online.blocks import b6_signal_output, b7_position_monitor
from captain_online.blocks.b6_signal_output import _publish_signals
from shared.online_replay_providers import CapturingSignalSink


# --------------------------------------------------------------------------- #
# Signal envelope                                                             #
# --------------------------------------------------------------------------- #


def test_run_signal_output_accepts_signal_sink_kwarg():
    sig = inspect.signature(b6_signal_output.run_signal_output)
    assert "signal_sink" in sig.parameters
    assert sig.parameters["signal_sink"].default is None


# --------------------------------------------------------------------------- #
# _publish_signals                                                            #
# --------------------------------------------------------------------------- #


def test_publish_signals_routes_through_supplied_sink():
    sink = CapturingSignalSink()
    sigs = [{
        "signal_id": "SIG-1", "asset": "ES", "direction": 1, "size": 1,
        "tp_level": 100.0, "sl_level": 99.0,
        "timestamp": "2026-01-15T09:30:00",
    }]
    _publish_signals("u1", sigs, [], 1, signal_sink=sink)
    captured = sink.captured()
    assert len(captured) == 1
    assert captured[0]["user_id"] == "u1"
    assert captured[0]["session_id"] == 1
    assert captured[0]["signals"][0]["signal_id"] == "SIG-1"


def test_publish_signals_does_not_use_redis_when_sink_supplied():
    """When signal_sink is supplied, publish_to_stream is bypassed."""
    sink = CapturingSignalSink()
    sigs = [{
        "signal_id": "SIG-1", "asset": "ES", "direction": 1, "size": 1,
        "tp_level": 100.0, "sl_level": 99.0,
        "timestamp": "2026-01-15T09:30:00",
    }]
    with patch.object(b6_signal_output, "publish_to_stream") as mock_pub:
        _publish_signals("u1", sigs, [], 1, signal_sink=sink)
    mock_pub.assert_not_called()
    assert len(sink.captured()) == 1


def test_publish_signals_default_uses_redis_publish_to_stream():
    """No sink → falls back to live publish_to_stream."""
    sigs = [{
        "signal_id": "SIG-2", "asset": "ES", "direction": 1, "size": 1,
        "tp_level": 100.0, "sl_level": 99.0,
        "timestamp": "2026-01-15T09:30:00",
    }]
    with patch.object(b6_signal_output, "publish_to_stream") as mock_pub:
        _publish_signals("u2", sigs, [], 1)
    mock_pub.assert_called_once()
    args, _ = mock_pub.call_args
    channel, payload = args
    assert channel == b6_signal_output.STREAM_SIGNALS
    assert payload["user_id"] == "u2"


# --------------------------------------------------------------------------- #
# B7 D03 writer                                                               #
# --------------------------------------------------------------------------- #


def test_b7_write_trade_outcome_accepts_signal_id():
    sig = inspect.signature(b7_position_monitor._write_trade_outcome)
    assert "signal_id" in sig.parameters
    assert sig.parameters["signal_id"].default is None


def test_b7_writes_signal_id_into_d03_insert():
    """When _write_trade_outcome receives a signal_id, the INSERT carries it."""
    captured_sql_args = {}

    def _capture(sql, args=None):
        captured_sql_args["sql"] = sql
        captured_sql_args["args"] = args

    cursor = MagicMock()
    cursor.execute.side_effect = _capture
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False
    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx):
        b7_position_monitor._write_trade_outcome(
            trade_id="TRD-1",
            user_id="u1", account_id="a1", asset="ES", direction=1,
            entry_price=100.0, signal_entry_price=100.0, exit_price=101.0,
            contracts=1, gross_pnl=50.0, commission=2.0, net_pnl=48.0,
            slippage=None, outcome="TP",
            entry_time=None, regime_at_entry="LOW_VOL",
            aim_modifier=1.0, aim_breakdown=None, session=1, tsm_used="0",
            signal_id="SIG-EXACT",
        )
    assert "signal_id" in captured_sql_args["sql"]
    assert "SIG-EXACT" in captured_sql_args["args"]


def test_b7_falls_back_to_legacy_id_when_signal_id_missing():
    captured_args: dict = {}

    def _capture(sql, args=None):
        captured_args["args"] = args

    cursor = MagicMock()
    cursor.execute.side_effect = _capture
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False
    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx):
        b7_position_monitor._write_trade_outcome(
            trade_id="TRD-1",
            user_id="u1", account_id="a1", asset="ES", direction=1,
            entry_price=100.0, signal_entry_price=100.0, exit_price=101.0,
            contracts=1, gross_pnl=50.0, commission=2.0, net_pnl=48.0,
            slippage=None, outcome="TP",
            entry_time=None, regime_at_entry=None,
            aim_modifier=1.0, aim_breakdown=None, session=1, tsm_used="0",
            # signal_id intentionally omitted
        )
    args = captured_args["args"]
    sig_id_in_args = next((a for a in args if isinstance(a, str) and
                            a.startswith("LEGACY-")), None)
    assert sig_id_in_args is not None, (
        f"expected LEGACY-* fallback in INSERT args, got: {args}"
    )
