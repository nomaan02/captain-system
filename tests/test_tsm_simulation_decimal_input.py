"""Phase 2 regression: b7_tsm_simulation accepts Decimal-typed D08 config.

Pre-fix, run_tsm_simulation passed D08 monetary fields straight into
_simulate_one_path's float arithmetic. After Phase A migration those
fields arrive as Decimal — `sim_balance += ret` raised TypeError on the
first inner-loop iteration. The fix coerces to float at the explicit
boundary inside run_tsm_simulation.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _stub_writers(monkeypatch):
    """Stub the QuestDB write + Redis publish + RPT-07 paths."""
    from captain_offline.blocks import b7_tsm_simulation as mod
    monkeypatch.setattr(mod, "_write_pass_probability",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(mod, "_generate_rpt07",
                        lambda *args, **kwargs: None)
    yield


def _decimal_tsm_config():
    return {
        "starting_balance": Decimal("150000.00"),
        "current_balance": Decimal("150000.00"),
        "max_drawdown_limit": Decimal("3000.00"),
        "max_daily_loss": Decimal("1500.00"),
        "profit_target": Decimal("9000.00"),
        "risk_goal": "PASS_EVAL",
    }


class TestDecimalConfigDoesNotTypeError:
    def test_decimal_config_runs_to_completion(self):
        from captain_offline.blocks.b7_tsm_simulation import (
            run_tsm_simulation,
        )
        # 50 mild positive returns — runs cleanly through MC inner loop
        trade_returns = [50.0] * 50
        result = run_tsm_simulation(
            account_id="AC1",
            trade_returns=trade_returns,
            tsm_config=_decimal_tsm_config(),
        )
        assert result["pass_probability"] is not None
        assert 0.0 <= result["pass_probability"] <= 1.0

    def test_decimal_config_with_unconstrained_account(self):
        """No mdd_limit and no mll_limit → pass_probability=None per spec."""
        from captain_offline.blocks.b7_tsm_simulation import (
            run_tsm_simulation,
        )
        cfg = _decimal_tsm_config()
        cfg["max_drawdown_limit"] = None
        cfg["max_daily_loss"] = None
        result = run_tsm_simulation(
            account_id="AC1",
            trade_returns=[10.0] * 50,
            tsm_config=cfg,
        )
        assert result["pass_probability"] is None

    def test_mixed_int_decimal_config(self):
        """Defensive: integer literals from older fixtures still work."""
        from captain_offline.blocks.b7_tsm_simulation import (
            run_tsm_simulation,
        )
        cfg = {
            "starting_balance": 150000,        # int (legacy fixture)
            "current_balance": Decimal("150000.00"),
            "max_drawdown_limit": Decimal("3000.00"),
            "max_daily_loss": 1500,            # int
            "profit_target": Decimal("9000.00"),
            "risk_goal": "PASS_EVAL",
        }
        result = run_tsm_simulation(
            account_id="AC1",
            trade_returns=[20.0] * 50,
            tsm_config=cfg,
        )
        assert result["pass_probability"] is not None


class TestSizingOverrideWithDecimalConfig:
    def test_decay_sizing_factor_does_not_typeerror(self):
        from captain_offline.blocks.b7_tsm_simulation import (
            run_tsm_simulation,
        )
        result = run_tsm_simulation(
            account_id="AC1",
            trade_returns=[30.0] * 50,
            tsm_config=_decimal_tsm_config(),
            sizing_override=0.5,
        )
        assert result["pass_probability"] is not None
