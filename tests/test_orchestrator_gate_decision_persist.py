"""Tests for the offline orchestrator's gate-decision audit row.

Closes the observability gap diagnosed 2026-05-08: when ``_pseudotrader_gate``
short-circuits via cold-start, or ``_handle_trade_outcome`` /
``_handle_signal_outcome`` short-circuit via the trivial-change branch, an
audit row must be persisted to ``p3_d11_pseudotrader_results`` so the GUI
Decision Log surfaces every gate event, not just the rare counterfactual
replay results.

These tests use static-source assertions (cheap, no DB) plus an in-memory
cursor mock to capture the INSERT shape from `_persist_gate_decision`.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch


class _CapturingCursor:
    """Minimal cursor that captures every SQL call for assertion."""

    def __init__(self):
        self.executes: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executes.append((sql, params))

    def fetchone(self):
        return None

    def fetchall(self):
        return []


@contextmanager
def _yield_cursor(cur):
    yield cur


def _build_orchestrator():
    """Build a real OfflineOrchestrator without starting threads/Redis."""
    from captain_offline.blocks.orchestrator import OfflineOrchestrator

    orch = OfflineOrchestrator.__new__(OfflineOrchestrator)
    orch.running = False
    orch._detectors = {}
    orch._active_transitions = {}
    orch._redis_thread = None
    orch._last_heartbeat_time = 0

    class _NopLog:
        def info(self, *a, **kw): pass
        def warn(self, *a, **kw): pass
        def warning(self, *a, **kw): pass
        def error(self, *a, **kw): pass

    orch.plog = _NopLog()
    return orch


# --------------------------------------------------------------------------- #
# Behaviour: _persist_gate_decision writes the right INSERT shape             #
# --------------------------------------------------------------------------- #


def test_persist_gate_decision_writes_cold_start_row():
    """Cold-start invocation produces an INSERT with COLD- prefix + JSON payload."""
    orch = _build_orchestrator()
    cur = _CapturingCursor()

    with patch(
        "shared.questdb_client.get_cursor",
        return_value=_yield_cursor(cur),
    ), patch(
        "shared.questdb_client.qexecute",
        side_effect=lambda c, sql, params: c.execute(sql, params),
    ):
        orch._persist_gate_decision(
            "ES", "AIM_WEIGHT_CHANGE", "SKIP_COLD_START",
            pair_payload={
                "asset": "ES",
                "reason": "cold_start_insufficient_d03_history",
                "d03_count": 1,
                "min_required": 5,
            },
        )

    assert len(cur.executes) == 1, "expected exactly one INSERT"
    sql, params = cur.executes[0]
    assert "INSERT INTO p3_d11_pseudotrader_results" in sql
    assert "(result_id, update_type, recommendation, pair_series, ts)" in sql

    result_id, update_type, recommendation, payload_str = params
    assert result_id.startswith("COLD-ES-AIM-")
    assert update_type == "AIM_WEIGHT_CHANGE"
    assert recommendation == "SKIP_COLD_START"

    payload = json.loads(payload_str)
    assert payload["asset"] == "ES"
    assert payload["reason"] == "cold_start_insufficient_d03_history"
    assert payload["d03_count"] == 1
    assert payload["min_required"] == 5


def test_persist_gate_decision_writes_trivial_row():
    """Trivial-change invocation produces TRIV- prefix + outcome context."""
    orch = _build_orchestrator()
    cur = _CapturingCursor()

    with patch(
        "shared.questdb_client.get_cursor",
        return_value=_yield_cursor(cur),
    ), patch(
        "shared.questdb_client.qexecute",
        side_effect=lambda c, sql, params: c.execute(sql, params),
    ):
        orch._persist_gate_decision(
            "NKD", "KELLY_UPDATE", "SKIP_TRIVIAL",
            pair_payload={
                "asset": "NKD",
                "reason": "delta_below_epsilon",
                "epsilon": 1e-4,
                "trade_id": "TRD-XYZ",
                "signal_id": "SIG-ABC",
                "outcome_pnl": 422.20,
                "trigger": "trade_outcome",
            },
        )

    assert len(cur.executes) == 1
    _, params = cur.executes[0]
    result_id, update_type, recommendation, payload_str = params
    assert result_id.startswith("TRIV-NKD-KEL-")
    assert update_type == "KELLY_UPDATE"
    assert recommendation == "SKIP_TRIVIAL"

    payload = json.loads(payload_str)
    assert payload["trade_id"] == "TRD-XYZ"
    assert payload["signal_id"] == "SIG-ABC"
    assert payload["outcome_pnl"] == 422.20
    assert payload["trigger"] == "trade_outcome"


def test_persist_gate_decision_swallows_db_failure():
    """A failing INSERT must NOT raise — the gate is fail-safe."""
    orch = _build_orchestrator()

    def _boom(*a, **kw):
        raise RuntimeError("simulated DB outage")

    with patch(
        "shared.questdb_client.get_cursor",
        side_effect=_boom,
    ):
        # Should NOT raise — gate decisions must not be blocked by audit failure.
        orch._persist_gate_decision(
            "ES", "AIM_WEIGHT_CHANGE", "SKIP_COLD_START",
            pair_payload={"reason": "test"},
        )


def test_persist_gate_decision_handles_missing_qdb_module():
    """Missing shared.questdb_client must NOT raise (handled ImportError)."""
    orch = _build_orchestrator()

    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *a, **kw):
        if name == "shared.questdb_client":
            raise ImportError("simulated import failure")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", side_effect=_fake_import):
        # Should NOT raise.
        orch._persist_gate_decision(
            "ES", "AIM_WEIGHT_CHANGE", "SKIP_COLD_START",
            pair_payload={"reason": "test"},
        )


# --------------------------------------------------------------------------- #
# Static wiring: every short-circuit branch calls the helper                  #
# --------------------------------------------------------------------------- #


def test_orchestrator_wires_helper_into_cold_start_and_trivial_paths():
    """All five short-circuit sites must call _persist_gate_decision.

    1 cold-start branch in _pseudotrader_gate +
    2 trivial branches in _handle_trade_outcome (DMA + Kelly) +
    2 trivial branches in _handle_signal_outcome (DMA + Kelly)
    = 5 call sites + 1 definition = 6 occurrences total.
    """
    src = open(
        "captain-offline/captain_offline/blocks/orchestrator.py",
        encoding="utf-8",
    ).read()

    occurrences = src.count("_persist_gate_decision")
    assert occurrences >= 6, (
        f"expected >= 6 references to _persist_gate_decision (1 def + 5 calls), "
        f"found {occurrences}"
    )

    # The helper must INSERT into the right table with the right column shape.
    assert "INSERT INTO p3_d11_pseudotrader_results" in src
    assert "(result_id, update_type, recommendation, pair_series, ts)" in src

    # SKIP_COLD_START and SKIP_TRIVIAL must both appear as recommendation values.
    assert '"SKIP_COLD_START"' in src
    assert '"SKIP_TRIVIAL"' in src


def test_orchestrator_helper_uses_lazy_import_pattern():
    """Helper must lazy-import shared.questdb_client (orchestrator-wide pattern)."""
    src = open(
        "captain-offline/captain_offline/blocks/orchestrator.py",
        encoding="utf-8",
    ).read()
    # The lazy-import pattern is repeated; we just need the helper to follow it.
    helper_start = src.index("def _persist_gate_decision")
    helper_end = src.index("\n    @staticmethod\n    def _is_trivial_dma_change",
                           helper_start)
    helper_body = src[helper_start:helper_end]
    assert "from shared.questdb_client import get_cursor, qexecute" in helper_body
