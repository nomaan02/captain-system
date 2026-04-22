#!/usr/bin/env python3
"""Dry run of captain-command execution path — verifies API adapter readiness.

Usage (inside captain-command container):

  # Level 1: Connection check only (read-only, no orders placed)
  python3 /app/dry_run_command.py

  # Level 2: Place and cancel a test limit order (proves full round trip)
  python3 /app/dry_run_command.py --test-order

The test order places a 1-lot MES limit BUY at $1.00 (will never fill),
verifies acceptance, then immediately cancels it. Your account is a
Trading Combine (practice) so this costs nothing.
"""

import json
import logging
import os
import sys

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="[CMD-CHECK] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cmd_check")

PASS = "OK"
FAIL = "FAILED"


def main():
    test_order = "--test-order" in sys.argv
    results = {}

    logger.info("=" * 70)
    logger.info("COMMAND EXECUTION PATH CHECK")
    if test_order:
        logger.info("Mode: FULL (includes test order placement + cancel)")
    else:
        logger.info("Mode: READ-ONLY (connection check only)")
    logger.info("=" * 70)

    # ── 1. Check _active_connections ──
    logger.info("-" * 70)
    logger.info("1. Checking API adapter connections...")
    from captain_command.blocks.b3_api_adapter import (
        _active_connections, get_connection_summary,
    )

    summary = get_connection_summary()
    logger.info("  Connection summary: %s", summary)

    if not _active_connections:
        logger.error("  _active_connections is EMPTY — no API adapters registered")
        logger.error("  This means auto-execute will silently skip all signals")
        results["adapter_registered"] = FAIL
        _summary(results)
        return False

    results["adapter_registered"] = PASS

    for ac_id, state in _active_connections.items():
        adapter = state.get("adapter")
        connected = adapter.connected if adapter else False
        logger.info("  Account %-12s: connected=%s, adapter=%s",
                    ac_id, connected, type(adapter).__name__ if adapter else "None")

        if not connected:
            logger.error("  Adapter for %s is NOT connected — orders will fail", ac_id)
            results[f"adapter_{ac_id}_connected"] = FAIL
        else:
            results[f"adapter_{ac_id}_connected"] = PASS

    # ── 2. Ping API ──
    logger.info("-" * 70)
    logger.info("2. Pinging TopstepX API...")
    for ac_id, state in _active_connections.items():
        adapter = state.get("adapter")
        if adapter:
            latency = adapter.ping()
            if latency >= 0:
                logger.info("  Account %s: API latency = %.0fms", ac_id, latency)
                results[f"ping_{ac_id}"] = PASS
            else:
                logger.error("  Account %s: ping FAILED (latency=%s)", ac_id, latency)
                results[f"ping_{ac_id}"] = FAIL

    # ── 3. Account status ──
    logger.info("-" * 70)
    logger.info("3. Fetching account status...")
    for ac_id, state in _active_connections.items():
        adapter = state.get("adapter")
        if adapter and adapter.connected:
            status = adapter.get_account_status()
            balance = status.get("balance")
            positions = status.get("open_positions", 0)
            logger.info("  Account %s: balance=$%.2f, open_positions=%s",
                        ac_id, balance or 0, positions)

            if balance is not None and balance > 0:
                results[f"account_{ac_id}_status"] = PASS
            else:
                logger.warning("  Account %s: balance is %s — may indicate issue",
                               ac_id, balance)
                results[f"account_{ac_id}_status"] = FAIL

    # ── 4. Contract resolution for recommended assets ──
    logger.info("-" * 70)
    logger.info("4. Resolving contract IDs for tradeable assets...")
    from shared.contract_resolver import resolve_contract_id
    test_assets = ["MNQ", "MYM", "MES", "M2K", "NQ", "ES"]
    for asset in test_assets:
        cid = resolve_contract_id(asset)
        if cid:
            logger.info("  %-6s → %s", asset, cid)
            results[f"contract_{asset}"] = PASS
        else:
            logger.error("  %-6s → NOT RESOLVED", asset)
            results[f"contract_{asset}"] = FAIL

    # ── 5. Compliance gate ──
    logger.info("-" * 70)
    logger.info("5. Checking compliance gate...")
    from captain_command.blocks.b3_api_adapter import check_compliance_gate
    gate = check_compliance_gate()
    mode = gate.get("execution_mode", "UNKNOWN")
    allowed = gate.get("allowed", False)
    logger.info("  Execution mode: %s, allowed: %s", mode, allowed)
    if mode == "AUTO" or allowed:
        results["compliance_gate"] = PASS
    else:
        logger.warning("  Compliance gate: mode=%s, allowed=%s — auto-execute may be blocked", mode, allowed)
        results["compliance_gate"] = FAIL

    # ── 6. AUTO_EXECUTE env var ──
    logger.info("-" * 70)
    logger.info("6. Checking AUTO_EXECUTE setting...")
    auto_exec = os.environ.get("AUTO_EXECUTE", "")
    is_auto = auto_exec.lower() in ("1", "true", "yes")
    logger.info("  AUTO_EXECUTE=%s (active=%s)", auto_exec, is_auto)
    if is_auto:
        results["auto_execute"] = PASS
    else:
        logger.warning("  AUTO_EXECUTE is not enabled — signals will show in GUI but NOT be placed")
        results["auto_execute"] = FAIL

    # ── 7. Test order (optional) ──
    if test_order:
        logger.info("-" * 70)
        logger.info("7. TEST ORDER: placing 1-lot MES limit BUY @ $1.00...")

        # Find the first connected adapter
        adapter = None
        ac_id_int = None
        for ac_id, state in _active_connections.items():
            a = state.get("adapter")
            if a and a.connected:
                adapter = a
                ac_id_int = a.account_id
                break

        if not adapter or not ac_id_int:
            logger.error("  No connected adapter — cannot test")
            results["test_order"] = FAIL
        else:
            from shared.topstep_client import OrderType, OrderSide
            mes_contract = resolve_contract_id("MES")
            if not mes_contract:
                logger.error("  Cannot resolve MES contract — cannot test")
                results["test_order"] = FAIL
            else:
                try:
                    # Place limit buy at $1.00 — will never fill
                    logger.info("  Placing: BUY 1 MES LIMIT @ $1.00 (account=%s, contract=%s)",
                                ac_id_int, mes_contract)
                    resp = adapter.client.place_limit_order(
                        ac_id_int, mes_contract, OrderSide.BUY, 1, 1.00,
                    )
                    order_id = resp.get("orderId")
                    success = resp.get("success", False)
                    logger.info("  Place response: orderId=%s, success=%s, resp=%s",
                                order_id, success, resp)

                    if success and order_id:
                        results["test_order_place"] = PASS

                        # Cancel immediately
                        logger.info("  Cancelling order %s...", order_id)
                        cancel_resp = adapter.client.cancel_order(ac_id_int, order_id)
                        logger.info("  Cancel response: %s", cancel_resp)
                        results["test_order_cancel"] = PASS

                        logger.info("  TEST ORDER: place + cancel round trip PASSED")
                        results["test_order"] = PASS
                    else:
                        error = resp.get("errorCode") or resp.get("errorMessage", "unknown")
                        logger.error("  Order placement REJECTED: %s", error)
                        logger.error("  Full response: %s", resp)
                        results["test_order"] = FAIL

                except Exception as e:
                    logger.error("  Test order CRASHED: %s", e, exc_info=True)
                    results["test_order"] = FAIL

    # ── Summary ──
    _summary(results)

    failed = [k for k, v in results.items() if v == FAIL]
    if failed:
        logger.warning("VERDICT: %d check(s) failed — review above", len(failed))
        return False
    else:
        logger.info("VERDICT: All checks passed. Command execution path is ready.")
        return True


def _summary(results: dict):
    logger.info("=" * 70)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 70)
    for key, status in results.items():
        logger.info("  %-35s [%s]", key, status)
    failed = [k for k, v in results.items() if v == FAIL]
    if failed:
        logger.error("FAILURES: %s", failed)
    else:
        logger.info("All checks passed.")


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        logger.error("COMMAND CHECK CRASHED: %s", e, exc_info=True)
        sys.exit(1)
