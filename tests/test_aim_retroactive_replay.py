"""Phase 7 — Tests for shared.aim_retroactive (F-24).

Covers ``aim_retroactive_replay`` per-day series + the aggregator used
by ``b4_injection._compute_aim_adjusted_edge``.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from shared import aim_retroactive
from shared.aim_retroactive import (
    _iter_session_days,
    _state_from_candidate,
    aggregate_modifiers,
    aim_retroactive_replay,
)


# --------------------------------------------------------------------------- #
# Helper coverage                                                             #
# --------------------------------------------------------------------------- #


def test_iter_session_days_skips_weekends():
    days = list(_iter_session_days(date(2026, 1, 12), date(2026, 1, 16)))
    # Mon Jan 12 2026 → Fri Jan 16 2026 = 5 weekdays
    assert days == [
        date(2026, 1, 12), date(2026, 1, 13), date(2026, 1, 14),
        date(2026, 1, 15), date(2026, 1, 16),
    ]


def test_iter_session_days_inclusive_endpoints():
    days = list(_iter_session_days(date(2026, 1, 12), date(2026, 1, 13)))
    assert days == [date(2026, 1, 12), date(2026, 1, 13)]


def test_state_from_candidate_per_asset_keyed():
    state = _state_from_candidate(
        {"sl_multiplier": 0.5, "tp_multiplier": 1.5}, "ES",
    )
    assert "ES" in state
    assert state["ES"]["sl_multiplier"] == 0.5
    assert state["ES"]["tp_multiplier"] == 1.5


# --------------------------------------------------------------------------- #
# aim_retroactive_replay                                                      #
# --------------------------------------------------------------------------- #


def test_aim_retroactive_replay_returns_per_day_series():
    """When features load and dispatch returns a modifier, we get a tuple
    per session day."""
    fake_features = {"vrp": 0.05, "daily_close": 100.0}
    with patch.object(aim_retroactive, "_load_historical_features",
                      return_value=fake_features), \
         patch.object(aim_retroactive, "compute_aim_modifier",
                      return_value={"modifier": 1.25, "confidence": 0.9, "reason_tag": "OK"}):
        series = aim_retroactive_replay(
            1, {"some": "candidate"},
            (date(2026, 1, 12), date(2026, 1, 14)),
            user_id="u1", asset="ES",
        )
    # 3 weekdays Mon-Wed
    assert len(series) == 3
    assert all(isinstance(d, date) for d, _ in series)
    assert all(modifier == 1.25 for _, modifier in series)


def test_aim_retroactive_replay_skips_days_without_features():
    """Days with no feature row are dropped from the series."""
    feature_calls = {"n": 0}

    def loader(asset, d):
        feature_calls["n"] += 1
        return {"vrp": 0.05} if feature_calls["n"] != 2 else None

    with patch.object(aim_retroactive, "_load_historical_features",
                      side_effect=loader), \
         patch.object(aim_retroactive, "compute_aim_modifier",
                      return_value={"modifier": 1.2, "confidence": 0.9, "reason_tag": "OK"}):
        series = aim_retroactive_replay(
            1, {"x": 1},
            (date(2026, 1, 12), date(2026, 1, 14)),
            user_id="u1", asset="ES",
        )
    # 3 weekdays, but day-2 returned None → 2 entries
    assert len(series) == 2


def test_aim_retroactive_replay_drops_no_handler_results():
    """``NO_HANDLER`` and ``ERROR`` reason tags are dropped."""
    with patch.object(aim_retroactive, "_load_historical_features",
                      return_value={"any": "feat"}), \
         patch.object(aim_retroactive, "compute_aim_modifier",
                      return_value={"modifier": 1.0, "confidence": 0.0, "reason_tag": "NO_HANDLER"}):
        series = aim_retroactive_replay(
            1, {"x": 1},
            (date(2026, 1, 12), date(2026, 1, 14)),
            user_id="u1", asset="ES",
        )
    assert series == []


def test_aim_retroactive_replay_uses_candidate_state():
    """compute_aim_modifier receives the candidate-derived state, not live."""
    captured_state = {}

    def fake_dispatch(aim_id, features, asset, state):
        captured_state["state"] = state
        return {"modifier": 1.0, "confidence": 0.5, "reason_tag": "OK"}

    with patch.object(aim_retroactive, "_load_historical_features",
                      return_value={"x": 1}), \
         patch.object(aim_retroactive, "compute_aim_modifier",
                      side_effect=fake_dispatch):
        aim_retroactive_replay(
            1, {"sl_multiplier": 0.7},
            (date(2026, 1, 12), date(2026, 1, 12)),
            user_id="u1", asset="ES",
        )
    assert captured_state["state"]["ES"]["sl_multiplier"] == 0.7


# --------------------------------------------------------------------------- #
# aggregate_modifiers                                                         #
# --------------------------------------------------------------------------- #


def test_aggregate_modifiers_weighted_average():
    """Per-day weighted-average across two AIMs."""
    series = {
        1: [(date(2026, 1, 12), 1.5), (date(2026, 1, 13), 2.0)],
        3: [(date(2026, 1, 12), 0.5), (date(2026, 1, 13), 1.0)],
    }
    weights = {1: 0.6, 3: 0.4}
    aggregated = aggregate_modifiers(series, weights)
    assert aggregated[0][0] == date(2026, 1, 12)
    # 0.6 * 1.5 + 0.4 * 0.5 / (0.6 + 0.4) = 1.1
    assert aggregated[0][1] == pytest.approx(1.1)
    # 0.6 * 2.0 + 0.4 * 1.0 / 1.0 = 1.6
    assert aggregated[1][1] == pytest.approx(1.6)


def test_aggregate_modifiers_skips_zero_weight_aims():
    series = {
        1: [(date(2026, 1, 12), 1.5)],
        3: [(date(2026, 1, 12), 0.5)],
    }
    weights = {1: 1.0, 3: 0.0}
    aggregated = aggregate_modifiers(series, weights)
    assert len(aggregated) == 1
    assert aggregated[0][1] == pytest.approx(1.5)


def test_aggregate_modifiers_handles_empty_input():
    assert aggregate_modifiers({}, {}) == []
    assert aggregate_modifiers({1: []}, {1: 1.0}) == []


# --------------------------------------------------------------------------- #
# b4_injection routing                                                        #
# --------------------------------------------------------------------------- #


def test_compute_aim_adjusted_edge_uses_retroactive_replay_when_window_supplied():
    """When historical_window + user_id + asset_id are passed, the helper
    invokes aim_retroactive_replay per active AIM."""
    from captain_offline.blocks.b4_injection import _compute_aim_adjusted_edge

    calls: list[int] = []

    def fake_replay(aim_id, candidate, window, *, user_id, asset):
        calls.append(aim_id)
        return [(date(2026, 1, 12), 1.5), (date(2026, 1, 13), 1.5)]

    with patch("shared.aim_retroactive.aim_retroactive_replay",
               side_effect=fake_replay):
        edge = _compute_aim_adjusted_edge(
            strategy={"sl_multiplier": 0.5},
            aim_weights={1: 0.5, 3: 0.5},
            historical_pnl=[10.0, 20.0],
            historical_window=(date(2026, 1, 12), date(2026, 1, 13)),
            user_id="u1",
            asset_id="ES",
        )
    assert sorted(calls) == [1, 3]
    # mean(10*1.5, 20*1.5) = 22.5
    assert edge == pytest.approx(22.5)


def test_compute_aim_adjusted_edge_falls_back_to_scalar_when_window_missing():
    """No window → original scalar heuristic preserved."""
    from captain_offline.blocks.b4_injection import _compute_aim_adjusted_edge

    edge = _compute_aim_adjusted_edge(
        strategy={"x": 1},
        aim_weights={1: 1.0, 3: 1.0},
        historical_pnl=[10.0, 20.0],
    )
    # mean(pnl)=15, mean(modifier)=(2/2)=1.0 → 15.0
    assert edge == pytest.approx(15.0)
