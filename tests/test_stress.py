# region imports
from AlgorithmImports import *
# endregion
"""Task 7.5 — Stress Tests (7 scenarios per Architecture Section 20).

Each scenario injects extreme conditions and verifies correct block-level response.
"""

import json
import math
import os
import sqlite3
import tempfile
import time
from copy import deepcopy
from unittest.mock import patch, MagicMock

import pytest

from captain_online.blocks.b2_regime_probability import run_regime_probability
from captain_online.blocks.b3_aim_aggregation import run_aim_aggregation
from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
from captain_online.blocks.b5c_circuit_breaker import (
    run_circuit_breaker_screen, _layer5_session_halt,
    DEFAULT_VIX_CB_THRESHOLD,
)
from captain_online.blocks.b6_signal_output import run_signal_output
from captain_offline.blocks.b2_level_escalation import (
    check_level_escalation, _compute_reduction_factor,
    LEVEL2_THRESHOLD, LEVEL3_THRESHOLD, LEVEL3_SUSTAINED_WINDOW,
)
from captain_offline.blocks.b8_kelly_update import (
    _compute_adaptive_alpha, _compute_kelly, _compute_shrinkage,
)

from tests.helpers.state_store import InMemoryStateStore
from tests.fixtures.synthetic_data import (
    make_features, make_regime_model_neutral, make_ewma_states,
    make_kelly_params, make_assets_detail, make_locked_strategy,
)
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_configs
from tests.fixtures.aim_fixtures import make_aim_states_all_active, make_aim_weights


# =====================================================================
# S1: Flash Crash — VIX > 50 + 3 assets DATA_HOLD
# =====================================================================

class TestFlashCrash:
    """S1: All accounts BLOCKED when VIX > threshold or DATA_HOLD >= 3."""

    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params",
           return_value={"acc_eval_1": {"beta_b": 0.0, "r_bar": 50.0, "sigma": 10.0,
                                         "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5}})
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state",
           return_value={"acc_eval_1": {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}}})
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=60.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=3)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_vix_spike_blocks_all(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb):
        """VIX=60 > threshold=50 -> L4 blocks all accounts."""
        tsm = make_tsm_configs(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["ES"],
            final_contracts={"ES": {"acc_eval_1": 3}},
            account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
            account_skip_reason={"ES": {"acc_eval_1": None}},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
        )

        assert result["account_recommendation"]["ES"]["acc_eval_1"] == "BLOCKED"
        assert "Circuit breaker" in result["account_skip_reason"]["ES"]["acc_eval_1"]
        assert len(result["recommended_trades"]) == 0

    def test_l4_vix_unit(self):
        """Direct L4 check: VIX above threshold."""
        with patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=55.0):
            with patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0):
                reason = _layer5_session_halt(1)
        assert reason is not None
        assert "VIX" in reason

    def test_l4_data_hold_count(self):
        """Direct L4 check: DATA_HOLD >= 3."""
        with patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0):
            with patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=3):
                reason = _layer5_session_halt(1)
        assert reason is not None
        assert "DATA_HOLD" in reason

    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params",
           return_value={"acc_eval_1": {"beta_b": 0.0, "r_bar": 50.0, "sigma": 10.0,
                                         "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5}})
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state",
           return_value={"acc_eval_1": {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}}})
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=60.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=5)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    def test_multi_asset_flash_crash(self, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb):
        """Multiple assets during flash crash — all blocked."""
        tsm = make_tsm_configs(["acc_eval_1"])
        result = run_circuit_breaker_screen(
            recommended_trades=["ES", "NQ", "CL"],
            final_contracts={a: {"acc_eval_1": 2} for a in ["ES", "NQ", "CL"]},
            account_recommendation={a: {"acc_eval_1": "TRADE"} for a in ["ES", "NQ", "CL"]},
            account_skip_reason={a: {"acc_eval_1": None} for a in ["ES", "NQ", "CL"]},
            accounts=["acc_eval_1"],
            tsm_configs=tsm,
            session_id=1,
        )

        assert len(result["recommended_trades"]) == 0
        for asset in ["ES", "NQ", "CL"]:
            assert result["account_recommendation"][asset]["acc_eval_1"] == "BLOCKED"


# =====================================================================
# S2: Data Blackout — All features null for an asset
# =====================================================================

class TestDataBlackout:
    """S2: When feature data is missing, B2 falls back to REGIME_NEUTRAL."""

    def test_no_model_regime_neutral(self):
        """No regime model -> neutral fallback."""
        result = run_regime_probability(["ES"], make_features("ES"), {})
        assert result["regime_probs"]["ES"] == {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}
        assert result["regime_uncertain"]["ES"] is True

    def test_null_features_aim_neutral(self):
        """All features None -> AIM modifiers = 1.0 (neutral)."""
        null_features = {"ES": {k: None for k in [
            "vrp", "pcr", "gex", "ivts", "cot_smi", "cross_corr_z",
            "cross_momentum", "opex_window", "spread_z", "volume_ratio",
            "vix_z", "econ_tier", "or_range", "entry_price",
        ]}}

        # With all features None, AIM modifiers should be neutral or error-safe
        from tests.fixtures.aim_fixtures import make_aim_states_all_suppressed, make_aim_weights
        aim_states = make_aim_states_all_suppressed("ES")
        aim_weights = make_aim_weights("ES")

        result = run_aim_aggregation(["ES"], null_features, aim_states, aim_weights)
        assert result["combined_modifier"]["ES"] == 1.0

    def test_data_hold_blocks_session(self):
        """DATA_HOLD >= 3 triggers session halt via L4."""
        with patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0):
            with patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=4):
                reason = _layer5_session_halt(1)
        assert reason is not None
        assert "DATA_HOLD" in reason


# =====================================================================
# S3: Multi-Asset Decay — BOCPD Level 3 on 3+ assets
# =====================================================================

class TestMultiAssetDecay:
    """S3: cp_prob > 0.9 sustained for 5+ trades triggers Level 3."""

    def test_reduction_factor_formula(self):
        """Level 2 reduction: severity=0.80->1.0, 0.85->0.875, 0.90->0.75, 1.0->0.5."""
        assert abs(_compute_reduction_factor(0.80) - 1.0) < 0.001
        assert abs(_compute_reduction_factor(0.85) - 0.875) < 0.001
        assert abs(_compute_reduction_factor(0.90) - 0.75) < 0.001
        assert abs(_compute_reduction_factor(1.00) - 0.5) < 0.001

    def test_reduction_factor_floor(self):
        """Reduction never goes below 0.5."""
        assert _compute_reduction_factor(2.0) == 0.5

    @patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
    @patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
    def test_level2_triggered(self, mock_l3, mock_l2):
        """cp_prob > 0.8 -> Level 2 triggered."""
        check_level_escalation("ES", 0.85, [0.5, 0.6, 0.7, 0.85], "OK")
        mock_l2.assert_called_once_with("ES", 0.85, "BOCPD")
        mock_l3.assert_not_called()

    @patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
    @patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
    def test_level3_sustained(self, mock_l3, mock_l2):
        """cp_prob > 0.9 for 5 consecutive -> Level 3."""
        cp_history = [0.95, 0.92, 0.93, 0.96, 0.91]
        check_level_escalation("ES", 0.95, cp_history, "OK")
        mock_l3.assert_called_once_with("ES", "BOCPD_sustained")

    @patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
    @patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
    def test_level3_three_assets_simultaneously(self, mock_l3, mock_l2):
        """3 assets all hitting Level 3 in same cycle."""
        cp_history = [0.95] * 5

        for asset in ["ES", "NQ", "CL"]:
            check_level_escalation(asset, 0.95, cp_history, "OK")

        assert mock_l3.call_count == 3
        called_assets = [call.args[0] for call in mock_l3.call_args_list]
        assert set(called_assets) == {"ES", "NQ", "CL"}

    @patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
    @patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
    def test_level3_not_triggered_if_short_history(self, mock_l3, mock_l2):
        """cp_prob > 0.9 but only 3 consecutive (need 5) -> no Level 3."""
        cp_history = [0.5, 0.95, 0.92, 0.91]
        check_level_escalation("ES", 0.95, cp_history, "OK")
        mock_l3.assert_not_called()

    @patch("captain_offline.blocks.b2_level_escalation.trigger_level2")
    @patch("captain_offline.blocks.b2_level_escalation.trigger_level3")
    def test_cusum_breach_triggers_level2(self, mock_l3, mock_l2):
        """CUSUM breach -> Level 2 with source='CUSUM'."""
        check_level_escalation("ES", 0.5, [0.5], "BREACH")
        mock_l2.assert_called_once_with("ES", 0.85, "CUSUM")


# =====================================================================
# S4: API Cascade Failure — Redis publish fails
# =====================================================================

class TestApiCascadeFailure:
    """S4: Signal generation succeeds even when Redis publish fails."""

    @patch("captain_online.blocks.b6_signal_output._log_signal_output")
    @patch("captain_online.blocks.b6_signal_output._load_system_param",
           side_effect=lambda k, d: d)
    @patch("captain_online.blocks.b6_signal_output._get_daily_pnl", return_value=0.0)
    def test_signal_survives_publish_failure(self, mock_pnl, mock_param, mock_log):
        """B6 returns signals even when Redis publish fails.

        Mock at the Redis client level so the real _publish_signals try/except fires.
        """
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("Redis connection refused")

        with patch("captain_online.blocks.b6_signal_output.get_redis_client",
                    return_value=mock_client):
            result = run_signal_output(
                recommended_trades=["ES"],
                available_not_recommended=[],
                quality_results={"ES": {"quality_score": 0.015, "quality_multiplier": 1.0, "data_maturity": 1.0}},
                final_contracts={"ES": {"acc_eval_1": 2}},
                account_recommendation={"ES": {"acc_eval_1": "TRADE"}},
                account_skip_reason={"ES": {"acc_eval_1": None}},
                features=make_features("ES"),
                ewma_states=make_ewma_states("ES"),
                aim_breakdown={"ES": {}},
                combined_modifier={"ES": 1.0},
                regime_probs={"ES": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4}},
                expected_edge={"ES": 0.02},
                locked_strategies=make_locked_strategy("ES"),
                tsm_configs=make_tsm_configs(["acc_eval_1"]),
                user_silo=make_user_silo(accounts=["acc_eval_1"]),
                assets_detail=make_assets_detail("ES"),
                session_id=1,
            )

        # Signal still constructed and returned — publish failure caught by _publish_signals
        assert len(result["signals"]) == 1
        assert result["signals"][0]["asset"] == "ES"
        mock_client.publish.assert_called_once()


# =====================================================================
# S5: Infrastructure Overload — 20 users × 5 accounts × 3 assets
# =====================================================================

class TestInfrastructureOverload:
    """S5: Large-scale Kelly sizing completes without error."""

    def test_20_users_5_accounts_3_assets(self):
        """300 account-asset pairs processed correctly."""
        assets = ["ES", "NQ", "CL"]
        n_users = 20
        accounts_per_user = 5

        # Provide EWMA/Kelly for all assets × both regimes
        ewma = {}
        kelly = {}
        for asset in assets:
            for regime in ("LOW_VOL", "HIGH_VOL"):
                ewma[(asset, regime, 1)] = {
                    "win_rate": 0.55, "avg_win": 200.0, "avg_loss": 100.0, "n_trades": 50,
                }
                kelly[(asset, regime, 1)] = {
                    "kelly_full": 0.10, "shrinkage_factor": 0.85,
                }

        regime_probs = {a: {"LOW_VOL": 0.6, "HIGH_VOL": 0.4} for a in assets}
        regime_uncertain = {a: False for a in assets}
        combined_modifier = {a: 1.0 for a in assets}
        strategy = {a: {"threshold": 1.25, "sl_multiple": 1.0, "tp_multiple": 2.0} for a in assets}
        detail = {a: {"point_value": 50.0, "tick_size": 0.25, "margin_per_contract": 500.0} for a in assets}

        results = []
        start = time.time()

        for u in range(n_users):
            user_id = f"user_{u:03d}"
            accs = [f"acc_{u:03d}_{a}" for a in range(accounts_per_user)]
            silo = make_user_silo(user_id=user_id, accounts=accs)
            tsm = {ac: make_tsm_configs([ac])[ac] for ac in accs}

            result = run_kelly_sizing(
                active_assets=assets,
                regime_probs=regime_probs,
                regime_uncertain=regime_uncertain,
                combined_modifier=combined_modifier,
                kelly_params=kelly,
                ewma_states=ewma,
                tsm_configs=tsm,
                sizing_overrides={},
                user_silo=silo,
                locked_strategies=strategy,
                assets_detail=detail,
                session_id=1,
            )
            results.append(result)

        elapsed = time.time() - start

        # All 20 users produced results
        assert len(results) == n_users
        for r in results:
            assert r is not None
            assert r["silo_blocked"] is False
            # Each user has 3 assets × 5 accounts
            for asset in assets:
                assert asset in r["final_contracts"]
                assert len(r["final_contracts"][asset]) == accounts_per_user

        # Should complete well under 5 seconds
        assert elapsed < 5.0, f"Overload test took {elapsed:.2f}s (limit: 5s)"


# =====================================================================
# S6: Regime Whipsaw — 10 rapid alternating trades
# =====================================================================

class TestRegimeWhipsaw:
    """S6: Rapid alternating win/loss trades don't cause EWMA/Kelly instability."""

    def test_10_alternating_trades_stable(self):
        """10 alternating +$500/-$300 trades: EWMA/Kelly stay bounded, no NaN."""
        store = InMemoryStateStore()
        store.seed_default()

        alternating_pnls = [500, -300, 500, -300, 500, -300, 500, -300, 500, -300]

        for i, pnl in enumerate(alternating_pnls):
            # Get current state before update
            ewma_before = store.snapshot_ewma("ES", "LOW_VOL", 1)

            # Simulate Offline update
            cp_prob = 0.5  # Elevated instability during whipsaw
            alpha = _compute_adaptive_alpha(cp_prob)

            key = ("ES", "LOW_VOL", 1)
            ewma = deepcopy(store.d05_ewma[key])

            if pnl > 0:
                ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 1.0
                ewma["avg_win"] = (1 - alpha) * ewma["avg_win"] + alpha * abs(pnl)
            else:
                ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 0.0
                ewma["avg_loss"] = (1 - alpha) * ewma["avg_loss"] + alpha * abs(pnl)

            ewma["n_trades"] += 1
            store.update_ewma("ES", "LOW_VOL", 1, ewma)

            # Recompute Kelly
            kelly_full = _compute_kelly(ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"])
            shrinkage = _compute_shrinkage(ewma["n_trades"])
            store.update_kelly("ES", "LOW_VOL", 1, {
                "kelly_full": kelly_full, "shrinkage_factor": shrinkage,
            })

            # STABILITY ASSERTIONS after every trade
            assert 0.0 <= ewma["win_rate"] <= 1.0, f"Trade {i}: win_rate={ewma['win_rate']} out of bounds"
            assert ewma["avg_win"] > 0, f"Trade {i}: avg_win={ewma['avg_win']} not positive"
            assert ewma["avg_loss"] > 0, f"Trade {i}: avg_loss={ewma['avg_loss']} not positive"
            assert 0.0 <= kelly_full <= 1.0, f"Trade {i}: kelly={kelly_full} out of bounds"
            assert 0.0 < shrinkage <= 1.0, f"Trade {i}: shrinkage={shrinkage} out of bounds"
            assert not math.isnan(ewma["win_rate"]), f"Trade {i}: win_rate is NaN"
            assert not math.isnan(kelly_full), f"Trade {i}: kelly is NaN"
            assert not math.isinf(kelly_full), f"Trade {i}: kelly is Inf"

    def test_extreme_pnl_values(self):
        """Extreme PnL values ($10000 win, $5000 loss) don't break EWMA."""
        store = InMemoryStateStore()
        store.seed_default()

        extreme_pnls = [10000, -5000, 10000, -5000, 10000]
        alpha = _compute_adaptive_alpha(0.8)  # Near-changepoint (fast learning)

        key = ("ES", "LOW_VOL", 1)
        for pnl in extreme_pnls:
            ewma = deepcopy(store.d05_ewma[key])
            if pnl > 0:
                ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 1.0
                ewma["avg_win"] = (1 - alpha) * ewma["avg_win"] + alpha * abs(pnl)
            else:
                ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 0.0
                ewma["avg_loss"] = (1 - alpha) * ewma["avg_loss"] + alpha * abs(pnl)
            ewma["n_trades"] += 1
            store.update_ewma("ES", "LOW_VOL", 1, ewma)

            kelly = _compute_kelly(ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"])
            assert 0.0 <= kelly <= 1.0
            assert not math.isnan(kelly)

    def test_adaptive_alpha_bounds(self):
        """Alpha stays bounded across all cp_prob values."""
        for cp in [0.0, 0.1, 0.2, 0.5, 0.8, 0.9, 0.99, 1.0]:
            alpha = _compute_adaptive_alpha(cp)
            assert 0 < alpha < 1.0, f"cp={cp}: alpha={alpha} out of bounds"


# =====================================================================
# S7: Journal Recovery — SQLite checkpoint round-trip
# =====================================================================

class TestJournalRecovery:
    """S7: SQLite WAL journal checkpoint write/read round-trip."""

    def test_checkpoint_round_trip(self):
        """Write a checkpoint and read it back — all fields match."""
        # Use a temp file for the SQLite journal
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            tmp_path = f.name

        try:
            # Create the journal schema
            conn = sqlite3.connect(tmp_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_journal (
                    entry_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    component TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    state_hash TEXT,
                    last_action TEXT,
                    next_action TEXT,
                    metadata TEXT
                )
            """)
            conn.commit()
            conn.close()

            # Patch journal path to use temp file
            with patch("shared.journal.JOURNAL_PATH", tmp_path):
                from shared.journal import write_checkpoint, get_last_checkpoint

                # Write
                write_checkpoint(
                    component="ONLINE",
                    checkpoint="SESSION_COMPLETE",
                    last_action="signal_generated",
                    next_action="wait_for_next_session",
                    metadata={"session_id": 1, "signals_count": 3},
                    state_hash="abc123",
                )

                # Read
                cp = get_last_checkpoint("ONLINE")

            assert cp is not None
            assert cp["checkpoint"] == "SESSION_COMPLETE"
            assert cp["last_action"] == "signal_generated"
            assert cp["next_action"] == "wait_for_next_session"
            assert cp["state_hash"] == "abc123"
            assert cp["metadata"]["session_id"] == 1
            assert cp["metadata"]["signals_count"] == 3

        finally:
            os.unlink(tmp_path)

    def test_no_checkpoint_returns_none(self):
        """Reading checkpoint for unknown component returns None."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            tmp_path = f.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_journal (
                    entry_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    component TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    state_hash TEXT,
                    last_action TEXT,
                    next_action TEXT,
                    metadata TEXT
                )
            """)
            conn.commit()
            conn.close()

            with patch("shared.journal.JOURNAL_PATH", tmp_path):
                from shared.journal import get_last_checkpoint
                cp = get_last_checkpoint("NONEXISTENT")

            assert cp is None
        finally:
            os.unlink(tmp_path)
