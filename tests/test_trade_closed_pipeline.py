"""GUI trade-close plumbing: hub payload normalization + Command WS payload builder."""

from __future__ import annotations

from captain_command.blocks.trade_gui_bridge import build_trade_closed_ws_payload
from shared.topstep_stream import _normalize_hub_payload


def test_normalize_hub_payload_pascal_case_to_camel_case():
    raw = {"Id": 789, "AccountId": 123, "Status": 2, "ContractId": "CON.F.US.MNQ"}
    out = _normalize_hub_payload(raw)
    assert out["id"] == 789
    assert out["accountId"] == 123
    assert out["status"] == 2
    assert out["contractId"] == "CON.F.US.MNQ"


def test_normalize_hub_payload_already_camel_case_unchanged():
    raw = {"id": 1, "profitAndLoss": 12.5}
    out = _normalize_hub_payload(raw)
    assert out["id"] == 1
    assert out["profitAndLoss"] == 12.5


def test_build_trade_closed_ws_payload_full():
    pair = build_trade_closed_ws_payload({
        "user_id": "primary_user",
        "trade_id": "TRD-ABC",
        "signal_id": "SIG-1",
        "asset": "MNQ",
        "direction": 1,
        "pnl": -50.0,
        "outcome": "SL_HIT",
        "exit_time": "2026-04-28T10:00:00-04:00",
    })
    assert pair is not None
    uid, msg = pair
    assert uid == "primary_user"
    assert msg["type"] == "trade_closed"
    assert msg["trade_id"] == "TRD-ABC"
    assert msg["signal_id"] == "SIG-1"
    assert msg["pnl"] == -50.0


def test_build_trade_closed_ws_payload_rejects_missing_user():
    assert build_trade_closed_ws_payload({"trade_id": "TRD-X"}) is None
