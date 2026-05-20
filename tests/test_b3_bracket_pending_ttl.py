"""Q3-(1) bracket-pending TTL extension test.

Verifies that _BRACKET_PENDING_TTL_S is 600s (extended from 10s) so the
bracket:pending hash survives a UserStream reconnect window. If this fails
the NKD trail ratchet can be permanently inert (sl_order_id stuck at
"BRACKET"). See audit section 8 G1 for root cause.
"""
from __future__ import annotations

from captain_command.blocks.b3_api_adapter import _BRACKET_PENDING_TTL_S


def test_bracket_pending_ttl_extended():
    """_BRACKET_PENDING_TTL_S must be 600s (Q3-(1) extended from 10s).

    A value ≤ 10 means the key expires before UserStream reconnects in the
    worst-case 60s exponential backoff window, leaving sl_order_id=BRACKET.
    A value >> 600 wastes Redis memory on stale keys.
    """
    assert _BRACKET_PENDING_TTL_S == 600, (
        f"Expected _BRACKET_PENDING_TTL_S=600 (Q3-(1) fix); "
        f"got {_BRACKET_PENDING_TTL_S}. Revert looks like a regression."
    )
