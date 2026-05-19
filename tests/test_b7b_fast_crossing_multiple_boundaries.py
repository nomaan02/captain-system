"""Fast-crossing integration test: NKD trail phase math is stateless.

Audit §5.4 H1: when PnL jumps multiple $500 boundaries in a single 10-second
poll (e.g. a news-driven gap on NKD), the trail block must compute the FINAL
phase + buffer in one pass and issue ONE modify call — never walk each
boundary intermediately.

Negative phrasing: if a 0 → $4200 PnL jump in one poll caused 8 separate
modify calls (one per $500 step), TopstepX would rate-limit us and the
trail could miss the actual phase transition.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from captain_online.blocks import b7b_nkd_trail
from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails

# Shared NKD spec — duplicated here so this file is self-contained.
NKD_POINT_VALUE = Decimal("5")


def _pnl_to_mark_long(pnl_dollars, entry, contracts=1):
    return Decimal(str(entry)) + Decimal(str(pnl_dollars)) / (
        NKD_POINT_VALUE * Decimal(contracts))


@pytest.fixture(autouse=True)
def _reset_state():
    b7b_nkd_trail._reset_state_for_tests()
    yield
    b7b_nkd_trail._reset_state_for_tests()


def _make_position(
    *, snapped_d_init=Decimal("1750"), sl_order_id=999_777,
    signal_id="SIG-NKDFAST00001",
):
    return {
        "signal_id": signal_id, "user_id": "primary_user", "asset": "NKD",
        "direction": 1, "entry_price": Decimal("38000"),
        "contracts": 1, "tp_level": Decimal("38890"),
        "sl_level": Decimal("38000") - snapped_d_init / NKD_POINT_VALUE,
        "point_value": NKD_POINT_VALUE,
        "account": "21855714", "session": 3,
        "bracket": True, "entry_order_id": "ENT-FAST",
        "sl_order_id": sl_order_id, "tp_order_id": 999_778,
        "is_nkd_trail": True, "tp_dollars": Decimal("4450"),
        "snapped_d_init": snapped_d_init,
        "jitter_x": None, "jitter_y": None, "jitter_j": None,
        "current_phase": None, "current_buffer": None,
        "current_stop_price": None, "modify_seq": 0,
    }


def test_single_poll_jumping_0_to_4200_issues_one_modify_for_phase_c():
    """0 → $4200 in one poll lands in Phase C; ONE modify call, not 8."""
    pos = _make_position()
    client = MagicMock()
    client.modify_order.return_value = {"success": True}
    persisted = []

    def _q(_asset, _cid):
        return (_pnl_to_mark_long(Decimal("4200"), 38000), 0.0)

    scan_nkd_trails(
        open_positions=[pos],
        client=client,
        redis_client=None,
        quote_lookup=_q,
        persist_d34=persisted.append,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0",
        execution_mode="AUTO",
    )

    # Exactly ONE broker call — for the final Phase C state
    assert client.modify_order.call_count == 1, (
        f"Expected 1 modify call for fast 0→$4200 jump, got "
        f"{client.modify_order.call_count}"
    )
    # Position state reflects FINAL phase (not the intermediates we
    # crossed)
    assert pos["current_phase"] == "C"
    assert pos["current_buffer"] == Decimal("450")
    # Stop placement: mark = 38840, buffer=450, distance=90 → stop=38750
    assert pos["current_stop_price"] == Decimal("38750")
    # D34: exactly one row for this poll
    assert len(persisted) == 1
    assert persisted[0]["phase"] == "C"
    assert persisted[0]["modify_seq"] == 1


def test_single_poll_jumping_0_to_3000_lands_in_phase_c():
    """0 → $3000 jump in one poll lands exactly at the Phase C boundary.

    C14 replaced the linear taper with a step-ladder:
      Phase A: pnl < $2,000  (buffer = snapped_d_init = $1,750)
      Phase B: $2,000 <= pnl < $3,000  (buffer = $1,000 flat)
      Phase C: pnl >= $3,000  (buffer = $450 flat)

    At exactly pnl = $3,000 the condition `pnl < _PHASE_C_START_BASE_DOLLARS`
    evaluates False, so the step-ladder routes to Phase C with a $450 buffer.
    This test was previously named "…_phase_b_midpoint" and used the old
    linear-taper formula; updated in Batch 4 to match the C14 step-ladder.
    """
    pos = _make_position()
    client = MagicMock()
    client.modify_order.return_value = {"success": True}

    def _q(_asset, _cid):
        return (_pnl_to_mark_long(Decimal("3000"), 38000), 0.0)

    scan_nkd_trails(
        open_positions=[pos], client=client, redis_client=None,
        quote_lookup=_q,
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )

    assert client.modify_order.call_count == 1
    assert pos["current_phase"] == "C"
    assert pos["current_buffer"] == Decimal("450")


def test_pre_existing_phase_a_stop_replaced_by_phase_c_in_one_poll():
    """Position that previously sat in Phase A is jumped to Phase C in a
    single poll. New stop wins via ratchet (it's tighter)."""
    # Previous state: Phase A stop placed at mark 38080 minus full d_init
    # 38080 - 1750/5 = 38080 - 350 = 37730
    pos = _make_position()
    pos["current_phase"] = "A"
    pos["current_buffer"] = Decimal("1750")
    pos["current_stop_price"] = Decimal("37730")
    pos["modify_seq"] = 1

    client = MagicMock()
    client.modify_order.return_value = {"success": True}

    def _q(_asset, _cid):
        return (_pnl_to_mark_long(Decimal("4200"), 38000), 0.0)

    scan_nkd_trails(
        open_positions=[pos], client=client, redis_client=None,
        quote_lookup=_q,
        persist_d34=lambda r: None,
        compliance_modify_check=lambda *a, **k: (True, None),
        parity_env="0", execution_mode="AUTO",
    )

    assert client.modify_order.call_count == 1
    # New stop (Phase C) is dramatically tighter — 38750 vs 37730
    assert pos["current_stop_price"] == Decimal("38750")
    assert pos["current_phase"] == "C"
    assert pos["modify_seq"] == 2
