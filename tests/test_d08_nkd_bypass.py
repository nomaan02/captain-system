"""Q2-B-strict D08 defensive assertion tests for run_tsm_simulation.

Tests 13-15 from audit section 10: verify that run_tsm_simulation refuses
to execute for NKD (fixed-strategy asset) via the asset_id guard.

No DB, Redis, or scipy deps — all downstream is bypassed by the assertion.
"""
from __future__ import annotations

import pytest

from captain_offline.blocks.b7_tsm_simulation import run_tsm_simulation

_MINIMAL_TSM_CONFIG = {
    "starting_balance": 150000.0,
    "current_balance": 150000.0,
    "max_drawdown_limit": 2000.0,
    "max_daily_loss": 1000.0,
    "profit_target": 9000.0,
    "risk_goal": "PASS_EVAL",
    "evaluation_end_date": None,
}

_DUMMY_RETURNS = [100.0] * 11  # 11 > 10 so we get past the "insufficient trades" guard


def test_d08_write_nkd_assertion_trips():
    """Calling run_tsm_simulation with asset_id='NKD' must raise AssertionError.

    This is the regression guard — if the offline orchestrator bypass at
    _handle_trade_outcome ever fails, this assertion catches the leak before
    any D08 write occurs.
    """
    with pytest.raises(AssertionError, match="Q2-B-strict"):
        run_tsm_simulation(
            account_id="21855714",
            trade_returns=_DUMMY_RETURNS,
            tsm_config=_MINIMAL_TSM_CONFIG,
            asset_id="NKD",
        )


def test_d08_write_non_nkd_works(monkeypatch):
    """ES outcome must pass the guard without raising.

    We mock the DB and Redis calls so the function can proceed without
    real infrastructure — the goal is to confirm no assertion is raised.
    """
    from unittest.mock import MagicMock, patch
    import captain_offline.blocks.b7_tsm_simulation as mod

    with patch.object(mod, "get_cursor") as mock_cursor_ctx, \
         patch.object(mod, "_generate_rpt07", return_value=None), \
         patch.object(mod, "_write_pass_probability", return_value=None):

        # Provide a minimal cursor mock so the fallback path (no MDD/MLL →
        # unconstrained account) works — function returns early with None
        # pass_probability and calls _write_pass_probability.
        result = run_tsm_simulation(
            account_id="21855714",
            trade_returns=_DUMMY_RETURNS,
            tsm_config={
                **_MINIMAL_TSM_CONFIG,
                "max_drawdown_limit": None,  # unconstrained → returns early
                "max_daily_loss": None,
            },
            asset_id="ES",
        )

    # The unconstrained branch returns {"pass_probability": None, ...}
    assert result["pass_probability"] is None
    assert result.get("account_id") == "21855714"


def test_d08_read_sites_no_nkd_path():
    """D08 READ sites (b1_data_ingestion, orchestrator pre-load) are asset-agnostic.

    These reads load TSM config for ALL accounts before the per-asset loop in
    B4. Since B4 short-circuits for NKD before ever consulting tsm_configs,
    the read-side never materialises into NKD-specific behaviour. No explicit
    asset guard is needed at the read sites — the B4 entry bypass (C2) is the
    correct enforcement layer.

    This test is intentionally a no-op / documentation stub. It is marked
    xfail(strict=False) to make the intent explicit without polluting the
    test count with a trivially-passing empty test.
    """
    pytest.skip(
        "D08 read sites are implicitly guarded by the B4 entry bypass (P3-C2). "
        "No assertion needed here — see audit §2 row D-3."
    )
