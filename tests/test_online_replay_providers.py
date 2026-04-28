"""Phase 7 — Tests for shared.online_replay_providers.

Tests are isolated to the protocol surface; real-QuestDB integration is
covered by the broader live-parity guard in 7.14.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from shared.online_replay import (
    MarketDataProvider,
    SignalSink,
    TimeProvider,
)
from shared.online_replay_providers import (
    CapturingSignalSink,
    FixedTimeProvider,
    HistoricalMarketDataProvider,
    LiveMarketDataProvider,
    LiveTimeProvider,
    RedisSignalPublisher,
)

_ET = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# LiveMarketDataProvider                                                      #
# --------------------------------------------------------------------------- #


def test_live_provider_implements_protocol():
    p = LiveMarketDataProvider()
    assert isinstance(p, MarketDataProvider)


def test_live_provider_wraps_topstep_client():
    """LiveMarketDataProvider.get_bars threads through topstep_client."""
    p = LiveMarketDataProvider()
    fake_bars = [{"o": 1, "h": 2, "l": 0, "c": 1, "v": 100}]
    fake_client = MagicMock()
    fake_client.get_bars.return_value = fake_bars
    with patch("shared.online_replay_providers.get_topstep_client",
               return_value=fake_client), \
         patch("shared.online_replay_providers.resolve_contract_id",
               return_value="CONTRACT-1"):
        bars = p.get_bars(
            "ES", "1m",
            datetime(2026, 1, 15, 9, 30, tzinfo=_ET),
            datetime(2026, 1, 15, 16, 0, tzinfo=_ET),
        )
    assert bars == fake_bars
    fake_client.get_bars.assert_called_once()
    args = fake_client.get_bars.call_args[0]
    assert args[0] == "CONTRACT-1"
    assert args[1] == 2  # barUnit minute
    assert args[2] == 1  # barValue


# --------------------------------------------------------------------------- #
# HistoricalMarketDataProvider                                                #
# --------------------------------------------------------------------------- #


def test_historical_provider_implements_protocol():
    p = HistoricalMarketDataProvider(as_of=datetime(2026, 1, 15, 9, 30, tzinfo=_ET))
    assert isinstance(p, MarketDataProvider)


def test_historical_get_bars_returns_empty_for_intraday():
    """Until a 1-minute bar table lands, get_bars(timeframe='1m') returns []."""
    p = HistoricalMarketDataProvider(as_of=datetime(2026, 1, 15, 9, 30, tzinfo=_ET))
    bars = p.get_bars(
        "ES", "1m",
        datetime(2026, 1, 14, tzinfo=_ET),
        datetime(2026, 1, 15, tzinfo=_ET),
    )
    assert bars == []


def test_historical_quote_synthesis_uses_prior_close(monkeypatch):
    """get_current_quote synthesizes from the most recent prior daily close."""
    p = HistoricalMarketDataProvider(as_of=datetime(2026, 1, 15, 9, 30, tzinfo=_ET))
    monkeypatch.setattr(
        HistoricalMarketDataProvider, "get_prior_close",
        lambda self, asset_id: 4500.25,
    )
    quote = p.get_current_quote("ES")
    assert quote is not None
    assert quote["bid"] == 4500.25
    assert quote["ask"] == 4500.25


def test_historical_quote_returns_none_when_no_close(monkeypatch):
    p = HistoricalMarketDataProvider(as_of=datetime(2026, 1, 15, 9, 30, tzinfo=_ET))
    monkeypatch.setattr(
        HistoricalMarketDataProvider, "get_prior_close",
        lambda self, asset_id: None,
    )
    assert p.get_current_quote("ES") is None


# --------------------------------------------------------------------------- #
# Sinks                                                                       #
# --------------------------------------------------------------------------- #


def test_capturing_signal_sink_implements_protocol():
    s = CapturingSignalSink()
    assert isinstance(s, SignalSink)


def test_capturing_signal_sink_collects_publishes():
    sink = CapturingSignalSink()
    sink.publish("channel-a", {"id": 1})
    sink.publish("channel-a", {"id": 2})
    sink.publish("channel-b", {"id": 3})
    captured = sink.captured()
    assert len(captured) == 3
    assert captured[0]["id"] == 1
    assert captured[2]["id"] == 3


def test_capturing_signal_sink_isolates_per_instance():
    s1 = CapturingSignalSink()
    s2 = CapturingSignalSink()
    s1.publish("c", {"id": 1})
    assert s1.captured() and not s2.captured()


def test_redis_publisher_does_not_capture():
    pub = RedisSignalPublisher()
    fake = MagicMock()
    with patch("shared.online_replay_providers.get_redis_client", return_value=fake):
        pub.publish("c", {"id": 1})
    assert pub.captured() == []


# --------------------------------------------------------------------------- #
# Time providers                                                              #
# --------------------------------------------------------------------------- #


def test_live_time_provider_implements_protocol():
    assert isinstance(LiveTimeProvider(), TimeProvider)


def test_fixed_time_provider_returns_fixed_value():
    t = datetime(2026, 1, 15, 9, 30, tzinfo=_ET)
    p = FixedTimeProvider(fixed=t)
    assert p.now_et() == t


def test_fixed_time_provider_advance():
    t = datetime(2026, 1, 15, 9, 30, tzinfo=_ET)
    p = FixedTimeProvider(fixed=t)
    p.advance(60)
    assert p.now_et() == t + timedelta(seconds=60)


def test_fixed_time_provider_assigns_default_tz():
    """Naive datetime is interpreted as ET."""
    t = datetime(2026, 1, 15, 9, 30)
    p = FixedTimeProvider(fixed=t)
    assert p.now_et().tzinfo is not None


# --------------------------------------------------------------------------- #
# Cross-provider invariants                                                   #
# --------------------------------------------------------------------------- #


def test_provider_protocols_are_distinct():
    """A SignalSink isn't a MarketDataProvider — keeps mismatched wiring loud."""
    sink = CapturingSignalSink()
    assert not isinstance(sink, MarketDataProvider)
    market = LiveMarketDataProvider()
    assert not isinstance(market, SignalSink)
