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
# DOUBLE→DECIMAL casts on assignment.  Quoted-string DECIMAL literals
# also crash the QuestDB server (HTTP 500, empty error, position=0)
# for short values like '0', '1', '1.4' — the parser hits an unhandled
# code path on values shorter than ~5 chars.  See:
#   docs2/audits/questdb-re-seed/2026-04-29_d08_tsm_insert_debug_handoff.md
#
# Wrapping every value in `cast(... as DECIMAL)` bypasses the short-string
# crash, but `DECIMAL` (no params) defaults to DECIMAL(18, 3) inside the
# cast expression — which then rejects values with scale > 3 (e.g. ZB
# tick_size 0.03125, ZN 0.015625, ZT 0.0078125, FX 5e-7, OHLC prices like
# 6256.006214) with `inconvertible value: ... [STRING -> DECIMAL(18,3)]`.
#
# Solution: introspect each Decimal's representation and emit
# `cast('<value>' as DECIMAL(<precision>, <scale>))` with the minimal
# (p, s) that fits the value losslessly. QuestDB widens or narrows on
# assignment, so the same adapter works for every DECIMAL(p,s) column.
def _decimal_to_cast_sql(d: Decimal) -> str:
    """Render a Decimal as `cast('<value>' as DECIMAL(<p>, <s>))`.

    The precision/scale are derived from the Decimal's own digits so the
    cast expression always fits the value.  QuestDB then widens or
    narrows at column-assignment time as needed.
    """
    s = format(d, "f")  # expand any scientific notation: 5E-7 -> '0.0000005'
    sign = ""
    if s.startswith("-"):
        sign, s = "-", s[1:]
    if "." in s:
        int_part, frac_part = s.split(".", 1)
        scale = len(frac_part)
    else:
        int_part = s
        scale = 0
    int_digits = max(len(int_part.lstrip("0")), 1)
    precision = int_digits + scale
    if precision > 38:  # QuestDB DECIMAL precision cap
        precision = 38
        if scale > precision:
            scale = precision
    return f"cast('{sign}{s}' as DECIMAL({precision}, {scale}))"


psycopg2.extensions.register_adapter(
    Decimal,
    lambda d: psycopg2.extensions.AsIs(_decimal_to_cast_sql(d)),
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
