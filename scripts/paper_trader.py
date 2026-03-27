"""Captain Paper Trader — automated simulation using live TopstepX market data.

Generates ORB-style signals, auto-takes them, tracks positions against
live ES prices, closes on TP/SL hits, and updates PnL in real time.

SAFETY: This script NEVER calls TopstepX order/trade APIs.
It only reads market prices and writes to QuestDB + Redis.

Usage:
  python scripts/paper_trader.py [--interval 30] [--max-positions 3]
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

import threading
import websocket as ws_lib

from shared.topstep_client import get_topstep_client
from shared.topstep_stream import quote_cache
from shared.redis_client import get_redis_client, signals_channel, CH_ALERTS
from shared.questdb_client import get_cursor

logging.basicConfig(
    level=logging.INFO,
    format="[PAPER] %(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONTRACT_ID = os.environ.get("TOPSTEP_CONTRACT_ID", "CON.F.US.EP.M26")
USER_ID = "primary_user"
ACCOUNT_ID = "20260837"
ACCOUNT_NAME = "150KTC-V2-551001-19064435"
TICK_SIZE = 0.25
TICK_VALUE = 12.50
POINT_VALUE = 50.0  # ES: $50 per point


class Position:
    """In-memory position tracker."""

    def __init__(self, trade_id: str, signal_id: str, direction: int,
                 entry_price: float, contracts: int, tp: float, sl: float):
        self.trade_id = trade_id
        self.signal_id = signal_id
        self.direction = direction  # 1=long, -1=short
        self.entry_price = entry_price
        self.contracts = contracts
        self.tp = tp
        self.sl = sl
        self.entry_time = datetime.now(timezone.utc)
        self.pnl = 0.0
        self.status = "OPEN"

    def update_pnl(self, current_price: float) -> float:
        """Compute unrealised PnL."""
        self.pnl = (current_price - self.entry_price) * self.direction * \
                    self.contracts * POINT_VALUE
        return self.pnl

    def check_exit(self, current_price: float) -> str | None:
        """Check if TP or SL is hit. Returns 'TP', 'SL', or None."""
        if self.direction == 1:  # Long
            if current_price >= self.tp:
                return "TP"
            if current_price <= self.sl:
                return "SL"
        else:  # Short
            if current_price <= self.tp:
                return "TP"
            if current_price >= self.sl:
                return "SL"
        return None


class PaperTrader:
    """Automated paper trading engine using live market data."""

    def __init__(self, signal_interval: int = 60, max_positions: int = 3):
        self.signal_interval = signal_interval  # seconds between signals
        self.max_positions = max_positions
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[Position] = []
        self.cumulative_pnl = 0.0
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.redis = get_redis_client()
        self.stream: MarketStream | None = None
        self._last_signal_time = 0.0
        # ORB parameters from locked strategy (M4 k=017)
        self.or_pct = 0.003       # OR range as % of price (~0.3%)
        self.sl_multiple = 1.5
        self.tp_multiple = 2.0

    def start(self):
        """Start the paper trading loop."""
        logger.info("=" * 60)
        logger.info("CAPTAIN PAPER TRADER — Live Simulation")
        logger.info("=" * 60)
        logger.info("Contract: %s", CONTRACT_ID)
        logger.info("Signal interval: %ds", self.signal_interval)
        logger.info("Max positions: %d", self.max_positions)
        logger.info("SAFETY: No real orders will be placed")
        logger.info("=" * 60)

        # Connect to TopstepX market stream
        client = get_topstep_client()
        client.authenticate()
        logger.info("TopstepX authenticated")

        self._client = client
        self._ws = None
        self._ws_thread = None

        # Start raw WebSocket stream (more reliable than signalrcore)
        self._start_ws_stream(client.current_token)

        # Wait for first quote
        price = None
        for _ in range(15):
            price = self._get_price()
            if price:
                break
            time.sleep(1)

        if not price:
            logger.error("Cannot get market price after 15s — aborting")
            return

        logger.info("Starting price: $%.2f — beginning simulation", price)

        try:
            self._run_loop()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.stream.stop()
            self._print_summary()

    def _run_loop(self):
        """Main simulation loop."""
        last_price = None
        no_price_count = 0

        while True:
            price = self._get_price()

            if price is None:
                no_price_count += 1
                if no_price_count % 30 == 0:
                    logger.warning("No price data for %ds — stream may be down",
                                   no_price_count)
                    # Try to reconnect stream
                    try:
                        self.stream.stop()
                        time.sleep(1)
                        self._client.validate_token()
                        self.stream = MarketStream(
                            token=self._client.current_token,
                            contract_id=CONTRACT_ID,
                            on_quote=self._on_quote,
                        )
                        self.stream.start()
                        logger.info("MarketStream reconnected")
                    except Exception as exc:
                        logger.debug("Reconnect failed: %s", exc)
                time.sleep(1)
                continue

            no_price_count = 0
            last_price = price

            # Monitor open positions
            self._monitor_positions(price)

            # Generate new signal if interval elapsed and room for more
            now = time.time()
            if (now - self._last_signal_time >= self.signal_interval and
                    len(self.positions) < self.max_positions):
                self._generate_and_take_signal(price)
                self._last_signal_time = now

            time.sleep(0.5)

    def _get_price(self) -> float | None:
        """Get latest price from stream cache."""
        quote = quote_cache.get(CONTRACT_ID)
        if quote and isinstance(quote, dict):
            p = quote.get("lastPrice")
            if p:
                return float(p)
        return None

    def _get_bid_ask(self) -> tuple[float, float]:
        quote = quote_cache.get(CONTRACT_ID)
        if quote and isinstance(quote, dict):
            bid = float(quote.get("bestBid", 0))
            ask = float(quote.get("bestAsk", 0))
            return bid, ask
        return 0.0, 0.0

    def _generate_and_take_signal(self, price: float):
        """Generate an ORB signal and immediately take it."""
        # Direction based on simple momentum (random for now, can be enhanced)
        bid, ask = self._get_bid_ask()
        mid = (bid + ask) / 2 if bid and ask else price

        # Simple mean-reversion signal: if price > mid → sell, else buy
        # Add randomness for variety
        if random.random() < 0.5:
            direction = 1   # BUY
            dir_str = "BUY"
        else:
            direction = -1  # SELL
            dir_str = "SELL"

        or_range = price * self.or_pct
        if direction == 1:
            tp = round(price + self.tp_multiple * or_range, 2)
            sl = round(price - self.sl_multiple * or_range, 2)
        else:
            tp = round(price - self.tp_multiple * or_range, 2)
            sl = round(price + self.sl_multiple * or_range, 2)

        signal_id = f"SIG-PAPER-{uuid.uuid4().hex[:8].upper()}"
        trade_id = f"TRD-PAPER-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build and publish signal
        signal = {
            "signal_id": signal_id,
            "user_id": USER_ID,
            "asset": "ES",
            "session": 1,
            "timestamp": now_iso,
            "direction": direction,
            "tp_level": tp,
            "sl_level": sl,
            "sl_method": "OR_RANGE",
            "entry_conditions": {
                "or_range": round(or_range, 2),
                "entry_price": price,
            },
            "per_account": {
                ACCOUNT_ID: {
                    "contracts": 1,
                    "recommendation": "TRADE",
                    "skip_reason": None,
                    "account_name": ACCOUNT_NAME,
                    "category": "PROP_FUNDED",
                    "risk_goal": "CAPITAL_PRESERVATION",
                    "remaining_mdd": max(4500 - abs(self.daily_pnl), 0),
                    "remaining_mll": max(3000 - abs(self.daily_pnl), 0),
                    "pass_probability": 0.72,
                    "risk_budget_pct": 0.5,
                },
            },
            "combined_modifier": 1.0,
            "regime_state": "LOW_VOL",
            "regime_probs": {"LOW_VOL": 0.78, "HIGH_VOL": 0.22},
            "expected_edge": round(random.uniform(0.05, 0.12), 3),
            "win_rate": 0.54,
            "payoff_ratio": 1.6,
            "user_total_capital": 150000 + self.cumulative_pnl,
            "user_daily_pnl": self.daily_pnl,
            "quality_score": round(random.uniform(0.7, 0.95), 2),
            "quality_multiplier": 1.0,
            "data_maturity": 1.0,
            "confidence_tier": random.choice(["HIGH", "HIGH", "MEDIUM"]),
        }

        # Publish to Redis
        payload = {
            "user_id": USER_ID,
            "session_id": 1,
            "timestamp": now_iso,
            "signals": [signal],
            "below_threshold": [],
        }
        self.redis.publish(signals_channel(USER_ID), json.dumps(payload))

        # Create position
        pos = Position(trade_id, signal_id, direction, price, 1, tp, sl)
        self.positions[trade_id] = pos

        # Log to QuestDB D03
        self._log_trade_open(pos)

        logger.info(
            "%s %s ES @ $%.2f | TP=$%.2f SL=$%.2f | ID=%s",
            dir_str, "1 lot", price, tp, sl, trade_id[:16],
        )

    def _monitor_positions(self, price: float):
        """Check all open positions for TP/SL hits."""
        to_close = []
        for tid, pos in self.positions.items():
            pos.update_pnl(price)
            exit_type = pos.check_exit(price)
            if exit_type:
                to_close.append((tid, exit_type, price))

        for tid, exit_type, exit_price in to_close:
            self._close_position(tid, exit_type, exit_price)

    def _close_position(self, trade_id: str, exit_type: str, exit_price: float):
        """Close a position and update PnL."""
        pos = self.positions.pop(trade_id)
        pos.status = exit_type
        final_pnl = pos.update_pnl(exit_price)

        # Subtract commission ($2.80 round trip per contract)
        commission = 2.80 * pos.contracts
        net_pnl = final_pnl - commission

        self.cumulative_pnl += net_pnl
        self.daily_pnl += net_pnl
        self.trade_count += 1
        if net_pnl > 0:
            self.win_count += 1
        self.closed_trades.append(pos)

        # Log to QuestDB D03
        self._log_trade_close(pos, exit_price, net_pnl, commission)

        # Publish trade outcome to Redis
        outcome = {
            "trade_id": trade_id,
            "asset": "ES",
            "pnl": round(net_pnl, 2),
            "exit_type": exit_type,
            "direction": "LONG" if pos.direction == 1 else "SHORT",
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "contracts": pos.contracts,
        }
        self.redis.publish("captain:trade_outcomes", json.dumps(outcome))

        dir_str = "LONG" if pos.direction == 1 else "SHORT"
        pnl_str = f"+${net_pnl:.2f}" if net_pnl >= 0 else f"-${abs(net_pnl):.2f}"
        logger.info(
            "CLOSED %s %s @ $%.2f → $%.2f | %s | PnL=%s | Cumulative=$%.2f",
            dir_str, "ES", pos.entry_price, exit_price, exit_type,
            pnl_str, self.cumulative_pnl,
        )

    def _update_capital_silo(self, price: float):
        """Update unrealised PnL for display."""
        total_unrealised = sum(
            p.update_pnl(price) for p in self.positions.values()
        )
        # The GUI reads capital from TopstepX REST (which won't change)
        # but we can push an alert with current sim PnL
        pass  # PnL is tracked in D03 and shown via positions panel

    def _log_trade_open(self, pos: Position):
        """Insert OPEN trade into P3-D03."""
        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d03_trade_outcome_log (
                        trade_id, user_id, account_id, asset, direction,
                        entry_price, contracts, outcome, entry_time,
                        session, ts
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                    (
                        pos.trade_id, USER_ID, ACCOUNT_ID, "ES",
                        pos.direction,  # INT: 1 or -1
                        pos.entry_price, pos.contracts, "OPEN",
                        pos.entry_time.isoformat(), 1,  # session 1 = NY
                    ),
                )
        except Exception as exc:
            logger.warning("D03 open log failed: %s", exc)

    def _log_trade_close(self, pos: Position, exit_price: float,
                         net_pnl: float, commission: float):
        """Insert closed trade into P3-D03."""
        try:
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d03_trade_outcome_log (
                        trade_id, user_id, account_id, asset, direction,
                        entry_price, exit_price, contracts,
                        gross_pnl, commission, pnl, outcome,
                        entry_time, exit_time, session, ts
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())""",
                    (
                        pos.trade_id, USER_ID, ACCOUNT_ID, "ES",
                        pos.direction,  # INT: 1 or -1
                        pos.entry_price, exit_price, pos.contracts,
                        round(net_pnl + commission, 2), commission,
                        round(net_pnl, 2), pos.status,
                        pos.entry_time.isoformat(),
                        datetime.now(timezone.utc).isoformat(), 1,  # session 1 = NY
                    ),
                )
        except Exception as exc:
            logger.warning("D03 close log failed: %s", exc)

    def _print_summary(self):
        """Print end-of-session summary."""
        win_rate = (self.win_count / self.trade_count * 100) if self.trade_count else 0
        logger.info("=" * 60)
        logger.info("SESSION SUMMARY")
        logger.info("=" * 60)
        logger.info("  Trades: %d", self.trade_count)
        logger.info("  Wins: %d (%.1f%%)", self.win_count, win_rate)
        logger.info("  Open positions: %d", len(self.positions))
        logger.info("  Daily PnL: $%.2f", self.daily_pnl)
        logger.info("  Cumulative PnL: $%.2f", self.cumulative_pnl)
        logger.info("=" * 60)

    def _start_ws_stream(self, token: str):
        """Start a raw WebSocket connection to TopstepX market hub."""
        SEP = chr(0x1e)
        url = f"wss://rtc.topstepx.com/hubs/market?access_token={token}"

        def _ws_loop():
            while True:
                try:
                    ws = ws_lib.create_connection(url, timeout=30)
                    # SignalR handshake
                    ws.send(json.dumps({"protocol": "json", "version": 1}) + SEP)
                    ws.recv()
                    # Subscribe
                    ws.send(json.dumps({
                        "type": 1, "invocationId": "1",
                        "target": "SubscribeContractQuotes",
                        "arguments": [CONTRACT_ID],
                    }) + SEP)
                    logger.info("WebSocket stream connected and subscribed")

                    while True:
                        msg = ws.recv()
                        for part in msg.split(SEP):
                            part = part.strip()
                            if not part:
                                continue
                            data = json.loads(part)
                            t = data.get("type")
                            if t == 6:  # Ping
                                ws.send(json.dumps({"type": 6}) + SEP)
                            elif t == 1 and "Quote" in data.get("target", ""):
                                args = data.get("arguments", [])
                                for item in args:
                                    if isinstance(item, dict):
                                        quote_cache.update(CONTRACT_ID, item)
                                        break
                            elif t == 7:  # Close
                                logger.warning("Server sent close — reconnecting")
                                break
                except ws_lib.WebSocketTimeoutException:
                    continue
                except Exception as exc:
                    logger.debug("WS error: %s — reconnecting in 3s", exc)
                finally:
                    try:
                        ws.close()
                    except Exception:
                        pass
                time.sleep(3)

        self._ws_thread = threading.Thread(target=_ws_loop, daemon=True)
        self._ws_thread.start()

    def _on_quote(self, data):
        """Callback for market stream quotes."""
        pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Captain Paper Trader")
    parser.add_argument("--interval", type=int, default=60,
                        help="Seconds between new signals (default: 60)")
    parser.add_argument("--max-positions", type=int, default=3,
                        help="Max simultaneous positions (default: 3)")
    args = parser.parse_args()

    trader = PaperTrader(
        signal_interval=args.interval,
        max_positions=args.max_positions,
    )
    trader.start()


if __name__ == "__main__":
    main()
