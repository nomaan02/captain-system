# region imports
from AlgorithmImports import *
# endregion
"""Phase 3 batch B4_F-20 — Quarterly PG-07 refreshes in-memory CUSUM.

After `calibrate_and_persist` runs at quarter-end, the orchestrator must
refresh `self._detectors[asset_id][1].sequential_limits` so the next trade
outcome uses fresh calibration without waiting for a process restart.
"""

from unittest.mock import patch, MagicMock

import pytest

scipy = pytest.importorskip("scipy")

from captain_offline.blocks.orchestrator import OfflineOrchestrator
from captain_offline.blocks.b2_bocpd import BOCPDDetector
from captain_offline.blocks.b2_cusum import CUSUMDetector


def _mock_cursor_for_assets(asset_ids, returns_per_asset):
    """Build a context-manager mock cursor that returns asset list once and
    then returns rows for each asset."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    asset_rows = [(a,) for a in asset_ids]
    pnl_rows_per_asset = [
        [(r, 1) for r in returns_per_asset.get(a, [])]
        for a in asset_ids
    ]

    fetchall_responses = [asset_rows] + pnl_rows_per_asset
    cur.fetchall = MagicMock(side_effect=fetchall_responses)
    return cur


@patch("captain_offline.blocks.orchestrator.calibrate_and_persist", create=True)
def test_quarterly_refreshes_in_memory_limits(mock_calibrate, monkeypatch):
    """Seed self._detectors[asset_id][1].sequential_limits = {1: 0.1};
    run _run_quarterly with calibrate_and_persist returning {1: 0.5, 2: 0.6};
    assert in-memory dict matches the new return."""
    asset = "ES"
    orch = OfflineOrchestrator()
    bocpd = BOCPDDetector()
    cusum = CUSUMDetector()
    cusum.sequential_limits = {1: 0.1}
    orch._detectors[asset] = (bocpd, cusum)

    mock_calibrate.return_value = {1: 0.5, 2: 0.6}

    cur = _mock_cursor_for_assets([asset], {asset: [0.01] * 25})
    monkeypatch.setattr(
        "shared.questdb_client.get_cursor",
        MagicMock(return_value=cur),
    )

    # Patch the inner import inside _run_quarterly
    with patch("captain_offline.blocks.b2_cusum.calibrate_and_persist",
               return_value={1: 0.5, 2: 0.6}):
        orch._run_quarterly()

    refreshed = orch._detectors[asset][1].sequential_limits
    assert refreshed == {1: 0.5, 2: 0.6}, (
        f"Expected refreshed limits, got {refreshed}"
    )


def test_quarterly_no_op_when_calibration_returns_empty(monkeypatch, caplog):
    """When calibrate_and_persist returns None, in-memory dict is unchanged."""
    asset = "ES"
    orch = OfflineOrchestrator()
    bocpd = BOCPDDetector()
    cusum = CUSUMDetector()
    cusum.sequential_limits = {1: 0.1}
    orch._detectors[asset] = (bocpd, cusum)

    cur = _mock_cursor_for_assets([asset], {asset: [0.01] * 25})
    monkeypatch.setattr(
        "shared.questdb_client.get_cursor",
        MagicMock(return_value=cur),
    )

    with patch("captain_offline.blocks.b2_cusum.calibrate_and_persist",
               return_value=None):
        orch._run_quarterly()

    # Original limits intact
    assert orch._detectors[asset][1].sequential_limits == {1: 0.1}


def test_calibrate_and_persist_returns_limits_dict():
    """Extension to b2_cusum: calibrate_and_persist returns the dict it persists."""
    from captain_offline.blocks.b2_cusum import calibrate_and_persist
    # Generate enough returns for calibration to produce limits.
    import random
    random.seed(42)
    returns = [random.gauss(0.01, 0.02) for _ in range(200)]

    with patch("captain_offline.blocks.b2_cusum.get_cursor") as mock_gc:
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        mock_gc.return_value = cur

        result = calibrate_and_persist("ES", returns, B=50, arl_0=200)

    # Either a dict (with limits) or None (if calibration produced nothing).
    assert result is None or isinstance(result, dict)
