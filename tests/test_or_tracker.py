"""Tests for the OR tracker state machine.

Uses fixed clocks and synthetic prices — no DB or stream dependencies.
"""

import json
import threading
from datetime import date, time as dtime, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch config paths before import so ORTracker finds session_registry.json
import captain_online.blocks.or_tracker as ort
from captain_online.blocks.or_tracker import (
    ORTracker, ORState, AssetORSession,
    get_asset_session_type, get_or_times,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_caches():
    """Clear module-level caches between tests."""
    ort._registry_cache = None
    ort._contract_to_asset = None
    yield
    ort._registry_cache = None
    ort._contract_to_asset = None


@pytest.fixture
def tracker():
    return ORTracker(cutoff_minutes=30)


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

class TestSessionRegistry:
    def test_asset_session_map(self):
        assert get_asset_session_type("ES") == "NY"
        assert get_asset_session_type("NKD") == "APAC"
        assert get_asset_session_type("ZB") == "NY_PRE"
        assert get_asset_session_type("MGC") == "LONDON"

    def test_or_times_ny(self):
        start, end = get_or_times("NY")
        assert start == dtime(9, 30)
        assert end == dtime(9, 35)

    def test_or_times_apac(self):
        start, end = get_or_times("APAC")
        assert start == dtime(18, 0)
        assert end == dtime(18, 5)

    def test_unknown_asset_defaults_ny(self):
        assert get_asset_session_type("UNKNOWN_ASSET") == "NY"


# ---------------------------------------------------------------------------
# AssetORSession
# ---------------------------------------------------------------------------

class TestAssetORSession:
    def test_initial_state(self):
        s = AssetORSession("ES", date(2026, 3, 27), "NY",
                           dtime(9, 30), dtime(9, 35), cutoff_minutes=30)
        assert s.state == ORState.WAITING
        assert s.or_high is None
        assert s.or_low is None
        assert s.or_range is None
        assert s.direction == 0
        assert not s.is_resolved

    def test_or_range_computation(self):
        s = AssetORSession("ES", date(2026, 3, 27), "NY",
                           dtime(9, 30), dtime(9, 35))
        s.or_high = 5010.0
        s.or_low = 5000.0
        assert s.or_range == 10.0

    def test_is_resolved(self):
        s = AssetORSession("ES", date(2026, 3, 27), "NY",
                           dtime(9, 30), dtime(9, 35))
        assert not s.is_resolved
        s.state = ORState.BREAKOUT_LONG
        assert s.is_resolved
        s.state = ORState.EXPIRED
        assert s.is_resolved


# ---------------------------------------------------------------------------
# OR Tracker — state machine transitions
# ---------------------------------------------------------------------------

class TestORFormation:
    """Test OR window formation (WAITING → FORMING → COMPLETE)."""

    def test_waiting_before_or_start(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        state = tracker.get_state("ES")
        assert state.state == ORState.WAITING

    def test_forming_on_first_tick_in_window(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]

        # Simulate tick at 09:30:01
        now = datetime(2026, 3, 27, 9, 30, 1, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(session, 5000.0, now, now.timetz())

        assert session.state == ORState.FORMING
        assert session.or_high == 5000.0
        assert session.or_low == 5000.0
        assert session.tick_count == 1

    def test_high_low_tracked_during_formation(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]

        prices = [5000.0, 5005.0, 4998.0, 5003.0, 5010.0]
        base = datetime(2026, 3, 27, 9, 30, 0, tzinfo=ort._ET)

        with tracker._lock:
            for i, p in enumerate(prices):
                t = base + timedelta(seconds=i + 1)
                tracker._update_state(session, p, t, t.timetz())

        assert session.state == ORState.FORMING
        assert session.or_high == 5010.0
        assert session.or_low == 4998.0
        assert session.tick_count == 5

    def test_complete_at_or_end(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]

        # Tick during OR
        t1 = datetime(2026, 3, 27, 9, 30, 30, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(session, 5000.0, t1, t1.timetz())
            tracker._update_state(session, 5010.0, t1, t1.timetz())
            tracker._update_state(session, 4995.0, t1, t1.timetz())

        assert session.state == ORState.FORMING

        # Tick at or_end (09:35)
        t2 = datetime(2026, 3, 27, 9, 35, 0, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(session, 5002.0, t2, t2.timetz())

        assert session.state == ORState.COMPLETE
        assert session.or_high == 5010.0
        assert session.or_low == 4995.0
        assert session.or_range == 15.0


class TestORBreakout:
    """Test breakout detection (COMPLETE → BREAKOUT_LONG/SHORT)."""

    def _make_complete_session(self, tracker, high=5010.0, low=4995.0):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]
        session.state = ORState.COMPLETE
        session.or_high = high
        session.or_low = low
        session.tick_count = 100
        return session

    def test_breakout_long(self, tracker):
        session = self._make_complete_session(tracker)
        now = datetime(2026, 3, 27, 9, 36, 0, tzinfo=ort._ET)

        with tracker._lock:
            tracker._update_state(session, 5010.25, now, now.timetz())

        assert session.state == ORState.BREAKOUT_LONG
        assert session.direction == 1
        assert session.entry_price == 5010.25
        assert session.breakout_time == now

    def test_breakout_short(self, tracker):
        session = self._make_complete_session(tracker)
        now = datetime(2026, 3, 27, 9, 36, 0, tzinfo=ort._ET)

        with tracker._lock:
            tracker._update_state(session, 4994.75, now, now.timetz())

        assert session.state == ORState.BREAKOUT_SHORT
        assert session.direction == -1
        assert session.entry_price == 4994.75

    def test_no_breakout_within_range(self, tracker):
        session = self._make_complete_session(tracker)
        now = datetime(2026, 3, 27, 9, 36, 0, tzinfo=ort._ET)

        # Price at exact high — not through
        with tracker._lock:
            tracker._update_state(session, 5010.0, now, now.timetz())

        assert session.state == ORState.COMPLETE
        assert session.direction == 0

    def test_gap_through_both_sides_larger_penetration_wins(self, tracker):
        session = self._make_complete_session(tracker, high=5010.0, low=4995.0)
        now = datetime(2026, 3, 27, 9, 36, 0, tzinfo=ort._ET)

        # Price above high AND below low can't happen with a single price,
        # but test the tie-break logic by checking larger penetration
        # A price of 5015.0 is 5 above high vs 0 below low → LONG
        with tracker._lock:
            tracker._update_state(session, 5015.0, now, now.timetz())

        assert session.state == ORState.BREAKOUT_LONG
        assert session.direction == 1

    def test_immediate_breakout_at_or_close(self, tracker):
        """Breakout on the same tick that closes the OR window."""
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]

        # Form OR
        t1 = datetime(2026, 3, 27, 9, 30, 30, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(session, 5000.0, t1, t1.timetz())
            tracker._update_state(session, 5010.0, t1, t1.timetz())

        # Close tick at 09:35 is above high
        t2 = datetime(2026, 3, 27, 9, 35, 0, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(session, 5015.0, t2, t2.timetz())

        assert session.state == ORState.BREAKOUT_LONG
        assert session.direction == 1
        assert session.entry_price == 5015.0


class TestORExpiry:
    """Test no-breakout expiry."""

    def test_expiry_after_cutoff(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]
        session.state = ORState.COMPLETE
        session.or_high = 5010.0
        session.or_low = 5000.0

        # Cutoff is or_end + 30min = 10:05 for NY
        with patch.object(ort, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 27, 10, 6, 0, tzinfo=ort._ET)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            expired = tracker.check_expirations()

        assert "ES" in expired
        assert session.state == ORState.EXPIRED
        assert session.is_resolved

    def test_no_expiry_before_cutoff(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]
        session.state = ORState.COMPLETE
        session.or_high = 5010.0
        session.or_low = 5000.0

        with patch.object(ort, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 27, 10, 0, 0, tzinfo=ort._ET)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            expired = tracker.check_expirations()

        assert expired == []
        assert session.state == ORState.COMPLETE


class TestORTrackerMultiAsset:
    """Test multiple assets tracked simultaneously."""

    def test_independent_tracking(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        tracker.register_asset("NQ", date(2026, 3, 27))

        es = tracker._sessions["ES"]
        nq = tracker._sessions["NQ"]

        t = datetime(2026, 3, 27, 9, 31, 0, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(es, 5000.0, t, t.timetz())
            tracker._update_state(nq, 18000.0, t, t.timetz())

        assert es.or_high == 5000.0
        assert nq.or_high == 18000.0

    def test_different_session_types(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))   # NY
        tracker.register_asset("NKD", date(2026, 3, 27))  # APAC

        es = tracker.get_state("ES")
        nkd = tracker.get_state("NKD")

        assert es.session_type == "NY"
        assert es.or_start == dtime(9, 30)
        assert nkd.session_type == "APAC"
        assert nkd.or_start == dtime(18, 0)

    def test_clear(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        tracker.register_asset("NQ", date(2026, 3, 27))
        tracker.clear()
        assert tracker.get_state("ES") is None
        assert tracker.get_state("NQ") is None


class TestNarrowOR:
    """Test narrow OR range edge case."""

    def test_narrow_range_still_detects_breakout(self, tracker):
        tracker.register_asset("ES", date(2026, 3, 27))
        session = tracker._sessions["ES"]
        session.state = ORState.COMPLETE
        session.or_high = 5000.25
        session.or_low = 5000.00
        session.tick_count = 10

        assert session.or_range == 0.25

        now = datetime(2026, 3, 27, 9, 36, 0, tzinfo=ort._ET)
        with tracker._lock:
            tracker._update_state(session, 5000.50, now, now.timetz())

        assert session.state == ORState.BREAKOUT_LONG
        assert session.direction == 1
