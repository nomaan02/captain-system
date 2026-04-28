"""Phase A: topstep_state JSON must preserve Decimals (dumps_decimal / loads_decimal)."""
from decimal import Decimal

from shared.decimal_json import dumps_decimal, loads_decimal


def test_topstep_state_computed_sod_dollar_fields_roundtrip():
    state = {
        "payout_rules": {"max_per_payout": Decimal("5000")},
        "computed_sod": {
            "E_daily_exposure": Decimal("1500.00"),
            "L_halt": Decimal("750.00"),
        },
    }
    s = dumps_decimal(state)
    back = loads_decimal(s)
    assert back["computed_sod"]["E_daily_exposure"] == Decimal("1500.00")
    assert back["computed_sod"]["L_halt"] == Decimal("750.00")
    assert back["payout_rules"]["max_per_payout"] == Decimal("5000")
