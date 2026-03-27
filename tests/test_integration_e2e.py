# region imports
from AlgorithmImports import *
# endregion
"""Task 7.4 — End-to-End Integration Test (CRITICAL GATE).

Tests the full feedback loop across all 3 Captain processes:

  DAY 1: Online signal → TAKEN → B7 monitor → TP hit → trade outcome
         → Offline updates EWMA/Kelly
  DAY 2: Online generates NEW signal reflecting Day 1's trade

This is the single most important test in Phase 7 — it proves the
system learns from its own trades.
"""

import json
import math
from unittest.mock import patch, MagicMock
from copy import deepcopy

import pytest

# Online blocks
from captain_online.blocks.b2_regime_probability import run_regime_probability
from captain_online.blocks.b3_aim_aggregation import run_aim_aggregation
from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
from captain_online.blocks.b5_trade_selection import run_trade_selection
from captain_online.blocks.b5b_quality_gate import run_quality_gate
from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen
from captain_online.blocks.b6_signal_output import run_signal_output

# Offline blocks (pure computation helpers)
from captain_offline.blocks.b8_kelly_update import (
    _compute_adaptive_alpha, _compute_kelly, _compute_shrinkage,
)
from captain_online.blocks.b7_position_monitor import resolve_commission

# Test helpers
from tests.helpers.state_store import InMemoryStateStore
from tests.helpers.message_bus import InMemoryPubSub
from tests.fixtures.synthetic_data import (
    make_features, make_regime_model_neutral, make_assets_detail, make_locked_strategy,
)
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_configs
from tests.fixtures.aim_fixtures import make_aim_states_all_active, make_aim_weights


def _mock_compute_aim_modifier(aim_id, features, asset_id, state):
    return {"modifier": 1.0, "confidence": 0.8, "reason_tag": f"TEST_{aim_id}"}


def _run_online_pipeline(store, features, models, aim_states, aim_weights,
                          user_silo, tsm_configs, strategy, detail, session_id,
                          mocks):
    """Run the full Online pipeline B2→B3→B4→B5→B5B→B5C→B6.

    Returns the signal result from B6.
    """
    ewma = store.get_ewma_as_block_input()
    kelly = store.get_kelly_as_block_input()
    accounts = json.loads(user_silo.get("accounts", "[]"))

    # B2: Regime
    b2 = run_regime_probability(["ES"], features, models)
    regime_probs = b2["regime_probs"]
    regime_uncertain = b2["regime_uncertain"]

    # B3: AIM Aggregation
    b3 = run_aim_aggregation(["ES"], features, aim_states, aim_weights)
    combined_modifier = b3["combined_modifier"]
    aim_breakdown = b3["aim_breakdown"]

    # B4: Kelly Sizing
    b4 = run_kelly_sizing(
        active_assets=["ES"],
        regime_probs=regime_probs,
        regime_uncertain=regime_uncertain,
        combined_modifier=combined_modifier,
        kelly_params=kelly,
        ewma_states=ewma,
        tsm_configs=tsm_configs,
        sizing_overrides={},
        user_silo=user_silo,
        locked_strategies=strategy,
        assets_detail=detail,
        session_id=session_id,
    )
    assert b4 is not None and not b4["silo_blocked"]
    final_contracts = b4["final_contracts"]
    account_rec = b4["account_recommendation"]
    account_skip = b4["account_skip_reason"]

    # B5: Trade Selection
    b5 = run_trade_selection(
        active_assets=["ES"],
        final_contracts=final_contracts,
        account_recommendation=account_rec,
        account_skip_reason=account_skip,
        ewma_states=ewma,
        regime_probs=regime_probs,
        user_silo=user_silo,
        session_id=session_id,
    )
    selected_trades = b5["selected_trades"]
    expected_edge = b5["expected_edge"]
    final_contracts = b5["final_contracts"]
    account_rec = b5["account_recommendation"]
    account_skip = b5["account_skip_reason"]

    # B5B: Quality Gate
    b5b = run_quality_gate(
        selected_trades=selected_trades,
        expected_edge=expected_edge,
        combined_modifier=combined_modifier,
        regime_probs=regime_probs,
        user_silo=user_silo,
        session_id=session_id,
    )
    recommended = b5b["recommended_trades"]
    available_nr = b5b["available_not_recommended"]
    quality_results = b5b["quality_results"]

    # B5C: Circuit Breaker
    b5c = run_circuit_breaker_screen(
        recommended_trades=recommended,
        final_contracts=final_contracts,
        account_recommendation=account_rec,
        account_skip_reason=account_skip,
        accounts=accounts,
        tsm_configs=tsm_configs,
        session_id=session_id,
    )
    recommended = b5c["recommended_trades"]
    final_contracts = b5c["final_contracts"]
    account_rec = b5c["account_recommendation"]
    account_skip = b5c["account_skip_reason"]

    # B6: Signal Output
    b6 = run_signal_output(
        recommended_trades=recommended,
        available_not_recommended=available_nr,
        quality_results=quality_results,
        final_contracts=final_contracts,
        account_recommendation=account_rec,
        account_skip_reason=account_skip,
        features=features,
        ewma_states=ewma,
        aim_breakdown=aim_breakdown,
        combined_modifier=combined_modifier,
        regime_probs=regime_probs,
        expected_edge=expected_edge,
        locked_strategies=strategy,
        tsm_configs=tsm_configs,
        user_silo=user_silo,
        assets_detail=detail,
        session_id=session_id,
    )

    return {
        "signals": b6["signals"],
        "below_threshold": b6["below_threshold"],
        "expected_edge": expected_edge,
        "regime_probs": regime_probs,
        "combined_modifier": combined_modifier,
        "aim_breakdown": aim_breakdown,
        "final_contracts": final_contracts,
    }


def _simulate_offline_update(store, trade_outcome):
    """Simulate Offline orchestrator _handle_trade_outcome().

    Updates EWMA and Kelly in the state store using the same math
    as the actual Offline B8 blocks.
    """
    asset = trade_outcome["asset"]
    pnl = trade_outcome["pnl"]
    contracts = trade_outcome.get("contracts", 1)
    regime = trade_outcome.get("regime_at_entry", "LOW_VOL")
    session = trade_outcome.get("session", 1)

    if contracts <= 0:
        return

    pnl_per_contract = pnl / contracts

    # Get adaptive alpha from BOCPD cp_prob
    cp_prob = store.d04_bocpd.get(asset, {}).get("current_changepoint_probability", 0.1)
    alpha = _compute_adaptive_alpha(cp_prob)

    # Update EWMA for the trade's [regime][session]
    key = (asset, regime, session)
    ewma = deepcopy(store.d05_ewma.get(key, {
        "win_rate": 0.5, "avg_win": 0.01, "avg_loss": 0.01, "n_trades": 0
    }))

    if pnl_per_contract > 0:
        ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 1.0
        ewma["avg_win"] = (1 - alpha) * ewma["avg_win"] + alpha * pnl_per_contract
    else:
        ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 0.0
        ewma["avg_loss"] = (1 - alpha) * ewma["avg_loss"] + alpha * abs(pnl_per_contract)

    ewma["n_trades"] = ewma["n_trades"] + 1
    store.update_ewma(asset, regime, session, ewma)

    # Recompute Kelly for ALL regime/session combinations
    for r in ("LOW_VOL", "HIGH_VOL"):
        for ss in (1, 2, 3):
            k = (asset, r, ss)
            e = store.d05_ewma.get(k)
            if e is None:
                continue
            kelly_full = _compute_kelly(e["win_rate"], e["avg_win"], e["avg_loss"])
            total_trades = sum(
                store.d05_ewma.get((asset, rr, sss), {}).get("n_trades", 0)
                for rr in ("LOW_VOL", "HIGH_VOL") for sss in (1, 2, 3)
            )
            shrinkage = _compute_shrinkage(total_trades)
            store.update_kelly(asset, r, ss, {
                "kelly_full": kelly_full,
                "shrinkage_factor": shrinkage,
            })


class TestTwoDayLifecycle:
    """Task 7.4: Full 2-day feedback loop integration test."""

    @patch("captain_online.blocks.b5c_circuit_breaker._load_cb_params",
           return_value={"acc_eval_1": {"beta_b": 0.0, "r_bar": 50.0, "sigma": 10.0,
                                         "rho_bar": 0.0, "n_observations": 200, "p_value": 0.5}})
    @patch("captain_online.blocks.b5c_circuit_breaker._load_intraday_state",
           return_value={"acc_eval_1": {"l_t": 0.0, "n_t": 0, "l_b": {}, "n_b": {}}})
    @patch("captain_online.blocks.b5c_circuit_breaker._get_current_vix", return_value=20.0)
    @patch("captain_online.blocks.b5c_circuit_breaker._get_data_hold_count", return_value=0)
    @patch("captain_online.blocks.b5c_circuit_breaker._check_manual_halt", return_value=False)
    @patch("captain_online.blocks.b5b_quality_gate._load_system_param",
           side_effect=lambda k, d: {"quality_hard_floor": 0.003, "quality_ceiling": 0.010}.get(k, d))
    @patch("captain_online.blocks.b5b_quality_gate._get_trade_count", return_value=50)
    @patch("captain_online.blocks.b5b_quality_gate._log_quality_results")
    @patch("captain_online.blocks.b5_trade_selection._load_correlation_matrix", return_value={})
    @patch("captain_online.blocks.b5_trade_selection._get_correlation", return_value=0.0)
    @patch("captain_online.blocks.b3_aim_aggregation.compute_aim_modifier",
           side_effect=_mock_compute_aim_modifier)
    @patch("captain_online.blocks.b6_signal_output._publish_signals")
    @patch("captain_online.blocks.b6_signal_output._log_signal_output")
    @patch("captain_online.blocks.b6_signal_output._load_system_param",
           side_effect=lambda k, d: d)
    @patch("captain_online.blocks.b6_signal_output._get_daily_pnl", return_value=0.0)
    @patch("captain_online.blocks.b7_position_monitor._get_api_commission", return_value=None)
    def test_full_feedback_loop(
        self, mock_api_comm, mock_pnl, mock_b6_param, mock_b6_log, mock_b6_pub,
        mock_aim, mock_corr, mock_corr_mat, mock_qlog, mock_tc,
        mock_qparam, mock_halt, mock_dh, mock_vix, mock_intra, mock_cb,
    ):
        # ====================================================================
        # STEP 1: Seed initial state
        # ====================================================================
        store = InMemoryStateStore()
        store.seed_default()
        bus = InMemoryPubSub()

        # Shared setup
        features = make_features("ES")
        models = make_regime_model_neutral("ES")
        aim_ids = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
        aim_states = make_aim_states_all_active("ES", aim_ids)
        aim_weights = make_aim_weights("ES", aim_ids)
        user_silo = make_user_silo(accounts=["acc_eval_1"])
        tsm_configs = make_tsm_configs(["acc_eval_1"])
        strategy = make_locked_strategy("ES")
        detail = make_assets_detail("ES")

        # Determine which regime B5 will use as dominant (to compare correctly)
        # REGIME_NEUTRAL → {HIGH_VOL: 0.5, LOW_VOL: 0.5} → argmax = HIGH_VOL (first key)
        # We need to track the regime that gets updated by the trade outcome
        # Record initial state for comparison — will pick correct regime after B2 runs
        ewma_before = None
        kelly_before = None

        # ====================================================================
        # STEP 2: Day 1 — Generate signal
        # ====================================================================
        day1 = _run_online_pipeline(
            store, features, models, aim_states, aim_weights,
            user_silo, tsm_configs, strategy, detail, session_id=1,
            mocks={},
        )

        # A1: Day 1 signal generated with >= 1 contract
        assert len(day1["signals"]) >= 1, \
            f"Day 1 failed to generate signal. Edge={day1['expected_edge']}"
        signal_day1 = day1["signals"][0]
        assert signal_day1["asset"] == "ES"
        assert signal_day1["signal_id"].startswith("SIG-")

        day1_contracts = signal_day1["per_account"]["acc_eval_1"]["contracts"]
        day1_edge = day1["expected_edge"].get("ES", 0)

        # Now that we know the dominant regime, record initial state
        r_probs = day1["regime_probs"].get("ES", {"HIGH_VOL": 0.5, "LOW_VOL": 0.5})
        dominant_regime = max(r_probs, key=r_probs.get)
        ewma_before = store.snapshot_ewma("ES", dominant_regime, 1)
        kelly_before = store.snapshot_kelly("ES", dominant_regime, 1)

        # ====================================================================
        # STEP 3: Day 1 — Simulate TAKEN + Position creation
        # ====================================================================
        r_probs = day1["regime_probs"].get("ES", {"HIGH_VOL": 0.5, "LOW_VOL": 0.5})
        dominant_regime = max(r_probs, key=r_probs.get)

        position = {
            "user_id": "primary_user",
            "asset": "ES",
            "direction": 1,
            "entry_price": 5000.0,
            "signal_entry_price": 5000.0,
            "tp_level": 5010.0,
            "sl_level": 4995.0,
            "contracts": max(day1_contracts, 1),
            "account": "acc_eval_1",
            "point_value": 50.0,
            "session": 1,
            "regime_state": dominant_regime,
            "combined_modifier": day1["combined_modifier"].get("ES", 1.0),
            "aim_breakdown": day1["aim_breakdown"].get("ES", {}),
            "risk_amount": 4.0 * 50.0 * max(day1_contracts, 1),
            "tsm_id": "acc_eval_1",
        }

        # ====================================================================
        # STEP 4: Day 1 — Simulate TP hit → resolve trade
        # ====================================================================
        exit_price = 5010.0  # TP hit
        contracts = position["contracts"]
        point_value = position["point_value"]
        direction = position["direction"]

        gross_pnl = (exit_price - position["entry_price"]) * direction * contracts * point_value
        commission = resolve_commission("acc_eval_1", contracts, "ES", tsm_configs)
        net_pnl = gross_pnl - commission

        # A2: Trade outcome has all required fields
        trade_outcome = {
            "trade_id": "TRD-INTEGRATION-001",
            "user_id": position["user_id"],
            "asset": position["asset"],
            "direction": direction,
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "contracts": contracts,
            "pnl": net_pnl,
            "gross_pnl": gross_pnl,
            "commission": commission,
            "slippage": None,
            "outcome": "TP_HIT",
            "regime_at_entry": position["regime_state"],
            "aim_modifier_at_entry": position["combined_modifier"],
            "aim_breakdown_at_entry": position["aim_breakdown"],
            "session": position["session"],
            "account": position["account"],
        }

        assert trade_outcome["trade_id"] is not None
        assert trade_outcome["pnl"] is not None
        assert trade_outcome["commission"] is not None
        assert trade_outcome["regime_at_entry"] is not None

        # A3: Net PnL = gross - commission, with commission from fee_schedule
        expected_gross = (5010 - 5000) * 1 * contracts * 50  # = 500 * contracts
        assert abs(gross_pnl - expected_gross) < 0.01
        assert commission > 0  # fee_schedule should produce non-zero
        assert abs(net_pnl - (gross_pnl - commission)) < 0.01

        # Log to store
        store.add_trade(trade_outcome)

        # ====================================================================
        # STEP 5: Day 1 — Offline processes trade outcome
        # ====================================================================
        _simulate_offline_update(store, trade_outcome)

        ewma_after = store.snapshot_ewma("ES", dominant_regime, 1)
        kelly_after = store.snapshot_kelly("ES", dominant_regime, 1)

        # A4: EWMA win_rate changed after trade
        assert ewma_after["win_rate"] != ewma_before["win_rate"], \
            f"EWMA win_rate unchanged: {ewma_before['win_rate']} -> {ewma_after['win_rate']}"
        # Win -> win_rate should increase from 0.50
        assert ewma_after["win_rate"] > ewma_before["win_rate"], \
            "Win should increase win_rate"
        assert ewma_after["n_trades"] == ewma_before["n_trades"] + 1

        # A5: Kelly fraction changed after EWMA update
        assert kelly_after["kelly_full"] != kelly_before["kelly_full"], \
            f"Kelly unchanged: {kelly_before['kelly_full']} -> {kelly_after['kelly_full']}"
        # Higher win_rate -> higher Kelly
        assert kelly_after["kelly_full"] > kelly_before["kelly_full"], \
            "Win improving win_rate should increase Kelly"

        # ====================================================================
        # STEP 6: Day 2 — Generate signal with updated state
        # ====================================================================
        # Update the mock to return new trade count (one more trade)
        mock_tc.return_value = 51

        day2 = _run_online_pipeline(
            store, features, models, aim_states, aim_weights,
            user_silo, tsm_configs, strategy, detail, session_id=1,
            mocks={},
        )

        # A6: Day 2 signal exists and is different from Day 1
        assert len(day2["signals"]) >= 1, \
            f"Day 2 failed to generate signal. Edge={day2['expected_edge']}"
        signal_day2 = day2["signals"][0]
        day2_edge = day2["expected_edge"].get("ES", 0)

        # A7: Day 2 expected_edge > Day 1 expected_edge
        # Win improved win_rate AND avg_win, so edge = wr*W - (1-wr)*L should increase
        assert day2_edge > day1_edge, \
            f"Day 2 edge ({day2_edge:.4f}) should exceed Day 1 edge ({day1_edge:.4f})"

        # Additional: verify the signal reflects the update
        # Day 2 win_rate in signal should be higher
        assert signal_day2["win_rate"] > signal_day1["win_rate"], \
            f"Day 2 win_rate ({signal_day2['win_rate']:.4f}) should exceed " \
            f"Day 1 ({signal_day1['win_rate']:.4f})"


class TestTradeOutcomeComputation:
    """Verify trade outcome math in isolation."""

    def test_gross_pnl_long_win(self):
        """Long trade, TP hit: (exit-entry)*dir*contracts*pv."""
        gross = (5010 - 5000) * 1 * 2 * 50
        assert gross == 1000.0

    def test_gross_pnl_long_loss(self):
        """Long trade, SL hit."""
        gross = (4995 - 5000) * 1 * 2 * 50
        assert gross == -500.0

    def test_commission_from_fee_schedule(self):
        """resolve_commission reads fee_schedule.fees_by_instrument first."""
        tsm = make_tsm_configs(["acc_eval_1"])

        with patch("captain_online.blocks.b7_position_monitor._get_api_commission",
                    return_value=None):
            comm = resolve_commission("acc_eval_1", 2, "ES", tsm)

        # fee_schedule has ES round_turn=7.12, so 7.12 * 2 contracts = 14.24
        assert abs(comm - 14.24) < 0.01

    def test_net_pnl(self):
        """Net = gross - commission."""
        gross = 1000.0
        commission = 14.24
        net = gross - commission
        assert abs(net - 985.76) < 0.01


class TestOfflineStateTransitions:
    """Verify Offline update math matches spec."""

    def test_ewma_update_win(self):
        """Win trade: win_rate increases, avg_win moves toward trade PnL."""
        store = InMemoryStateStore()
        store.seed_default()

        before = store.snapshot_ewma("ES", "LOW_VOL", 1)
        assert before["win_rate"] == 0.50

        outcome = {
            "asset": "ES", "pnl": 500.0, "contracts": 1,
            "regime_at_entry": "LOW_VOL", "session": 1,
        }
        _simulate_offline_update(store, outcome)

        after = store.snapshot_ewma("ES", "LOW_VOL", 1)
        assert after["win_rate"] > before["win_rate"]
        assert after["avg_win"] > before["avg_win"]  # avg_win moves toward 500
        assert after["avg_loss"] == before["avg_loss"]  # loss unchanged on a win

    def test_ewma_update_loss(self):
        """Loss trade: win_rate decreases, avg_loss moves toward trade loss."""
        store = InMemoryStateStore()
        store.seed_default()

        before = store.snapshot_ewma("ES", "LOW_VOL", 1)

        outcome = {
            "asset": "ES", "pnl": -200.0, "contracts": 1,
            "regime_at_entry": "LOW_VOL", "session": 1,
        }
        _simulate_offline_update(store, outcome)

        after = store.snapshot_ewma("ES", "LOW_VOL", 1)
        assert after["win_rate"] < before["win_rate"]
        assert after["avg_loss"] > before["avg_loss"]  # avg_loss moves toward 200
        assert after["avg_win"] == before["avg_win"]  # win unchanged on a loss

    def test_kelly_recompute_after_win(self):
        """Kelly increases after a winning trade."""
        store = InMemoryStateStore()
        store.seed_default()

        kelly_before = store.snapshot_kelly("ES", "LOW_VOL", 1)

        outcome = {
            "asset": "ES", "pnl": 500.0, "contracts": 1,
            "regime_at_entry": "LOW_VOL", "session": 1,
        }
        _simulate_offline_update(store, outcome)

        kelly_after = store.snapshot_kelly("ES", "LOW_VOL", 1)
        assert kelly_after["kelly_full"] > kelly_before["kelly_full"]

    def test_kelly_recompute_after_loss(self):
        """Kelly decreases after a losing trade."""
        store = InMemoryStateStore()
        store.seed_default()

        kelly_before = store.snapshot_kelly("ES", "LOW_VOL", 1)

        outcome = {
            "asset": "ES", "pnl": -200.0, "contracts": 1,
            "regime_at_entry": "LOW_VOL", "session": 1,
        }
        _simulate_offline_update(store, outcome)

        kelly_after = store.snapshot_kelly("ES", "LOW_VOL", 1)
        assert kelly_after["kelly_full"] < kelly_before["kelly_full"]

    def test_shrinkage_increases_with_trade(self):
        """One more trade should slightly increase shrinkage."""
        store = InMemoryStateStore()
        store.seed_default()

        kelly_before = store.snapshot_kelly("ES", "LOW_VOL", 1)

        outcome = {
            "asset": "ES", "pnl": 500.0, "contracts": 1,
            "regime_at_entry": "LOW_VOL", "session": 1,
        }
        _simulate_offline_update(store, outcome)

        kelly_after = store.snapshot_kelly("ES", "LOW_VOL", 1)
        assert kelly_after["shrinkage_factor"] >= kelly_before["shrinkage_factor"]
