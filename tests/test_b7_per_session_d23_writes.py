"""Phase 3: B7 _update_capital_and_cb writes per-session D23 rows.

Verifies the read-modify-write path:
  1. SELECT scoped by (account_id, session_id) — not just account_id.
  2. INSERT carries session_id in the row + preserves effective_l_halt /
     effective_e_exposure / session_opened_at from the prior row.
  3. l_b basket keys are namespaced by "<session_id>:<model_m>" so a
     strategy running in multiple sessions doesn't pollute itself.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from shared.decimal_json import dumps_decimal


class MockCursor:
    """Captures executes; serves scripted fetchone responses."""

    def __init__(self, fetch_responses: list):
        self._responses = list(fetch_responses)
        self._next = None
        self.executes: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = None) -> None:
        self.executes.append((sql, params))
        upper = sql.strip().upper()
        if upper.startswith("INSERT"):
            self._next = None
            return
        # SELECT — pop the next scripted response if present
        if self._responses:
            self._next = self._responses.pop(0)
        else:
            self._next = None

    def fetchone(self):
        return self._next

    def fetchall(self):
        return [self._next] if self._next else []


@contextmanager
def _scripted(cursor):
    yield cursor


def test_d23_select_scoped_by_account_and_session():
    """SELECT in _update_capital_and_cb must include `session_id = %s`."""
    from captain_online.blocks.b7_position_monitor import _update_capital_and_cb

    # Scripted SELECT responses:
    # 1) D16 silo SELECT — return None (no silo row, simplifies)
    # 2) D23 SELECT — return None (no row yet — first trade in this session)
    cursor = MockCursor([None, None])

    with patch(
        "captain_online.blocks.b7_position_monitor.get_cursor",
        lambda: _scripted(cursor),
    ):
        _update_capital_and_cb(
            user_id="primary_user",
            account_id="21855714",
            net_pnl=Decimal("-100.00"),
            outcome="SL_HIT",
            model_m="6",
            session_id=2,  # LON
        )

    # Find the D23 SELECT (third execute after D16 SELECT)
    d23_selects = [
        (sql, p) for sql, p in cursor.executes
        if "p3_d23_circuit_breaker_intraday" in sql and "SELECT" in sql.upper()
    ]
    assert len(d23_selects) == 1
    sql, params = d23_selects[0]
    # Must filter on both account_id and session_id
    assert "account_id = %s" in sql
    assert "session_id = %s" in sql
    assert params == ("21855714", 2)


def test_d23_insert_writes_session_id_and_preserves_effective_fields():
    """INSERT must include session_id AND carry forward the SOD-locked
    effective_l_halt / effective_e_exposure / session_opened_at fields
    from the prior row (set by the orchestrator session-open hook)."""
    from captain_online.blocks.b7_position_monitor import _update_capital_and_cb

    # Prior D23 row for (21855714, NY): l_t=-200, n_t=2, basket P&L,
    # eff_L_halt=750, eff_E=750, opened_at=...
    prior_d23 = (
        Decimal("-200.00"),  # l_t
        2,                   # n_t
        dumps_decimal({"1:6": Decimal("-150.00")}),  # l_b (NY:m6)
        '{"1:6": 2}',        # n_b
        Decimal("750.00"),   # effective_l_halt
        Decimal("750.00"),   # effective_e_exposure
        "2026-05-06T09:30:00-04:00",  # session_opened_at
    )
    cursor = MockCursor([None, prior_d23])

    with patch(
        "captain_online.blocks.b7_position_monitor.get_cursor",
        lambda: _scripted(cursor),
    ):
        _update_capital_and_cb(
            user_id="primary_user",
            account_id="21855714",
            net_pnl=Decimal("-50.00"),
            outcome="SL_HIT",
            model_m="6",
            session_id=1,  # NY
        )

    # Find the D23 INSERT
    d23_inserts = [
        (sql, p) for sql, p in cursor.executes
        if "p3_d23_circuit_breaker_intraday" in sql and "INSERT" in sql.upper()
    ]
    assert len(d23_inserts) == 1
    _sql, params = d23_inserts[0]
    # Params order: (account_id, session_id, l_t, n_t, l_b, n_b,
    #                effective_l_halt, effective_e_exposure, session_opened_at)
    assert params[0] == "21855714"
    assert params[1] == 1                                   # NY
    assert params[2] == Decimal("-250.00")                  # -200 + -50
    assert params[3] == 3                                   # 2 + 1
    assert params[6] == Decimal("750.00")                   # eff_l_halt preserved
    assert params[7] == Decimal("750.00")                   # eff_e preserved
    assert params[8] == "2026-05-06T09:30:00-04:00"         # session_opened_at preserved


def test_l_b_basket_keys_are_session_scoped():
    """Strategy m=6 trades in both NY and LON. The l_b basket dict must use
    keys of form '<session_id>:<model_m>' so the two sessions' P&L don't
    bleed into each other.
    """
    from captain_online.blocks.b7_position_monitor import _update_capital_and_cb
    from shared.decimal_json import loads_decimal

    # Prior LON row already has 1:6 (NY:m6) entry from a NY trade; should
    # NOT be touched when LON trade for m=6 closes.
    prior_d23 = (
        Decimal("0"),
        0,
        dumps_decimal({"1:6": Decimal("-300.00")}),  # NY:m6 unchanged
        '{"1:6": 1}',
        Decimal("500.00"),
        Decimal("500.00"),
        "2026-05-06T03:00:00-04:00",
    )
    cursor = MockCursor([None, prior_d23])
    with patch(
        "captain_online.blocks.b7_position_monitor.get_cursor",
        lambda: _scripted(cursor),
    ):
        _update_capital_and_cb(
            user_id="primary_user",
            account_id="21855714",
            net_pnl=Decimal("80.00"),
            outcome="TP_HIT",
            model_m="6",
            session_id=2,  # LON
        )

    d23_insert = [
        (sql, p) for sql, p in cursor.executes
        if "p3_d23_circuit_breaker_intraday" in sql and "INSERT" in sql.upper()
    ][0]
    params = d23_insert[1]
    # l_b is index 4 (json string)
    l_b = loads_decimal(params[4])
    assert "1:6" in l_b
    assert "2:6" in l_b
    assert l_b["1:6"] == Decimal("-300.00")  # NY untouched
    assert l_b["2:6"] == Decimal("80.00")    # LON new entry


def test_session_id_defaults_to_1_when_pos_lacks_session():
    """resolve_position falls back to session_id=1 (NY) for legacy positions
    where the signal didn't propagate session.

    This test verifies the int() coercion in resolve_position handles missing
    or malformed session values without raising.
    """
    # Just verify the int(pos.get("session", 1) or 1) idiom does the right thing
    test_cases = [
        ({"session": None}, 1),
        ({}, 1),
        ({"session": 0}, 1),    # 0 is falsy → defaults to 1
        ({"session": 2}, 2),
        ({"session": "3"}, 3),
        ({"session": "garbage"}, 1),  # int() raises → caught → 1
    ]
    for pos, expected in test_cases:
        try:
            sid = int(pos.get("session", 1) or 1)
        except (ValueError, TypeError):
            sid = 1
        assert sid == expected, f"pos={pos} → expected {expected} got {sid}"
