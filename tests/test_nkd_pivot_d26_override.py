"""Tests for C12 — scripts/nkd_pivot_d26_override.py.

Verifies:
1. apply_override() with default args INSERTs the locked NKD-pivot values
   (NY=0.10, LON=0.10, APAC=0.80; cold_start=False; n_observations=60).
2. apply_override(revert=True) writes a cold-start row with equal 1/3 shares.
3. shared.sod_session_budget.session_budget_shares returns (0.10, 0.10, 0.80)
   when given a Python dict equivalent to the post-override row.
4. The script is idempotent — running twice produces identical written values.

DB IO is mocked. These tests do not require a live QuestDB.
"""

import json
from unittest.mock import patch, MagicMock
from decimal import Decimal

import pytest

from scripts.nkd_pivot_d26_override import (
    apply_override,
    NKD_PIVOT_WEIGHTS,
    NKD_PIVOT_N_OBS,
    NKD_PIVOT_TRAINING_WINDOW,
)
from shared.sod_session_budget import session_budget_shares


class _FakeCursor:
    """Tiny stand-in for shared.questdb_client.get_cursor's context manager.

    Captures (sql, params) of each execute/qexecute call into a list shared
    across all instances inside one test so we can assert against them.
    """

    def __init__(self, calls: list, fetch_rows: list[tuple] | None):
        self._calls = calls
        self._fetch_rows = fetch_rows or []
        self._next_row_idx = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self._calls.append(("execute", sql, params))

    def fetchone(self):
        if self._next_row_idx >= len(self._fetch_rows):
            return None
        row = self._fetch_rows[self._next_row_idx]
        self._next_row_idx += 1
        return row


@pytest.fixture
def captured_calls(monkeypatch):
    """Patch get_cursor and qexecute so tests can introspect what was written."""
    calls: list = []

    # 1 SELECT call returns None (no prior D26 row), then any further fetches
    # also return None — this is the common-case at test time.
    def fake_get_cursor():
        return _FakeCursor(calls, fetch_rows=[None, None])

    def fake_qexecute(cursor, sql, params):
        calls.append(("qexecute", sql, params))

    monkeypatch.setattr("scripts.nkd_pivot_d26_override.get_cursor", fake_get_cursor)
    monkeypatch.setattr("scripts.nkd_pivot_d26_override.qexecute", fake_qexecute)
    return calls


class TestApplyOverrideDefault:
    """apply_override() with default args writes the locked NKD-pivot row."""

    def test_returns_locked_values(self, captured_calls):
        result = apply_override()
        assert result["opportunity_weights"] == {"NY": 0.10, "LON": 0.10, "APAC": 0.80}
        assert result["n_observations"] == NKD_PIVOT_N_OBS == 60
        assert result["cold_start"] is False

    def test_calls_qexecute_with_correct_sql(self, captured_calls):
        apply_override()
        qexecute_calls = [c for c in captured_calls if c[0] == "qexecute"]
        assert len(qexecute_calls) == 1
        _, sql, params = qexecute_calls[0]
        assert "INSERT INTO p3_d26_hmm_opportunity_state" in sql

    def test_opportunity_weights_serialised_as_json_string(self, captured_calls):
        apply_override()
        _, _, params = next(c for c in captured_calls if c[0] == "qexecute")
        opportunity_weights_json = params[2]
        parsed = json.loads(opportunity_weights_json)
        assert parsed == {"NY": 0.10, "LON": 0.10, "APAC": 0.80}

    def test_cold_start_false(self, captured_calls):
        apply_override()
        _, _, params = next(c for c in captured_calls if c[0] == "qexecute")
        cold_start = params[6]
        assert cold_start is False

    def test_n_observations_is_60(self, captured_calls):
        apply_override()
        _, _, params = next(c for c in captured_calls if c[0] == "qexecute")
        n_obs = params[5]
        assert n_obs == 60

    def test_training_window_is_60(self, captured_calls):
        apply_override()
        _, _, params = next(c for c in captured_calls if c[0] == "qexecute")
        training_window = params[4]
        assert training_window == NKD_PIVOT_TRAINING_WINDOW == 60


class TestApplyOverrideRevert:
    """apply_override(revert=True) restores cold-start equal 1/3 shares."""

    def test_returns_cold_start_values(self, captured_calls):
        result = apply_override(revert=True)
        assert result["opportunity_weights"] == {}
        assert result["n_observations"] == 0
        assert result["cold_start"] is True

    def test_opportunity_weights_empty_dict_on_revert(self, captured_calls):
        apply_override(revert=True)
        _, _, params = next(c for c in captured_calls if c[0] == "qexecute")
        opportunity_weights_json = params[2]
        assert json.loads(opportunity_weights_json) == {}

    def test_cold_start_true_on_revert(self, captured_calls):
        apply_override(revert=True)
        _, _, params = next(c for c in captured_calls if c[0] == "qexecute")
        cold_start = params[6]
        assert cold_start is True


class TestSessionBudgetSharesAfterOverride:
    """Integration: session_budget_shares() returns (0.10, 0.10, 0.80) post-override."""

    def test_full_hmm_branch_returns_locked_shares(self):
        """When the override row is read back as a hmm_state dict, the budget
        helper should produce the locked NKD-pivot shares verbatim."""
        hmm_state = {
            "n_observations": NKD_PIVOT_N_OBS,
            "cold_start": False,
            "opportunity_weights": NKD_PIVOT_WEIGHTS,
        }
        shares = session_budget_shares(hmm_state)
        assert shares["NY"] == pytest.approx(Decimal("0.10"), abs=Decimal("1e-9"))
        assert shares["LON"] == pytest.approx(Decimal("0.10"), abs=Decimal("1e-9"))
        assert shares["APAC"] == pytest.approx(Decimal("0.80"), abs=Decimal("1e-9"))
        total = shares["NY"] + shares["LON"] + shares["APAC"]
        assert total == pytest.approx(Decimal("1.0"), abs=Decimal("1e-9"))

    def test_cold_start_revert_returns_equal_shares(self):
        """Reverted state returns equal 1/3 shares."""
        hmm_state = {
            "n_observations": 0,
            "cold_start": True,
            "opportunity_weights": {},
        }
        shares = session_budget_shares(hmm_state)
        expected = Decimal("1") / Decimal("3")
        assert shares["NY"] == pytest.approx(expected, abs=Decimal("1e-9"))
        assert shares["LON"] == pytest.approx(expected, abs=Decimal("1e-9"))
        assert shares["APAC"] == pytest.approx(expected, abs=Decimal("1e-9"))


class TestIdempotency:
    """Running the script twice produces the same written values."""

    def test_two_calls_emit_same_params(self, captured_calls):
        apply_override()
        # Snapshot the qexecute params from the first call
        first_qexec = next(c for c in captured_calls if c[0] == "qexecute")
        captured_calls.clear()

        apply_override()
        second_qexec = next(c for c in captured_calls if c[0] == "qexecute")
        # SQL and params (except for the now() server-side defaults) must match
        assert first_qexec[1] == second_qexec[1]
        assert first_qexec[2] == second_qexec[2]
