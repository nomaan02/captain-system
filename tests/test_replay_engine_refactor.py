"""Phase 7 — replay_engine refactor (D10).

Phase 7.12 introduces a delegation bridge: when
``config["delegate_to_replay_session"]`` is set, ``run_replay`` and
``run_whatif`` route through ``shared.online_replay.replay_session``.
The default behaviour (no flag) is preserved byte-identical so GUI
replay continues to work until the full B3-B5C wiring lands.

Note: complete deletion of the parallel B-block logic (~600 LOC) is
deferred to Phase 12 per design D10 — see plan §7.12 Discrepancy 7.12A.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from shared import replay_engine
from shared.replay_engine import _delegate_to_replay_session, run_replay, run_whatif


# --------------------------------------------------------------------------- #
# Public API preserved                                                        #
# --------------------------------------------------------------------------- #


def test_public_api_still_exported():
    """Public symbols ``run_replay`` / ``run_whatif`` / ``load_replay_config``
    remain available."""
    from shared import replay_engine as re
    assert callable(re.run_replay)
    assert callable(re.run_whatif)
    assert callable(re.load_replay_config)


def test_run_replay_default_does_not_delegate(monkeypatch):
    """Without the opt-in flag, the legacy parallel B-block path runs."""
    called = {"n": 0}

    def fake_delegate(config, target_date=None):
        called["n"] += 1
        return {"results": []}

    monkeypatch.setattr(replay_engine, "_delegate_to_replay_session", fake_delegate)
    # Call run_replay with a config that lacks the flag — this should NOT
    # invoke the delegate. We don't care if the legacy path itself errors;
    # we just need to confirm the delegate was bypassed before any error.
    try:
        run_replay({}, target_date=date(2026, 1, 15))
    except Exception:
        pass
    assert called["n"] == 0


def test_run_replay_delegates_when_flag_set():
    """``config["delegate_to_replay_session"]`` opts into the new driver."""
    captured = {}

    def fake_delegate(config, target_date=None):
        captured["config"] = config
        captured["target_date"] = target_date
        return {
            "results": [{"signal_id": "SIG-1"}],
            "errors": [], "trades_taken": 1,
            "excluded": [], "no_breakout": [], "zero_sized": [],
            "total_pnl": 0.0, "summary": {}, "cached_bars": None,
        }

    with patch.object(replay_engine, "_delegate_to_replay_session",
                      side_effect=fake_delegate):
        out = run_replay(
            {"delegate_to_replay_session": True},
            target_date=date(2026, 1, 15),
        )
    assert captured["config"]["delegate_to_replay_session"] is True
    assert captured["target_date"] == date(2026, 1, 15)
    assert out["results"][0]["signal_id"] == "SIG-1"


def test_run_replay_legacy_return_shape_preserved_in_delegate():
    """The delegate returns the legacy ``run_replay`` keys."""
    with patch("shared.online_replay.replay_session") as mock_sess:
        from shared.online_replay import ReplayResult
        mock_sess.return_value = ReplayResult(
            session_date=date(2026, 1, 15),
            session_id=1,
            signals=[{"signal_id": "SIG-1", "asset": "ES"}],
            phase_a_outputs={"b1": {}, "b2": {}},
            phase_b_outputs={"b6": {}},
            diagnostics={"reset_hooks_invoked": 1},
        )
        out = _delegate_to_replay_session(
            {"session_id": 1}, target_date=date(2026, 1, 15),
        )
    for key in ("results", "errors", "trades_taken", "excluded",
                "no_breakout", "zero_sized", "total_pnl", "summary",
                "cached_bars"):
        assert key in out
    assert out["results"][0]["signal_id"] == "SIG-1"


def test_run_whatif_delegates_when_flag_set():
    """run_whatif also opts in via the flag."""
    captured = {}

    def fake_delegate(config, target_date=None):
        captured["called"] = True
        return {
            "results": [{"signal_id": "SIG-X"}],
            "errors": [], "trades_taken": 1, "excluded": [],
            "no_breakout": [], "zero_sized": [], "total_pnl": 0.0,
            "summary": {}, "cached_bars": None,
        }

    with patch.object(replay_engine, "_delegate_to_replay_session",
                      side_effect=fake_delegate):
        out = run_whatif(
            {"delegate_to_replay_session": True},
            cached_bars={}, original_results={},
            target_date=date(2026, 1, 15),
        )
    assert captured["called"]
    # Whatif return shape: original / whatif / whatif_results
    assert "whatif" in out
    assert "whatif_results" in out
    assert out["whatif_results"][0]["signal_id"] == "SIG-X"
