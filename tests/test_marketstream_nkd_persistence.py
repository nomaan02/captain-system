"""Tests for C10 — MarketStream NKD subscription persistence guard.

When an NKD trail position is open at session rollover, the system must
retain NKD's MarketStream subscription so the live quote feed stays active
for the B7B trail loop's stale-quote check.

Tests cover:
1. is_subscribed() getter on MarketStream
2. ensure_nkd_subscribed() in captain-online/main.py:
   - adds NKD contract when not subscribed + open position present
   - no-op when already subscribed
   - no-op when no open NKD positions
   - no-op when _market_stream is None (startup race)
"""

from unittest.mock import patch, MagicMock
import pytest

import captain_online.main as online_main
from shared.topstep_stream import MarketStream


class TestMarketStreamIsSubscribed:
    """MarketStream.is_subscribed() getter unit tests."""

    def test_subscribed_contract_returns_true(self):
        """A contract in the initial list is subscribed."""
        stream = MarketStream.__new__(MarketStream)
        stream._contract_ids = ["CON.F.US.NKD.M26", "CON.F.US.EP.M26"]
        assert stream.is_subscribed("CON.F.US.NKD.M26") is True

    def test_unsubscribed_contract_returns_false(self):
        """A contract NOT in the list is not subscribed."""
        stream = MarketStream.__new__(MarketStream)
        stream._contract_ids = ["CON.F.US.EP.M26"]
        assert stream.is_subscribed("CON.F.US.NKD.M26") is False

    def test_empty_subscription_list_returns_false(self):
        stream = MarketStream.__new__(MarketStream)
        stream._contract_ids = []
        assert stream.is_subscribed("CON.F.US.NKD.M26") is False


class TestEnsureNKDSubscribed:
    """ensure_nkd_subscribed() in captain-online/main.py."""

    def _make_open_position(self, asset="NKD", is_nkd_trail=True):
        return {"asset": asset, "is_nkd_trail": is_nkd_trail, "signal_id": "SIG-TEST"}

    @pytest.fixture(autouse=True)
    def restore_market_stream(self):
        """Restore module-level _market_stream after each test."""
        original = online_main._market_stream
        yield
        online_main._market_stream = original

    def test_nkd_retained_when_open_position_present(self):
        """When NKD position is open and contract not subscribed, add_contract is called."""
        mock_stream = MagicMock()
        mock_stream.is_subscribed.return_value = False
        online_main._market_stream = mock_stream

        pos = self._make_open_position("NKD", True)
        with patch("shared.contract_resolver.resolve_contract_id", return_value="CON.F.US.NKD.M26"):
            online_main.ensure_nkd_subscribed([pos])

        mock_stream.add_contract.assert_called_once_with("CON.F.US.NKD.M26")

    def test_nkd_not_added_when_already_subscribed(self):
        """No redundant add_contract call when NKD already subscribed."""
        mock_stream = MagicMock()
        mock_stream.is_subscribed.return_value = True
        online_main._market_stream = mock_stream

        pos = self._make_open_position("NKD", True)
        with patch("shared.contract_resolver.resolve_contract_id", return_value="CON.F.US.NKD.M26"):
            online_main.ensure_nkd_subscribed([pos])

        mock_stream.add_contract.assert_not_called()

    def test_nkd_removed_when_no_open_position(self):
        """When no NKD positions, add_contract is NOT called (fast path exit)."""
        mock_stream = MagicMock()
        mock_stream.is_subscribed.return_value = False
        online_main._market_stream = mock_stream

        es_pos = self._make_open_position("ES", False)
        with patch("shared.contract_resolver.resolve_contract_id", return_value="CON.F.US.NKD.M26"):
            online_main.ensure_nkd_subscribed([es_pos])

        mock_stream.add_contract.assert_not_called()

    def test_no_op_when_market_stream_is_none(self):
        """Guards gracefully when called before market_stream is set (startup race)."""
        online_main._market_stream = None
        pos = self._make_open_position("NKD", True)
        # Should not raise
        online_main.ensure_nkd_subscribed([pos])

    def test_empty_positions_list_is_no_op(self):
        """Empty list exits early without touching stream."""
        mock_stream = MagicMock()
        online_main._market_stream = mock_stream
        online_main.ensure_nkd_subscribed([])
        mock_stream.add_contract.assert_not_called()

    def test_is_nkd_trail_flag_alone_triggers_guard(self):
        """is_nkd_trail=True on a non-NKD asset (future APAC) still triggers guard."""
        mock_stream = MagicMock()
        mock_stream.is_subscribed.return_value = False
        online_main._market_stream = mock_stream

        pos = {"asset": "FUTURE_APAC", "is_nkd_trail": True, "signal_id": "SIG-X"}
        with patch("shared.contract_resolver.resolve_contract_id", return_value="CON.F.US.NKD.M26"):
            online_main.ensure_nkd_subscribed([pos])

        mock_stream.add_contract.assert_called_once()
