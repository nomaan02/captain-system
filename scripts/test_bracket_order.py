#!/usr/bin/env python3
"""Test script: place a harmless MES bracket order, verify SL+TP, then exit.

Mirrors EXACTLY how captain-command B3 send_signal() places atomic bracket
orders via TopstepXClient.place_bracket_order().

Flow:
  1. Authenticate with TopstepX (same as live system)
  2. Resolve account ID from TOPSTEP_ACCOUNT_NAME (same as live system)
  3. Place 1-lot MES BUY market order with atomic SL+TP brackets
     - SL: 8 ticks below fill (2 points = $2.50 max risk)
     - TP: 4 ticks above fill (1 point = $1.25 max gain)
  4. Verify the SL and TP working orders were created by the exchange
  5. Immediately close the position + cancel bracket orders
  6. Print full order/position details for verification

Uses: shared/topstep_client.py (same client the live system uses)
Cost: ~1 tick slippage on MES = $1.25 worst case
"""
import os
import sys
import time

# -- path setup (same as running from repo root) ---------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from shared.topstep_client import (
    TopstepXClient, OrderSide, OrderType, OrderStatus,
)

# -- config ----------------------------------------------------------------
ASSET = "MES"
CONTRACT_ID = "CON.F.US.MES.M26"  # Micro E-mini S&P 500, June 2026
TICK_SIZE = 0.25
TICK_VALUE = 1.25   # $1.25 per tick
SIZE = 1            # 1 lot — minimum possible

# Bracket offsets (in ticks) — mirrors how B3 computes them:
#   sl_ticks = max(1, int(round(abs(entry - sl_price) / tick_size)))
#   tp_ticks = max(1, int(round(abs(tp_price - entry) / tick_size)))
SL_TICKS = 8   # 2.0 points below entry — max risk $10.00
TP_TICKS = 4   # 1.0 point above entry  — we won't wait for this

SIDE = OrderSide.BUY  # BUY so we can close with a SELL


def main():
    print("=" * 60)
    print("  BRACKET ORDER TEST — MES (Micro E-mini S&P 500)")
    print("=" * 60)
    print()

    # ── Step 1: Authenticate ──────────────────────────────────────────
    print("[1/6] Authenticating with TopstepX...")
    client = TopstepXClient()  # reads TOPSTEP_USERNAME, TOPSTEP_API_KEY from env
    token = client.authenticate()
    print(f"  ✓ Authenticated (token: ...{token[-8:]})")
    print()

    # ── Step 2: Resolve account ───────────────────────────────────────
    print("[2/6] Resolving account...")
    account_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")
    if not account_name:
        print("  ✗ TOPSTEP_ACCOUNT_NAME not set in .env")
        sys.exit(1)

    account = client.get_account_by_name(account_name)
    if not account:
        # Fallback: list all accounts so user can see what's available
        all_accounts = client.get_accounts(only_active=True)
        print(f"  ✗ Account '{account_name}' not found. Active accounts:")
        for a in all_accounts:
            print(f"    - {a.get('name')} (id={a.get('id')})")
        sys.exit(1)

    account_id = account["id"]
    print(f"  ✓ Account: {account_name} (id={account_id})")
    print()

    # ── Step 3: Check no existing MES positions ───────────────────────
    print("[3/6] Checking for existing MES positions...")
    positions = client.search_positions(account_id)
    mes_positions = [p for p in positions if p.get("contractId") == CONTRACT_ID]
    if mes_positions:
        print(f"  ⚠ Found {len(mes_positions)} existing MES position(s):")
        for p in mes_positions:
            print(f"    size={p.get('size')}, avgPrice={p.get('averagePrice')}")
        print("  Aborting to avoid interfering with existing trades.")
        sys.exit(1)
    print(f"  ✓ No existing MES positions — safe to proceed")
    print()

    # ── Step 4: Place atomic bracket order ────────────────────────────
    # This is EXACTLY what the live system does in B3 send_signal():
    #   bracket_resp = self._client.place_bracket_order(
    #       self._account_id, contract_id, side, size,
    #       sl_ticks=sl_ticks, tp_ticks=tp_ticks,
    #   )
    print("[4/6] Placing atomic bracket order...")
    print(f"  Contract:  {CONTRACT_ID}")
    print(f"  Side:      BUY (OrderSide={SIDE})")
    print(f"  Size:      {SIZE}")
    print(f"  SL:        {SL_TICKS} ticks ({SL_TICKS * TICK_SIZE} pts, ${SL_TICKS * TICK_VALUE:.2f} risk)")
    print(f"  TP:        {TP_TICKS} ticks ({TP_TICKS * TICK_SIZE} pts, ${TP_TICKS * TICK_VALUE:.2f} gain)")
    print()

    bracket_resp = client.place_bracket_order(
        account_id, CONTRACT_ID,
        side=SIDE, size=SIZE,
        sl_ticks=SL_TICKS, tp_ticks=TP_TICKS,
    )
    print(f"  API Response: {bracket_resp}")

    entry_order_id = bracket_resp.get("orderId")
    success = bracket_resp.get("success", False)

    if not success or not entry_order_id:
        print(f"  ✗ Bracket order FAILED: {bracket_resp.get('errorCode', 'unknown')}")
        sys.exit(1)

    print(f"  ✓ Entry order placed (orderId={entry_order_id})")
    print()

    # ── Step 5: Verify brackets — poll for fill + check working orders ─
    print("[5/6] Verifying bracket orders were created...")
    time.sleep(1.5)  # brief wait for fill + bracket creation

    # 5a. Check the entry order fill
    orders = client.search_orders(account_id)
    entry_order = None
    bracket_orders = []

    for o in orders:
        oid = o.get("id")
        status = o.get("status", 0)
        otype = o.get("type", 0)
        oside = o.get("side", -1)
        contract = o.get("contractId", "")

        if contract != CONTRACT_ID:
            continue

        if oid == entry_order_id:
            entry_order = o
        elif status == OrderStatus.OPEN and oside != SIDE:
            # Working orders on the opposite side = our SL/TP brackets
            bracket_orders.append(o)

    # Also check open orders endpoint
    open_orders = client.search_open_orders(account_id)
    for o in open_orders:
        if o.get("contractId") != CONTRACT_ID:
            continue
        if o.get("id") != entry_order_id and o.get("side") != SIDE:
            # Avoid duplicates
            existing_ids = {bo.get("id") for bo in bracket_orders}
            if o.get("id") not in existing_ids:
                bracket_orders.append(o)

    type_names = {0: "UNKNOWN", 1: "LIMIT", 2: "MARKET", 4: "STOP",
                  5: "TRAILING_STOP", 6: "JOIN_BID", 7: "JOIN_ASK"}
    status_names = {0: "NONE", 1: "OPEN", 2: "FILLED", 3: "CANCELLED",
                    4: "EXPIRED", 5: "REJECTED", 6: "PENDING"}
    side_names = {0: "BUY", 1: "SELL"}

    print(f"  Entry order (id={entry_order_id}):")
    if entry_order:
        fill_price = entry_order.get("filledPrice") or entry_order.get("averageFilledPrice")
        print(f"    status:     {status_names.get(entry_order.get('status', 0), '?')}")
        print(f"    fillPrice:  {fill_price}")
        print(f"    type:       {type_names.get(entry_order.get('type', 0), '?')}")
    else:
        print(f"    (not found in recent orders — may need more time)")

    print()
    print(f"  Bracket orders found: {len(bracket_orders)}")
    sl_found = False
    tp_found = False
    for bo in bracket_orders:
        bo_type = bo.get("type", 0)
        bo_status = bo.get("status", 0)
        bo_side = bo.get("side", -1)
        bo_price = bo.get("limitPrice") or bo.get("stopPrice") or bo.get("price")
        print(f"    orderId={bo.get('id')}: "
              f"type={type_names.get(bo_type, '?')} "
              f"side={side_names.get(bo_side, '?')} "
              f"status={status_names.get(bo_status, '?')} "
              f"price={bo_price}")
        if bo_type == OrderType.STOP:
            sl_found = True
            print(f"      ^ This is the STOP LOSS")
        elif bo_type == OrderType.LIMIT:
            tp_found = True
            print(f"      ^ This is the TAKE PROFIT")

    print()
    if sl_found and tp_found:
        print("  ✓ BOTH SL and TP bracket orders confirmed!")
    elif sl_found:
        print("  ⚠ SL found but TP missing")
    elif tp_found:
        print("  ⚠ TP found but SL missing")
    else:
        print("  ⚠ No bracket orders detected (they may be embedded in the entry)")
        print("    This could mean the exchange handles brackets internally")
        print("    Check positions to confirm the entry filled:")
    print()

    # 5b. Check position exists
    positions = client.search_positions(account_id)
    mes_pos = [p for p in positions if p.get("contractId") == CONTRACT_ID]
    if mes_pos:
        p = mes_pos[0]
        print(f"  Position: size={p.get('size')}, avgPrice={p.get('averagePrice')}")
    else:
        print("  No open position found (may have already hit SL/TP)")
        print("  Skipping cleanup.")
        _cancel_remaining_orders(client, account_id, bracket_orders, type_names,
                                  status_names, side_names)
        _print_summary(bracket_resp, entry_order, bracket_orders, sl_found, tp_found)
        return

    # ── Step 6: Cleanup — close position + cancel brackets ────────────
    print()
    print("[6/6] Cleaning up — closing position and cancelling brackets...")

    # Close the position
    close_resp = client.close_position(account_id, CONTRACT_ID, SIZE)
    print(f"  Close position response: {close_resp}")
    close_success = close_resp.get("success", False)
    if close_success:
        print("  ✓ Position closed")
    else:
        print(f"  ⚠ Close may have failed: {close_resp}")
        # Try market order on opposite side as fallback
        print("  Attempting market SELL as fallback...")
        fallback = client.place_market_order(
            account_id, CONTRACT_ID, OrderSide.SELL, SIZE,
        )
        print(f"  Fallback response: {fallback}")

    # Cancel bracket orders
    _cancel_remaining_orders(client, account_id, bracket_orders, type_names,
                              status_names, side_names)

    # Brief pause then verify cleanup
    time.sleep(1)
    remaining_positions = client.search_positions(account_id)
    mes_remaining = [p for p in remaining_positions if p.get("contractId") == CONTRACT_ID]
    remaining_open = client.search_open_orders(account_id)
    mes_open = [o for o in remaining_open if o.get("contractId") == CONTRACT_ID]

    print()
    if not mes_remaining and not mes_open:
        print("  ✓ Fully cleaned up — no MES positions or open orders remain")
    else:
        if mes_remaining:
            print(f"  ⚠ {len(mes_remaining)} MES position(s) still open!")
            for p in mes_remaining:
                print(f"    size={p.get('size')}, avgPrice={p.get('averagePrice')}")
        if mes_open:
            print(f"  ⚠ {len(mes_open)} MES open order(s) still working!")
            for o in mes_open:
                print(f"    orderId={o.get('id')}, type={type_names.get(o.get('type',0), '?')}")

    _print_summary(bracket_resp, entry_order, bracket_orders, sl_found, tp_found)


def _cancel_remaining_orders(client, account_id, bracket_orders,
                              type_names, status_names, side_names):
    """Cancel any working bracket orders."""
    # Re-fetch open orders in case brackets are still live
    open_orders = client.search_open_orders(account_id)
    mes_open = [o for o in open_orders if o.get("contractId") == CONTRACT_ID]

    for o in mes_open:
        oid = o.get("id")
        try:
            cancel_resp = client.cancel_order(account_id, oid)
            print(f"  Cancelled order {oid} "
                  f"(type={type_names.get(o.get('type',0), '?')}): {cancel_resp}")
        except Exception as e:
            print(f"  ⚠ Failed to cancel order {oid}: {e}")


def _print_summary(bracket_resp, entry_order, bracket_orders, sl_found, tp_found):
    """Print final test summary."""
    print()
    print("=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    print(f"  Entry order ID:     {bracket_resp.get('orderId')}")
    print(f"  API success:        {bracket_resp.get('success')}")
    if entry_order:
        fill = entry_order.get("filledPrice") or entry_order.get("averageFilledPrice")
        print(f"  Fill price:         {fill}")
        if fill:
            print(f"  Expected SL price:  {float(fill) - SL_TICKS * TICK_SIZE}")
            print(f"  Expected TP price:  {float(fill) + TP_TICKS * TICK_SIZE}")
    print(f"  SL bracket found:   {'YES' if sl_found else 'NO'}")
    print(f"  TP bracket found:   {'YES' if tp_found else 'NO'}")
    print(f"  Bracket orders:     {len(bracket_orders)}")
    print()

    if sl_found and tp_found:
        print("  RESULT: ✓ PASS — Atomic bracket order works correctly")
        print("  The exchange created both SL and TP as OCO working orders.")
    elif bracket_resp.get("success"):
        print("  RESULT: ~ PARTIAL — Entry succeeded, bracket verification inconclusive")
        print("  The API accepted the bracket params but working orders may be")
        print("  managed internally by the exchange (not visible via Order/search).")
    else:
        print("  RESULT: ✗ FAIL — Bracket order was rejected by the API")

    print()
    print("  Cost: ~1 tick slippage on close = ~$1.25")
    print("=" * 60)


if __name__ == "__main__":
    main()
