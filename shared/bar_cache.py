# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""SQLite WAL bar cache for TopstepX historical bars.

Stores fetched 1-minute bars so they can be reused across multiple replay
runs for the same date/asset/session without re-fetching from the API.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from shared.constants import now_et


logger = logging.getLogger(__name__)


BAR_CACHE_PATH = os.environ.get(
    "BAR_CACHE_PATH",
    "/captain/data/bar_cache.sqlite" if os.path.isdir("/captain/data") else "data/bar_cache.sqlite",
)


_initialized = False


def _get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite WAL bar cache.

    Auto-creates the database file and bar_cache table on first access
    so fresh deployments don't need a separate init step.
    """
    global _initialized
    # Ensure parent directory exists
    parent = os.path.dirname(BAR_CACHE_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(BAR_CACHE_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    if not _initialized:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bar_cache (
                asset_id TEXT NOT NULL,
                bar_date TEXT NOT NULL,
                session_type TEXT NOT NULL,
                bars_json TEXT NOT NULL,
                bar_count INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (asset_id, bar_date, session_type)
            );
            CREATE INDEX IF NOT EXISTS idx_bar_cache_date ON bar_cache(bar_date);
            CREATE INDEX IF NOT EXISTS idx_bar_cache_fetched ON bar_cache(fetched_at);
        """)
        _initialized = True
    return conn


def get_cached_bars(asset_id: str, bar_date: str, session_type: str) -> list[dict] | None:
    """Return cached bars or None if not cached."""
    conn = _get_connection()
    cur = conn.execute(
        """SELECT bars_json FROM bar_cache
           WHERE asset_id = ? AND bar_date = ? AND session_type = ?""",
        (asset_id, bar_date, session_type),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    bars = json.loads(row[0])
    logger.debug("bar_cache HIT: %s %s %s (%d bars)", asset_id, bar_date, session_type, len(bars))
    return bars


def cache_bars(asset_id: str, bar_date: str, session_type: str, bars: list[dict]) -> None:
    """Store bars in cache. Overwrites existing entry for same key."""
    conn = _get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO bar_cache
           (asset_id, bar_date, session_type, bars_json, bar_count, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            asset_id,
            bar_date,
            session_type,
            json.dumps(bars),
            len(bars),
            now_et().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    logger.debug("bar_cache STORE: %s %s %s (%d bars)", asset_id, bar_date, session_type, len(bars))


def prune_cache(max_age_days: int = 30) -> int:
    """Delete entries older than max_age_days. Return count deleted."""
    cutoff = (now_et() - timedelta(days=max_age_days)).isoformat()
    conn = _get_connection()
    cur = conn.execute(
        "DELETE FROM bar_cache WHERE fetched_at < ?",
        (cutoff,),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info("bar_cache PRUNE: removed %d entries older than %d days", deleted, max_age_days)
    return deleted


if __name__ == "__main__":
    conn = _get_connection()
    cur = conn.execute("SELECT COUNT(*), COALESCE(SUM(bar_count), 0) FROM bar_cache")
    total_entries, total_bars = cur.fetchone()
    conn.close()
    disk_bytes = os.path.getsize(BAR_CACHE_PATH) if os.path.exists(BAR_CACHE_PATH) else 0
    disk_kb = disk_bytes / 1024
    print(f"Bar cache: {BAR_CACHE_PATH}")
    print(f"  Entries : {total_entries}")
    print(f"  Bars    : {total_bars}")
    print(f"  Disk    : {disk_kb:.1f} KB")
