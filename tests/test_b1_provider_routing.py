"""Phase 7 — B1 / b1_features provider routing tests.

Verifies the ``market_data`` (alias: ``MarketDataProvider``) kwarg
threads through ``run_data_ingestion`` and ``compute_all_features``
without changing live behaviour when the kwarg is omitted.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from captain_online.blocks import b1_data_ingestion, b1_features


# --------------------------------------------------------------------------- #
# Signature smoke                                                             #
# --------------------------------------------------------------------------- #


def test_run_data_ingestion_accepts_market_data_kwarg():
    sig = inspect.signature(b1_data_ingestion.run_data_ingestion)
    assert "market_data" in sig.parameters
    assert sig.parameters["market_data"].default is None


def test_compute_all_features_accepts_market_data_kwarg():
    sig = inspect.signature(b1_features.compute_all_features)
    assert "market_data" in sig.parameters
    assert sig.parameters["market_data"].default is None


def test_get_intraday_bars_accepts_provider_kwarg():
    sig = inspect.signature(b1_features._get_intraday_bars)
    assert "market_data_provider" in sig.parameters


def test_get_daily_closes_accepts_provider_kwarg():
    sig = inspect.signature(b1_features._get_daily_closes)
    assert "market_data_provider" in sig.parameters


def test_get_recent_5min_vol_accepts_provider_kwarg():
    sig = inspect.signature(b1_features._get_recent_5min_vol)
    assert "market_data_provider" in sig.parameters


# --------------------------------------------------------------------------- #
# Provider routing — helpers                                                  #
# --------------------------------------------------------------------------- #


def test_get_intraday_bars_routes_through_supplied_provider():
    """When a provider is supplied, _get_intraday_bars uses it instead of
    TopstepX REST."""
    fake_provider = MagicMock()
    fake_provider.get_intraday_bars.return_value = [
        {"c": 100.0}, {"c": 101.0},
    ]
    bars = b1_features._get_intraday_bars(
        "ES", 5, market_data_provider=fake_provider,
    )
    assert bars == [{"c": 100.0}, {"c": 101.0}]
    fake_provider.get_intraday_bars.assert_called_once_with("ES", 5)


def test_get_daily_closes_routes_through_supplied_provider():
    fake_provider = MagicMock()
    fake_provider.get_daily_closes.return_value = [10.0, 11.0, 12.0]
    closes = b1_features._get_daily_closes(
        "ES", 3, market_data_provider=fake_provider,
    )
    assert closes == [10.0, 11.0, 12.0]
    fake_provider.get_daily_closes.assert_called_once_with("ES", 3)


def test_get_recent_5min_vol_routes_through_supplied_provider():
    """Provider returns 5 1-min bars; helper computes std dev of log returns."""
    fake_provider = MagicMock()
    fake_provider.get_intraday_bars.return_value = [
        {"c": 100.0}, {"c": 101.0}, {"c": 102.0}, {"c": 101.0}, {"c": 103.0},
    ]
    vol = b1_features._get_recent_5min_vol(
        "ES", market_data_provider=fake_provider,
    )
    assert vol is not None
    assert vol > 0


def test_get_recent_5min_vol_returns_none_without_bars():
    fake_provider = MagicMock()
    fake_provider.get_intraday_bars.return_value = None
    assert b1_features._get_recent_5min_vol(
        "ES", market_data_provider=fake_provider,
    ) is None


# --------------------------------------------------------------------------- #
# Provider routing — entry points                                             #
# --------------------------------------------------------------------------- #


def test_b1_helpers_default_to_live_path_when_provider_none():
    """No provider → helpers fall through to the live (cached / TopstepX)
    path. We pin this by mocking quote_cache and asserting it was consulted."""
    from captain_online.blocks import b1_data_ingestion as b1_di

    quote = {"lastPrice": 4500.25}
    captured: list[str] = []

    class _Cache(dict):
        def get(self, key, default=None):
            captured.append(key)
            return quote

    saved_qc = b1_di.quote_cache
    b1_di.quote_cache = _Cache()
    saved_resolve = b1_di.resolve_contract_id
    b1_di.resolve_contract_id = lambda a: "CONTRACT-ES"
    try:
        price = b1_di._get_latest_price("ES")
    finally:
        b1_di.quote_cache = saved_qc
        b1_di.resolve_contract_id = saved_resolve
    assert price == 4500.25
    assert captured  # cache was consulted


def test_b1_helper_uses_provider_quote_when_supplied():
    """_get_latest_price routes through provider.get_current_quote."""
    fake_provider = MagicMock()
    fake_provider.get_current_quote.return_value = {"lastPrice": 4501.0}
    price = b1_data_ingestion._get_latest_price(
        "ES", market_data_provider=fake_provider,
    )
    assert price == 4501.0
    fake_provider.get_current_quote.assert_called_once_with("ES")


def test_b1_helper_provider_path_falls_back_to_bid_ask_midpoint():
    fake_provider = MagicMock()
    fake_provider.get_current_quote.return_value = {"bid": 100.0, "ask": 100.5}
    price = b1_data_ingestion._get_latest_price(
        "ES", market_data_provider=fake_provider,
    )
    assert price == 100.25


def test_b1_prefetch_threads_provider_through():
    fake_provider = MagicMock()
    fake_provider.get_current_quote.return_value = {"lastPrice": 4500.0}
    fake_provider.get_prior_close.return_value = 4499.0
    fake_provider.get_avg_session_volume_20d.return_value = 100_000.0
    out = b1_data_ingestion._prefetch_market_data(
        [{"asset_id": "ES"}], market_data_provider=fake_provider,
    )
    assert out["ES"]["latest_price"] == 4500.0
    assert out["ES"]["prior_close"] == 4499.0
    assert out["ES"]["avg_volume_20d"] == 100_000.0
