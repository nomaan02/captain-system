"""Boundary coercion for monetary values flowing in/out of the trading core.

Use these three primitives at every database read and every output dict
construction that touches a DECIMAL column from QuestDB. Internal arithmetic
on monetary state stays in Decimal end-to-end. The explicit ``to_float``
escape hatch is reserved for sizing math and probabilistic estimators where
float precision is more than adequate (rounded via ``math.floor``/``round``).

Anti-patterns this module exists to eliminate
---------------------------------------------
* ``Decimal('0.00') or 0.0 -> 0.0`` (float)        — the falsy-zero collapse
* ``Decimal(value)`` with a float input            — inherits float bit pattern
* Six private ``_money*`` helpers per file         — consolidated here
* Type-mixed dicts (some Decimal, some float)      — produced TypeError on
  ``mdd_limit - current_drawdown`` at NY open 2026-04-30. See
  ``docs2/quick-fixes/fixing-decimal-errors/`` for the audit + plan.

Public API
----------
* ``as_money(value, *, default=Decimal("0"))`` -> Decimal
* ``as_money_or_none(value)`` -> Decimal | None
* ``to_float(value, *, default=0.0)`` -> float
* ``assert_money_dict(d, *fields, allow_none=())`` -> None  (test helper)
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")


def as_money(value: Any, *, default: Decimal = ZERO) -> Decimal:
    """Coerce *value* to Decimal. None / blank string / unparseable -> *default*.

    Always returns a Decimal — never float, never int, never None. Use for
    monetary fields where 0 is a valid sentinel (e.g. ``current_drawdown``,
    ``daily_loss_used``, ``current_balance`` after bootstrap, ``l_t`` at SOD).

    Conversion uses ``Decimal(str(value))`` to avoid inheriting float bit
    patterns (``Decimal(0.1)`` vs ``Decimal("0.1")``).
    """
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def as_money_or_none(value: Any) -> Decimal | None:
    """Preserve NULL semantics for nullable monetary columns.

    Returns ``None`` only if the input is genuinely missing (``None`` or
    empty string). Use for columns where ``None`` has distinct semantics from
    0: ``max_drawdown_limit``, ``max_daily_loss``, ``profit_target``,
    ``l_star``. A Decimal value of zero stays ``Decimal("0")`` — it is NOT
    coerced to None.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def to_float(value: Any, *, default: float = 0.0) -> float:
    """Controlled escape hatch from Decimal into sizing/probabilistic math.

    Use ONLY at the function boundary into a sizing or statistical routine
    where float precision is sufficient (Kelly, percentage caps, Monte Carlo,
    EWMA, regime probabilities, GUI percentages displayed to 1 decimal place).
    Never in monetary state mutation paths (D03 writes, D08/D16 balance
    updates, ``l_t``/``l_b`` accumulators).

    None / unparseable -> *default*.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def assert_money_dict(
    d: dict,
    *money_fields: str,
    allow_none: tuple[str, ...] = (),
) -> None:
    """Test helper: assert every named field is Decimal (or None for nullable).

    Use in producer-side tests to verify type purity at the data ingestion
    boundary. Raises ``AssertionError`` with a descriptive message on the
    first violation.
    """
    for f in money_fields:
        v = d.get(f)
        if f in allow_none and v is None:
            continue
        assert isinstance(v, Decimal), (
            f"field {f!r} expected Decimal, got {type(v).__name__}: {v!r}"
        )
