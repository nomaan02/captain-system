# region imports
from AlgorithmImports import *
# endregion
"""Version snapshot calls before D01/D02 lifecycle writes (Phase 2 B2-1)."""

from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks.b1_aim_lifecycle import (
    _update_aim_status,
    _update_warmup_progress,
    run_tier_retrain,
)
from captain_offline.blocks.b1_hdwm_diversity import _reactivate_aim


@patch("captain_offline.blocks.b1_aim_lifecycle.get_cursor")
def test_update_aim_status_snapshots_before_insert(mock_get_cursor):
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update", MagicMock()
    ) as snap_mock:
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        _update_aim_status(aim_id=1, asset_id="ES", new_status="ACTIVE")
        snap_mock.assert_called_once_with("P3-D01", "AIM_LIFECYCLE")
        assert cur.execute.called


@patch("captain_offline.blocks.b1_aim_lifecycle.get_cursor")
@patch("shared.questdb_client.read_d00_row", return_value={})
@patch("shared.questdb_client.update_d00_fields")
def test_update_warmup_progress_snapshots_before_insert(
    _u1, _u2, mock_get_cursor
):
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update", MagicMock()
    ) as snap_mock:
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        _update_warmup_progress(aim_id=1, asset_id="ES", progress=0.5)
        snap_mock.assert_called_once_with("P3-D01", "AIM_LIFECYCLE")


@patch("captain_offline.blocks.b1_hdwm_diversity.get_cursor")
def test_reactivate_aim_snapshots_d01_and_d02(mock_get_cursor):
    with patch(
        "captain_offline.blocks.b1_hdwm_diversity.snapshot_before_update", MagicMock()
    ) as snap_mock:
        cur = MagicMock()
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        _reactivate_aim(aim_id=3, asset_id="ES", num_active=5)
        assert snap_mock.call_count == 2
        comps = [c[0][0] for c in snap_mock.call_args_list]
        assert "P3-D01" in comps
        assert "P3-D02" in comps
        for c in snap_mock.call_args_list:
            assert c[0][1] == "AIM_LIFECYCLE"


@patch("captain_offline.blocks.b1_aim_lifecycle.run_aim_lifecycle", MagicMock())
@patch("captain_offline.blocks.b1_aim_lifecycle.get_cursor")
def test_tier_retrain_snapshot_still_present(mock_get_cursor):
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update", MagicMock()
    ) as snap_mock:
        cur = MagicMock()
        cur.fetchone.return_value = ("ACTIVE",)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=cur)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        run_tier_retrain(asset_id="ES", aim_ids=[4])
        assert any(
            len(c[0]) >= 2 and c[0][1] == "AIM_RETRAIN"
            for c in snap_mock.call_args_list
        )
