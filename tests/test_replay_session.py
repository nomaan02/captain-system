"""Phase 7 — Tests for shared.online_replay driver (Layer 2 + Layer 3).

Covers ``OnlineReplayContext``, ``replay_session``, ``replay_reset``,
``default_reset_hooks``, ``captain_online_replay``.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from shared.online_replay import (
    OnlineReplayContext,
    ReplayParameters,
    ReplayResult,
    captain_online_replay,
    default_reset_hooks,
    replay_reset,
    replay_session,
)
from shared.online_replay_providers import (
    CapturingSignalSink,
    FixedTimeProvider,
    HistoricalMarketDataProvider,
)

_ET = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# Hooks                                                                       #
# --------------------------------------------------------------------------- #


def test_default_reset_hooks_includes_b5c_reset():
    hooks = default_reset_hooks()
    assert len(hooks) >= 1
    # Sanity: each hook is callable
    for h in hooks:
        assert callable(h)


def test_replay_reset_invokes_each_hook():
    calls = []
    hooks = [
        lambda: calls.append("a"),
        lambda: calls.append("b"),
        lambda: calls.append("c"),
    ]
    replay_reset(hooks)
    assert calls == ["a", "b", "c"]


def test_replay_reset_safe_to_call_repeatedly():
    counter = {"n": 0}

    def inc():
        counter["n"] += 1
    hooks = [inc]
    replay_reset(hooks)
    replay_reset(hooks)
    assert counter["n"] == 2


def test_replay_reset_clears_b5c_seen():
    from captain_online.blocks.b5c_circuit_breaker import _get_seen
    _get_seen().add("dirty")
    replay_reset(default_reset_hooks())
    assert "dirty" not in _get_seen()


# --------------------------------------------------------------------------- #
# OnlineReplayContext                                                         #
# --------------------------------------------------------------------------- #


def test_context_resets_on_enter_and_exit():
    n = {"calls": 0}

    def hook():
        n["calls"] += 1

    ctx = OnlineReplayContext(
        market_data=MagicMock(),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=[hook],
    )
    with ctx:
        assert n["calls"] == 1
    assert n["calls"] == 2  # reset on enter and on exit


# --------------------------------------------------------------------------- #
# replay_session                                                              #
# --------------------------------------------------------------------------- #


def test_replay_session_returns_no_active_assets_when_b1_returns_none():
    ctx = OnlineReplayContext(
        market_data=MagicMock(),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=default_reset_hooks(),
    )
    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion",
               return_value=None):
        result = replay_session(date(2026, 1, 15), 1, ctx)
    assert isinstance(result, ReplayResult)
    assert result.signals == []
    assert result.diagnostics["reason"] == "no_active_assets"


def test_replay_session_threads_market_data_into_b1():
    """B1.run_data_ingestion is called with market_data=ctx.market_data."""
    fake_market = MagicMock()
    sink = CapturingSignalSink()
    ctx = OnlineReplayContext(
        market_data=fake_market,
        signal_sink=sink,
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=default_reset_hooks(),
    )
    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion",
               return_value=None) as mock_b1:
        replay_session(date(2026, 1, 15), 1, ctx)
    # mock_b1 is called once
    mock_b1.assert_called_once()
    _, kwargs = mock_b1.call_args
    assert kwargs.get("market_data") is fake_market


def test_replay_session_invokes_reset_hooks():
    fired = {"n": 0}

    def hook():
        fired["n"] += 1

    ctx = OnlineReplayContext(
        market_data=MagicMock(),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=[hook],
    )
    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion",
               return_value=None):
        replay_session(date(2026, 1, 15), 1, ctx)
    assert fired["n"] == 2  # entry + exit


def test_replay_session_diagnostics_include_reset_count():
    ctx = OnlineReplayContext(
        market_data=MagicMock(),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=[lambda: None, lambda: None],
    )
    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion",
               return_value=None):
        result = replay_session(date(2026, 1, 15), 1, ctx)
    assert result.diagnostics["reset_hooks_invoked"] == 2


def test_replay_session_applies_parameter_overrides():
    """Parameter overrides land on B1's returned state before downstream blocks."""
    fake_b1_state = {
        "active_assets": ["ES"],
        "features": {},
        "regime_models": {},
        "aim_states": {"old": True},
    }
    ctx = OnlineReplayContext(
        market_data=MagicMock(),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=[],
    )
    params = ReplayParameters(aim_states={"new": True})
    captured_b2_args = {}

    def fake_b2(active_assets, features, regime_models):
        captured_b2_args["called"] = True
        return {}

    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion",
               return_value=fake_b1_state), \
         patch("captain_online.blocks.b2_regime_probability.run_regime_probability",
               side_effect=fake_b2), \
         patch("captain_online.blocks.b6_signal_output.run_signal_output",
               return_value={"signals": []}):
        result = replay_session(date(2026, 1, 15), 1, ctx, params)
    assert captured_b2_args["called"]
    assert result.phase_a_outputs["b1"]["aim_states"] == {"new": True}


# --------------------------------------------------------------------------- #
# captain_online_replay (Layer 3)                                             #
# --------------------------------------------------------------------------- #


def test_captain_online_replay_returns_signal_list():
    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion",
               return_value=None):
        signals = captain_online_replay(
            date(2026, 1, 15),
            using=ReplayParameters(),
            user_id="u1",
            asset="ES",
            session_id=1,
        )
    assert isinstance(signals, list)


def test_captain_online_replay_uses_historical_market_data():
    """Layer 3 instantiates HistoricalMarketDataProvider."""
    with patch(
        "captain_online.blocks.b1_data_ingestion.run_data_ingestion",
        return_value=None,
    ) as mock_b1:
        captain_online_replay(
            date(2026, 1, 15),
            using=ReplayParameters(),
            user_id="u1",
            asset="ES",
            session_id=1,
        )
    _, kwargs = mock_b1.call_args
    md = kwargs.get("market_data")
    assert isinstance(md, HistoricalMarketDataProvider)


def test_captain_online_replay_does_not_touch_redis():
    """The replay path uses CapturingSignalSink and never publishes to Redis."""
    fake_b1_state = {
        "active_assets": ["ES"],
        "features": {},
        "regime_models": {},
    }
    with patch(
        "captain_online.blocks.b1_data_ingestion.run_data_ingestion",
        return_value=fake_b1_state,
    ), patch(
        "captain_online.blocks.b2_regime_probability.run_regime_probability",
        return_value={},
    ), patch(
        "captain_online.blocks.b6_signal_output.run_signal_output",
        return_value={"signals": []},
    ), patch(
        "shared.online_replay_providers.get_redis_client",
    ) as mock_redis:
        captain_online_replay(
            date(2026, 1, 15),
            using=ReplayParameters(),
            user_id="u1",
            asset="ES",
            session_id=1,
        )
    mock_redis.assert_not_called()
