# region imports
from AlgorithmImports import *
# endregion
"""F-19: BOCPD Level 2 material-delta re-fire (Δ = 0.05)."""

from unittest.mock import patch

import pytest

from captain_offline.blocks.b2_level_escalation import (
    check_level_escalation,
    _level2_active,
)


@pytest.fixture(autouse=True)
def clear_level2_state():
    _level2_active.clear()
    yield
    _level2_active.clear()


@patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
@patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
def test_first_crossing_fires_once(mock_l2, mock_l3):
    check_level_escalation("ES", 0.81, [0.7], "OK")
    mock_l2.assert_called_once_with("ES", 0.81, "BOCPD")
    mock_l3.assert_not_called()


@patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
@patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
def test_no_refire_below_delta(mock_l2, mock_l3):
    for cp in [0.81, 0.83, 0.85]:
        check_level_escalation("ES", cp, [cp], "OK")
    mock_l2.assert_called_once_with("ES", 0.81, "BOCPD")


@patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
@patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
def test_refire_at_delta(mock_l2, mock_l3):
    check_level_escalation("ES", 0.81, [0.81], "OK")
    check_level_escalation("ES", 0.86, [0.81, 0.86], "OK")
    assert mock_l2.call_count == 2
    mock_l2.assert_any_call("ES", 0.81, "BOCPD")
    mock_l2.assert_any_call("ES", 0.86, "BOCPD")


@patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
@patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
def test_monotonic_ramp_refires(mock_l2, mock_l3):
    seq = [0.81, 0.85, 0.86, 0.91]
    hist = []
    for cp in seq:
        hist.append(cp)
        check_level_escalation("ES", cp, hist, "OK")
    assert mock_l2.call_count == 3
    mock_l2.assert_any_call("ES", 0.81, "BOCPD")
    mock_l2.assert_any_call("ES", 0.86, "BOCPD")
    mock_l2.assert_any_call("ES", 0.91, "BOCPD")


@patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
@patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
def test_drop_below_threshold_resets(mock_l2, mock_l3):
    check_level_escalation("ES", 0.81, [0.81], "OK")
    check_level_escalation("ES", 0.79, [0.81, 0.79], "OK")
    check_level_escalation("ES", 0.82, [0.81, 0.79, 0.82], "OK")
    assert mock_l2.call_count == 2
    mock_l2.assert_any_call("ES", 0.81, "BOCPD")
    mock_l2.assert_any_call("ES", 0.82, "BOCPD")


@patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
@patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
def test_level3_takeover_then_fresh_level2(mock_l2, mock_l3):
    cp_history = [0.95] * 5
    check_level_escalation("ES", 0.95, cp_history, "OK")
    mock_l3.assert_called_once()
    mock_l2.reset_mock()
    mock_l3.reset_mock()
    check_level_escalation("ES", 0.81, [0.5, 0.5, 0.5, 0.5, 0.81], "OK")
    mock_l2.assert_called_once_with("ES", 0.81, "BOCPD")
