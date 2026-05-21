# region imports
from AlgorithmImports import *
# endregion
"""PRE-FIX / POST-FIX tests for Kelly warm-up collapse (Bug-A).

PRE-FIX tests (names ending _pre_fix) document the BROKEN behaviour that
existed before the kelly-zero-fix patch.  After Step 3 (I-8 mask fix) and
Step 4 (W-C floor) they become POST-FIX tests that assert the corrected
behaviour.

test_unconditional_default_emits_kelly_zero_pre_fix:
  The bootstrap default (win_rate=0.5, avg_win=0.01, avg_loss=0.01) produces
  kelly_full = 0.5 - 0.5/1.0 = 0.0 exactly.  This is not a bug per-se but it
  means any asset bootstrapped from an empty-return cell starts with kelly=0,
  which propagates silently to D12 and blocks the asset at session open.

test_load_ewma_masks_zero_winrate_pre_fix:
  _load_ewma uses `row[0] or 0.5`.  When a legitimately-learned win_rate=0.0
  is stored in D05, this masks the real value with 0.5 (wrong).  After fix I-8
  it should return 0.0 exactly.

test_cold_start_loss_collapse_pre_fix:
  Starting from default EWMA (0.5, 0.01, 0.01), a single loss drives
  win_rate toward 0 while avg_loss spikes.  _compute_kelly then returns 0.
  With no warmup floor, this collapses the cell — confirmed here.
"""

import pytest
from unittest.mock import patch, MagicMock

from captain_offline.blocks.b8_kelly_update import (
    _compute_kelly,
    _load_ewma,
    _compute_adaptive_alpha,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_cursor(row):
    """Context-manager cursor that returns *row* from fetchone()."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = row
    return cur


def _apply_ewma_loss(ewma: dict, pnl_per_contract: float, alpha: float) -> dict:
    """Apply one loss update to an EWMA state dict (mirrors b8_kelly_update logic)."""
    e = dict(ewma)
    e["win_rate"] = (1 - alpha) * e["win_rate"] + alpha * 0.0
    e["avg_loss"] = (1 - alpha) * e["avg_loss"] + alpha * abs(pnl_per_contract)
    e["n_trades"] = e["n_trades"] + 1
    return e


# ---------------------------------------------------------------------------
# PRE-FIX tests — document the broken behaviour
# (After fix I-8 + W-C these become the reference baseline for what changed)
# ---------------------------------------------------------------------------

class TestBootstrapDefaultEmitsKellyZero:
    """Bootstrap default inputs produce kelly_full == 0 (audit §5.1 sub-cause 2)."""

    def test_unconditional_default_emits_kelly_zero_pre_fix(self):
        """win_rate=0.5, avg_win=avg_loss=0.01 → b=1.0 → kelly = 0.5-0.5 = 0."""
        k = _compute_kelly(0.5, 0.01, 0.01)
        assert k == 0.0, (
            f"Expected kelly=0.0 for balanced-edge defaults, got {k}. "
            "This is the bootstrap zero-seed that starts the collapse chain."
        )

    def test_symmetric_payoff_no_edge_is_zero(self):
        """Equal win/loss with 50% win rate has no Kelly edge."""
        assert _compute_kelly(0.5, 100.0, 100.0) == 0.0


class TestLoadEwmaPreservesZeroWinRate:
    """_load_ewma now uses None-check instead of `or default` (fix I-8).

    A legitimately-learned win_rate=0.0 stored in D05 is preserved as 0.0,
    not silently upgraded to 0.5 (which was the PRE-FIX bug).
    """

    @patch("captain_offline.blocks.b8_kelly_update.get_cursor")
    def test_load_ewma_preserves_zero_winrate(self, mock_get_cursor):
        """row[0]=0.0 is preserved as 0.0 (POST-FIX: None-check, not `or 0.5`)."""
        # D05 row: win_rate=0.0, avg_win=0.01, avg_loss=50.0, n_trades=10
        mock_get_cursor.return_value = _fake_cursor((0.0, 0.01, 50.0, 10))
        result = _load_ewma("ES", "LOW_VOL", 1)
        # POST-FIX: win_rate=0.0 is preserved exactly as stored
        assert result["win_rate"] == 0.0, (
            "POST-FIX (I-8): _load_ewma must preserve a learned 0.0 win_rate. "
            f"Got {result['win_rate']} instead."
        )

    @patch("captain_offline.blocks.b8_kelly_update.get_cursor")
    def test_load_ewma_no_row_returns_defaults(self, mock_get_cursor):
        """No D05 row → cold-start defaults. Unchanged by fix I-8."""
        mock_get_cursor.return_value = _fake_cursor(None)
        result = _load_ewma("ES", "LOW_VOL", 1)
        assert result["win_rate"] == 0.5
        assert result["avg_win"] == 0.01
        assert result["avg_loss"] == 0.01
        assert result["n_trades"] == 0

    @patch("captain_offline.blocks.b8_kelly_update.get_cursor")
    def test_load_ewma_preserves_zero_avg_win(self, mock_get_cursor):
        """avg_win=0.0 in D05 is preserved (not silently reset to 0.01)."""
        mock_get_cursor.return_value = _fake_cursor((0.5, 0.0, 50.0, 5))
        result = _load_ewma("ES", "LOW_VOL", 1)
        assert result["avg_win"] == 0.0

    @patch("captain_offline.blocks.b8_kelly_update.get_cursor")
    def test_load_ewma_preserves_positive_values_unchanged(self, mock_get_cursor):
        """Positive learned values are unaffected by the None-check change."""
        mock_get_cursor.return_value = _fake_cursor((0.62, 150.0, 80.0, 30))
        result = _load_ewma("ES", "LOW_VOL", 1)
        assert result["win_rate"] == pytest.approx(0.62)
        assert result["avg_win"] == pytest.approx(150.0)
        assert result["avg_loss"] == pytest.approx(80.0)
        assert result["n_trades"] == 30


class TestColdStartLossCollapse:
    """One loss from cold-start defaults drives kelly to 0 (audit §5.1 sub-cause 1)."""

    def test_cold_start_loss_collapse_pre_fix(self):
        """Single large loss from (0.5, 0.01, 0.01) → kelly collapses to 0."""
        alpha = _compute_adaptive_alpha(0.1)  # stable regime, slow alpha ≈ 0.064
        ewma = {"win_rate": 0.5, "avg_win": 0.01, "avg_loss": 0.01, "n_trades": 0}
        ewma = _apply_ewma_loss(ewma, pnl_per_contract=-100.0, alpha=alpha)
        k = _compute_kelly(ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"])
        # After one $100 loss: win_rate drops, avg_loss spikes → no edge
        assert k == 0.0, (
            f"Expected kelly=0.0 after cold-start loss, got {k}. "
            "This confirms the collapse path (Bug-A)."
        )

    def test_three_sequential_losses_all_cells_zero(self):
        """Three losses on the trigger cell: the default EWMA produces kelly=0."""
        alpha = _compute_adaptive_alpha(0.1)
        ewma = {"win_rate": 0.5, "avg_win": 0.01, "avg_loss": 0.01, "n_trades": 0}
        for _ in range(3):
            ewma = _apply_ewma_loss(ewma, pnl_per_contract=-200.0, alpha=alpha)
        k = _compute_kelly(ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"])
        assert k == 0.0

    def test_avg_loss_zero_guard(self):
        """_compute_kelly guards avg_loss<=0 → returns 0."""
        assert _compute_kelly(0.6, 100.0, 0.0) == 0.0

    def test_win_rate_zero_guard(self):
        """_compute_kelly guards win_rate<=0 → returns 0."""
        assert _compute_kelly(0.0, 100.0, 100.0) == 0.0
