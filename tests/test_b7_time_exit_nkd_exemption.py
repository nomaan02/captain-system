"""Tests for C9 — TIME_EXIT NKD exemption in b7_position_monitor.monitor_positions.

NKD positions (or positions with is_nkd_trail=True) must NEVER be force-closed
by the TIME_EXIT path, even when the wall-clock is past the session close_time.

This exemption exists because NKD pivot trades span 22 hours across APAC/NY/LON
session boundaries. It also acts as a critical safety net: if audit candidate I11
(_parse_close_time returning None on dict-form trading_hours) is ever fixed,
NKD would be silently force-flattened WITHOUT this exemption.

Tests use unittest.mock to:
- Patch _get_live_price to return a stable quote
- Patch _resolve_point_value to return NKD's point_value=5.0
- Patch datetime.now to simulate wall-clock past close_time
- Patch _parse_close_time to return a close_time in the past
- Patch resolve_position to track calls (the "did we flatten?" oracle)
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo
import pytest

import captain_online.blocks.b7_position_monitor as b7


def _make_pos(asset="NKD", is_nkd_trail=True, account="21855714", user_id="primary_user"):
    """Minimal position dict sufficient to trigger the time-exit code path."""
    return {
        "asset": asset,
        "is_nkd_trail": is_nkd_trail,
        "account": account,
        "user_id": user_id,
        "direction": 1,
        "entry_price": Decimal("38000"),
        "tp_level": Decimal("38890"),
        "sl_level": Decimal("37750"),
        "size": 1,
        "signal_id": "SIG-TESTABCDEF",
        "bracket": True,
    }


def _make_tsm_no_overnight(account="21855714"):
    """TSM config that normally triggers TIME_EXIT (overnight_allowed=False)."""
    return {
        account: {
            "overnight_allowed": False,
            "trading_hours": "09:30-16:00",
        }
    }


def _past_close_time():
    """Returns a datetime representing 2 minutes before 'now' (i.e. close_time already passed)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).astimezone() + timedelta(minutes=-2)


class TestNKDExemptedFromTimeExit:
    """NKD positions survive the TIME_EXIT check regardless of wall-clock."""

    def _run_monitor_with_mocked_time(self, pos, tsm):
        """Shared test helper that stubs out all IO and time-related functions."""
        # Provide a live price that does NOT trigger TP or SL (price between sl and tp)
        mid_price = float((pos["tp_level"] + pos["sl_level"]) / 2)

        past_close = datetime.now(ZoneInfo("America/New_York")) - timedelta(minutes=2)

        with (
            patch.object(b7, "_get_live_price", return_value=mid_price),
            patch.object(b7, "_resolve_point_value", return_value=Decimal("5.0")),
            patch.object(b7, "_parse_close_time", return_value=past_close),
            patch.object(b7, "resolve_position") as mock_resolve,
            patch.object(b7, "_notify"),
            patch.object(b7, "_resolve_exchange_exit_price", return_value=None),
        ):
            resolved = b7.monitor_positions([pos], tsm)

        return resolved, mock_resolve

    def test_nkd_position_not_flattened_at_time_exit(self):
        """NKD position survives past close_time — no TIME_EXIT resolve call."""
        pos = _make_pos(asset="NKD", is_nkd_trail=True)
        tsm = _make_tsm_no_overnight()
        resolved, mock_resolve = self._run_monitor_with_mocked_time(pos, tsm)

        assert resolved == [], "NKD position must not appear in resolved list (no force-close)"
        mock_resolve.assert_not_called()

    def test_nkd_asset_name_alone_exempts_even_without_trail_flag(self):
        """asset=='NKD' alone is sufficient to exempt — trail flag optional."""
        pos = _make_pos(asset="NKD", is_nkd_trail=False)
        tsm = _make_tsm_no_overnight()
        resolved, mock_resolve = self._run_monitor_with_mocked_time(pos, tsm)

        assert resolved == []
        mock_resolve.assert_not_called()

    def test_is_nkd_trail_flag_alone_exempts_any_asset(self):
        """is_nkd_trail=True exempts even if asset name differs (future APAC asset)."""
        pos = _make_pos(asset="SOME_FUTURE_APAC", is_nkd_trail=True)
        tsm = _make_tsm_no_overnight(account="21855714")
        resolved, mock_resolve = self._run_monitor_with_mocked_time(pos, tsm)

        assert resolved == []
        mock_resolve.assert_not_called()


class TestNonNKDPositionStillFlattened:
    """Negative control: non-NKD positions ARE still closed by TIME_EXIT."""

    def test_mgc_position_flattened_past_close_time(self):
        """MGC (LON session) is force-closed when close_time has passed."""
        pos = _make_pos(asset="MGC", is_nkd_trail=False)
        # Price between TP and SL so TP/SL don't fire
        pos["tp_level"] = Decimal("2900")
        pos["sl_level"] = Decimal("2800")
        mid_price = 2850.0
        past_close = datetime.now(ZoneInfo("America/New_York")) - timedelta(minutes=2)

        tsm = _make_tsm_no_overnight()
        with (
            patch.object(b7, "_get_live_price", return_value=mid_price),
            patch.object(b7, "_resolve_point_value", return_value=Decimal("10.0")),
            patch.object(b7, "_parse_close_time", return_value=past_close),
            patch.object(b7, "resolve_position") as mock_resolve,
            patch.object(b7, "_notify"),
            patch.object(b7, "_resolve_exchange_exit_price", return_value=None),
        ):
            resolved = b7.monitor_positions([pos], tsm)

        mock_resolve.assert_called_once()
        call_args = mock_resolve.call_args
        assert call_args[0][1] == "TIME_EXIT"

    def test_es_position_not_flattened_when_no_close_time(self):
        """ES with overnight_allowed=True is not touched by TIME_EXIT."""
        pos = _make_pos(asset="ES", is_nkd_trail=False)
        pos["tp_level"] = Decimal("5100")
        pos["sl_level"] = Decimal("5000")
        mid_price = 5050.0

        tsm = {"21855714": {"overnight_allowed": True}}
        with (
            patch.object(b7, "_get_live_price", return_value=mid_price),
            patch.object(b7, "_resolve_point_value", return_value=Decimal("50.0")),
            patch.object(b7, "_parse_close_time", return_value=None),
            patch.object(b7, "resolve_position") as mock_resolve,
            patch.object(b7, "_notify"),
            patch.object(b7, "_resolve_exchange_exit_price", return_value=None),
        ):
            resolved = b7.monitor_positions([pos], tsm)

        mock_resolve.assert_not_called()
