"""Phase A: Layer 1 uses Decimal so boundary comparisons are exact."""
from decimal import Decimal

from captain_online.blocks.b5c_circuit_breaker import _layer1_preemptive_halt


def test_l1_boundary_lt_rho_blocks_when_sum_meets_halt():
    from shared.decimal_json import dumps_decimal

    intraday = {"l_t": Decimal("-495.00")}
    tsm = {
        "current_balance": Decimal("50000"),
        "account_id": "t1",
        "topstep_state": dumps_decimal({"computed_sod": {"L_halt": Decimal("750")}}),
        "topstep_params": "{}",
    }
    rho_j = Decimal("495.00")
    msg = _layer1_preemptive_halt(intraday, tsm, rho_j)
    assert msg is not None
    assert "990" in msg or "preemptive" in msg.lower()
