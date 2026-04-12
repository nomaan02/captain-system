# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Tests for Redis Stream PEL (Pending Entries List) recovery.

Validates that read_pending_stream() correctly recovers unacknowledged
messages after a simulated crash, and returns an empty list when the
PEL is empty.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from shared.redis_client import read_pending_stream, read_stream, ack_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xreadgroup_result(stream, messages):
    """Build the nested list structure returned by redis-py xreadgroup.

    messages: list of (msg_id, {field: value}) tuples.
    """
    if not messages:
        return []
    return [(stream, messages)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReadPendingStream:
    """Test read_pending_stream() for PEL recovery after crash."""

    @patch("shared.redis_client.get_redis_client")
    def test_recovers_pending_messages(self, mock_get_client):
        """Simulate a crash: message was delivered but not ACKed.

        read_pending_stream (ID "0") should return the unacknowledged message.
        """
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client

        payload = {"signal_id": "sig_001", "asset": "ES", "direction": 1}
        pending_msg = (b"1712000000000-0", {"payload": json.dumps(payload)})
        fake_client.xreadgroup.return_value = _make_xreadgroup_result(
            "stream:signals", [pending_msg],
        )

        result = read_pending_stream("stream:signals", "grp", "consumer_1")

        assert len(result) == 1
        msg_id, data = result[0]
        assert msg_id == b"1712000000000-0"
        assert data["signal_id"] == "sig_001"
        assert data["asset"] == "ES"
        assert data["direction"] == 1

        # Verify it was called with ID "0" (not ">")
        call_args = fake_client.xreadgroup.call_args
        streams_arg = call_args[0][2]  # third positional arg is the streams dict
        assert streams_arg == {"stream:signals": "0"}

        # Verify no block parameter was passed (non-blocking)
        assert "block" not in call_args[1]

    @patch("shared.redis_client.get_redis_client")
    def test_empty_pel_returns_empty_list(self, mock_get_client):
        """When PEL is empty, read_pending_stream returns []."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client

        # Redis returns None or [] when no pending messages
        fake_client.xreadgroup.return_value = None

        result = read_pending_stream("stream:signals", "grp", "consumer_1")

        assert result == []

    @patch("shared.redis_client.get_redis_client")
    def test_empty_result_list_returns_empty(self, mock_get_client):
        """When xreadgroup returns an empty list, read_pending_stream returns []."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client

        fake_client.xreadgroup.return_value = []

        result = read_pending_stream("stream:signals", "grp", "consumer_1")

        assert result == []

    @patch("shared.redis_client.get_redis_client")
    def test_multiple_pending_messages(self, mock_get_client):
        """Multiple messages in PEL are all recovered."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client

        messages = [
            (b"1712000000000-0", {"payload": json.dumps({"signal_id": "sig_001"})}),
            (b"1712000000001-0", {"payload": json.dumps({"signal_id": "sig_002"})}),
            (b"1712000000002-0", {"payload": json.dumps({"signal_id": "sig_003"})}),
        ]
        fake_client.xreadgroup.return_value = _make_xreadgroup_result(
            "stream:signals", messages,
        )

        result = read_pending_stream("stream:signals", "grp", "consumer_1")

        assert len(result) == 3
        assert result[0][1]["signal_id"] == "sig_001"
        assert result[1][1]["signal_id"] == "sig_002"
        assert result[2][1]["signal_id"] == "sig_003"

    @patch("shared.redis_client.get_redis_client")
    def test_malformed_payload_returns_empty_dict(self, mock_get_client):
        """A message with invalid JSON payload returns {} as data."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client

        messages = [
            (b"1712000000000-0", {"payload": "NOT-VALID-JSON{{{"}),
        ]
        fake_client.xreadgroup.return_value = _make_xreadgroup_result(
            "stream:signals", messages,
        )

        result = read_pending_stream("stream:signals", "grp", "consumer_1")

        assert len(result) == 1
        assert result[0][1] == {}

    @patch("shared.redis_client.get_redis_client")
    def test_skips_empty_field_sentinel_entries(self, mock_get_client):
        """Redis returns entries with empty fields for already-ACKed messages
        when using ID '0' — these should be skipped."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client

        messages = [
            (b"1712000000000-0", {}),  # sentinel — already ACKed
            (b"1712000000001-0", {"payload": json.dumps({"signal_id": "sig_real"})}),
        ]
        fake_client.xreadgroup.return_value = _make_xreadgroup_result(
            "stream:signals", messages,
        )

        result = read_pending_stream("stream:signals", "grp", "consumer_1")

        assert len(result) == 1
        assert result[0][1]["signal_id"] == "sig_real"

    @patch("shared.redis_client.get_redis_client")
    def test_default_count_is_100(self, mock_get_client):
        """Default count parameter should be 100 (higher than read_stream's 10)."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client
        fake_client.xreadgroup.return_value = None

        read_pending_stream("stream:signals", "grp", "consumer_1")

        call_args = fake_client.xreadgroup.call_args
        assert call_args[1].get("count", call_args[0][3] if len(call_args[0]) > 3 else None) == 100


class TestReadStreamUsesNewOnly:
    """Confirm read_stream still uses '>' for new messages only."""

    @patch("shared.redis_client.get_redis_client")
    def test_read_stream_uses_greater_than(self, mock_get_client):
        """read_stream must use ID '>' to get only new messages."""
        fake_client = MagicMock()
        mock_get_client.return_value = fake_client
        fake_client.xreadgroup.return_value = None

        read_stream("stream:signals", "grp", "consumer_1")

        call_args = fake_client.xreadgroup.call_args
        streams_arg = call_args[0][2]
        assert streams_arg == {"stream:signals": ">"}
