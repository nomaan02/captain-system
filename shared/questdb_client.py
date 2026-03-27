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
QUESTDB_USER = os.environ.get("QUESTDB_USER", "admin")
QUESTDB_PASSWORD = os.environ.get("QUESTDB_PASSWORD", "quest")
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
