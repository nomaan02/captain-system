"""Type-purity test for b1_data_ingestion._load_tsm_configs.

Verifies that every monetary field in the dict returned by the data
ingestion layer is Decimal (or Decimal | None for nullable). Catches
regressions to the `r[N] or 0.0` antipattern that produced type-mixed
dicts and tripped TypeError in b6_signal_output at NY open 2026-04-30.

Marked real_questdb because it requires a live QuestDB with the Phase A
DECIMAL schema applied. Skipped in static-only environments.
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
def insert_test_d08_row():
    _skip_if_no_questdb()
    """Insert a fresh D08 row with explicit Decimal values, yield account_id."""
    from shared.questdb_client import get_cursor
    import json

    account_id = "TYPE_PURITY_TEST"
    user_id = "type_purity_test_user"

    with get_cursor() as cur:
        cur.execute(
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
                %s, now(), %s,
                %s, %s,
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
                None, json.dumps({}),
                False, json.dumps({}), json.dumps({}),
                json.dumps({}), json.dumps({}), False,
                0,
            ),
        )

    yield account_id

    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM p3_d08_tsm_state WHERE account_id = %s", (account_id,)
        )


def test_load_tsm_configs_type_purity(insert_test_d08_row):
    """Every monetary field must be Decimal (or None for nullable)."""
    from captain_online.blocks.b1_data_ingestion import _load_tsm_configs
    from shared.decimal_boundary import assert_money_dict

    configs = _load_tsm_configs()
    assert insert_test_d08_row in configs, (
        f"Account {insert_test_d08_row} not found in loaded TSM configs"
    )

    cfg = configs[insert_test_d08_row]
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

    # Spot check exact preservation of Decimal('0.00')
    assert cfg["current_drawdown"] == Decimal("0.00")
    assert cfg["daily_loss_used"] == Decimal("0.00")
    assert cfg["max_drawdown_limit"] == Decimal("3000.00")
