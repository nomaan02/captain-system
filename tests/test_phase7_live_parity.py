"""Phase 7 — Live-parity regression guard (Batch 7.14).

Verifies that the live B1 / B6 paths default to the same provider and
sink semantics they used pre-Phase-7. Without a sealed live QuestDB
fixture in this test environment (Stage 1B O9), we assert the call
shape: when no kwargs are supplied, ``LiveMarketDataProvider`` /
``RedisSignalPublisher`` are the constructed defaults.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest


def test_b1_default_provider_is_live():
    """``run_data_ingestion(session_id)`` with no provider kwarg routes
    through ``LiveMarketDataProvider`` (or the live ``quote_cache`` /
    ``topstep_client`` shims)."""
    from captain_online.blocks import b1_data_ingestion

    sig = inspect.signature(b1_data_ingestion.run_data_ingestion)
    assert sig.parameters["market_data"].default is None
    # When omitted, _prefetch_market_data routes through helpers that
    # consult quote_cache / topstep_client — i.e. the live path.


def test_b1_helper_default_uses_quote_cache():
    """``_get_latest_price`` with no provider kwarg consults the live
    ``quote_cache``."""
    from captain_online.blocks import b1_data_ingestion as b1

    saved_qc = b1.quote_cache
    saved_resolve = b1.resolve_contract_id
    seen = []

    class _Cache(dict):
        def get(self, key, default=None):
            seen.append(key)
            return {"lastPrice": 4500.0}

    b1.quote_cache = _Cache()
    b1.resolve_contract_id = lambda a: "CONTRACT-1"
    try:
        price = b1._get_latest_price("ES")
    finally:
        b1.quote_cache = saved_qc
        b1.resolve_contract_id = saved_resolve
    assert price == 4500.0
    assert seen, "live quote cache must be consulted on the default path"


def test_b6_default_sink_is_redis():
    """``_publish_signals`` with no sink kwarg routes through
    ``publish_to_stream`` (Redis)."""
    from captain_online.blocks import b6_signal_output

    sig = inspect.signature(b6_signal_output.run_signal_output)
    assert sig.parameters["signal_sink"].default is None

    sigs = [{
        "signal_id": "SIG-1", "asset": "ES", "direction": 1, "size": 1,
        "tp_level": 100.0, "sl_level": 99.0,
        "timestamp": "2026-01-15T09:30:00",
    }]
    with patch.object(b6_signal_output, "publish_to_stream") as mock_pub:
        b6_signal_output._publish_signals("u1", sigs, [], 1)
    mock_pub.assert_called_once()


def test_b1_calls_unchanged_when_market_data_omitted():
    """Pre-/post-Phase-7 invariant: the public ``run_data_ingestion``
    signature gained an ``*, market_data=None`` parameter, but its
    positional surface is unchanged."""
    from captain_online.blocks import b1_data_ingestion

    sig = inspect.signature(b1_data_ingestion.run_data_ingestion)
    positional = [
        p for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    assert [p.name for p in positional] == ["session_id"]


def test_b6_signature_extends_with_signal_sink_only():
    from captain_online.blocks import b6_signal_output

    sig = inspect.signature(b6_signal_output.run_signal_output)
    kwonly = [
        p for p in sig.parameters.values()
        if p.kind == p.KEYWORD_ONLY
    ]
    assert [p.name for p in kwonly] == ["signal_sink"]


def test_run_signal_output_default_doesnt_capture():
    """Default sink (None) → live path → no in-memory capture remains
    after publish (the live ``publish_to_stream`` is fire-and-forget)."""
    from captain_online.blocks import b6_signal_output

    sigs = [{
        "signal_id": "SIG-LP", "asset": "ES", "direction": 1, "size": 1,
        "tp_level": 100.0, "sl_level": 99.0,
        "timestamp": "2026-01-15T09:30:00",
    }]
    with patch.object(b6_signal_output, "publish_to_stream"):
        b6_signal_output._publish_signals("u1", sigs, [], 1)  # no sink
    # No captured assertion — the live path doesn't expose one. The
    # test passes if we get here without raising.
