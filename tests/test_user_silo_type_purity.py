"""Type-purity test for orchestrator._load_user_silo (D16).

Verifies starting_capital and total_capital come back as Decimal even when
the underlying value is exactly zero — the falsy-zero antipattern that
made `row[N] or 0` collapse to int.

Marked real_questdb because it requires a live QuestDB. Skipped in
static-only environments.

QuestDB note: this table is append-only (no DELETE FROM). Each test run
uses a unique time-suffixed user_id and leaves the row in place.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal

import pytest
from psycopg2 import OperationalError

from tests._qdb_helpers import wait_for_row

pytestmark = pytest.mark.real_questdb


def _skip_if_no_questdb():
    from shared.questdb_client import get_cursor
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
    except OperationalError:
        pytest.skip("QuestDB not reachable")


def test_load_user_silo_type_purity():
    """starting_capital / total_capital must be Decimal even at zero."""
    _skip_if_no_questdb()
    from shared.questdb_client import get_cursor
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    from shared.decimal_boundary import assert_money_dict

    user_id = f"silo-type-purity-{int(time.time())}"

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

        # Wait for WAL applier to make the row visible
        row = wait_for_row(
            cur,
            """SELECT user_id FROM p3_d16_user_capital_silos
               WHERE user_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (user_id,),
        )
    assert row is not None, "row not visible after WAL wait"

    orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
    silo = orch._load_user_silo(user_id)

    assert silo is not None
    assert_money_dict(silo, "starting_capital", "total_capital")
    assert silo["starting_capital"] == Decimal("0.00")
    assert silo["total_capital"] == Decimal("0.00")
