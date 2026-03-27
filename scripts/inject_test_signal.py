"""Inject a synthetic test signal into the Captain pipeline via Redis.

Tests the full downstream flow:
  Redis publish → Command B1 routing → GUI push → signal card display

Usage:
  python scripts/inject_test_signal.py [--direction BUY|SELL] [--price 5800.0]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.redis_client import get_redis_client, signals_channel


def build_test_signal(direction: str = "BUY", price: float = 0.0,
                      user_id: str = "primary_user",
                      account_id: str = "20260837") -> dict:
    """Build a realistic signal payload matching B6 output format."""
    signal_id = f"SIG-TEST-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    # Use live price if available, otherwise default
    if price <= 0:
        try:
            from shared.topstep_stream import quote_cache
            quote = quote_cache.get(
                os.environ.get("TOPSTEP_CONTRACT_ID", "CON.F.US.EP.M26")
            )
            if quote and quote.get("lastPrice"):
                price = float(quote["lastPrice"])
        except Exception:
            pass
    if price <= 0:
        price = 5800.0

    # OR-range based TP/SL (typical for MOST strategy)
    or_range = price * 0.003  # ~0.3% of price
    sl_mult = 1.5
    tp_mult = 2.0

    if direction == "BUY":
        dir_int = 1
        tp_level = round(price + tp_mult * or_range, 2)
        sl_level = round(price - sl_mult * or_range, 2)
    else:
        dir_int = -1
        tp_level = round(price - tp_mult * or_range, 2)
        sl_level = round(price + sl_mult * or_range, 2)

    signal = {
        "signal_id": signal_id,
        "user_id": user_id,
        "asset": "ES",
        "session": 1,  # NY
        "timestamp": now,
        "direction": dir_int,
        "tp_level": tp_level,
        "sl_level": sl_level,
        "sl_method": "OR_RANGE",
        "entry_conditions": {
            "or_high": round(price + or_range / 2, 2),
            "or_low": round(price - or_range / 2, 2),
            "or_range": round(or_range, 2),
        },
        "per_account": {
            account_id: {
                "contracts": 1,
                "recommendation": "TRADE",
                "skip_reason": None,
                "account_name": "150KTC-V2-551001-19064435",
                "category": "PROP_FUNDED",
                "risk_goal": "CAPITAL_PRESERVATION",
                "remaining_mdd": 4500.0,
                "remaining_mll": 3000.0,
                "pass_probability": 0.72,
                "risk_budget_pct": 0.5,
            },
        },
        "aim_breakdown": {
            "4": {"modifier": 1.05, "confidence": 0.8, "reason_tag": "IVTS bullish"},
            "11": {"modifier": 0.95, "confidence": 0.7, "reason_tag": "VIX neutral"},
            "12": {"modifier": 1.0, "confidence": 0.9, "reason_tag": "Spread normal"},
        },
        "combined_modifier": 1.0,
        "regime_state": "LOW_VOL",
        "regime_probs": {"LOW_VOL": 0.78, "HIGH_VOL": 0.22},
        "expected_edge": 0.087,
        "win_rate": 0.54,
        "payoff_ratio": 1.6,
        "user_total_capital": 150000.0,
        "user_daily_pnl": 0.0,
        "quality_score": 0.82,
        "quality_multiplier": 1.0,
        "data_maturity": 1.0,
        "confidence_tier": "HIGH",
    }

    return signal


def inject_signal(signal: dict, user_id: str = "primary_user"):
    """Publish signal to Redis captain:signals:{user_id} channel."""
    payload = {
        "user_id": user_id,
        "session_id": 1,
        "timestamp": signal["timestamp"],
        "signals": [signal],
        "below_threshold": [],
    }

    client = get_redis_client()
    channel = signals_channel(user_id)
    msg = json.dumps(payload)
    subscribers = client.publish(channel, msg)

    print(f"Published to {channel} ({subscribers} subscriber(s))")
    print(f"  Signal ID: {signal['signal_id']}")
    print(f"  Direction: {'BUY' if signal['direction'] == 1 else 'SELL'}")
    print(f"  TP: {signal['tp_level']}, SL: {signal['sl_level']}")
    print(f"  Confidence: {signal['confidence_tier']}")
    print(f"  Quality: {signal['quality_score']}")

    return subscribers


def main():
    parser = argparse.ArgumentParser(description="Inject test signal into Captain pipeline")
    parser.add_argument("--direction", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--price", type=float, default=0.0,
                        help="Entry price (0 = auto from live stream)")
    parser.add_argument("--user", default="primary_user")
    parser.add_argument("--account", default="20260837")
    args = parser.parse_args()

    print("=" * 50)
    print("CAPTAIN — Test Signal Injection")
    print("=" * 50)

    signal = build_test_signal(
        direction=args.direction,
        price=args.price,
        user_id=args.user,
        account_id=args.account,
    )

    subs = inject_signal(signal, args.user)

    if subs == 0:
        print("\nWARNING: 0 subscribers — captain-command may not be listening.")
        print("Check: docker-compose logs captain-command | grep 'Redis listener'")
    else:
        print(f"\nSignal delivered to {subs} subscriber(s).")
        print("Check the GUI — signal should appear in Pending Signals panel.")


if __name__ == "__main__":
    main()
