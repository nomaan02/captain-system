"""Regression test for Phase 2 D16 account-switch bug.

PRODUCTION ISSUE (2026-05-01)
-----------------------------
User switched their TopstepX account from `20319811` (PRAC) to
`21855714` (Trading Combine eval `150KTC-V2-551001-86041837`) and ran:

    BOOTSTRAP_ACCOUNT_ID=21855714 \
    BOOTSTRAP_USER_ID=primary_user \
    bootstrap_production.py

Phase 2 (D16 capital silo linkage) output:
    [SKIP] primary_user: silo already bootstrapped (capital=$150,000)

But D16 still showed:
    accounts: ["20319811"]   ← OLD account ID

ROOT CAUSE
----------
phase2_update_capital_silo's idempotency guard only checked
`starting_capital > 0`. It did NOT verify whether the existing
`accounts` JSON list contained the new BOOTSTRAP_ACCOUNT_ID. When the
user switched accounts, the function saw the existing silo and skipped,
leaving the OLD account ID in D16.

Downstream impact:
  * B4 Kelly sizing iterates over D16's `accounts` list to size positions
  * B6 signal output's per_account dict iterates over the same list
  * captain-online would have produced signals for the OLD (now-defunct)
    account_id and skipped the new one entirely
  * No trades would execute on the new account

FIX
---
Idempotency now checks accounts list membership:
  * Silo exists AND new ACCOUNT_ID in accounts -> SKIP
  * Silo exists but new ACCOUNT_ID NOT in accounts -> INSERT new D16 row
    with accounts=[ACCOUNT_ID] and capital reset to STARTING_CAPITAL
  * No silo -> INSERT new D16 row (unchanged behaviour)

Capital_history JSON preserves prior events and appends an
"account_switch" event with from_accounts and to_account fields for
audit trail.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def stub_questdb(monkeypatch):
    """Stub get_cursor with a programmable mock that captures executed SQL."""
    executed = []
    cursor_state = {"fetchone_return": None}

    class _StubCursor:
        def execute(self, sql, params=None):
            executed.append({"sql": sql, "params": params})
        def fetchone(self):
            return cursor_state["fetchone_return"]
        def __enter__(self): return self
        def __exit__(self, *args): pass

    from shared import questdb_client
    monkeypatch.setattr(questdb_client, "get_cursor", lambda: _StubCursor())
    return executed, cursor_state


@pytest.fixture(autouse=True)
def stub_module_globals(monkeypatch):
    """Set ACCOUNT_ID / USER_ID / STARTING_CAPITAL / MAX_SIMULTANEOUS_POSITIONS
    module globals (normally set from env vars at module import time)."""
    import scripts.bootstrap_production as bootstrap

    monkeypatch.setattr(bootstrap, "ACCOUNT_ID", "21855714", raising=False)
    monkeypatch.setattr(bootstrap, "USER_ID", "primary_user", raising=False)
    monkeypatch.setattr(bootstrap, "STARTING_CAPITAL", 150000, raising=False)
    monkeypatch.setattr(
        bootstrap, "MAX_SIMULTANEOUS_POSITIONS", 5, raising=False,
    )
    yield


# ---------------------------------------------------------------------------
# Bug scenario: silo exists with OLD account ID, user requests NEW account
# ---------------------------------------------------------------------------

class TestAccountSwitch:
    def test_old_account_silo_writes_new_d16_row_with_new_account(
        self, stub_questdb
    ):
        """The exact production scenario: D16 has accounts=['20319811'],
        bootstrap requested with ACCOUNT_ID=21855714 -> must INSERT new row."""
        executed, cursor_state = stub_questdb

        # First fetchone returns existing silo row with OLD account
        cursor_state["fetchone_return"] = (
            150000.0,                      # starting_capital
            json.dumps(["20319811"]),      # accounts (OLD)
            json.dumps([{"date": "2026-03-27", "event": "initial_bootstrap"}]),
        )

        from scripts.bootstrap_production import phase2_update_capital_silo
        phase2_update_capital_silo(dry_run=False)

        # Should have executed: 1 SELECT + 1 INSERT
        selects = [e for e in executed if "SELECT" in e["sql"]]
        inserts = [e for e in executed if "INSERT INTO p3_d16_user_capital_silos" in e["sql"]]
        assert len(selects) == 1
        assert len(inserts) == 1, (
            f"Expected an INSERT to register the new account; got 0. "
            f"All SQL executed: {[e['sql'][:60] for e in executed]}"
        )

        # The INSERT params must contain the NEW account ID
        insert_params = inserts[0]["params"]
        accounts_json = insert_params[3]  # accounts field is param index 3
        assert "21855714" in accounts_json
        assert "20319811" not in accounts_json, (
            "New D16 row should NOT contain the OLD account; "
            "user switched accounts."
        )

    def test_capital_history_records_account_switch(self, stub_questdb):
        """capital_history JSON must preserve prior events and append an
        account_switch event with from/to account IDs for audit trail."""
        executed, cursor_state = stub_questdb

        prior_history = [
            {"date": "2026-03-27", "event": "initial_bootstrap", "capital": 150000},
            {"date": "2026-04-15", "event": "manual_balance_correction"},
        ]
        cursor_state["fetchone_return"] = (
            150000.0,
            json.dumps(["20319811"]),
            json.dumps(prior_history),
        )

        from scripts.bootstrap_production import phase2_update_capital_silo
        phase2_update_capital_silo(dry_run=False)

        inserts = [e for e in executed if "INSERT INTO p3_d16_user_capital_silos" in e["sql"]]
        assert len(inserts) == 1
        history_json = inserts[0]["params"][5]  # capital_history is param 5
        history = json.loads(history_json)

        # Prior events preserved
        assert any(e.get("event") == "initial_bootstrap" for e in history)
        assert any(e.get("event") == "manual_balance_correction" for e in history)

        # New account_switch event appended
        switch = [e for e in history if e.get("event") == "account_switch"]
        assert len(switch) == 1
        assert switch[0]["from_accounts"] == ["20319811"]
        assert switch[0]["to_account"] == "21855714"


# ---------------------------------------------------------------------------
# True idempotency: silo with the SAME account already exists -> SKIP
# ---------------------------------------------------------------------------

class TestTrueIdempotency:
    def test_same_account_already_present_skips_insert(self, stub_questdb):
        """If silo already contains the requested ACCOUNT_ID, SKIP the
        INSERT. This preserves accumulated total_capital from realized PnL."""
        executed, cursor_state = stub_questdb

        cursor_state["fetchone_return"] = (
            150000.0,
            json.dumps(["21855714"]),  # same as ACCOUNT_ID
            json.dumps([]),
        )

        from scripts.bootstrap_production import phase2_update_capital_silo
        phase2_update_capital_silo(dry_run=False)

        inserts = [e for e in executed if "INSERT INTO p3_d16_user_capital_silos" in e["sql"]]
        assert len(inserts) == 0, "Should have skipped INSERT (true idempotent re-run)"

    def test_account_id_string_vs_int_matches(self, stub_questdb):
        """The accounts list might store IDs as strings or ints depending on
        how they were originally serialised. Both should match."""
        executed, cursor_state = stub_questdb

        # Existing accounts stored as INT
        cursor_state["fetchone_return"] = (
            150000.0,
            json.dumps([21855714]),  # int (not string)
            json.dumps([]),
        )

        from scripts.bootstrap_production import phase2_update_capital_silo
        phase2_update_capital_silo(dry_run=False)

        inserts = [e for e in executed if "INSERT INTO p3_d16_user_capital_silos" in e["sql"]]
        assert len(inserts) == 0, (
            "ACCOUNT_ID '21855714' (str) should match accounts [21855714] (int) "
            "after str() coercion in the membership check"
        )


# ---------------------------------------------------------------------------
# No silo exists -> standard insert (unchanged behaviour)
# ---------------------------------------------------------------------------

class TestNoExistingSilo:
    def test_inserts_new_silo_when_none_exists(self, stub_questdb):
        executed, cursor_state = stub_questdb

        cursor_state["fetchone_return"] = None  # no row

        from scripts.bootstrap_production import phase2_update_capital_silo
        phase2_update_capital_silo(dry_run=False)

        inserts = [e for e in executed if "INSERT INTO p3_d16_user_capital_silos" in e["sql"]]
        assert len(inserts) == 1
        accounts_json = inserts[0]["params"][3]
        assert "21855714" in accounts_json

        # capital_history should record initial_bootstrap event
        history_json = inserts[0]["params"][5]
        history = json.loads(history_json)
        assert any(e.get("event") == "initial_bootstrap" for e in history)
