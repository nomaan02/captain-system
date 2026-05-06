"""Phase 3a: Online orchestrator session-open budget initialiser.

Verifies _initialize_session_budget computes effective_l_halt /
effective_e_exposure correctly with carryover and writes the initial D23 row.

Uses an in-memory `MockCursor` to capture every SQL call so we don't need a
live QuestDB. The cursor returns scripted rows for SELECTs and records every
INSERT for assertion.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from shared.decimal_json import dumps_decimal


class MockCursor:
    """Minimal cursor that scripts SELECT responses and captures INSERTs.

    `select_responses` is a list of `(matcher, rows)` tuples. The first
    matcher whose substring is in the executed SQL produces the rows.
    Each match consumes the matcher (one-shot).

    `inserts` accumulates `(sql, params)` tuples for assertion.
    """

    def __init__(self, select_responses: list[tuple[str, list]]):
        self._select_responses = list(select_responses)
        self._last_select_match = None
        self.inserts: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = None) -> None:
        upper = sql.strip().upper()
        if upper.startswith("INSERT"):
            self.inserts.append((sql, params))
            self._last_select_match = None
            return
        # SELECT — match against the registered responses
        for i, (matcher, rows) in enumerate(self._select_responses):
            if matcher in sql:
                self._last_select_match = rows
                self._select_responses.pop(i)
                return
        # Unmatched SELECT → empty
        self._last_select_match = []

    def fetchone(self):
        rows = self._last_select_match or []
        return rows[0] if rows else None

    def fetchall(self):
        return list(self._last_select_match or [])


@contextmanager
def _scripted_cursor(cursor):
    yield cursor


def _make_d08_row(account_id: str, computed_sod: dict) -> tuple:
    """Shape-of-row for the SELECT account_id, topstep_state in
    _initialize_session_budget."""
    payload = dumps_decimal({"computed_sod": computed_sod})
    return (account_id, payload)


def _build_orchestrator():
    """Build a real OnlineOrchestrator instance without starting threads."""
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
    orch.running = False
    orch.open_positions = []
    orch.shadow_positions = []

    class _NopLog:
        def info(self, *a, **kw): pass
        def warning(self, *a, **kw): pass
        def error(self, *a, **kw): pass

    orch.plog = _NopLog()
    orch._or_tracker = None
    orch._pending_sessions = {}
    return orch


def test_lon_open_no_prior_writes_d23_row_with_own_sod_share():
    """LON is the first session — no carryover — effective_l_halt = SOD share.

    With c=1.0, e=0.01, A=$150K → L_halt_total = $1500, E_total = $1500.
    Equal cold-start shares → LON gets 1500 / 3 = $500 each.
    """
    sod = {
        "L_halt": Decimal("1500.00"),
        "E_daily_exposure": Decimal("1500.00"),
        "session": {
            "NY":   {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
            "LON":  {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
            "APAC": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
        },
    }

    cursor = MockCursor([
        # 1st SELECT: D08 accounts list
        ("FROM p3_d08_tsm_state", [_make_d08_row("21855714", sod)]),
        # 2nd SELECT: idempotency check on this (account, session) — no row yet
        ("WHERE account_id = %s AND session_id = %s", []),
    ])

    with patch(
        "shared.questdb_client.get_cursor",
        lambda: _scripted_cursor(cursor),
    ):
        orch = _build_orchestrator()
        orch._initialize_session_budget(2)  # LON

    # Exactly one INSERT into p3_d23 for the LON row.
    inserts = [(sql, p) for sql, p in cursor.inserts if "p3_d23" in sql]
    assert len(inserts) == 1, f"expected 1 D23 insert, got {len(inserts)}"
    _sql, params = inserts[0]
    # Params order: (account_id, session_id, l_t, n_t, l_b, n_b,
    #                effective_l_halt, effective_e_exposure,
    #                session_opened_at, last_updated)
    assert params[0] == "21855714"
    assert params[1] == 2  # LON session_id
    assert params[2] == Decimal("0")  # l_t starts at 0
    assert params[3] == 0  # n_t starts at 0
    eff_l_halt = params[6]
    eff_e = params[7]
    # LON open with no prior sessions → eff = SOD share = 500
    assert abs(eff_l_halt - Decimal("500")) < Decimal("0.01"), eff_l_halt
    assert abs(eff_e - Decimal("500")) < Decimal("0.01"), eff_e
    assert params[8] is not None  # session_opened_at populated


def test_ny_open_after_lon_skipped_inherits_carryover():
    """NY opens after LON had no trades (parity skipped).

    Expected: effective_NY = (1500 - 0) × (1/3) / (2/3) = 750.
    """
    sod = {
        "L_halt": Decimal("1500.00"),
        "E_daily_exposure": Decimal("1500.00"),
        "session": {
            "NY":   {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
            "LON":  {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
            "APAC": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
        },
    }
    # LON row exists with l_t=0 and session_opened_at set (LON did open today,
    # just had 0 trades because of parity skip at signal-decision time).
    from datetime import datetime
    today_iso = datetime.now().isoformat()

    cursor = MockCursor([
        ("FROM p3_d08_tsm_state", [_make_d08_row("21855714", sod)]),
        # Earlier session SELECT: LON state
        ("WHERE account_id = %s AND session_id = %s",
         [(Decimal("0"), Decimal("500"), Decimal("500"), today_iso)]),
        # Idempotency check on NY: no existing row
        ("WHERE account_id = %s AND session_id = %s", []),
    ])

    with patch(
        "shared.questdb_client.get_cursor",
        lambda: _scripted_cursor(cursor),
    ):
        orch = _build_orchestrator()
        orch._initialize_session_budget(1)  # NY

    inserts = [(sql, p) for sql, p in cursor.inserts if "p3_d23" in sql]
    assert len(inserts) == 1
    _, params = inserts[0]
    assert params[1] == 1  # NY
    eff_l_halt = params[6]
    eff_e = params[7]
    # consumed = 0 (LON l_t=0), available = 1500, share = 1/3, remaining = 2/3
    # eff = 1500 × (1/3) / (2/3) = 750
    assert abs(eff_l_halt - Decimal("750")) < Decimal("0.01"), eff_l_halt
    assert abs(eff_e - Decimal("750")) < Decimal("0.01"), eff_e


def test_apac_open_after_ny_lost_300_inherits_smaller_pool():
    """APAC opens last. LON skipped (l_t=0), NY lost $300 (l_t=-300).

    Expected: available = 1500 - 0 - 300 = 1200; APAC alone remains so
    effective_APAC = 1200 × (1/3) / (1/3) = 1200.
    """
    sod = {
        "L_halt": Decimal("1500.00"),
        "E_daily_exposure": Decimal("1500.00"),
        "session": {
            "NY":   {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
            "LON":  {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
            "APAC": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500"),
                     "share": Decimal("0.333333")},
        },
    }
    from datetime import datetime
    today_iso = datetime.now().isoformat()

    cursor = MockCursor([
        ("FROM p3_d08_tsm_state", [_make_d08_row("21855714", sod)]),
        # Earlier session SELECT round 1 (LON: session_id=2)
        ("WHERE account_id = %s AND session_id = %s",
         [(Decimal("0"), Decimal("500"), Decimal("500"), today_iso)]),
        # Earlier session SELECT round 2 (NY: session_id=1)
        ("WHERE account_id = %s AND session_id = %s",
         [(Decimal("-300"), Decimal("750"), Decimal("750"), today_iso)]),
        # Idempotency check on APAC
        ("WHERE account_id = %s AND session_id = %s", []),
    ])

    with patch(
        "shared.questdb_client.get_cursor",
        lambda: _scripted_cursor(cursor),
    ):
        orch = _build_orchestrator()
        orch._initialize_session_budget(3)  # APAC

    inserts = [(sql, p) for sql, p in cursor.inserts if "p3_d23" in sql]
    assert len(inserts) == 1
    _, params = inserts[0]
    eff_l_halt = params[6]
    eff_e = params[7]
    # consumed = abs(0) + abs(-300) = 300; available = 1200; eff_APAC = 1200
    assert abs(eff_l_halt - Decimal("1200")) < Decimal("0.01"), eff_l_halt
    assert abs(eff_e - Decimal("1200")) < Decimal("0.01"), eff_e


def test_idempotent_skips_when_session_already_opened_today():
    """If APAC already has session_opened_at populated for today, _initialize
    must skip (no second INSERT)."""
    sod = {
        "L_halt": Decimal("1500.00"),
        "E_daily_exposure": Decimal("1500.00"),
        "session": {
            "NY":   {"L_halt": Decimal("500"), "share": Decimal("0.333333"),
                     "E_daily_exposure": Decimal("500")},
            "LON":  {"L_halt": Decimal("500"), "share": Decimal("0.333333"),
                     "E_daily_exposure": Decimal("500")},
            "APAC": {"L_halt": Decimal("500"), "share": Decimal("0.333333"),
                     "E_daily_exposure": Decimal("500")},
        },
    }
    from datetime import datetime
    today_iso = datetime.now().isoformat()

    cursor = MockCursor([
        ("FROM p3_d08_tsm_state", [_make_d08_row("21855714", sod)]),
        # Earlier session SELECTs (LON + NY) — not actually consulted because
        # idempotency check fires first. We provide minimal stubs.
        ("WHERE account_id = %s AND session_id = %s",
         [(Decimal("0"), Decimal("500"), Decimal("500"), today_iso)]),
        ("WHERE account_id = %s AND session_id = %s",
         [(Decimal("0"), Decimal("500"), Decimal("500"), today_iso)]),
        # Idempotency check on APAC: existing row with session_opened_at set
        ("WHERE account_id = %s AND session_id = %s",
         [(Decimal("1200"), today_iso)]),
    ])

    with patch(
        "shared.questdb_client.get_cursor",
        lambda: _scripted_cursor(cursor),
    ):
        orch = _build_orchestrator()
        orch._initialize_session_budget(3)

    inserts = [(sql, p) for sql, p in cursor.inserts if "p3_d23" in sql]
    assert len(inserts) == 0, "must skip re-init when session already opened today"


def test_unknown_session_id_falls_through_to_legacy():
    """NY_PRE (session_id=4) is not in TRADING_DAY_SESSION_ORDER for v1.
    Method must return early without writing any D23 row."""
    cursor = MockCursor([])
    with patch(
        "shared.questdb_client.get_cursor",
        lambda: _scripted_cursor(cursor),
    ):
        orch = _build_orchestrator()
        orch._initialize_session_budget(4)
    assert cursor.inserts == []


def test_account_without_computed_sod_is_skipped():
    """An account that hasn't had Phase 2 SOD run (computed_sod missing) is
    skipped — legacy behaviour for that account on this session."""
    sod = {}  # no computed_sod
    payload = dumps_decimal({})  # empty topstep_state
    cursor = MockCursor([
        ("FROM p3_d08_tsm_state", [("21855714", payload)]),
    ])
    with patch(
        "shared.questdb_client.get_cursor",
        lambda: _scripted_cursor(cursor),
    ):
        orch = _build_orchestrator()
        orch._initialize_session_budget(2)
    assert [i for i in cursor.inserts if "p3_d23" in i[0]] == []
