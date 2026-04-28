"""Phase 7 — G-OFF-016 verification suite (Batch 7.14).

These tests pin the in-fact resolution of G-OFF-016: ``captain_online_replay``
runs the live B1-B6 chain (no parallel logic, no Redis I/O, no TopstepX
side effects) and PG-09 sources realised P&L from D03 paired by
``signal_id``.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from shared.online_replay import (
    OnlineReplayContext,
    ReplayParameters,
    captain_online_replay,
    default_reset_hooks,
    replay_session,
)
from shared.online_replay_providers import (
    CapturingSignalSink,
    FixedTimeProvider,
    HistoricalMarketDataProvider,
)


_ET = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# Driver invokes live blocks                                                  #
# --------------------------------------------------------------------------- #


def test_captain_online_replay_invokes_live_b1_with_historical_provider():
    """Layer 3 calls the live ``run_data_ingestion`` with
    ``market_data=HistoricalMarketDataProvider(...)``."""
    with patch(
        "captain_online.blocks.b1_data_ingestion.run_data_ingestion",
        return_value=None,
    ) as mock_b1:
        captain_online_replay(
            date(2026, 1, 15),
            using=ReplayParameters(),
            user_id="u1", asset="ES", session_id=1,
        )
    _, kwargs = mock_b1.call_args
    assert isinstance(kwargs["market_data"], HistoricalMarketDataProvider)


def test_replay_session_invokes_live_b6_with_capturing_sink():
    """``replay_session`` passes a ``CapturingSignalSink`` into ``run_signal_output``."""
    sink = CapturingSignalSink()
    ctx = OnlineReplayContext(
        market_data=MagicMock(),
        signal_sink=sink,
        time_provider=FixedTimeProvider(datetime(2026, 1, 15, 9, 30, tzinfo=_ET)),
        reset_hooks=default_reset_hooks(),
    )
    fake_b1 = {"active_assets": [], "features": {}, "regime_models": {}}
    with patch(
        "captain_online.blocks.b1_data_ingestion.run_data_ingestion",
        return_value=fake_b1,
    ), patch(
        "captain_online.blocks.b2_regime_probability.run_regime_probability",
        return_value={},
    ), patch(
        "captain_online.blocks.b6_signal_output.run_signal_output",
    ) as mock_b6:
        mock_b6.return_value = {"signals": []}
        replay_session(date(2026, 1, 15), 1, ctx)
    mock_b6.assert_called_once()
    _, kwargs = mock_b6.call_args
    assert kwargs.get("signal_sink") is sink


# --------------------------------------------------------------------------- #
# D03 → outcome pairing                                                       #
# --------------------------------------------------------------------------- #


def test_pg09_reads_d03_for_outcome_via_actual_trade_outcome():
    """PG-09's pair series is built from D03 lookups by signal_id."""
    from captain_offline.blocks import b3_pseudotrader
    from shared.trade_source import RealisedOutcome

    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False

    base_outcome = RealisedOutcome(
        signal_id="BASE-1", trade_id="TRD-1", pnl=10.0, gross_pnl=11.0,
        commission=1.0, contracts=1, entry_price=100.0, exit_price=101.0,
        entry_time=None, exit_time=None, direction=1,
        regime_at_entry="LOW_VOL",
    )

    seen_calls = []

    def fake_outcome(d, *, user_id, asset=None, signal_id=None):
        seen_calls.append((d, user_id, asset, signal_id))
        return base_outcome

    def fake_replay(d, asset_id, params=None, *, user_id=None, **kw):
        return {
            "asset": asset_id,
            "signal": {"asset": asset_id, "signal_id": "BASE-1"},
            "signal_id": "BASE-1",
            "pnl": 0.0,
        }

    with patch.object(b3_pseudotrader, "fetch_d03_trade_outcomes",
                      return_value=[{"ts": date(2026, 1, 15)}]), \
         patch.object(b3_pseudotrader, "captain_online_replay",
                      side_effect=fake_replay), \
         patch("shared.trade_source.actual_trade_outcome",
               side_effect=fake_outcome), \
         patch.object(b3_pseudotrader, "get_cursor", return_value=ctx):
        b3_pseudotrader.run_pseudotrader(
            "ES", "AIM_WEIGHT_CHANGE",
            user_id="u1", lookback_days=1,
        )
    assert seen_calls
    # signal_id was passed into the outcome lookup
    sig_ids = [c[3] for c in seen_calls]
    assert "BASE-1" in sig_ids


# --------------------------------------------------------------------------- #
# Replay isolation                                                            #
# --------------------------------------------------------------------------- #


def test_replay_does_not_touch_redis():
    """A full Layer-3 replay never publishes via Redis."""
    fake_b1 = {"active_assets": ["ES"], "features": {}, "regime_models": {}}
    with patch(
        "captain_online.blocks.b1_data_ingestion.run_data_ingestion",
        return_value=fake_b1,
    ), patch(
        "captain_online.blocks.b2_regime_probability.run_regime_probability",
        return_value={},
    ), patch(
        "captain_online.blocks.b6_signal_output.run_signal_output",
        return_value={"signals": []},
    ), patch(
        "shared.online_replay_providers.get_redis_client",
    ) as mock_redis:
        captain_online_replay(
            date(2026, 1, 15),
            using=ReplayParameters(),
            user_id="u1", asset="ES", session_id=1,
        )
    mock_redis.assert_not_called()


def test_replay_resets_b5c_seen_state_between_calls():
    """``default_reset_hooks`` clears the B5C ``_seen`` set; consecutive
    replays start clean."""
    from captain_online.blocks.b5c_circuit_breaker import _get_seen

    _get_seen().add("dirty")
    fake_b1 = None
    with patch(
        "captain_online.blocks.b1_data_ingestion.run_data_ingestion",
        return_value=fake_b1,
    ):
        captain_online_replay(
            date(2026, 1, 15),
            using=ReplayParameters(),
            user_id="u1", asset="ES", session_id=1,
        )
    assert "dirty" not in _get_seen()


# --------------------------------------------------------------------------- #
# Static — F-22: pseudotrader gate doesn't reach SignalReplayEngine            #
# --------------------------------------------------------------------------- #


def test_pseudotrader_gate_does_not_use_signal_replay_engine():
    src = open(
        "captain-offline/captain_offline/blocks/b3_pseudotrader.py",
        encoding="utf-8",
    ).read()
    assert "from shared.signal_replay import SignalReplayEngine" not in src
    assert "SignalReplayEngine(" not in src
