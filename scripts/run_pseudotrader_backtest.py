#!/usr/bin/env python3
"""Run pseudotrader backtest with historical P1/P2 trade data.

Usage:
    # Single asset — full lifecycle (EVAL → XFA → LIVE)
    python scripts/run_pseudotrader_backtest.py --asset ES

    # Single asset — account-aware replay (single stage)
    python scripts/run_pseudotrader_backtest.py --asset ES --mode account-aware --stage XFA

    # All assets with P2 data
    python scripts/run_pseudotrader_backtest.py --all

    # Date range filter
    python scripts/run_pseudotrader_backtest.py --asset ES --start 2020-01-01 --end 2025-12-31

    # Custom OR range (affects dollar P&L scale)
    python scripts/run_pseudotrader_backtest.py --asset ES --or-range 5.0

Modes:
    multistage      Full EVAL → XFA → LIVE lifecycle (default)
    account-aware   Single-stage replay with account constraints
    basic           Simple Sharpe/PBO comparison (original pseudotrader)
"""

import argparse
import json
import logging
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

# Add captain-system to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.trade_source import load_trades
from shared.account_lifecycle import (
    MultiStageTopstepAccount, TopstepStage,
    TopstepEvalAccount, TopstepXFAAccount, TopstepLiveAccount,
    ACCOUNT_LOSS_FEE, EVAL_STARTING_BALANCE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metric helpers (standalone — no QuestDB dependency)
# ---------------------------------------------------------------------------

def _sharpe(returns):
    if len(returns) < 2:
        return 0.0
    import numpy as np
    arr = np.array(returns)
    std = arr.std()
    return float(arr.mean() / std * math.sqrt(252)) if std > 1e-10 else 0.0


def _max_dd(equity_curve):
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _win_rate(pnl_list):
    if not pnl_list:
        return 0.0
    return sum(1 for p in pnl_list if p > 0) / len(pnl_list)


# ---------------------------------------------------------------------------
# Backtest modes
# ---------------------------------------------------------------------------

def run_multistage(trades, starting_balance=EVAL_STARTING_BALANCE):
    """Full EVAL → XFA → LIVE lifecycle replay."""
    acct = MultiStageTopstepAccount(starting_balance=starting_balance)

    by_day = defaultdict(list)
    for t in trades:
        by_day[t["day"]].append(t)

    per_stage_pnl = defaultdict(list)
    taken = 0
    blocked = 0

    for day in sorted(by_day.keys()):
        day_trades = sorted(by_day[day], key=lambda t: t["ts"])
        day_pnl = 0.0
        stage_before = acct.current_stage.value

        for trade in day_trades:
            result = acct.process_trade(trade)
            if result["allowed"]:
                day_pnl += result["adjusted_pnl"]
                taken += 1
            else:
                blocked += 1
            if result.get("breach_type") == "MLL":
                break

        per_stage_pnl[stage_before].append(day_pnl)
        acct.end_of_day(day)

    snap = acct.get_state_snapshot()

    # Per-stage metrics
    stage_metrics = {}
    for stage, pnl_list in per_stage_pnl.items():
        import numpy as np
        eq = list(np.cumsum(pnl_list))
        stage_metrics[stage] = {
            "days": len(pnl_list),
            "net_pnl": sum(pnl_list),
            "sharpe": _sharpe(pnl_list),
            "max_dd_pct": _max_dd(eq),
            "win_rate": _win_rate(pnl_list),
            "avg_daily_pnl": sum(pnl_list) / len(pnl_list) if pnl_list else 0,
        }

    return {
        "mode": "multistage",
        "snap": snap,
        "stage_metrics": stage_metrics,
        "taken": taken,
        "blocked": blocked,
        "events": acct.events,
    }


def run_account_aware(trades, stage="XFA"):
    """Single-stage replay with account constraints."""
    if stage == "EVAL":
        config = TopstepEvalAccount()
    elif stage == "XFA":
        config = TopstepXFAAccount()
    else:
        config = TopstepLiveAccount(starting_balance=30_000, tradable_cap=30_000)

    by_day = defaultdict(list)
    for t in trades:
        by_day[t["day"]].append(t)

    daily_pnls = []
    balance = config.starting_balance or 150_000
    peak = balance
    breaches = {"mll": 0, "scaling": 0, "consistency": 0}
    mll_breached = False

    for day in sorted(by_day.keys()):
        if mll_breached:
            daily_pnls.append(0.0)
            continue

        day_pnl = 0.0
        for trade in sorted(by_day[day], key=lambda t: t["ts"]):
            pnl = trade["pnl"]

            # MLL check (EVAL/XFA only)
            if config.max_drawdown_limit and (peak - balance) >= config.max_drawdown_limit:
                mll_breached = True
                breaches["mll"] += 1
                break

            # Scaling (XFA)
            if hasattr(config, "get_scaling_tier_micros") and config.scaling_plan_active:
                tier = config.get_scaling_tier_micros(balance)
                trade_micros = trade["contracts"] * 10
                if trade_micros > tier:
                    pnl = pnl * (tier / trade_micros)
                    breaches["scaling"] += 1

            balance += pnl
            peak = max(peak, balance)
            day_pnl += pnl

        # Consistency (XFA)
        if hasattr(config, "consistency_rule_max_daily_profit"):
            if day_pnl > config.consistency_rule_max_daily_profit:
                breaches["consistency"] += 1

        daily_pnls.append(day_pnl)

    import numpy as np
    eq = list(np.cumsum(daily_pnls))

    return {
        "mode": f"account-aware ({stage})",
        "days": len(daily_pnls),
        "net_pnl": sum(daily_pnls),
        "final_balance": balance,
        "sharpe": _sharpe(daily_pnls),
        "max_dd_pct": _max_dd(eq),
        "win_rate": _win_rate(daily_pnls),
        "breaches": breaches,
        "mll_breached": mll_breached,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_multistage_results(asset, results):
    snap = results["snap"]
    print(f"\n{'='*60}")
    print(f"  MULTISTAGE PSEUDOTRADER — {asset}")
    print(f"{'='*60}")
    print(f"  Final stage:    {snap['current_stage']}")
    print(f"  Final balance:  ${snap['balance']:>12,.2f}")
    print(f"  Tradable:       ${snap['tradable_balance']:>12,.2f}")
    print(f"  Reserve:        ${snap['reserve_balance']:>12,.2f}")
    print(f"  Payouts taken:  {snap['payouts_taken']}")
    print(f"  Total resets:   {snap['total_resets']}")
    print(f"  Total fees:     ${snap['total_fees']:>12,.2f}")
    print(f"  Trades taken:   {results['taken']}")
    print(f"  Trades blocked: {results['blocked']}")

    print(f"\n  Per-stage breakdown:")
    print(f"  {'Stage':<8} {'Days':>6} {'Net P&L':>12} {'Sharpe':>8} {'MaxDD%':>8} {'WinRate':>8} {'Avg/Day':>10}")
    print(f"  {'-'*62}")
    for stage, m in results["stage_metrics"].items():
        print(f"  {stage:<8} {m['days']:>6} ${m['net_pnl']:>10,.2f} {m['sharpe']:>8.3f} {m['max_dd_pct']:>7.2%} {m['win_rate']:>7.1%} ${m['avg_daily_pnl']:>9,.2f}")

    if results["events"]:
        print(f"\n  Lifecycle events:")
        for e in results["events"]:
            fee_str = f" (fee: ${e.fee_charged:.2f})" if e.fee_charged > 0 else ""
            print(f"    {e.event_type:<20} {e.from_stage} -> {e.to_stage}  "
                  f"trigger={e.trigger}, balance=${e.balance_at_event:,.2f}{fee_str}")
    print()


def print_account_aware_results(asset, results):
    print(f"\n{'='*60}")
    print(f"  ACCOUNT-AWARE REPLAY — {asset} ({results['mode']})")
    print(f"{'='*60}")
    print(f"  Trading days:   {results['days']}")
    print(f"  Net P&L:        ${results['net_pnl']:>12,.2f}")
    print(f"  Final balance:  ${results['final_balance']:>12,.2f}")
    print(f"  Sharpe:         {results['sharpe']:>8.3f}")
    print(f"  Max Drawdown:   {results['max_dd_pct']:>7.2%}")
    print(f"  Win Rate:       {results['win_rate']:>7.1%}")
    print(f"  MLL breached:   {results['mll_breached']}")
    print(f"  Breaches:       {results['breaches']}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ASSETS_WITH_D22 = ["ES", "M2K", "MES", "MGC", "MNQ", "MYM", "NKD", "NQ", "ZB", "ZN", "ZT"]


def main():
    parser = argparse.ArgumentParser(description="Pseudotrader backtest runner")
    parser.add_argument("--asset", type=str, default="ES", help="Asset symbol (default: ES)")
    parser.add_argument("--all", action="store_true", help="Run all assets with P2 trade data")
    parser.add_argument("--mode", choices=["multistage", "account-aware", "basic"],
                        default="multistage", help="Replay mode (default: multistage)")
    parser.add_argument("--stage", choices=["EVAL", "XFA", "LIVE"], default="XFA",
                        help="Account stage for account-aware mode (default: XFA)")
    parser.add_argument("--start", type=str, default=None, help="Start date filter (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date filter (YYYY-MM-DD)")
    parser.add_argument("--or-range", type=float, default=None,
                        help="Override avg opening range in points (affects PnL scale)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    assets = ASSETS_WITH_D22 if args.all else [args.asset.upper()]

    all_results = {}
    for asset in assets:
        trades = load_trades(
            source="synthetic", asset=asset,
            start_date=args.start, end_date=args.end,
            or_range_points=args.or_range,
        )

        if not trades:
            logger.warning("No trades found for %s — skipping", asset)
            continue

        logger.info("Running %s backtest for %s (%d trades, %s to %s)",
                     args.mode, asset, len(trades), trades[0]["day"], trades[-1]["day"])

        if args.mode == "multistage":
            results = run_multistage(trades)
            if not args.json:
                print_multistage_results(asset, results)
        elif args.mode == "account-aware":
            results = run_account_aware(trades, stage=args.stage)
            if not args.json:
                print_account_aware_results(asset, results)
        else:
            # Basic mode — just compute metrics on raw trades
            daily_pnls = []
            by_day = defaultdict(float)
            for t in trades:
                by_day[t["day"]] += t["pnl"]
            daily_pnls = [by_day[d] for d in sorted(by_day)]
            import numpy as np
            eq = list(np.cumsum(daily_pnls))
            results = {
                "mode": "basic",
                "days": len(daily_pnls),
                "net_pnl": sum(daily_pnls),
                "sharpe": _sharpe(daily_pnls),
                "max_dd_pct": _max_dd(eq),
                "win_rate": _win_rate(daily_pnls),
            }
            if not args.json:
                print(f"\n  BASIC REPLAY — {asset}: {len(trades)} trades, "
                      f"Sharpe={results['sharpe']:.3f}, "
                      f"PnL=${results['net_pnl']:,.2f}, "
                      f"WinRate={results['win_rate']:.1%}\n")

        all_results[asset] = results

    if args.json:
        # Serialize (strip non-serializable objects)
        def _clean(obj):
            if hasattr(obj, "__dict__"):
                return {k: v for k, v in obj.__dict__.items()
                        if not k.startswith("_")}
            return str(obj)
        print(json.dumps(all_results, default=_clean, indent=2))


if __name__ == "__main__":
    main()
