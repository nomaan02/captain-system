"""Phase 7 — SignalReplayEngine deprecation (D9 / 7.13).

Asserts that the public API still works (``b5_sensitivity`` is the only
remaining caller and migrates in Phase 12) but emits ``DeprecationWarning``
on every entry method.

Note: complete class deletion is deferred to Phase 12 — see plan §7.13.
"""
from __future__ import annotations

import warnings

import pytest


def test_signal_replay_engine_constructor_emits_deprecation_warning():
    from shared.signal_replay import SignalReplayEngine
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        SignalReplayEngine(asset="ES")
    assert any(issubclass(r.category, DeprecationWarning) for r in records), (
        "expected DeprecationWarning on SignalReplayEngine()"
    )


def test_load_replay_context_emits_deprecation_warning():
    from shared.signal_replay import SignalReplayEngine
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        try:
            SignalReplayEngine.load_replay_context(asset="ES")
        except Exception:
            pass
    assert any(issubclass(r.category, DeprecationWarning) for r in records), (
        "expected DeprecationWarning on load_replay_context"
    )


def test_sizing_replay_emits_deprecation_warning():
    from shared.signal_replay import SignalReplayEngine
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        engine = SignalReplayEngine(asset="ES")
        engine.sizing_replay(trades=[])
    # One on __init__, one on sizing_replay
    assert (
        sum(1 for r in records if issubclass(r.category, DeprecationWarning))
        >= 2
    )


def test_strategy_replay_emits_deprecation_warning():
    from shared.signal_replay import SignalReplayEngine
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        engine = SignalReplayEngine(asset="ES")
        engine.strategy_replay(trades=[])
    assert (
        sum(1 for r in records if issubclass(r.category, DeprecationWarning))
        >= 2
    )


# --------------------------------------------------------------------------- #
# Phase 7 modules no longer import the engine                                 #
# --------------------------------------------------------------------------- #


def test_phase7_modules_no_longer_import_signal_replay():
    """b3_pseudotrader and b6_auto_expansion: no SignalReplayEngine refs."""
    for path in (
        "captain-offline/captain_offline/blocks/b3_pseudotrader.py",
        "captain-offline/captain_offline/blocks/b6_auto_expansion.py",
    ):
        src = open(path, encoding="utf-8").read()
        assert "from shared.signal_replay import SignalReplayEngine" not in src, (
            f"{path}: still imports SignalReplayEngine"
        )
        # The b3 docstring may mention the name historically; bare
        # ``SignalReplayEngine`` symbol use is what we forbid.
        assert "SignalReplayEngine(" not in src, (
            f"{path}: still instantiates SignalReplayEngine"
        )


def test_b5_sensitivity_still_callable_via_stub():
    """``b5_sensitivity`` keeps the only remaining caller; instantiating
    the engine + calling its methods must not raise."""
    from shared.signal_replay import SignalReplayEngine

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        engine = SignalReplayEngine(asset="ES")
        # Must complete without raising
        out = engine.strategy_replay(
            trades=[],
            regime_labels={},
            aim_weights={},
            kelly_params={},
            strategy_params={"sl_multiplier": 1.0, "tp_multiplier": 2.0},
        )
    assert isinstance(out, list)
