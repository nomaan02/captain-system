"""Phase 2 regression: b4_kelly_sizing._get_expected_fee with Decimal-encoded JSON.

Pre-fix, _get_expected_fee called parse_json (not parse_json_decimal) on
the fee_schedule STRING column. After Phase A's dumps_decimal write path,
the encoded JSON contains numeric strings that parse_json returned as
Python str — `cpc * 2` then mis-typed (str * int = string repeat). The
fix uses parse_json_decimal + as_money + to_float boundary.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from shared.decimal_json import dumps_decimal


def _tsm_with_fee_schedule(fees: dict) -> dict:
    """Build a TSM dict whose fee_schedule is a Phase-A-encoded JSON string."""
    return {"fee_schedule": dumps_decimal(fees)}


class TestFeeScheduleByInstrument:
    def test_decimal_round_turn_returns_correct_float(self):
        from captain_online.blocks.b4_kelly_sizing import (
            _get_expected_fee,
        )
        tsm = _tsm_with_fee_schedule({
            "fees_by_instrument": {
                "ES": {"round_turn": Decimal("3.85")},
                "MES": {"round_turn": Decimal("0.74")},
            }
        })
        assert _get_expected_fee(tsm, "ES") == 3.85
        assert _get_expected_fee(tsm, "MES") == 0.74

    def test_unknown_asset_falls_back_to_default_round_turn(self):
        from captain_online.blocks.b4_kelly_sizing import (
            _get_expected_fee,
        )
        tsm = _tsm_with_fee_schedule({
            "default_round_turn": Decimal("4.20"),
            "fees_by_instrument": {"ES": {"round_turn": Decimal("3.85")}},
        })
        assert _get_expected_fee(tsm, "MNQ") == 4.20

    def test_no_fee_schedule_falls_back_to_commission_per_contract(self):
        from captain_online.blocks.b4_kelly_sizing import (
            _get_expected_fee,
        )
        # commission_per_contract is the D08 column — Decimal post-Phase-A
        tsm = {"commission_per_contract": Decimal("1.40")}
        # round-trip = cpc * 2
        assert _get_expected_fee(tsm, "ES") == 2.80

    def test_zero_commission_returns_zero(self):
        from captain_online.blocks.b4_kelly_sizing import (
            _get_expected_fee,
        )
        tsm = {"commission_per_contract": Decimal("0.00")}
        assert _get_expected_fee(tsm, "ES") == 0.0

    def test_no_fee_data_at_all_returns_zero(self):
        from captain_online.blocks.b4_kelly_sizing import (
            _get_expected_fee,
        )
        assert _get_expected_fee({}, "ES") == 0.0
