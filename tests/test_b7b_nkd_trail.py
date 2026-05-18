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
            Decimal("-500"), Decimal("1750"), Decimal("0"))
        assert phase == _PHASE_A
        assert buf == Decimal("1750")

    def test_pnl_zero_returns_phase_a_at_d_init(self):
        phase, buf = compute_nkd_phase(
            Decimal("0"), Decimal("1750"), Decimal("0"))
        assert phase == _PHASE_A
        assert buf == Decimal("1750")

    def test_phase_b_start_boundary_returns_phase_b_at_d_init(self):
        """At pnl == phase_b_start (no jitter): enter Phase B, buffer=d_init."""
        d_init = Decimal("1750")
        phase, buf = compute_nkd_phase(d_init, d_init, Decimal("0"))
        assert phase == _PHASE_B
        assert buf == d_init  # progress=0 → buffer=d_init

    def test_phase_b_just_before_c_returns_buffer_near_450(self):
        """At pnl just under phase_c_start: buffer → 450."""
        d_init = Decimal("1750")
        pnl = Decimal("3999.99")  # one cent below 4000
        phase, buf = compute_nkd_phase(pnl, d_init, Decimal("0"))
        assert phase == _PHASE_B
        # Use math.isclose on float() for tolerance
        assert float(buf) == pytest.approx(450.00, abs=0.05)

    def test_phase_b_midpoint_at_d_init_1750(self):
        """At midpoint between 1750 and 4000: buffer == (1750 + 450) / 2 = 1100."""
        d_init = Decimal("1750")
        pnl = (d_init + _PHASE_C_START_BASE_DOLLARS) / Decimal("2")  # 2875
        phase, buf = compute_nkd_phase(pnl, d_init, Decimal("0"))
        assert phase == _PHASE_B
        # progress = 0.5 → buffer = d_init - 0.5 * (d_init - 450)
        #                       = 1750 - 0.5 * 1300 = 1100
        assert buf == Decimal("1100")

    def test_phase_b_midpoint_at_d_init_1500(self):
        """d_init==1500 (phase_b_start collapses to 1500): midpoint = 2750.
        At midpoint: buffer = 1500 - 0.5 * (1500 - 450) = 975."""
        d_init = Decimal("1500")
        pnl = Decimal("2750")
        phase, buf = compute_nkd_phase(pnl, d_init, Decimal("0"))
        assert phase == _PHASE_B
        assert buf == Decimal("975")

    def test_phase_c_returns_tight_450(self):
        """In [4000, 4450): Phase C, buffer=450."""
        for pnl in (Decimal("4000"), Decimal("4200"), Decimal("4449")):
            phase, buf = compute_nkd_phase(
                pnl, Decimal("1750"), Decimal("0"))
            assert phase == _PHASE_C, f"pnl={pnl}"
            assert buf == _PHASE_C_BUFFER_DOLLARS, f"pnl={pnl}"

    def test_phase_tp_hit_at_and_above_4450(self):
        """pnl >= 4450 → TP_HIT."""
        for pnl in (Decimal("4450"), Decimal("5000"), Decimal("10000")):
            phase, _ = compute_nkd_phase(
                pnl, Decimal("1750"), Decimal("0"))
            assert phase == _PHASE_TP

    def test_d_init_le_450_collapses_phase_b(self):
        """Degenerate case: d_init=300 (≤450). Buffer stays at 300 in A/B."""
        for pnl in (Decimal("0"), Decimal("500"), Decimal("2000"), Decimal("3500")):
            phase, buf = compute_nkd_phase(
                pnl, Decimal("300"), Decimal("0"))
            if pnl < Decimal("1500"):
                assert phase == _PHASE_A, f"pnl={pnl}"
            else:
                assert phase == _PHASE_B, f"pnl={pnl}"
            assert buf == Decimal("300"), f"pnl={pnl} expected collapsed=300, got {buf}"
        # At pnl==4000 we enter Phase C and the buffer tightens to 450
        # (broker side wins).
        phase, buf = compute_nkd_phase(
            Decimal("4000"), Decimal("300"), Decimal("0"))
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

    def test_isaac_jitter_does_not_touch_broker_prices(self):
        """End-to-end: even with a non-zero J, the broker receives only
        prices computed from (mark, buffer) — J never appears in the
        modify_order call."""
        random.seed(101)
        pos = _make_nkd_position(
            entry_price=Decimal("38000"), snapped_d_init=Decimal("1750"))
        # Run with Isaac jitter — phase math will see J
        mark = _pnl_to_mark_long(Decimal("2000"), 38000)  # mid Phase B
        diag, client, persisted, _ = _scan(
            [pos], quote_price=mark, parity_env="1")
        # Jitter was sampled
        assert pos["jitter_x"] != Decimal("0") or pos["jitter_y"] != 0 \
            or pos["jitter_j"] != Decimal("0")
        # modify_order was called exactly once with a stop_price derived from
        # mark and buffer — never with J added
        client.modify_order.assert_called_once()
        kwargs = client.modify_order.call_args.kwargs
        # stop_price float must be a clean NKD tick-grid value, no jitter
        # leakage (J would shift it by < 4 NKD points = $20)
        stop_price = kwargs["stop_price"]
        # NKD tick is 5.0; must be on grid
        assert (stop_price * 1.0) % 5.0 == pytest.approx(0.0), \
            f"stop_price {stop_price} not on NKD 5-tick grid"


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
# Phase B linear taper — end-to-end
# ---------------------------------------------------------------------------

class TestPhaseBLinearTaperE2E:
    """Phase B buffer interpolation observable through stop placement."""

    def test_buffer_at_boundaries(self):
        """At phase_b_start: buffer=d_init. At phase_c_start-1: buffer≈450."""
        # phase_b_start boundary (no jitter, d_init=1750 -> b_start=1750)
        phase, buf = compute_nkd_phase(
            Decimal("1750"), Decimal("1750"), Decimal("0"))
        assert phase == _PHASE_B
        assert buf == Decimal("1750")

        # Near phase_c_start
        phase, buf = compute_nkd_phase(
            Decimal("3999"), Decimal("1750"), Decimal("0"))
        assert phase == _PHASE_B
        assert float(buf) == pytest.approx(450.578, abs=1.0)

    def test_taper_e2e_observable_stop_move(self):
        """Stop tightens (toward entry) as PnL progresses through Phase B."""
        pos = _make_nkd_position(snapped_d_init=Decimal("1750"))
        client = _make_client(True)

        # Phase B early: pnl=$2000 → buffer ≈ 1750 - (250/2250)*1300
        # = 1750 - 144.4 = ~1605.5; stop=mark-1605.5/5 = mark - 321.1
        mark_early = _pnl_to_mark_long(Decimal("2000"), 38000)  # =38400
        _scan([pos], quote_price=mark_early, client=client)
        stop_early = pos["current_stop_price"]

        # Phase B late: pnl=$3500 → buffer ≈ 1750 - (1750/2250)*1300
        # = 1750 - 1011 = ~739; stop = mark - 739/5 = mark - 147.8
        mark_late = _pnl_to_mark_long(Decimal("3500"), 38000)  # =38700
        _scan([pos], quote_price=mark_late, client=client)
        stop_late = pos["current_stop_price"]

        # Stop should be tighter (closer to entry-side proportion of mark)
        # In absolute terms it must be higher than early (mark went up + buffer shrank)
        assert stop_late > stop_early


# ---------------------------------------------------------------------------
# Phase C / TP_HIT
# ---------------------------------------------------------------------------

class TestPhaseCTightTrail:
    def test_phase_c_buffer_is_450(self):
        for pnl in (Decimal("4000"), Decimal("4200"), Decimal("4449")):
            _, buf = compute_nkd_phase(
                pnl, Decimal("1750"), Decimal("0"))
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
                Decimal("1750"), Decimal("0"))
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
