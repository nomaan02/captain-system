"""Phase B: SUM(pnl) over many small trades stays exact (requires QuestDB)."""
from __future__ import annotations

import time
from decimal import Decimal

import pytest
from psycopg2 import OperationalError

from shared.questdb_client import get_cursor

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
        cur.execute(
            "SELECT sum(pnl) FROM p3_d03_trade_outcome_log WHERE user_id = %s",
            (uid,),
        )
        total = cur.fetchone()[0]

    got = Decimal(str(total)) if not isinstance(total, Decimal) else total
    assert got == expect
