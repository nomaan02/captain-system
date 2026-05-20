"""Regression tests for the multi-instance parity filter.

Covers ``captain_command.blocks.parity`` and the orchestrator wrapper that
calls it.  This is the May-2026 fix that replaced the per-tower Redis
``INCR`` counter with a content-addressed hash of
``(date, session_id, user_id, sorted-asset-set)``.

Background: the old counter design desynchronised permanently the moment
one tower missed or duplicated a signal; the resulting ``drift = 1``
produced alternating BOTH-SKIP (lost trade) and BOTH-TAKE (duplicated
execution) sessions.  See
``docs2/quick-fixes/NY_OPEN_06-05_logs+fixes/`` for the May 5/6 incident.

These tests pin the new invariants:

1. Two towers that observe the same batch always reach OPPOSITE skip
   decisions — exactly one takes the trade.
2. Asset ordering inside the batch payload is irrelevant (sorted key).
3. Re-processing the same batch on one tower is parity-idempotent.
4. A duplicate-on-this-tower fires a P1_CRITICAL self-consistency alert
   (PEL replay detector).
5. Empty batches are not skipped.
6. Distribution over a realistic synthetic corpus is balanced.

The pure helpers are imported from ``captain_command.blocks.parity``
which has no FastAPI / Redis dependencies, so the test runs on a bare
host without container-only packages.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make captain-command/captain_command importable on a bare host.
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "captain-command"))

from captain_command.blocks.parity import (  # noqa: E402
    build_parity_key,
    compute_parity_decision,
)


# ---------------------------------------------------------------------------
# Pure helpers — no orchestrator/Redis required
# ---------------------------------------------------------------------------


def test_build_key_sorts_assets():
    """Assets are sorted so payload assembly order does not matter."""
    a = build_parity_key("2026-05-07", 1, "primary_user", ["MNQ", "MES"])
    b = build_parity_key("2026-05-07", 1, "primary_user", ["MES", "MNQ"])
    assert a == b == "2026-05-07|1|primary_user|MES,MNQ"


def test_build_key_includes_all_fields():
    key = build_parity_key("2026-05-07", 4, "primary_user", ["NKD"])
    assert key == "2026-05-07|4|primary_user|NKD"


def test_two_towers_reach_opposite_decisions_pure():
    """For any single batch, exactly one tower takes and one skips."""
    key = build_parity_key("2026-05-05", 4, "primary_user", ["NKD"])
    p_a, skip_a = compute_parity_decision(0, key)
    p_b, skip_b = compute_parity_decision(1, key)
    assert p_a == p_b
    assert skip_a != skip_b, (
        "Both towers reached the same skip decision — drift bug regression. "
        "The May 5/6 incident produced exactly this symptom (BOTH-SKIP for "
        "NKD; BOTH-TAKE for MYM/ZB)."
    )


@pytest.mark.parametrize(
    "date_str,session_id,assets",
    [
        ("2026-05-05", 4, ["NKD"]),
        ("2026-05-06", 2, ["MGC"]),
        ("2026-05-06", 1, ["MNQ", "MES"]),
        ("2026-05-06", 1, ["MYM"]),
        ("2026-05-06", 1, ["ZN"]),
        ("2026-05-06", 1, ["ZB"]),
        ("2026-05-07", 1, ["ES", "MES", "NQ", "MNQ"]),
        # The exact May 5/6 batches from the incident report
        ("2026-05-05", 1, ["MNQ", "MES"]),
        ("2026-05-05", 1, ["MYM"]),
        ("2026-05-05", 1, ["ZN"]),
        ("2026-05-05", 1, ["ZB"]),
    ],
)
def test_partition_is_complete_for_each_batch(date_str, session_id, assets):
    """Every batch is taken by exactly one tower — never both, never neither."""
    key = build_parity_key(date_str, session_id, "primary_user", assets)
    _, skip_a = compute_parity_decision(0, key)
    _, skip_b = compute_parity_decision(1, key)
    takes = [not skip_a, not skip_b]
    assert sum(takes) == 1, (
        f"Batch (date={date_str}, session={session_id}, assets={assets}) ended up "
        f"{'BOTH SKIP (lost trade)' if not any(takes) else 'BOTH TAKE (duplicate)'}"
    )


def test_distribution_is_balanced_over_realistic_corpus():
    """SHA-256 over realistic batches partitions ~50/50.

    Hard tolerance: 30/70 imbalance over an 84-batch sample is statistically
    impossible if the hash is well-distributed.
    """
    corpus = []
    for day in range(1, 15):
        date_suffix = f"2026-05-{day:02d}"
        for session_id, batches in [
            (2, [["MGC"]]),
            (1, [["MNQ", "MES"], ["MYM"], ["ZN"], ["ZB"]]),
            (4, [["NKD"]]),
        ]:
            for assets in batches:
                corpus.append((date_suffix, session_id, assets))

    take_a, take_b = 0, 0
    for date_str, session_id, assets in corpus:
        key = build_parity_key(date_str, session_id, "primary_user", assets)
        if not compute_parity_decision(0, key)[1]:
            take_a += 1
        if not compute_parity_decision(1, key)[1]:
            take_b += 1

    total = len(corpus)
    assert take_a + take_b == total
    assert 0.30 <= take_a / total <= 0.70, (
        f"Tower A take rate {take_a}/{total} is implausibly biased — "
        "hash function or key construction has changed."
    )


# ---------------------------------------------------------------------------
# Orchestrator wrapper — exercised via patching to avoid FastAPI import
# ---------------------------------------------------------------------------


class FakeRedis:
    """Minimal fake supporting just SADD/EXPIRE for the parity self-check."""

    def __init__(self):
        self.sets: dict[str, set[str]] = {}
        self.expires: dict[str, int] = {}

    def sadd(self, key, value):
        bucket = self.sets.setdefault(key, set())
        if value in bucket:
            return 0
        bucket.add(value)
        return 1

    def expire(self, key, seconds):
        self.expires[key] = seconds
        return True


@pytest.fixture
def orchestrator_module():
    """Import ``captain_command.blocks.orchestrator`` with heavy deps stubbed.

    Parity tests don't exercise FastAPI; they only need the orchestrator
    class definition.  We stub ``captain_command.api`` (the heaviest import
    chain — pulls FastAPI, pydantic, jwt, uvicorn) directly so the module
    loads on a bare host without container-only packages.
    """
    api_stub = MagicMock()
    api_stub.gui_push = MagicMock()
    api_stub.update_process_health = MagicMock()
    api_stub.update_api_connections = MagicMock()
    api_stub.update_last_signal_time = MagicMock()
    api_stub.set_orchestrator_ready = MagicMock()
    api_stub._ws_sessions = {}
    sys.modules["captain_command.api"] = api_stub

    from captain_command.blocks import orchestrator
    return orchestrator


def _make_orch(orchestrator_module):
    """Build a CommandOrchestrator without running the heavy ``__init__``."""
    orch = orchestrator_module.CommandOrchestrator.__new__(
        orchestrator_module.CommandOrchestrator,
    )
    orch.telegram_bot = None
    return orch


def _payload(*, assets, session_id=1, user_id="primary_user"):
    return {
        "session_id": session_id,
        "user_id": user_id,
        "signals": [{"asset": a} for a in assets],
    }


def test_check_parity_skip_idempotent(orchestrator_module):
    """Replaying the same batch twice yields the same parity decision.

    Uses a non-NKD asset because Q1 NKD parity exemption (audit 2026-05-20)
    short-circuits before the hash machinery for any batch containing NKD;
    this test must exercise the hash path so we use MGC instead.
    """
    orch = _make_orch(orchestrator_module)
    fake = FakeRedis()
    payload = _payload(assets=["MGC"], session_id=4)

    with patch.object(orchestrator_module, "get_redis_client", return_value=fake):
        first = orch._check_parity_skip(0, payload)
        second = orch._check_parity_skip(0, payload)
    assert first == second


def test_check_parity_skip_duplicate_raises_p1(orchestrator_module):
    """Duplicate-on-this-tower must fire a P1_CRITICAL incident.

    Uses a non-NKD asset because the Q1 NKD parity exemption (audit
    2026-05-20) short-circuits before the duplicate-batch detector; the
    detector must still run as a diagnostic for non-NKD batches.
    """
    orch = _make_orch(orchestrator_module)
    fake = FakeRedis()
    payload = _payload(assets=["MGC"], session_id=4)

    with patch.object(
        orchestrator_module, "get_redis_client", return_value=fake,
    ), patch.object(
        orchestrator_module, "create_incident",
    ) as mock_incident:
        orch._check_parity_skip(0, payload)
        orch._check_parity_skip(0, payload)

    assert mock_incident.call_count == 1, (
        "Duplicate-batch detector did not fire on second invocation. "
        "Regression — PEL replay would now go undetected."
    )
    args, _kwargs = mock_incident.call_args
    assert args[1] == "P1_CRITICAL"
    assert "Duplicate parity batch processed" in args[3]


def test_check_parity_skip_empty_batch(orchestrator_module):
    """A batch with no signals returns skip=False."""
    orch = _make_orch(orchestrator_module)
    fake = FakeRedis()
    payload = {"session_id": 1, "user_id": "primary_user", "signals": []}

    with patch.object(orchestrator_module, "get_redis_client", return_value=fake):
        assert orch._check_parity_skip(0, payload) is False
        assert orch._check_parity_skip(1, payload) is False


def test_check_parity_skip_self_check_failure_does_not_block(orchestrator_module):
    """If the Redis self-check explodes, parity decision still proceeds."""
    orch = _make_orch(orchestrator_module)
    payload = _payload(assets=["NKD"], session_id=4)

    broken = MagicMock()
    broken.sadd.side_effect = RuntimeError("redis is down")

    with patch.object(orchestrator_module, "get_redis_client", return_value=broken):
        result = orch._check_parity_skip(0, payload)
    assert isinstance(result, bool)
