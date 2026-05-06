"""Phase 5: B4 _compute_topstep_daily_cap reads per-session E_daily_exposure."""
from decimal import Decimal

from shared.decimal_json import dumps_decimal


def _tsm_with_session_map(per_session: dict, c: float = 1.0) -> dict:
    """Build a TSM dict with topstep_state.computed_sod.session populated."""
    return {
        "current_balance": Decimal("150000.00"),
        "topstep_optimisation": True,
        "topstep_params": f'{{"c": {c}, "e": 0.01, "p": 0.005}}',
        "topstep_state": dumps_decimal({
            "computed_sod": {
                "L_halt": Decimal("1500"),
                "E_daily_exposure": Decimal("1500"),  # legacy flat
                "session": per_session,
            },
        }),
    }


def test_per_session_cap_reads_session_specific_e():
    """NY gets E_NY=$465; APAC gets E_APAC=$345. Each cap is independent."""
    from captain_online.blocks.b4_kelly_sizing import _compute_topstep_daily_cap

    tsm = _tsm_with_session_map({
        "NY":   {"L_halt": Decimal("465"), "E_daily_exposure": Decimal("465"),
                 "share": Decimal("0.31")},
        "LON":  {"L_halt": Decimal("345"), "E_daily_exposure": Decimal("345"),
                 "share": Decimal("0.23")},
        "APAC": {"L_halt": Decimal("345"), "E_daily_exposure": Decimal("345"),
                 "share": Decimal("0.23")},
    })

    # ES: strategy_sl=4 pts, point_value=$50/pt → risk_per_trade=$200/contract
    # NY cap = floor(465 / 200) = 2
    cap_ny = _compute_topstep_daily_cap(tsm, strategy_sl=4.0, point_value=50.0, session_id=1)
    assert cap_ny == 2

    # APAC NKD: strategy_sl=6 pts, point_value=$5/pt → $30/contract
    # APAC cap = floor(345 / 30) = 11 contracts.
    cap_apac = _compute_topstep_daily_cap(tsm, strategy_sl=6.0, point_value=5.0, session_id=3)
    assert cap_apac == 11


def test_falls_back_to_flat_e_when_no_session_map():
    """Pre-Phase-2 state (no session block) → uses legacy flat E."""
    from captain_online.blocks.b4_kelly_sizing import _compute_topstep_daily_cap

    tsm = {
        "current_balance": Decimal("150000.00"),
        "topstep_optimisation": True,
        "topstep_params": '{"c": 1.0, "e": 0.01, "p": 0.005}',
        "topstep_state": dumps_decimal({
            "computed_sod": {
                "L_halt": Decimal("1500"),
                "E_daily_exposure": Decimal("1500"),
                # No session block
            },
        }),
    }
    # NY cap = floor(1500 / 200) = 7 (full day budget)
    cap = _compute_topstep_daily_cap(tsm, strategy_sl=4.0, point_value=50.0, session_id=1)
    assert cap == 7


def test_returns_999_when_no_topstep_optimisation():
    from captain_online.blocks.b4_kelly_sizing import _compute_topstep_daily_cap

    tsm = {"topstep_optimisation": False}
    assert _compute_topstep_daily_cap(tsm, session_id=1) == 999


def test_static_fallback_when_e_is_zero():
    """Pre-SOD state (no computed_sod or E=0) → static cap from topstep_params."""
    from captain_online.blocks.b4_kelly_sizing import _compute_topstep_daily_cap

    tsm = {
        "current_balance": Decimal("150000.00"),
        "topstep_optimisation": True,
        "topstep_params": '{"c": 1.0, "e": 0.01, "daily_contract_cap": 5}',
        "topstep_state": "{}",
    }
    cap = _compute_topstep_daily_cap(tsm, strategy_sl=4.0, point_value=50.0, session_id=1)
    assert cap == 5
