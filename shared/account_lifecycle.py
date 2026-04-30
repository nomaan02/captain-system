"""Topstep account lifecycle: EVAL → XFA → LIVE stage management.

Provides standalone account classes (TopstepEvalAccount, TopstepXFAAccount,
TopstepLiveAccount) and a MultiStageTopstepAccount state machine that
progresses through all three stages with automatic transitions.

Constraints per stage:
    EVAL: $4,500 MLL (max loss limit, trailing). 15 minis / 150 micros.
          No daily loss limit. No payouts. Pass at $9K profit.
    XFA:  $4,500 MLL. Contract scaling plan (3→15 minis).
          5 payouts max, then transition to LIVE.
    LIVE: No MLL (MLL = $0 account balance). Daily drawdown $4,500.
          If balance < $10K, daily drawdown drops to $2,000.
          Daily drawdown breach → auto-liquidate + halt until 19:00 EST.
          Capital unlock: tradable capped at $30K, reserve in 4 blocks.

Failure at any stage: $226.60 fee logged, revert to fresh $150K EVAL.
"""

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from shared.constants import now_et

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNT_LOSS_FEE = Decimal("226.60")
EVAL_STARTING_BALANCE = Decimal("150000")
EVAL_MLL = Decimal("4500")
EVAL_PROFIT_TARGET = Decimal("9000")
EVAL_MAX_CONTRACTS = 15  # 150 micros

XFA_MLL = Decimal("4500")
XFA_MAX_PAYOUTS = 5

LIVE_DAILY_DRAWDOWN = Decimal("4500")
LIVE_LOW_BALANCE_THRESHOLD = Decimal("10000")
LIVE_LOW_BALANCE_DAILY_DD = Decimal("2000")
LIVE_TRADABLE_CAP = Decimal("30000")
LIVE_UNLOCK_LEVELS = 4
LIVE_UNLOCK_PROFIT = Decimal("9000")


class TopstepStage(str, Enum):
    """Account lifecycle stages."""
    EVAL = "EVAL"
    XFA = "XFA"
    LIVE = "LIVE"


# ---------------------------------------------------------------------------
# Standalone account configs
# ---------------------------------------------------------------------------

@dataclass
class TopstepEvalAccount:
    """Standalone evaluation account.

    Single constraint: $4,500 trailing MLL.
    Pass when cumulative profit >= $9,000.
    """
    starting_balance: Decimal = field(default_factory=lambda: EVAL_STARTING_BALANCE)
    max_drawdown_limit: Decimal = field(default_factory=lambda: EVAL_MLL)
    profit_target: Decimal = field(default_factory=lambda: EVAL_PROFIT_TARGET)
    max_contracts: int = EVAL_MAX_CONTRACTS
    max_micros: int = EVAL_MAX_CONTRACTS * 10
    scaling_plan_active: bool = False
    scaling_plan: list = field(default_factory=list)
    stage: TopstepStage = TopstepStage.EVAL

    def check_mll_breach(self, peak_balance, current_balance) -> bool:
        """True if trailing drawdown exceeds MLL."""
        peak = Decimal(str(peak_balance))
        cur = Decimal(str(current_balance))
        return (peak - cur) >= self.max_drawdown_limit

    def check_pass(self, current_balance) -> bool:
        """True if profit target reached."""
        cur = Decimal(str(current_balance))
        sb = (
            self.starting_balance
            if isinstance(self.starting_balance, Decimal)
            else Decimal(str(self.starting_balance))
        )
        return cur >= sb + self.profit_target


@dataclass
class TopstepXFAAccount:
    """Standalone XFA (Express Funded Account).

    $4,500 trailing MLL. Contract scaling plan.
    Max 5 payouts before transition to LIVE.
    """
    starting_balance: Decimal = field(default_factory=lambda: EVAL_STARTING_BALANCE)
    max_drawdown_limit: Decimal = field(default_factory=lambda: XFA_MLL)
    max_contracts: int = EVAL_MAX_CONTRACTS
    scaling_plan_active: bool = True
    scaling_plan: list = field(default_factory=lambda: [
        {"balance_threshold": 150000, "max_contracts": 3, "max_micros": 30},
        {"balance_threshold": 151500, "max_contracts": 4, "max_micros": 40},
        {"balance_threshold": 152000, "max_contracts": 5, "max_micros": 50},
        {"balance_threshold": 153000, "max_contracts": 10, "max_micros": 100},
        {"balance_threshold": 154500, "max_contracts": 15, "max_micros": 150},
    ])
    max_total_payouts: int = XFA_MAX_PAYOUTS
    consistency_rule_max_daily_profit: Decimal = Decimal("4500")
    payout_commission_rate: Decimal = Decimal("0.10")
    stage: TopstepStage = TopstepStage.XFA

    def check_mll_breach(self, peak_balance, current_balance) -> bool:
        peak = Decimal(str(peak_balance))
        cur = Decimal(str(current_balance))
        return (peak - cur) >= self.max_drawdown_limit

    def get_scaling_tier_micros(self, current_balance) -> int:
        """Return max micros for current balance tier."""
        bal = Decimal(str(current_balance))
        if not self.scaling_plan:
            return self.max_contracts * 10
        sorted_plan = sorted(self.scaling_plan,
                             key=lambda t: t.get("balance_threshold", 0))
        result = sorted_plan[0].get("max_micros", 30)
        for tier in sorted_plan:
            thr = tier.get("balance_threshold", 0)
            if bal >= Decimal(str(thr)):
                result = tier.get("max_micros", result)
        return result


@dataclass
class TopstepLiveAccount:
    """Standalone Live funded account.

    No trailing MLL (MLL = $0 account balance).
    Daily drawdown: $4,500 (or $2,000 if balance < $10K).
    Daily drawdown breach: auto-liquidate + halt until 19:00 EST next day.
    Capital unlock: tradable capped at $30K, reserve in 4 blocks.

    starting_balance is None for standalone — set by MultiStageTopstepAccount.
    """
    starting_balance: Decimal | None = None
    max_drawdown_limit: Decimal | None = None  # No trailing MLL
    max_daily_drawdown: Decimal = field(default_factory=lambda: LIVE_DAILY_DRAWDOWN)
    low_balance_threshold: Decimal = field(default_factory=lambda: LIVE_LOW_BALANCE_THRESHOLD)
    low_balance_daily_drawdown: Decimal = field(default_factory=lambda: LIVE_LOW_BALANCE_DAILY_DD)
    max_contracts: int = EVAL_MAX_CONTRACTS
    scaling_plan_active: bool = False
    tradable_cap: Decimal = field(default_factory=lambda: LIVE_TRADABLE_CAP)
    unlock_levels: int = LIVE_UNLOCK_LEVELS
    unlock_profit: Decimal = field(default_factory=lambda: LIVE_UNLOCK_PROFIT)
    stage: TopstepStage = TopstepStage.LIVE

    def get_effective_daily_drawdown(self, tradable_balance) -> Decimal:
        """Return daily drawdown limit based on current tradable balance."""
        tb = Decimal(str(tradable_balance))
        if tb <= self.low_balance_threshold:
            return self.low_balance_daily_drawdown
        return self.max_daily_drawdown

    def check_daily_drawdown_breach(self, daily_pnl, tradable_balance) -> bool:
        """True if daily drawdown limit breached (triggers auto-liquidate)."""
        dp = Decimal(str(daily_pnl))
        limit = self.get_effective_daily_drawdown(tradable_balance)
        return dp <= -limit


# ---------------------------------------------------------------------------
# Multi-stage lifecycle state machine
# ---------------------------------------------------------------------------

@dataclass
class LifecycleEvent:
    """Record of a lifecycle event (transition, failure, payout, etc.)."""
    event_id: str
    event_type: str  # STAGE_TRANSITION | FAILURE | FEE_CHARGED | PAYOUT | RESET
    from_stage: str
    to_stage: str
    trigger: str
    balance_at_event: Decimal
    fee_charged: Decimal = field(default_factory=lambda: Decimal("0"))
    payout_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    payout_net: Decimal = field(default_factory=lambda: Decimal("0"))
    payouts_taken: int = 0
    tradable_balance: Decimal = field(default_factory=lambda: Decimal("0"))
    reserve_balance: Decimal = field(default_factory=lambda: Decimal("0"))
    details: dict = field(default_factory=dict)
    ts: str = field(default_factory=lambda: now_et().isoformat())


class MultiStageTopstepAccount:
    """EVAL → XFA → LIVE lifecycle with automatic transitions.

    On failure at any stage: charge $226.60 fee, revert to fresh $150K EVAL.
    EVAL → XFA: when profit target ($9K) reached.
    XFA → LIVE: when 5 payouts taken.
    LIVE: tradable = min(xfa_balance, $30K), reserve = remainder / 4 blocks.
    """

    def __init__(self, starting_balance=EVAL_STARTING_BALANCE):
        sb = Decimal(str(starting_balance))
        self.starting_balance = sb
        self.current_stage = TopstepStage.EVAL
        self.balance = sb
        self.peak_balance = sb
        self.daily_pnl = Decimal("0")
        self.daily_peak_pnl = Decimal("0")

        # XFA tracking
        self.payouts_taken = 0
        self.winning_days = 0

        # Live tracking
        self.tradable_balance = Decimal("0")
        self.reserve_balance = Decimal("0")
        self.reserve_per_block = Decimal("0")
        self.unlocks_remaining = 0
        self.cumulative_live_profit = Decimal("0")
        self.halted_until_19est = False

        # Lifecycle history
        self.events: list[LifecycleEvent] = []
        self.total_fees = Decimal("0")
        self.total_resets = 0

        # Stage configs (loaded lazily)
        self._eval_config = TopstepEvalAccount(starting_balance=sb)
        self._xfa_config = TopstepXFAAccount(starting_balance=sb)
        self._live_config = TopstepLiveAccount()

    @property
    def active_config(self):
        """Return the config object for the current stage."""
        if self.current_stage == TopstepStage.EVAL:
            return self._eval_config
        elif self.current_stage == TopstepStage.XFA:
            return self._xfa_config
        return self._live_config

    # ----- Trade processing -----

    def process_trade(self, trade: dict) -> dict:
        """Apply current-stage constraints to a trade.

        Args:
            trade: dict with keys: day, pnl, contracts, ts, model

        Returns:
            dict with: allowed (bool), adjusted_pnl, reason, breach_type
        """
        pnl = Decimal(str(trade.get("pnl", 0)))
        contracts = trade.get("contracts", 1)
        zero = Decimal("0")

        # Live: check if halted
        if self.current_stage == TopstepStage.LIVE and self.halted_until_19est:
            return {"allowed": False, "adjusted_pnl": zero,
                    "reason": "HALTED_DAILY_DD", "breach_type": None}

        # EVAL: check MLL before trade
        if self.current_stage == TopstepStage.EVAL:
            if self._eval_config.check_mll_breach(self.peak_balance, self.balance):
                return {"allowed": False, "adjusted_pnl": zero,
                        "reason": "MLL_BREACH", "breach_type": "MLL"}

        # XFA: check MLL + scaling
        elif self.current_stage == TopstepStage.XFA:
            if self._xfa_config.check_mll_breach(self.peak_balance, self.balance):
                return {"allowed": False, "adjusted_pnl": zero,
                        "reason": "MLL_BREACH", "breach_type": "MLL"}
            tier_micros = self._xfa_config.get_scaling_tier_micros(self.balance)
            trade_micros = contracts * 10
            if trade_micros > tier_micros:
                scale_factor = Decimal(tier_micros) / Decimal(trade_micros)
                pnl = pnl * scale_factor

        # LIVE: check daily drawdown
        elif self.current_stage == TopstepStage.LIVE:
            effective_balance = self.tradable_balance
            if self._live_config.check_daily_drawdown_breach(
                    self.daily_pnl, effective_balance):
                self.halted_until_19est = True
                return {"allowed": False, "adjusted_pnl": zero,
                        "reason": "DAILY_DD_BREACH", "breach_type": "DAILY_DD"}

        # Trade allowed — apply P&L
        self.balance += pnl
        self.daily_pnl += pnl
        self.peak_balance = max(self.peak_balance, self.balance)

        if self.current_stage == TopstepStage.LIVE:
            self.tradable_balance += pnl
            self.cumulative_live_profit += pnl

        # Post-trade MLL check (detect breach on this trade)
        post_breach = None
        if self.current_stage == TopstepStage.EVAL:
            if self._eval_config.check_mll_breach(self.peak_balance, self.balance):
                post_breach = "MLL"
        elif self.current_stage == TopstepStage.XFA:
            if self._xfa_config.check_mll_breach(self.peak_balance, self.balance):
                post_breach = "MLL"
        elif self.current_stage == TopstepStage.LIVE:
            if self._live_config.check_daily_drawdown_breach(
                    self.daily_pnl, self.tradable_balance):
                self.halted_until_19est = True
                post_breach = "DAILY_DD"

        return {"allowed": True, "adjusted_pnl": pnl,
                "reason": None, "breach_type": post_breach}

    # ----- End of day -----

    def end_of_day(self, day: str) -> dict:
        """EOD processing: check transitions, update counters, handle breaches.

        Call after all trades for a day are processed.

        Returns:
            dict with: stage_changed, new_stage, failure, halt, events
        """
        result = {
            "stage_changed": False, "new_stage": None,
            "failure": False, "halt": False, "events": [],
        }

        # Check for MLL failure (EVAL/XFA)
        if self.current_stage in (TopstepStage.EVAL, TopstepStage.XFA):
            mll = (EVAL_MLL if self.current_stage == TopstepStage.EVAL
                   else XFA_MLL)
            if (self.peak_balance - self.balance) >= mll:
                failure_event = self.handle_failure(
                    day, f"MLL_BREACH_{self.current_stage.value}")
                result["failure"] = True
                result["stage_changed"] = True
                result["new_stage"] = TopstepStage.EVAL
                result["events"].append(failure_event)
                self._reset_daily()
                return result

        # Check for EVAL pass → XFA
        if self.current_stage == TopstepStage.EVAL:
            if self._eval_config.check_pass(self.balance):
                event = self._transition_to(TopstepStage.XFA, day,
                                            "PROFIT_TARGET_MET")
                result["stage_changed"] = True
                result["new_stage"] = TopstepStage.XFA
                result["events"].append(event)

        # Track winning day (for payout eligibility)
        if self.daily_pnl > 0:
            self.winning_days += 1

        # LIVE: check capital unlock
        if self.current_stage == TopstepStage.LIVE:
            unlock_event = self._check_live_unlock(day)
            if unlock_event:
                result["events"].append(unlock_event)

            # Record halt state
            if self.halted_until_19est:
                result["halt"] = True

        self._reset_daily()
        return result

    # ----- Stage transitions -----

    def _transition_to(self, new_stage: TopstepStage, day: str,
                       trigger: str) -> LifecycleEvent:
        """Execute a stage transition."""
        old_stage = self.current_stage

        if new_stage == TopstepStage.XFA:
            # EVAL → XFA: balance carries over, reset peak for new MLL tracking
            self._xfa_config.starting_balance = self.balance
            self.peak_balance = self.balance
            self.payouts_taken = 0

        elif new_stage == TopstepStage.LIVE:
            # XFA → LIVE: calculate tradable + reserve
            self.tradable_balance = min(self.balance, LIVE_TRADABLE_CAP)
            remainder = max(self.balance - LIVE_TRADABLE_CAP, Decimal("0"))
            self.reserve_balance = remainder
            self.reserve_per_block = (
                remainder / Decimal(LIVE_UNLOCK_LEVELS)
                if remainder > 0 else Decimal("0")
            )
            self.unlocks_remaining = (LIVE_UNLOCK_LEVELS
                                      if remainder > 0 else 0)
            self.cumulative_live_profit = Decimal("0")
            self.halted_until_19est = False
            self.peak_balance = self.tradable_balance

        self.current_stage = new_stage

        event = LifecycleEvent(
            event_id=f"LCE-{uuid.uuid4().hex[:12].upper()}",
            event_type="STAGE_TRANSITION",
            from_stage=old_stage.value,
            to_stage=new_stage.value,
            trigger=trigger,
            balance_at_event=self.balance,
            payouts_taken=self.payouts_taken,
            tradable_balance=self.tradable_balance,
            reserve_balance=self.reserve_balance,
            details={"day": day},
        )
        self.events.append(event)

        logger.info("Stage transition: %s → %s on day %s (trigger: %s, "
                     "balance: %s)", old_stage.value, new_stage.value,
                     day, trigger, self.balance)
        return event

    def handle_failure(self, day: str, trigger: str) -> LifecycleEvent:
        """Handle failure: charge fee, revert to fresh EVAL.

        Logs $226.60 fee. Resets balance to $150K. Resets all counters.
        """
        old_stage = self.current_stage
        fee = ACCOUNT_LOSS_FEE
        self.total_fees += fee
        self.total_resets += 1

        event = LifecycleEvent(
            event_id=f"LCE-{uuid.uuid4().hex[:12].upper()}",
            event_type="FAILURE",
            from_stage=old_stage.value,
            to_stage=TopstepStage.EVAL.value,
            trigger=trigger,
            balance_at_event=self.balance,
            fee_charged=fee,
            payouts_taken=self.payouts_taken,
            tradable_balance=self.tradable_balance,
            reserve_balance=self.reserve_balance,
            details={"day": day, "reason": trigger},
        )
        self.events.append(event)

        logger.warning("Account failure: %s on day %s (stage: %s, "
                        "balance: %s). Fee: $%s. Reverting to EVAL.",
                        trigger, day, old_stage.value, self.balance, fee)

        # Reset to fresh EVAL
        self.current_stage = TopstepStage.EVAL
        self.balance = EVAL_STARTING_BALANCE
        self.peak_balance = EVAL_STARTING_BALANCE
        self.payouts_taken = 0
        self.winning_days = 0
        self.tradable_balance = Decimal("0")
        self.reserve_balance = Decimal("0")
        self.reserve_per_block = Decimal("0")
        self.unlocks_remaining = 0
        self.cumulative_live_profit = Decimal("0")
        self.halted_until_19est = False
        self._eval_config = TopstepEvalAccount(
            starting_balance=EVAL_STARTING_BALANCE)
        self._xfa_config = TopstepXFAAccount(
            starting_balance=EVAL_STARTING_BALANCE)

        return event

    # ----- Payouts -----

    def process_payout(self, amount, day: str) -> dict:
        """Process a payout withdrawal.

        XFA: 10% commission, increments payout counter.
             After 5 payouts → transition to LIVE.
        LIVE: 0% commission.

        Returns:
            dict with: success, net_amount, commission, transition
        """
        amt = Decimal(str(amount))
        if self.current_stage == TopstepStage.EVAL:
            return {"success": False, "reason": "NO_PAYOUTS_IN_EVAL"}

        if self.current_stage == TopstepStage.XFA:
            commission = amt * self._xfa_config.payout_commission_rate
            net = amt - commission
            self.balance -= amt
            self.payouts_taken += 1

            event = LifecycleEvent(
                event_id=f"LCE-{uuid.uuid4().hex[:12].upper()}",
                event_type="PAYOUT",
                from_stage="XFA", to_stage="XFA",
                trigger="PAYOUT_REQUESTED",
                balance_at_event=self.balance,
                payout_amount=amt, payout_net=net,
                payouts_taken=self.payouts_taken,
                details={"day": day, "commission": commission},
            )
            self.events.append(event)

            result = {"success": True, "net_amount": net,
                      "commission": commission, "transition": None}

            # Check XFA → LIVE transition
            if self.payouts_taken >= XFA_MAX_PAYOUTS:
                trans_event = self._transition_to(
                    TopstepStage.LIVE, day, "PAYOUTS_EXHAUSTED")
                result["transition"] = trans_event

            return result

        elif self.current_stage == TopstepStage.LIVE:
            net = amt
            self.tradable_balance -= amt
            self.balance -= amt

            event = LifecycleEvent(
                event_id=f"LCE-{uuid.uuid4().hex[:12].upper()}",
                event_type="PAYOUT",
                from_stage="LIVE", to_stage="LIVE",
                trigger="PAYOUT_REQUESTED",
                balance_at_event=self.balance,
                payout_amount=amt, payout_net=net,
                payouts_taken=self.payouts_taken,
                tradable_balance=self.tradable_balance,
                reserve_balance=self.reserve_balance,
                details={"day": day},
            )
            self.events.append(event)
            return {"success": True, "net_amount": net,
                    "commission": Decimal("0"), "transition": None}

        return {"success": False, "reason": "UNKNOWN_STAGE"}

    # ----- Live capital unlock -----

    def _check_live_unlock(self, day: str) -> LifecycleEvent | None:
        """Check if cumulative Live profit unlocks a reserve block."""
        if self.unlocks_remaining <= 0 or self.reserve_per_block <= 0:
            return None

        unlocks_earned = int(self.cumulative_live_profit // LIVE_UNLOCK_PROFIT)
        unlocks_already = LIVE_UNLOCK_LEVELS - self.unlocks_remaining
        new_unlocks = max(unlocks_earned - unlocks_already, 0)

        if new_unlocks <= 0:
            return None

        # Unlock blocks (cap at remaining)
        actual_unlocks = min(new_unlocks, self.unlocks_remaining)
        unlock_amount = actual_unlocks * self.reserve_per_block
        self.tradable_balance += unlock_amount
        self.reserve_balance -= unlock_amount
        self.unlocks_remaining -= actual_unlocks

        event = LifecycleEvent(
            event_id=f"LCE-{uuid.uuid4().hex[:12].upper()}",
            event_type="CAPITAL_UNLOCK",
            from_stage="LIVE", to_stage="LIVE",
            trigger="PROFIT_THRESHOLD_MET",
            balance_at_event=self.balance,
            tradable_balance=self.tradable_balance,
            reserve_balance=self.reserve_balance,
            details={
                "day": day,
                "blocks_unlocked": actual_unlocks,
                "amount_unlocked": unlock_amount,
                "cumulative_profit": self.cumulative_live_profit,
            },
        )
        self.events.append(event)

        logger.info("Live capital unlock: %d blocks ($%s) unlocked. "
                     "Tradable: $%s, Reserve: $%s",
                     actual_unlocks, unlock_amount,
                     self.tradable_balance, self.reserve_balance)
        return event

    # ----- Helpers -----

    def _reset_daily(self):
        """Reset daily counters for next trading day."""
        self.daily_pnl = Decimal("0")
        self.daily_peak_pnl = Decimal("0")
        self.halted_until_19est = False

    def get_state_snapshot(self) -> dict:
        """Return full account state for persistence or reporting."""
        return {
            "current_stage": self.current_stage.value,
            "balance": self.balance,
            "peak_balance": self.peak_balance,
            "payouts_taken": self.payouts_taken,
            "winning_days": self.winning_days,
            "tradable_balance": self.tradable_balance,
            "reserve_balance": self.reserve_balance,
            "reserve_per_block": self.reserve_per_block,
            "unlocks_remaining": self.unlocks_remaining,
            "cumulative_live_profit": self.cumulative_live_profit,
            "total_fees": self.total_fees,
            "total_resets": self.total_resets,
            "events_count": len(self.events),
            "halted": self.halted_until_19est,
        }

    def to_tsm_dict(self) -> dict:
        """Export current state as a TSM-compatible config dict.

        This can be passed to run_account_aware_replay() as account_config.
        """
        if self.current_stage == TopstepStage.EVAL:
            return {
                "classification": {"provider": "TopstepX",
                                   "category": "PROP_EVAL",
                                   "stage": "STAGE_1"},
                "starting_balance": self._eval_config.starting_balance,
                "max_drawdown_limit": EVAL_MLL,
                "max_contracts": EVAL_MAX_CONTRACTS,
                "profit_target": EVAL_PROFIT_TARGET,
                "scaling_plan_active": False,
                "scaling_plan": None,
            }
        elif self.current_stage == TopstepStage.XFA:
            return {
                "classification": {"provider": "TopstepX",
                                   "category": "PROP_FUNDED",
                                   "stage": "XFA"},
                "starting_balance": self._xfa_config.starting_balance,
                "max_drawdown_limit": XFA_MLL,
                "max_contracts": EVAL_MAX_CONTRACTS,
                "scaling_plan_active": True,
                "scaling_plan": self._xfa_config.scaling_plan,
                "consistency_rule": {
                    "max_daily_profit":
                        self._xfa_config.consistency_rule_max_daily_profit,
                },
            }
        else:  # LIVE
            return {
                "classification": {"provider": "TopstepX",
                                   "category": "PROP_FUNDED",
                                   "stage": "LIVE"},
                "starting_balance": self.tradable_balance,
                "max_drawdown_limit": None,
                "max_daily_drawdown": LIVE_DAILY_DRAWDOWN,
                "low_balance_threshold": LIVE_LOW_BALANCE_THRESHOLD,
                "low_balance_daily_drawdown": LIVE_LOW_BALANCE_DAILY_DD,
                "max_contracts": EVAL_MAX_CONTRACTS,
                "scaling_plan_active": False,
                "scaling_plan": None,
                "tradable_balance": self.tradable_balance,
                "reserve_balance": self.reserve_balance,
            }
