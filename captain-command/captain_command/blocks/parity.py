"""Multi-instance parity helpers — pure, dependency-light.

These helpers exist as a separate module so they can be unit-tested without
pulling in the heavy ``captain_command.api`` / FastAPI / Redis import chain
of ``orchestrator.py``.

The parity decision is content-addressed: both towers compute the same
``signal_parity`` for the same ``(date, session_id, user_id, sorted-asset-set)``
batch, so they always agree on which one of them takes a given trade and
drift between instances is mathematically impossible.

See ``orchestrator._check_parity_skip`` for the wrapper that adds a Redis-side
self-consistency check (duplicate-batch detector for PEL replay).
"""
from __future__ import annotations

import hashlib
from typing import Iterable


def build_parity_key(today: str, session_id, user_id: str,
                     assets: Iterable[str]) -> str:
    """Build the deterministic content key for a signal batch.

    Parameters
    ----------
    today : str
        Date in ``YYYY-MM-DD`` form, evaluated in ``America/New_York``.
    session_id : Any
        Session identifier from the B6 batch payload (typically int).
    user_id : str
        User identifier from the batch payload.
    assets : iterable of str
        The asset symbols carried in the batch — order does NOT matter,
        the helper sorts them so payloads assembled in slightly different
        orders on different towers still produce the same key.

    Returns
    -------
    str
        ``f"{today}|{session_id}|{user_id}|{a1,a2,...}"`` with assets sorted.
    """
    sorted_assets = sorted(assets)
    return f"{today}|{session_id}|{user_id}|{','.join(sorted_assets)}"


def is_nkd_exempt_batch(signals: list[dict]) -> bool:
    """Return True if any signal in the batch is NKD (asset or is_nkd_trail flag).

    Q1 NKD parity exemption (audit 2026-05-20): NKD signals must NEVER be
    parity-skipped — both towers always take NKD, jitter J differentiates
    per-trade. Pure helper so ``orchestrator._check_parity_skip`` can short
    -circuit before hashing, and so unit tests can exercise the decision
    without importing the heavy orchestrator module (which transitively
    pulls in pysignalr).
    """
    if not signals:
        return False
    return any(
        s.get("asset") == "NKD" or s.get("is_nkd_trail")
        for s in signals
    )


def compute_parity_decision(my_parity: int, key: str) -> tuple[int, bool]:
    """Compute ``(signal_parity, skip)`` from a key and this tower's parity.

    Parameters
    ----------
    my_parity : int
        Either ``0`` or ``1`` — this tower's ``INSTANCE_PARITY`` env var.
    key : str
        Content key produced by :func:`build_parity_key`.

    Returns
    -------
    tuple of (int, bool)
        ``signal_parity`` is the batch's hashed parity (0 or 1);
        ``skip`` is ``True`` when this tower should NOT take the batch
        (i.e. when ``signal_parity != my_parity``).
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    signal_parity = digest[0] & 1
    return signal_parity, signal_parity != my_parity
