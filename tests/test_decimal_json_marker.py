"""Phase 4 regression: structural Decimal marker in dumps_decimal / loads_decimal.

Closes the second structural cause of the recurring decimal bug class:
the prior _coerce aggressively coerced every numeric-looking JSON string
to Decimal, which polluted account_id (SYMBOL), session_id (INT), and any
other ID column passing through Redis. This test pins the new wire format
({"__type__":"Decimal","value":"…"}) and verifies the backwards-compat
reader still accepts in-flight pre-marker payloads during the deploy
cycle.
"""
from __future__ import annotations

import json
import warnings
from decimal import Decimal

import pytest

from shared.decimal_json import (
    DecimalJSONEncoder,
    dumps_decimal,
    loads_decimal,
)


# ---------------------------------------------------------------------------
# 1. dumps_decimal emits the structural marker
# ---------------------------------------------------------------------------

def test_dumps_decimal_emits_marker_for_decimal():
    out = dumps_decimal({"price": Decimal("0.96")})
    parsed = json.loads(out)
    assert parsed == {"price": {"__type__": "Decimal", "value": "0.96"}}


def test_dumps_decimal_emits_marker_for_nested_decimal():
    out = dumps_decimal({
        "outer": {"inner": Decimal("4523.50")},
        "list": [Decimal("1.5"), Decimal("0.0")],
    })
    parsed = json.loads(out)
    assert parsed == {
        "outer": {"inner": {"__type__": "Decimal", "value": "4523.50"}},
        "list": [
            {"__type__": "Decimal", "value": "1.5"},
            {"__type__": "Decimal", "value": "0.0"},
        ],
    }


def test_dumps_decimal_expands_scientific_notation():
    """format(d, 'f') must NOT emit scientific notation."""
    out = dumps_decimal({"x": Decimal("5E-7")})
    parsed = json.loads(out)
    assert parsed == {"x": {"__type__": "Decimal", "value": "0.0000005"}}


def test_dumps_decimal_passes_through_non_decimal_types():
    out = dumps_decimal({"i": 42, "s": "hello", "b": True, "n": None, "f": 1.5})
    parsed = json.loads(out)
    assert parsed == {"i": 42, "s": "hello", "b": True, "n": None, "f": 1.5}


# ---------------------------------------------------------------------------
# 2. loads_decimal reconstructs Decimal from marker only
# ---------------------------------------------------------------------------

def test_loads_decimal_marker_round_trip():
    payload = '{"price": {"__type__": "Decimal", "value": "0.96"}}'
    out = loads_decimal(payload)
    assert out == {"price": Decimal("0.96")}
    assert isinstance(out["price"], Decimal)


def test_loads_decimal_account_id_stays_str_under_legacy_default():
    """The smoking-gun fix: integer-shaped strings must NOT become Decimal,
    even when legacy=True (the deploy-window default)."""
    payload = '{"account_id": "21855714", "session_id": "1"}'
    out = loads_decimal(payload)
    assert out == {"account_id": "21855714", "session_id": "1"}
    assert isinstance(out["account_id"], str)
    assert isinstance(out["session_id"], str)


def test_loads_decimal_uuid_strings_stay_str():
    payload = '{"trade_id": "TRD-A1B2C3", "signal_id": "SIG-D4E5F6"}'
    out = loads_decimal(payload)
    assert out == {"trade_id": "TRD-A1B2C3", "signal_id": "SIG-D4E5F6"}


def test_loads_decimal_alphabetic_strings_stay_str():
    payload = '{"user_id": "primary_user", "role": "ADMIN"}'
    out = loads_decimal(payload)
    assert out == {"user_id": "primary_user", "role": "ADMIN"}


def test_loads_decimal_short_numeric_strings_stay_str():
    """Length-5 floor protects '1', '0', '1.5' from being coerced."""
    payload = '{"a": "1", "b": "0", "c": "1.5", "d": "0.5"}'
    out = loads_decimal(payload)
    assert out == {"a": "1", "b": "0", "c": "1.5", "d": "0.5"}


# ---------------------------------------------------------------------------
# 3. Legacy bare-string coercion (deploy-window backwards compat)
# ---------------------------------------------------------------------------

def test_legacy_true_coerces_long_decimal_string():
    """Legacy=True (default) coerces strings with '.' AND length >= 5."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        payload = '{"price": "4523.50"}'
        out = loads_decimal(payload, legacy=True)
        assert isinstance(out["price"], Decimal)
        assert out["price"] == Decimal("4523.50")


def test_legacy_false_strict_no_coercion():
    """Legacy=False is strict — only marker dicts become Decimal."""
    payload = '{"price": "4523.50"}'
    out = loads_decimal(payload, legacy=False)
    assert out == {"price": "4523.50"}
    assert isinstance(out["price"], str)


def test_legacy_emits_deprecation_warning_once_per_process():
    """First legacy fire emits a DeprecationWarning. Subsequent fires don't
    (deliberate: avoid log spam)."""
    import shared.decimal_json as dj
    dj._LEGACY_WARNED = False
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loads_decimal('{"price": "4523.50"}', legacy=True)
        loads_decimal('{"other": "9999.99"}', legacy=True)
    deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) == 1, (
        f"expected exactly 1 DeprecationWarning, got {len(deprecation_warnings)}"
    )
    dj._LEGACY_WARNED = False


# ---------------------------------------------------------------------------
# 4. Round-trip — dumps_decimal -> loads_decimal returns identical Decimal types
# ---------------------------------------------------------------------------

def test_round_trip_preserves_decimal_type():
    original = {
        "a": Decimal("0.96"),
        "b": [Decimal("1.5"), {"c": Decimal("3.14")}],
        "d": {"e": Decimal("4523.50")},
    }
    serialised = dumps_decimal(original)
    parsed = loads_decimal(serialised)
    assert parsed == original
    assert isinstance(parsed["a"], Decimal)
    assert isinstance(parsed["b"][0], Decimal)
    assert isinstance(parsed["b"][1]["c"], Decimal)
    assert isinstance(parsed["d"]["e"], Decimal)


def test_round_trip_preserves_string_type():
    """Non-Decimal strings stay str through round-trip."""
    original = {"account_id": "21855714", "user_id": "primary_user"}
    parsed = loads_decimal(dumps_decimal(original))
    assert parsed == original
    assert isinstance(parsed["account_id"], str)


def test_round_trip_preserves_int_type():
    """JSON ints with coerce_json_int=False stay int."""
    original = {"contracts": 5, "session": 1}
    serialised = dumps_decimal(original)
    parsed = loads_decimal(serialised, coerce_json_int=False)
    assert parsed == original
    assert isinstance(parsed["contracts"], int)


# ---------------------------------------------------------------------------
# 5. parse_json_decimal still works (json_helpers.py thin wrapper)
# ---------------------------------------------------------------------------

def test_parse_json_decimal_delegates_to_loads_decimal():
    from shared.json_helpers import parse_json_decimal
    out = parse_json_decimal('{"price": {"__type__": "Decimal", "value": "0.96"}}', {})
    assert out == {"price": Decimal("0.96")}


def test_parse_json_decimal_returns_default_on_invalid_json():
    from shared.json_helpers import parse_json_decimal
    out = parse_json_decimal("not valid json", {"fallback": True})
    assert out == {"fallback": True}


def test_parse_json_decimal_returns_default_on_none():
    from shared.json_helpers import parse_json_decimal
    out = parse_json_decimal(None, {"fallback": True})
    assert out == {"fallback": True}


# ---------------------------------------------------------------------------
# 6. Malformed marker is preserved as dict (defensive)
# ---------------------------------------------------------------------------

def test_malformed_decimal_marker_value_stays_as_dict():
    """If marker.value can't be Decimal()-ed, leave the dict intact."""
    payload = '{"x": {"__type__": "Decimal", "value": "not-a-number"}}'
    out = loads_decimal(payload, legacy=False)
    assert out == {"x": {"__type__": "Decimal", "value": "not-a-number"}}


def test_marker_missing_value_stays_as_dict():
    payload = '{"x": {"__type__": "Decimal"}}'
    out = loads_decimal(payload, legacy=False)
    assert out == {"x": {"__type__": "Decimal"}}


def test_unrelated_dict_with_type_field_passes_through():
    """A dict with __type__ != "Decimal" must not be consumed."""
    payload = '{"x": {"__type__": "Note", "value": "hello"}}'
    out = loads_decimal(payload, legacy=False)
    assert out == {"x": {"__type__": "Note", "value": "hello"}}
