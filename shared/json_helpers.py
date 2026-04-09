"""Shared JSON parsing utilities."""

import json


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
