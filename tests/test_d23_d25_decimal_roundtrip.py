"""Phase A: D23 l_t and D25 l_star DECIMAL round-trip (requires QuestDB)."""
import time
from decimal import Decimal

import pytest
from psycopg2 import OperationalError

from shared.questdb_client import get_cursor
from tests._qdb_helpers import wait_for_row

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
        cur.execute(  # qexecute: ok — test fixture: directly exercises DECIMAL roundtrip
            """INSERT INTO p3_d23_circuit_breaker_intraday
               (account_id, session_id, l_t, n_t, l_b, n_b,
                effective_l_halt, effective_e_exposure, session_opened_at,
                last_updated)
               VALUES (%s, 1, %s, 0, '{}', '{}', NULL, NULL, NULL, now())""",
            (aid, v),
        )
        row = wait_for_row(
            cur,
            """SELECT l_t FROM p3_d23_circuit_breaker_intraday
               WHERE account_id = %s ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert Decimal(str(row[0])) == v


def test_d23_per_session_columns_roundtrip():
    """Per-session budget columns (M043-M046) round-trip with Decimal precision."""
    _skip_if_no_questdb()
    aid = f"D23PS-{int(time.time())}"
    eff_l_halt = Decimal("250.00")
    eff_e = Decimal("500.00")
    with get_cursor() as cur:
        # Write three rows for the same account on different session_ids,
        # each with its own effective_l_halt / effective_e / session_opened_at.
        for sid, lhalt, e in [
            (1, eff_l_halt, eff_e),
            (2, eff_l_halt + Decimal("100"), eff_e + Decimal("200")),
            (3, eff_l_halt + Decimal("50"), eff_e + Decimal("100")),
        ]:
            cur.execute(  # qexecute: ok — test fixture: directly exercises DECIMAL roundtrip
                """INSERT INTO p3_d23_circuit_breaker_intraday
                   (account_id, session_id, l_t, n_t, l_b, n_b,
                    effective_l_halt, effective_e_exposure, session_opened_at,
                    last_updated)
                   VALUES (%s, %s, 0, 0, '{}', '{}', %s, %s, now(), now())""",
                (aid, sid, lhalt, e),
            )
        # Read back per-session rows and verify round-trip
        row_ny = wait_for_row(
            cur,
            """SELECT effective_l_halt, effective_e_exposure
               FROM p3_d23_circuit_breaker_intraday
               WHERE account_id = %s AND session_id = 1
               ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
        row_lon = wait_for_row(
            cur,
            """SELECT effective_l_halt, effective_e_exposure
               FROM p3_d23_circuit_breaker_intraday
               WHERE account_id = %s AND session_id = 2
               ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
    assert row_ny is not None and row_lon is not None
    assert Decimal(str(row_ny[0])) == eff_l_halt
    assert Decimal(str(row_ny[1])) == eff_e
    assert Decimal(str(row_lon[0])) == eff_l_halt + Decimal("100")
    assert Decimal(str(row_lon[1])) == eff_e + Decimal("200")


def test_d25_l_star_decimal_roundtrip():
    _skip_if_no_questdb()
    aid = f"D25DEC-{int(time.time())}"
    v = Decimal("1234.56")
    with get_cursor() as cur:
        cur.execute(  # qexecute: ok — test fixture: directly exercises DECIMAL roundtrip
            """INSERT INTO p3_d25_circuit_breaker_params(
                account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                n_observations, p_value, l_star, cold_start, last_updated)
            VALUES (%s, 0, 0, 0, 1, 0, 0, 1, %s, true, now())""",
            (aid, v),
        )
        row = wait_for_row(
            cur,
            """SELECT l_star FROM p3_d25_circuit_breaker_params
               WHERE account_id = %s ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert Decimal(str(row[0])) == v
