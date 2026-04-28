# region imports
from AlgorithmImports import *
# endregion
"""Tests for b5_sensitivity AIM-13 FRAGILE / ROBUST D01 modifier envelopes (Phase 2 B2-3)."""

import json
from unittest.mock import MagicMock

import pytest

from captain_offline.blocks import b5_sensitivity
from captain_offline.blocks.b5_sensitivity import run_sensitivity_scan
from shared.aim_compute import _aim13_sensitivity
from shared.json_helpers import parse_json


def _base_returns_40():
    return [0.01 * (i % 5 - 2) for i in range(40)]


def _last_aim13_modifier(mock_cursor) -> str | None:
    """Last INSERT into p3_d01 for aim_id=13: return current_modifier cell (JSON string)."""
    for call in reversed(mock_cursor.execute.call_args_list):
        args, _ = call
        if len(args) < 2:
            continue
        sql, params = args[0], args[1]
        if "p3_d01_aim_model_states" in sql and params and len(params) >= 3:
            if params[0] == 13 and "current_modifier" in sql.replace("\n", " "):
                return params[2]
    return None


def test_aim13_fragile_writes_dict_envelope(monkeypatch):
    """b5_sensitivity FRAGILE path must write JSON dict, not bare float."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_get_cursor = MagicMock(return_value=mock_cursor)
    monkeypatch.setattr(
        "captain_offline.blocks.b5_sensitivity.get_cursor", mock_get_cursor
    )
    monkeypatch.setattr(
        b5_sensitivity, "_compute_dsr", lambda *a, **k: 0.5
    )
    # Force FRAGILE outcome without depending on full scan numerics
    monkeypatch.setattr(
        b5_sensitivity, "MIN_FLAGS_FOR_FRAGILE", 0
    )

    run_sensitivity_scan(asset_id="ES", base_returns=_base_returns_40())

    mod = _last_aim13_modifier(mock_cursor)
    assert mod, "expected D01 modifier INSERT for aim 13"
    val = json.loads(mod)
    assert val == {"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"}


def test_aim13_fragile_round_trip():
    """parse_json on dict-envelope string returns dict; _aim13_sensitivity extracts 0.85."""
    raw = json.dumps({"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"})
    parsed = parse_json(raw, None)
    result = _aim13_sensitivity({}, {"current_modifier": parsed})
    assert result["modifier"] == 0.85
    assert result["reason_tag"] == "AIM13_FRAGILE"


def test_aim13_robust_writes_neutral_envelope(monkeypatch):
    """ROBUST path writes neutral dict to clear prior FRAGILE state."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_get_cursor = MagicMock(return_value=mock_cursor)
    monkeypatch.setattr(
        "captain_offline.blocks.b5_sensitivity.get_cursor", mock_get_cursor
    )
    monkeypatch.setattr(
        b5_sensitivity, "_compute_dsr", lambda *a, **k: 0.5
    )
    # Never mark as FRAGILE
    monkeypatch.setattr(
        b5_sensitivity, "MIN_FLAGS_FOR_FRAGILE", 999
    )

    run_sensitivity_scan(asset_id="ES", base_returns=_base_returns_40())

    mod = _last_aim13_modifier(mock_cursor)
    assert mod, "expected D01 neutral modifier INSERT for aim 13"
    val = json.loads(mod)
    assert val["modifier"] == 1.0
    assert val["reason_tag"] == "SENSITIVITY_NORMAL"
