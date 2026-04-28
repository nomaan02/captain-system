"""Phase A: D23 l_b JSON path — cumulative Decimal sum matches exact sum."""
from decimal import Decimal

from shared.decimal_json import dumps_decimal, loads_decimal


def test_fifty_trades_basket_sum_exact():
    l_b = {}
    key = "4"
    total = Decimal("0")
    for _ in range(50):
        step = Decimal("0.03")
        total += step
        l_b[key] = l_b.get(key, Decimal("0")) + step
    raw = dumps_decimal(l_b)
    back = loads_decimal(raw)
    assert back[key] == Decimal("1.50")
    assert total == Decimal("1.50")
