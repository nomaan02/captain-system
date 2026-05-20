"""Regression test for b1_core_routing._log_signal_received Decimal serialisation.

Failure mode (2026-05-05 LON open, MGC SIG-66D2424516E4):
    [COMMAND] ERROR captain_command.blocks.b1_core_routing:
        Failed to log signal SIG-66D2424516E4: Object of type Decimal is
        not JSON serializable

Cause: signal dict contains Decimal values (entry_price, tp_level, sl_level,
quality_score, size) post Phase A migration. json.dumps does not handle
Decimal. dumps_decimal does.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from shared.decimal_json import loads_decimal


def _decimal_signal() -> dict:
    """Mirror the runtime payload shape from b6_signal_output."""
    return {
        "signal_id": "SIG-DECIMAL-TEST",
        "user_id": "primary_user",
        "asset": "MGC",
        "direction": "BUY",
        "size": 5,
        "tp_level": Decimal("4568.5"),
        "sl_level": Decimal("4561.6"),
        "_context": {
            "entry_price": Decimal("4563.9"),
            "confidence_tier": "MEDIUM",
            "quality_score": Decimal("0.82"),
        },
    }


def test_log_signal_received_does_not_typeerror_on_decimal_signal(monkeypatch):
    """The failure mode that lost SIG-66D2424516E4's audit row this morning."""
    from captain_command.blocks import b1_core_routing

    captured = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(b1_core_routing, "get_cursor", lambda: _FakeCursor())

    signal = _decimal_signal()
    b1_core_routing._log_signal_received(
        signal["signal_id"], signal["user_id"], signal,
    )

    assert "params" in captured, (
        "INSERT was never executed — _log_signal_received fell into the "
        "bare-except branch (likely a TypeError on Decimal serialisation)."
    )
    details_json = captured["params"][5]
    parsed = loads_decimal(details_json)
    assert parsed["entry_price"] == Decimal("4563.9")
    assert parsed["tp_level"] == Decimal("4568.5")
    assert parsed["sl_level"] == Decimal("4561.6")
    assert parsed["quality_score"] == Decimal("0.82")
    assert parsed["size"] == Decimal("5")  # int -> Decimal via loads_decimal default


def test_log_trade_confirmation_does_not_typeerror_on_decimal_actual_entry(monkeypatch):
    """Same risk pattern at the second hot path (line 477)."""
    from captain_command.blocks import b1_core_routing

    captured = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["params"] = params

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(b1_core_routing, "get_cursor", lambda: _FakeCursor())

    data = {
        "asset": "MES",
        "account_id": "21855714",
        "contracts": 5,
        "actual_entry_price": Decimal("5825.50"),
    }
    b1_core_routing._log_trade_confirmation("SIG-TEST", "primary_user", "TAKEN", data)

    assert "params" in captured, "INSERT path did not execute — Decimal regressed."
    parsed = loads_decimal(captured["params"][5])
    assert parsed["actual_entry_price"] == Decimal("5825.50")


def test_route_command_taken_preserves_nkd_trail_fields(monkeypatch):
    """Audit F3 fix: the manual GUI TAKEN path must forward all 6 NKD
    trail-control fields onto STREAM_COMMANDS so b7b_nkd_trail engages
    even when a NKD signal is taken manually via the GUI (not auto-execute).
    See REJECTED_ORDERS_AUDIT.md §0 F3, §7 Option B.
    """
    from captain_command.blocks import b1_core_routing

    captured: dict = {}

    def _fake_publish(stream, data):
        captured["stream"] = stream
        captured["data"] = data
        return "1-0"

    monkeypatch.setattr(b1_core_routing, "publish_to_stream", _fake_publish)
    monkeypatch.setattr(
        b1_core_routing, "_log_trade_confirmation",
        lambda *_args, **_kw: None,
    )

    data = {
        "type": "TAKEN_SKIPPED",
        "action": "TAKEN",
        "signal_id": "SIG-NKD-MANUAL-001",
        "user_id": "primary_user",
        "asset": "NKD",
        "direction": -1,
        "actual_entry_price": 61600,
        "entry_price": 61570,
        "contracts": 1,
        "tp_level": 60680,
        "sl_level": 61805,
        "account_id": "21855714",
        "session": 3,
        "bracket": True,
        "entry_order_id": "ENT-NKD-001",
        "is_nkd_trail": True,
        "tp_dollars": 4450,
        "snapped_d_init": 1025.0,
        "jitter_x": 0.5,
        "jitter_y": 1,
        "jitter_j": 10.0,
    }
    b1_core_routing.route_command(data, gui_push_fn=lambda *_a, **_kw: None)

    assert "data" in captured, "publish_to_stream was never called"
    msg = captured["data"]
    assert msg["type"] == "TAKEN_SKIPPED"
    assert msg["action"] == "TAKEN"
    assert msg["asset"] == "NKD"
    assert msg["is_nkd_trail"] is True
    assert msg["tp_dollars"] == 4450
    assert msg["snapped_d_init"] == 1025.0
    assert msg["jitter_x"] == 0.5
    assert msg["jitter_y"] == 1
    assert msg["jitter_j"] == 10.0


def test_route_command_taken_non_nkd_signal_has_none_nkd_keys(monkeypatch):
    """Defensive: GUI clients that do not yet ship the 6 NKD keys must not
    cause KeyError or change behaviour for ES/MES/etc. — the 6 keys default
    to None on STREAM_COMMANDS, and downstream _handle_taken_skipped will
    coerce them harmlessly.
    """
    from captain_command.blocks import b1_core_routing

    captured: dict = {}

    def _fake_publish(stream, data):
        captured["data"] = data
        return "1-0"

    monkeypatch.setattr(b1_core_routing, "publish_to_stream", _fake_publish)
    monkeypatch.setattr(
        b1_core_routing, "_log_trade_confirmation",
        lambda *_args, **_kw: None,
    )

    data = {
        "type": "TAKEN_SKIPPED",
        "action": "TAKEN",
        "signal_id": "SIG-ES-MANUAL-001",
        "user_id": "primary_user",
        "asset": "ES",
        "direction": 1,
        "contracts": 2,
        "tp_level": 6443.20,
        "sl_level": 6460.53,
        "account_id": "20319784",
    }
    b1_core_routing.route_command(data, gui_push_fn=lambda *_a, **_kw: None)

    msg = captured["data"]
    assert msg["asset"] == "ES"
    assert msg["is_nkd_trail"] is None
    assert msg["tp_dollars"] is None
    assert msg["snapped_d_init"] is None
    assert msg["jitter_x"] is None
    assert msg["jitter_y"] is None
    assert msg["jitter_j"] is None


def _build_online_position(stream_msg: dict) -> dict:
    """Replicate the type-coercion logic from OnlineOrchestrator._handle_taken_skipped.

    The online orchestrator cannot be imported in tower-safe tests (transitive
    pysignalr dependency). This helper copies the relevant field extraction
    and as_money_or_none coercions verbatim so the C8 E2E tests verify that
    the same Decimal types arrive at B7B as they would in production.
    """
    from shared.decimal_boundary import as_money, as_money_or_none
    data = stream_msg
    direction_raw = data.get("direction")
    if direction_raw in (1, "BUY"):
        direction = 1
    elif direction_raw in (-1, "SELL"):
        direction = -1
    else:
        direction = int(direction_raw or 1)
    return {
        "signal_id": data.get("signal_id"),
        "user_id": data.get("user_id"),
        "asset": data.get("asset"),
        "direction": direction,
        "entry_price": as_money_or_none(
            data.get("actual_entry_price") if data.get("actual_entry_price") is not None
            else data.get("entry_price")
        ),
        "signal_entry_price": as_money_or_none(data.get("entry_price")),
        "actual_entry_price": as_money_or_none(data.get("actual_entry_price")),
        "contracts": int(data.get("contracts", 0) or 0),
        "tp_level": as_money_or_none(data.get("tp_level")),
        "sl_level": as_money_or_none(data.get("sl_level")),
        "point_value": as_money(data.get("point_value"), default=as_money(50)),
        "risk_amount": as_money(data.get("risk_amount")),
        "account": data.get("account_id"),
        "session": data.get("session"),
        "regime_state": data.get("regime_state"),
        "combined_modifier": data.get("combined_modifier"),
        "aim_breakdown": data.get("aim_breakdown"),
        "tsm_id": data.get("tsm_id"),
        "entry_time": None,
        "bracket": bool(data.get("bracket", False)),
        "entry_order_id": data.get("entry_order_id"),
        "sl_order_id": data.get("sl_order_id"),
        "tp_order_id": data.get("tp_order_id"),
        "is_nkd_trail": bool(data.get("is_nkd_trail", False)),
        "tp_dollars": as_money_or_none(data.get("tp_dollars")),
        "snapped_d_init": as_money_or_none(data.get("snapped_d_init")),
        "jitter_x": as_money_or_none(data.get("jitter_x")),
        "jitter_y": (int(data["jitter_y"]) if data.get("jitter_y") is not None else None),
        "jitter_j": as_money_or_none(data.get("jitter_j")),
        "current_phase": None,
        "current_buffer": None,
        "current_stop_price": None,
        "modify_seq": 0,
    }


def test_e2e_manual_taken_nkd_signal_to_ratchet(monkeypatch):
    """G4 E2E: manual GUI TAKEN with all 6 NKD fields → command forwards to
    STREAM_COMMANDS → online position dict has correct Decimal types → B7B
    scan proceeds past the sl_order_id gate and enters ratchet logic.

    This test verifies the full command→online→B7B field-forwarding chain
    without importing the online orchestrator (pysignalr-free).
    """
    from captain_command.blocks import b1_core_routing
    from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails
    from decimal import Decimal as D

    captured: dict = {}

    def _fake_publish(stream, data):
        captured["data"] = data
        return "1-0"

    monkeypatch.setattr(b1_core_routing, "publish_to_stream", _fake_publish)
    monkeypatch.setattr(b1_core_routing, "_log_trade_confirmation",
                        lambda *_a, **_kw: None)

    gui_post = {
        "type": "TAKEN_SKIPPED",
        "action": "TAKEN",
        "signal_id": "SIG-NKD-E2E-001",
        "user_id": "primary_user",
        "asset": "NKD",
        "direction": -1,
        "actual_entry_price": 61600,
        "entry_price": 61570,
        "contracts": 1,
        "tp_level": 60680,
        "sl_level": 61805,
        "account_id": "21855714",
        "session": 3,
        "bracket": True,
        "entry_order_id": "ENT-NKD-E2E-001",
        "sl_order_id": 777777,   # real SL id — bypass the unresolved gate
        "tp_order_id": 777778,
        "is_nkd_trail": True,
        "tp_dollars": 4450,
        "snapped_d_init": 1025,
        "jitter_x": 0.0,
        "jitter_y": 0,
        "jitter_j": 0.0,
    }
    b1_core_routing.route_command(gui_post, gui_push_fn=lambda *_a, **_kw: None)

    stream_msg = captured["data"]
    assert stream_msg["is_nkd_trail"] is True, "Command must forward is_nkd_trail"
    assert stream_msg["jitter_j"] == 0.0
    # route_command intentionally omits sl_order_id — it is set later by UserStream
    assert "sl_order_id" not in stream_msg or stream_msg["sl_order_id"] is None

    # Replicate _handle_taken_skipped position-dict construction
    position = _build_online_position(stream_msg)

    # Decimal coercion must have happened for the 6 NKD trail fields
    assert isinstance(position["tp_dollars"], D), (
        f"tp_dollars must be Decimal after coercion; got {type(position['tp_dollars'])}"
    )
    assert isinstance(position["snapped_d_init"], D)
    assert isinstance(position["jitter_j"], D)

    # Simulate UserStream resolving the SL child order (as happens post-bracket placement).
    # route_command → STREAM_COMMANDS has no sl_order_id; UserStream fills it in.
    position["sl_order_id"] = "777777"

    # Feed to B7B — with a resolved sl_order_id the scan proceeds to ratchet logic
    diag_rows = []
    scan_nkd_trails(
        open_positions=[position],
        client=MagicMock(**{"modify_order.return_value": {"success": True}}),
        redis_client=None,
        quote_lookup=lambda asset, cid: (D("61700"), 0.0),  # SHORT: mark rising = loss
        persist_d34=lambda row: diag_rows.append(row),
        compliance_modify_check=lambda *_: (True, None),
        parity_env="0",
    )
    assert diag_rows, "B7B must emit a D34 row — scan reached ratchet logic"
    assert diag_rows[0].get("skip_reason") != "sl_order_id_unresolved", (
        "B7B must NOT skip due to unresolved sl_order_id when a real ID was provided"
    )


def test_e2e_manual_taken_without_jitter_field_logs_warning(monkeypatch):
    """G4 regression: GUI POST body MISSING jitter_j → position has jitter_j=None
    → on Isaac tower (parity_env='1') first-poll B7B emits CRITICAL
    NKD_TRAIL_JITTER_MISSING alert and defence-in-depth re-samples J.

    This covers the pre-F2 regression scenario where jitter_j was absent.
    """
    import json
    from captain_command.blocks import b1_core_routing
    from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails
    from decimal import Decimal as D

    captured: dict = {}

    def _fake_publish(stream, data):
        captured["data"] = data
        return "1-0"

    monkeypatch.setattr(b1_core_routing, "publish_to_stream", _fake_publish)
    monkeypatch.setattr(b1_core_routing, "_log_trade_confirmation",
                        lambda *_a, **_kw: None)

    gui_post_missing_jitter = {
        "type": "TAKEN_SKIPPED",
        "action": "TAKEN",
        "signal_id": "SIG-NKD-E2E-002",
        "user_id": "primary_user",
        "asset": "NKD",
        "direction": 1,
        "actual_entry_price": 38000,
        "entry_price": 38000,
        "contracts": 1,
        "tp_level": 38890,
        "sl_level": 37795,
        "account_id": "21855714",
        "session": 3,
        "bracket": True,
        "entry_order_id": "ENT-NKD-E2E-002",
        "sl_order_id": 888888,
        "tp_order_id": 888889,
        "is_nkd_trail": True,
        "tp_dollars": 4450,
        "snapped_d_init": 1025,
        # jitter_x, jitter_y, jitter_j intentionally absent
    }
    b1_core_routing.route_command(gui_post_missing_jitter,
                                  gui_push_fn=lambda *_a, **_kw: None)

    stream_msg = captured["data"]
    assert stream_msg.get("jitter_j") is None, (
        "STREAM_COMMANDS must carry jitter_j=None when GUI didn't send it"
    )

    position = _build_online_position(stream_msg)
    assert position["jitter_j"] is None, (
        "Position dict jitter_j must be None (triggers defence-in-depth re-sample)"
    )

    # Simulate UserStream resolving the SL child order so B7B reaches jitter sampling.
    # Without sl_order_id, _scan_one_trail returns at the unresolved gate before
    # the jitter check — we want to test the jitter path, not the unresolved path.
    position["sl_order_id"] = "888888"

    mock_redis = MagicMock()
    mock_redis.hget.return_value = None

    diag_rows = []
    scan_nkd_trails(
        open_positions=[position],
        client=MagicMock(**{"modify_order.return_value": {"success": True}}),
        redis_client=mock_redis,
        quote_lookup=lambda asset, cid: (D("38100"), 0.0),
        persist_d34=lambda row: diag_rows.append(row),
        compliance_modify_check=lambda *_: (True, None),
        parity_env="1",  # Isaac tower — alert must fire when jitter_j is None
    )

    # B7B must have published NKD_TRAIL_JITTER_MISSING CRITICAL alert
    jitter_alerts = []
    for call_args in mock_redis.publish.call_args_list:
        try:
            payload = json.loads(call_args[0][1])
            if payload.get("event_type") == "NKD_TRAIL_JITTER_MISSING":
                jitter_alerts.append(payload)
        except (json.JSONDecodeError, IndexError):
            pass
    assert len(jitter_alerts) >= 1, (
        "NKD_TRAIL_JITTER_MISSING CRITICAL alert must fire on Isaac tower "
        "when jitter_j is absent from the GUI POST body"
    )
    # Defence-in-depth must have re-sampled J (position dict now has a value)
    assert position.get("jitter_j") is not None, (
        "B7B defence-in-depth must re-sample jitter_j when it arrives as None"
    )
