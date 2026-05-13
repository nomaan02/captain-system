"""Phase 2b regression: qexecute typed-INSERT helper.

Verifies that qexecute() correctly coerces Decimal params to the right
Python type for each destination column type, before psycopg2 sees them.

Closes the bug class introduced when the global Decimal psycopg2 adapter
unconditionally renders cast('<v>' as DECIMAL(p,s)) — fatal when the
destination column is DOUBLE / SYMBOL / INT / LONG.
"""
from decimal import Decimal

from shared.questdb_client import qexecute


class MockCursor:
    """Captures the params passed to .execute() for assertion."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.rowcount = 1

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))


def test_decimal_aim_modifier_to_double_becomes_float():
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d03_trade_outcome_log "
        "(trade_id, signal_id, user_id, account_id, asset, direction, "
        " entry_price, signal_entry_price, exit_price, contracts, "
        " gross_pnl, commission, pnl, slippage, outcome, "
        " entry_time, exit_time, regime_at_entry, aim_modifier_at_entry, "
        " aim_breakdown_at_entry, session, tsm_used, model_m, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        " %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
    )
    params = (
        "TRD-1", "SIG-1", "u1", "21855714", "MES", 1,
        Decimal("4523.5"), Decimal("4523.5"), Decimal("4525.0"), 2,
        Decimal("100"), Decimal("4"), Decimal("96"), Decimal("0"),
        "TP_HIT", "2026-05-06T09:30:00", "2026-05-06T09:35:00",
        "LOW_VOL", Decimal("0.96"), '{}', 1, "AC1", 7,
    )
    qexecute(cur, sql, params)
    assert len(cur.calls) == 1
    captured = cur.calls[0][1]
    # aim_modifier_at_entry is index 18 (0-based) in the column list.
    assert isinstance(captured[18], float)
    assert captured[18] == 0.96
    # entry_price (index 6) is DECIMAL — must stay Decimal.
    assert isinstance(captured[6], Decimal)


def test_decimal_account_id_to_symbol_becomes_str():
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d08_tsm_state (account_id, user_id, name) "
        "VALUES (%s, %s, %s)"
    )
    qexecute(cur, sql, (Decimal("21855714"), "u1", "Eval"))
    captured = cur.calls[0][1]
    assert isinstance(captured[0], str)
    assert captured[0] == "21855714"


def test_decimal_session_to_int_becomes_int():
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d23_circuit_breaker_intraday "
        "(account_id, session_id, l_t, n_t, l_b, n_b, last_updated) "
        "VALUES (%s, %s, %s, %s, %s, %s, now())"
    )
    qexecute(
        cur, sql,
        ("21855714", Decimal("1"), Decimal("0"), Decimal("0"), "{}", "{}"),
    )
    captured = cur.calls[0][1]
    assert isinstance(captured[1], int)
    assert captured[1] == 1
    # l_t is DECIMAL — stays Decimal.
    assert isinstance(captured[2], Decimal)
    # n_t is INT — Decimal → int.
    assert isinstance(captured[3], int)
    assert captured[3] == 0


def test_d23_money_columns_quantize_high_scale_decimal():
    """QuestDB rejects DECIMAL(11,8) cast into DECIMAL(18,2); qexecute fixes scale."""
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d23_circuit_breaker_intraday("
        "account_id, session_id, l_t, n_t, l_b, n_b, "
        "effective_l_halt, effective_e_exposure, session_opened_at, last_updated"
        ") VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    noisy = Decimal("551.18400000")
    qexecute(
        cur,
        sql,
        (
            "21855714",
            2,
            Decimal("0"),
            0,
            "{}",
            "{}",
            noisy,
            noisy,
            "2026-05-13T02:55:00",
            "2026-05-13T02:55:00",
        ),
    )
    captured = cur.calls[0][1]
    assert captured[6] == Decimal("551.18")
    assert captured[7] == Decimal("551.18")


def test_d03_pnl_columns_quantize_to_scale_4():
    """D03 gross_pnl / commission / pnl / slippage are DECIMAL(18, 4)."""
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d03_trade_outcome_log ("
        "trade_id, signal_id, user_id, account_id, asset, direction, "
        "entry_price, signal_entry_price, exit_price, contracts, "
        "gross_pnl, commission, pnl, slippage, outcome, "
        "entry_time, exit_time, regime_at_entry, aim_modifier_at_entry, "
        "aim_breakdown_at_entry, session, tsm_used, model_m, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
    )
    noisy_pnl = Decimal("96.123456789")
    params = (
        "TRD-1", "SIG-1", "u1", "21855714", "MES", 1,
        Decimal("4523.5"), Decimal("4523.5"), Decimal("4525.0"), 2,
        noisy_pnl, noisy_pnl, noisy_pnl, noisy_pnl,
        "TP_HIT", "2026-05-06T09:30:00", "2026-05-06T09:35:00",
        "LOW_VOL", Decimal("0.96"), '{}', 1, "AC1", 7,
    )
    qexecute(cur, sql, params)
    captured = cur.calls[0][1]
    expected = Decimal("96.1235")
    assert captured[10] == expected
    assert captured[11] == expected
    assert captured[12] == expected
    assert captured[13] == expected


def test_d00_tick_size_quantizes_to_scale_8():
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d00_asset_universe "
        "(asset_id, point_value, tick_size, warm_up_progress, last_updated) "
        "VALUES (%s, %s, %s, %s, now())"
    )
    qexecute(
        cur,
        sql,
        (
            "MES-QE",
            Decimal("1.234567"),
            Decimal("0.03125000123456789"),
            Decimal("0.85"),
        ),
    )
    captured = cur.calls[0][1]
    assert captured[1] == Decimal("1.234567")
    assert captured[2] == Decimal("0.03125000")
    assert captured[3] == 0.85


def test_decimal_to_decimal_unchanged():
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d03_trade_outcome_log (trade_id, entry_price) "
        "VALUES (%s, %s)"
    )
    qexecute(cur, sql, ("TRD-X", Decimal("4523.5")))
    captured = cur.calls[0][1]
    assert isinstance(captured[1], Decimal)
    assert captured[1] == Decimal("4523.5")


def test_none_preserves_null():
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d08_tsm_state (account_id, max_drawdown_limit) "
        "VALUES (%s, %s)"
    )
    qexecute(cur, sql, ("21855714", None))
    captured = cur.calls[0][1]
    assert captured[1] is None


def test_multiline_sql_parses_correctly():
    cur = MockCursor()
    sql = """
        INSERT INTO p3_d03_trade_outcome_log
            (trade_id, account_id, aim_modifier_at_entry)
        VALUES (%s, %s, %s)
    """
    qexecute(cur, sql, ("TRD-1", "AC1", Decimal("0.85")))
    captured = cur.calls[0][1]
    assert isinstance(captured[2], float)
    assert captured[2] == 0.85


def test_explicit_columns_override_for_fstring_sql():
    """For dynamically built SQL, caller passes columns= explicitly."""
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d00_asset_universe "
        "(asset_id, point_value, warm_up_progress) "
        "VALUES (%s, %s, %s)"
    )
    qexecute(
        cur, sql, ("MES", Decimal("5.0"), Decimal("0.85")),
        table="p3_d00_asset_universe",
        columns=["asset_id", "point_value", "warm_up_progress"],
    )
    captured = cur.calls[0][1]
    # point_value is DECIMAL — stays Decimal.
    assert isinstance(captured[1], Decimal)
    # warm_up_progress is DOUBLE — Decimal → float.
    assert isinstance(captured[2], float)


def test_select_passes_through_unchanged():
    cur = MockCursor()
    sql = "SELECT * FROM p3_d03_trade_outcome_log WHERE asset = %s"
    qexecute(cur, sql, (Decimal("0.96"),))
    # SELECT params are filter values, not column writes — no coercion.
    captured = cur.calls[0][1]
    assert isinstance(captured[0], Decimal)


def test_ddl_passes_through_unchanged():
    cur = MockCursor()
    sql = "CREATE TABLE IF NOT EXISTS foo (x INT)"
    qexecute(cur, sql, ())
    assert cur.calls[0][0] == sql


def test_unknown_table_passes_through_unchanged():
    cur = MockCursor()
    sql = "INSERT INTO p3_does_not_exist (col1) VALUES (%s)"
    # No coercion, no crash — pass-through.
    qexecute(cur, sql, (Decimal("1.5"),))
    captured = cur.calls[0][1]
    assert isinstance(captured[0], Decimal)


def test_returns_rowcount():
    cur = MockCursor()
    cur.rowcount = 5
    rc = qexecute(
        cur,
        "INSERT INTO p3_d17_system_monitor_state (param_key) VALUES (%s)",
        ("k1",),
    )
    assert rc == 5


def test_decimal_to_long_becomes_int():
    """LONG columns receive int() coercion (e.g. p3_d29_opening_volumes.volume_first_m_min)."""
    cur = MockCursor()
    sql = (
        "INSERT INTO p3_d29_opening_volumes "
        "(asset_id, session_date, session_type, or_minutes, "
        " volume_first_m_min, or_range_first_m_min, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s, now())"
    )
    qexecute(
        cur, sql,
        ("MES", "2026-05-06", "NY", 30, Decimal("12345"), Decimal("0.5")),
    )
    captured = cur.calls[0][1]
    # volume_first_m_min is LONG.
    assert isinstance(captured[4], int)
    assert captured[4] == 12345
    # or_range_first_m_min is DOUBLE.
    assert isinstance(captured[5], float)
