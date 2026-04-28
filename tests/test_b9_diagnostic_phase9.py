"""Phase 9 Block 9 diagnostic — plans B1–B4 (Q-19..Q-21, Q-34)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks import b9_diagnostic as b9


ET = timezone(timedelta(hours=-5))


@pytest.fixture
def fixed_now():
    return datetime(2026, 6, 15, 16, 0, 0, tzinfo=ET)


def _ctx_cursor(mock_cur):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_cur)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_compute_d3_never_queries_global_injection_history(fixed_now):
    """B1: D3 staleness must not use p3_d06 max(ts) for scoring (F-35)."""
    recent = (fixed_now - timedelta(days=10)).isoformat()
    stale_ts = (fixed_now - timedelta(days=100)).isoformat()

    executed: list[str] = []

    mock_cur = MagicMock()

    def exec_side(sql, params=None):
        executed.append(sql)

    mock_cur.execute.side_effect = exec_side

    # Ordered fetchall/fetchone responses matching compute_d3 + _active_asset_p1p2_stale_days
    fetchall_seq = [
        [("ES",), ("NQ",)],  # active assets (call 1)
        [("ES", recent), ("NQ", stale_ts)],  # d22b (call 2)
        [
            ("ES", json.dumps({"timestamp": recent}), fixed_now.isoformat()),
            ("NQ", json.dumps({"timestamp": recent}), fixed_now.isoformat()),
        ],  # p3_d00 (call 3)
        [("ES", recent), ("NQ", stale_ts)],  # d22b again (call 4)
        [(1, fixed_now.isoformat())],  # aim rows (call 5)
    ]
    seq = iter(fetchall_seq)

    def fetchall():
        return next(seq)

    mock_cur.fetchall.side_effect = fetchall

    with patch.object(b9, "now_et", return_value=fixed_now):
        with patch.object(b9, "get_cursor", return_value=_ctx_cursor(mock_cur)):
            aq: list = []
            score = b9.compute_d3(aq)

    joined = " ".join(executed)
    assert "p3_d06_injection_history" not in joined
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_modifier_pnl_hit_basic():
    """Q-20 directional agreement (neutral modifier skipped)."""
    assert b9._modifier_pnl_hit(1.1, 50.0) is True
    assert b9._modifier_pnl_hit(1.1, -10.0) is False
    assert b9._modifier_pnl_hit(0.9, -20.0) is True
    assert b9._modifier_pnl_hit(0.9, 30.0) is False
    assert b9._modifier_pnl_hit(1.0, 100.0) is None


def test_overall_health_equal_weight_weekly_monthly():
    """Q-34: explicit 1/N over declared keys."""
    wscores = {k: 0.2 for k in b9.OVERALL_HEALTH_KEYS_WEEKLY}
    assert abs(b9._overall_health_equal_weight(wscores, "WEEKLY") - 0.2) < 1e-9

    mscores = {k: 0.1 for k in b9.OVERALL_HEALTH_KEYS_MONTHLY}
    assert abs(b9._overall_health_equal_weight(mscores, "MONTHLY") - 0.1) < 1e-9


@patch("captain_offline.blocks.b9_diagnostic.compute_d8", return_value=0.5)
@patch("captain_offline.blocks.b9_diagnostic.compute_d6", return_value=0.6)
@patch("captain_offline.blocks.b9_diagnostic.compute_d4", return_value=0.4)
@patch("captain_offline.blocks.b9_diagnostic.compute_d3", return_value=0.3)
@patch("captain_offline.blocks.b9_diagnostic.compute_d2", return_value=0.2)
@patch("captain_offline.blocks.b9_diagnostic.compute_d1", return_value=0.1)
@patch("captain_offline.blocks.b9_diagnostic.get_cursor")
def test_run_diagnostic_weekly_no_research_pipeline_key(
    mock_get_cursor,
    _mock_d1,
    _mock_d2,
    _mock_d3,
    _mock_d4,
    _mock_d6,
    _mock_d8,
):
    """B3: scores must omit research_pipeline / D7."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = (json.dumps([]),)
    mock_get_cursor.return_value = cur

    out = b9.run_diagnostic(mode="WEEKLY")
    assert "research_pipeline" not in out["scores"]
    expected_mean = sum([0.1, 0.2, 0.3, 0.4, 0.6, 0.5]) / 6.0
    assert abs(out["overall_health"] - expected_mean) < 1e-9


@patch("captain_offline.blocks.b9_diagnostic.compute_d8", return_value=0.5)
@patch("captain_offline.blocks.b9_diagnostic.compute_d6", return_value=0.6)
@patch("captain_offline.blocks.b9_diagnostic.compute_d5", return_value=0.55)
@patch("captain_offline.blocks.b9_diagnostic.compute_d4", return_value=0.4)
@patch("captain_offline.blocks.b9_diagnostic.compute_d3", return_value=0.3)
@patch("captain_offline.blocks.b9_diagnostic.compute_d2", return_value=0.2)
@patch("captain_offline.blocks.b9_diagnostic.compute_d1", return_value=0.1)
@patch("captain_offline.blocks.b9_diagnostic.get_cursor")
def test_run_diagnostic_monthly_includes_edge_in_mean(
    mock_get_cursor,
    _mock_d1,
    _mock_d2,
    _mock_d3,
    _mock_d4,
    _mock_d5,
    _mock_d6,
    _mock_d8,
):
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = (json.dumps([]),)
    mock_get_cursor.return_value = cur

    out = b9.run_diagnostic(mode="MONTHLY")
    assert "edge_trajectory" in out["scores"]
    expected_mean = sum([0.1, 0.2, 0.3, 0.4, 0.55, 0.6, 0.5]) / 7.0
    assert abs(out["overall_health"] - expected_mean) < 1e-9


def test_compute_d4_monthly_window_sql_uses_trade_outcome_only(fixed_now):
    """B2: D4 reads P3-D03 only (monthly window); smoke-check SQL fragment."""
    captured: list[str] = []

    mock_cur = MagicMock()

    def exec_side(sql, params=None):
        captured.append(sql)

    mock_cur.execute.side_effect = exec_side
    mock_cur.fetchall.return_value = []

    with patch.object(b9, "now_et", return_value=fixed_now):
        with patch.object(b9, "get_cursor", return_value=_ctx_cursor(mock_cur)):
            b9.compute_d4([])

    joined = " ".join(captured)
    assert "p3_d03_trade_outcome_log" in joined
    assert "p3_d02_aim_meta_weights" not in joined
