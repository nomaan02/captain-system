"""Type-purity test for b1_data_ingestion._load_active_assets (D00).

Verifies point_value, tick_size, margin_per_contract come back as Decimal
even when the underlying values are zero — the falsy-zero antipattern.

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


def test_load_active_assets_type_purity():
    """Every D00 monetary field must be Decimal."""
    _skip_if_no_questdb()
    from captain_online.blocks.b1_data_ingestion import _load_active_assets
    from shared.decimal_boundary import assert_money_dict

    assets = _load_active_assets(session_id=1)
    if not assets:
        pytest.skip("No active assets in D00 — bootstrap required first")

    for a in assets:
        assert_money_dict(
            a,
            "point_value",
            "tick_size",
            "margin_per_contract",
        )
