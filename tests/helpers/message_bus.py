# region imports
from AlgorithmImports import *
# endregion
"""In-memory message bus replacing Redis pub/sub for integration tests.

Captures all published messages so tests can inspect the exact payloads
flowing between Online, Command, and Offline.
"""

import json


class InMemoryPubSub:
    """Dict-based replacement for Redis pub/sub."""

    def __init__(self):
        self._messages = {}  # {channel: [payload, ...]}

    def publish(self, channel, payload):
        """Publish a message (stores for later inspection)."""
        if channel not in self._messages:
            self._messages[channel] = []
        if isinstance(payload, str):
            payload = json.loads(payload)
        self._messages[channel].append(payload)

    def get_messages(self, channel):
        """Get all messages published to a channel."""
        return self._messages.get(channel, [])

    def get_last_message(self, channel):
        """Get the most recent message on a channel."""
        msgs = self._messages.get(channel, [])
        return msgs[-1] if msgs else None

    def clear(self):
        """Reset all messages."""
        self._messages.clear()
