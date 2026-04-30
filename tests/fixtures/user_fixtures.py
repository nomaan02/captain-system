# region imports
from AlgorithmImports import *
# endregion
"""User, account, TSM, and capital silo fixtures for regression tests."""

import json


from decimal import Decimal


def make_user_silo(user_id="primary_user",
                   starting_capital: Decimal | None = None,
                   total_capital: Decimal | None = None,
                   accounts=None, **overrides):
    """Capital silo for a user."""
    if starting_capital is None:
        starting_capital = Decimal("100000.00")
    if total_capital is None:
        total_capital = Decimal("95000.00")
    if accounts is None:
        accounts = ["acc_eval_1"]
    base = {
        "user_id": user_id,
        "starting_capital": starting_capital,
        "total_capital": total_capital,
        "accounts": json.dumps(accounts),
        "user_kelly_ceiling": 1.0,
        "max_portfolio_risk_pct": 0.10,
        "correlation_threshold": 0.7,
    }
    base.update(overrides)
    return base


def make_tsm_config(account_id="acc_eval_1", category="PROP_EVAL",
                    balance=50_000.0, **overrides):
    """TSM config for one account."""
    base = {
        "name": f"Topstep {account_id}",
        "classification": {"category": category},
        "current_balance": balance,
        "max_drawdown_limit": 2000.0,  # Topstep $50k eval (calibrated from P1 data)
        "current_drawdown": 0.0,
        "max_daily_loss": 1000.0,
        "daily_loss_used": 0.0,
        "max_contracts": 10,
        "risk_goal": "GROW_CAPITAL",
        "topstep_optimisation": True,
        "scaling_plan_active": False,
        "scaling_plan": None,
        "fee_schedule": json.dumps({
            "fees_by_instrument": {"ES": {"round_turn": 7.12}},
            "default_round_turn": 7.12,
        }),
        "commission_per_contract": 3.56,
        "instrument_permissions": [],
        "pass_probability": 0.65,
        "topstep_params": json.dumps({
            "daily_contract_cap": 10,
            "p": 0.005,
            "e": 0.01,
            "c": 0.5,
            "lambda": 0,
        }),
    }
    base.update(overrides)
    # Phase 1B/3 (F-03/F-07/F-08): mirror SOD-frozen state into D08.topstep_state.
    # Computed from the post-override topstep_params + current_balance so that
    # B5C's SOD-preferred path produces the same numeric outcome as its
    # cold-start fallback (i.e. existing L1/L2 tests stay green).
    if "topstep_state" not in overrides:
        try:
            tp = json.loads(base.get("topstep_params") or "{}")
        except (json.JSONDecodeError, TypeError):
            tp = {}
        c = tp.get("c", 0.5)
        e = tp.get("e", 0.01)
        # Test fixture: float bal is fine here because c, e are plain floats
        # (test scenario constants). Production code uses Decimal end-to-end
        # via shared.decimal_boundary.as_money — see b8_reconciliation.
        bal_raw = base.get("current_balance", 0.0)
        bal = float(bal_raw) if bal_raw is not None else 0.0  # decimal-boundary: ok (test fixture)
        base["topstep_state"] = json.dumps({
            "computed_sod": {
                "L_halt": c * e * bal,
                "E_daily_exposure": e * bal,
                "computed_at": "1970-01-01T00:00:00Z",
            },
        })
    return base


def make_tsm_configs(accounts=None, **overrides):
    """Dict of account_id -> TSM config."""
    if accounts is None:
        accounts = ["acc_eval_1"]
    return {ac: make_tsm_config(account_id=ac, **overrides) for ac in accounts}


def make_silo_drawdown_blocked(user_id="primary_user"):
    """Silo with >30% drawdown -> should be BLOCKED."""
    return make_user_silo(
        user_id=user_id,
        starting_capital=Decimal("100000.00"),
        total_capital=Decimal("65000.00"),  # 35% drawdown
    )


def make_tsm_pass_eval(account_id="acc_eval_1"):
    """TSM with PASS_EVAL risk goal."""
    return make_tsm_config(
        account_id=account_id,
        risk_goal="PASS_EVAL",
    )


def make_tsm_mdd_tight(account_id="acc_eval_1"):
    """TSM with very tight MDD headroom — only 1 contract possible."""
    return make_tsm_config(
        account_id=account_id,
        max_drawdown_limit=500.0,
        current_drawdown=300.0,  # remaining = $200, SL*pv = 4*50 = $200 -> 1 contract
    )
