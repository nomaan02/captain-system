# region imports
from AlgorithmImports import *
# endregion
"""Phase 3 batch B6_F-42 — Level 3 immediate-dispatch of AIM14_EXPANSION.

When `check_level_escalation` returns a Level 3 result, the orchestrator
must call `_dispatch_pending_jobs(filter_job_type="AIM14_EXPANSION",
filter_asset=asset_id)` in the same call frame — not wait up to ~24h for
the next daily tick.

P1P2_RERUN must remain `AWAITING_MANUAL` (preserves F-21 by-design).
"""

from unittest.mock import patch, MagicMock

import pytest

pytest.importorskip("scipy")  # b2_bocpd needs scipy

from captain_offline.blocks.orchestrator import OfflineOrchestrator


def test_trigger_level3_returns_dict_with_level_3():
    """trigger_level3 returns a dict with `level=3` and `enqueued`."""
    from captain_offline.blocks.b2_level_escalation import trigger_level3
    with patch("captain_offline.blocks.b2_level_escalation._set_captain_status_decayed"), \
         patch("captain_offline.blocks.b2_level_escalation._log_decay_event"), \
         patch("captain_offline.blocks.b2_level_escalation._publish_alert"), \
         patch("captain_offline.blocks.b2_level_escalation._enqueue_job"):
        result = trigger_level3("ES", "BOCPD_sustained")

    assert isinstance(result, dict)
    assert result.get("level") == 3
    assert result.get("l3_triggered") is True
    assert result.get("asset_id") == "ES"
    assert "AIM14_EXPANSION" in result.get("enqueued", [])
    assert "P1P2_RERUN" in result.get("enqueued", [])


def test_check_level_escalation_returns_none_when_below_l3():
    """No L3 trigger -> returns None."""
    from captain_offline.blocks.b2_level_escalation import check_level_escalation, _level2_active
    _level2_active.clear()
    result = check_level_escalation("ES", cp_probability=0.1, cp_history=[0.1] * 10,
                                    cusum_signal="OK")
    assert result is None


def test_l3_trigger_dispatches_aim14_immediately():
    """Sustained high cp_prob -> Level 3 -> immediate-dispatch fires."""
    from captain_offline.blocks.b2_level_escalation import _level2_active
    _level2_active.clear()

    orch = OfflineOrchestrator()
    # Mock dependencies that _handle_trade_outcome touches.
    orch._pseudotrader_gate = MagicMock(return_value=False)
    orch._is_trivial_dma_change = MagicMock(return_value=True)
    orch._is_trivial_kelly_change = MagicMock(return_value=True)
    orch._run_tsm_for_account = MagicMock()
    orch._dispatch_pending_jobs = MagicMock()

    # Build a BOCPD detector whose cp_history is sustained-high so Level 3 fires.
    from captain_offline.blocks.b2_bocpd import BOCPDDetector
    from captain_offline.blocks.b2_cusum import CUSUMDetector
    bocpd = BOCPDDetector()
    bocpd.cp_history = [0.99] * 30  # exceed LEVEL3_SUSTAINED_WINDOW with high cp_prob
    cusum = CUSUMDetector()
    orch._detectors["ES"] = (bocpd, cusum)

    outcome = {"asset": "ES", "pnl": -100.0, "contracts": 1,
               "account": "TEST", "model": 4}

    with patch("captain_offline.blocks.b1_dma_update.run_dma_update", return_value=None), \
         patch("captain_offline.blocks.b2_bocpd.run_bocpd_update",
               return_value=(0.99, bocpd)), \
         patch("captain_offline.blocks.b2_bocpd.persist_combined_detector_state"), \
         patch("captain_offline.blocks.b2_cusum.run_cusum_update",
               return_value=("OK", cusum)), \
         patch("captain_offline.blocks.b2_level_escalation._set_captain_status_decayed"), \
         patch("captain_offline.blocks.b2_level_escalation._log_decay_event"), \
         patch("captain_offline.blocks.b2_level_escalation._publish_alert"), \
         patch("captain_offline.blocks.b2_level_escalation._enqueue_job"), \
         patch("captain_offline.blocks.b8_kelly_update.run_kelly_update", return_value=None), \
         patch("captain_offline.blocks.b8_cb_params.estimate_cb_params"):
        orch._handle_trade_outcome(outcome)

    # immediate-dispatch should have been called with AIM14_EXPANSION + filter_asset
    dispatch_calls = orch._dispatch_pending_jobs.call_args_list
    aim14_calls = [
        c for c in dispatch_calls
        if c.kwargs.get("filter_job_type") == "AIM14_EXPANSION"
        and c.kwargs.get("filter_asset") == "ES"
    ]
    assert len(aim14_calls) == 1, (
        f"Expected one AIM14_EXPANSION immediate-dispatch, got {dispatch_calls}"
    )


def test_l2_does_not_immediate_dispatch():
    """Level 2 only -> no immediate AIM14_EXPANSION dispatch."""
    from captain_offline.blocks.b2_level_escalation import _level2_active
    _level2_active.clear()

    orch = OfflineOrchestrator()
    orch._pseudotrader_gate = MagicMock(return_value=False)
    orch._is_trivial_dma_change = MagicMock(return_value=True)
    orch._is_trivial_kelly_change = MagicMock(return_value=True)
    orch._run_tsm_for_account = MagicMock()
    orch._dispatch_pending_jobs = MagicMock()

    from captain_offline.blocks.b2_bocpd import BOCPDDetector
    from captain_offline.blocks.b2_cusum import CUSUMDetector
    bocpd = BOCPDDetector()
    bocpd.cp_history = [0.85, 0.6, 0.4, 0.85]  # cp_prob > 0.8 but not sustained
    cusum = CUSUMDetector()
    orch._detectors["ES"] = (bocpd, cusum)

    outcome = {"asset": "ES", "pnl": -100.0, "contracts": 1,
               "account": "TEST", "model": 4}

    with patch("captain_offline.blocks.b1_dma_update.run_dma_update", return_value=None), \
         patch("captain_offline.blocks.b2_bocpd.run_bocpd_update",
               return_value=(0.85, bocpd)), \
         patch("captain_offline.blocks.b2_bocpd.persist_combined_detector_state"), \
         patch("captain_offline.blocks.b2_cusum.run_cusum_update",
               return_value=("OK", cusum)), \
         patch("captain_offline.blocks.b2_level_escalation.trigger_level2"), \
         patch("captain_offline.blocks.b8_kelly_update.run_kelly_update", return_value=None), \
         patch("captain_offline.blocks.b8_cb_params.estimate_cb_params"):
        orch._handle_trade_outcome(outcome)

    # No AIM14 immediate-dispatch
    dispatch_calls = orch._dispatch_pending_jobs.call_args_list
    aim14_calls = [
        c for c in dispatch_calls
        if c.kwargs.get("filter_job_type") == "AIM14_EXPANSION"
    ]
    assert len(aim14_calls) == 0, (
        f"L2 should not trigger immediate AIM14 dispatch, got {dispatch_calls}"
    )


def test_dispatch_filter_excludes_p1p2_rerun():
    """immediate-dispatch with filter_job_type='AIM14_EXPANSION' should
    not touch P1P2_RERUN — preserves F-21 AWAITING_MANUAL behaviour."""
    orch = OfflineOrchestrator()

    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall = MagicMock(return_value=[])  # no AIM14 jobs in this stub

    captured_sql = {}

    def _exec(sql, params=None):
        captured_sql["sql"] = sql
        captured_sql["params"] = params

    cur.execute = MagicMock(side_effect=_exec)

    with patch("shared.questdb_client.get_cursor", MagicMock(return_value=cur)):
        orch._dispatch_pending_jobs(
            filter_job_type="AIM14_EXPANSION", filter_asset="ES",
        )

    assert "AIM14_EXPANSION" in str(captured_sql.get("params", ""))
    # SQL must not name P1P2_RERUN at all in the WHERE clause.
    assert "P1P2_RERUN" not in captured_sql.get("sql", ""), (
        "filter_job_type should not include P1P2_RERUN — preserves F-21"
    )
