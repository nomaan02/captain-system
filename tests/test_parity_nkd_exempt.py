"""Q1 NKD parity exemption tests.

The audit (docs2/quick-fixes/NKD_Pivot/day_3/PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md
§2 Q1) requires that NKD signals NEVER be parity-skipped — both towers always
take NKD, jitter J differentiates per-trade.

These tests target the pure helper ``is_nkd_exempt_batch`` in
``captain_command.blocks.parity`` so they run without pulling in the
orchestrator's heavy import chain (pysignalr is unavailable on towers).

The wrapper ``_check_parity_skip`` in orchestrator.py calls the helper as its
first decision; tests 4/5 exercise the integration by ensuring the helper
returns False for non-NKD batches (so the existing hash-based parity decision
still runs) and True for any mixed batch containing one NKD signal.
"""
from __future__ import annotations

from captain_command.blocks.parity import (
    build_parity_key,
    compute_parity_decision,
    is_nkd_exempt_batch,
)


# ---------------------------------------------------------------------------
# Test 1 — Nomaan tower (parity=0), NKD-only batch: must take.
# ---------------------------------------------------------------------------

def test_nkd_exempt_parity_0_pure_nkd_batch_takes():
    """Helper returns True for NKD-only batch — both towers exempt."""
    signals = [{"asset": "NKD", "is_nkd_trail": True, "size": 1}]
    assert is_nkd_exempt_batch(signals) is True


# ---------------------------------------------------------------------------
# Test 2 — Isaac tower (parity=1), NKD-only batch: must take.
# ---------------------------------------------------------------------------

def test_nkd_exempt_parity_1_pure_nkd_batch_takes():
    """Helper return value is parity-agnostic — both towers exempt."""
    signals = [{"asset": "NKD", "is_nkd_trail": True, "size": 1}]
    # The helper is independent of my_parity; the orchestrator wrapper
    # consumes the bool and short-circuits before invoking
    # compute_parity_decision. Both towers see the same exempt=True.
    assert is_nkd_exempt_batch(signals) is True


# ---------------------------------------------------------------------------
# Test 3 — Mixed batch (NKD + non-NKD): exempt fires, whole batch taken.
# ---------------------------------------------------------------------------

def test_nkd_mixed_batch_exempt_fires():
    """One NKD signal in a mixed batch triggers exemption for the whole batch.

    The audit explicitly accepts this — when a batch contains both NKD and
    non-NKD signals, both towers take the entire batch (rather than splitting).
    """
    signals = [
        {"asset": "ES", "size": 2},
        {"asset": "NKD", "is_nkd_trail": True, "size": 1},
        {"asset": "MGC", "size": 1},
    ]
    assert is_nkd_exempt_batch(signals) is True


# ---------------------------------------------------------------------------
# Test 4 — Pure non-NKD batch: existing parity behaviour preserved.
# ---------------------------------------------------------------------------

def test_pure_non_nkd_batch_not_exempt():
    """No NKD anywhere → helper returns False, normal hash-based parity runs."""
    signals = [
        {"asset": "ES", "size": 2},
        {"asset": "NQ", "size": 1},
    ]
    assert is_nkd_exempt_batch(signals) is False

    # Confirm the existing parity machinery is still reachable for this case.
    key = build_parity_key("2026-05-20", 1, "primary_user",
                           [s["asset"] for s in signals])
    _, skip_a = compute_parity_decision(0, key)
    _, skip_b = compute_parity_decision(1, key)
    assert skip_a != skip_b, (
        "Non-NKD batch must still produce opposite decisions across towers — "
        "exactly one takes, exactly one skips."
    )


# ---------------------------------------------------------------------------
# Test 5 — is_nkd_trail-only signal (no asset=NKD): still exempt.
# ---------------------------------------------------------------------------

def test_is_nkd_trail_flag_alone_triggers_exemption():
    """A signal with ``is_nkd_trail=True`` but no ``asset`` field still exempts.

    Defence-in-depth: the audit specifies BOTH conditions (asset == 'NKD' OR
    is_nkd_trail flag) so an off-template signal can't accidentally fall into
    the parity gate.
    """
    signals = [{"is_nkd_trail": True, "size": 1}]  # no 'asset' key
    assert is_nkd_exempt_batch(signals) is True


# ---------------------------------------------------------------------------
# Bonus — empty batch is NOT exempt (no signals = nothing to exempt).
# ---------------------------------------------------------------------------

def test_empty_batch_not_exempt():
    """Empty signal list returns False so the orchestrator's existing
    ``if not assets: return False`` continues to handle the empty case."""
    assert is_nkd_exempt_batch([]) is False
    assert is_nkd_exempt_batch(None) is False  # type: ignore[arg-type]
