"""Bug A regression — b7 PnL must use D00 point_value per symbol, never default to 50.

Origin: 2026-04-29 production incident. The Captain System silo drawdown
tripped at 39.2% (~-$59K) when the actual cumulative PnL on TopstepX was
only ~-$2.7K. Investigation found `b7_position_monitor.resolve_position`
read `pos.get("point_value", 50.0)`, defaulting to ES's PV for every asset
because `sanitise_for_api` strips the field before it reaches B7.

These tests pin the per-symbol gross_pnl invariant against D00's authoritative
contract specs and assert the historic 50.0 default is gone for good.

Inflation ratios that this test prevents (50 / true_PV per asset):
    MES  -> 10x   (true PV 5,    bug applied 50)
    M2K  -> 10x   (true PV 5,    bug applied 50)
    MNQ  -> 25x   (true PV 2,    bug applied 50)
    MGC  ->  5x   (true PV 10,   bug applied 50)
    MYM  -> 100x  (true PV 0.5,  bug applied 50)
    NQ   -> 2.5x  (true PV 20,   bug applied 50)
    NKD  -> 10x   (true PV 5,    bug applied 50)
    ZB   -> 0.05x (true PV 1000, bug applied 50)  -- under-reported
    ZN   -> 0.05x (true PV 1000, bug applied 50)  -- under-reported
    ES   ->  1x   (true PV 50,   bug applied 50)  -- only correct case
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# Authoritative per-asset specs from p3_d00_asset_universe (matches
# scripts/bootstrap_production.py ASSET_SPECS).
PER_SYMBOL_POINT_VALUE = {
    "ES":  Decimal("50"),
    "MES": Decimal("5"),
    "NQ":  Decimal("20"),
    "MNQ": Decimal("2"),
    "M2K": Decimal("5"),
    "MYM": Decimal("0.5"),
    "NKD": Decimal("5"),
    "MGC": Decimal("10"),
    "ZB":  Decimal("1000"),
    "ZN":  Decimal("1000"),
}


def _make_d00_cursor(point_value: Decimal | None):
    """Return a context-manager-cursor that yields a single (point_value,) row."""
    cursor = MagicMock()
    cursor.fetchone.return_value = (point_value,) if point_value is not None else None
    ctx = MagicMock()
    ctx.__enter__.return_value = cursor
    ctx.__exit__.return_value = False
    return ctx, cursor


def _make_pos(asset: str, *, entry: float, contracts: int = 1, direction: int = 1,
              actual_entry: float | None = None,
              # Intentionally include a stale 50.0 to prove the writer ignores it
              poison_point_value: float | None = 50.0):
    pos = {
        "signal_id": "SIG-T1",
        "user_id": "test_user",
        "account": "ACC-T1",
        "asset": asset,
        "direction": direction,
        "entry_price": entry,
        "signal_entry_price": entry,
        "contracts": contracts,
        "regime_state": "REGIME_NEUTRAL",
        "tsm_id": None,
    }
    if actual_entry is not None:
        pos["actual_entry_price"] = actual_entry
    if poison_point_value is not None:
        # Bug A regression bait: even with 50.0 poisoned on the pos dict,
        # the writer must ignore it and read the true value from D00.
        pos["point_value"] = poison_point_value
    return pos


# ---------------------------------------------------------------------------
# _resolve_point_value direct contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "asset_id,expected_pv",
    sorted(PER_SYMBOL_POINT_VALUE.items()),
)
def test_resolve_point_value_returns_d00_value(asset_id, expected_pv):
    """For every active asset, _resolve_point_value returns D00's value."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    ctx, _ = _make_d00_cursor(expected_pv)

    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx):
        result = b7._resolve_point_value(asset_id)

    assert result == expected_pv
    assert isinstance(result, Decimal)


def test_resolve_point_value_caches_subsequent_calls():
    """Second call for the same asset MUST NOT hit the database."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    ctx, cursor = _make_d00_cursor(Decimal("10"))

    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx) as get_cursor_patch:
        b7._resolve_point_value("MGC")
        b7._resolve_point_value("MGC")
        b7._resolve_point_value("MGC")

    # First call should hit DB once; subsequent calls served from cache.
    assert get_cursor_patch.call_count == 1


def test_resolve_point_value_raises_when_d00_missing():
    """D00 returns no row -> raise, NEVER silently default to 50."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    ctx, _ = _make_d00_cursor(None)

    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx):
        with pytest.raises(b7.PointValueResolutionError) as excinfo:
            b7._resolve_point_value("UNKNOWN_ASSET")

    assert "UNKNOWN_ASSET" in str(excinfo.value)
    # Cache must NOT be populated on failure.
    assert "UNKNOWN_ASSET" not in b7._POINT_VALUE_CACHE


def test_resolve_point_value_raises_on_zero_or_negative():
    """Zero/negative point_value in D00 is corrupted data; refuse to use."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    ctx, _ = _make_d00_cursor(Decimal("0"))

    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx):
        with pytest.raises(b7.PointValueResolutionError):
            b7._resolve_point_value("ES")


def test_resolve_point_value_raises_on_db_error():
    """DB failure must raise — never a silent default."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    raising_get_cursor = MagicMock(side_effect=RuntimeError("connection lost"))

    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               raising_get_cursor):
        with pytest.raises(b7.PointValueResolutionError):
            b7._resolve_point_value("ES")


def test_resolve_point_value_rejects_empty_asset():
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    with pytest.raises(b7.PointValueResolutionError):
        b7._resolve_point_value("")


# ---------------------------------------------------------------------------
# resolve_position end-to-end PnL — the regression test that should have
# caught Bug A on day 1.
# ---------------------------------------------------------------------------

# (asset, entry, exit, direction, contracts, expected_gross_pnl)
# Hand-computed via (exit - entry) * direction * contracts * D00.point_value.
# The user's incident report confirms ES is the only asset where the bugged
# default (50) coincidentally matches D00 — every other row was inflated.
PNL_CASES = [
    # ES: 5 points * 1 contract * $50 = $250
    ("ES",  Decimal("5995.00"), Decimal("6000.00"), 1, 1, Decimal("250.00")),
    # MES: 5 points * 2 contracts * $5 = $50  (was $500 under bug — 10x)
    ("MES", Decimal("5995.00"), Decimal("6000.00"), 1, 2, Decimal("50.00")),
    # MNQ: 10 points * 1 contract * $2 = $20  (was $500 under bug — 25x)
    ("MNQ", Decimal("21000.00"), Decimal("21010.00"), 1, 1, Decimal("20.00")),
    # M2K: 4 points * 3 contracts * $5 = $60  (was $600 under bug — 10x)
    ("M2K", Decimal("2200.00"), Decimal("2204.00"), 1, 3, Decimal("60.00")),
    # MGC short: -10 points (price up, short) * 2 contracts * $10 = -$200
    # exit > entry, direction=-1 -> loss. (was -$1000 under bug — 5x)
    ("MGC", Decimal("4742.10"), Decimal("4752.10"), -1, 2, Decimal("-200.00")),
    # MGC long winning: 61.6 points * 1 * $10 = $616 (the actual MGC trade)
    ("MGC", Decimal("4742.10"), Decimal("4803.70"), 1, 1, Decimal("616.00")),
    # MYM: 100 points * 1 * $0.50 = $50  (was $5000 under bug — 100x!)
    ("MYM", Decimal("39500.00"), Decimal("39600.00"), 1, 1, Decimal("50.00")),
    # NKD: 50 points * 1 * $5 = $250 (was $2500 under bug — 10x)
    ("NKD", Decimal("39500.00"), Decimal("39550.00"), 1, 1, Decimal("250.00")),
    # ZB: 1 point * 1 * $1000 = $1000 (was $50 under bug — 0.05x, UNDER-REPORTED)
    ("ZB",  Decimal("117.00"), Decimal("118.00"), 1, 1, Decimal("1000.00")),
]


@pytest.mark.parametrize(
    "asset,entry,exit_,direction,contracts,expected_gross",
    PNL_CASES,
    ids=[c[0] + (f"_{c[3]}d{c[4]}c" if c[3] != 1 or c[4] != 1 else "") for c in PNL_CASES],
)
def test_resolve_position_writes_correct_per_symbol_gross_pnl(
    asset, entry, exit_, direction, contracts, expected_gross,
):
    """gross_pnl written to D03 equals (exit-entry) * dir * contracts * D00.point_value.

    Most importantly: even with a 50.0 left on `pos["point_value"]` (simulating
    the legacy default-cascade), the writer ignores it and reads from D00.
    """
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    # Pre-populate cache with D00 value for the asset under test
    b7._POINT_VALUE_CACHE[asset] = PER_SYMBOL_POINT_VALUE[asset]

    pos = _make_pos(
        asset, entry=float(entry), contracts=contracts, direction=direction,
        actual_entry=None, poison_point_value=50.0,
    )

    captured = {}

    def _capture_write(**kwargs):
        captured.update(kwargs)

    with patch.object(b7, "_write_trade_outcome", side_effect=_capture_write), \
         patch.object(b7, "resolve_commission", return_value=0.0), \
         patch.object(b7, "_update_capital_and_cb"), \
         patch.object(b7, "_publish_trade_outcome"), \
         patch.object(b7, "_notify"):
        b7.resolve_position(pos, "TP_HIT", float(exit_), tsm_configs={})

    assert captured["asset"] == asset
    assert captured["gross_pnl"] == expected_gross, (
        f"gross_pnl for {asset} should be {expected_gross}, "
        f"got {captured['gross_pnl']} — "
        f"is the 50.0 default leaking back in?"
    )
    # net_pnl identity (commission=0 here)
    assert captured["net_pnl"] == expected_gross


def test_resolve_position_uses_d00_even_when_pos_has_wrong_point_value():
    """Belt-and-braces: pos['point_value']=999 must be ignored entirely."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    b7._POINT_VALUE_CACHE["MGC"] = Decimal("10")  # canonical D00 value

    pos = _make_pos("MGC", entry=4742.10, contracts=1, direction=1,
                    poison_point_value=999.0)  # blatantly wrong

    captured = {}
    with patch.object(b7, "_write_trade_outcome",
                      side_effect=lambda **kw: captured.update(kw)), \
         patch.object(b7, "resolve_commission", return_value=0.0), \
         patch.object(b7, "_update_capital_and_cb"), \
         patch.object(b7, "_publish_trade_outcome"), \
         patch.object(b7, "_notify"):
        b7.resolve_position(pos, "TP_HIT", 4803.70, tsm_configs={})

    # 61.6 * 1 * 10 = 616 — uses D00, not pos[point_value]
    assert captured["gross_pnl"] == Decimal("616.00")


def test_resolve_position_raises_when_d00_lookup_fails():
    """If D00 has no point_value row for the asset, refuse to write D03."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    ctx, _ = _make_d00_cursor(None)  # D00 returns nothing

    pos = _make_pos("UNKNOWN", entry=100.0)

    with patch("captain_online.blocks.b7_position_monitor.get_cursor",
               return_value=ctx), \
         patch.object(b7, "_write_trade_outcome") as mock_write, \
         patch.object(b7, "resolve_commission", return_value=0.0), \
         patch.object(b7, "_update_capital_and_cb"), \
         patch.object(b7, "_publish_trade_outcome"), \
         patch.object(b7, "_notify"):
        with pytest.raises(b7.PointValueResolutionError):
            b7.resolve_position(pos, "TP_HIT", 101.0, tsm_configs={})

    # Critical: D03 must NOT be written if point_value can't be resolved.
    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Slippage uses the same D00 point_value
# ---------------------------------------------------------------------------

def test_resolve_position_slippage_uses_d00_point_value():
    """Slippage = (actual_entry - signal_entry) * dir * contracts * pv (from D00)."""
    from captain_online.blocks import b7_position_monitor as b7

    b7._reset_point_value_cache()
    b7._POINT_VALUE_CACHE["MGC"] = Decimal("10")

    # signal said 4742.00, fill came in at 4742.10 -> 0.10 points adverse on long
    pos = _make_pos("MGC", entry=4742.00, contracts=1, direction=1,
                    actual_entry=4742.10, poison_point_value=50.0)
    pos["signal_entry_price"] = 4742.00

    captured = {}
    with patch.object(b7, "_write_trade_outcome",
                      side_effect=lambda **kw: captured.update(kw)), \
         patch.object(b7, "resolve_commission", return_value=0.0), \
         patch.object(b7, "_update_capital_and_cb"), \
         patch.object(b7, "_publish_trade_outcome"), \
         patch.object(b7, "_notify"):
        b7.resolve_position(pos, "TP_HIT", 4803.70, tsm_configs={})

    # slippage = (4742.10 - 4742.00) * 1 * 1 * 10 = 1.00 (NOT 5.00 with the buggy 50)
    assert captured["slippage"] == Decimal("1.00")
