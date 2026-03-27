# region imports
from AlgorithmImports import *
# endregion
"""User, account, TSM, and capital silo fixtures for regression tests."""

import json


def make_user_silo(user_id="primary_user", starting_capital=100_000.0,
                   total_capital=95_000.0, accounts=None, **overrides):
    """Capital silo for a user."""
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
        starting_capital=100_000.0,
        total_capital=65_000.0,  # 35% drawdown
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
