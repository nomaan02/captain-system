"""Phase 7 — Tests for ``shared.trade_source.actual_trade_outcome``.

Covers PG-09 line 357 helper: realised P&L lookups by ``signal_id`` and
aggregate fallbacks by ``(user_id, asset, day)``.
"""
from __future__ import annotations

from datetime import date, datetime, time as _time
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from shared.trade_source import (
    RealisedOutcome,
    _aggregate_outcomes,
    _row_to_outcome,
    actual_trade_outcome,
)


_ET = ZoneInfo("America/New_York")


def _row(trade_id, signal_id, pnl, gross=None, commission=0.0, contracts=1,
         direction=1, regime="LOW_VOL", entry_time=None, exit_time=None,
         entry_price=100.0, exit_price=101.0):
    return (
        trade_id, signal_id, pnl,
        gross if gross is not None else pnl + commission,
        commission, contracts, entry_price, exit_price,
        entry_time, exit_time, direction, regime,
    )


def _patch_cursor(rows):
    """Build a context manager + cursor that returns ``rows`` on fetchall and
    rows[0] on fetchone."""
    cursor = MagicMock()
    cursor.fetchall.return_value = list(rows)
    cursor.fetchone.return_value = rows[0] if rows else None
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False
    return patch("shared.questdb_client.get_cursor", return_value=ctx), cursor


# --------------------------------------------------------------------------- #
# Row → outcome                                                               #
# --------------------------------------------------------------------------- #


def test_row_to_outcome_maps_fields():
    r = _row("TRD-1", "SIG-1", 12.5, gross=15.0, commission=2.5, contracts=2)
    out = _row_to_outcome(r)
    assert isinstance(out, RealisedOutcome)
    assert out.trade_id == "TRD-1"
    assert out.signal_id == "SIG-1"
    assert out.pnl == 12.5
    assert out.gross_pnl == 15.0
    assert out.commission == 2.5
    assert out.contracts == 2


# --------------------------------------------------------------------------- #
# Aggregate outcomes                                                          #
# --------------------------------------------------------------------------- #


def test_aggregate_sums_pnl_gross_commission_and_contracts():
    rows = [
        _row("TRD-1", "SIG-1", 10.0, gross=12.0, commission=2.0, contracts=1),
        _row("TRD-2", "SIG-2", 20.0, gross=22.0, commission=2.0, contracts=2),
        _row("TRD-3", "SIG-3", -5.0, gross=-3.0, commission=2.0, contracts=1),
    ]
    out = _aggregate_outcomes(rows)
    assert out.pnl == 25.0
    assert out.gross_pnl == 31.0
    assert out.commission == 6.0
    assert out.contracts == 4
    assert out.signal_id == "SIG-1"  # first


# --------------------------------------------------------------------------- #
# actual_trade_outcome (signal_id path)                                       #
# --------------------------------------------------------------------------- #


def test_lookup_by_signal_id_returns_matching_row():
    row = _row("TRD-1", "SIG-EXACT", 12.5)
    p, _ = _patch_cursor([row])
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", signal_id="SIG-EXACT",
        )
    assert out is not None
    assert out.signal_id == "SIG-EXACT"
    assert out.pnl == 12.5


def test_lookup_by_signal_id_missing_returns_none():
    p, _ = _patch_cursor([])
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", signal_id="SIG-MISSING",
        )
    assert out is None


def test_lookup_by_signal_id_uses_correct_query_window():
    """Entry-time predicate is the calendar day in America/New_York."""
    captured = {}

    def _exec(sql, args=None):
        captured["sql"] = sql
        captured["args"] = args

    cursor = MagicMock()
    cursor.execute.side_effect = _exec
    cursor.fetchone.return_value = None
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False
    with patch("shared.questdb_client.get_cursor", return_value=ctx):
        actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", signal_id="SIG-1",
        )
    sig_id, user_id, start, end = captured["args"]
    assert sig_id == "SIG-1"
    assert user_id == "u1"
    # Start is 2026-01-15 00:00 ET, end is 2026-01-16 00:00 ET
    assert start.startswith("2026-01-15T00:00")
    assert end.startswith("2026-01-16T00:00")


# --------------------------------------------------------------------------- #
# actual_trade_outcome (aggregate path)                                       #
# --------------------------------------------------------------------------- #


def test_aggregate_path_requires_asset():
    """Without signal_id and without asset → ValueError."""
    with pytest.raises(ValueError):
        actual_trade_outcome(date(2026, 1, 15), user_id="u1")


def test_aggregate_path_returns_composite_for_multiple_rows():
    rows = [
        _row("TRD-1", "SIG-1", 10.0, gross=12.0, commission=2.0, contracts=1),
        _row("TRD-2", "SIG-2", 5.0, gross=7.0, commission=2.0, contracts=2),
    ]
    p, _ = _patch_cursor(rows)
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", asset="ES",
        )
    assert out is not None
    assert out.pnl == 15.0
    assert out.contracts == 3


def test_aggregate_path_returns_single_when_one_row():
    """Single row goes through ``_row_to_outcome`` directly, not aggregator."""
    rows = [_row("TRD-ONLY", "SIG-ONLY", 7.5)]
    p, _ = _patch_cursor(rows)
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", asset="ES",
        )
    assert out is not None
    assert out.pnl == 7.5
    assert out.signal_id == "SIG-ONLY"


def test_aggregate_path_returns_none_when_empty():
    p, _ = _patch_cursor([])
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", asset="ES",
        )
    assert out is None


# --------------------------------------------------------------------------- #
# LEGACY signal_id round-trip                                                 #
# --------------------------------------------------------------------------- #


def test_lookup_with_legacy_prefix_signal_id():
    """LEGACY-prefixed IDs (from the backfill) are queryable like any other."""
    row = _row("TRD-LEG", "LEGACY-abc-123", 0.0)
    p, _ = _patch_cursor([row])
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", signal_id="LEGACY-abc-123",
        )
    assert out is not None
    assert out.signal_id == "LEGACY-abc-123"


# --------------------------------------------------------------------------- #
# Realised vs gross                                                           #
# --------------------------------------------------------------------------- #


def test_outcome_returns_net_pnl():
    """``pnl`` is net (gross - commission)."""
    row = _row("TRD-1", "SIG-1", 95.0, gross=100.0, commission=5.0)
    p, _ = _patch_cursor([row])
    with p:
        out = actual_trade_outcome(
            date(2026, 1, 15), user_id="u1", signal_id="SIG-1",
        )
    assert out is not None
    assert out.pnl == 95.0
    assert out.gross_pnl == 100.0
    assert out.commission == 5.0
