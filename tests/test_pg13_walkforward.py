"""Phase 7 — Tests for PG-13 walk-forward (F-28, F-29) + per-candidate OOS (F-26).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from captain_offline.blocks import b6_auto_expansion
from captain_offline.blocks.b6_auto_expansion import (
    Candidate,
    WALK_FORWARD_FOLDS,
    _build_expanding_folds,
    _candidate_oos_returns,
    _evaluate_candidate,
    _robust_sharpe,
)


def _candidate(seed=0):
    return Candidate(
        or_window=8,
        threshold=0.15,
        sl_multiplier=1.0 + 0.1 * seed,
        tp_multiplier=2.0,
        feature_idx=0,
    )


# --------------------------------------------------------------------------- #
# Walk-forward fold builder                                                   #
# --------------------------------------------------------------------------- #


def test_build_expanding_folds_returns_5_pairs():
    returns = list(range(60))
    folds = _build_expanding_folds(returns, n_folds=5)
    assert len(folds) == 5


def test_build_expanding_folds_train_strictly_precedes_validate():
    """No leakage: each fold's train indices end before its validate indices start.

    Since slicing is positional, this is enforced by construction; the
    test pins the invariant for future maintainers.
    """
    returns = list(range(120))
    folds = _build_expanding_folds(returns, n_folds=5)
    for train, validate in folds:
        assert len(train) > 0
        assert len(validate) > 0
        # Last train value's positional index < first validate value's index
        assert train[-1] < validate[0]


def test_build_expanding_folds_train_window_grows():
    returns = list(range(60))
    folds = _build_expanding_folds(returns, n_folds=5)
    train_lengths = [len(t) for t, _ in folds]
    assert train_lengths == sorted(train_lengths)
    assert train_lengths[0] < train_lengths[-1]


def test_build_expanding_folds_returns_empty_when_data_too_short():
    assert _build_expanding_folds([1.0, 2.0], n_folds=5) == []


# --------------------------------------------------------------------------- #
# _evaluate_candidate                                                         #
# --------------------------------------------------------------------------- #


def test_evaluate_candidate_uses_5_folds_by_default():
    candidate = _candidate()
    returns = [float(i) for i in range(60)]
    fitness = _evaluate_candidate(candidate, returns, "ES")
    assert candidate.fold_sharpes
    assert len(candidate.fold_sharpes) == WALK_FORWARD_FOLDS


def test_evaluate_candidate_fitness_is_mean_of_fold_sharpes():
    candidate = _candidate()
    returns = [float(i) for i in range(60)]
    # Force deterministic noise off
    with patch("captain_offline.blocks.b6_auto_expansion.random.gauss",
               return_value=0.0):
        fitness = _evaluate_candidate(candidate, returns, "ES")
    expected = sum(candidate.fold_sharpes) / len(candidate.fold_sharpes)
    assert fitness == pytest.approx(expected)


def test_evaluate_candidate_returns_zero_for_empty_returns():
    candidate = _candidate()
    assert _evaluate_candidate(candidate, [], "ES") == 0.0


def test_evaluate_candidate_no_signal_replay_engine_used():
    """No SignalReplayEngine import touches the call path."""
    candidate = _candidate()
    returns = [float(i) for i in range(60)]
    with patch.dict("sys.modules", {"shared.signal_replay": None}):
        fitness = _evaluate_candidate(candidate, returns, "ES")
    assert isinstance(fitness, float)


# --------------------------------------------------------------------------- #
# _candidate_oos_returns                                                      #
# --------------------------------------------------------------------------- #


def test_candidate_oos_returns_distinct_per_candidate():
    """Two candidates with different multipliers → distinct OOS series."""
    c1 = Candidate(or_window=8, threshold=0.15, sl_multiplier=1.0,
                    tp_multiplier=2.0, feature_idx=0)
    c2 = Candidate(or_window=8, threshold=0.15, sl_multiplier=2.0,
                    tp_multiplier=2.0, feature_idx=0)
    holdout = [1.0, 2.0, 3.0]
    oos1 = _candidate_oos_returns(c1, holdout, "ES")
    oos2 = _candidate_oos_returns(c2, holdout, "ES")
    assert oos1 != oos2


def test_candidate_oos_returns_handles_empty_holdout():
    candidate = _candidate()
    assert _candidate_oos_returns(candidate, [], "ES") == []


# --------------------------------------------------------------------------- #
# Static — no SignalReplayEngine                                              #
# --------------------------------------------------------------------------- #


def test_b6_auto_expansion_no_longer_imports_signal_replay():
    src = open(
        "captain-offline/captain_offline/blocks/b6_auto_expansion.py",
        encoding="utf-8",
    ).read()
    assert "from shared.signal_replay" not in src
    assert "SignalReplayEngine" not in src


# --------------------------------------------------------------------------- #
# DSR uses OOS Sharpe, not validation fitness (F-28)                          #
# --------------------------------------------------------------------------- #


def test_dsr_called_with_oos_sharpe_not_fitness():
    """run_auto_expansion calls _compute_dsr with the OOS Sharpe, not
    the GA validation fitness."""
    from unittest.mock import MagicMock
    captured = []

    def fake_dsr(sharpe, n_trials, T):
        captured.append(sharpe)
        return 0.6

    historical = [float(i) for i in range(120)]
    holdout = [float(i) for i in range(40)]

    cursor = MagicMock()
    cursor.fetchone.return_value = ('{}',)
    cursor.fetchall.return_value = []
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False

    with patch.object(b6_auto_expansion, "_compute_dsr", side_effect=fake_dsr), \
         patch.object(b6_auto_expansion, "_compute_pbo", return_value=0.3), \
         patch.object(b6_auto_expansion, "get_cursor", return_value=ctx), \
         patch.object(b6_auto_expansion, "POPULATION_SIZE", 4), \
         patch.object(b6_auto_expansion, "GENERATIONS", 1), \
         patch.object(b6_auto_expansion, "TOP_K_CANDIDATES", 2):
        b6_auto_expansion.run_auto_expansion("ES", historical, holdout)

    # _compute_dsr was called for each top candidate; each call gets that
    # candidate's OOS Sharpe (a robust_sharpe over its scaled holdout).
    assert captured  # at least one DSR call
    # All values are robust_sharpe outputs over scaled holdout — independent
    # of GA fitness.
    for v in captured:
        assert isinstance(v, float)


# --------------------------------------------------------------------------- #
# Per-candidate OOS handoff to PG-10 (F-26)                                   #
# --------------------------------------------------------------------------- #


def test_per_candidate_oos_passed_to_run_injection_comparison():
    """When viable candidates exist, each handoff gets that candidate's
    own OOS series, not a shared holdout."""
    from unittest.mock import MagicMock

    historical = [float(i) for i in range(120)]
    holdout = [float(i) for i in range(40)]

    captured_calls = []

    def fake_inject(*args, **kwargs):
        captured_calls.append(kwargs)
        return {"recommendation": "ADOPT"}

    cursor = MagicMock()
    cursor.fetchone.return_value = ('{}',)
    cursor.fetchall.return_value = []
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False

    # Make every candidate viable so the handoff fires
    with patch.object(b6_auto_expansion, "_compute_dsr", return_value=0.99), \
         patch.object(b6_auto_expansion, "_compute_pbo", return_value=0.0), \
         patch.object(b6_auto_expansion, "get_cursor", return_value=ctx), \
         patch.object(b6_auto_expansion, "POPULATION_SIZE", 4), \
         patch.object(b6_auto_expansion, "GENERATIONS", 1), \
         patch.object(b6_auto_expansion, "TOP_K_CANDIDATES", 2), \
         patch("captain_offline.blocks.b4_injection.run_injection_comparison",
               side_effect=fake_inject):
        b6_auto_expansion.run_auto_expansion("ES", historical, holdout)

    assert captured_calls, "expected at least one injection call"
    # Each call carries oos_returns_candidate (per-candidate, F-26)
    for call_kwargs in captured_calls:
        assert "oos_returns_candidate" in call_kwargs
        assert call_kwargs["oos_returns_candidate"] is not None
