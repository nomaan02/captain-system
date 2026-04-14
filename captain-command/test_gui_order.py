#!/usr/bin/env python3
"""Place a real MES market order, hold for 15 seconds, then flatten.

This places a REAL position on your practice account so you can see
how the GUI displays it. After 15 seconds it closes the position.

Usage (inside captain-command container):
  python3 /app/test_gui_order.py
"""

import logging
import os
import sys
import time

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="[GUI-TEST] %(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("gui_test")

HOLD_SECONDS = 15


def main():
    logger.info("=" * 70)
    logger.info("GUI ORDER TEST — BUY 1 MES, hold %ds, then close", HOLD_SECONDS)
    logger.info("=" * 70)

    from shared.topstep_client import (
        get_topstep_client, OrderSide, TopstepXClientError,
    )
    from shared.contract_resolver import resolve_contract_id

    # Authenticate
    logger.info("Authenticating...")
    client = get_topstep_client()
    client.authenticate()

    # Get account
    account_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")
    accounts = client.get_accounts(only_active=True)
    account = None
    for acc in accounts:
        if acc.get("name") == account_name or not account_name:
            account = acc
            break

    if not account:
        logger.error("No account found")
        return False

    account_id = account["id"]
    logger.info("Account: %s (id=%s, balance=$%.2f)",
                account.get("name"), account_id, account.get("balance", 0))

    # Resolve MES
    contract_id = resolve_contract_id("MES")
    if not contract_id:
        logger.error("Cannot resolve MES contract")
        return False

    # Place market BUY 1 MES
    logger.info("Placing: BUY 1 MES @ MARKET...")
    resp = client.place_market_order(account_id, contract_id, OrderSide.BUY, 1)
    order_id = resp.get("orderId")
    success = resp.get("success", False)
    logger.info("Response: %s", resp)

    if not success:
        logger.error("Order rejected: %s", resp.get("errorMessage"))
        return False

    logger.info("ORDER FILLED — orderId=%s", order_id)
    logger.info("Check the GUI now. Position will close in %d seconds...", HOLD_SECONDS)
    logger.info("")

    # Countdown
    for remaining in range(HOLD_SECONDS, 0, -1):
        sys.stdout.write(f"\r  Closing in {remaining}s... ")
        sys.stdout.flush()
        time.sleep(1)

    print()

    # Close: SELL 1 MES @ MARKET
    logger.info("Closing position: SELL 1 MES @ MARKET...")
    close_resp = client.place_market_order(account_id, contract_id, OrderSide.SELL, 1)
    logger.info("Close response: %s", close_resp)

    if close_resp.get("success"):
        logger.info("Position CLOSED")
    else:
        logger.error("Close FAILED: %s — manually close in TopstepX dashboard",
                     close_resp.get("errorMessage"))
        return False

    # Verify flat
    positions = client.search_positions(account_id)
    open_pos = [p for p in positions if p.get("size", 0) != 0]
    if open_pos:
        logger.warning("Still have open positions: %s", open_pos)
    else:
        logger.info("Confirmed flat — no open positions")

    logger.info("=" * 70)
    logger.info("DONE")
    logger.info("=" * 70)
    return True


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        logger.error("CRASHED: %s", e, exc_info=True)
        # Emergency close attempt
        logger.error("Attempting emergency flatten...")
        try:
            from shared.topstep_client import get_topstep_client, OrderSide
            from shared.contract_resolver import resolve_contract_id
            c = get_topstep_client()
            c.authenticate()
            accs = c.get_accounts(only_active=True)
            if accs:
                aid = accs[0]["id"]
                cid = resolve_contract_id("MES")
                if cid:
                    c.place_market_order(aid, cid, OrderSide.SELL, 1)
                    logger.info("Emergency close sent")
        except Exception:
            logger.error("Emergency close also failed — CHECK TOPSTEP DASHBOARD")
        sys.exit(1)
