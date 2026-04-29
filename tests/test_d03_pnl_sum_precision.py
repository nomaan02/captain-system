"""Phase B: SUM(pnl) over many small trades stays exact (requires QuestDB)."""
from __future__ import annotations

import time
from decimal import Decimal

import pytest
from psycopg2 import OperationalError

from shared.questdb_client import get_cursor
from tests._qdb_helpers import wait_for_count

pytestmark = pytest.mark.real_questdb


def _skip_if_no_questdb():
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
    except OperationalError:
        pytest.skip("QuestDB not reachable")


def test_d03_sum_pnl_many_fractional_trades():
    _skip_if_no_questdb()
    uid = f"sum-prec-{int(time.time())}"
    stamp = int(time.time())
    v = Decimal("0.01")
    n_rows = 100
    expect = Decimal("1")

    with get_cursor() as cur:
        for i in range(n_rows):
            cur.execute(
                """INSERT INTO p3_d03_trade_outcome_log
                   (trade_id, signal_id, user_id, account_id, asset, direction,
                    outcome, pnl, gross_pnl, commission, contracts, ts)
                   VALUES (%s, %s, %s, 'acct-x', 'ES', 1,
                           'CLOSED', %s, %s, 0, 1, now())""",
                (f"SUM-{stamp}-{i}", f"LEGACY-{i}", uid, v, v),
            )
        # All n_rows must be WAL-applied before SUM — otherwise SUM
        # silently returns the partial total of whatever happens to be
        # visible at SELECT time (e.g. 0.99 instead of 1.00 for 99/100).
        observed = wait_for_count(
            cur,
            "SELECT count() FROM p3_d03_trade_outcome_log WHERE user_id = %s",
            (uid,),
            target=n_rows,
            max_wait=5.0,
            interval=0.1,
        )
        assert observed == n_rows, (
            f"only {observed}/{n_rows} rows visible after WAL wait"
        )

        cur.execute(
            "SELECT sum(pnl) FROM p3_d03_trade_outcome_log WHERE user_id = %s",
            (uid,),
        )
        total = cur.fetchone()[0]

    got = Decimal(str(total)) if not isinstance(total, Decimal) else total
    assert got == expect
