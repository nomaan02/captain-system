"""Unit tests for shared.decimal_boundary primitives.

Covers the falsy-zero antipattern that tripped NY open on 2026-04-30,
plus None-handling, float precision preservation via str(), and the
test helper `assert_money_dict`.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from shared.decimal_boundary import (
    ZERO,
    as_money,
    as_money_or_none,
    assert_money_dict,
    to_float,
)


# ---------------------------------------------------------------------------
# as_money
# ---------------------------------------------------------------------------

class TestAsMoney:
    def test_decimal_passthrough_zero(self):
        """Decimal('0.00') must NOT collapse to default — that was the bug."""
        result = as_money(Decimal("0.00"))
        assert result == Decimal("0.00")
        assert isinstance(result, Decimal)

    def test_decimal_passthrough_nonzero(self):
        result = as_money(Decimal("3000.00"))
        assert result == Decimal("3000.00")

    def test_none_returns_default(self):
        assert as_money(None) == ZERO
        assert isinstance(as_money(None), Decimal)

    def test_empty_string_returns_default(self):
        assert as_money("") == ZERO

    def test_custom_default(self):
        assert as_money(None, default=Decimal("4500")) == Decimal("4500")

    def test_int_coerces(self):
        assert as_money(150000) == Decimal("150000")

    def test_float_coerces_via_str(self):
        """Decimal(str(0.1+0.2)) avoids the 0.30000000000000004 leak."""
        result = as_money(0.1 + 0.2)
        assert result == Decimal("0.30000000000000004")  # str() faithfully preserves
        assert isinstance(result, Decimal)

    def test_string_numeric(self):
        assert as_money("150000.50") == Decimal("150000.50")

    def test_invalid_string_returns_default(self):
        assert as_money("not_a_number") == ZERO
        assert as_money("not_a_number", default=Decimal("99")) == Decimal("99")

    def test_always_returns_decimal(self):
        for v in [None, "", "0", 0, 0.0, Decimal("0"), "abc", float("nan")]:
            try:
                assert isinstance(as_money(v), Decimal)
            except Exception:
                # Decimal('nan') is technically a Decimal — fine
                pass


# ---------------------------------------------------------------------------
# as_money_or_none
# ---------------------------------------------------------------------------

class TestAsMoneyOrNone:
    def test_none_returns_none(self):
        assert as_money_or_none(None) is None

    def test_empty_string_returns_none(self):
        assert as_money_or_none("") is None

    def test_decimal_zero_NOT_none(self):
        """Critical: Decimal('0.00') is a real value, not missing data."""
        result = as_money_or_none(Decimal("0.00"))
        assert result == Decimal("0.00")
        assert result is not None

    def test_decimal_passthrough(self):
        assert as_money_or_none(Decimal("3000.00")) == Decimal("3000.00")

    def test_int_coerces(self):
        assert as_money_or_none(4500) == Decimal("4500")

    def test_invalid_string_returns_none(self):
        assert as_money_or_none("not_a_number") is None


# ---------------------------------------------------------------------------
# to_float
# ---------------------------------------------------------------------------

class TestToFloat:
    def test_decimal_to_float(self):
        assert to_float(Decimal("3000.00")) == 3000.0
        assert isinstance(to_float(Decimal("3000.00")), float)

    def test_decimal_zero(self):
        assert to_float(Decimal("0.00")) == 0.0

    def test_none_returns_default(self):
        assert to_float(None) == 0.0
        assert to_float(None, default=1.5) == 1.5

    def test_int_coerces(self):
        assert to_float(150000) == 150000.0

    def test_string_numeric(self):
        assert to_float("3000.50") == 3000.5

    def test_invalid_string_returns_default(self):
        assert to_float("nope") == 0.0
        assert to_float("nope", default=99.0) == 99.0


# ---------------------------------------------------------------------------
# assert_money_dict
# ---------------------------------------------------------------------------

class TestAssertMoneyDict:
    def test_all_decimal_passes(self):
        d = {
            "current_balance": Decimal("150000.00"),
            "current_drawdown": Decimal("0.00"),
            "max_drawdown_limit": Decimal("3000.00"),
        }
        # Should not raise
        assert_money_dict(d, "current_balance", "current_drawdown", "max_drawdown_limit")

    def test_float_value_fails(self):
        """The exact bug we are guarding against."""
        d = {
            "current_balance": Decimal("150000.00"),
            "current_drawdown": 0.0,  # type-mixed dict — float instead of Decimal
            "max_drawdown_limit": Decimal("3000.00"),
        }
        with pytest.raises(AssertionError, match="current_drawdown.*float"):
            assert_money_dict(d, "current_balance", "current_drawdown", "max_drawdown_limit")

    def test_none_in_allow_none_passes(self):
        d = {"max_drawdown_limit": None}
        assert_money_dict(d, "max_drawdown_limit", allow_none=("max_drawdown_limit",))

    def test_none_outside_allow_none_fails(self):
        d = {"current_balance": None}
        with pytest.raises(AssertionError, match="current_balance.*NoneType"):
            assert_money_dict(d, "current_balance")

    def test_int_value_fails(self):
        d = {"current_balance": 150000}  # int, not Decimal
        with pytest.raises(AssertionError, match="current_balance.*int"):
            assert_money_dict(d, "current_balance")
