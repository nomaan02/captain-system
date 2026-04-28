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
    """Serialise an object to JSON, encoding Decimal as string.

    ``default=str`` matches stream/pubsub payloads that include datetimes and
    other non-JSON-native objects (same behaviour as prior ``json.dumps(..., default=str)``).
    """
    return json.dumps(obj, cls=DecimalJSONEncoder, default=str)


def loads_decimal(s: str, *, coerce_json_int: bool = True) -> Any:
    """Parse JSON, returning floats and (optionally) ints as Decimal.

    Decimals encoded by ``DecimalJSONEncoder`` appear as JSON strings; those
    are coerced back to ``Decimal`` after parse. Non-numeric strings are left
    unchanged.

    ``coerce_json_int``: when True (default), JSON integers become ``Decimal``
    for round-trip consistency with :func:`dumps_decimal`. When False (e.g. Redis
    stream payloads), integers stay ``int`` so ``direction`` / ``contracts`` etc.
    remain usable without casting.
    """
    parse_int = Decimal if coerce_json_int else int
    data = json.loads(s, parse_float=Decimal, parse_int=parse_int)

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
