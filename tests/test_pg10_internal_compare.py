"""Phase 7 — PG-10 Step 3 internal compare via replay (F-25).

Verifies that ``b4_injection.run_injection_comparison`` no longer passes
precomputed ``baseline_pnl`` / ``proposed_pnl`` into ``run_pseudotrader``
and instead supplies ``current_params`` / ``proposed_params`` so the
replay path runs.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from captain_offline.blocks import b4_injection


# --------------------------------------------------------------------------- #
# Static — call shape                                                         #
# --------------------------------------------------------------------------- #


def test_step3_does_not_pass_precomputed_pnl_to_run_pseudotrader():
    src = open(
        "captain-offline/captain_offline/blocks/b4_injection.py",
        encoding="utf-8",
    ).read()
    # The call site sets parameters by keyword; verify the precomputed
    # P&L positional args are not passed in the replay-path block.
    assert "STRATEGY_INJECTION" in src
    # The call has neither positional ``current_pnl, candidate_pnl`` nor
    # explicit ``baseline_pnl=`` / ``proposed_pnl=`` kwargs in the
    # primary-path call.
    primary_path_call = src.split(
        "Phase 7 (F-25): the precomputed P&L"
    )[1].split(")\n", 1)[0]
    assert "current_pnl" not in primary_path_call
    assert "candidate_pnl" not in primary_path_call
    assert "baseline_pnl=" not in primary_path_call
    assert "proposed_pnl=" not in primary_path_call


# --------------------------------------------------------------------------- #
# Behaviour                                                                   #
# --------------------------------------------------------------------------- #


def test_step3_invokes_run_pseudotrader_with_params_only():
    """run_injection_comparison passes current_params + proposed_params; no
    pre-computed P&L lists."""
    captured = {}

    def fake_pt(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"pbo": 0.3, "dsr": 0.7, "sharpe_improvement": 0.1,
                "recommendation": "ADOPT"}

    with patch.object(b4_injection, "run_pseudotrader", side_effect=fake_pt), \
         patch.object(b4_injection, "_load_aim_weights", return_value={1: 1.0}), \
         patch.object(b4_injection, "_store_injection"):
        b4_injection.run_injection_comparison(
            "ES",
            new_candidate={"sl_multiplier": 0.5},
            current_strategy={"sl_multiplier": 1.0},
            candidate_pnl=[1.0, 2.0, 3.0],
            current_pnl=[0.5, 1.0, 1.5],
        )
    args = captured["args"]
    kwargs = captured["kwargs"]
    # Positional args: (asset_id, update_type) only.
    assert args[0] == "ES"
    assert args[1] == "STRATEGY_INJECTION"
    assert "current_params" in kwargs
    assert "proposed_params" in kwargs
    assert kwargs["current_params"]["locked_strategies"]["ES"]["sl_multiplier"] == 1.0
    assert kwargs["proposed_params"]["locked_strategies"]["ES"]["sl_multiplier"] == 0.5
    # No precomputed P&L positional args
    assert len(args) == 2


def test_step3_uses_oos_returns_candidate_when_provided():
    """PG-13 handoff path: oos_returns_candidate overrides candidate_pnl."""
    seen_candidate = {}

    def fake_aim_edge(strategy, weights, pnl, *, historical_window=None,
                       user_id=None, asset_id=None):
        if strategy.get("sl_multiplier") == 0.5:
            seen_candidate["pnl"] = pnl
        return 1.0

    with patch.object(b4_injection, "_compute_aim_adjusted_edge",
                      side_effect=fake_aim_edge), \
         patch.object(b4_injection, "run_pseudotrader",
                      return_value={"pbo": 0.3, "dsr": 0.7,
                                    "sharpe_improvement": 0.1,
                                    "recommendation": "ADOPT"}), \
         patch.object(b4_injection, "_load_aim_weights", return_value={1: 1.0}), \
         patch.object(b4_injection, "_store_injection"):
        b4_injection.run_injection_comparison(
            "ES",
            new_candidate={"sl_multiplier": 0.5},
            current_strategy={"sl_multiplier": 1.0},
            candidate_pnl=[1.0, 2.0, 3.0],
            current_pnl=[0.5, 1.0, 1.5],
            oos_returns_candidate=[10.0, 20.0],
        )
    # candidate_pnl was overridden
    assert seen_candidate["pnl"] == [10.0, 20.0]
