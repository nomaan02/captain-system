# region imports
from AlgorithmImports import *
# endregion
"""Combined D04 persist (Phase 2 B2-2)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks.b2_bocpd import (
    BOCPDDetector,
    persist_combined_detector_state,
    run_bocpd_update,
)
from captain_offline.blocks.b2_cusum import (
    CUSUMDetector,
    calibrate_and_persist,
    run_cusum_update,
)
from captain_offline.blocks.b8_kelly_update import _get_cp_prob
from captain_offline.blocks.orchestrator import OfflineOrchestrator


def _register_mock_cursor():
    m = MagicMock()
    m.__enter__ = MagicMock(return_value=m)
    m.__exit__ = MagicMock(return_value=False)
    return m


@patch("captain_offline.blocks.b2_bocpd.get_cursor")
def test_persist_combined_writes_all_bocpd_cusum_columns(mock_get_cursor):
    bocpd_det = BOCPDDetector()
    bocpd_det.update(0.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    cusum_det.update(0.5)
    cur = _register_mock_cursor()
    mock_get_cursor.return_value = cur
    persist_combined_detector_state("ES", bocpd_det, cusum_det)
    cur.execute.assert_called()
    args = cur.execute.call_args[0]
    row = args[1]
    assert args[0].strip().startswith("INSERT INTO p3_d04_decay_detector_states")
    # parameter order: asset, bocpd_full_json, bocpd_cp, bocpd_hist, c_up, c_down, ...
    assert row[0] == "ES"
    assert json.loads(row[1])  # full BOCPD to_dict
    assert row[2] is not None
    assert row[3] is not None
    assert row[4] is not None
    assert row[9] == pytest.approx(float(bocpd_det.cp_probability), abs=1e-6)


@patch("captain_offline.blocks.b2_bocpd.get_cursor")
def test_run_bocpd_update_does_not_write_d04(mock_get_cursor):
    bocpd_det = BOCPDDetector()
    cur = _register_mock_cursor()
    mock_get_cursor.return_value = cur
    run_bocpd_update("ES", 0.5, bocpd_det)
    for call in cur.execute.call_args_list:
        sql = call[0][0] if call[0] else ""
        assert "p3_d04_decay_detector_states" not in sql


@patch("captain_offline.blocks.b2_cusum.get_cursor")
def test_run_cusum_update_does_not_write_d04(mock_get_cursor):
    det = CUSUMDetector(allowance=0.3)
    cur = _register_mock_cursor()
    mock_get_cursor.return_value = cur
    run_cusum_update("ES", 0.5, det)
    for call in cur.execute.call_args_list:
        sql = call[0][0] if call[0] else ""
        assert "p3_d04_decay_detector_states" not in sql


@patch("captain_offline.blocks.b8_kelly_update.get_cursor")
@patch("captain_offline.blocks.b8_kelly_update.get_redis_client")
def test_get_cp_prob_reads_non_null_changepoint_from_db(mock_get_redis, mock_get_cursor):
    mock_get_redis.return_value.get.return_value = None  # Redis miss → QuestDB path
    cur = _register_mock_cursor()
    mock_get_cursor.return_value = cur
    cur.fetchone.return_value = (0.37,)
    assert _get_cp_prob("ES") == pytest.approx(0.37, abs=1e-9)


@patch("shared.questdb_client.get_cursor")
def test_restore_detectors_recovers_both_states(mock_get_cursor):
    bocpd_det = BOCPDDetector()
    bocpd_det.update(0.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    cusum_det.update(0.8)
    bocpd_json = json.dumps(bocpd_det.to_dict())
    cusum_lim = json.dumps(cusum_det.to_dict()["sequential_limits"])
    cur = _register_mock_cursor()
    mock_get_cursor.return_value = cur
    cur.fetchall.return_value = [
        (
            "ES",
            bocpd_json,
            cusum_det.c_up,
            cusum_det.c_down,
            cusum_det.sprint_length,
            cusum_det.allowance,
            cusum_lim,
        )
    ]
    orch = OfflineOrchestrator()
    orch._restore_detectors()
    r_bocpd, r_cusum = orch._detectors["ES"]
    assert r_bocpd is not None
    assert r_cusum is not None
    assert r_bocpd.cp_probability == pytest.approx(bocpd_det.cp_probability, abs=1e-5)
    assert r_cusum.sprint_length == cusum_det.sprint_length


@patch("captain_offline.blocks.b2_cusum.calibrate_cusum_limits")
@patch("captain_offline.blocks.b2_cusum.get_cursor")
def test_calibrate_and_persist_still_writes_d04(
    mock_get_cursor, mock_calm_limits
):
    mock_calm_limits.return_value = {1: 1.0, 2: 1.1}
    cur = _register_mock_cursor()
    mock_get_cursor.return_value = cur
    calibrate_and_persist("ES", in_control_pnl=[0.1, -0.05, 0.2, -0.1] * 10)
    found = any(
        "p3_d04_decay_detector_states" in (c[0][0] or "")
        for c in cur.execute.call_args_list
    )
    assert found
    d04_calls = [
        c[0] for c in cur.execute.call_args_list
        if c[0] and "p3_d04_decay_detector_states" in c[0][0]
    ]
    assert d04_calls
