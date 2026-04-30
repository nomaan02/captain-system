"""QuestDB test helpers — handle WAL ingestion lag deterministically.

QuestDB WAL tables apply writes asynchronously. With autocommit enabled,
``INSERT`` returns immediately but the row is not always visible to the
*next* ``SELECT`` on the same connection — the WAL applier may not have
flushed yet. Production code is unaffected because read/write cycles are
spaced seconds apart by event loops, but an INSERT-then-SELECT inside a
single test races the applier and produces flaky failures.

This module provides:

* ``wait_for_row`` — poll a SELECT until any row appears.
* ``wait_for_count`` — poll a count() query until it reaches a target value
  (use when running an aggregate like SUM that needs *all* rows visible,
  not just one).

Both helpers timeout deterministically rather than retrying forever.
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


def wait_for_count(
    cur,
    sql: str,
    params: Optional[Sequence[Any]] = None,
    *,
    target: int,
    max_wait: float = 5.0,
    interval: float = 0.1,
) -> int:
    """Poll a ``SELECT count() ...`` query until it reaches ``target`` or
    a timeout. Returns the final count observed.

    Use before aggregate queries (SUM, AVG, MIN, MAX) that depend on
    *every* row being visible — a single-row poll via ``wait_for_row``
    isn't sufficient because the aggregate would happily return a
    partial result.

    The supplied ``sql`` must be a ``SELECT count() ...`` (or equivalent
    aggregate returning a single integer). The function does not modify
    the SQL; the caller writes whatever ``WHERE`` filter they need.
    """
    deadline = time.monotonic() + max_wait
    last = 0
    while True:
        cur.execute(sql, params)
        row = cur.fetchone()
        last = int(row[0]) if row and row[0] is not None else 0
        if last >= target:
            return last
        if time.monotonic() >= deadline:
            return last
        time.sleep(interval)
