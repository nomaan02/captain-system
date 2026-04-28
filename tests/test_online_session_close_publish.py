# region imports
from AlgorithmImports import *
# endregion
"""Phase 3 batch B1_F-01 — Online publishes SESSION_CLOSE on STREAM_COMMANDS.

Asserts that `_run_session` publishes one SESSION_CLOSE message at session
end with the correct cmd type and session_id.
"""

from unittest.mock import patch, MagicMock

import pytest

pytest.importorskip("pysignalr")  # online b1_data_ingestion needs pysignalr (container-only)


@patch("captain_online.blocks.orchestrator.publish_to_stream")
def test_run_session_publishes_session_close(mock_publish):
    """When the legacy (non-OR) session pipeline completes, a SESSION_CLOSE
    is emitted on STREAM_COMMANDS exactly once."""
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    from shared.redis_client import STREAM_COMMANDS

    orch = OnlineOrchestrator.__new__(OnlineOrchestrator)
    # Minimal attributes needed to pass through _run_session legacy path
    orch._or_tracker = None
    orch._session_evaluated_today = {}
    orch._all_signals = []
    orch._pending_sessions = {}
    orch.plog = MagicMock()
    orch._publish_pipeline_stage = MagicMock()
    orch._circuit_breaker_check = MagicMock(return_value=True)
    orch._get_active_users = MagicMock(return_value=[])
    orch._load_user_silo = MagicMock(return_value=None)
    orch._process_user = MagicMock()
    orch._process_user_sizing = MagicMock(return_value=None)

    # Patch the heavy pipeline blocks the legacy path imports lazily.
    with patch("captain_online.blocks.b1_data_ingestion.run_data_ingestion") as mock_b1, \
         patch("captain_online.blocks.b2_regime_probability.run_regime_probability") as mock_b2, \
         patch("shared.aim_compute.run_aim_aggregation") as mock_b3, \
         patch("captain_online.blocks.b7_position_monitor.update_regime_cache"), \
         patch("captain_online.blocks.b9_capacity_evaluation.run_capacity_evaluation"):
        mock_b1.return_value = {
            "active_assets": ["ES"],
            "features": {},
            "regime_models": {},
            "aim_states": {},
            "aim_weights": {},
        }
        mock_b2.return_value = {"regime_probs": {}}
        mock_b3.return_value = {}

        orch._run_session(session_id=1)

    # At least one SESSION_CLOSE publish on STREAM_COMMANDS
    session_close_calls = [
        c for c in mock_publish.call_args_list
        if c[0][0] == STREAM_COMMANDS and c[0][1].get("type") == "SESSION_CLOSE"
    ]
    assert len(session_close_calls) == 1, (
        f"Expected exactly one SESSION_CLOSE publish, got "
        f"{len(session_close_calls)} (all calls: {mock_publish.call_args_list})"
    )

    payload = session_close_calls[0][0][1]
    assert payload["type"] == "SESSION_CLOSE"
    assert payload["session_id"] == 1
    assert "closed_at" in payload and payload["closed_at"], "closed_at must be set"
    assert "source" in payload
