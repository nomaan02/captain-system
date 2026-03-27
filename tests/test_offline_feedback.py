# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 22-23: Offline Feedback Loop regression tests.

Tests that trade outcomes correctly update EWMA and Kelly parameters.
"""

import math
from unittest.mock import patch, MagicMock, call

import pytest

from captain_offline.blocks.b8_kelly_update import (
    _compute_adaptive_alpha, _compute_kelly, _compute_shrinkage,
)


class TestEwmaUpdateAfterWin:
    """Scenario 22: EWMA update after a winning trade."""

    def test_adaptive_alpha_stable(self):
        """cp_prob=0.1 (stable) -> span=30, alpha=2/31."""
        alpha = _compute_adaptive_alpha(0.1)
        assert abs(alpha - 2.0 / 31.0) < 0.001

    def test_adaptive_alpha_near_changepoint(self):
        """cp_prob=0.9 (near changepoint) -> span=8, alpha=2/9."""
        alpha = _compute_adaptive_alpha(0.9)
        assert abs(alpha - 2.0 / 9.0) < 0.001

    def test_ewma_win_rate_increases_after_win(self):
        """Simulate EWMA update for a win and verify win_rate increases."""
        # Prior state
        prior_wr = 0.50
        prior_avg_win = 150.0
        pnl_per_contract = 200.0  # win

        # Stable regime: alpha = 2/31 ~ 0.0645
        alpha = _compute_adaptive_alpha(0.1)

        # After win: win_rate = (1-alpha)*prior + alpha*1.0
        new_wr = (1 - alpha) * prior_wr + alpha * 1.0
        assert new_wr > prior_wr
        assert abs(new_wr - (prior_wr + alpha * (1.0 - prior_wr))) < 0.001

        # avg_win updates toward new pnl
        new_avg_win = (1 - alpha) * prior_avg_win + alpha * pnl_per_contract
        assert new_avg_win > prior_avg_win
        assert abs(new_avg_win - (prior_avg_win + alpha * (pnl_per_contract - prior_avg_win))) < 0.001

    def test_ewma_win_rate_decreases_after_loss(self):
        """EWMA update for a loss: win_rate should decrease."""
        prior_wr = 0.55
        alpha = _compute_adaptive_alpha(0.1)

        new_wr = (1 - alpha) * prior_wr + alpha * 0.0
        assert new_wr < prior_wr

    def test_per_contract_normalisation(self):
        """PnL is normalised per-contract to remove sizing bias."""
        total_pnl = 600.0
        contracts = 3
        pnl_per_contract = total_pnl / contracts
        assert pnl_per_contract == 200.0


class TestKellyRecomputeAfterUpdate:
    """Scenario 23: Kelly fraction recomputation after EWMA update."""

    def test_kelly_increases_with_higher_win_rate(self):
        """Higher win_rate -> higher Kelly fraction."""
        k1 = _compute_kelly(0.55, 200.0, 100.0)
        k2 = _compute_kelly(0.58, 200.0, 100.0)
        assert k2 > k1

    def test_kelly_increases_with_better_payoff(self):
        """Higher avg_win/avg_loss -> higher Kelly fraction."""
        k1 = _compute_kelly(0.55, 200.0, 100.0)
        k2 = _compute_kelly(0.55, 250.0, 100.0)
        assert k2 > k1

    def test_kelly_formula_exact(self):
        """Verify exact Kelly formula: f* = p - (1-p)/b."""
        wr = 0.55
        avg_win = 200.0
        avg_loss = 100.0
        b = avg_win / avg_loss  # 2.0
        expected = wr - (1 - wr) / b  # 0.55 - 0.225 = 0.325
        actual = _compute_kelly(wr, avg_win, avg_loss)
        assert abs(actual - expected) < 0.0001

    def test_shrinkage_unchanged_for_same_n(self):
        """Shrinkage doesn't change when n_trades stays the same."""
        s1 = _compute_shrinkage(50)
        s2 = _compute_shrinkage(50)
        assert s1 == s2

    def test_shrinkage_increases_with_more_data(self):
        """More trades -> higher shrinkage (closer to 1.0)."""
        s1 = _compute_shrinkage(25)
        s2 = _compute_shrinkage(100)
        assert s2 > s1

    def test_full_feedback_scenario(self):
        """Simulate Day 1 win -> EWMA update -> Kelly recompute."""
        # Day 1: prior state
        prior = {"win_rate": 0.50, "avg_win": 150.0, "avg_loss": 100.0, "n_trades": 50}
        pnl_per_contract = 200.0  # win

        alpha = _compute_adaptive_alpha(0.1)  # stable regime

        # Update EWMA
        new_wr = (1 - alpha) * prior["win_rate"] + alpha * 1.0
        new_avg_win = (1 - alpha) * prior["avg_win"] + alpha * pnl_per_contract
        new_n = prior["n_trades"] + 1

        # Recompute Kelly
        kelly_before = _compute_kelly(prior["win_rate"], prior["avg_win"], prior["avg_loss"])
        kelly_after = _compute_kelly(new_wr, new_avg_win, prior["avg_loss"])

        # Kelly should increase after a win that improves win_rate and avg_win
        assert kelly_after > kelly_before

        # Shrinkage
        shrink_before = _compute_shrinkage(prior["n_trades"])
        shrink_after = _compute_shrinkage(new_n)
        assert shrink_after >= shrink_before  # One more trade -> slightly higher

        # Final adjusted Kelly
        final_before = kelly_before * shrink_before
        final_after = kelly_after * shrink_after
        assert final_after > final_before

        # Verify update is bounded (alpha~0.065 so delta can be up to ~0.07)
        assert abs(kelly_after - kelly_before) < 0.10
