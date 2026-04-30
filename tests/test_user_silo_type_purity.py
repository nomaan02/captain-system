"""Type-purity test for orchestrator._load_user_silo (D16).

Verifies starting_capital and total_capital come back as Decimal even when
the underlying value is exactly zero — the falsy-zero antipattern that
made `row[N] or 0` collapse to int.

Marked real_questdb because it requires a live QuestDB. Skipped in
static-only environments.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from psycopg2 import OperationalError

pytestmark = pytest.mark.real_questdb


def _skip_if_no_questdb():
    from shared.questdb_client import get_cursor
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
    except OperationalError:
        pytest.skip("QuestDB not reachable")


@pytest.fixture
def insert_test_d16_row():
    _skip_if_no_questdb()
    """Insert a fresh D16 row with zero capital, yield user_id."""
    from shared.questdb_client import get_cursor
    import json

    user_id = "type_purity_silo_user"

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d16_user_capital_silos (
                user_id, status, role, starting_capital, total_capital,
                accounts, max_simultaneous_positions, max_portfolio_risk_pct,
                correlation_threshold, user_kelly_ceiling, capital_history,
                telegram_chat_id, created, last_updated
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, now(), now()
            )""",
            (
                user_id, "ACTIVE", "USER",
                Decimal("0.00"), Decimal("0.00"),
                json.dumps([]), 5, 0.10,
                0.7, 1.0, json.dumps([]),
                None,
            ),
        )

    yield user_id

    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM p3_d16_user_capital_silos WHERE user_id = %s",
            (user_id,),
        )


def test_load_user_silo_type_purity(insert_test_d16_row):
    """starting_capital / total_capital must be Decimal even at zero."""
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    from shared.decimal_boundary import assert_money_dict

    orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
    silo = orch._load_user_silo(insert_test_d16_row)

    assert silo is not None
    assert_money_dict(silo, "starting_capital", "total_capital")
    assert silo["starting_capital"] == Decimal("0.00")
    assert silo["total_capital"] == Decimal("0.00")
