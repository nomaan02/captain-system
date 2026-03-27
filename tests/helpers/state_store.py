# region imports
from AlgorithmImports import *
# endregion
"""In-memory state store replacing QuestDB for integration tests.

Provides seeded initial state and tracks all mutations so assertions
can verify the feedback loop updated the right datasets.
"""

import json
import math


class InMemoryStateStore:
    """Dict-based replacement for QuestDB in integration tests."""

    def __init__(self):
        # P3-D02: AIM meta weights {(asset, aim_id): {inclusion_probability, ...}}
        self.d02_aim_weights = {}
        # P3-D04: BOCPD state {asset: {cp_prob, ...}}
        self.d04_bocpd = {}
        # P3-D05: EWMA states {(asset, regime, session): {win_rate, avg_win, avg_loss, n_trades}}
        self.d05_ewma = {}
        # P3-D12: Kelly params {(asset, regime, session): {kelly_full, shrinkage}}
        self.d12_kelly = {}
        # P3-D03: Trade outcomes (append-only log)
        self.d03_trades = []
        # P3-D23: Intraday CB state {account: {l_t, n_t}}
        self.d23_intraday = {}
        # P3-D17: System params {key: value}
        self.d17_params = {}
        # Mutation log for assertions
        self._mutations = []

    def seed_default(self):
        """Seed with standard test state for ES + primary_user."""
        # AIM weights: 6 Tier-1 AIMs with uniform weights
        tier1 = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
        n = len(tier1)
        for aid in tier1:
            self.d02_aim_weights[("ES", aid)] = {
                "aim_id": aid,
                "inclusion_probability": 1.0 / n,
                "inclusion_flag": True,
                "recent_effectiveness": 0.5,
                "days_below_threshold": 0,
            }

        # BOCPD: stable (low cp_prob)
        self.d04_bocpd["ES"] = {"current_changepoint_probability": 0.1}

        # EWMA: both regimes, session 1
        for regime in ("LOW_VOL", "HIGH_VOL"):
            self.d05_ewma[("ES", regime, 1)] = {
                "win_rate": 0.50,
                "avg_win": 150.0,
                "avg_loss": 100.0,
                "n_trades": 50,
            }

        # Kelly: computed from EWMA
        for regime in ("LOW_VOL", "HIGH_VOL"):
            wr = 0.50
            b = 150.0 / 100.0
            kelly_full = max(0.0, wr - (1 - wr) / b)  # 0.50 - 0.50/1.5 = 0.167
            shrinkage = max(0.3, 1.0 - 1.0 / math.sqrt(50))  # ~0.858
            self.d12_kelly[("ES", regime, 1)] = {
                "kelly_full": kelly_full,
                "shrinkage_factor": shrinkage,
            }

        # Intraday CB: clean
        self.d23_intraday["acc_eval_1"] = {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}}

        # System params
        self.d17_params["quality_hard_floor"] = 0.003
        self.d17_params["quality_ceiling"] = 0.010
        self.d17_params["manual_halt_all"] = "false"

    def snapshot_ewma(self, asset="ES", regime="LOW_VOL", session=1):
        """Get a copy of current EWMA state for comparison."""
        key = (asset, regime, session)
        state = self.d05_ewma.get(key)
        return dict(state) if state else None

    def snapshot_kelly(self, asset="ES", regime="LOW_VOL", session=1):
        """Get a copy of current Kelly state for comparison."""
        key = (asset, regime, session)
        state = self.d12_kelly.get(key)
        return dict(state) if state else None

    def get_ewma_as_block_input(self):
        """Return EWMA states in the format Online B4/B5/B6 expect."""
        return dict(self.d05_ewma)

    def get_kelly_as_block_input(self):
        """Return Kelly params in the format Online B4 expects."""
        return dict(self.d12_kelly)

    def update_ewma(self, asset, regime, session, new_state):
        """Update EWMA (called by Offline B8 simulation)."""
        key = (asset, regime, session)
        old = self.d05_ewma.get(key, {})
        self.d05_ewma[key] = new_state
        self._mutations.append(("d05_ewma", key, old, new_state))

    def update_kelly(self, asset, regime, session, new_state):
        """Update Kelly (called by Offline B8 simulation)."""
        key = (asset, regime, session)
        old = self.d12_kelly.get(key, {})
        self.d12_kelly[key] = new_state
        self._mutations.append(("d12_kelly", key, old, new_state))

    def add_trade(self, trade):
        """Append trade outcome to D03 log."""
        self.d03_trades.append(trade)
        self._mutations.append(("d03_trades", len(self.d03_trades) - 1, None, trade))

    def get_trade_count(self, asset="ES"):
        """Count trades for an asset."""
        return sum(1 for t in self.d03_trades if t.get("asset") == asset)
