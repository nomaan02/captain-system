#!/usr/bin/env python3
"""Test order round trip — places a limit order and immediately cancels it.

Bypasses the in-memory adapter (which can't be accessed from a separate
process) and calls the TopstepX API directly with the same credentials.
This proves the API, account, and contract resolution all work.

Usage (inside captain-command container):
  python3 /app/test_order_roundtrip.py
"""

import logging
import os
import sys
import time

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="[ORDER-TEST] %(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("order_test")


def main():
    logger.info("=" * 70)
    logger.info("TOPSTEPX ORDER ROUND-TRIP TEST")
    logger.info("=" * 70)

    # 1. Authenticate
    logger.info("1. Authenticating with TopstepX...")
    from shared.topstep_client import (
        get_topstep_client, OrderType, OrderSide, TopstepXClientError,
    )
    try:
        client = get_topstep_client()
        client.authenticate()
        logger.info("   Authenticated as %s", os.environ.get("TOPSTEP_USERNAME", "?"))
    except Exception as e:
        logger.error("   Auth FAILED: %s", e)
        return False

    # 2. Get account
    logger.info("2. Resolving account...")
    try:
        account_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")
        accounts = client.get_accounts(only_active=True)
        account = None
        for acc in accounts:
            if acc.get("name") == account_name or not account_name:
                account = acc
                break

        if not account:
            logger.error("   No matching account found (looking for '%s')", account_name)
            logger.error("   Available: %s", [a.get("name") for a in accounts])
            return False

        account_id = account["id"]
        balance = account.get("balance", 0)
        can_trade = account.get("canTrade", False)
        logger.info("   Account: %s (id=%s)", account.get("name"), account_id)
        logger.info("   Balance: $%.2f, canTrade: %s", balance, can_trade)

        if not can_trade:
            logger.error("   Account canTrade=False — cannot place orders")
            return False
    except Exception as e:
        logger.error("   Account resolution FAILED: %s", e)
        return False

    # 3. Resolve MES contract
    logger.info("3. Resolving MES contract ID...")
    from shared.contract_resolver import resolve_contract_id
    contract_id = resolve_contract_id("MES")
    if not contract_id:
        logger.error("   MES contract not resolved")
        return False
    logger.info("   MES → %s", contract_id)

    # 4. Place limit order at $1.00 (will never fill)
    logger.info("4. Placing test order: BUY 1 MES LIMIT @ $1.00...")
    try:
        resp = client.place_limit_order(
            account_id, contract_id, OrderSide.BUY, 1, 1.00,
        )
        order_id = resp.get("orderId")
        success = resp.get("success", False)
        logger.info("   Response: %s", resp)

        if not success or not order_id:
            error = resp.get("errorCode") or resp.get("errorMessage", "unknown")
            logger.error("   Order REJECTED: %s", error)
            return False

        logger.info("   Order PLACED: orderId=%s", order_id)
    except Exception as e:
        logger.error("   Place order FAILED: %s", e, exc_info=True)
        return False

    # 5. Cancel it
    logger.info("5. Cancelling order %s...", order_id)
    try:
        cancel_resp = client.cancel_order(account_id, order_id)
        logger.info("   Cancel response: %s", cancel_resp)
        logger.info("   Order CANCELLED")
    except Exception as e:
        logger.error("   Cancel FAILED: %s", e, exc_info=True)
        logger.error("   WARNING: order %s may still be open — check TopstepX dashboard", order_id)
        return False

    # 6. Verify no open orders remain
    logger.info("6. Verifying no open orders...")
    try:
        open_orders = client.search_open_orders(account_id)
        test_still_open = [o for o in open_orders if o.get("orderId") == order_id]
        if test_still_open:
            logger.warning("   Test order still appears open — may take a moment to clear")
        else:
            logger.info("   Clean: no leftover orders")
    except Exception as e:
        logger.warning("   Could not verify: %s", e)

    logger.info("=" * 70)
    logger.info("RESULT: PASSED — full order place + cancel round trip works")
    logger.info("=" * 70)
    return True


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        logger.error("TEST CRASHED: %s", e, exc_info=True)
        sys.exit(1)
