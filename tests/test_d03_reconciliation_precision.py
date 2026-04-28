"""Phase B: D03 net P&L matches broker identity gross − commission (unit-level).

Broker statements report net realised P&L per fill. The migration stores
``gross_pnl``, ``commission``, and ``pnl`` (net) as DECIMAL; helper
``RealisedOutcome`` and aggregation must preserve ``gross − commission = net``.
"""
from __future__ import annotations

from decimal import Decimal

from shared.trade_source import RealisedOutcome, _aggregate_outcomes, _row_to_outcome


def _row(
    trade_id: str,
    signal_id: str,
    net: Decimal,
    gross: Decimal,
    commission: Decimal,
):
    return (
        trade_id,
        signal_id,
        net,
        gross,
        commission,
        1,
        Decimal("100"),
        Decimal("101"),
        None,
        None,
        1,
        "LOW_VOL",
    )


def test_single_trade_reconciles_to_broker_net():
    """One D03 row: net P&L equals gross minus commission (exact)."""
    gross = Decimal("1000.01")
    commission = Decimal("2.50")
    net = gross - commission
    r = _row("TRD-1", "SIG-1", net, gross, commission)
    o = _row_to_outcome(r)
    assert isinstance(o, RealisedOutcome)
    assert o.pnl == net
    assert o.gross_pnl == gross
    assert o.commission == commission
    assert o.gross_pnl - o.commission == o.pnl


def test_daily_aggregate_matches_broker_statement_sum():
    """Multiple fills same day: sum of nets equals sum of (gross − commission)."""
    rows = [
        _row("A", "S1", Decimal("10.01"), Decimal("12.01"), Decimal("2.00")),
        _row("B", "S2", Decimal("-5.10"), Decimal("-3.10"), Decimal("2.00")),
        _row("C", "S3", Decimal("0.25"), Decimal("1.25"), Decimal("1.00")),
    ]
    for r in rows:
        assert r[2] == r[3] - r[4]
    agg = _aggregate_outcomes(rows)
    manual_net = sum((r[3] - r[4]) for r in rows)
    assert agg.pnl == manual_net
    assert agg.gross_pnl == sum(r[3] for r in rows)
    assert agg.commission == sum(r[4] for r in rows)
