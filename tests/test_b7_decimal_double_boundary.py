"""Phase 1 hotfix regression tests — DOUBLE-column boundary in B7.

Closes the Issue 5 May-5 NY-open crash where Decimal aim_modifier from the
Redis-reloaded position dict was rendered as cast('0.96' as DECIMAL(3,2))
by the global psycopg2 adapter and rejected by QuestDB's DOUBLE column
``p3_d03_trade_outcome_log.aim_modifier_at_entry``.

Three regression sites covered:
  1. ``_write_trade_outcome``: aim_modifier (DOUBLE column) coerced to float
     before the INSERT params tuple is built.
  2. ``_resolve_shadow``: same coercion when the shadow monitor publishes a
     theoretical outcome that flows into the same D03 writer downstream.
  3. ``_update_capital_and_cb``: D16 INSERT defensively coerces the three
     DOUBLE columns (max_portfolio_risk_pct, correlation_threshold,
     user_kelly_ceiling) in case ``_load_user_silo`` ever regresses to
     emitting Decimal-typed values for these fields.

The MockCursor pattern follows ``tests/test_orchestrator_session_budget_init.py``.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# MockCursor — scripted SELECTs + INSERT capture
# ---------------------------------------------------------------------------

class MockCursor:
    """Minimal cursor that scripts SELECT responses and captures INSERTs.

    `select_responses` is a list of `(matcher, rows)` tuples. The first
    matcher whose substring is in the executed SQL produces the rows.
    Each match consumes the matcher (one-shot).

    `inserts` accumulates `(sql, params)` tuples for assertion.
    """

    def __init__(self, select_responses: list[tuple[str, list]] | None = None):
        self._select_responses = list(select_responses or [])
        self._last_select_match: list | None = None
        self.inserts: list[tuple[str, tuple]] = []
        # rowcount mimics psycopg2's cursor attribute. ``qexecute`` (Phase 2)
        # returns ``cur.rowcount`` after every INSERT/UPDATE; production code
        # ignores the return value but the attribute must exist.
        self.rowcount = 1

    def execute(self, sql: str, params: tuple = None) -> None:
        upper = sql.strip().upper()
        if upper.startswith("INSERT"):
            self.inserts.append((sql, params))
            self._last_select_match = None
            return
        for i, (matcher, rows) in enumerate(self._select_responses):
            if matcher in sql:
                self._last_select_match = rows
                self._select_responses.pop(i)
                return
        self._last_select_match = []

    def fetchone(self):
        rows = self._last_select_match or []
        return rows[0] if rows else None

    def fetchall(self):
        return list(self._last_select_match or [])


@contextmanager
def _scripted_cursor(cursor):
    yield cursor


# ---------------------------------------------------------------------------
# Test 1 — _write_trade_outcome coerces Decimal aim_modifier to float
# ---------------------------------------------------------------------------

def test_write_trade_outcome_coerces_decimal_aim_modifier_to_float(monkeypatch):
    """Issue 5 hotfix: aim_modifier=Decimal must reach cur.execute as float.

    Without this fix, the global Decimal psycopg2 adapter would render
    Decimal("0.96") as ``cast('0.96' as DECIMAL(3,2))``, which QuestDB
    rejects on assignment to the DOUBLE column ``aim_modifier_at_entry``.
    """
    from captain_online.blocks import b7_position_monitor as mod

    cursor = MockCursor()
    monkeypatch.setattr(mod, "get_cursor", lambda: _scripted_cursor(cursor))
    monkeypatch.setattr(mod, "_get_locked_m", lambda asset: 7)

    mod._write_trade_outcome(
        trade_id="T-TEST",
        user_id="primary_user",
        account_id="21855714",
        asset="MES",
        direction=1,
        entry_price=Decimal("4500.00"),
        signal_entry_price=Decimal("4500.00"),
        exit_price=Decimal("4505.00"),
        contracts=3,
        gross_pnl=Decimal("75.00"),
        commission=Decimal("3.00"),
        net_pnl=Decimal("72.00"),
        slippage=Decimal("0.00"),
        outcome="TP_HIT",
        entry_time=datetime(2026, 5, 5, 9, 30),
        regime_at_entry="BIN_HIGH",
        aim_modifier=Decimal("0.96"),
        aim_breakdown=None,
        session=1,
        tsm_used="primary_user",
        signal_id="SIG-TEST",
    )

    d03_inserts = [(s, p) for s, p in cursor.inserts if "p3_d03_trade_outcome_log" in s]
    assert len(d03_inserts) == 1, f"expected 1 D03 INSERT, got {len(d03_inserts)}"
    _sql, params = d03_inserts[0]

    # INSERT params order (per _write_trade_outcome):
    #   0:trade_id, 1:sig_id, 2:user_id, 3:account_id, 4:asset, 5:direction,
    #   6:entry_price, 7:signal_entry_price, 8:exit_price, 9:contracts,
    #   10:gross_pnl, 11:commission, 12:net_pnl, 13:slippage, 14:outcome,
    #   15:entry_ts, 16:exit_ts, 17:regime_at_entry, 18:aim_modifier, ...
    aim_modifier_param = params[18]
    assert isinstance(aim_modifier_param, float), (
        f"aim_modifier must be float (DOUBLE column), "
        f"got {type(aim_modifier_param).__name__}: {aim_modifier_param!r}"
    )
    assert aim_modifier_param == pytest.approx(0.96, rel=1e-9)


def test_write_trade_outcome_handles_none_aim_modifier_default_one(monkeypatch):
    """Defensive: aim_modifier=None falls through to the default=1.0 sentinel."""
    from captain_online.blocks import b7_position_monitor as mod

    cursor = MockCursor()
    monkeypatch.setattr(mod, "get_cursor", lambda: _scripted_cursor(cursor))
    monkeypatch.setattr(mod, "_get_locked_m", lambda asset: 7)

    mod._write_trade_outcome(
        trade_id="T-NONE",
        user_id="primary_user",
        account_id="21855714",
        asset="MES",
        direction=1,
        entry_price=Decimal("4500.00"),
        signal_entry_price=Decimal("4500.00"),
        exit_price=Decimal("4505.00"),
        contracts=3,
        gross_pnl=Decimal("75.00"),
        commission=Decimal("3.00"),
        net_pnl=Decimal("72.00"),
        slippage=Decimal("0.00"),
        outcome="TP_HIT",
        entry_time=datetime(2026, 5, 5, 9, 30),
        regime_at_entry="BIN_HIGH",
        aim_modifier=None,
        aim_breakdown=None,
        session=1,
        tsm_used="primary_user",
        signal_id="SIG-NONE",
    )

    d03_inserts = [(s, p) for s, p in cursor.inserts if "p3_d03_trade_outcome_log" in s]
    assert len(d03_inserts) == 1
    _sql, params = d03_inserts[0]
    aim_modifier_param = params[18]
    assert isinstance(aim_modifier_param, float)
    assert aim_modifier_param == 1.0


# ---------------------------------------------------------------------------
# Test 2 — Shadow monitor mirrors the same coercion in the published outcome
# ---------------------------------------------------------------------------

def test_resolve_shadow_publishes_float_aim_modifier_for_decimal_input(monkeypatch):
    """Shadow theoretical outcome: combined_modifier=Decimal coerces to float
    in ``aim_modifier_at_entry`` before publishing to the Redis stream.

    The downstream consumer (Offline Category A learner) will eventually feed
    this value into a D03-style INSERT path; the float boundary keeps it
    DOUBLE-safe regardless of whether it ever reaches the cursor.
    """
    from captain_online.blocks import b7_shadow_monitor as mod

    captured: list[tuple[str, dict]] = []

    def _fake_publish(stream_name, payload):
        captured.append((stream_name, payload))

    monkeypatch.setattr(mod, "publish_to_stream", _fake_publish)

    shadow = {
        "signal_id": "SIG-SHADOW",
        "asset": "MES",
        "direction": 1,
        "entry_price": Decimal("4500.00"),
        "tp_level": Decimal("4505.00"),
        "sl_level": Decimal("4498.00"),
        "point_value": Decimal("5"),
        "contracts": 3,
        "session": 1,
        "regime_state": "BIN_HIGH",
        "combined_modifier": Decimal("0.85"),
        "aim_breakdown": None,
        "user_id": "primary_user",
        "created_at": datetime(2026, 5, 5, 9, 30),
        "resolved": False,
    }

    mod._resolve_shadow(shadow, "TP_HIT", 4505.25)

    assert len(captured) == 1, f"expected 1 publish, got {len(captured)}"
    _stream, outcome = captured[0]
    aim_modifier_at_entry = outcome["aim_modifier_at_entry"]
    assert isinstance(aim_modifier_at_entry, float), (
        f"aim_modifier_at_entry must be float for D03 DOUBLE column, "
        f"got {type(aim_modifier_at_entry).__name__}: {aim_modifier_at_entry!r}"
    )
    assert aim_modifier_at_entry == pytest.approx(0.85, rel=1e-9)


# ---------------------------------------------------------------------------
# Test 3 — _update_capital_and_cb D16 INSERT coerces DOUBLE columns to float
# ---------------------------------------------------------------------------

def test_update_capital_and_cb_d16_insert_coerces_double_columns_to_float(monkeypatch):
    """Defensive: even if _load_user_silo regresses to Decimal-typed reads of
    max_portfolio_risk_pct / correlation_threshold / user_kelly_ceiling
    (DOUBLE columns), the D16 INSERT must coerce each to float to avoid the
    same Decimal->DOUBLE crash class as Issue 5.
    """
    from captain_online.blocks import b7_position_monitor as mod

    # SELECT order in _update_capital_and_cb (lines 600-608):
    #   0:status, 1:role, 2:starting_capital, 3:total_capital, 4:accounts,
    #   5:max_simultaneous_positions, 6:max_portfolio_risk_pct,
    #   7:correlation_threshold, 8:user_kelly_ceiling,
    #   9:capital_history, 10:telegram_chat_id, 11:created
    d16_row = (
        "ACTIVE",                # 0 status
        "OWNER",                 # 1 role
        Decimal("150000.00"),    # 2 starting_capital (DECIMAL)
        Decimal("150000.00"),    # 3 total_capital (DECIMAL)
        '["21855714"]',          # 4 accounts (STRING json)
        5,                       # 5 max_simultaneous_positions (INT)
        Decimal("0.05"),         # 6 max_portfolio_risk_pct (DOUBLE) — Decimal regression input
        Decimal("0.5"),          # 7 correlation_threshold (DOUBLE) — Decimal regression input
        Decimal("0.25"),         # 8 user_kelly_ceiling (DOUBLE) — Decimal regression input
        "[]",                    # 9 capital_history (STRING json)
        None,                    # 10 telegram_chat_id (STRING)
        datetime(2026, 1, 1),    # 11 created (TIMESTAMP)
    )

    cursor = MockCursor([
        ("FROM p3_d16_user_capital_silos", [d16_row]),
        ("FROM p3_d23_circuit_breaker_intraday", []),
    ])
    monkeypatch.setattr(mod, "get_cursor", lambda: _scripted_cursor(cursor))

    mod._update_capital_and_cb(
        user_id="primary_user",
        account_id="21855714",
        net_pnl=Decimal("100.00"),
        outcome="WIN",
        model_m="7",
        session_id=1,
    )

    d16_inserts = [(s, p) for s, p in cursor.inserts if "p3_d16_user_capital_silos" in s]
    assert len(d16_inserts) == 1, f"expected 1 D16 INSERT, got {len(d16_inserts)}"
    _sql, params = d16_inserts[0]

    # INSERT params order (per _update_capital_and_cb):
    #   0:user_id, 1:status, 2:role, 3:starting_capital, 4:new_capital,
    #   5:d16_accounts, 6:max_simultaneous_positions,
    #   7:max_portfolio_risk_pct (DOUBLE), 8:correlation_threshold (DOUBLE),
    #   9:user_kelly_ceiling (DOUBLE), 10:capital_history,
    #   11:telegram_chat_id, 12:created
    max_portfolio_risk_pct = params[7]
    correlation_threshold = params[8]
    user_kelly_ceiling = params[9]

    assert isinstance(max_portfolio_risk_pct, float), (
        f"max_portfolio_risk_pct must be float (DOUBLE column), "
        f"got {type(max_portfolio_risk_pct).__name__}: {max_portfolio_risk_pct!r}"
    )
    assert isinstance(correlation_threshold, float), (
        f"correlation_threshold must be float (DOUBLE column), "
        f"got {type(correlation_threshold).__name__}: {correlation_threshold!r}"
    )
    assert isinstance(user_kelly_ceiling, float), (
        f"user_kelly_ceiling must be float (DOUBLE column), "
        f"got {type(user_kelly_ceiling).__name__}: {user_kelly_ceiling!r}"
    )

    assert max_portfolio_risk_pct == pytest.approx(0.05, rel=1e-9)
    assert correlation_threshold == pytest.approx(0.5, rel=1e-9)
    assert user_kelly_ceiling == pytest.approx(0.25, rel=1e-9)

    # DECIMAL columns must remain Decimal (the global adapter handles them).
    starting_capital = params[3]
    new_capital = params[4]
    assert isinstance(starting_capital, Decimal), (
        f"starting_capital must remain Decimal (DECIMAL column), "
        f"got {type(starting_capital).__name__}: {starting_capital!r}"
    )
    assert isinstance(new_capital, Decimal), (
        f"new_capital (total_capital) must remain Decimal (DECIMAL column), "
        f"got {type(new_capital).__name__}: {new_capital!r}"
    )
