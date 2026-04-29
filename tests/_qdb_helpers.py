"""QuestDB test helpers — handle WAL ingestion lag deterministically.

QuestDB WAL tables apply writes asynchronously. With autocommit enabled,
``INSERT`` returns immediately but the row is not always visible to the
*next* ``SELECT`` on the same connection — the WAL applier may not have
flushed yet. Production code is unaffected because read/write cycles are
spaced seconds apart by event loops, but an INSERT-then-SELECT inside a
single test races the applier and produces flaky failures.

This module provides ``wait_for_row``: a tiny polling helper that retries
the SELECT until a row appears or the timeout elapses. Use it in any
real-QuestDB test that reads back a value it just inserted.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Sequence


def wait_for_row(
    cur,
    sql: str,
    params: Optional[Sequence[Any]] = None,
    *,
    max_wait: float = 2.0,
    interval: float = 0.05,
):
    """Poll a SELECT statement until a row appears or timeout.

    Parameters
    ----------
    cur : psycopg2 cursor (already bound to QuestDB).
    sql : str — the SELECT statement to retry.
    params : tuple/list — bind params for ``sql`` (or ``None``).
    max_wait : float — max total seconds to keep retrying. Default 2.0s.
    interval : float — seconds between retries. Default 50ms.

    Returns
    -------
    The first non-None row returned by ``cur.fetchone()``, or ``None`` if
    no row appears within ``max_wait``. The caller is responsible for
    asserting ``row is not None`` (or otherwise interpreting the result).

    Notes
    -----
    Production code does not need this — it never reads back microseconds
    after writing. This helper exists purely to make INSERT-then-SELECT
    test patterns deterministic against QuestDB's async WAL applier.
    """
    deadline = time.monotonic() + max_wait
    while True:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is not None:
            return row
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)
