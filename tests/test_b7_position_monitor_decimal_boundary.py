"""Regression test for Bug C (2026-04-30 09:44 ET):

    File "b7_position_monitor.py", line 236, in monitor_positions
        tp_distance = abs(tp - current_price) / tp_range if tp_range > 0 else 1.0
    TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'

ROOT CAUSE
----------
Position state (tp_level, sl_level, entry_price, risk_amount) flows through
Redis stream payloads via parse_json_decimal / loads_decimal — comes back as
Decimal-typed. current_price comes from the live quote stream (TopstepX) as
float. Any Decimal-vs-float arithmetic in monitor_positions or
monitor_shadow_positions tripped TypeError at every poll.

Bug C is the third sister-bug after:
  * Bug A round 1 (b4_kelly_sizing) — fixed in 4c225c0 on 2026-04-29
  * Bug A round 2 (b6_signal_output) — fixed in 1910f71 on 2026-04-30 AM
  * Bug C (b7_position_monitor + b7_shadow_monitor) — fixed today

The monitor_positions inner loop runs every 10s and was outside the audit
scope of the earlier fixes (which targeted D08 reads + signal output).

FIX
---
Coerce all position price fields via shared.decimal_boundary.as_money once
at the top of each loop iteration. Use Decimal end-to-end for arithmetic
and comparisons; convert to float only when notifying / passing exit_price
to resolve_position (which already coerces internally via _money_d).

Producer side (orchestrator._handle_taken_skipped) also coerces all
monetary fields when constructing the position dict so the open_positions
list is type-pure end-to-end.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_d00_point_value():
    """Stub _resolve_point_value so tests don't hit QuestDB."""
    from captain_online.blocks import b7_position_monitor
    with patch.object(
        b7_position_monitor, "_resolve_point_value",
        return_value=Decimal("50"),
    ):
        yield


@pytest.fixture
def stub_live_price_float():
    """Stub _get_live_price to return a float (mimics live quote stream)."""
    def _make(price_value: float):
        from captain_online.blocks import b7_position_monitor
        return patch.object(
            b7_position_monitor, "_get_live_price",
            return_value=price_value,
        )
    return _make


@pytest.fixture(autouse=True)
def stub_side_effect_writers(monkeypatch):
    """Stub write paths so monitor_positions doesn't touch Redis / QuestDB."""
    from captain_online.blocks import b7_position_monitor as mod

    monkeypatch.setattr(mod, "_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_check_vix_spike", lambda pos: None)
    monkeypatch.setattr(mod, "_regime_shift_detected",
                        lambda asset, regime: False)
    monkeypatch.setattr(mod, "_parse_close_time", lambda hours: None)
    yield


def _decimal_position(**overrides):
    """Position dict with Decimal monetary fields (Phase A migrated state)."""
    base = {
        "signal_id": "SIG-TEST",
        "user_id": "primary_user",
        "asset": "MES",
        "direction": 1,
        "contracts": 3,
        "entry_price": Decimal("4500.00"),
        "tp_level": Decimal("4505.00"),
        "sl_level": Decimal("4498.00"),
        "risk_amount": Decimal("30.00"),
        "point_value": Decimal("5"),
        "account": "AC1",
        "session": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Bug C regression: monitor_positions with Decimal/float mixing
# ---------------------------------------------------------------------------

class TestMonitorPositionsDecimalBoundary:
    """The exact failure mode from NY open 2026-04-30 09:44 ET."""

    def test_decimal_tp_with_float_current_price_no_typeerror(
        self, stub_d00_point_value, stub_live_price_float
    ):
        """monitor_positions must not TypeError on Decimal tp + float current_price."""
        from captain_online.blocks.b7_position_monitor import monitor_positions

        pos = _decimal_position()
        # Live quote stream returns float — exactly the production shape
        with stub_live_price_float(4501.50):
            resolved = monitor_positions([pos], tsm_configs={})

        # No TypeError + position not yet at TP/SL
        assert resolved == []
        assert "current_pnl" in pos
        assert isinstance(pos["current_pnl"], float)

    def test_decimal_tp_hit_resolves_correctly(
        self, stub_d00_point_value, stub_live_price_float, monkeypatch
    ):
        """Decimal tp + float current_price >= tp -> TP_HIT path triggers."""
        from captain_online.blocks import b7_position_monitor as mod
        from captain_online.blocks.b7_position_monitor import monitor_positions

        resolved_calls = []
        monkeypatch.setattr(
            mod, "resolve_position",
            lambda pos, outcome, exit_price, tsm: resolved_calls.append(
                (pos["asset"], outcome, exit_price)
            ),
        )

        pos = _decimal_position()  # tp = Decimal("4505.00")
        # current_price (float) crosses tp
        with stub_live_price_float(4505.25):
            resolved = monitor_positions([pos], tsm_configs={})

        assert len(resolved_calls) == 1
        assert resolved_calls[0][1] == "TP_HIT"
        # exit_price passed to resolve_position must be float (not Decimal)
        assert isinstance(resolved_calls[0][2], float)
        assert resolved_calls[0][2] == 4505.25
        assert len(resolved) == 1

    def test_decimal_sl_hit_short_position(
        self, stub_d00_point_value, stub_live_price_float, monkeypatch
    ):
        """SHORT position + Decimal sl + float current_price >= sl -> SL_HIT."""
        from captain_online.blocks import b7_position_monitor as mod
        from captain_online.blocks.b7_position_monitor import monitor_positions

        resolved_calls = []
        monkeypatch.setattr(
            mod, "resolve_position",
            lambda pos, outcome, exit_price, tsm: resolved_calls.append(
                (pos["asset"], outcome, exit_price)
            ),
        )

        # Realistic SHORT: TP below entry, SL above entry
        pos = _decimal_position(
            direction=-1,
            tp_level=Decimal("4495.00"),
            sl_level=Decimal("4502.00"),
        )
        # SHORT SL_HIT when price rises above sl (4502.50 >= sl=4502)
        with stub_live_price_float(4502.50):
            monitor_positions([pos], tsm_configs={})

        assert len(resolved_calls) == 1
        assert resolved_calls[0][1] == "SL_HIT"

    def test_proximity_alert_does_not_typeerror(
        self, stub_d00_point_value, stub_live_price_float, monkeypatch
    ):
        """TP proximity check (within 10% of TP) computes Decimal arithmetic correctly."""
        from captain_online.blocks import b7_position_monitor as mod
        from captain_online.blocks.b7_position_monitor import monitor_positions

        notifications = []
        monkeypatch.setattr(
            mod, "_notify",
            lambda user_id, priority, msg: notifications.append((priority, msg)),
        )

        pos = _decimal_position()  # entry=4500, tp=4505 (range=5)
        # current_price = 4504.6 -> tp_distance = (4505-4504.6)/5 = 0.08 < 0.10
        with stub_live_price_float(4504.60):
            monitor_positions([pos], tsm_configs={})

        # Should fire the HIGH proximity alert
        high_alerts = [n for n in notifications if n[0] == "HIGH"]
        assert len(high_alerts) == 1
        assert "TP approaching" in high_alerts[0][1]

    def test_pnl_pct_correct_with_decimal_risk_amount(
        self, stub_d00_point_value, stub_live_price_float
    ):
        """pnl_pct must be float (for downstream % calcs) and arithmetically correct."""
        from captain_online.blocks.b7_position_monitor import monitor_positions

        # entry=4500, current=4502, direction=1, contracts=3, pv=50
        # gross = (4502-4500) * 1 * 3 * 50 = 300
        # pnl_pct = 300 / 30 = 10.0
        pos = _decimal_position()
        with stub_live_price_float(4502.0):
            monitor_positions([pos], tsm_configs={})

        assert isinstance(pos["pnl_pct"], float)
        assert pos["pnl_pct"] == pytest.approx(10.0, rel=1e-6)


class TestMonitorPositionsMixedTypeDicts:
    """Defensive: even if a producer regresses to type-mixed dict, we don't crash."""

    def test_float_tp_with_decimal_entry_price(
        self, stub_d00_point_value, stub_live_price_float
    ):
        """Mixed: tp=float, entry_price=Decimal, current_price=float."""
        from captain_online.blocks.b7_position_monitor import monitor_positions
        pos = _decimal_position(tp_level=4505.0)  # float tp
        with stub_live_price_float(4501.0):
            monitor_positions([pos], tsm_configs={})
        # No TypeError; current_pnl present
        assert "current_pnl" in pos

    def test_int_zero_risk_amount(
        self, stub_d00_point_value, stub_live_price_float
    ):
        """risk_amount=0 must not divide-by-zero — pnl_pct=0.0."""
        from captain_online.blocks.b7_position_monitor import monitor_positions
        pos = _decimal_position(risk_amount=0)
        with stub_live_price_float(4501.0):
            monitor_positions([pos], tsm_configs={})
        assert pos["pnl_pct"] == 0.0


# ---------------------------------------------------------------------------
# Bug C regression: monitor_shadow_positions same shape
# ---------------------------------------------------------------------------

class TestMonitorShadowPositionsDecimalBoundary:
    """Same Bug C fix applied to b7_shadow_monitor."""

    def test_decimal_tp_no_typeerror_on_shadow(self, monkeypatch):
        from captain_online.blocks import b7_shadow_monitor as mod
        from captain_online.blocks.b7_shadow_monitor import monitor_shadow_positions

        monkeypatch.setattr(mod, "_get_live_price", lambda asset: 4505.25)
        # Stub _resolve_shadow so we don't hit publish path
        resolved_calls = []
        monkeypatch.setattr(
            mod, "_resolve_shadow",
            lambda shadow, outcome, exit_price: resolved_calls.append((outcome, exit_price)),
        )

        from datetime import datetime, timezone
        shadow = {
            "signal_id": "SHADOW-TEST",
            "user_id": "primary_user",
            "asset": "MES",
            "direction": 1,
            "tp_level": Decimal("4505.00"),
            "sl_level": Decimal("4498.00"),
            "entry_price": Decimal("4500.00"),
            "contracts": 3,
            "point_value": Decimal("5"),
            "created_at": datetime.now(timezone.utc),
            "resolved": False,
        }
        # No TypeError + TP_HIT triggers (current=4505.25 >= tp=4505.00)
        monitor_shadow_positions([shadow])
        assert len(resolved_calls) == 1
        assert resolved_calls[0][0] == "TP_HIT"
        assert isinstance(resolved_calls[0][1], float)


class TestInferEntryDecimalBoundary:
    """_infer_entry must work with Decimal tp/sl from Redis."""

    def test_decimal_tp_sl_returns_float(self):
        from captain_online.blocks.b7_shadow_monitor import _infer_entry
        signal = {
            "tp_level": Decimal("4505.00"),
            "sl_level": Decimal("4498.00"),
            "direction": 1,
        }
        result = _infer_entry(signal)
        assert isinstance(result, float)
        # entry = sl + (tp-sl)/3 = 4498 + 7/3 = ~4500.33
        assert result == pytest.approx(4500.333, rel=1e-3)
