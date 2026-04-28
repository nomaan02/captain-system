# region imports
from AlgorithmImports import *
# endregion
"""F-09: DMA loads D02 only for AIMs with latest D01 status ACTIVE."""

from unittest.mock import MagicMock, patch

from captain_offline.blocks.b1_dma_update import _load_active_aims, run_dma_update


def _ctx_cursor(cursor: MagicMock):
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


@patch("captain_offline.blocks.b1_dma_update.get_cursor")
def test_dma_excludes_warm_up_aims(mock_get_cursor):
    """Only ACTIVE AIM-1 appears in _load_active_aims for mixed D01 statuses."""
    cur_d01 = MagicMock()
    cur_d01.fetchall.return_value = [(1,)]
    cur_d01 = _ctx_cursor(cur_d01)

    cur_d02 = MagicMock()
    cur_d02.fetchall.return_value = [
        (1, 0.25, True, 0.1, 0),
    ]
    cur_d02 = _ctx_cursor(cur_d02)

    mock_get_cursor.side_effect = [cur_d01, cur_d02]

    rows = _load_active_aims("ES")
    assert [r["aim_id"] for r in rows] == [1]
    assert len(rows) == 1


@patch("captain_offline.blocks.b1_dma_update.snapshot_before_update", MagicMock())
@patch("captain_offline.blocks.b1_dma_update.get_cursor")
def test_dma_normalisation_only_over_active(mock_get_cursor):
    """run_dma_update normalises proposed_weights over ACTIVE AIMs only."""
    cur_d01 = _ctx_cursor(MagicMock())
    cur_d01.fetchall.return_value = [(1,)]

    cur_d02 = _ctx_cursor(MagicMock())
    cur_d02.fetchall.return_value = [
        (1, 0.5, True, 0.1, 0),
    ]

    cur_ewma = _ctx_cursor(MagicMock())
    cur_ewma.fetchall.return_value = [
        ("S1", 0.5, 100.0, 50.0, 10),
    ]

    mock_get_cursor.side_effect = [cur_d01, cur_d02, cur_ewma]

    outcome = {
        "asset": "ES",
        "pnl": 100.0,
        "contracts": 1,
        "regime_at_entry": "LOW_VOL",
        "aim_breakdown_at_entry": {"1": {"modifier": 1.1}},
    }
    result = run_dma_update(outcome, commit=False)
    assert set(result["proposed_weights"].keys()) == {1}
    assert abs(sum(result["proposed_weights"].values()) - 1.0) < 1e-6


@patch("captain_offline.blocks.b1_dma_update.get_cursor")
def test_dma_empty_active_set_returns_empty(mock_get_cursor):
    """No ACTIVE D01 rows → early exit with empty dict."""
    cur_d01 = _ctx_cursor(MagicMock())
    cur_d01.fetchall.return_value = []

    mock_get_cursor.side_effect = [cur_d01]

    outcome = {
        "asset": "ES",
        "pnl": 50.0,
        "contracts": 1,
        "regime_at_entry": "LOW_VOL",
        "aim_breakdown_at_entry": {},
    }
    assert run_dma_update(outcome, commit=False) == {}
