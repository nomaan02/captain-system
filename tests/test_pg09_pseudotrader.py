"""Phase 7 — Tests for PG-09 rebuild (F-22, F-23).

PG-09 was rebuilt to:
* Replay live B1-B6 via ``shared.online_replay.captain_online_replay``
* Source realised P&L from D03 paired by ``signal_id`` (Q-15)
* Drop the ``SignalReplayEngine`` path
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks import b3_pseudotrader
from shared.trade_source import RealisedOutcome


# --------------------------------------------------------------------------- #
# captain_online_replay wrapper                                               #
# --------------------------------------------------------------------------- #


def test_b3_captain_online_replay_delegates_to_shared_driver():
    """The wrapper calls shared.online_replay.captain_online_replay."""
    with patch(
        "shared.online_replay.captain_online_replay",
        return_value=[{"asset": "ES", "signal_id": "SIG-1", "direction": 1, "size": 1}],
    ) as mock_replay:
        out = b3_pseudotrader.captain_online_replay(
            date(2026, 1, 15), "ES", user_id="u1",
        )
    mock_replay.assert_called_once()
    assert out["asset"] == "ES"
    assert out["signal_id"] == "SIG-1"


def test_b3_captain_online_replay_returns_no_signal_when_replay_empty():
    with patch(
        "shared.online_replay.captain_online_replay",
        return_value=[],
    ):
        out = b3_pseudotrader.captain_online_replay(
            date(2026, 1, 15), "ES", user_id="u1",
        )
    assert out["direction"] == 0
    assert out["exit_reason"] == "NO_SIGNAL"


def test_b3_captain_online_replay_filters_to_target_asset():
    """Only the target asset's signal is returned in the per-asset summary."""
    with patch(
        "shared.online_replay.captain_online_replay",
        return_value=[
            {"asset": "NQ", "signal_id": "SIG-NQ"},
            {"asset": "ES", "signal_id": "SIG-ES"},
        ],
    ):
        out = b3_pseudotrader.captain_online_replay(
            date(2026, 1, 15), "ES", user_id="u1",
        )
    assert out["asset"] == "ES"
    assert out["signal_id"] == "SIG-ES"


# --------------------------------------------------------------------------- #
# run_pseudotrader — pair-based metrics                                       #
# --------------------------------------------------------------------------- #


def _outcome(signal_id, pnl, contracts=1):
    return RealisedOutcome(
        signal_id=signal_id, trade_id=f"TRD-{signal_id}",
        pnl=pnl, gross_pnl=pnl + 1.0, commission=1.0,
        contracts=contracts, entry_price=100.0, exit_price=101.0,
        entry_time=None, exit_time=None,
        direction=1, regime_at_entry="LOW_VOL",
    )


def test_pg09_uses_d03_realised_pnl_via_actual_trade_outcome():
    """Replay supplies signals; D03 supplies realised P&L; metrics are
    computed from the resulting pair series."""
    days = [date(2026, 1, 15), date(2026, 1, 16), date(2026, 1, 17)]

    def fake_d03(_user, _asset, _limit):
        return [{"ts": d} for d in days]

    base_signals_by_day = {
        d: {"asset": "ES", "signal_id": f"BASE-{d}", "direction": 1, "size": 1}
        for d in days
    }
    prop_signals_by_day = {
        d: {"asset": "ES", "signal_id": f"PROP-{d}", "direction": 1, "size": 1}
        for d in days
    }
    base_pnls = {d: _outcome(f"BASE-{d}", v)
                 for d, v in zip(days, [10.0, 5.0, -2.0])}
    prop_pnls = {d: _outcome(f"PROP-{d}", v)
                 for d, v in zip(days, [12.0, 8.0, 1.0])}

    def fake_replay(d, *, using, user_id, asset, session_id=None):
        sig = (
            base_signals_by_day[d] if user_id == "u1" and using.aim_weights is None
            else prop_signals_by_day[d]
        )
        return [sig]

    def fake_outcome(d, *, user_id, asset=None, signal_id=None):
        if signal_id and signal_id.startswith("BASE-"):
            return base_pnls[d]
        if signal_id and signal_id.startswith("PROP-"):
            return prop_pnls[d]
        return None

    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False

    with patch.object(b3_pseudotrader, "fetch_d03_trade_outcomes",
                      side_effect=fake_d03), \
         patch("shared.online_replay.captain_online_replay",
               side_effect=fake_replay), \
         patch("shared.trade_source.actual_trade_outcome",
               side_effect=fake_outcome), \
         patch.object(b3_pseudotrader, "get_cursor", return_value=ctx):
        result = b3_pseudotrader.run_pseudotrader(
            "ES", "AIM_WEIGHT_CHANGE",
            current_params=None,
            proposed_params={"aim_weights": {1: 0.5}},
            user_id="u1",
            lookback_days=3,
        )
    assert "sharpe_baseline" in result
    assert "sharpe_updated" in result
    assert result["sharpe_improvement"] == pytest.approx(
        result["sharpe_updated"] - result["sharpe_baseline"]
    )
    assert "pair_series" in result


def test_pg09_returns_no_historical_data_when_d03_empty():
    with patch.object(b3_pseudotrader, "fetch_d03_trade_outcomes",
                      return_value=[]):
        result = b3_pseudotrader.run_pseudotrader(
            "ES", "AIM_WEIGHT_CHANGE",
            user_id="u1", lookback_days=3,
        )
    assert result["recommendation"] == "REJECT"
    assert result["reason"] == "NO_HISTORICAL_DATA"
    assert result["sharpe_baseline"] == 0.0
    assert result["sharpe_updated"] == 0.0


def test_pg09_persists_phase7_columns_into_d11():
    """D11 INSERT carries sharpe_baseline, sharpe_updated, pair_series."""
    days = [date(2026, 1, 15)]

    captured = {}

    def _exec(sql, args=None):
        if "p3_d11_pseudotrader_results" in sql:
            captured["sql"] = sql
            captured["args"] = args

    cursor = MagicMock()
    cursor.execute.side_effect = _exec
    cursor.fetchall.return_value = []
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False

    out = _outcome("BASE-X", 10.0)

    def fake_replay(d, *, using, user_id, asset, session_id=None):
        return [{"asset": "ES", "signal_id": "BASE-X", "direction": 1, "size": 1}]

    with patch.object(b3_pseudotrader, "fetch_d03_trade_outcomes",
                      return_value=[{"ts": days[0]}]), \
         patch("shared.online_replay.captain_online_replay",
               side_effect=fake_replay), \
         patch("shared.trade_source.actual_trade_outcome",
               return_value=out), \
         patch.object(b3_pseudotrader, "get_cursor", return_value=ctx):
        b3_pseudotrader.run_pseudotrader(
            "ES", "AIM_WEIGHT_CHANGE",
            user_id="u1", lookback_days=1,
        )
    assert "sharpe_baseline" in captured["sql"]
    assert "sharpe_updated" in captured["sql"]
    assert "pair_series" in captured["sql"]


# --------------------------------------------------------------------------- #
# Static — no SignalReplayEngine import                                       #
# --------------------------------------------------------------------------- #


def test_b3_module_no_longer_imports_signal_replay_engine():
    """F-22 closed: b3_pseudotrader does not import SignalReplayEngine."""
    src = open(
        "captain-offline/captain_offline/blocks/b3_pseudotrader.py",
        encoding="utf-8",
    ).read()
    assert "from shared.signal_replay import SignalReplayEngine" not in src
    assert "import shared.signal_replay" not in src
    assert "shared.signal_replay.SignalReplayEngine" not in src


def test_run_signal_replay_comparison_delegates_to_run_pseudotrader():
    """The shim exists for backwards compat and now delegates internally."""
    with patch.object(b3_pseudotrader, "run_pseudotrader",
                      return_value={"recommendation": "ADOPT"}) as mock_pt:
        out = b3_pseudotrader.run_signal_replay_comparison(
            "ES",
            {"update_type": "AIM_WEIGHT_CHANGE",
             "proposed_aim_weights": {1: 0.5}},
        )
    mock_pt.assert_called_once()
    assert out["recommendation"] == "ADOPT"


# --------------------------------------------------------------------------- #
# Orchestrator gate                                                           #
# --------------------------------------------------------------------------- #


def test_pseudotrader_gate_uses_run_pseudotrader_directly():
    """Orchestrator gate routes through run_pseudotrader (not the legacy shim)."""
    src = open(
        "captain-offline/captain_offline/blocks/orchestrator.py",
        encoding="utf-8",
    ).read()
    assert "from captain_offline.blocks.b3_pseudotrader import run_pseudotrader" in src
