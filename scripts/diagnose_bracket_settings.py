#!/usr/bin/env python3
"""Diagnose TopstepX account bracket settings — read-only.

Why this exists
---------------
On 2026-05-05 NY open, MYM bracket orders were rejected by TopstepX with:

    "Brackets cannot be used with Position Brackets.
     You must enable Auto OCO Brackets."

The user reports Auto OCO IS enabled in the TopstepX UI (verified via
screenshot) and brackets had worked on the same account for other
assets/sessions. The failure is intermittent. This script dumps every
field TopstepX exposes on the account REST endpoint so we can see what
account-level flags exist and check them next time the failure recurs.

The script is READ-ONLY:
  - authenticates with TopstepX
  - fetches all accounts (filterable by name via TOPSTEP_ACCOUNT_NAME)
  - prints the full JSON payload for each
  - prints any open positions and recent orders for context
  - does NOT place any orders
  - does NOT modify any account settings

Usage
-----
  # On the tower (inside any captain container that has shared/ mounted):
  cmd-run diagnose_bracket_settings.py

  # Or on the host directly:
  PYTHONPATH=. python3 scripts/diagnose_bracket_settings.py

  # Filter to a specific account:
  TOPSTEP_ACCOUNT_NAME=150KTC-V2-551001-86041837 cmd-run diagnose_bracket_settings.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass  # env vars assumed pre-set inside containers

from shared.topstep_client import TopstepXClient  # noqa: E402


def _print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _safe_dump(obj: dict | list) -> str:
    return json.dumps(obj, indent=2, default=str, sort_keys=True)


def main() -> int:
    target_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "").strip()

    _print_section("STEP 1: Authenticate")
    client = TopstepXClient()
    try:
        token = client.authenticate()
    except Exception as exc:
        print(f"  AUTH FAILED: {exc}")
        return 1
    print(f"  Authenticated. Token suffix: ...{token[-8:]}")

    _print_section("STEP 2: Fetch all accounts")
    try:
        accounts = client.get_accounts(only_active=False)
    except Exception as exc:
        print(f"  get_accounts FAILED: {exc}")
        return 2
    print(f"  Found {len(accounts)} account(s).")
    print()
    for a in accounts:
        marker = "  *" if (target_name and a.get("name") == target_name) else "   "
        print(f"{marker} id={a.get('id')} name={a.get('name')!r} "
              f"balance={a.get('balance')} canTrade={a.get('canTrade')} "
              f"simulated={a.get('simulated')}")

    targets = [a for a in accounts if not target_name or a.get("name") == target_name]
    if not targets:
        print(f"\n  WARNING: TOPSTEP_ACCOUNT_NAME={target_name!r} not found.")
        print("  Dumping ALL accounts instead.")
        targets = accounts

    for acct in targets:
        aid = acct.get("id")
        name = acct.get("name")
        _print_section(f"STEP 3: Full account JSON for {name} (id={aid})")
        print(_safe_dump(acct))

        _print_section(f"STEP 4: Open positions for {name}")
        try:
            positions = client.search_positions(int(aid))
            if positions:
                print(f"  {len(positions)} open position(s):")
                for p in positions:
                    print(_safe_dump(p))
            else:
                print("  No open positions.")
        except Exception as exc:
            print(f"  search_positions FAILED: {exc}")

        _print_section(f"STEP 5: Last 24h orders for {name}")
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=24))
            since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            orders = client.search_orders(int(aid), start_timestamp=since_iso)
            if orders:
                print(f"  {len(orders)} order(s) in last 24h. "
                      f"Showing types/statuses:")
                type_names = {0: "UNKNOWN", 1: "LIMIT", 2: "MARKET",
                              3: "STOP_LIMIT", 4: "STOP", 5: "TRAILING_STOP",
                              6: "JOIN_BID", 7: "JOIN_ASK"}
                status_names = {0: "NONE", 1: "OPEN", 2: "FILLED",
                                3: "CANCELLED", 4: "EXPIRED", 5: "REJECTED",
                                6: "PENDING"}
                side_names = {0: "BUY", 1: "SELL"}
                for o in orders[:25]:
                    print(f"    id={o.get('id')} "
                          f"contract={o.get('contractId')} "
                          f"size={o.get('size')} "
                          f"side={side_names.get(o.get('side', -1), '?')} "
                          f"type={type_names.get(o.get('type', -1), '?')} "
                          f"status={status_names.get(o.get('status', -1), '?')} "
                          f"limitPrice={o.get('limitPrice')} "
                          f"stopPrice={o.get('stopPrice')}")
                if len(orders) > 25:
                    print(f"    ... ({len(orders) - 25} more)")
            else:
                print("  No orders in last 24h.")
        except Exception as exc:
            print(f"  search_orders FAILED: {exc}")

        _print_section(f"STEP 6: Open working orders for {name}")
        try:
            open_orders = client.search_open_orders(int(aid))
            if open_orders:
                print(f"  {len(open_orders)} open working order(s):")
                for o in open_orders:
                    print(_safe_dump(o))
            else:
                print("  No open working orders.")
        except Exception as exc:
            print(f"  search_open_orders FAILED: {exc}")

    _print_section("DONE")
    print("  This script is READ-ONLY. No orders or settings were modified.")
    print()
    print("  What to look for in the account JSON:")
    print("    - any field containing 'bracket', 'oco', 'auto', 'position'")
    print("    - canTrade flag")
    print("    - simulated flag (PRAC accounts vs LIVE)")
    print("    - any 'lock' or 'restriction' fields")
    print()
    print("  Compare the account JSON across two timestamps (one when brackets")
    print("  worked vs one when they failed) to identify the toggling flag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
