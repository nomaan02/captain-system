# region imports
from AlgorithmImports import *
# endregion
"""F-12: Redis consecutive-trade counters (4a); 4b logging BLOCKED — Q-26."""

from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks.b1_aim_lifecycle import (
    RECOVERY_CONSECUTIVE,
    SUPPRESSION_CONSECUTIVE_ZERO,
    run_aim_lifecycle,
)
from captain_offline.blocks.b1_dma_update import run_dma_update


class FakeRedis:
    """Minimal Redis hash behavior for aim_counters (decode_responses-style str values)."""

    def __init__(self):
        self.h = {}

    def hincrby(self, key, field, amount=1):
        d = self.h.setdefault(key, {})
        cur = int(d.get(field, 0))
        d[field] = cur + int(amount)
        return d[field]

    def hset(self, key, field=None, value=None, mapping=None):
        d = self.h.setdefault(key, {})
        if mapping is not None:
            for k, v in mapping.items():
                d[k] = int(v) if not isinstance(v, str) else v
        else:
            d[field] = int(value) if value is not None else 0
        return 1

    def hgetall(self, key):
        d = self.h.get(key, {})
        return {k: str(v) for k, v in d.items()}


def _four_phase_get_cursor():
    """get_cursor side_effect factory: D01 active ids, D02 rows, EWMA, write cursor."""
    n = [0]

    def _next(*_a, **_kw):
        phase = n[0] % 4
        n[0] += 1
        c = MagicMock()
        c.__enter__ = MagicMock(return_value=c)
        c.__exit__ = MagicMock(return_value=False)
        if phase == 0:
            c.fetchall.return_value = [(1,), (2,)]
        elif phase == 1:
            c.fetchall.return_value = [
                (1, 0.5, True, 0.0, 0),
                (2, 0.5, True, 0.0, 0),
            ]
        elif phase == 2:
            c.fetchall.return_value = [("s", 0.5, 1.0, 1.0, 10)]
        else:
            c.fetchall.return_value = []
        return c

    return _next, n


def test_consecutive_zero_increments_on_zero_dma_output():
    """Twenty DMA commits with inclusion_probability 0 for AIM-1 builds suppression counter."""
    fake = FakeRedis()
    get_c, _ctr = _four_phase_get_cursor()

    outcome_loss = {
        "asset": "ES",
        "pnl": -100.0,
        "contracts": 1,
        "regime_at_entry": "LOW_VOL",
        "aim_breakdown_at_entry": {
            "1": {"modifier": 1.1},
            "2": {"modifier": 1.0},
        },
    }

    with patch(
        "captain_offline.blocks.b1_dma_update.get_cursor",
        side_effect=get_c,
    ), patch(
        "captain_offline.blocks.b1_dma_update.get_redis_client",
        return_value=fake,
    ), patch(
        "captain_offline.blocks.b1_dma_update.snapshot_before_update",
        MagicMock(),
    ):
        for _ in range(SUPPRESSION_CONSECUTIVE_ZERO):
            _ctr[0] = 0
            run_dma_update(outcome_loss, commit=True)

    key = "aim_counters:1:ES"
    assert int(fake.h[key].get("consecutive_zero", 0)) >= SUPPRESSION_CONSECUTIVE_ZERO


def test_consecutive_zero_resets_on_nonzero():
    """After 19 zero-updates, one update with positive shar e resets consecutive_zero."""
    fake = FakeRedis()
    get_c, _ctr = _four_phase_get_cursor()
    outcome_loss = {
        "asset": "ES",
        "pnl": -100.0,
        "contracts": 1,
        "regime_at_entry": "LOW_VOL",
        "aim_breakdown_at_entry": {
            "1": {"modifier": 1.1},
            "2": {"modifier": 1.0},
        },
    }
    outcome_win = {
        "asset": "ES",
        "pnl": 500.0,
        "contracts": 1,
        "regime_at_entry": "LOW_VOL",
        "aim_breakdown_at_entry": {
            "1": {"modifier": 1.1},
            "2": {"modifier": 1.0},
        },
    }
    with patch(
        "captain_offline.blocks.b1_dma_update.get_cursor",
        side_effect=get_c,
    ), patch(
        "captain_offline.blocks.b1_dma_update.get_redis_client",
        return_value=fake,
    ), patch(
        "captain_offline.blocks.b1_dma_update.snapshot_before_update",
        MagicMock(),
    ):
        for _ in range(19):
            _ctr[0] = 0
            run_dma_update(outcome_loss, commit=True)
        _ctr[0] = 0
        run_dma_update(outcome_win, commit=True)

    assert int(fake.h["aim_counters:1:ES"].get("consecutive_zero", 0)) == 0


def test_consecutive_above_recovery():
    """SUPPRESSED AIM with ten DMA outputs > 0.1 triggers auto ACTIVE."""
    fake = FakeRedis()
    fake.h["aim_counters:1:ES"] = {"consecutive_above": RECOVERY_CONSECUTIVE}
    state = {
        "aim_id": 1,
        "asset_id": "ES",
        "status": "SUPPRESSED",
        "model_object": {},
        "warmup_progress": 0.0,
        "current_modifier": {},
        "last_retrained": None,
        "missing_data_rate_30d": 0,
    }
    with patch(
        "captain_offline.blocks.b1_aim_lifecycle.get_redis_client",
        return_value=fake,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._load_aim_states",
        return_value=[state],
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._load_meta_weight",
        return_value=0.15,
    ), patch(
        "captain_offline.blocks.b1_aim_lifecycle._update_aim_status",
    ) as mock_st, patch(
        "captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update",
        MagicMock(),
    ):
        run_aim_lifecycle("ES")
    assert any(c[0][2] == "ACTIVE" for c in mock_st.call_args_list)


@patch("captain_offline.blocks.b1_dma_update.snapshot_before_update")
@patch(
    "captain_offline.blocks.b1_dma_update._compute_likelihood",
    side_effect=[0.05, 0.95],
)
def test_mid_band_does_not_count(mock_likelihood, mock_snapshot):
    """0 < inclusion_probability <= 0.1 clears counters without increment."""
    fake = FakeRedis()
    fake.h["aim_counters:1:ES"] = {"consecutive_zero": 5, "consecutive_above": 5}

    get_c, _ctr = _four_phase_get_cursor()
    outcome = {
        "asset": "ES",
        "pnl": 0.0,
        "contracts": 1,
        "regime_at_entry": "LOW_VOL",
        "aim_breakdown_at_entry": {"1": {"modifier": 1.0}, "2": {"modifier": 1.0}},
    }

    with patch(
        "captain_offline.blocks.b1_dma_update.get_cursor",
        side_effect=get_c,
    ), patch(
        "captain_offline.blocks.b1_dma_update.get_redis_client",
        return_value=fake,
    ):
        _ctr[0] = 0
        run_dma_update(outcome, commit=True)

    d = fake.h["aim_counters:1:ES"]
    assert int(d["consecutive_zero"]) == 0
    assert int(d["consecutive_above"]) == 0


@pytest.mark.skip(reason="BLOCKED — Q-26 unresolved (P3-D06 suppression event shape)")
def test_suppression_event_logged_to_p3_d06():
    raise AssertionError("unreachable")
