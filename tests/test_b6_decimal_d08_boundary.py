"""Regression test: b6_signal_output._build_per_account against Decimal D08.

Reproduces the exact NY-open 2026-04-30 failure mode:

    captain-online-1  | TypeError: unsupported operand type(s) for -:
                        'decimal.Decimal' and 'float'
    captain-online-1  |   File "b6_signal_output.py", line 332, in _build_per_account
    captain-online-1  |     "remaining_mdd": (mdd_limit - current_dd) ...

After the fix, _build_per_account coerces every D08 monetary field via
shared.decimal_boundary so the arithmetic is Decimal end-to-end and the
exact-zero `current_drawdown` boundary case (fresh account, post daily
reset) no longer trips TypeError.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from captain_online.blocks.b6_signal_output import _build_per_account


def _tsm_dict(**overrides):
    """Realistic Phase-A-migrated TSM dict (all monetary fields Decimal)."""
    base = {
        "name": "TestAccount",
        "classification": {"category": "PROP_EVAL"},
        "risk_goal": "PASS_EVAL",
        "starting_balance": Decimal("150000.00"),
        "current_balance": Decimal("150000.00"),
        "current_drawdown": Decimal("0.00"),
        "daily_loss_used": Decimal("0.00"),
        "max_drawdown_limit": Decimal("3000.00"),
        "max_daily_loss": Decimal("1500.00"),
        "profit_target": Decimal("9000.00"),
        "commission_per_contract": Decimal("2.80"),
        "pass_probability": 0.65,
        "api_validated": True,
    }
    base.update(overrides)
    return base


class TestBuildPerAccountFreshAccount:
    """The exact NY-open failure mode: zero drawdown + zero daily_loss_used."""

    def test_fresh_account_zero_drawdown(self):
        """Decimal('0.00') current_drawdown must NOT TypeError on subtraction."""
        tsm_configs = {"AC1": _tsm_dict()}
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 3}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )

        ac = out["AC1"]
        assert ac["remaining_mdd"] == Decimal("3000.00")
        assert ac["remaining_mll"] == Decimal("1500.00")
        assert ac["risk_budget_pct"] == 0.0
        assert ac["contracts"] == 3
        assert ac["recommendation"] == "TRADE"

    def test_partial_drawdown(self):
        """Non-zero drawdown -> remaining shrinks correctly."""
        tsm_configs = {
            "AC1": _tsm_dict(
                current_drawdown=Decimal("750.00"),
                daily_loss_used=Decimal("250.00"),
            )
        }
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 2}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )

        ac = out["AC1"]
        assert ac["remaining_mdd"] == Decimal("2250.00")
        assert ac["remaining_mll"] == Decimal("1250.00")
        # 250 / 1500 * 100 = 16.666...
        assert ac["risk_budget_pct"] == pytest.approx(16.6666666666, rel=1e-6)


class TestBuildPerAccountNullableFields:
    """BROKER_LIVE accounts have NULL max_drawdown_limit / max_daily_loss."""

    def test_null_mdd_limit_returns_none(self):
        tsm_configs = {"AC1": _tsm_dict(max_drawdown_limit=None)}
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 1}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )
        assert out["AC1"]["remaining_mdd"] is None

    def test_null_mll_returns_none(self):
        tsm_configs = {"AC1": _tsm_dict(max_daily_loss=None)}
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 1}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )
        assert out["AC1"]["remaining_mll"] is None
        assert out["AC1"]["risk_budget_pct"] is None


class TestBuildPerAccountTypeMixedDictDefence:
    """Defensive coercion: even if a producer regresses to type-mixed dict,
    _build_per_account still works because it re-coerces at the boundary."""

    def test_float_drawdown_with_decimal_limit(self):
        """The exact bug shape: max_drawdown_limit=Decimal, current_drawdown=float."""
        tsm_configs = {
            "AC1": _tsm_dict(
                current_drawdown=0.0,  # float (the bug)
                daily_loss_used=0.0,   # float (the bug)
            )
        }
        # Should not raise TypeError
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 1}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )
        assert out["AC1"]["remaining_mdd"] == Decimal("3000.00")

    def test_int_zero_inputs(self):
        tsm_configs = {
            "AC1": _tsm_dict(
                current_drawdown=0,
                daily_loss_used=0,
            )
        }
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1"],
            final_contracts={"MES": {"AC1": 1}},
            account_recommendation={"MES": {"AC1": "TRADE"}},
            account_skip_reason={},
            tsm_configs=tsm_configs,
        )
        assert out["AC1"]["remaining_mdd"] == Decimal("3000.00")


class TestBuildPerAccountMultipleAccounts:
    def test_three_accounts_one_blocked(self):
        tsm_configs = {
            "AC1": _tsm_dict(),
            "AC2": _tsm_dict(current_drawdown=Decimal("2900.00")),  # near MDD
            "AC3": _tsm_dict(max_drawdown_limit=None),  # broker live
        }
        out = _build_per_account(
            asset_id="MES",
            accounts=["AC1", "AC2", "AC3"],
            final_contracts={"MES": {"AC1": 3, "AC2": 0, "AC3": 1}},
            account_recommendation={
                "MES": {"AC1": "TRADE", "AC2": "BLOCKED", "AC3": "TRADE"}
            },
            account_skip_reason={"MES": {"AC2": "Near MDD"}},
            tsm_configs=tsm_configs,
        )
        assert out["AC1"]["remaining_mdd"] == Decimal("3000.00")
        assert out["AC2"]["remaining_mdd"] == Decimal("100.00")
        assert out["AC2"]["skip_reason"] == "Near MDD"
        assert out["AC3"]["remaining_mdd"] is None
