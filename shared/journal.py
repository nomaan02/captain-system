# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""SQLite WAL journal interface for crash recovery (P3-D20)."""

import os
import uuid
import json
import sqlite3
from datetime import datetime


JOURNAL_PATH = os.environ.get("CAPTAIN_JOURNAL_PATH", "/captain/journal.sqlite")


_initialized = False


def get_journal_connection() -> sqlite3.Connection:
    """Get a connection to the per-process SQLite WAL journal.

    Auto-creates the journal file and system_journal table on first access
    so fresh deployments don't need a separate init step.
    """
    global _initialized
    # Ensure parent directory exists
    parent = os.path.dirname(JOURNAL_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(JOURNAL_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    if not _initialized:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS system_journal (
                entry_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                component TEXT NOT NULL,
                checkpoint TEXT NOT NULL,
                state_hash TEXT,
                last_action TEXT,
                next_action TEXT,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_journal_component ON system_journal(component);
            CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON system_journal(timestamp);
        """)
        _initialized = True
    return conn


def write_checkpoint(
    component: str,
    checkpoint: str,
    last_action: str,
    next_action: str,
    metadata: dict | None = None,
    state_hash: str | None = None,
):
    """Write a checkpoint entry to the journal."""
    conn = get_journal_connection()
    conn.execute(
        """INSERT INTO system_journal
           (entry_id, timestamp, component, checkpoint, state_hash, last_action, next_action, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            datetime.now().isoformat(),
            component,
            checkpoint,
            state_hash,
            last_action,
            next_action,
            json.dumps(metadata) if metadata else None,
        ),
    )
    conn.commit()
    conn.close()


def get_last_checkpoint(component: str) -> dict | None:
    """Get the most recent checkpoint for a component."""
    conn = get_journal_connection()
    cur = conn.execute(
        """SELECT entry_id, timestamp, checkpoint, state_hash, last_action, next_action, metadata
           FROM system_journal WHERE component = ? ORDER BY timestamp DESC LIMIT 1""",
        (component,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "entry_id": row[0],
        "timestamp": row[1],
        "checkpoint": row[2],
        "state_hash": row[3],
        "last_action": row[4],
        "next_action": row[5],
        "metadata": json.loads(row[6]) if row[6] else None,
    }
