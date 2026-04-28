"""Phase 7 — PG-13 → PG-10 candidate handoff (F-26).

The pre-Phase-7 bug: every candidate received the same ``holdout_returns``
when handed off to ``run_injection_comparison``. Phase 7 hands each
candidate its own per-candidate OOS series.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks import b6_auto_expansion


def test_no_call_passes_candidate_pnl_eq_holdout_returns():
    """Static check: the auto-expansion source no longer hands the raw
    ``holdout_returns`` to ``candidate_pnl=`` for every candidate."""
    src = open(
        "captain-offline/captain_offline/blocks/b6_auto_expansion.py",
        encoding="utf-8",
    ).read()
    # The new code passes ``candidate_pnl=fc["oos"]``, NOT
    # ``candidate_pnl=holdout_returns``.
    assert "candidate_pnl=holdout_returns" not in src


def test_each_candidate_uses_own_oos():
    """Two viable candidates with different multipliers must receive
    distinct ``candidate_pnl`` and ``oos_returns_candidate`` series."""
    historical = [float(i) for i in range(120)]
    holdout = [float(i) for i in range(40)]
    seen_oos: list[list[float]] = []

    def fake_inject(*args, **kwargs):
        seen_oos.append(kwargs.get("oos_returns_candidate"))
        return {"recommendation": "ADOPT"}

    cursor = MagicMock()
    cursor.fetchone.return_value = ('{}',)
    cursor.fetchall.return_value = []
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False

    with patch.object(b6_auto_expansion, "_compute_dsr", return_value=0.9), \
         patch.object(b6_auto_expansion, "_compute_pbo", return_value=0.1), \
         patch.object(b6_auto_expansion, "get_cursor", return_value=ctx), \
         patch.object(b6_auto_expansion, "POPULATION_SIZE", 6), \
         patch.object(b6_auto_expansion, "GENERATIONS", 1), \
         patch.object(b6_auto_expansion, "TOP_K_CANDIDATES", 3), \
         patch("captain_offline.blocks.b4_injection.run_injection_comparison",
               side_effect=fake_inject):
        b6_auto_expansion.run_auto_expansion("ES", historical, holdout)

    assert len(seen_oos) >= 2
    # Each oos series is distinct (per-candidate scaling).
    distinct = {tuple(s) for s in seen_oos if s is not None}
    assert len(distinct) >= 2, (
        "expected at least two distinct OOS series across candidates"
    )
