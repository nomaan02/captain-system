# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Redis connection utilities shared across all Captain processes.

Uses a module-level singleton so all callers share one connection pool
instead of creating a separate pool per get_redis_client() call.
"""

import json
import logging
import os
import threading
import redis

logger = logging.getLogger(__name__)


REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None) or None

# Channel constants
REDIS_KEY_QUOTES = "captain:quotes"
CH_SIGNALS = "captain:signals:{user_id}"
CH_TRADE_OUTCOMES = "captain:trade_outcomes"
CH_COMMANDS = "captain:commands"
CH_ALERTS = "captain:alerts"
CH_STATUS = "captain:status"
CH_PROCESS_LOGS = "captain:process_logs"

_client = None
_client_lock = threading.Lock()


def get_redis_client() -> redis.Redis:
    """Get the shared Redis client (singleton with internal connection pool)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    password=REDIS_PASSWORD,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_error=[TimeoutError],
                    health_check_interval=30,
                )
    return _client


def get_redis_pubsub() -> redis.client.PubSub:
    """Get a Redis PubSub instance from the shared client."""
    return get_redis_client().pubsub()


def signals_channel(user_id: str) -> str:
    """Get the signals channel for a specific user."""
    return CH_SIGNALS.format(user_id=user_id)


# ---------------------------------------------------------------------------
# Redis Streams — durable message delivery with consumer group acknowledgment
# ---------------------------------------------------------------------------

# Stream names (separate namespace from pub/sub channels)
STREAM_SIGNALS = "stream:signals"
STREAM_TRADE_OUTCOMES = "stream:trade_outcomes"
STREAM_COMMANDS = "stream:commands"
STREAM_SIGNAL_OUTCOMES = "stream:signal_outcomes"  # Theoretical outcomes from shadow monitor

# Consumer group names (one per consuming process)
GROUP_COMMAND_SIGNALS = "command_signals"
GROUP_OFFLINE_OUTCOMES = "offline_outcomes"
GROUP_OFFLINE_COMMANDS = "offline_commands"
GROUP_ONLINE_COMMANDS = "online_commands"
GROUP_OFFLINE_SIGNAL_OUTCOMES = "offline_signal_outcomes"  # Category A learning from theoretical trades


def publish_to_stream(stream: str, data: dict) -> str:
    """Publish a message to a Redis Stream. Returns the message ID.

    Keeps the last 1000 messages per stream to prevent unbounded growth.
    """
    client = get_redis_client()
    msg_id = client.xadd(
        stream, {"payload": json.dumps(data, default=str)}, maxlen=1000,
    )
    return msg_id


def ensure_consumer_group(stream: str, group: str) -> None:
    """Create a consumer group if it doesn't exist. Idempotent."""
    client = get_redis_client()
    try:
        client.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("Created consumer group '%s' on stream '%s'", group, stream)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
        # Group already exists — normal on restart


def read_stream(stream: str, group: str, consumer: str,
                count: int = 10, block: int = 1000) -> list:
    """Read new messages from a stream consumer group.

    Returns list of (message_id, data_dict) tuples.
    block: milliseconds to wait for new messages (1000 = 1s).
    """
    client = get_redis_client()
    results = client.xreadgroup(
        group, consumer, {stream: ">"}, count=count, block=block,
    )
    if not results:
        return []
    # results = [(stream_name, [(msg_id, {field: value}), ...])]
    messages = []
    for msg_id, fields in results[0][1]:
        try:
            data = json.loads(fields.get("payload", "{}"))
        except (json.JSONDecodeError, TypeError):
            data = {}
        messages.append((msg_id, data))
    return messages


def ack_message(stream: str, group: str, msg_id: str) -> None:
    """Acknowledge a processed message so it won't be re-delivered."""
    get_redis_client().xack(stream, group, msg_id)
