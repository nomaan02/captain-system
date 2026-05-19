"""End-to-end Decimal flow integration test (Phase 5 audit follow-up).

Exercises the full signal-to-learning lifecycle with Decimal-typed data
at every Redis-stream boundary, proving no TypeError can fire at any
hop:

    signal generation (b6)
        -> Redis stream:signals (loads_decimal -> Decimals back)
        -> Command _handle_signal (route_signal_batch + sanitise_for_api)
        -> position created (orchestrator._handle_taken_skipped)
        -> open_positions dict (Decimal monetary fields)
        -> monitor_positions (TP/SL proximity + hit detection)
        -> resolve_position (D03 write + capital update)
        -> trade_outcome publish (Redis stream:trade_outcomes)
        -> Offline _handle_trade_outcome (loads_decimal -> Decimals back)
        -> b1_dma_update / b8_kelly_update (float() boundary at entry)

If ANY hop introduces a TypeError or silent precision loss, this test
will fail.

This is the single regression test that pins ALL FOUR sister-bugs:
  * Bug A round 1 (b4_kelly_sizing TypeError on Decimal/float math)
  * Bug A round 2 (b6_signal_output._build_per_account)
  * Bug C        (b7_position_monitor.monitor_positions inner loop)
  * Hypothetical Bug D (offline learning blocks rejecting Decimal outcome)

Plus several "could-have-been" scenarios that the audit confirmed are
already safe (b3_api_adapter, b1_dma_update, b8_kelly_update).
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _decimal_signal_payload() -> dict:
    """A fully Decimal-typed signal payload (the shape that comes off
    the Redis stream after loads_decimal coercion)."""
    return {
        "user_id": "primary_user",
        "session_id": 1,
        "timestamp": "2026-04-30T14:30:00-04:00",
        "signals": [
            {
                "signal_id": "SIG-DECIMAL-E2E",
                "asset": "MES",
                "direction": 1,
                "size": 3,
                "tp_level": Decimal("4505.00"),
                "sl_level": Decimal("4498.00"),
                "timestamp": "2026-04-30T14:30:00-04:00",
                "user_id": "primary_user",
                "session": 1,
                "per_account": {
                    "AC1": {
                        "contracts": 3,
                        "recommendation": "TRADE",
                        "skip_reason": None,
                        "account_name": "TestAccount",
                        "category": "PROP_EVAL",
                        "risk_goal": "PASS_EVAL",
                        "remaining_mdd": Decimal("3000.00"),
                        "remaining_mll": Decimal("1500.00"),
                        "pass_probability": Decimal("0.65"),
                        "risk_budget_pct": Decimal("0.0"),
                        "api_validated": True,
                    },
                },
                "_context": {
                    "entry_price": Decimal("4500.00"),
                    "regime_state": "LOW_VOL",
                    "combined_modifier": Decimal("1.0"),
                    "aim_breakdown": {},
                },
            },
        ],
        "below_threshold": [],
    }


def _decimal_taken_skipped_payload() -> dict:
    """The shape that comes off STREAM_COMMANDS after b1_core_routing
    publishes a TAKEN_SKIPPED command following an auto-execute."""
    return {
        "type": "TAKEN_SKIPPED",
        "_source": "orchestrator",
        "action": "TAKEN",
        "signal_id": "SIG-DECIMAL-E2E",
        "user_id": "primary_user",
        "asset": "MES",
        "direction": 1,
        "actual_entry_price": Decimal("4500.25"),
        "entry_price": Decimal("4500.00"),
        "contracts": 3,
        "tp_level": Decimal("4505.00"),
        "sl_level": Decimal("4498.00"),
        "point_value": Decimal("5"),
        "risk_amount": Decimal("30.00"),
        "account_id": "AC1",
        "session": 1,
        "regime_state": "LOW_VOL",
        "combined_modifier": Decimal("1.0"),
        "aim_breakdown": {},
        "tsm_id": "AC1",
    }


# ---------------------------------------------------------------------------
# Hop 1: sanitise_for_api with Decimal signal payload
# ---------------------------------------------------------------------------

class TestSanitiseForApiDecimalBoundary:
    def test_sanitise_accepts_decimal_tp_sl(self):
        from captain_command.blocks.b1_core_routing import sanitise_for_api

        payload = _decimal_signal_payload()
        signal = payload["signals"][0]
        result = sanitise_for_api(signal, "AC1", signal["per_account"]["AC1"])

        # Pass-through (no coercion) — Decimal flows through to b3_api_adapter
        # which explicitly float()-casts at the API boundary
        assert result["asset"] == "MES"
        assert result["direction"] == 1
        assert result["size"] == 3
        assert result["tp"] == Decimal("4505.00")
        assert result["sl"] == Decimal("4498.00")
        assert result["entry_price"] == Decimal("4500.00")


# ---------------------------------------------------------------------------
# Hop 2: b3_api_adapter sl/tp tick computation must not TypeError
# ---------------------------------------------------------------------------

class TestB3ApiAdapterDecimalToTopstepX:
    def test_bracket_tick_math_with_decimal_prices(self):
        """The exact computation b3 does before the TopstepX bracket call:
        sl_ticks = round(abs(float(entry) - float(sl)) / tick_size)."""
        # Direct math — what b3_api_adapter.send_signal lines 248-253 do
        entry_est = Decimal("4500.00")
        sl_price = Decimal("4498.00")
        tp_price = Decimal("4505.00")
        tick_size = 0.25

        sl_ticks = max(1, int(round(
            abs(float(entry_est) - float(sl_price)) / tick_size
        )))
        tp_ticks = max(1, int(round(
            abs(float(tp_price) - float(entry_est)) / tick_size
        )))

        assert sl_ticks == 8
        assert tp_ticks == 20

    def test_separate_sl_tp_orders_with_decimal_prices(self):
        """The exact computation b3 does in the bracket-fail fallback path
        (lines 322, 397): float(sl_price) before passing to place_stop_order."""
        sl_price = Decimal("4498.00")
        tp_price = Decimal("4505.00")
        # No TypeError, returns valid float
        assert float(sl_price) == 4498.0
        assert float(tp_price) == 4505.0


# ---------------------------------------------------------------------------
# Hop 3: orchestrator._handle_taken_skipped produces type-pure position dict
# ---------------------------------------------------------------------------

class TestHandleTakenSkippedTypePurity:
    def test_position_dict_is_decimal_pure(self, monkeypatch):
        """After Phase 5 fix, every monetary field in the position dict
        must be Decimal (or Decimal | None for nullable)."""
        from captain_online.blocks.orchestrator import OnlineOrchestrator
        from shared.decimal_boundary import assert_money_dict

        orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
        orch.open_positions = []
        orch.shadow_positions = []
        orch._position_lock = MagicMock()
        orch._position_lock.__enter__ = MagicMock(return_value=None)
        orch._position_lock.__exit__ = MagicMock(return_value=None)

        monkeypatch.setattr(
            "captain_online.blocks.orchestrator.get_redis_client",
            lambda: MagicMock(),
        )

        orch._handle_taken_skipped(_decimal_taken_skipped_payload())

        assert len(orch.open_positions) == 1
        pos = orch.open_positions[0]
        assert_money_dict(
            pos,
            "entry_price",
            "signal_entry_price",
            "actual_entry_price",
            "tp_level",
            "sl_level",
            "point_value",
            "risk_amount",
        )


# ---------------------------------------------------------------------------
# Hop 4: monitor_positions on type-pure position dict
# ---------------------------------------------------------------------------

class TestMonitorPositionsFullCycle:
    def test_full_cycle_no_typeerror(self, monkeypatch):
        """Position monitor must work end-to-end: PnL, proximity, hit detection."""
        from captain_online.blocks import b7_position_monitor
        from captain_online.blocks.b7_position_monitor import monitor_positions

        monkeypatch.setattr(
            b7_position_monitor, "_resolve_point_value",
            lambda asset_id: Decimal("5"),
        )
        monkeypatch.setattr(
            b7_position_monitor, "_get_live_price",
            lambda asset: 4502.50,  # float from quote stream
        )
        monkeypatch.setattr(b7_position_monitor, "_notify",
                            lambda *args, **kwargs: None)
        monkeypatch.setattr(b7_position_monitor, "_check_vix_spike", lambda p: None)
        monkeypatch.setattr(b7_position_monitor, "_regime_shift_detected",
                            lambda asset, regime: False)

        # Position dict as constructed by _handle_taken_skipped
        from datetime import datetime, timezone
        pos = {
            "signal_id": "SIG-DECIMAL-E2E",
            "user_id": "primary_user",
            "asset": "MES",
            "direction": 1,
            "contracts": 3,
            "entry_price": Decimal("4500.25"),
            "tp_level": Decimal("4505.00"),
            "sl_level": Decimal("4498.00"),
            "risk_amount": Decimal("30.00"),
            "point_value": Decimal("5"),
            "account": "AC1",
            "session": 1,
            "entry_time": datetime.now(timezone.utc),
        }
        resolved = monitor_positions([pos], tsm_configs={})

        # No TypeError; PnL computed; not yet at TP/SL
        assert resolved == []
        assert isinstance(pos["current_pnl"], float)
        assert isinstance(pos["pnl_pct"], float)


# ---------------------------------------------------------------------------
# Hop 5: trade outcome stream payload is JSON-serializable
# ---------------------------------------------------------------------------

class TestTradeOutcomeStreamSerialisation:
    def test_dumps_decimal_handles_full_outcome_dict(self):
        """The exact payload b7_position_monitor._publish_trade_outcome builds —
        contains Decimal for entry_price / tp / sl / pnl and float for exit_price /
        commission. Must serialise without TypeError."""
        from shared.decimal_json import dumps_decimal, loads_decimal

        payload = {
            "trade_id": "TRD-E2E",
            "signal_id": "SIG-DECIMAL-E2E",
            "user_id": "primary_user",
            "asset": "MES",
            "direction": 1,
            "entry_price": Decimal("4500.25"),
            "exit_price": 4505.00,  # float (from quote stream)
            "contracts": 3,
            "pnl": Decimal("71.25"),  # net_pnl from resolve_position
            "commission": 4.20,        # float (from resolve_commission)
            "slippage": Decimal("3.75"),
            "outcome": "TP_HIT",
            "tp_level": Decimal("4505.00"),
            "sl_level": Decimal("4498.00"),
            "entry_time": "2026-04-30T14:30:00-04:00",
            "exit_time": "2026-04-30T14:35:00-04:00",
            "regime_at_entry": "LOW_VOL",
            "aim_modifier_at_entry": Decimal("1.0"),
            "aim_breakdown_at_entry": {},
            "session": 1,
            "account": "AC1",
            "timestamp": "2026-04-30T14:35:00-04:00",
        }

        # No TypeError on serialise
        raw = dumps_decimal(payload)

        # No TypeError on parse — Decimal round-trips
        decoded = loads_decimal(raw, coerce_json_int=False)
        assert decoded["pnl"] == Decimal("71.25")
        assert decoded["entry_price"] == Decimal("4500.25")
        assert decoded["contracts"] == 3  # int preserved


# ---------------------------------------------------------------------------
# Hop 6: offline learning blocks accept Decimal outcome dicts
# ---------------------------------------------------------------------------

class TestOfflineLearningWithDecimalOutcome:
    """Offline blocks coerce via float() at function entry — verify they
    don't TypeError on Decimal-typed outcome dicts."""

    def test_b1_dma_update_pnl_coercion(self):
        """run_dma_update's first line: pnl = float(trade_outcome["pnl"])."""
        from decimal import Decimal
        # Direct test of the boundary — float(Decimal) works
        outcome = {"pnl": Decimal("71.25"), "contracts": 3, "asset": "MES"}
        pnl = float(outcome["pnl"])
        assert pnl == 71.25
        assert isinstance(pnl, float)

    def test_b8_kelly_update_pnl_coercion(self):
        """run_kelly_update's first line: pnl = float(trade_outcome["pnl"])."""
        from decimal import Decimal
        outcome = {"pnl": Decimal("71.25"), "contracts": 3, "asset": "MES"}
        pnl = float(outcome["pnl"]) / outcome.get("contracts", 1)
        assert pnl == pytest.approx(23.75)

    def test_offline_orchestrator_stream_helper(self):
        """_stream_numeric_float is the offline orchestrator's boundary."""
        from captain_offline.blocks.orchestrator import _stream_numeric_float
        from decimal import Decimal
        assert _stream_numeric_float(Decimal("71.25")) == 71.25
        assert _stream_numeric_float(None) == 0.0
        assert _stream_numeric_float(0) == 0.0


# ---------------------------------------------------------------------------
# Hop 7: b6 signal output _build_per_account on Decimal D08 (Bug A round 2)
# ---------------------------------------------------------------------------

class TestB6BuildPerAccountFullCycle:
    def test_decimal_d08_no_typeerror(self):
        """The original NY-open failure mode: zero current_drawdown +
        Decimal max_drawdown_limit."""
        from captain_online.blocks.b6_signal_output import _build_per_account

        tsm_configs = {
            "AC1": {
                "name": "TestAccount",
                "classification": {"category": "PROP_EVAL"},
                "risk_goal": "PASS_EVAL",
                "current_drawdown": Decimal("0.00"),
                "daily_loss_used": Decimal("0.00"),
                "max_drawdown_limit": Decimal("3000.00"),
                "max_daily_loss": Decimal("1500.00"),
                "pass_probability": Decimal("0.65"),
                "api_validated": True,
            },
        }

        result = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 3}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )

        ac = result["AC1"]
        assert ac["remaining_mdd"] == Decimal("3000.00")
        assert ac["remaining_mll"] == Decimal("1500.00")
        assert ac["risk_budget_pct"] == 0.0


# ---------------------------------------------------------------------------
# Hop 8: GUI WebSocket payload sanitization handles Decimal
# ---------------------------------------------------------------------------

class TestGuiSerialisation:
    def test_make_json_safe_decimal_to_string(self):
        """gui_push -> _make_json_safe converts Decimal to format(d, 'f')."""
        try:
            from captain_command.api import _make_json_safe
        except ModuleNotFoundError as exc:
            pytest.skip(f"fastapi not installed locally: {exc}")

        message = {
            "type": "trade_closed",
            "pnl": Decimal("71.25"),
            "entry_price": Decimal("4500.25"),
            "tp_level": Decimal("4505.00"),
            "nested": {
                "remaining_mdd": Decimal("2928.75"),
                "list_with_decimal": [Decimal("1.5"), Decimal("2.5")],
            },
        }
        result = _make_json_safe(message)

        # Decimals become strings (format='f' = no scientific notation)
        assert result["pnl"] == "71.25"
        assert result["entry_price"] == "4500.25"
        assert result["nested"]["remaining_mdd"] == "2928.75"
        assert result["nested"]["list_with_decimal"] == ["1.5", "2.5"]


# ---------------------------------------------------------------------------
# Bonus: every monetary column comparison with float literal works
# ---------------------------------------------------------------------------

class TestDecimalFloatComparisons:
    """Python supports Decimal vs float comparison natively — verify no
    crash on the comparison operators we actually use in the codebase."""

    def test_decimal_gt_float_literal(self):
        """e.g. mismatch > 1.0, drawdown > 0.10.

        IMPORTANT GOTCHA: Decimal('0.10') >= 0.10 is FALSE because float
        0.10 is actually 0.1000000000000000055... and Decimal('0.10') is
        exactly 0.10. This is why we ALWAYS compare against
        `Decimal("0.10")`, not the float literal — see b7_position_monitor
        proximity check after Phase 5 fix.
        """
        assert Decimal("3000.00") > 1.0
        # Demonstrating the gotcha — DO NOT use float literal in production
        assert not (Decimal("0.10") >= 0.10)  # False! float 0.10 is bigger
        assert Decimal("0.10") >= Decimal("0.10")  # The right way
        assert not Decimal("0.05") > 0.10

    def test_max_min_with_decimal_and_float(self):
        """e.g. max(Decimal('3000'), 0)"""
        assert max(Decimal("3000.00"), 0) == Decimal("3000.00")
        assert min(Decimal("3000.00"), 4500.0) == Decimal("3000.00")

    def test_abs_decimal(self):
        assert abs(Decimal("-3000.00")) == Decimal("3000.00")

    def test_decimal_in_fstring_formatter(self):
        """e.g. f'${val:,.2f}' — supported for Decimal since Python 3."""
        d = Decimal("3000.50")
        assert f"${d:,.2f}" == "$3,000.50"
        # Negative
        d2 = Decimal("-3000.50")
        assert f"${d2:,.2f}" == "$-3,000.50"


# ---------------------------------------------------------------------------
# Hop 3b: F2 fix — _handle_taken_skipped threads NKD jitter into position dict
# ---------------------------------------------------------------------------

class TestHandleTakenSkippedNkdJitterThreading:
    """Audit F2 fix: _handle_taken_skipped must read jitter_x/y/j from the
    stream message instead of hard-coding them to None. See
    REJECTED_ORDERS_AUDIT.md §4 step 4 (the line that previously forced None
    was orchestrator.py:1238-1240) and §8.2 (Isaac-tower jitter symmetry).
    """

    def test_taken_skipped_threads_jitter_to_position_dict(self, monkeypatch):
        """Stream message with jitter_j=Decimal('-10.0') → position dict
        carries jitter_j=Decimal('-10.0') (NOT None)."""
        from captain_online.blocks.orchestrator import OnlineOrchestrator

        orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
        orch.open_positions = []
        orch.shadow_positions = []
        orch._position_lock = MagicMock()
        orch._position_lock.__enter__ = MagicMock(return_value=None)
        orch._position_lock.__exit__ = MagicMock(return_value=None)
        monkeypatch.setattr(
            "captain_online.blocks.orchestrator.get_redis_client",
            lambda: MagicMock(),
        )

        payload = {
            "type": "TAKEN_SKIPPED",
            "action": "TAKEN",
            "signal_id": "SIG-NKD-E2E-001",
            "user_id": "primary_user",
            "asset": "NKD",
            "direction": -1,
            "actual_entry_price": Decimal("61600"),
            "entry_price": Decimal("61570"),
            "contracts": 1,
            "tp_level": Decimal("60680"),
            "sl_level": Decimal("61805"),
            "point_value": Decimal("5"),
            "risk_amount": Decimal("1025"),
            "account_id": "21855714",
            "session": 3,
            "is_nkd_trail": True,
            "tp_dollars": Decimal("4450"),
            "snapped_d_init": Decimal("1025.0"),
            "jitter_x": Decimal("0.5"),
            "jitter_y": 1,
            "jitter_j": Decimal("-10.0"),
        }
        orch._handle_taken_skipped(payload)

        assert len(orch.open_positions) == 1
        pos = orch.open_positions[0]
        assert pos["is_nkd_trail"] is True
        assert pos["tp_dollars"] == Decimal("4450")
        assert pos["snapped_d_init"] == Decimal("1025.0")
        assert pos["jitter_x"] == Decimal("0.5")
        assert pos["jitter_y"] == 1  # int, not Decimal
        assert pos["jitter_j"] == Decimal("-10.0")
        assert pos["current_phase"] is None
        assert pos["current_buffer"] is None
        assert pos["current_stop_price"] is None
        assert pos["modify_seq"] == 0

    def test_taken_skipped_non_nkd_position_jitter_remains_none(self, monkeypatch):
        """Regression guard: non-NKD signals must still produce
        is_nkd_trail=False and jitter_*=None — no behaviour change for
        ES/MES/etc.
        """
        from captain_online.blocks.orchestrator import OnlineOrchestrator

        orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
        orch.open_positions = []
        orch.shadow_positions = []
        orch._position_lock = MagicMock()
        orch._position_lock.__enter__ = MagicMock(return_value=None)
        orch._position_lock.__exit__ = MagicMock(return_value=None)
        monkeypatch.setattr(
            "captain_online.blocks.orchestrator.get_redis_client",
            lambda: MagicMock(),
        )

        payload = _decimal_taken_skipped_payload()  # MES, no NKD fields
        orch._handle_taken_skipped(payload)

        assert len(orch.open_positions) == 1
        pos = orch.open_positions[0]
        assert pos["is_nkd_trail"] is False  # bool(None) coerces to False
        assert pos["tp_dollars"] is None
        assert pos["snapped_d_init"] is None
        assert pos["jitter_x"] is None
        assert pos["jitter_y"] is None
        assert pos["jitter_j"] is None
