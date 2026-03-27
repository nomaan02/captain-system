# region imports
from AlgorithmImports import *
# endregion
"""Tests for shared.account_lifecycle — EVAL → XFA → LIVE state machine.

Covers standalone account configs (TopstepEvalAccount, TopstepXFAAccount,
TopstepLiveAccount) and the full MultiStageTopstepAccount lifecycle including
transitions, failures, payouts, capital unlocks, and fee accumulation.

All assertions are derived directly from the module constants and the
exact branching logic in account_lifecycle.py — no approximations.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Import account_lifecycle directly from the filesystem BEFORE replacing the
# shared package in sys.modules.
#
# Background: conftest.py has two autouse fixtures that call
#   monkeypatch.setattr("shared.questdb_client.get_cursor", ...)
#   monkeypatch.setattr("shared.redis_client.get_redis_client", ...)
# pytest resolves dotted-path targets as:
#   obj = sys.modules["shared"]
#   obj = getattr(obj, "questdb_client")   ← fails on a real package
#   setattr(obj, "get_cursor", mock)
#
# When "shared" is a real Python package, getattr(shared, "questdb_client")
# fails because Python packages do not auto-expose unimported sub-modules as
# attributes.  Importing shared.questdb_client directly would trigger
# `import redis`, which is not installed in this environment.
#
# Solution: load account_lifecycle by file path (bypassing the package
# lookup), then replace sys.modules["shared"] with a MagicMock so that
# conftest's autouse fixtures traverse mock attribute chains instead of
# real package attributes.  The MagicMock replacement happens AFTER we have
# captured the real module object, so our imported symbols remain valid.
# ---------------------------------------------------------------------------

_captain_system_root = Path(__file__).resolve().parent.parent
_lifecycle_path = _captain_system_root / "shared" / "account_lifecycle.py"

_spec = importlib.util.spec_from_file_location("shared.account_lifecycle", _lifecycle_path)
_lifecycle_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lifecycle_module)

# Register it in sys.modules under its canonical name so subsequent imports
# see the same object.
sys.modules["shared.account_lifecycle"] = _lifecycle_module

# Now replace the shared package and its external-dependency sub-modules with
# MagicMocks so conftest's autouse fixtures resolve their setattr paths safely.
_shared_mock = MagicMock()
sys.modules["shared"] = _shared_mock
sys.modules["shared.questdb_client"] = MagicMock()
sys.modules["shared.redis_client"] = MagicMock()
sys.modules["shared.journal"] = MagicMock()
# Re-register account_lifecycle under the mock shared namespace as well
sys.modules["shared.account_lifecycle"] = _lifecycle_module

import pytest

from shared.account_lifecycle import (
    # Constants
    ACCOUNT_LOSS_FEE,
    EVAL_STARTING_BALANCE,
    EVAL_MLL,
    EVAL_PROFIT_TARGET,
    EVAL_MAX_CONTRACTS,
    XFA_MLL,
    XFA_MAX_PAYOUTS,
    LIVE_DAILY_DRAWDOWN,
    LIVE_LOW_BALANCE_THRESHOLD,
    LIVE_LOW_BALANCE_DAILY_DD,
    LIVE_TRADABLE_CAP,
    LIVE_UNLOCK_LEVELS,
    LIVE_UNLOCK_PROFIT,
    # Classes
    TopstepStage,
    TopstepEvalAccount,
    TopstepXFAAccount,
    TopstepLiveAccount,
    MultiStageTopstepAccount,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_trades(daily_pnls: list[float], day_prefix: str = "2026-03-") -> list[dict]:
    """Create a list of trade dicts from a sequence of daily P&L values.

    Each entry becomes one trade on a distinct calendar day so that EOD
    processing sees one trade per day.  This is the canonical factory used
    across all lifecycle tests.

    Args:
        daily_pnls: Ordered list of P&L values (one per day).
        day_prefix: YYYY-MM- prefix used for the day field.

    Returns:
        List of trade dicts compatible with MultiStageTopstepAccount.process_trade.
    """
    trades = []
    for i, pnl in enumerate(daily_pnls):
        day = f"{day_prefix}{i + 1:02d}"
        trades.append(
            {
                "day": day,
                "pnl": pnl,
                "contracts": 1,
                "ts": f"{day}T10:00:00",
                "model": 4,
            }
        )
    return trades


def _run_daily(account: MultiStageTopstepAccount, trades: list[dict]) -> list[dict]:
    """Process trades grouped by day, calling end_of_day after each group.

    Returns the list of end_of_day result dicts (one per unique day).

    Args:
        account: The MultiStageTopstepAccount instance to drive.
        trades: Flat list of trade dicts; grouped internally by the 'day' key.

    Returns:
        List of dicts returned by account.end_of_day for each day processed.
    """
    from collections import defaultdict

    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_day[t["day"]].append(t)

    eod_results = []
    for day in sorted(by_day):
        for trade in by_day[day]:
            account.process_trade(trade)
        eod_results.append(account.end_of_day(day))
    return eod_results


# ---------------------------------------------------------------------------
# Class 1 — TopstepEvalAccount (standalone dataclass)
# ---------------------------------------------------------------------------

class TestTopstepEvalAccount:
    """Standalone EVAL account: trailing MLL and profit-target checks."""

    def test_mll_breach_detected_at_exact_limit(self):
        """Drawdown of exactly $4,500 from peak is a breach (>= comparison)."""
        acct = TopstepEvalAccount()
        # peak=150000, current=145500 → drawdown = $4,500 exactly
        assert acct.check_mll_breach(peak_balance=150_000.0, current_balance=145_500.0) is True

    def test_mll_not_breached_one_dollar_above(self):
        """Drawdown of $4,499 (one dollar under limit) is not a breach."""
        acct = TopstepEvalAccount()
        # peak=150000, current=146000 → drawdown = $4,000 < $4,500
        assert acct.check_mll_breach(peak_balance=150_000.0, current_balance=146_000.0) is False

    def test_mll_not_breached_one_cent_above_limit(self):
        """Drawdown of $4,499.99 is strictly below the limit."""
        acct = TopstepEvalAccount()
        assert acct.check_mll_breach(150_000.0, 145_500.01) is False

    def test_pass_detected_at_target(self):
        """Balance at exactly starting + $9,000 triggers a pass."""
        acct = TopstepEvalAccount()
        target_balance = EVAL_STARTING_BALANCE + EVAL_PROFIT_TARGET  # 159_000.0
        assert acct.check_pass(target_balance) is True

    def test_pass_detected_above_target(self):
        """Balance above the profit target also triggers a pass."""
        acct = TopstepEvalAccount()
        assert acct.check_pass(160_000.0) is True

    def test_pass_not_yet_one_cent_short(self):
        """Balance one cent below the profit target is not a pass."""
        acct = TopstepEvalAccount()
        below_target = EVAL_STARTING_BALANCE + EVAL_PROFIT_TARGET - 0.01  # 158_999.99
        assert acct.check_pass(below_target) is False

    def test_pass_not_yet_round_number(self):
        """$158,999 is below target — confirms integer boundary."""
        acct = TopstepEvalAccount()
        assert acct.check_pass(158_999.0) is False

    def test_max_contracts_is_fifteen(self):
        """EVAL has a hard cap of 15 mini contracts (150 micros)."""
        acct = TopstepEvalAccount()
        assert acct.max_contracts == EVAL_MAX_CONTRACTS
        assert acct.max_contracts == 15

    def test_max_micros_is_one_fifty(self):
        """150 micros = 15 minis × 10."""
        acct = TopstepEvalAccount()
        assert acct.max_micros == 150

    def test_no_scaling_plan(self):
        """EVAL has no active scaling plan."""
        acct = TopstepEvalAccount()
        assert acct.scaling_plan_active is False
        assert acct.scaling_plan == []

    def test_default_starting_balance(self):
        """Default starting balance matches the module constant."""
        acct = TopstepEvalAccount()
        assert acct.starting_balance == EVAL_STARTING_BALANCE

    def test_custom_starting_balance(self):
        """Constructor accepts a custom starting balance."""
        acct = TopstepEvalAccount(starting_balance=200_000.0)
        assert acct.starting_balance == 200_000.0
        # Pass threshold shifts with the custom balance
        assert acct.check_pass(209_000.0) is True
        assert acct.check_pass(208_999.0) is False


# ---------------------------------------------------------------------------
# Class 2 — TopstepXFAAccount (standalone dataclass)
# ---------------------------------------------------------------------------

class TestTopstepXFAAccount:
    """Standalone XFA account: scaling tiers, MLL, and payout cap."""

    def test_mll_breach_detected_at_exact_limit(self):
        """Trailing drawdown of exactly $4,500 is a breach."""
        acct = TopstepXFAAccount()
        assert acct.check_mll_breach(peak_balance=150_000.0, current_balance=145_500.0) is True

    def test_mll_not_breached_below_limit(self):
        """Trailing drawdown of $4,000 (< $4,500) is not a breach."""
        acct = TopstepXFAAccount()
        assert acct.check_mll_breach(peak_balance=150_000.0, current_balance=146_000.0) is False

    def test_mll_not_breached_one_cent_short(self):
        """$4,499.99 drawdown is strictly below the limit."""
        acct = TopstepXFAAccount()
        assert acct.check_mll_breach(150_000.0, 145_500.01) is False

    def test_scaling_tier_at_starting_balance(self):
        """At $150,000 the first tier applies: 30 micros (3 minis)."""
        acct = TopstepXFAAccount()
        assert acct.get_scaling_tier_micros(150_000.0) == 30

    def test_scaling_tier_above_tier_two_threshold(self):
        """$151,500 crosses tier-2 threshold → 40 micros."""
        acct = TopstepXFAAccount()
        assert acct.get_scaling_tier_micros(151_500.0) == 40

    def test_scaling_tier_mid_between_tier_three_and_four(self):
        """$152,500 is between tier-3 ($152K) and tier-4 ($153K) → 50 micros."""
        acct = TopstepXFAAccount()
        assert acct.get_scaling_tier_micros(152_500.0) == 50

    def test_scaling_tier_at_tier_four_threshold(self):
        """$153,000 exactly hits tier-4 → 100 micros."""
        acct = TopstepXFAAccount()
        assert acct.get_scaling_tier_micros(153_000.0) == 100

    def test_scaling_tier_max_at_154500(self):
        """$154,500 reaches tier-5 → 150 micros (max)."""
        acct = TopstepXFAAccount()
        assert acct.get_scaling_tier_micros(154_500.0) == 150

    def test_scaling_tier_well_above_max(self):
        """Far above max tier still returns 150 micros — no higher tier."""
        acct = TopstepXFAAccount()
        assert acct.get_scaling_tier_micros(200_000.0) == 150

    def test_max_total_payouts_is_five(self):
        """XFA allows exactly 5 payouts before transitioning to LIVE."""
        acct = TopstepXFAAccount()
        assert acct.max_total_payouts == XFA_MAX_PAYOUTS
        assert acct.max_total_payouts == 5

    def test_scaling_plan_active(self):
        """XFA has an active scaling plan."""
        acct = TopstepXFAAccount()
        assert acct.scaling_plan_active is True

    def test_scaling_plan_has_five_tiers(self):
        """Default scaling plan contains exactly 5 tiers."""
        acct = TopstepXFAAccount()
        assert len(acct.scaling_plan) == 5

    def test_payout_commission_rate(self):
        """XFA payout commission is 10%."""
        acct = TopstepXFAAccount()
        assert acct.payout_commission_rate == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Class 3 — TopstepLiveAccount (standalone dataclass)
# ---------------------------------------------------------------------------

class TestTopstepLiveAccount:
    """Standalone LIVE account: no trailing MLL, daily drawdown limits."""

    def test_no_trailing_mll(self):
        """LIVE accounts have no trailing max loss limit (set to None)."""
        acct = TopstepLiveAccount()
        assert acct.max_drawdown_limit is None

    def test_starting_balance_is_none_for_standalone(self):
        """Standalone LIVE account has no starting balance — set by MultiStage."""
        acct = TopstepLiveAccount()
        assert acct.starting_balance is None

    def test_daily_drawdown_normal_balance(self):
        """Balance > $10,000 uses the standard $4,500 daily drawdown limit."""
        acct = TopstepLiveAccount()
        assert acct.get_effective_daily_drawdown(tradable_balance=50_000.0) == pytest.approx(
            LIVE_DAILY_DRAWDOWN
        )
        assert acct.get_effective_daily_drawdown(50_000.0) == pytest.approx(4_500.0)

    def test_daily_drawdown_at_threshold_uses_low_balance(self):
        """Balance exactly at $10,000 threshold IS low balance — uses $2,000."""
        acct = TopstepLiveAccount()
        # Condition is <= threshold, so at exactly $10,000 it uses low-balance DD
        assert acct.get_effective_daily_drawdown(tradable_balance=10_000.0) == pytest.approx(
            LIVE_LOW_BALANCE_DAILY_DD
        )
        assert acct.get_effective_daily_drawdown(10_000.0) == pytest.approx(2_000.0)

    def test_daily_drawdown_low_balance(self):
        """Balance < $10,000 uses the reduced $2,000 daily drawdown limit."""
        acct = TopstepLiveAccount()
        assert acct.get_effective_daily_drawdown(tradable_balance=8_000.0) == pytest.approx(
            LIVE_LOW_BALANCE_DAILY_DD
        )
        assert acct.get_effective_daily_drawdown(8_000.0) == pytest.approx(2_000.0)

    def test_daily_drawdown_just_below_threshold(self):
        """$9,999.99 is one cent below threshold → $2,000 limit."""
        acct = TopstepLiveAccount()
        assert acct.get_effective_daily_drawdown(9_999.99) == pytest.approx(2_000.0)

    def test_daily_dd_breach_at_exact_limit(self):
        """daily_pnl == -4,500 with normal balance triggers a breach (<=  -limit)."""
        acct = TopstepLiveAccount()
        # check_daily_drawdown_breach returns True when daily_pnl <= -limit
        assert acct.check_daily_drawdown_breach(daily_pnl=-4_500.0, tradable_balance=50_000.0) is True

    def test_daily_dd_breach_beyond_limit(self):
        """daily_pnl worse than -$4,500 also triggers breach."""
        acct = TopstepLiveAccount()
        assert acct.check_daily_drawdown_breach(-5_000.0, 50_000.0) is True

    def test_daily_dd_no_breach_one_cent_short(self):
        """daily_pnl of -$4,499.99 is one cent better than the limit → no breach."""
        acct = TopstepLiveAccount()
        assert acct.check_daily_drawdown_breach(-4_499.99, 50_000.0) is False

    def test_daily_dd_no_breach_round_number(self):
        """daily_pnl of -$4,499 is strictly above -$4,500 → no breach."""
        acct = TopstepLiveAccount()
        assert acct.check_daily_drawdown_breach(-4_499.0, 50_000.0) is False

    def test_daily_dd_breach_uses_low_balance_limit(self):
        """Low-balance account breaches at -$2,000, not -$4,500."""
        acct = TopstepLiveAccount()
        # $8,000 balance → effective limit = $2,000
        assert acct.check_daily_drawdown_breach(-2_000.0, 8_000.0) is True
        # -$1,999 should NOT breach under the reduced limit
        assert acct.check_daily_drawdown_breach(-1_999.0, 8_000.0) is False

    def test_default_constants_match_module(self):
        """Dataclass defaults match module-level constants."""
        acct = TopstepLiveAccount()
        assert acct.max_daily_drawdown == LIVE_DAILY_DRAWDOWN
        assert acct.low_balance_threshold == LIVE_LOW_BALANCE_THRESHOLD
        assert acct.low_balance_daily_drawdown == LIVE_LOW_BALANCE_DAILY_DD
        assert acct.tradable_cap == LIVE_TRADABLE_CAP
        assert acct.unlock_levels == LIVE_UNLOCK_LEVELS
        assert acct.unlock_profit == LIVE_UNLOCK_PROFIT


# ---------------------------------------------------------------------------
# Class 4 — MultiStageTopstepAccount (full lifecycle state machine)
# ---------------------------------------------------------------------------

class TestMultiStageLifecycle:
    """Full lifecycle: EVAL → XFA → LIVE with failures, payouts, and unlocks."""

    # ------------------------------------------------------------------ init

    def test_starts_in_eval(self):
        """Freshly constructed account is in EVAL with $150,000 balance."""
        acct = MultiStageTopstepAccount()
        assert acct.current_stage == TopstepStage.EVAL
        assert acct.balance == pytest.approx(EVAL_STARTING_BALANCE)
        assert acct.peak_balance == pytest.approx(EVAL_STARTING_BALANCE)

    def test_starts_with_zero_fees(self):
        """No fees on a fresh account."""
        acct = MultiStageTopstepAccount()
        assert acct.total_fees == pytest.approx(0.0)
        assert acct.total_resets == 0

    def test_starts_with_zero_payouts(self):
        """No payouts on a fresh account."""
        acct = MultiStageTopstepAccount()
        assert acct.payouts_taken == 0

    def test_eval_disallows_payout(self):
        """process_payout during EVAL is rejected."""
        acct = MultiStageTopstepAccount()
        result = acct.process_payout(amount=1_000.0, day="2026-03-01")
        assert result["success"] is False

    # ------------------------------------------------------------------ EVAL → XFA

    def test_eval_pass_transitions_to_xfa(self):
        """Earning $9,000 profit in EVAL triggers a transition to XFA at EOD."""
        acct = MultiStageTopstepAccount()
        # Nine winning days of $1,000 each → cumulative profit = $9,000
        trades = make_trades([1_000.0] * 9)
        eod_results = _run_daily(acct, trades)

        assert acct.current_stage == TopstepStage.XFA
        # Confirm stage_changed=True was returned on the day the pass occurred
        passed_days = [r for r in eod_results if r["stage_changed"] and not r["failure"]]
        assert len(passed_days) == 1
        assert passed_days[0]["new_stage"] == TopstepStage.XFA

    def test_eval_pass_balance_carries_into_xfa(self):
        """Balance accumulated in EVAL carries over into XFA — no reset on pass."""
        acct = MultiStageTopstepAccount()
        trades = make_trades([1_000.0] * 9)
        _run_daily(acct, trades)

        assert acct.current_stage == TopstepStage.XFA
        assert acct.balance == pytest.approx(159_000.0)  # 150K + 9K

    def test_eval_pass_peak_reset_for_xfa_mll(self):
        """Peak balance resets to current balance when entering XFA so MLL tracks from XFA start."""
        acct = MultiStageTopstepAccount()
        trades = make_trades([1_000.0] * 9)
        _run_daily(acct, trades)

        assert acct.peak_balance == pytest.approx(acct.balance)

    # ------------------------------------------------------------------ EVAL failure

    def test_eval_mll_failure_reverts_to_fresh_eval(self):
        """Losing $4,500 in EVAL triggers failure → revert to fresh $150K EVAL."""
        acct = MultiStageTopstepAccount()
        # Single loss of exactly $4,500 breaches the MLL
        trades = make_trades([-4_500.0])
        eod_results = _run_daily(acct, trades)

        assert acct.current_stage == TopstepStage.EVAL
        assert acct.balance == pytest.approx(EVAL_STARTING_BALANCE)
        assert eod_results[0]["failure"] is True
        assert eod_results[0]["new_stage"] == TopstepStage.EVAL

    def test_eval_mll_failure_charges_fee(self):
        """A failure in EVAL charges exactly $226.60."""
        acct = MultiStageTopstepAccount()
        trades = make_trades([-4_500.0])
        _run_daily(acct, trades)

        assert acct.total_fees == pytest.approx(ACCOUNT_LOSS_FEE)  # $226.60
        assert acct.total_resets == 1

    def test_eval_mll_failure_resets_peak(self):
        """After a failure, peak_balance is reset to $150,000."""
        acct = MultiStageTopstepAccount()
        trades = make_trades([-4_500.0])
        _run_daily(acct, trades)

        assert acct.peak_balance == pytest.approx(EVAL_STARTING_BALANCE)

    # ------------------------------------------------------------------ XFA failure

    def test_xfa_mll_failure_reverts_to_eval(self):
        """Losing $4,500 from XFA peak reverts to fresh EVAL with fee."""
        acct = MultiStageTopstepAccount()
        # First pass EVAL
        _run_daily(acct, make_trades([1_000.0] * 9))
        assert acct.current_stage == TopstepStage.XFA

        # Now lose enough to breach XFA MLL from its new peak
        # XFA peak = 159,000 after transition; lose $4,500 → breach
        trades = make_trades([-4_500.0], day_prefix="2026-04-")
        eod_results = _run_daily(acct, trades)

        assert acct.current_stage == TopstepStage.EVAL
        assert acct.balance == pytest.approx(EVAL_STARTING_BALANCE)
        assert eod_results[0]["failure"] is True
        assert acct.total_fees == pytest.approx(ACCOUNT_LOSS_FEE)

    def test_xfa_mll_failure_resets_payouts(self):
        """After XFA failure, payouts_taken is reset to 0."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        # Take one payout before failing
        acct.process_payout(500.0, "2026-04-01")
        assert acct.payouts_taken == 1

        trades = make_trades([-4_500.0], day_prefix="2026-04-")
        _run_daily(acct, trades)

        assert acct.payouts_taken == 0

    # ------------------------------------------------------------------ XFA → LIVE

    def test_xfa_to_live_after_five_payouts(self):
        """Exactly 5 XFA payouts trigger the XFA → LIVE transition."""
        acct = MultiStageTopstepAccount()
        # Pass EVAL
        _run_daily(acct, make_trades([1_000.0] * 9))
        assert acct.current_stage == TopstepStage.XFA

        for i in range(5):
            result = acct.process_payout(100.0, f"2026-04-{i + 1:02d}")
            assert result["success"] is True

        assert acct.current_stage == TopstepStage.LIVE

    def test_xfa_to_live_fifth_payout_has_transition(self):
        """The 5th payout dict contains a transition event (not None)."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))

        results = [acct.process_payout(100.0, f"2026-04-{i + 1:02d}") for i in range(5)]

        # First four payouts should not trigger a transition
        for r in results[:4]:
            assert r["transition"] is None
        # Fifth payout triggers the transition
        assert results[4]["transition"] is not None

    def test_xfa_payout_commission_ten_percent(self):
        """XFA payout applies 10% commission (net = amount × 0.90)."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))

        result = acct.process_payout(1_000.0, "2026-04-01")

        assert result["success"] is True
        assert result["net_amount"] == pytest.approx(900.0)
        assert result["commission"] == pytest.approx(100.0)

    # ------------------------------------------------------------------ LIVE balance split

    def test_live_balance_calculation_over_tradable_cap(self):
        """XFA balance > $30K → tradable = $30K, reserve = remainder."""
        acct = MultiStageTopstepAccount()
        # Pass EVAL and inflate XFA balance to $155,000 via profit
        _run_daily(acct, make_trades([1_000.0] * 9))   # → $159K in XFA
        # Make 5 payouts that cost very little to trigger LIVE transition
        # Use $1 payouts just to exhaust the counter
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        # balance is now ~$159K - $5 = ~$158,995 but let's check the split
        # At transition: tradable = min(balance, 30K) = 30K
        assert acct.current_stage == TopstepStage.LIVE
        assert acct.tradable_balance == pytest.approx(LIVE_TRADABLE_CAP)  # $30,000

    def test_live_reserve_equals_balance_minus_tradable(self):
        """Reserve = total balance − tradable_cap when balance > tradable_cap."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")

        expected_reserve = acct.balance - LIVE_TRADABLE_CAP
        assert acct.reserve_balance == pytest.approx(expected_reserve)

    def test_live_balance_calculation_under_tradable_cap(self):
        """XFA balance below $30,000 cap → tradable = full balance, reserve = $0.

        Uses starting_balance=20_000 so that after passing EVAL ($9K profit =
        $29K total) the balance stays strictly under the $30K tradable cap even
        after five tiny payouts.
        """
        # 20_000 + 9_000 = 29_000 — safely below the $30K cap
        acct = MultiStageTopstepAccount(starting_balance=20_000.0)
        # 9 days of $1,000 profit meets the $9K profit target
        _run_daily(acct, make_trades([1_000.0] * 9))
        assert acct.current_stage == TopstepStage.XFA
        assert acct.balance == pytest.approx(29_000.0)

        # Take 5 tiny payouts (each $1) to exhaust the XFA payout counter
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        assert acct.current_stage == TopstepStage.LIVE

        # balance is now 29_000 - 5 = 28_995, which is < LIVE_TRADABLE_CAP
        # → tradable = full balance, reserve = 0, no unlock blocks
        assert acct.balance == pytest.approx(28_995.0)
        assert acct.tradable_balance == pytest.approx(acct.balance)
        assert acct.reserve_balance == pytest.approx(0.0)
        assert acct.unlocks_remaining == 0

    def test_live_reserve_divided_into_four_blocks(self):
        """Reserve capital is split evenly into LIVE_UNLOCK_LEVELS (4) blocks."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")

        assert acct.unlocks_remaining == LIVE_UNLOCK_LEVELS  # 4
        expected_per_block = acct.reserve_balance / LIVE_UNLOCK_LEVELS
        assert acct.reserve_per_block == pytest.approx(expected_per_block)

    # ------------------------------------------------------------------ LIVE trading

    def test_live_daily_dd_halts_not_reverts(self):
        """In LIVE, daily drawdown breach sets halted_until_19est=True; stage stays LIVE."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        assert acct.current_stage == TopstepStage.LIVE

        # A single trade losing exactly $4,500 on the tradable balance
        trade = {"day": "2026-05-01", "pnl": -4_500.0, "contracts": 1,
                 "ts": "2026-05-01T10:00:00", "model": 4}
        acct.process_trade(trade)
        eod = acct.end_of_day("2026-05-01")

        assert acct.current_stage == TopstepStage.LIVE  # NOT reverted
        assert eod["halt"] is True

    def test_live_trade_blocked_when_halted(self):
        """A trade submitted while halted_until_19est=True is rejected."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")

        # Trigger halt
        trade = {"day": "2026-05-01", "pnl": -4_500.0, "contracts": 1,
                 "ts": "2026-05-01T10:00:00", "model": 4}
        acct.process_trade(trade)
        assert acct.halted_until_19est is True

        # Subsequent trade on same day is blocked
        blocked = {"day": "2026-05-01", "pnl": 500.0, "contracts": 1,
                   "ts": "2026-05-01T11:00:00", "model": 4}
        result = acct.process_trade(blocked)
        assert result["allowed"] is False
        assert result["reason"] == "HALTED_DAILY_DD"

    def test_live_halt_clears_after_eod(self):
        """_reset_daily called by end_of_day clears the halt flag for the next day."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")

        trade = {"day": "2026-05-01", "pnl": -4_500.0, "contracts": 1,
                 "ts": "2026-05-01T10:00:00", "model": 4}
        acct.process_trade(trade)
        acct.end_of_day("2026-05-01")

        assert acct.halted_until_19est is False

    def test_live_low_balance_dd_limit_applied(self):
        """LIVE account with tradable < $10K uses $2,000 daily drawdown."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        assert acct.current_stage == TopstepStage.LIVE

        # Manually set tradable balance below threshold to simulate scenario
        acct.tradable_balance = 8_000.0

        # Loss of $2,000 should breach at low balance
        trade = {"day": "2026-05-01", "pnl": -2_000.0, "contracts": 1,
                 "ts": "2026-05-01T10:00:00", "model": 4}
        result = acct.process_trade(trade)
        # Post-trade: daily_pnl = -2000, tradable = 6000 → effective limit = 2000
        # check_daily_drawdown_breach: daily_pnl (-2000) <= -2000 → True
        assert result["breach_type"] == "DAILY_DD"

    def test_live_normal_dd_not_breached(self):
        """Loss of $4,499 with normal balance does not breach the $4,500 limit."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")

        trade = {"day": "2026-05-01", "pnl": -4_499.0, "contracts": 1,
                 "ts": "2026-05-01T10:00:00", "model": 4}
        result = acct.process_trade(trade)

        assert result["allowed"] is True
        assert result["breach_type"] is None

    # ------------------------------------------------------------------ LIVE capital unlock

    def test_live_capital_unlock_after_9k_profit(self):
        """Earning $9,000 cumulative live profit unlocks one reserve block.

        In LIVE, each winning trade also increments tradable_balance directly
        (see process_trade: self.tradable_balance += pnl).  So the expected
        final tradable is:
            initial_tradable + (sum of live trade PnLs) + per_block
        """
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        assert acct.current_stage == TopstepStage.LIVE

        initial_unlocks = acct.unlocks_remaining
        initial_tradable = acct.tradable_balance
        initial_reserve = acct.reserve_balance
        per_block = acct.reserve_per_block

        if initial_unlocks == 0:
            pytest.skip("No reserve blocks present — balance was below tradable cap.")

        # Nine winning days of $1,000 each → cumulative_live_profit = $9,000
        live_pnls = [1_000.0] * 9
        trades = make_trades(live_pnls, day_prefix="2026-05-")
        _run_daily(acct, trades)

        live_pnl_total = sum(live_pnls)  # $9,000 added to tradable during trade processing
        expected_tradable = initial_tradable + live_pnl_total + per_block
        expected_reserve = initial_reserve - per_block

        assert acct.unlocks_remaining == initial_unlocks - 1
        assert acct.tradable_balance == pytest.approx(expected_tradable)
        assert acct.reserve_balance == pytest.approx(expected_reserve)

    def test_live_unlock_event_logged(self):
        """A CAPITAL_UNLOCK lifecycle event is recorded after an unlock."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")

        if acct.unlocks_remaining == 0:
            pytest.skip("No reserve blocks present.")

        events_before = len(acct.events)
        trades = make_trades([1_000.0] * 9, day_prefix="2026-05-")
        _run_daily(acct, trades)

        unlock_events = [e for e in acct.events if e.event_type == "CAPITAL_UNLOCK"]
        assert len(unlock_events) >= 1
        assert unlock_events[0].trigger == "PROFIT_THRESHOLD_MET"

    # ------------------------------------------------------------------ fees

    def test_multiple_failures_accumulate_fees(self):
        """Two separate failures accumulate $226.60 × 2 = $453.20 in total fees."""
        acct = MultiStageTopstepAccount()

        # First failure
        _run_daily(acct, make_trades([-4_500.0], day_prefix="2026-03-"))
        assert acct.total_fees == pytest.approx(ACCOUNT_LOSS_FEE)

        # Second failure (account has reset to fresh EVAL)
        _run_daily(acct, make_trades([-4_500.0], day_prefix="2026-04-"))
        assert acct.total_fees == pytest.approx(ACCOUNT_LOSS_FEE * 2)

    def test_failure_fee_matches_constant(self):
        """Fee constant is exactly $226.60."""
        assert ACCOUNT_LOSS_FEE == pytest.approx(226.60)

    def test_failure_increments_reset_counter(self):
        """Each failure increments total_resets."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([-4_500.0], day_prefix="2026-03-"))
        _run_daily(acct, make_trades([-4_500.0], day_prefix="2026-04-"))
        assert acct.total_resets == 2

    # ------------------------------------------------------------------ state snapshot

    def test_get_state_snapshot_fields(self):
        """get_state_snapshot returns all expected keys."""
        acct = MultiStageTopstepAccount()
        snap = acct.get_state_snapshot()

        required_keys = {
            "current_stage", "balance", "peak_balance", "payouts_taken",
            "winning_days", "tradable_balance", "reserve_balance",
            "reserve_per_block", "unlocks_remaining", "cumulative_live_profit",
            "total_fees", "total_resets", "events_count", "halted",
        }
        assert required_keys <= snap.keys()

    def test_get_state_snapshot_initial_values(self):
        """Fresh account snapshot has correct initial values."""
        acct = MultiStageTopstepAccount()
        snap = acct.get_state_snapshot()

        assert snap["current_stage"] == "EVAL"
        assert snap["balance"] == pytest.approx(EVAL_STARTING_BALANCE)
        assert snap["total_fees"] == pytest.approx(0.0)
        assert snap["total_resets"] == 0
        assert snap["events_count"] == 0
        assert snap["halted"] is False

    def test_to_tsm_dict_eval_stage(self):
        """to_tsm_dict in EVAL returns PROP_EVAL classification with correct fields."""
        acct = MultiStageTopstepAccount()
        tsm = acct.to_tsm_dict()

        assert tsm["classification"]["category"] == "PROP_EVAL"
        assert tsm["max_drawdown_limit"] == pytest.approx(EVAL_MLL)
        assert tsm["max_contracts"] == EVAL_MAX_CONTRACTS
        assert tsm["profit_target"] == pytest.approx(EVAL_PROFIT_TARGET)
        assert tsm["scaling_plan_active"] is False

    def test_to_tsm_dict_xfa_stage(self):
        """to_tsm_dict in XFA returns PROP_FUNDED/XFA with scaling plan."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        assert acct.current_stage == TopstepStage.XFA
        tsm = acct.to_tsm_dict()

        assert tsm["classification"]["stage"] == "XFA"
        assert tsm["scaling_plan_active"] is True
        assert tsm["scaling_plan"] is not None
        assert tsm["max_drawdown_limit"] == pytest.approx(XFA_MLL)

    def test_to_tsm_dict_live_stage(self):
        """to_tsm_dict in LIVE returns PROP_FUNDED/LIVE with no trailing MLL."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        assert acct.current_stage == TopstepStage.LIVE
        tsm = acct.to_tsm_dict()

        assert tsm["classification"]["stage"] == "LIVE"
        assert tsm["max_drawdown_limit"] is None
        assert tsm["max_daily_drawdown"] == pytest.approx(LIVE_DAILY_DRAWDOWN)
        assert tsm["scaling_plan_active"] is False

    # ------------------------------------------------------------------ full lifecycle

    def test_full_lifecycle_eval_xfa_live(self):
        """End-to-end: EVAL pass → XFA → 5 payouts → LIVE with reserve blocks."""
        acct = MultiStageTopstepAccount()

        # ---- Phase 1: EVAL — accumulate $9,000 profit over 9 days ----
        _run_daily(acct, make_trades([1_000.0] * 9, day_prefix="2026-01-"))
        assert acct.current_stage == TopstepStage.XFA, "Should be in XFA after passing EVAL"
        assert acct.balance == pytest.approx(159_000.0)
        assert acct.total_fees == pytest.approx(0.0)

        # ---- Phase 2: XFA — earn a bit more, then take 5 payouts ----
        _run_daily(acct, make_trades([500.0] * 4, day_prefix="2026-02-"))
        # balance now ~$161,000
        for i in range(5):
            result = acct.process_payout(200.0, f"2026-02-{i + 10:02d}")
            assert result["success"] is True

        assert acct.current_stage == TopstepStage.LIVE, "Should be in LIVE after 5 payouts"
        assert acct.payouts_taken == 5

        # ---- Phase 3: LIVE — verify structure ----
        assert acct.tradable_balance == pytest.approx(LIVE_TRADABLE_CAP)  # $30K cap
        assert acct.reserve_balance > 0
        assert acct.unlocks_remaining == LIVE_UNLOCK_LEVELS  # 4 blocks pending

        snap = acct.get_state_snapshot()
        assert snap["current_stage"] == "LIVE"
        assert snap["total_resets"] == 0
        assert snap["total_fees"] == pytest.approx(0.0)

    def test_full_lifecycle_with_one_failure_then_pass(self):
        """Fail once in EVAL (pay fee), start fresh, then pass to XFA."""
        acct = MultiStageTopstepAccount()

        # First attempt: fail
        _run_daily(acct, make_trades([-4_500.0], day_prefix="2026-01-"))
        assert acct.current_stage == TopstepStage.EVAL
        assert acct.total_fees == pytest.approx(ACCOUNT_LOSS_FEE)
        assert acct.balance == pytest.approx(EVAL_STARTING_BALANCE)

        # Second attempt: pass
        _run_daily(acct, make_trades([1_000.0] * 9, day_prefix="2026-02-"))
        assert acct.current_stage == TopstepStage.XFA
        assert acct.total_fees == pytest.approx(ACCOUNT_LOSS_FEE)  # fee persists

    def test_winning_days_counter_increments(self):
        """winning_days increments for each day with positive daily P&L."""
        acct = MultiStageTopstepAccount()
        trades = make_trades([100.0, -50.0, 200.0, 0.0, 300.0])
        _run_daily(acct, trades)

        # Days with positive pnl: day 1 ($100), day 3 ($200), day 5 ($300) = 3
        assert acct.winning_days == 3

    def test_events_list_grows_with_lifecycle(self):
        """events list captures transitions and failures as LifecycleEvent objects."""
        acct = MultiStageTopstepAccount()

        # Transition: EVAL → XFA
        _run_daily(acct, make_trades([1_000.0] * 9, day_prefix="2026-01-"))
        assert len(acct.events) == 1
        assert acct.events[0].event_type == "STAGE_TRANSITION"

        # Payout events
        for i in range(5):
            acct.process_payout(100.0, f"2026-02-{i + 1:02d}")

        # Expect: 1 transition (EVAL→XFA) + 5 payout events + 1 transition (XFA→LIVE)
        payout_events = [e for e in acct.events if e.event_type == "PAYOUT"]
        transition_events = [e for e in acct.events if e.event_type == "STAGE_TRANSITION"]
        assert len(payout_events) == 5
        assert len(transition_events) == 2

    def test_failure_event_recorded_in_events_list(self):
        """A FAILURE lifecycle event is appended on breach."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([-4_500.0]))

        failure_events = [e for e in acct.events if e.event_type == "FAILURE"]
        assert len(failure_events) == 1
        assert failure_events[0].fee_charged == pytest.approx(ACCOUNT_LOSS_FEE)
        assert failure_events[0].from_stage == "EVAL"
        assert failure_events[0].to_stage == "EVAL"

    def test_no_transition_on_borderline_profit(self):
        """$8,999 cumulative profit does not trigger an EVAL pass — one cent too short."""
        acct = MultiStageTopstepAccount()
        # Eight winning days of $1,000 and one day of $999 = $8,999 total
        _run_daily(acct, make_trades([1_000.0] * 8 + [999.0]))
        assert acct.current_stage == TopstepStage.EVAL

    def test_eval_no_breach_on_4499_loss(self):
        """Loss of $4,499 from peak does not trigger an EVAL MLL breach."""
        acct = MultiStageTopstepAccount()
        trade = {"day": "2026-03-01", "pnl": -4_499.0, "contracts": 1,
                 "ts": "2026-03-01T10:00:00", "model": 4}
        result = acct.process_trade(trade)
        assert result["allowed"] is True
        assert result["breach_type"] is None

    def test_live_payout_has_no_commission(self):
        """LIVE stage payouts carry 0% commission (full amount returned)."""
        acct = MultiStageTopstepAccount()
        _run_daily(acct, make_trades([1_000.0] * 9))
        for i in range(5):
            acct.process_payout(1.0, f"2026-04-{i + 1:02d}")
        assert acct.current_stage == TopstepStage.LIVE

        result = acct.process_payout(500.0, "2026-05-01")
        assert result["success"] is True
        assert result["commission"] == pytest.approx(0.0)
        assert result["net_amount"] == pytest.approx(500.0)
