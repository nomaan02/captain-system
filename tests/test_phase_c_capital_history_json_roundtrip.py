"""Phase C: D16 capital_history JSON preserves Decimal dollar snapshots."""
from decimal import Decimal

from shared.decimal_json import dumps_decimal, loads_decimal


def test_capital_history_dumps_loads_decimal_preservation():
    payload = [
        {"date": "2026-04-28", "event": "bootstrap", "capital": Decimal("150000.00")},
        {"date": "2026-04-29", "event": "trade", "capital": Decimal("150125.37")},
    ]
    s = dumps_decimal(payload)
    out = loads_decimal(s)
    assert isinstance(out, list)
    assert out[0]["capital"] == Decimal("150000.00")
    assert out[1]["capital"] == Decimal("150125.37")
