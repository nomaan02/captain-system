# region imports
from AlgorithmImports import *
# endregion
"""Tests for pseudotrader account-type awareness (C1 gap resolution).

Validates that run_account_aware_replay enforces DLL, MDD, contract scaling,
trading hours, and consistency rules per TSM account config.
"""

import pytest
from unittest.mock import patch, MagicMock

# Mock shared.questdb_client before importing the module
import sys
sys.modules.setdefault("shared", MagicMock())
sys.modules.setdefault("shared.questdb_client", MagicMock())
sys.modules.setdefault("shared.journal", MagicMock())
_stats_mock = MagicMock()
_stats_mock.compute_pbo = MagicMock(return_value=0.3)
_stats_mock.compute_dsr = MagicMock(return_value=0.6)
sys.modules.setdefault("shared.statistics", _stats_mock)

from captain_offline.blocks.b3_pseudotrader import (
    _enforce_trading_hours,
    _lookup_scaling_tier,
    _check_dll,
    run_account_aware_replay,
)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestEnforceTradingHours:
    """Test trading hours enforcement."""

    def test_no_trading_hours_allows_all(self):
        assert _enforce_trading_hours("2026-03-16T10:00:00", None) is None
        assert _enforce_trading_hours("2026-03-16T10:00:00", {}) is None

    def test_trade_within_session_allowed(self):
        hours = {
            "session_open": "18:00 EST",
            "flat_by": "16:10 EST",
            "eod_exit_buffer": "15:55 EST",
        }
        # 10:00 AM is within session
        assert _enforce_trading_hours("2026-03-16T10:00:00", hours) is None

    def test_trade_after_eod_buffer_blocked(self):
        hours = {
            "session_open": "18:00 EST",
            "flat_by": "16:10 EST",
            "eod_exit_buffer": "15:55 EST",
        }
        # 15:56 is after 15:55 buffer
        result = _enforce_trading_hours("2026-03-16T15:56:00", hours)
        assert result == "AFTER_EOD_BUFFER"

    def test_trade_at_flat_by_blocked(self):
        hours = {
            "session_open": "18:00 EST",
            "flat_by": "16:10 EST",
            "eod_exit_buffer": "15:55 EST",
        }
        result = _enforce_trading_hours("2026-03-16T16:10:00", hours)
        # Should be blocked by either flat_by or eod_buffer
        assert result is not None

    def test_unparseable_timestamp_allowed(self):
        hours = {"flat_by": "16:10 EST"}
        assert _enforce_trading_hours("not-a-timestamp", hours) is None


class TestLookupScalingTier:
    """Test XFA scaling tier lookup."""

    SCALING_PLAN = [
        {"balance_threshold": 150000, "max_contracts": 3, "max_micros": 30},
        {"balance_threshold": 151500, "max_contracts": 4, "max_micros": 40},
        {"balance_threshold": 152000, "max_contracts": 5, "max_micros": 50},
        {"balance_threshold": 153000, "max_contracts": 10, "max_micros": 100},
        {"balance_threshold": 154500, "max_contracts": 15, "max_micros": 150},
    ]

    def test_starting_balance_tier_1(self):
        assert _lookup_scaling_tier(150000, 150000, self.SCALING_PLAN) == 30

    def test_above_tier_2_threshold(self):
        assert _lookup_scaling_tier(151600, 150000, self.SCALING_PLAN) == 40

    def test_max_tier(self):
        assert _lookup_scaling_tier(160000, 150000, self.SCALING_PLAN) == 150

    def test_between_tiers(self):
        # $152,500 is between tier 3 ($152k) and tier 4 ($153k)
        assert _lookup_scaling_tier(152500, 150000, self.SCALING_PLAN) == 50

    def test_empty_plan_returns_high(self):
        assert _lookup_scaling_tier(150000, 150000, []) == 999

    def test_none_plan_returns_high(self):
        assert _lookup_scaling_tier(150000, 150000, None) == 999


class TestCheckDLL:
    """Test daily loss limit check."""

    def test_no_dll_never_breaches(self):
        assert _check_dll(-5000, None) is False
        assert _check_dll(-5000, 0) is False

    def test_within_limit(self):
        assert _check_dll(-2999, 3000) is False

    def test_at_limit_breaches(self):
        assert _check_dll(-3000, 3000) is True

    def test_beyond_limit_breaches(self):
        assert _check_dll(-3500, 3000) is True

    def test_positive_pnl_never_breaches(self):
        assert _check_dll(1000, 3000) is False


# ---------------------------------------------------------------------------
# Account-aware replay tests
# ---------------------------------------------------------------------------

def _make_trades(daily_pnls, day_prefix="2026-03-"):
    """Create trade dicts from daily P&L values."""
    trades = []
    for i, pnl in enumerate(daily_pnls):
        day = f"{day_prefix}{i + 1:02d}"
        trades.append({
            "day": day,
            "pnl": pnl,
            "contracts": 1,
            "ts": f"{day}T10:00:00",
            "model": 4,
        })
    return trades


XFA_CONFIG = {
    "name": "Topstep 150K XFA",
    "classification": {"provider": "TopstepX", "category": "PROP_FUNDED", "stage": "XFA"},
    "starting_balance": 150000,
    "max_drawdown_limit": 4500,
    "max_daily_loss": 3000,
    "max_contracts": 15,
    "trading_hours": {
        "session_open": "18:00 EST",
        "flat_by": "16:10 EST",
        "eod_exit_buffer": "15:55 EST",
    },
    "scaling_plan_active": True,
    "scaling_plan": [
        {"balance_threshold": 150000, "max_contracts": 3, "max_micros": 30},
        {"balance_threshold": 154500, "max_contracts": 15, "max_micros": 150},
    ],
    "consistency_rule": {"max_daily_profit": 4500},
}

EVAL_CONFIG = {
    "name": "Topstep 150K Eval",
    "classification": {"provider": "TopstepX", "category": "PROP_EVAL", "stage": "STAGE_1"},
    "starting_balance": 150000,
    "profit_target": 9000,
    "max_drawdown_limit": 4500,
    "max_daily_loss": 3000,
    "max_contracts": 15,
}


@patch("captain_offline.blocks.b3_pseudotrader.get_cursor")
class TestAccountAwareReplay:
    """Test the full account-aware replay function."""

    def test_no_config_legacy_behavior(self, mock_cursor):
        """Without account_config, replay uses hardcoded $4,500 MDD only."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = _make_trades([100, -50, 200, -100, 150])
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, None)

        assert result["trading_days"] == 5
        assert result["dll_breaches"] == 0
        assert result["mdd_breach"] is False
        assert result["account_type"] == "UNKNOWN"

    def test_dll_halts_day(self, mock_cursor):
        """DLL breach stops remaining trades on that day."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Two trades on same day: first loses $3001, second should be blocked
        trades = [
            {"day": "2026-03-01", "pnl": -3001, "contracts": 1, "ts": "2026-03-01T09:30:00", "model": 4},
            {"day": "2026-03-01", "pnl": 500, "contracts": 1, "ts": "2026-03-01T10:00:00", "model": 4},
        ]
        config = {**XFA_CONFIG}
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, config)

        assert result["dll_breaches"] == 1
        assert result["total_trades_blocked"] >= 1

    def test_mdd_breach_halts_permanently(self, mock_cursor):
        """MDD breach stops all subsequent trading."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Consecutive losses totaling $4500+
        trades = _make_trades([-1500, -1500, -1500, -500, 200])
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, XFA_CONFIG)

        assert result["mdd_breach"] is True
        assert result["mdd_breach_day"] is not None

    def test_scaling_cap_reduces_pnl(self, mock_cursor):
        """Trades exceeding scaling tier get size-reduced."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # At starting balance, tier 1 = 30 micros (3 minis)
        # Trade with 5 contracts (50 micros) exceeds tier
        trades = [
            {"day": "2026-03-01", "pnl": 1000, "contracts": 5, "ts": "2026-03-01T10:00:00", "model": 4},
        ]
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, XFA_CONFIG)

        assert result["scaling_cap_hits"] == 1
        # P&L should be scaled down: 1000 * (30/50) = 600
        assert result["net_pnl"] == pytest.approx(600.0, abs=1.0)

    def test_consistency_violation_flagged(self, mock_cursor):
        """Day exceeding max daily profit gets flagged."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Single day with $5000 profit exceeds $4500 consistency rule
        trades = _make_trades([5000, 100])
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, XFA_CONFIG)

        assert result["consistency_violations"] == 1

    def test_trading_hours_block(self, mock_cursor):
        """Trades outside trading hours get blocked."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = [
            {"day": "2026-03-01", "pnl": 500, "contracts": 1, "ts": "2026-03-01T15:56:00", "model": 4},
            {"day": "2026-03-01", "pnl": 200, "contracts": 1, "ts": "2026-03-01T10:00:00", "model": 4},
        ]
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, XFA_CONFIG)

        assert result["trading_hours_blocks"] >= 1

    def test_eval_pass(self, mock_cursor):
        """PROP_EVAL account reaching profit target shows PASS."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # 10 days of $1000 = $10,000 profit > $9,000 target
        trades = _make_trades([1000] * 10)
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, EVAL_CONFIG)

        assert result["eval_result"] == "PASS"

    def test_eval_fail_mdd(self, mock_cursor):
        """PROP_EVAL account breaching MDD shows FAIL_MDD."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = _make_trades([-2000, -2000, -1000])
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, EVAL_CONFIG)

        assert result["eval_result"] == "FAIL_MDD"

    def test_bankruptcy_halts_replay(self, mock_cursor):
        """G-OFF-020: Balance hitting zero stops replay immediately."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Starting balance 150k, one massive loss wipes it out
        config = {**EVAL_CONFIG, "max_drawdown_limit": None}
        trades = _make_trades([-200000, 500])
        result = run_account_aware_replay("ES", "MODEL_RETRAIN", trades, config)

        assert result["bankruptcy"] is True
        assert result["bankruptcy_day"] is not None
        # Second trade should not have been taken
        assert result["total_trades_taken"] == 1


# ---------------------------------------------------------------------------
# CB pseudotrader account constraint tests (G-OFF-021)
# ---------------------------------------------------------------------------

from captain_offline.blocks.b3_pseudotrader import run_cb_pseudotrader


CB_PARAMS = {"p": 0.02, "e": 0.05, "c": 0.5, "lambda_threshold": 0.0,
             "account_balance": 150000, "mdd": 4500}

BASKET_PARAMS = {"4": {"r_bar": 10.0, "beta_b": 0.0, "sigma": 1.0, "rho_bar": 0.0}}


@patch("captain_offline.blocks.b3_pseudotrader._compute_dsr", return_value=0.6)
@patch("captain_offline.blocks.b3_pseudotrader._compute_pbo", return_value=0.3)
@patch("captain_offline.blocks.b3_pseudotrader.get_cursor")
class TestCBPseudotraderAccountConstraints:
    """Test CB pseudotrader with account constraints (G-OFF-021)."""

    def test_no_account_config_unconstrained(self, mock_cursor, _pbo, _dsr):
        """Without account_config, CB replay applies only CB layers."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = _make_trades([500, 300, -200])
        result = run_cb_pseudotrader("acc1", trades, CB_PARAMS, BASKET_PARAMS)

        assert result["total_taken"] == 3
        assert "dsr" in result  # G-OFF-023: DSR should be computed

    def test_dll_blocks_in_cb_replay(self, mock_cursor, _pbo, _dsr):
        """DLL from account_config blocks trades in CB replay."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Two trades on same day: first loses $2500, second should be blocked by DLL=$3000
        trades = [
            {"day": "2026-03-01", "pnl": -2500, "contracts": 1, "ts": "2026-03-01T10:00:00", "model": 4},
            {"day": "2026-03-01", "pnl": -600, "contracts": 1, "ts": "2026-03-01T10:30:00", "model": 4},
            {"day": "2026-03-01", "pnl": 200, "contracts": 1, "ts": "2026-03-01T11:00:00", "model": 4},
        ]
        result = run_cb_pseudotrader("acc1", trades, CB_PARAMS, BASKET_PARAMS,
                                      account_config=XFA_CONFIG)

        # After -2500, daily_pnl = -2500. Then -600 would push to -3100 >= -3000 DLL.
        # The second trade's daily_pnl check: daily_pnl=-2500, -2500 <= -3000 is False.
        # The third trade after -3100: -3100 <= -3000 is True, blocked.
        assert result["total_blocked"] > 0

    def test_mdd_breach_halts_cb_replay(self, mock_cursor, _pbo, _dsr):
        """MDD breach from account_config stops CB replay permanently."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Losses exceeding MDD across days
        trades = _make_trades([-2000, -2000, -1000, 500])
        result = run_cb_pseudotrader("acc1", trades, CB_PARAMS, BASKET_PARAMS,
                                      account_config=XFA_CONFIG)

        # MDD = 4500: after day1 -2000, day2 -2000 = 4000 drawdown, day3 -1000 = 5000 > 4500
        assert "ACCOUNT_MDD_BREACH" in result.get("blocks_by_reason", {})

    def test_dsr_computed_not_zero(self, mock_cursor, _pbo, mock_dsr):
        """G-OFF-023: DSR should be computed, not hardcoded to 0."""
        mock_cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = _make_trades([500, 300, 200, 100, -50, 400, 350])
        result = run_cb_pseudotrader("acc1", trades, CB_PARAMS, BASKET_PARAMS)

        assert "dsr" in result
        assert isinstance(result["dsr"], float)
        # Verify _compute_dsr was actually called (not hardcoded)
        mock_dsr.assert_called()


# ---------------------------------------------------------------------------
# Per-account iteration tests (G-OFF-019)
# ---------------------------------------------------------------------------

from captain_offline.blocks.b3_pseudotrader import (
    fetch_active_accounts,
    run_pseudotrader_all_accounts,
)


@patch("captain_offline.blocks.b3_pseudotrader._compute_dsr", return_value=0.6)
@patch("captain_offline.blocks.b3_pseudotrader._compute_pbo", return_value=0.3)
@patch("captain_offline.blocks.b3_pseudotrader.get_cursor")
class TestPerAccountIteration:
    """Test per-account-type iteration from D08 (G-OFF-019)."""

    def test_no_active_accounts_fallback(self, mock_cursor, _pbo, _dsr):
        """With no D08 accounts, falls back to unconstrained replay."""
        cursor_mock = MagicMock()
        cursor_mock.execute.side_effect = Exception("no table")
        mock_cursor.return_value.__enter__ = MagicMock(return_value=cursor_mock)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = _make_trades([500, 300])
        result = run_pseudotrader_all_accounts("ES", "MODEL_RETRAIN", trades)

        assert result["accounts_tested"] == 0
        assert len(result["per_account"]) == 1  # fallback single run

    def test_multiple_accounts_iteration(self, mock_cursor, _pbo, _dsr):
        """Each active account gets its own replay."""
        cursor_mock = MagicMock()

        # Mock two active accounts
        cursor_mock.description = [
            ("account_id",), ("account_name",), ("current_balance",),
            ("starting_balance",), ("max_drawdown_limit",), ("max_daily_loss",),
            ("profit_target",), ("status",), ("classification",), ("scaling_plan",),
            ("consistency_rule",), ("trading_hours",), ("capital_unlock",),
        ]
        cursor_mock.fetchall.return_value = [
            ("acc1", "XFA Account", 155000, 150000, 4500, 3000,
             None, "ACTIVE", '{"category": "PROP_FUNDED"}', None, None, None, None),
            ("acc2", "Eval Account", 150000, 150000, 4500, 3000,
             9000, "ACTIVE", '{"category": "PROP_EVAL"}', None, None, None, None),
        ]
        mock_cursor.return_value.__enter__ = MagicMock(return_value=cursor_mock)
        mock_cursor.return_value.__exit__ = MagicMock(return_value=False)

        trades = _make_trades([500, 300, -100])
        result = run_pseudotrader_all_accounts("ES", "MODEL_RETRAIN", trades)

        assert result["accounts_tested"] == 2
        assert len(result["per_account"]) == 2
        assert all("account_recommendation" in r for r in result["per_account"])
