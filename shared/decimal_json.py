"""Decimal-aware JSON serialisation for monetary values stored in QuestDB STRING columns.

Used wherever a JSON-serialised STRING column contains dollar amounts that must
preserve precision through the round-trip. See MONETARY_DECIMAL_MIGRATION_COMPLETE.md
for the full list of affected columns.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any


class DecimalJSONEncoder(json.JSONEncoder):
    """Serialises Decimal as a JSON string to preserve precision."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def dumps_decimal(obj: Any) -> str:
    """Serialise an object to JSON, encoding Decimal as string."""
    return json.dumps(obj, cls=DecimalJSONEncoder)


def loads_decimal(s: str) -> Any:
    """Parse JSON, returning all numeric values as Decimal (not float).

    Decimals encoded by ``DecimalJSONEncoder`` appear as JSON strings; those
    are coerced back to ``Decimal`` after parse. Non-numeric strings are left
    unchanged. JSON integers use ``parse_int=Decimal`` so round-trips stay
    consistent with monetary arithmetic.
    """
    data = json.loads(s, parse_float=Decimal, parse_int=Decimal)

    def _coerce(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _coerce(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_coerce(v) for v in obj]
        if isinstance(obj, str):
            try:
                return Decimal(obj)
            except InvalidOperation:
                return obj
        return obj

    return _coerce(data)
