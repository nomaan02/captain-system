# region imports
from AlgorithmImports import *
# endregion
"""F-11: single observation gate for WARM_UP / ELIGIBLE / ACTIVE (Q-09)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from captain_offline.blocks.b1_aim_lifecycle import run_aim_lifecycle
from captain_offline.blocks.orchestrator import OfflineOrchestrator

ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_PY = ROOT / "captain-offline/captain_offline/blocks/b1_aim_lifecycle.py"

_WARMUP_STATE_BASE = {
    "aim_id": 1,
    "asset_id": "ES",
    "model_object": {},
    "warmup_progress": 0.3,
    "current_modifier": {},
    "last_retrained": None,
    "missing_data_rate_30d": 0,
}


def test_warmup_progresses_on_observations_alone():
    """WARM_UP → ELIGIBLE only when obs / required >= 1.0."""
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle._load_aim_states",
        return_value=[{**_WARMUP_STATE_BASE, "status": "WARM_UP"}],
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.warmup_required",
        return_value=10,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.observations_collected",
        return_value=9,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_warmup_progress",
    ) as mock_wu, patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_aim_status",
    ) as mock_st:
        run_aim_lifecycle("ES")
    mock_wu.assert_called()
    assert not any(c[0][2] == "ELIGIBLE" for c in mock_st.call_args_list)

    with patch(
        "captain_offline.blocks.b1_aim_lifecycle._load_aim_states",
        return_value=[{**_WARMUP_STATE_BASE, "status": "WARM_UP"}],
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.warmup_required",
        return_value=10,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.observations_collected",
        return_value=10,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_warmup_progress",
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_aim_status",
    ) as mock_st:
        run_aim_lifecycle("ES")
    assert any(c[0][2] == "ELIGIBLE" for c in mock_st.call_args_list)


def test_eligible_to_active_on_user_activation_alone():
    """ELIGIBLE → ACTIVE with zero trades if user activates (no learning gate)."""
    state = {
        **_WARMUP_STATE_BASE,
        "status": "ELIGIBLE",
    }
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle._load_aim_states",
        return_value=[state],
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.observations_collected",
        return_value=0,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_aim_status",
    ) as mock_st, patch(
        "captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update",
        MagicMock(),
    ):
        run_aim_lifecycle("ES", {1})
    assert any(c[0][2] == "ACTIVE" for c in mock_st.call_args_list)


def test_handle_aim_activation_unified_path():
    """GUI ACTIVATE_AIM routes through run_aim_lifecycle (single rule for ACTIVE)."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = [("ES",)]

    with patch(
        "captain_offline.blocks.b1_aim_lifecycle.run_aim_lifecycle",
    ) as mock_cycle, patch(
        "shared.questdb_client.get_cursor",
        return_value=cur,
    ):
        orch = OfflineOrchestrator()
        orch._handle_aim_activation({"type": "ACTIVATE_AIM", "aim_id": 1})

    mock_cycle.assert_called_once_with("ES", {1})


def test_no_dual_gate_residue():
    """No feat_progress / learn_progress identifiers in lifecycle module."""
    text = LIFECYCLE_PY.read_text(encoding="utf-8")
    assert "feat_progress" not in text
    assert "learn_progress" not in text


def test_warmup_skips_snapshot_when_progress_unchanged():
    """Same obs/progress as last D01 row — no _update_warmup_progress (no D01 snapshot)."""
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle._load_aim_states",
        return_value=[{**_WARMUP_STATE_BASE, "status": "WARM_UP", "warmup_progress": 0.9}],
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.warmup_required",
        return_value=10,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle.observations_collected",
        return_value=9,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_warmup_progress",
    ) as mock_wu, patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_aim_status",
    ) as mock_st:
        run_aim_lifecycle("ES")
    mock_wu.assert_not_called()
    assert not any(c[0][2] == "ELIGIBLE" for c in mock_st.call_args_list)
