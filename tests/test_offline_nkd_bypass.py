"""Q2-B-strict captain-offline NKD outcome bypass tests.

The offline orchestrator's ``_handle_trade_outcome`` and
``_handle_signal_outcome`` must NOT run DMA/BOCPD/CUSUM/Level/Kelly/CB/TSM
on an NKD outcome — NKD is fixed-strategy per audit §2 Q2.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks import orchestrator as offline_orch
from captain_offline.blocks.orchestrator import OfflineOrchestrator


def _make_orchestrator():
    """Build a minimal OfflineOrchestrator with stubbed I/O surfaces.

    We don't need a real Redis / QuestDB — the bypass branch fires on the
    asset name alone, before any downstream call.
    """
    orch = OfflineOrchestrator.__new__(OfflineOrchestrator)
    # Stub the few instance attributes the early code path touches.
    orch.plog = MagicMock()
    orch.plog.info = MagicMock()
    orch.plog.warn = MagicMock()
    orch._detectors = {}
    orch.running = True
    return orch


def test_handle_trade_outcome_nkd_skips_learning():
    """NKD outcome must short-circuit before DMA/BOCPD/CUSUM/Kelly/CB/TSM.

    We assert by patching every downstream call site: each must NOT have
    been imported. Since the orchestrator does `from ... import ...`
    inside the function body (lazy imports), we instead assert that NO
    pseudotrader gate or detector touch happens for the NKD outcome.
    """
    orch = _make_orchestrator()
    outcome = {
        "asset": "NKD",
        "pnl": 2500.0,
        "contracts": 1,
        "account": "21855714",
        "trade_id": "TRADE-NKD-001",
    }

    with patch.object(offline_orch, "write_checkpoint") as mock_checkpoint, \
         patch.object(offline_orch, "_stream_numeric_float", side_effect=float):
        orch._handle_trade_outcome(outcome)

    # The bypass writes a "skipped_nkd" checkpoint and the wrapping
    # "processing" checkpoint at the top — exactly two calls expected.
    statuses = [c.args[2] for c in mock_checkpoint.call_args_list]
    assert "skipped_nkd" in statuses, (
        f"Expected 'skipped_nkd' checkpoint to be written for NKD outcome; "
        f"got {statuses}"
    )
    # The "TRADE_OUTCOME_COMPLETE" final checkpoint must NOT be written
    # because the bypass `return`s before reaching it.
    completion = [c for c in mock_checkpoint.call_args_list
                  if c.args[1] == "TRADE_OUTCOME_COMPLETE"]
    assert not completion, (
        "NKD bypass should `return` early, skipping the "
        "TRADE_OUTCOME_COMPLETE checkpoint."
    )
    # And the per-block plog.info for B1/B2/B8 must NEVER fire.
    info_messages = [c.args[0] for c in orch.plog.info.call_args_list]
    forbidden_sources = ["B1:", "B2:", "B8:"]
    for msg in info_messages:
        assert not any(src in str(msg) for src in forbidden_sources), (
            f"Block log {msg!r} fired despite NKD bypass."
        )


def test_handle_signal_outcome_nkd_skips_category_a():
    """Defensive: shadow signal outcomes for NKD must also be skipped."""
    orch = _make_orchestrator()
    outcome = {
        "asset": "NKD",
        "pnl": -1000.0,
        "contracts": 1,
        "trade_id": "SHADOW-NKD-001",
        "theoretical": True,
    }

    with patch.object(offline_orch, "write_checkpoint") as mock_checkpoint, \
         patch.object(offline_orch, "_stream_numeric_float", side_effect=float):
        orch._handle_signal_outcome(outcome)

    # Only the top "processing" checkpoint should fire; no DMA/BOCPD/etc.
    completion = [c for c in mock_checkpoint.call_args_list
                  if "COMPLETE" in str(c.args[1])]
    assert not completion, (
        "NKD signal-outcome bypass should `return` early, skipping any "
        "completion checkpoint."
    )


def test_handle_trade_outcome_non_nkd_does_not_take_bypass_branch():
    """Regression guard: ES outcome must NOT route through the NKD bypass.

    We don't try to drive the full ES path (downstream blocks need scipy
    which is unavailable on towers). Instead we install ``sys.modules``
    fakes for the lazy imports and assert that the function CALLS the
    DMA stub at least once — proving execution flowed past the bypass.
    """
    import sys
    import types

    orch = _make_orchestrator()
    outcome = {
        "asset": "ES",
        "pnl": 200.0,
        "contracts": 2,
        "account": "21855714",
        "trade_id": "TRADE-ES-001",
    }

    dma_mock = MagicMock(return_value=None)
    bocpd_mock = MagicMock(return_value=(0.1, MagicMock(cp_history=[])))
    persist_mock = MagicMock(return_value=None)
    cusum_mock = MagicMock(return_value=(None, MagicMock()))
    level_mock = MagicMock(return_value=None)
    kelly_mock = MagicMock(return_value=None)
    cb_mock = MagicMock(return_value=None)

    fake_b1 = types.ModuleType("captain_offline.blocks.b1_dma_update")
    fake_b1.run_dma_update = dma_mock
    fake_b2_bocpd = types.ModuleType("captain_offline.blocks.b2_bocpd")
    fake_b2_bocpd.run_bocpd_update = bocpd_mock
    fake_b2_bocpd.persist_combined_detector_state = persist_mock
    fake_b2_cusum = types.ModuleType("captain_offline.blocks.b2_cusum")
    fake_b2_cusum.run_cusum_update = cusum_mock
    fake_b2_level = types.ModuleType("captain_offline.blocks.b2_level_escalation")
    fake_b2_level.check_level_escalation = level_mock
    fake_b8_kelly = types.ModuleType("captain_offline.blocks.b8_kelly_update")
    fake_b8_kelly.run_kelly_update = kelly_mock
    fake_b8_cb = types.ModuleType("captain_offline.blocks.b8_cb_params")
    fake_b8_cb.estimate_cb_params = cb_mock

    fakes = {
        "captain_offline.blocks.b1_dma_update": fake_b1,
        "captain_offline.blocks.b2_bocpd": fake_b2_bocpd,
        "captain_offline.blocks.b2_cusum": fake_b2_cusum,
        "captain_offline.blocks.b2_level_escalation": fake_b2_level,
        "captain_offline.blocks.b8_kelly_update": fake_b8_kelly,
        "captain_offline.blocks.b8_cb_params": fake_b8_cb,
    }

    with patch.dict(sys.modules, fakes), \
         patch.object(offline_orch, "write_checkpoint") as mock_checkpoint, \
         patch.object(offline_orch, "_stream_numeric_float", side_effect=float), \
         patch.object(orch, "_run_tsm_for_account", return_value=None):
        orch._handle_trade_outcome(outcome)

    statuses = [c.args[2] for c in mock_checkpoint.call_args_list]
    assert "skipped_nkd" not in statuses, (
        "ES outcome was incorrectly routed through the NKD bypass."
    )
    # Execution must reach the DMA stub — proves the bypass did NOT fire.
    assert dma_mock.called, (
        "ES outcome should have reached run_dma_update; bypass fired incorrectly."
    )
