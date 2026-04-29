"""Phase A: D08 monetary DECIMAL columns round-trip (requires QuestDB)."""
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


def test_d08_decimal_monetary_columns_roundtrip():
    _skip_if_no_questdb()
    aid = f"D08DEC-{int(time.time())}"
    v = Decimal("12345.67")
    # 10 %s placeholders (account_id + 9 monetary columns) → 10-element tuple.
    # An earlier revision of this test passed 11 values, triggering psycopg2's
    # "not all arguments converted during string formatting" error.
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d08_tsm_state(
                account_id, user_id, name, classification,
                starting_balance, current_balance, current_drawdown, daily_loss_used,
                profit_target, max_drawdown_limit, max_daily_loss, max_contracts,
                scaling_plan, commission_per_contract,
                instrument_permissions, overnight_allowed,
                trading_hours, margin_per_contract, margin_buffer_pct,
                pass_probability, simulation_date, risk_goal,
                evaluation_end_date, evaluation_stages,
                topstep_optimisation, topstep_params, topstep_state,
                fee_schedule, payout_rules, scaling_plan_active,
                scaling_tier_micros, last_updated
            ) VALUES (
                %s, 'u', 'n', '{}',
                %s, %s, %s, %s,
                %s, %s, %s, 1,
                '', %s,
                '[]', false,
                '', %s, 0,
                null, null, 'PASS_EVAL',
                null, '[]',
                false, '{}', '{}',
                '{}', '{}', false,
                0, now()
            )""",
            (aid, v, v, v, v, v, v, v, v, v),
        )
        row = wait_for_row(
            cur,
            """SELECT starting_balance, current_balance, current_drawdown, daily_loss_used,
                      profit_target, max_drawdown_limit, max_daily_loss,
                      commission_per_contract, margin_per_contract
               FROM p3_d08_tsm_state
               WHERE account_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
    assert row is not None, "row not visible after WAL wait"
    for x in row:
        assert Decimal(str(x)) == v
