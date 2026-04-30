"""Regression test for b8_reconciliation SOD computation signature bug.

PRODUCTION FAILURE (2026-04-30 19:00 EDT)
-----------------------------------------
At the daily 19:00 EDT reconciliation trigger:

    ERROR captain_command.blocks.b8_reconciliation:
        SOD Topstep computation failed for 20319811:
        parse_json_decimal() missing 1 required positional argument: 'default'
    File "/app/captain_command/blocks/b8_reconciliation.py", line 232
        fee_schedule = parse_json_decimal(ac.get("fee_schedule", "{}") or "{}")

ROOT CAUSE
----------
parse_json_decimal() requires two positional arguments: (raw, default).
Three of the four parse calls in _compute_sod_topstep_params passed `, {}`
as the default. The fourth (fee_schedule) was missing the default argument,
raising TypeError. The bare `try/except Exception` caught it, logged it,
and aborted the SOD computation for that account — meaning
topstep_state.computed_sod was never updated and L1/L2 circuit breaker
fall back to live computation on the next session.

Trading impact: low (live fallback produces the same numerical result as
the SOD-frozen value when balance is stable). Logging impact: a CRITICAL
error every 24h that hides real failures.

FIX
---
Add the missing `, {}` default argument to the fourth call.

This test pins the SIGNATURE invariant: every parse_json_decimal call
in b8_reconciliation must be invocable with the runtime arguments it
gets. We exercise the actual function with real production-shape inputs.
"""
from __future__ import annotations

import inspect

from shared.json_helpers import parse_json_decimal


def test_parse_json_decimal_signature_is_two_positional_args():
    """The function signature MUST stay as (raw, default) — two positional args."""
    sig = inspect.signature(parse_json_decimal)
    params = list(sig.parameters.values())
    assert len(params) == 2, (
        f"parse_json_decimal signature changed unexpectedly. "
        f"Expected 2 positional args (raw, default); got {len(params)}: "
        f"{[p.name for p in params]}"
    )
    assert params[0].name == "raw"
    assert params[1].name == "default"
    # Both must be REQUIRED (no defaults at the function level — callers must pass)
    assert params[0].default is inspect.Parameter.empty
    assert params[1].default is inspect.Parameter.empty


def test_b8_reconciliation_sod_call_sites_pass_default():
    """All four parse_json_decimal calls in _compute_sod_topstep_params
    must pass the required default argument."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / (
        "captain-command/captain_command/blocks/b8_reconciliation.py"
    )
    contents = src.read_text(encoding="utf-8")

    # Find all parse_json_decimal call sites
    # Pattern: parse_json_decimal(<arg1>, <arg2>) — must have the comma+default
    # Bug shape: parse_json_decimal(<single_arg>) — TypeError at runtime
    bad_pattern = re.compile(
        r"parse_json_decimal\(\s*[^,)]+\s*\)",  # one arg only, no default
        re.MULTILINE,
    )
    matches = bad_pattern.findall(contents)
    assert not matches, (
        f"Found parse_json_decimal call(s) missing the `default` argument "
        f"(would raise TypeError at runtime):\n  " + "\n  ".join(matches)
    )


def test_compute_sod_topstep_params_runs_without_signature_error(monkeypatch):
    """Smoke test: invoke _compute_sod_topstep_params with the production
    account-dict shape and verify it does NOT raise the parse_json_decimal
    TypeError that fired at 19:00 EDT 2026-04-30."""
    from captain_command.blocks import b8_reconciliation as b8

    # Stub the persist call so we don't touch QuestDB
    monkeypatch.setattr(
        b8, "_persist_topstep_state_to_d08",
        lambda ac_id, json_str: None,
    )
    monkeypatch.setattr(
        b8, "_check_payout_recommendation",
        lambda *args, **kwargs: None,
    )

    # Production account dict shape (what b1_data_ingestion._load_tsm_configs returns
    # AFTER Phase 1, and what b8_reconciliation.run_daily_reconciliation passes in)
    ac = {
        "account_id": "20319811",
        "user_id": "primary_user",
        "current_balance": "150000.00",
        "starting_balance": "150000.00",
        "max_drawdown_limit": "3000.00",
        "topstep_state": "{}",
        "topstep_params": '{"c": 0.5, "e": 0.01, "p": 0.005}',
        "payout_rules": "{}",
        "fee_schedule": '{"fees_by_instrument": {"ES": {"round_turn": 3.85}}}',
        "scaling_plan_active": False,
    }

    # Capture log calls
    pushes = []
    def gui_push(user_id, msg):
        pushes.append((user_id, msg))

    # Should NOT raise; should NOT log the parse_json_decimal TypeError
    b8._compute_sod_topstep_params(
        ac_id="20319811", user_id="primary_user", ac=ac,
        gui_push_fn=gui_push, notify_fn=None,
    )
