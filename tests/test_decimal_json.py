"""Tests for shared.decimal_json — monetary JSON round-trip."""
from __future__ import annotations

import json
from decimal import Decimal

from shared.decimal_json import DecimalJSONEncoder, dumps_decimal, loads_decimal


def test_round_trip_nested_dict_decimals():
    obj = {
        "a": Decimal("123.45"),
        "nested": {"b": Decimal("0.01"), "c": 2},
        "d": "keep",
    }
    s = dumps_decimal(obj)
    back = loads_decimal(s)
    assert back["a"] == Decimal("123.45")
    assert isinstance(back["a"], Decimal)
    assert back["nested"]["b"] == Decimal("0.01")
    assert back["nested"]["c"] == Decimal("2")
    assert back["d"] == "keep"


def test_mixed_decimal_int_string():
    obj = {"x": Decimal("1.5"), "y": 42, "z": "text"}
    back = loads_decimal(dumps_decimal(obj))
    assert back["x"] == Decimal("1.5")
    assert back["y"] == Decimal("42")
    assert back["z"] == "text"


def test_input_json_floats_become_decimal():
    raw = '{"f": 0.1, "g": 3.14}'
    data = loads_decimal(raw)
    assert isinstance(data["f"], Decimal)
    assert isinstance(data["g"], Decimal)
    assert data["f"] == Decimal("0.1")
    assert data["g"] == Decimal("3.14")


def test_decimal_json_encoder_standalone():
    s = json.dumps({"m": Decimal("99.99")}, cls=DecimalJSONEncoder)
    assert '"m"' in s
    parsed = loads_decimal(s)
    assert parsed["m"] == Decimal("99.99")


def test_redis_stream_payload_keeps_json_integers_as_int():
    raw = '{"direction": 1, "contracts": 2, "x": 1.5}'
    data = loads_decimal(raw, coerce_json_int=False)
    assert data["direction"] == 1
    assert isinstance(data["direction"], int)
    assert data["contracts"] == 2
    assert isinstance(data["x"], Decimal)
