"""Phase A: D23 l_t and D25 l_star DECIMAL round-trip (requires QuestDB)."""
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


def test_d23_l_t_decimal_roundtrip():
    _skip_if_no_questdb()
    aid = f"D23DEC-{int(time.time())}"
    v = Decimal("-987.65")
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d23_circuit_breaker_intraday
               (account_id, l_t, n_t, l_b, n_b, last_updated)
               VALUES (%s, %s, 0, '{}', '{}', now())""",
            (aid, v),
        )
        cur.execute(
            """SELECT l_t FROM p3_d23_circuit_breaker_intraday
               WHERE account_id = %s ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
        row = cur.fetchone()
    assert row and Decimal(str(row[0])) == v


def test_d25_l_star_decimal_roundtrip():
    _skip_if_no_questdb()
    aid = f"D25DEC-{int(time.time())}"
    v = Decimal("1234.56")
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d25_circuit_breaker_params(
                account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                n_observations, p_value, l_star, cold_start, last_updated)
            VALUES (%s, 0, 0, 0, 1, 0, 0, 1, %s, true, now())""",
            (aid, v),
        )
        cur.execute(
            """SELECT l_star FROM p3_d25_circuit_breaker_params
               WHERE account_id = %s ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
        row = cur.fetchone()
    assert row and Decimal(str(row[0])) == v
