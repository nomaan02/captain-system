# region imports
from AlgorithmImports import *
# endregion
"""Phase 3 batch B1_F-01 — SESSION_CLOSE dispatch (PG-01C).

Asserts:
1. SESSION_CLOSE command routes through `_handle_command` to
   `_handle_session_close` and triggers `_run_aim16_hmm_training`.
2. Idempotency: duplicate SESSION_CLOSE with same (session_id, closed_at)
   is deduped.
3. The skeleton training path calls `train_aim16_hmm` and
   `save_hmm_state` exactly once per session-close.
"""

from unittest.mock import patch, MagicMock

import pytest

pytest.importorskip("scipy")  # offline orchestrator transitively imports b2_bocpd

from captain_offline.blocks.orchestrator import OfflineOrchestrator


def _payload(session_id=1, closed_at="2026-04-27T16:00:00-04:00"):
    return {
        "type": "SESSION_CLOSE",
        "session_id": session_id,
        "closed_at": closed_at,
        "source": "tests.test_offline_session_close_dispatch",
    }


@patch("captain_offline.blocks.b1_aim16_hmm.save_hmm_state")
@patch("captain_offline.blocks.b1_aim16_hmm.train_aim16_hmm")
def test_session_close_command_dispatches_pg01c(mock_train, mock_save):
    """SESSION_CLOSE -> _handle_session_close -> _run_aim16_hmm_training."""
    mock_train.return_value = {
        "hmm_params": None,
        "current_state_probs": [1 / 3, 1 / 3, 1 / 3],
        "opportunity_weights": {},
        "prior_alpha": {},
        "smoothing_alpha": 0.3,
        "training_window": 60,
        "n_observations": 0,
        "cold_start": True,
    }

    orch = OfflineOrchestrator()
    orch._handle_command(_payload(session_id=1))

    assert mock_train.call_count == 1, "train_aim16_hmm should be called once"
    assert mock_save.call_count == 1, "save_hmm_state should be called once"

    # Cold-start: state passed to save_hmm_state has cold_start=True
    saved_state = mock_save.call_args[0][0]
    assert saved_state["cold_start"] is True


@patch("captain_offline.blocks.b1_aim16_hmm.save_hmm_state")
@patch("captain_offline.blocks.b1_aim16_hmm.train_aim16_hmm")
def test_session_close_idempotent_on_duplicate(mock_train, mock_save):
    """Two SESSION_CLOSE messages with the same token -> only one training run."""
    mock_train.return_value = {
        "hmm_params": None,
        "current_state_probs": [1 / 3, 1 / 3, 1 / 3],
        "opportunity_weights": {},
        "prior_alpha": {},
        "smoothing_alpha": 0.3,
        "training_window": 60,
        "n_observations": 0,
        "cold_start": True,
    }

    orch = OfflineOrchestrator()
    payload = _payload(session_id=42, closed_at="2026-04-27T16:00:00-04:00")
    orch._handle_command(payload)
    orch._handle_command(payload)  # duplicate

    assert mock_train.call_count == 1, (
        "Duplicate SESSION_CLOSE (same session_id+closed_at) must not retrain"
    )
    assert mock_save.call_count == 1


@patch("captain_offline.blocks.b1_aim16_hmm.save_hmm_state")
@patch("captain_offline.blocks.b1_aim16_hmm.train_aim16_hmm")
def test_session_close_global_not_per_asset(mock_train, mock_save):
    """One PG-01C dispatch per session close — not one per asset (Q-03 cadence)."""
    mock_train.return_value = {
        "hmm_params": None,
        "current_state_probs": [1 / 3, 1 / 3, 1 / 3],
        "opportunity_weights": {},
        "prior_alpha": {},
        "smoothing_alpha": 0.3,
        "training_window": 60,
        "n_observations": 0,
        "cold_start": True,
    }

    orch = OfflineOrchestrator()
    orch._handle_command(_payload(session_id=1, closed_at="2026-04-27T16:00:00-04:00"))

    # Even with 10 active assets, training fires exactly once per session close.
    assert mock_train.call_count == 1
    assert mock_save.call_count == 1
