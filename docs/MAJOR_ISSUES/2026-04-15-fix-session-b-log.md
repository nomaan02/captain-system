# Session B: Monitoring & Data Flow Fixes — 2026-04-15

## Fix 2E: Fix Position Search Endpoint (P0 — CRITICAL)
- **Status:** APPLIED
- **Files Modified:** `shared/topstep_client.py`
- **Changes:** Changed `search_positions()` endpoint from `/Position/search` (does not exist in TopstepX API) to `/Position/searchOpen` (correct endpoint). Single string change on line 306.

## Fix 2A: Capture Entry Price Through TAKEN Command (P1 — CRITICAL)
- **Status:** APPLIED
- **Files Modified:** `captain-command/captain_command/blocks/b3_api_adapter.py`, `captain-command/captain_command/blocks/b1_core_routing.py`, `captain-command/captain_command/blocks/orchestrator.py`
- **Changes:**
  - **b3_api_adapter.py**: After market entry order succeeds in `send_signal()`, call `receive_fill(entry_oid)` to retrieve the brokerage fill price. Include `fill_price` in the returned result dict.
  - **b1_core_routing.py**: Extended `sanitise_for_api()` to carry internal context fields (`signal_id`, `user_id`, `session`, `entry_price`, `regime_state`, `combined_modifier`, `aim_breakdown`) from the signal's `_context` dict. These fields are NOT sent to the brokerage API — they are only used by the orchestrator to publish the TAKEN command.
  - **orchestrator.py (command)**: After `send_signal()` returns PLACED status in `_auto_execute_signal()`, publish a `TAKEN_SKIPPED` command to the `STREAM_COMMANDS` Redis stream with `action=TAKEN`. The command includes `actual_entry_price` set to the brokerage fill price, plus all fields that `_handle_taken_skipped()` in Online expects (asset, direction, contracts, tp_level, sl_level, account_id, session, regime_state, etc.).
- **Data flow:** `send_signal()` -> `receive_fill()` -> fill_price in result -> `_auto_execute_signal()` publishes TAKEN with `actual_entry_price=fill_price` -> Online `_handle_taken_skipped()` stores `actual_entry_price` as `entry_price` in position dict -> B7 uses real fill price for P&L computation and TP/SL hit detection.

## Fix 2C: Reconcile Positions on Startup (P1 — CRITICAL)
- **Status:** APPLIED
- **Files Modified:** `captain-online/captain_online/blocks/orchestrator.py`
- **Changes:**
  - Added `REDIS_KEY_OPEN_POSITIONS = "captain:open_positions"` constant for the Redis hash key.
  - Added `_reconcile_positions_from_redis()` method: on startup, reads all entries from the `captain:open_positions` Redis hash, deserializes each position dict (including `entry_time` datetime parsing), and appends to `self.open_positions`. Logs a WARNING when positions are recovered.
  - Modified `start()` to call `_reconcile_positions_from_redis()` before starting the command listener and session loop.
  - Modified `_handle_taken_skipped()`: after adding a position to `self.open_positions`, serialize it to JSON and write to the Redis hash keyed by `signal_id`.
  - Modified `_run_position_monitor()`: after removing a resolved position from `self.open_positions`, delete it from the Redis hash by `signal_id`.
- **Approach:** Redis hash was chosen over QuestDB or brokerage API query because: (1) Redis is already a dependency with AOF persistence, so data survives container restarts; (2) no authentication needed (unlike querying the brokerage API from captain-online which normally doesn't connect directly); (3) minimal code change — just `hset`/`hgetall`/`hdel` on the existing Redis client.

## Summary
- Fixes applied: 3/3
- Files modified:
  - `shared/topstep_client.py`
  - `captain-command/captain_command/blocks/b3_api_adapter.py`
  - `captain-command/captain_command/blocks/b1_core_routing.py`
  - `captain-command/captain_command/blocks/orchestrator.py`
  - `captain-online/captain_online/blocks/orchestrator.py`
- Next steps:
  - Rebuild and restart all 3 Docker processes (`captain-online`, `captain-command`, and redeploy `shared/` volume)
  - Verify at next NY session open that: (1) positions appear with non-None entry_price; (2) B7 computes P&L correctly; (3) after a container restart, positions are recovered from Redis
  - Monitor logs for `POSITION RECONCILIATION` warnings to confirm recovery works
