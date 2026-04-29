# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""QuestDB connection utilities shared across all Captain processes."""

import logging
import os
import threading
import time
from decimal import Decimal

import psycopg2
import psycopg2.extensions
from contextlib import contextmanager

# QuestDB maps psycopg2's NUMERIC wire type to DOUBLE, then rejects
# DOUBLE→DECIMAL casts.  Sending Decimal as a quoted string lets QuestDB
# parse it directly into its native DECIMAL type.
psycopg2.extensions.register_adapter(
    Decimal, lambda d: psycopg2.extensions.AsIs("'" + str(d) + "'")
)

# QuestDB's PG wire doesn't handle psycopg2's binary boolean format.
# Send as SQL keyword literals instead.
psycopg2.extensions.register_adapter(
    bool, lambda b: psycopg2.extensions.AsIs("true" if b else "false")
)

logger = logging.getLogger(__name__)


QUESTDB_HOST = os.environ.get("QUESTDB_HOST", "localhost")
QUESTDB_PORT = int(os.environ.get("QUESTDB_PORT", "8812"))
QUESTDB_USER = os.environ.get("QUESTDB_USER", "captain")
QUESTDB_PASSWORD = os.environ.get("QUESTDB_PASSWORD", "")
QUESTDB_DB = os.environ.get("QUESTDB_DB", "qdb")

_local = threading.local()

_CONNECT_MAX_ATTEMPTS = 3
_CONNECT_DELAYS = [1, 2, 4]  # exponential backoff seconds


def _connect():
    """Create a fresh psycopg2 connection with exponential backoff retry.

    Attempts up to 3 times with delays [1s, 2s, 4s]. Raises on final failure.
    """
    last_exc = None
    for attempt in range(1, _CONNECT_MAX_ATTEMPTS + 1):
        try:
            conn = psycopg2.connect(
                host=QUESTDB_HOST,
                port=QUESTDB_PORT,
                user=QUESTDB_USER,
                password=QUESTDB_PASSWORD,
                database=QUESTDB_DB,
                connect_timeout=5,
            )
            conn.autocommit = True
            if attempt > 1:
                logger.info("QuestDB connection succeeded on attempt %d", attempt)
            return conn
        except Exception as exc:
            last_exc = exc
            if attempt < _CONNECT_MAX_ATTEMPTS:
                delay = _CONNECT_DELAYS[attempt - 1]
                logger.warning(
                    "QuestDB connection attempt %d/%d failed: %s — retrying in %ds",
                    attempt, _CONNECT_MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "QuestDB connection failed after %d attempts: %s",
                    _CONNECT_MAX_ATTEMPTS, exc,
                )
    raise last_exc


def wait_for_questdb(max_wait_seconds: int = 30) -> bool:
    """Poll QuestDB until reachable or timeout. Returns True on success."""
    for attempt in range(1, max_wait_seconds + 1):
        try:
            conn = psycopg2.connect(
                host=QUESTDB_HOST,
                port=QUESTDB_PORT,
                user=QUESTDB_USER,
                password=QUESTDB_PASSWORD,
                database=QUESTDB_DB,
                connect_timeout=5,
            )
            conn.autocommit = True
            conn.cursor().execute("SELECT 1")
            conn.close()
            logger.info("QuestDB reachable (attempt %d)", attempt)
            return True
        except Exception as exc:
            logger.info("QuestDB not yet reachable (attempt %d/%d): %s", attempt, max_wait_seconds, exc)
            time.sleep(1)
    logger.error("QuestDB unreachable after %d seconds", max_wait_seconds)
    return False


def get_connection():
    """Get a psycopg2 connection to QuestDB via PostgreSQL wire protocol.

    Returns a thread-local cached connection, creating a new one only if
    the cached connection is missing or has been closed/broken.
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.cursor().execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            conn = None
    conn = _connect()
    _local.conn = conn
    return conn


@contextmanager
def get_cursor():
    """Context manager yielding a QuestDB cursor with auto-commit."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
    except Exception:
        # If the connection went bad mid-query, discard it so the next
        # call to get_connection() creates a fresh one.
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
        raise


# ---------------------------------------------------------------------------
# D00 asset_universe read-then-reinsert helper
# ---------------------------------------------------------------------------

# All non-timestamp columns in p3_d00_asset_universe, in schema order.
D00_COLUMNS = [
    "asset_id", "p1_status", "p2_status", "captain_status",
    "warm_up_progress", "aim_warmup_progress", "locked_strategy",
    "roll_calendar", "exchange_timezone", "point_value", "tick_size",
    "margin_per_contract", "session_hours", "session_schedule",
    "p1_data_path", "p2_data_path", "data_sources", "data_quality_flag",
]


def read_d00_row(asset_id: str, cur=None) -> dict | None:
    """Read the latest full D00 row for *asset_id*.

    Returns a dict keyed by column name, or None if the asset doesn't exist.
    If *cur* is provided it is reused; otherwise a fresh cursor is created.
    """
    query = (
        "SELECT " + ", ".join(D00_COLUMNS)
        + " FROM p3_d00_asset_universe"
        + " WHERE asset_id = %s LATEST ON last_updated PARTITION BY asset_id"
    )

    if cur is not None:
        cur.execute(query, (asset_id,))
        row = cur.fetchone()
        return dict(zip(D00_COLUMNS, row)) if row else None

    with get_cursor() as c:
        c.execute(query, (asset_id,))
        row = c.fetchone()
    return dict(zip(D00_COLUMNS, row)) if row else None


def update_d00_fields(asset_id: str, updates: dict, cur=None) -> None:
    """Update specific D00 fields while preserving all other columns.

    Reads the current row, merges *updates*, and inserts a complete new row
    with ``last_updated = now()``.  Raises ``ValueError`` if the asset is not
    found in D00.
    """
    def _do(c):
        current = read_d00_row(asset_id, cur=c)
        if current is None:
            raise ValueError(
                f"Asset {asset_id} not found in p3_d00_asset_universe"
            )
        current.update(updates)
        cols = D00_COLUMNS + ["last_updated"]
        placeholders = ", ".join(["%s"] * len(D00_COLUMNS) + ["now()"])
        col_names = ", ".join(cols)
        c.execute(
            f"INSERT INTO p3_d00_asset_universe ({col_names}) VALUES ({placeholders})",
            tuple(current[k] for k in D00_COLUMNS),
        )

    if cur is not None:
        _do(cur)
    else:
        with get_cursor() as c:
            _do(c)
