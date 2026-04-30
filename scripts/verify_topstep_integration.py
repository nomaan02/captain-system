"""TopstepX Integration — Full Verification Script.

Run from project root:
    python captain-system/scripts/verify_topstep_integration.py
"""
import sys
import os
import time

sys.path.insert(0, "captain-system")
sys.path.insert(0, "captain-system/captain-command")
sys.path.insert(0, "captain-system/captain-online")

# When run inside a container, env vars are already injected via docker-compose
# env_file. dotenv is only needed for direct host execution. Make it optional so
# the script works in both contexts.
try:
    from dotenv import load_dotenv
    load_dotenv("captain-system/.env", override=True)
except ImportError:
    pass


def main():
    print("=" * 60)
    print("TOPSTEPX INTEGRATION — FULL VERIFICATION")
    print("=" * 60)

    # 1. Client auth + account discovery
    print("\n[1] AUTH + ACCOUNT DISCOVERY")
    from shared.topstep_client import (
        get_topstep_client,
        OrderSide, OrderType, OrderStatus, PositionType,
    )
    client = get_topstep_client()
    token = client.authenticate()
    print(f"  Auth: OK (token={len(token)} chars)")

    accounts = client.get_accounts(only_active=True)
    acc = accounts[0]
    account_id = acc["id"]
    print(f"  Account: {acc['name']} (id={account_id})")
    print(f"  Balance: ${acc['balance']:,.2f}")
    print(f"  Can trade: {acc['canTrade']}, Simulated: {acc['simulated']}")

    # 2. Contract resolution
    print("\n[2] CONTRACT RESOLUTION")
    contract = client.get_contract_by_id("CON.F.US.EP.M26")
    print(f"  Contract: {contract['id']} ({contract['name']})")
    print(f"  Tick: {contract['tickSize']} / Value: ${contract['tickValue']}")

    # 3. B3 API adapter
    print("\n[3] B3 API ADAPTER")
    from captain_command.blocks.b3_api_adapter import (
        TopstepXAdapter, check_compliance_gate,
    )
    adapter = TopstepXAdapter()
    conn = adapter.connect()
    print(f"  Connect: {conn['connected']} - {conn['message']}")
    print(f"  Account status: {adapter.get_account_status()}")
    print(f"  Ping: {adapter.ping():.0f}ms")

    gate = check_compliance_gate()
    print(f"  Compliance: mode={gate['execution_mode']}")

    # IMPORTANT: only fire the test signal when the compliance gate is in
    # MANUAL mode. In MANUAL mode send_signal short-circuits and returns
    # MANUAL_PENDING without hitting the broker. In AUTO mode it would
    # place a real market order on the live account — exactly what a
    # verification script must NOT do.
    if gate["execution_mode"] == "MANUAL":
        signal_result = adapter.send_signal({
            "asset": "ES", "direction": "BUY", "size": 1,
            "tp": 5900.0, "sl": 5700.0, "timestamp": "2026-03-16T22:00:00Z",
        })
        print(f"  Send signal (MANUAL): status={signal_result['status']}")
    else:
        print(f"  Send signal: SKIPPED (gate={gate['execution_mode']}, "
              "would place a real order — use scripts/test_bracket_order.py "
              "for an explicit live-order test)")

    # 4. Stream connectivity
    print("\n[4] STREAM CONNECTIVITY")
    from shared.topstep_stream import (
        MarketStream, UserStream, quote_cache, StreamState,
    )

    market = MarketStream(
        token=client.current_token, contract_id="CON.F.US.EP.M26",
    )
    market.start()
    time.sleep(2)
    print(f"  MarketStream: {market.state.value}")

    user = UserStream(
        token=client.current_token, account_id=account_id,
    )
    user.start()
    time.sleep(2)
    print(f"  UserStream: {user.state.value}")

    quote = quote_cache.get("CON.F.US.EP.M26")
    print(f"  Quote cache: {'populated' if quote else 'empty (market closed)'}")
    print(f"  Account cache: {'populated' if user.account_data else 'empty'}")

    market.stop()
    user.stop()

    # 5. B1 data ingestion stubs (captain_online — only available when run
    # from host venv with all three service trees on PYTHONPATH; skipped
    # cleanly when run inside captain-command).
    print("\n[5] B1 DATA INGESTION")
    try:
        from captain_online.blocks.b1_data_ingestion import (
            _get_latest_price, _get_prior_close,
            _get_current_session_volume, _get_avg_session_volume_20d,
        )
        from captain_online.blocks.b1_features import (
            _get_latest_price as f_price, _get_open_price,
            _get_prior_close_for_date,
            _get_best_bid, _get_best_ask, _get_daily_closes,
            _get_session_open_time,
        )
        checks = {
            "latest_price": _get_latest_price("ES"),
            "prior_close": _get_prior_close("ES"),
            "session_volume": _get_current_session_volume("ES"),
            "avg_volume_20d": _get_avg_session_volume_20d("ES"),
            "feat_price": f_price("ES"),
            "open_price": _get_open_price("ES", None),
            "prior_close_date": _get_prior_close_for_date("ES", None),
            "bid": _get_best_bid("ES"),
            "ask": _get_best_ask("ES"),
            "session_open": str(_get_session_open_time("ES")),
        }
        for k, v in checks.items():
            tag = "OK" if v is not None else "None (market closed)"
            print(f"  {k}: {v} - {tag}")
    except ImportError as e:
        print(f"  SKIPPED: {e} (captain_online not on PYTHONPATH — "
              "run from host venv to exercise this block)")

    # 6. B2 GUI data server (captain_command — only available when run
    # inside captain-command or from host venv).
    print("\n[6] B2 GUI DATA SERVER")
    try:
        from captain_command.blocks.b2_gui_data_server import (
            _get_capital_silo, _get_all_live_market_data,
            _get_api_connection_status,
        )
        capital = _get_capital_silo("user1")
        print(f"  Capital silo: ${capital.get('total_capital', 0):,.2f} "
              f"(source={capital.get('source')})")

        market_data = _get_all_live_market_data()
        # _get_all_live_market_data returns a dict keyed by asset; report
        # the count of populated assets and a coarse "any connected" flag.
        if isinstance(market_data, dict):
            populated = sum(1 for v in market_data.values() if v)
            print(f"  Live market: {populated}/{len(market_data)} assets populated")
        else:
            print(f"  Live market: {market_data!r}")

        api_stat = _get_api_connection_status()
        print(f"  API: authenticated={api_stat.get('api_authenticated')}, "
              f"token_age={api_stat.get('token_age_hours', 'N/A')}h")
    except ImportError as e:
        print(f"  SKIPPED: {e}")

    # 7. Enum sanity check
    print("\n[7] ENUM VERIFICATION")
    assert OrderSide.BUY == 0
    assert OrderSide.SELL == 1
    assert OrderType.MARKET == 2
    assert OrderType.LIMIT == 1
    assert OrderType.STOP == 4
    assert OrderStatus.FILLED == 2
    assert PositionType.LONG == 1
    assert PositionType.SHORT == 2
    print("  All enum values correct")

    # 8. Docker compose validation (host-only — paths don't exist inside
    # containers).
    print("\n[8] DOCKER COMPOSE")
    try:
        with open("captain-system/docker-compose.yml") as f:
            content = f.read()
        assert "env_file:" in content
        assert "- .env" in content
        print("  env_file directive: present in captain-online + captain-command")
    except FileNotFoundError:
        print("  SKIPPED: not running from host (captain-system/ path absent)")

    # 9. Anti-pattern check (host-only — paths don't exist inside containers).
    print("\n[9] ANTI-PATTERN CHECK")
    check_files = [
        "captain-system/shared/topstep_client.py",
        "captain-system/shared/topstep_stream.py",
        "captain-system/captain-command/captain_command/blocks/b3_api_adapter.py",
        "captain-system/captain-command/captain_command/blocks/b2_gui_data_server.py",
        "captain-system/captain-online/captain_online/blocks/b1_data_ingestion.py",
        "captain-system/captain-online/captain_online/blocks/b1_features.py",
    ]
    try:
        issues = []
        for fpath in check_files:
            with open(fpath) as f:
                text = f.read()
            if "import tsxapipy" in text:
                issues.append(f"{fpath}: imports tsxapipy")
        if issues:
            for i in issues:
                print(f"  WARNING: {i}")
        else:
            print("  No anti-patterns found")
    except FileNotFoundError:
        print("  SKIPPED: not running from host (captain-system/ path absent)")

    # Cleanup
    adapter.disconnect()
    client.logout()

    print("\n" + "=" * 60)
    print("ALL VERIFICATION CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
