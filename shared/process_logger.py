"""Process-level log emission for Live Terminal GUI display.

All 3 Captain processes (ONLINE, OFFLINE, COMMAND) use this to publish
structured log entries to the ``captain:process_logs`` Redis pub/sub channel.
Captain Command subscribes and forwards entries to the GUI via WebSocket
as ``process_log`` messages.

Usage::

    from shared.process_logger import ProcessLogger
    from shared.redis_client import get_redis_client

    plog = ProcessLogger("ONLINE", get_redis_client())
    plog.info("B1: Data ingestion started", source="b1_data")
    plog.error("Auth failed: token expired", source="topstep")
"""

import json
import logging
import threading
from shared.constants import now_et
from shared.redis_client import CH_PROCESS_LOGS, CH_BACKEND_LOGS

_logger = logging.getLogger(__name__)


class ProcessLogger:
    """Publish structured log entries to the Live Terminal GUI panel."""

    __slots__ = ("process", "redis")

    def __init__(self, process_name: str, redis_client):
        self.process = process_name
        self.redis = redis_client

    def _emit(self, level: str, message: str, source: str = ""):
        entry = {
            "process": self.process,
            "level": level,
            "source": source,
            "message": message,
            "timestamp": now_et().isoformat(),
        }
        try:
            self.redis.publish(CH_PROCESS_LOGS, json.dumps(entry))
        except Exception:
            pass  # Never let terminal logging break the main process

    def info(self, message: str, source: str = ""):
        self._emit("INFO", message, source)

    def warn(self, message: str, source: str = ""):
        self._emit("WARN", message, source)

    def error(self, message: str, source: str = ""):
        self._emit("ERROR", message, source)

    def debug(self, message: str, source: str = ""):
        self._emit("DEBUG", message, source)


class RedisLogHandler(logging.Handler):
    """Python logging handler that publishes to Redis for GUI backend log view."""

    _EXCLUDED = frozenset({
        "redis", "urllib3", "httpx", "asyncio",
        "uvicorn.access", "uvicorn.error",
    })
    _local = threading.local()

    def __init__(self, process_name: str, redis_client):
        super().__init__()
        self.process = process_name
        self.redis = redis_client

    def emit(self, record):
        if any(record.name.startswith(p) for p in self._EXCLUDED):
            return
        if getattr(self._local, "publishing", False):
            return
        self._local.publishing = True
        try:
            entry = {
                "process": self.process,
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
                "timestamp": now_et().isoformat(),
            }
            self.redis.publish(CH_BACKEND_LOGS, json.dumps(entry))
        except Exception:
            pass
        finally:
            self._local.publishing = False


def attach_backend_handler(process_name: str):
    """Attach a RedisLogHandler to the root logger for GUI backend view."""
    from shared.redis_client import get_redis_client
    handler = RedisLogHandler(process_name, get_redis_client())
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
