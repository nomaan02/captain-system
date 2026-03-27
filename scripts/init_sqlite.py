# region imports
from AlgorithmImports import *
# endregion
"""
SQLite WAL Journal Initialization — P3-D20 (one per Captain process).

Creates the system_journal table in WAL mode for crash recovery.
Each Captain process runs this at startup if the journal doesn't exist.

Usage: python scripts/init_sqlite.py [path_to_journal.sqlite]
"""

import sqlite3
import sys
import os


JOURNAL_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS idx_journal_checkpoint ON system_journal(checkpoint);
CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON system_journal(timestamp);
"""


def init_journal(path: str):
    """Create or verify the SQLite WAL journal at the given path."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(JOURNAL_SCHEMA)
    conn.commit()
    conn.close()
    print(f"  [OK] Journal initialized: {path}")


if __name__ == "__main__":
    journal_path = sys.argv[1] if len(sys.argv) > 1 else "/captain/journal.sqlite"
    print("=" * 60)
    print("CAPTAIN FUNCTION — SQLite WAL Journal Initialization")
    print("=" * 60)
    init_journal(journal_path)
