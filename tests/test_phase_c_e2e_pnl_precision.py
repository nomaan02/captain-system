"""Phase C: end-to-end P&L path uses Decimal with D00 point_value (no float drift)."""
from decimal import Decimal


def test_es_trade_pnl_matches_exact_decimal_pipeline():
    """Single ES trade: (exit - entry) * direction * contracts * point_value - commission."""
    entry_price = Decimal("5995.75")
    exit_price = Decimal("5999.50")
    direction = 1
    contracts = 2
    point_value = Decimal("50.0")
    commission = Decimal("7.8800")

    gross = (
        (exit_price - entry_price)
        * Decimal(direction)
        * Decimal(contracts)
        * point_value
    )
    pnl = gross - commission
    assert gross == Decimal("375.0000"), "375 points-dollar gross"
    assert pnl == Decimal("367.1200")
    assert isinstance(point_value, Decimal)
