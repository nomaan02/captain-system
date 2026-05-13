# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""QuestDB connection utilities shared across all Captain processes."""

import logging
import os
import re
import threading
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import psycopg2
import psycopg2.extensions
from contextlib import contextmanager

from shared.canonical_schemas import COLUMN_TYPES

# DECIMAL(p,s) as stored in COLUMN_TYPES — used to quantize values before the
# global Decimal adapter builds cast(..., DECIMAL(p_inner, s_inner)). QuestDB
# rejects DECIMAL(11,8) → DECIMAL(18,2) assignment when s_inner > column scale
# (session-budget carryover was 551.18400000 → cast as DECIMAL(11,8) into
# effective_l_halt DECIMAL(18,2) -> inconvertible).
_DECIMAL_COL_RE = re.compile(
    r"^DECIMAL\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*$", re.IGNORECASE
)

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
# (p, s) that fits the value losslessly after any consumer-side rounding.
# Typed INSERTs also run ``qexecute`` column-scale quantization (see
# ``_coerce_for_column``): QuestDB rejects some cast-to-column assignments
# when the cast's scale exceeds the column's (e.g. DECIMAL(11,8) value
# into DECIMAL(18,2)), so we must not rely on implicit narrowing.
def _decimal_to_cast_sql(d: Decimal) -> str:
    """Render a Decimal as `cast('<value>' as DECIMAL(<p>, <s>))`.

    The precision/scale are derived from the Decimal's own digits so the
    cast fits the (possibly pre-quantized) value. Column assignment is not
    guaranteed to narrow cast scale to the column; ``qexecute`` quantizes
    Decimals to each column's declared scale before this runs.
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


# ------------------------------------------------------------------------- #
# Typed-INSERT consumer-boundary helper (May 2026, fixes Issue 5 bug class) #
# ------------------------------------------------------------------------- #
#
# The global Decimal adapter above renders every Decimal as
# cast('<v>' as DECIMAL(p,s)) — correct for DECIMAL columns, FATAL for
# DOUBLE / SYMBOL / INT columns (QuestDB rejects DECIMAL→DOUBLE casts on
# assignment). qexecute() looks up each column's type from
# shared.canonical_schemas.COLUMN_TYPES and coerces Decimal-typed params
# to the right Python type BEFORE psycopg2 sees them.
#
# Usage:
#   qexecute(cur, "INSERT INTO p3_d03_trade_outcome_log (col1, col2, ...) VALUES (%s, %s, ...)", (v1, v2, ...))
#
# For dynamic SQL (f-strings) where columns can't be auto-parsed, pass:
#   qexecute(cur, sql, params, table="p3_d03_trade_outcome_log", columns=["col1", "col2", ...])
#
# Returns the cursor's rowcount — same as cur.execute().

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(p[23]_[a-z0-9_]+)\s*\(([^)]+)\)\s*VALUES",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE_RE = re.compile(
    r"UPDATE\s+(p[23]_[a-z0-9_]+)\s+SET\s+(.+?)(?:\s+WHERE|\s*$)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_table_columns_from_sql(sql: str) -> tuple[str, list[str]] | None:
    """Extract (table_name, [columns]) from an INSERT statement.

    Returns None for non-INSERT statements or unparseable SQL — caller
    falls through to default behaviour. Column names are stripped of
    leading/trailing whitespace and newlines so multi-line INSERT bodies
    parse correctly.
    """
    m = _INSERT_RE.search(sql)
    if not m:
        return None
    table = m.group(1).lower()
    cols = [c.strip() for c in m.group(2).split(",") if c.strip()]
    return table, cols


def _coerce_for_column(value: object, col_type: str) -> object:
    """Coerce a single param to the right Python type for col_type.

    DECIMAL columns: Decimal -> quantize to the column's declared scale
        (ROUND_HALF_UP) so psycopg2's cast DECIMAL(p,s) matches QuestDB's
        DECIMAL(18,2) / DECIMAL(14,6) etc.; other types pass through.
    DOUBLE / FLOAT:   Decimal -> float; None stays None.
    SYMBOL / VARCHAR / STRING / CHAR: Decimal -> str; None stays None.
    INT / LONG / SHORT / BYTE:       Decimal -> int; None stays None.
    BOOLEAN:          Decimal/numeric -> bool; None stays None.
    TIMESTAMP / DATE: datetime -> isoformat string; passthrough otherwise.
    UUID / GEOHASH / IPv4: passthrough.
    """
    if value is None:
        return None
    if col_type.strip().upper().startswith("DECIMAL"):
        m = _DECIMAL_COL_RE.match(col_type.strip())
        if m and isinstance(value, Decimal):
            scale = int(m.group(2))
            step = Decimal(1).scaleb(-scale)
            try:
                return value.quantize(step, rounding=ROUND_HALF_UP)
            except InvalidOperation:
                return value
        return value
    if col_type in ("DOUBLE", "FLOAT"):
        if isinstance(value, Decimal):
            return float(value)
        return value
    if col_type in ("SYMBOL", "VARCHAR", "STRING", "CHAR"):
        if isinstance(value, Decimal):
            return str(value)
        return value
    if col_type in ("INT", "LONG", "SHORT", "BYTE"):
        if isinstance(value, Decimal):
            return int(value)
        return value
    if col_type == "BOOLEAN":
        if isinstance(value, Decimal):
            return bool(int(value))
        return value
    if col_type in ("TIMESTAMP", "DATE"):
        if isinstance(value, datetime):
            return value.isoformat()
        return value
    return value  # unknown column type — passthrough (safer than crashing)


def qexecute(
    cur,
    sql: str,
    params: tuple = (),
    *,
    table: str | None = None,
    columns: list[str] | None = None,
) -> int:
    """psycopg2 cur.execute() wrapper that coerces each param to its column's type.

    For INSERT statements into p3_*/p2_* tables:
      - Parses the destination table + column list from the SQL (or uses
        the explicit ``table=`` / ``columns=`` overrides for f-string SQLs).
      - Looks up each column's type in ``shared.canonical_schemas.COLUMN_TYPES``.
      - Coerces each param to the right Python type via ``_coerce_for_column``.
      - Calls ``cur.execute(sql, coerced_params)`` and returns rowcount.

    For non-INSERT statements (SELECT, DELETE, UPDATE, DDL): pass-through to
    ``cur.execute()`` with no coercion — params for filter clauses are not
    column-write targets. The ``_UPDATE_RE`` regex is defined for future use
    when production UPDATE sites appear (Phase 0B inventory found 0 today).
    """
    if not isinstance(sql, str):
        cur.execute(sql, params)
        return getattr(cur, "rowcount", 0)

    parsed_table = None
    parsed_cols = None
    if columns is not None:
        parsed_table = table
        parsed_cols = columns
    else:
        parse = _parse_table_columns_from_sql(sql)
        if parse is not None:
            parsed_table, parsed_cols = parse

    if parsed_table is None or parsed_cols is None:
        cur.execute(sql, params)
        return getattr(cur, "rowcount", 0)

    type_map = COLUMN_TYPES.get(parsed_table)
    if type_map is None:
        cur.execute(sql, params)
        return getattr(cur, "rowcount", 0)

    coerced = list(params)
    for i, col in enumerate(parsed_cols):
        if i >= len(coerced):
            break  # SQL has more cols than params (NULL or now() literals)
        col_type = type_map.get(col)
        if col_type is None:
            continue
        coerced[i] = _coerce_for_column(coerced[i], col_type)

    cur.execute(sql, tuple(coerced))
    return getattr(cur, "rowcount", 0)


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
        qexecute(
            c,
            f"INSERT INTO p3_d00_asset_universe ({col_names}) VALUES ({placeholders})",
            tuple(current[k] for k in D00_COLUMNS),
            table="p3_d00_asset_universe",
            columns=list(D00_COLUMNS),
        )

    if cur is not None:
        _do(cur)
    else:
        with get_cursor() as c:
            _do(c)
