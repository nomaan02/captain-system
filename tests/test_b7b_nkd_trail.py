"""Unit + integration tests for ON-B7B: NKD trailing-stop ratchet.

Covers the locked phase spec, jitter sampling discipline, ratchet
monotonicity, the Phase A $500 step gate, the TP_HIT no-modify rule,
and the degenerate ``d_init <= 450`` collapse.

Per the captain-spec-audit skill: these are READ-ONLY behavioural tests —
no D34 writes, no Redis writes, no broker calls. All IO is injected.

NKD spec constants:
    point_value = 5.0  tick_size = 5.0  (config/contract_ids.json)
    PnL formula: (mark - entry) * direction * contracts * point_value
    So a $500 PnL move on a 1-contract trade = 100 NKD points = $500 mark move.
"""

from __future__ import annotations

import math
import random
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock

import pytest

from captain_online.blocks import b7b_nkd_trail
from captain_online.blocks.b7b_nkd_trail import (
    _PHASE_A, _PHASE_B, _PHASE_C, _PHASE_TP,
    _PHASE_B_START_BASE_DOLLARS, _PHASE_C_START_BASE_DOLLARS,
    _PHASE_C_BUFFER_DOLLARS, _TP_TARGET_DOLLARS,
    apply_ratchet, compute_nkd_phase, compute_stop_price,
    phase_a_should_modify, sample_isaac_jitter,
    scan_nkd_trails,
)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

NKD_POINT_VALUE = Decimal("5")  # point_value=5 → 1 NKD point = $5 per contract


def _pnl_to_mark_long(pnl_dollars, entry, contracts=1):
    """Inverse of (mark - entry) * dir * contracts * pv for a LONG position."""
    return Decimal(str(entry)) + Decimal(str(pnl_dollars)) / (
        NKD_POINT_VALUE * Decimal(contracts))


def _pnl_to_mark_short(pnl_dollars, entry, contracts=1):
    """Inverse for SHORT."""
    return Decimal(str(entry)) - Decimal(str(pnl_dollars)) / (
        NKD_POINT_VALUE * Decimal(contracts))


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Wipe per-process prev_pnl tracking between cases."""
    b7b_nkd_trail._reset_state_for_tests()
    yield
    b7b_nkd_trail._reset_state_for_tests()


def _make_nkd_position(
    *,
    direction: int = 1,
    entry_price: Decimal = Decimal("38000"),
    contracts: int = 1,
    snapped_d_init: Decimal = Decimal("1750"),
    sl_order_id: int = 999_001,
    tp_order_id: int = 999_002,
    entry_order_id: str = "ENT-999",
    signal_id: str = "SIG-NKDTEST00001",
    account: str = "21855714",
    user_id: str = "primary_user",
    current_stop_price: Optional[Decimal] = None,
    modify_seq: int = 0,
    jitter_j: Optional[Decimal] = None,
    jitter_x: Optional[Decimal] = None,
    jitter_y: Optional[int] = None,
    current_phase: Optional[str] = None,
    current_buffer: Optional[Decimal] = None,
) -> dict:
    """Build a fully-populated NKD trail position dict (post-C6 schema)."""
    return {
        "signal_id": signal_id,
        "user_id": user_id,
        "asset": "NKD",
        "direction": direction,
        "entry_price": entry_price,
        "signal_entry_price": entry_price,
        "actual_entry_price": entry_price,
        "contracts": contracts,
        "tp_level": entry_price + (Decimal("890") * direction),
        "sl_level": entry_price - (
            (snapped_d_init / NKD_POINT_VALUE) * direction),
        "point_value": NKD_POINT_VALUE,
        "risk_amount": snapped_d_init,
        "account": account,
        "session": 3,  # APAC
        "regime_state": "REGIME_NEUTRAL",
        "combined_modifier": 1.0,
        "aim_breakdown": None,
        "tsm_id": "topstep_150k_eval",
        "entry_time": None,
        "bracket": True,
        "entry_order_id": entry_order_id,
        "sl_order_id": sl_order_id,
        "tp_order_id": tp_order_id,
        "is_nkd_trail": True,
        "tp_dollars": Decimal("4450"),
        "snapped_d_init": snapped_d_init,
        "jitter_x": jitter_x,
        "jitter_y": jitter_y,
        "jitter_j": jitter_j,
        "current_phase": current_phase,
        "current_buffer": current_buffer,
        "current_stop_price": current_stop_price,
        "modify_seq": modify_seq,
    }


class _FakeQuoteFeed:
    """Injectable quote_lookup with a settable mark + age."""

    def __init__(self, price: Decimal, age: Optional[float] = 0.0):
        self.price = price
        self.age = age
        self.calls = []

    def __call__(self, asset, contract_id):
        self.calls.append((asset, contract_id))
        return (self.price, self.age)


def _make_client(success: bool = True, error_message: str = ""):
    """Return a MagicMock client whose modify_order returns {success: ...}."""
    client = MagicMock()
    resp = {"success": success}
    if not success and error_message:
        resp["errorMessage"] = error_message
    client.modify_order.return_value = resp
    return client


def _scan(
    positions,
    *,
    quote_price: Decimal,
    quote_age: Optional[float] = 0.0,
    client: Optional[MagicMock] = None,
    parity_env: str = "0",
    execution_mode: str = "AUTO",
    persisted: Optional[list] = None,
    compliance_result: tuple[bool, Optional[str]] = (True, None),
):
    """Run one scan_nkd_trails pass with injected quote + collected D34 rows."""
    feed = _FakeQuoteFeed(quote_price, quote_age)
    if client is None:
        client = _make_client(True)
    if persisted is None:
        persisted = []

    def _collect(row):
        persisted.append(row)

    def _compliance(_acct, _asset, _mode):
        return compliance_result

    diagnostics = scan_nkd_trails(
        open_positions=positions,
        client=client,
        redis_client=None,
        quote_lookup=feed,
        persist_d34=_collect,
        compliance_modify_check=_compliance,
        parity_env=parity_env,
        execution_mode=execution_mode,
    )
    return diagnostics, client, persisted, feed


# ---------------------------------------------------------------------------
# Pure phase math
# ---------------------------------------------------------------------------

class TestComputeNkdPhase:
    """Phase decision tree — locked spec coverage."""

    def test_pnl_negative_returns_phase_a_at_d_init(self):
        phase, buf = compute_nkd_phase(
            Decimal("-500"), Decimal("1750"))
        assert phase == _PHASE_A
        assert buf == Decimal("1750")

    def test_pnl_zero_returns_phase_a_at_d_init(self):
        phase, buf = compute_nkd_phase(
            Decimal("0"), Decimal("1750"))
        assert phase == _PHASE_A
        assert buf == Decimal("1750")

    def test_phase_b_start_boundary_returns_phase_b_at_d_init(self):
        """At pnl == 2000 (Phase B start): enter Phase B, buffer=1000 (flat step)."""
        phase, buf = compute_nkd_phase(
            Decimal("2000"), Decimal("1025"))
        assert phase == _PHASE_B
        assert buf == Decimal("1000")

    def test_phase_b_just_before_c_returns_buffer_near_450(self):
        """At pnl just under phase_c_start (2999): still Phase B, buffer=1000 flat."""
        phase, buf = compute_nkd_phase(
            Decimal("2999"), Decimal("1025"))
        assert phase == _PHASE_B
        assert buf == Decimal("1000")

    def test_phase_b_midpoint_at_d_init_1750(self):
        """At pnl=2500 (mid-Phase B): buffer=1000 flat step (not a midpoint average)."""
        phase, buf = compute_nkd_phase(
            Decimal("2500"), Decimal("1750"))
        assert phase == _PHASE_B
        assert buf == Decimal("1000")

    def test_phase_b_midpoint_at_d_init_1500(self):
        """d_init=1500: Phase B uses flat $1000 buffer (not a linear taper)."""
        phase, buf = compute_nkd_phase(
            Decimal("2500"), Decimal("1500"))
        assert phase == _PHASE_B
        assert buf == Decimal("1000")

    def test_phase_c_returns_tight_450(self):
        """In [3000, 4450): Phase C, buffer=450."""
        for pnl in (Decimal("3001"), Decimal("4200"), Decimal("4449")):
            phase, buf = compute_nkd_phase(
                pnl, Decimal("1750"))
            assert phase == _PHASE_C, f"pnl={pnl}"
            assert buf == _PHASE_C_BUFFER_DOLLARS, f"pnl={pnl}"

    def test_phase_tp_hit_at_and_above_4450(self):
        """pnl >= 4450 → TP_HIT."""
        for pnl in (Decimal("4450"), Decimal("5000"), Decimal("10000")):
            phase, _ = compute_nkd_phase(
                pnl, Decimal("1750"))
            assert phase == _PHASE_TP

    def test_phase_b_constant_1000(self):
        """Phase B buffer is flat $1000 regardless of pnl within [2000, 3000)."""
        for pnl in (Decimal("2000"), Decimal("2500"), Decimal("2999")):
            phase, buf = compute_nkd_phase(pnl, Decimal("1025"))
            assert phase == _PHASE_B, f"pnl={pnl} should be Phase B"
            assert buf == Decimal("1000"), f"pnl={pnl} buffer should be flat 1000"

    def test_phase_c_starts_at_3000(self):
        """pnl=3000 is the first tick of Phase C; buffer=450."""
        phase, buf = compute_nkd_phase(Decimal("3000"), Decimal("1025"))
        assert phase == _PHASE_C
        assert buf == Decimal("450")

    def test_phase_b_degenerate_when_d_init_lt_1000(self):
        """d_init=800 (< 1000): Phase B buffer floored at d_init=800, not 1000."""
        phase, buf = compute_nkd_phase(Decimal("2500"), Decimal("800"))
        assert phase == _PHASE_B
        assert buf == Decimal("800")  # min(1000, 800) = 800

    def test_d_init_le_450_collapses_phase_b(self):
        """Degenerate: d_init=300 (< 1000). Phase B buffer floored at d_init (never wider)."""
        # Phase A: pnl < 2000
        for pnl in (Decimal("0"), Decimal("500"), Decimal("1999")):
            phase, buf = compute_nkd_phase(pnl, Decimal("300"))
            assert phase == _PHASE_A, f"pnl={pnl}"
            assert buf == Decimal("300"), f"pnl={pnl}"
        # Phase B: 2000 <= pnl < 3000, buffer = min(1000, 300) = 300
        for pnl in (Decimal("2000"), Decimal("2500"), Decimal("2999")):
            phase, buf = compute_nkd_phase(pnl, Decimal("300"))
            assert phase == _PHASE_B, f"pnl={pnl}"
            assert buf == Decimal("300"), f"pnl={pnl} (floor at d_init=300)"
        # Phase C: pnl >= 3000, buffer=450 (spec is 450 in Phase C regardless of d_init)
        phase, buf = compute_nkd_phase(Decimal("3000"), Decimal("300"))
        assert phase == _PHASE_C
        assert buf == Decimal("450")


# ---------------------------------------------------------------------------
# Jitter sampling discipline
# ---------------------------------------------------------------------------

class TestSampleIsaacJitter:
    """Jitter is OFF on Nomaan tower, ACTIVE on Isaac tower."""

    @pytest.mark.parametrize("env", [None, "", "0", "false", "00"])
    def test_nomaan_tower_returns_zero_for_any_non_one_value(self, env):
        x, y, j = sample_isaac_jitter(env)
        assert x == Decimal("0")
        assert y == 0
        assert j == Decimal("0")

    def test_isaac_tower_samples_within_spec_bounds(self):
        """parity='1' → X ∈ [0.01, 1.00], Y ∈ {-1,1}, |J| ∈ [0.2, 20.0]."""
        random.seed(20260518)  # deterministic for the test
        samples = [sample_isaac_jitter("1") for _ in range(200)]
        for x, y, j in samples:
            assert Decimal("0.01") <= x <= Decimal("1.00")
            assert y in (-1, 1)
            # |J| = 20 * X; lower bound is 20*0.01 = 0.20
            assert Decimal("0.2") <= abs(j) <= Decimal("20.0")
            # Sign of J matches sign of Y
            if y == 1:
                assert j > 0
            else:
                assert j < 0

    def test_isaac_jitter_shifts_broker_prices(self):
        """End-to-end (C16+): Isaac tower's broker stop is shifted by J.
        The stop for Isaac (J≠0) differs from Nomaan (J=0) at the same mark."""
        random.seed(101)
        entry = Decimal("38000")
        d_init = Decimal("1025")
        mark = _pnl_to_mark_long(Decimal("2000"), 38000)  # Phase B

        # Nomaan tower (J=0): pre-populated jitter_j=0
        pos_n = _make_nkd_position(
            entry_price=entry, snapped_d_init=d_init,
            jitter_x=Decimal("0"), jitter_y=0, jitter_j=Decimal("0"))
        diag_n, client_n, _, _ = _scan([pos_n], quote_price=mark, parity_env="0")

        # Isaac tower: pre-populate a known J to make the test deterministic
        j_val = Decimal("15")  # |J|=15 within spec range
        pos_i = _make_nkd_position(
            entry_price=entry, snapped_d_init=d_init,
            jitter_x=Decimal("0.75"), jitter_y=1, jitter_j=j_val)
        diag_i, client_i, _, _ = _scan([pos_i], quote_price=mark, parity_env="1")

        # Both towers must have made a modify_order call
        client_n.modify_order.assert_called_once()
        client_i.modify_order.assert_called_once()

        stop_n = client_n.modify_order.call_args.kwargs["stop_price"]
        stop_i = client_i.modify_order.call_args.kwargs["stop_price"]

        # Both stops must be on NKD 5-tick grid
        assert (stop_n * 1.0) % 5.0 == pytest.approx(0.0), \
            f"Nomaan stop {stop_n} not on NKD 5-tick grid"
        assert (stop_i * 1.0) % 5.0 == pytest.approx(0.0), \
            f"Isaac stop {stop_i} not on NKD 5-tick grid"

        # Isaac's stop must differ from Nomaan's (effective_buffer = buffer + J)
        assert stop_i != stop_n, (
            f"Isaac (J={j_val}) and Nomaan (J=0) produced identical broker stop "
            f"({stop_n}). J should shift the broker SL buffer by ${j_val}."
        )

    def test_jitter_widens_broker_sl_buffer_by_j(self):
        """effective_buffer = buffer + J. For J=+10 and Phase B buffer=1000,
        Isaac's broker stop is placed 1010 dollars behind the mark."""
        entry = Decimal("38000")
        d_init = Decimal("1025")
        mark = _pnl_to_mark_long(Decimal("2000"), 38000)  # Phase B, buffer=1000
        j_val = Decimal("10")  # positive J: stop is further away

        pos = _make_nkd_position(
            entry_price=entry, snapped_d_init=d_init,
            jitter_x=Decimal("0.5"), jitter_y=1, jitter_j=j_val)
        _, client, _, _ = _scan([pos], quote_price=mark, parity_env="1")

        client.modify_order.assert_called_once()
        stop_price = client.modify_order.call_args.kwargs["stop_price"]

        # Phase B buffer = min(1000, 1025) = 1000
        # effective_buffer = 1000 + 10 = 1010
        # stop = mark - 1010/5 = 38400 - 202 = 38198 → snap outward (floor for LONG)
        # 38198 / 5 = 7639.6 → floor → 7639 * 5 = 38195
        expected_stop = 38195.0  # floor(38198/5)*5
        assert stop_price == pytest.approx(expected_stop, abs=5.0), (
            f"Isaac stop {stop_price} should be ~{expected_stop} "
            f"(mark={float(mark)}, buffer=1000, J={j_val})"
        )


# ---------------------------------------------------------------------------
# Ratchet monotonicity
# ---------------------------------------------------------------------------

class TestApplyRatchet:
    """Stop never weakens — LONG max, SHORT min."""

    def test_long_takes_higher_stop(self):
        out = apply_ratchet(Decimal("37800"), Decimal("37900"), 1)
        assert out == Decimal("37900")

    def test_long_refuses_lower_stop(self):
        out = apply_ratchet(Decimal("37900"), Decimal("37800"), 1)
        assert out == Decimal("37900")

    def test_short_takes_lower_stop(self):
        out = apply_ratchet(Decimal("38200"), Decimal("38100"), -1)
        assert out == Decimal("38100")

    def test_short_refuses_higher_stop(self):
        out = apply_ratchet(Decimal("38100"), Decimal("38200"), -1)
        assert out == Decimal("38100")

    def test_none_current_returns_candidate(self):
        out = apply_ratchet(None, Decimal("37800"), 1)
        assert out == Decimal("37800")

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            apply_ratchet(Decimal("0"), Decimal("0"), 0)


class TestRatchetNeverRetreats:
    """End-to-end via scan_nkd_trails: oscillating mark → monotone stop."""

    def test_ratchet_never_retreats_long(self):
        """LONG: mark goes up, stop goes up. Mark dips back: stop holds."""
        pos = _make_nkd_position()
        client = _make_client(True)

        # Step 1: pnl=$2000 → mid Phase B, mark goes up to 38400
        mark1 = _pnl_to_mark_long(Decimal("2000"), 38000)
        _scan([pos], quote_price=mark1, client=client)
        stop_after_1 = pos["current_stop_price"]
        assert stop_after_1 is not None

        # Step 2: pnl=$3000 → further into Phase B, stop should tighten upward
        mark2 = _pnl_to_mark_long(Decimal("3000"), 38000)
        _scan([pos], quote_price=mark2, client=client)
        stop_after_2 = pos["current_stop_price"]
        assert stop_after_2 >= stop_after_1, \
            f"Stop went down: {stop_after_1} -> {stop_after_2}"

        # Step 3: mark dips to $1500 PnL → buffer wider but ratchet refuses
        mark3 = _pnl_to_mark_long(Decimal("1500"), 38000)
        _scan([pos], quote_price=mark3, client=client)
        stop_after_3 = pos["current_stop_price"]
        assert stop_after_3 == stop_after_2, \
            f"Ratchet weakened: {stop_after_2} -> {stop_after_3}"

    def test_ratchet_never_retreats_short(self):
        """SHORT: mark goes down, stop goes down. Mark recovers: stop holds."""
        pos = _make_nkd_position(
            direction=-1, entry_price=Decimal("38000"),
            snapped_d_init=Decimal("1750"))
        client = _make_client(True)

        # Step 1: $2000 favourable PnL → mark = 38000 - 400 = 37600
        mark1 = _pnl_to_mark_short(Decimal("2000"), 38000)
        _scan([pos], quote_price=mark1, client=client)
        stop_after_1 = pos["current_stop_price"]
        assert stop_after_1 is not None

        # Step 2: $3000 → mark = 37400, stop should move DOWN
        mark2 = _pnl_to_mark_short(Decimal("3000"), 38000)
        _scan([pos], quote_price=mark2, client=client)
        stop_after_2 = pos["current_stop_price"]
        assert stop_after_2 <= stop_after_1, \
            f"SHORT stop moved up (weakened): {stop_after_1} -> {stop_after_2}"

        # Step 3: mark recovers to $1500 PnL → ratchet refuses
        mark3 = _pnl_to_mark_short(Decimal("1500"), 38000)
        _scan([pos], quote_price=mark3, client=client)
        stop_after_3 = pos["current_stop_price"]
        assert stop_after_3 == stop_after_2, \
            f"SHORT ratchet weakened on recovery: {stop_after_2} -> {stop_after_3}"


# ---------------------------------------------------------------------------
# Phase A $500 step gate
# ---------------------------------------------------------------------------

class TestPhaseAStepGate:
    """Phase A: only modify on $500 PnL crossings, not on every tick."""

    def test_phase_a_should_modify_first_poll_no_prev(self):
        assert phase_a_should_modify(Decimal("0"), None) is True

    def test_phase_a_should_not_modify_below_500_step(self):
        # 0 → 499: same bucket
        assert phase_a_should_modify(Decimal("499"), Decimal("0")) is False

    def test_phase_a_should_modify_at_500_boundary(self):
        # 499 → 500: crossed into next bucket
        assert phase_a_should_modify(Decimal("500"), Decimal("499")) is True

    def test_phase_a_should_modify_negative_to_positive(self):
        assert phase_a_should_modify(Decimal("100"), Decimal("-100")) is True

    def test_phase_a_step_ratchet_e2e(self):
        """Phase A position polled at small PnL increments — broker modify
        only fires after crossing a $500 boundary."""
        pos = _make_nkd_position(
            snapped_d_init=Decimal("1750"))  # d_init=1750
        client = _make_client(True)

        # Poll 1: pnl=$200 → Phase A, FIRST poll → modify fires
        mark1 = _pnl_to_mark_long(Decimal("200"), 38000)
        _scan([pos], quote_price=mark1, client=client)
        calls_after_1 = client.modify_order.call_count
        assert calls_after_1 == 1, "First poll should always modify"

        # Poll 2: pnl=$300 → same $500 bucket → NO modify
        mark2 = _pnl_to_mark_long(Decimal("300"), 38000)
        _scan([pos], quote_price=mark2, client=client)
        assert client.modify_order.call_count == calls_after_1, \
            "Same bucket should not re-modify"

        # Poll 3: pnl=$550 → crossed into [500, 1000) bucket → modify
        mark3 = _pnl_to_mark_long(Decimal("550"), 38000)
        _scan([pos], quote_price=mark3, client=client)
        assert client.modify_order.call_count == calls_after_1 + 1, \
            "$500 crossing should modify"


# ---------------------------------------------------------------------------
# Phase B flat step — end-to-end
# ---------------------------------------------------------------------------

class TestPhaseBStep:
    """Phase B flat-$1000 buffer observable through stop placement."""

    def test_buffer_at_boundaries(self):
        """At pnl=2000 (Phase B start) and pnl=2999 (Phase B end): buffer=1000."""
        # Phase B start boundary
        phase, buf = compute_nkd_phase(
            Decimal("2000"), Decimal("1750"))
        assert phase == _PHASE_B
        assert buf == Decimal("1000")

        # Near phase_c_start (2999 < 3000)
        phase, buf = compute_nkd_phase(
            Decimal("2999"), Decimal("1750"))
        assert phase == _PHASE_B
        assert buf == Decimal("1000")

    def test_step_e2e_observable_stop_move(self):
        """Buffer is flat $1000 throughout Phase B; stop tracks mark at $1000 distance."""
        pos = _make_nkd_position(snapped_d_init=Decimal("1750"))
        client = _make_client(True)

        # Phase B at pnl=$2000: buffer=1000, stop=mark-1000/5=mark-200 NKD pts
        mark_early = _pnl_to_mark_long(Decimal("2000"), 38000)  # =38400
        _scan([pos], quote_price=mark_early, client=client)
        stop_early = pos["current_stop_price"]

        # Phase B at pnl=$2500: buffer still 1000, stop=mark-200 NKD pts
        mark_late = _pnl_to_mark_long(Decimal("2500"), 38000)   # =38500
        _scan([pos], quote_price=mark_late, client=client)
        stop_late = pos["current_stop_price"]

        # Ratchet advances stop with mark (higher mark → higher stop for LONG)
        assert stop_late > stop_early


# ---------------------------------------------------------------------------
# Phase C / TP_HIT
# ---------------------------------------------------------------------------

class TestPhaseCTightTrail:
    def test_phase_c_buffer_is_450(self):
        for pnl in (Decimal("4000"), Decimal("4200"), Decimal("4449")):
            _, buf = compute_nkd_phase(
                pnl, Decimal("1750"))
            assert buf == Decimal("450")

    def test_phase_c_stop_placement_e2e(self):
        """In Phase C, stop is mark - 90 NKD points (450/5) for LONG."""
        pos = _make_nkd_position(
            current_stop_price=Decimal("38200"),  # pre-existing wider stop
            modify_seq=5,
        )
        client = _make_client(True)

        # pnl=$4200 → mark = 38840, Phase C buffer=450, distance=90 pts
        mark = _pnl_to_mark_long(Decimal("4200"), 38000)
        _scan([pos], quote_price=mark, client=client)
        # Stop should be mark - 90 = 38750
        assert pos["current_stop_price"] == Decimal("38750")
        assert pos["current_phase"] == _PHASE_C


class TestTpHitNoModify:
    def test_phase_tp_hit_emits_no_broker_call(self):
        pos = _make_nkd_position(current_stop_price=Decimal("38800"))
        client = _make_client(True)
        # pnl >= $4450 → TP_HIT
        mark = _pnl_to_mark_long(Decimal("4500"), 38000)  # =38900
        diag, client, persisted, _ = _scan(
            [pos], quote_price=mark, client=client)

        client.modify_order.assert_not_called()
        # Diagnostics record the TP_HIT phase
        assert diag[0]["phase"] == _PHASE_TP
        assert diag[0]["modify_status"] == "TP_HIT_NO_MODIFY"
        # D34 snapshot row still written
        assert len(persisted) == 1
        assert persisted[0]["phase"] == _PHASE_TP


# ---------------------------------------------------------------------------
# Modify skip on unchanged stop
# ---------------------------------------------------------------------------

class TestModifySkippedWhenStopUnchanged:
    def test_no_modify_when_price_didnt_move(self):
        """Two consecutive polls with the same PnL → only one modify."""
        pos = _make_nkd_position(snapped_d_init=Decimal("1750"))
        client = _make_client(True)

        # Poll 1: Phase B mid → modify fires
        mark = _pnl_to_mark_long(Decimal("2875"), 38000)  # 38000 + 575 = 38575
        _scan([pos], quote_price=mark, client=client)
        first_count = client.modify_order.call_count
        assert first_count == 1

        # Poll 2: same mark → ratchet wins (stop unchanged) → NO modify
        _scan([pos], quote_price=mark, client=client)
        assert client.modify_order.call_count == first_count


# ---------------------------------------------------------------------------
# TP never exceeded across random trajectories
# ---------------------------------------------------------------------------

class TestTpNeverExceeded:
    def test_tp_phase_caps_at_4450(self):
        """1000 random PnL values across full range — phase is TP_HIT at
        and above 4450, never above is treated as still trailing."""
        rng = random.Random(0xDEAD_BEEF)
        for _ in range(1000):
            pnl_dollars = rng.uniform(-2000, 10000)
            phase, _ = compute_nkd_phase(
                Decimal(str(round(pnl_dollars, 2))),
                Decimal("1750"))
            if pnl_dollars >= 4450:
                assert phase == _PHASE_TP, \
                    f"pnl={pnl_dollars} expected TP_HIT, got {phase}"
            else:
                assert phase != _PHASE_TP, \
                    f"pnl={pnl_dollars} expected non-TP, got {phase}"

    def test_simulated_trajectory_never_modifies_past_tp(self):
        """End-to-end: a trajectory that crosses 4450 stops modifying."""
        pos = _make_nkd_position(snapped_d_init=Decimal("1750"))
        client = _make_client(True)

        # Walk PnL from 0 → 5000 in $250 steps. After 4450, no more modifies.
        modifies_before_tp = 0
        modifies_in_tp = 0
        pnl = Decimal("0")
        while pnl <= Decimal("5000"):
            mark = _pnl_to_mark_long(pnl, 38000)
            client.modify_order.reset_mock()
            _scan([pos], quote_price=mark, client=client)
            n = client.modify_order.call_count
            if pnl >= Decimal("4450"):
                modifies_in_tp += n
            else:
                modifies_before_tp += n
            pnl += Decimal("250")

        assert modifies_in_tp == 0, \
            f"{modifies_in_tp} broker calls in TP_HIT zone (must be 0)"
        # And of course we DID modify during the climb
        assert modifies_before_tp > 0


# ---------------------------------------------------------------------------
# Order-ID guard: BRACKET sentinel skips modify cleanly
# ---------------------------------------------------------------------------

class TestSlOrderIdSentinel:
    def test_bracket_sentinel_skips_modify(self):
        """Until C5 captures the real SL ID, sl_order_id='BRACKET'. Trail
        must skip cleanly with a diagnostic — never crash, never call broker."""
        pos = _make_nkd_position(sl_order_id="BRACKET")
        client = _make_client(True)
        mark = _pnl_to_mark_long(Decimal("2000"), 38000)
        diag, client, persisted, _ = _scan(
            [pos], quote_price=mark, client=client)
        client.modify_order.assert_not_called()
        assert diag[0]["skip_reason"] == "sl_order_id_unresolved"
        assert persisted == []  # no D34 row when we couldn't even try


# ---------------------------------------------------------------------------
# Compute stop price helper
# ---------------------------------------------------------------------------

class TestComputeStopPrice:
    def test_long_subtracts_buffer_per_point(self):
        # buffer=$450, pv=5, contracts=1 → 90 pts → stop = mark - 90
        out = compute_stop_price(
            Decimal("38500"), Decimal("450"), 1, NKD_POINT_VALUE, 1)
        assert out == Decimal("38410")

    def test_short_adds_buffer_per_point(self):
        out = compute_stop_price(
            Decimal("38500"), Decimal("450"), -1, NKD_POINT_VALUE, 1)
        assert out == Decimal("38590")

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            compute_stop_price(
                Decimal("38500"), Decimal("450"), 0, NKD_POINT_VALUE, 1)

    def test_non_positive_pv_raises(self):
        with pytest.raises(ValueError):
            compute_stop_price(
                Decimal("38500"), Decimal("450"), 1, Decimal("0"), 1)
