"""Decimal-aware JSON serialisation for monetary values stored in QuestDB STRING columns.

Used wherever a JSON-serialised STRING column contains dollar amounts that must
preserve precision through the round-trip. See MONETARY_DECIMAL_MIGRATION_COMPLETE.md
for the full list of affected columns.

Phase 4 (2026-05-06): the wire format moved from a bare-string Decimal
to a structural marker ``{"__type__": "Decimal", "value": "<digits>"}``.
The marker eliminates the prior ``_coerce`` over-coercion that turned
account IDs / session IDs / any numeric-looking string into a Decimal
on decode (the structural cause of the SYMBOL/INT INSERT crash class).

A backwards-compat reader (``legacy=True``) is on by default during the
2026-05 deploy window so in-flight Redis state from pre-marker producers
still parses correctly. Set ``legacy=False`` once the open-positions hash
is confirmed marker-only (typically one weekly cycle after deploy).
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any


class DecimalJSONEncoder(json.JSONEncoder):
    """Serialise ``Decimal`` as a structural marker enabling lossless round-trip
    without ambiguous string→Decimal heuristics on the decode side.

    Wire format: ``{"__type__": "Decimal", "value": "<digits>"}``.

    ``format(obj, "f")`` matches the precision discipline in
    ``shared.questdb_client._decimal_to_cast_sql`` — it expands scientific
    notation losslessly (e.g. ``Decimal("5E-7") -> "0.0000005"``).

    Non-Decimal, non-JSON-native objects (datetimes etc.) fall through to
    ``str(obj)``, preserving the prior ``default=str`` behaviour for
    stream/pubsub payloads. We can't pass ``default=str`` to ``json.dumps``
    because that would override this class's ``default`` method via
    ``JSONEncoder.__init__`` and the marker would never be emitted.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return {"__type__": "Decimal", "value": format(obj, "f")}
        try:
            return str(obj)
        except Exception:
            return super().default(obj)


def dumps_decimal(obj: Any) -> str:
    """Serialise an object to JSON, encoding Decimal as the structural marker.

    Datetimes and other non-JSON-native objects fall through to ``str(obj)``
    via the encoder's ``default`` method (same behaviour as the prior
    ``json.dumps(..., default=str)`` shim).
    """
    return json.dumps(obj, cls=DecimalJSONEncoder)


_LEGACY_WARNED = False


def loads_decimal(
    s: str,
    *,
    coerce_json_int: bool = True,
    legacy: bool = True,
) -> Any:
    """Parse JSON. Decimals are reconstructed ONLY from the structural marker
    ``{"__type__": "Decimal", "value": "<digits>"}``. JSON ints/floats follow
    the ``parse_int`` / ``parse_float`` behaviour. Plain strings stay strings —
    no more ambiguous numeric-string coercion (the prior ``_coerce`` over-
    coercion was the structural source of the ``account_id`` SYMBOL crash
    incident).

    ``legacy=True`` (default during the 2026-05 deploy window): also accepts
    bare-string Decimals from pre-marker producers when the string contains a
    decimal point AND length >= 5 (excludes integer-shaped IDs like
    ``"21855714"``, short numerics like ``"1"`` / ``"0"`` / ``"1.5"``, and
    pure alphabetic strings). This compat path emits a ``DeprecationWarning``
    the first time it fires per process. Set ``legacy=False`` once the
    ``captain:open_positions`` Redis hash inspection confirms all entries
    use the new marker format (typically one weekly cycle after deploy).

    ``coerce_json_int=False`` (e.g. Redis stream payloads): JSON integers
    stay ``int`` so ``direction`` / ``contracts`` / ``session`` etc. remain
    usable without casting.
    """
    parse_int = Decimal if coerce_json_int else int
    data = json.loads(s, parse_float=Decimal, parse_int=parse_int)
    return _coerce_with_marker(data, legacy=legacy)


def _coerce_with_marker(obj: Any, *, legacy: bool) -> Any:
    """Recursive coercion respecting the structural Decimal marker.

    Marker shape: ``{"__type__": "Decimal", "value": "<digits>"}`` →
    ``Decimal("<digits>")``. Every other dict/list/scalar passes through
    unchanged, EXCEPT under ``legacy=True`` a string containing a decimal
    point AND length >= 5 is coerced to ``Decimal`` (matches old behaviour
    for legitimate price strings; excludes all-digit IDs).
    """
    if isinstance(obj, dict):
        if obj.get("__type__") == "Decimal" and "value" in obj:
            try:
                return Decimal(str(obj["value"]))
            except InvalidOperation:
                return obj
        return {k: _coerce_with_marker(v, legacy=legacy) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_with_marker(v, legacy=legacy) for v in obj]
    if isinstance(obj, str) and legacy:
        # Strict guard: must contain '.' AND length >= 5. Excludes:
        #   "21855714" (account ID, integer-shaped) — stays str
        #   "primary_user" (alphabetic) — stays str
        #   "SIG-…", "TRD-…" (UUID-shaped) — stays str
        #   "1", "0", "1.5", "0.5" (short numeric) — stays str
        # Coerces:
        #   "4523.50", "0.96000000" — to Decimal (old behaviour preserved)
        if "." in obj and len(obj) >= 5:
            try:
                v = Decimal(obj)
            except InvalidOperation:
                return obj
            global _LEGACY_WARNED
            if not _LEGACY_WARNED:
                import warnings
                warnings.warn(
                    "loads_decimal: legacy bare-string Decimal coercion "
                    "fired. Set legacy=False once all producers emit the "
                    "structural marker (see shared/decimal_json.py).",
                    DeprecationWarning,
                    stacklevel=3,
                )
                _LEGACY_WARNED = True
            return v
        return obj
    return obj
