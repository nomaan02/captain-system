"""Phase C: D16, D00, D30 monetary DECIMAL columns round-trip (requires QuestDB)."""
import json
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


def test_d16_decimal_capital_columns_roundtrip():
    _skip_if_no_questdb()
    uid = f"P16-{int(time.time())}"
    v = Decimal("99999.99")
    cap_hist = json.dumps([{"capital": float(v), "date": "2026-03-01"}])
    with get_cursor() as cur:
        cur.execute(  # qexecute: ok — test fixture: directly exercises DECIMAL roundtrip
            """INSERT INTO p3_d16_user_capital_silos (
                   user_id, status, role, starting_capital, total_capital, accounts,
                   max_simultaneous_positions, max_portfolio_risk_pct,
                   correlation_threshold, user_kelly_ceiling,
                   capital_history, telegram_chat_id, created, last_updated
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())""",
            (
                uid, "ACTIVE", "ADMIN",
                v, v,
                json.dumps(["x"]),
                1,
                0.10,
                0.70,
                1.0,
                cap_hist,
                None,
            ),
        )
        row = wait_for_row(
            cur,
            """SELECT starting_capital, total_capital
               FROM p3_d16_user_capital_silos WHERE user_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (uid,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert Decimal(str(row[0])) == v
    assert Decimal(str(row[1])) == v


def test_d00_decimal_asset_specs_roundtrip():
    _skip_if_no_questdb()
    aid = f"P00-{int(time.time())}"
    pv = Decimal("12.3400")
    ts = Decimal("0.2500")
    margin = Decimal("9876.5000")
    with get_cursor() as cur:
        cur.execute(  # qexecute: ok — test fixture: directly exercises DECIMAL roundtrip
            """INSERT INTO p3_d00_asset_universe (
                   asset_id, p1_status, p2_status, captain_status,
                   warm_up_progress, aim_warmup_progress, locked_strategy,
                   roll_calendar, exchange_timezone,
                   point_value, tick_size, margin_per_contract,
                   session_hours, session_schedule,
                   p1_data_path, p2_data_path, data_sources, data_quality_flag,
                   created, last_updated
               ) VALUES (
                   %s,'S','S','ACTIVE',
                   %s,%s,%s,
                   %s,%s,
                   %s,%s,%s,
                   %s,%s,
                   %s,%s,%s,%s,
                   now(),now()
               )""",
            (
                aid,
                1.0,
                "{}",
                "{}",
                "{}",
                "America/New_York",
                pv,
                ts,
                margin,
                "{}",
                "[]",
                "",
                "",
                "{}",
                "CLEAN",
            ),
        )
        row = wait_for_row(
            cur,
            """SELECT point_value, tick_size, margin_per_contract
               FROM p3_d00_asset_universe WHERE asset_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (aid,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert Decimal(str(row[0])) == pv
    assert Decimal(str(row[1])) == ts
    assert Decimal(str(row[2])) == margin


def test_d30_decimal_ohlc_roundtrip():
    _skip_if_no_questdb()
    aid = "ES"
    day = "2026-01-PHC"
    o = Decimal("5000.0000")
    h = Decimal("5010.5000")
    lo = Decimal("4995.7500")
    c = Decimal("5008.1250")
    with get_cursor() as cur:
        cur.execute(  # qexecute: ok — test fixture: directly exercises DECIMAL roundtrip
            """INSERT INTO p3_d30_daily_ohlcv
               (asset_id, trade_date, open, high, low, close, volume, ts)
               VALUES (%s,%s,%s,%s,%s,%s,%s, now())""",
            (aid, day, o, h, lo, c, 1),
        )
        row = wait_for_row(
            cur,
            """SELECT open, high, low, close FROM p3_d30_daily_ohlcv
               WHERE asset_id = %s AND trade_date = %s
               ORDER BY ts DESC LIMIT 1""",
            (aid, day),
        )
    assert row is not None, "row not visible after WAL wait"
    assert Decimal(str(row[0])) == o
    assert Decimal(str(row[1])) == h
    assert Decimal(str(row[2])) == lo
    assert Decimal(str(row[3])) == c
