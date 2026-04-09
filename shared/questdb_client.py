# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""QuestDB connection utilities shared across all Captain processes."""

import os
import psycopg2
from contextlib import contextmanager


QUESTDB_HOST = os.environ.get("QUESTDB_HOST", "localhost")
QUESTDB_PORT = int(os.environ.get("QUESTDB_PORT", "8812"))
QUESTDB_USER = os.environ.get("QUESTDB_USER", "captain")
QUESTDB_PASSWORD = os.environ.get("QUESTDB_PASSWORD", "")
QUESTDB_DB = os.environ.get("QUESTDB_DB", "qdb")


def get_connection():
    """Get a psycopg2 connection to QuestDB via PostgreSQL wire protocol."""
    return psycopg2.connect(
        host=QUESTDB_HOST,
        port=QUESTDB_PORT,
        user=QUESTDB_USER,
        password=QUESTDB_PASSWORD,
        database=QUESTDB_DB,
    )


@contextmanager
def get_cursor():
    """Context manager yielding a QuestDB cursor with auto-commit."""
    conn = get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        yield cur
    finally:
        conn.close()


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
        + " LATEST ON last_updated PARTITION BY asset_id WHERE asset_id = %s"
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
