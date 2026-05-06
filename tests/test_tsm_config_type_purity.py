"""Type-purity test for b1_data_ingestion._load_tsm_configs.

Verifies that every monetary field in the dict returned by the data
ingestion layer is Decimal (or Decimal | None for nullable). Catches
regressions to the `r[N] or 0.0` antipattern that produced type-mixed
dicts and tripped TypeError in b6_signal_output at NY open 2026-04-30.

Marked real_questdb because it requires a live QuestDB with the Phase A
DECIMAL schema applied. Skipped in static-only environments.

QuestDB note: this table is append-only (no DELETE FROM). Each test run
uses a unique time-suffixed account_id and leaves the row in place,
matching the pattern in tests/test_d08_decimal_roundtrip.py.
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


def test_load_tsm_configs_type_purity():
    """Every monetary field must be Decimal (or None for nullable)."""
    _skip_if_no_questdb()
    from shared.questdb_client import get_cursor
    from captain_online.blocks.b1_data_ingestion import _load_tsm_configs
    from shared.decimal_boundary import assert_money_dict

    account_id = f"TYPE-PURITY-{int(time.time())}"
    user_id = f"type_purity_user_{int(time.time())}"

    with get_cursor() as cur:
        cur.execute(  # qexecute: ok — test fixture: directly exercises type-purity
            """INSERT INTO p3_d08_tsm_state (
                account_id, user_id, name, classification,
                starting_balance, current_balance, current_drawdown,
                daily_loss_used, profit_target,
                max_drawdown_limit, max_daily_loss, max_contracts,
                scaling_plan, commission_per_contract,
                instrument_permissions, overnight_allowed,
                trading_hours, margin_per_contract, margin_buffer_pct,
                pass_probability, simulation_date, risk_goal,
                evaluation_end_date, evaluation_stages,
                topstep_optimisation, topstep_params, topstep_state,
                fee_schedule, payout_rules, scaling_plan_active,
                scaling_tier_micros, last_updated
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, null, %s,
                null, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, now()
            )""",
            (
                account_id, user_id, "TypePurityTest",
                json.dumps({"category": "PROP_EVAL"}),
                Decimal("150000.00"), Decimal("150000.00"), Decimal("0.00"),
                Decimal("0.00"), Decimal("9000.00"),
                Decimal("3000.00"), Decimal("1500.00"), 15,
                json.dumps([]), Decimal("2.80"),
                json.dumps([]), True,
                "09:30-16:00", Decimal("0.00"), 1.5,
                0.65, "GROW_CAPITAL",
                json.dumps([]),
                False, json.dumps({}), json.dumps({}),
                json.dumps({}), json.dumps({}), False,
                0,
            ),
        )

        # Wait for WAL applier to make the row visible
        row = wait_for_row(
            cur,
            """SELECT account_id FROM p3_d08_tsm_state
               WHERE account_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (account_id,),
        )
    assert row is not None, "row not visible after WAL wait"

    configs = _load_tsm_configs()
    assert account_id in configs, (
        f"Account {account_id} not found in loaded TSM configs "
        f"(found {len(configs)} accounts)"
    )

    cfg = configs[account_id]
    assert_money_dict(
        cfg,
        "starting_balance",
        "current_balance",
        "current_drawdown",
        "daily_loss_used",
        "commission_per_contract",
        "margin_per_contract",
        "profit_target",
        "max_drawdown_limit",
        "max_daily_loss",
        allow_none=("profit_target", "max_drawdown_limit", "max_daily_loss"),
    )

    # Spot check exact preservation of Decimal('0.00') (the falsy-zero
    # boundary case that was the NY-open 2026-04-30 failure mode).
    assert cfg["current_drawdown"] == Decimal("0.00")
    assert cfg["daily_loss_used"] == Decimal("0.00")
    assert cfg["max_drawdown_limit"] == Decimal("3000.00")
