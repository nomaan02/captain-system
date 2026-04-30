"""Shared JSON parsing utilities."""

import json

from shared.decimal_json import loads_decimal


def parse_json(raw, default):
    """Safely parse a JSON string, returning *default* on failure or None input."""
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def parse_json_decimal(raw, default):
    """Like ``parse_json``, but numeric leaves round-trip as ``Decimal`` (monetary JSON)."""
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return default
    try:
        return loads_decimal(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default
