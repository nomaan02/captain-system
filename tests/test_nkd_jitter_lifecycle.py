"""C16 — NKD jitter lifecycle: B6 samples J → position dict → trail block.

Tests that:
1. B6 samples J exactly once per NKD signal on Isaac tower.
2. J is stored in the signal payload (jitter_j, jitter_x, jitter_y fields).
3. The trail block reads J from the position dict without re-sampling.
4. On Isaac tower, NKD tp_level in the signal = _tp_from_dollars(4450 + J).
5. On Nomaan tower, J=0 → tp_level = _tp_from_dollars(4450 + 0) = standard.
"""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from captain_online.blocks.b6_signal_output import run_signal_output, _tp_from_dollars
from captain_online.blocks import b7b_nkd_trail
from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails
from tests.fixtures.synthetic_data import make_features, make_locked_strategy, make_assets_detail
from tests.fixtures.user_fixtures import make_user_silo, make_tsm_configs


NKD_ENTRY = 38000.0
NKD_POINT_VALUE = 5.0
NKD_TICK_SIZE = 5.0
NKD_TP_DOLLARS = 4450.0


def _make_nkd_signal_result(parity_env: str, entry: float = NKD_ENTRY):
    """Run B6 with NKD strategy and return the raw signal dict."""
    nkd_features = make_features("NKD")
    nkd_features["NKD"]["entry_price"] = entry
    nkd_features["NKD"]["or_range"] = 125.0
    nkd_features["NKD"]["or_direction"] = 1

    nkd_strategy = make_locked_strategy(
        "NKD",
        is_nkd_trail=True,
        tp_dollars=4450,
        sl_dollars_fixed=1025,
        sl_multiple=0.35,
        tp_multiple=0.70,
        default_direction=1,
    )
    nkd_assets_detail = make_assets_detail(
        "NKD",
        point_value=Decimal(str(NKD_POINT_VALUE)),
        tick_size=Decimal(str(NKD_TICK_SIZE)),
    )

    with patch("captain_online.blocks.b6_signal_output._publish_signals"), \
         patch("captain_online.blocks.b6_signal_output._log_signal_output"), \
         patch("captain_online.blocks.b6_signal_output._load_system_param",
               side_effect=lambda k, d: d), \
         patch("captain_online.blocks.b6_signal_output._get_daily_pnl",
               return_value=0.0), \
         patch.dict(os.environ, {"INSTANCE_PARITY": parity_env}):
        result = run_signal_output(
            recommended_trades=["NKD"],
            available_not_recommended=[],
            quality_results={"NKD": {"quality_score": 0.015, "quality_multiplier": 1.0,
                                     "data_maturity": 1.0}},
            final_contracts={"NKD": {"acc_1": 1}},
            account_recommendation={"NKD": {"acc_1": "TRADE"}},
            account_skip_reason={"NKD": {"acc_1": None}},
            features=nkd_features,
            ewma_states={},
            aim_breakdown={"NKD": {}},
            combined_modifier={"NKD": 1.0},
            regime_probs={"NKD": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4}},
            expected_edge={"NKD": 0.02},
            locked_strategies=nkd_strategy,
            tsm_configs={},
            user_silo=make_user_silo(accounts=["acc_1"]),
            assets_detail=nkd_assets_detail,
            session_id=3,
        )
    return result["signals"][0]


@pytest.fixture(autouse=True)
def _reset_trail_state():
    b7b_nkd_trail._reset_state_for_tests()
    yield
    b7b_nkd_trail._reset_state_for_tests()


class TestB6JitterSampling:
    """B6 samples J on Isaac tower and embeds it in the signal payload."""

    def test_nomaan_signal_has_zero_jitter(self):
        """Nomaan tower (parity=0): jitter_j=0.0, tp_level = standard 4450-based value."""
        signal = _make_nkd_signal_result(parity_env="0")
        assert signal["jitter_j"] == 0.0
        assert signal["jitter_x"] == 0.0
        assert signal["jitter_y"] == 0
        # tp_level should be at standard 4450 from entry
        expected_tp = _tp_from_dollars(
            NKD_TP_DOLLARS, NKD_ENTRY, 1, NKD_POINT_VALUE, 1, "NKD")
        assert signal["tp_level"] == pytest.approx(expected_tp, abs=NKD_TICK_SIZE)

    def test_isaac_signal_has_nonzero_jitter(self):
        """Isaac tower (parity=1): jitter_j != 0.0 in the signal payload."""
        import random
        random.seed(42)
        signal = _make_nkd_signal_result(parity_env="1")
        assert "jitter_j" in signal, "jitter_j must be in NKD signal payload"
        assert "jitter_x" in signal
        assert "jitter_y" in signal
        assert signal["jitter_y"] in (-1, 1)
        assert abs(signal["jitter_j"]) >= 0.2 - 1e-9, \
            f"|J|={abs(signal['jitter_j'])} should be >= 0.2 on Isaac tower"

    def test_jitter_shifts_broker_tp_by_j(self):
        """On Isaac tower, NKD signal tp_level = _tp_from_dollars(4450 + J, ...)."""
        import random
        random.seed(99)
        signal = _make_nkd_signal_result(parity_env="1")
        j = signal["jitter_j"]
        tp_level = signal["tp_level"]
        expected_tp = _tp_from_dollars(
            NKD_TP_DOLLARS + j, NKD_ENTRY, 1, NKD_POINT_VALUE, 1, "NKD")
        assert tp_level == pytest.approx(expected_tp, abs=NKD_TICK_SIZE), (
            f"Isaac tp_level={tp_level} should be _tp_from_dollars(4450+{j})={expected_tp}"
        )


class TestJitterPersistsFromB6ToTrailBlock:
    """J sampled by B6 must be preserved through the position dict so the
    trail block never re-samples mid-trade."""

    def _make_nkd_position_from_signal(self, signal: dict) -> dict:
        """Build a trail-block position dict shaped like a TAKEN message."""
        entry = NKD_ENTRY
        d_init = signal.get("snapped_d_init", 1025.0)
        jitter_j = Decimal(str(signal.get("jitter_j", 0.0)))
        return {
            "signal_id": signal["signal_id"],
            "user_id": signal.get("user_id", "primary_user"),
            "asset": "NKD",
            "direction": signal["direction"],
            "entry_price": Decimal(str(entry)),
            "contracts": signal["size"],
            "account": "21855714",
            "session": 3,
            "bracket": True,
            "entry_order_id": "ORD-ENTRY-1",
            "sl_order_id": 99901,
            "tp_order_id": 99902,
            "is_nkd_trail": True,
            "tp_dollars": Decimal("4450"),
            "snapped_d_init": Decimal(str(d_init)),
            "jitter_x": Decimal(str(signal.get("jitter_x", 0.0))),
            "jitter_y": signal.get("jitter_y", 0),
            "jitter_j": jitter_j,
            "current_phase": None,
            "current_buffer": None,
            "current_stop_price": None,
            "modify_seq": 0,
            "point_value": Decimal(str(NKD_POINT_VALUE)),
        }

    def test_jitter_persists_from_b6_to_trail_block(self):
        """B6 samples J → position dict contains jitter_j → trail block reads
        it without re-sampling across 10 polls."""
        import random
        random.seed(7)
        signal = _make_nkd_signal_result(parity_env="1")
        original_j = signal["jitter_j"]
        assert original_j != 0.0, "Expected non-zero J from Isaac tower"

        pos = self._make_nkd_position_from_signal(signal)
        client = MagicMock()
        client.modify_order.return_value = {"success": True}

        # Run 10 polls at rising marks through Phase B
        for pnl in [2000, 2200, 2400, 2600, 2800, 2900, 2999, 3000, 3500, 4000]:
            mark = Decimal(str(NKD_ENTRY)) + Decimal(str(pnl)) / Decimal(str(NKD_POINT_VALUE))
            scan_nkd_trails(
                open_positions=[pos],
                client=client,
                redis_client=None,
                quote_lookup=lambda a, c: (mark, None),
                persist_d34=lambda row: None,
                compliance_modify_check=lambda *_: (True, None),
                parity_env="1",
            )
            # J must be unchanged after every poll
            assert float(pos["jitter_j"]) == pytest.approx(original_j), (
                f"jitter_j changed after poll at pnl={pnl}: "
                f"was {original_j}, now {float(pos['jitter_j'])}"
            )
