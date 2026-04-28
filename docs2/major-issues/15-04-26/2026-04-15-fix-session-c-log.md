# Fix Session C: Wire UserStream WebSocket Callbacks (P2-2B)

**Date:** 2026-04-15
**Issue:** UserStream WebSocket callbacks defined but never wired in production
**Severity:** HIGH — real-time fill confirmations, position updates, and trade P&L silently dropped

---

## Problem

`shared/topstep_stream.py` contains a fully implemented `UserStream` class that subscribes to 4 TopStepX SignalR events:
- `GatewayUserAccount` — account balance updates
- `GatewayUserOrder` — order status changes (including rejections)
- `GatewayUserPosition` — position updates (including `averagePrice`)
- `GatewayUserTrade` — trade fills (including `profitAndLoss`, `fees`)

The constructor accepts `on_order_update`, `on_position_update`, `on_trade_update`, `on_account_update` callbacks — all remained `None` everywhere. Every event from the brokerage was received and silently discarded.

## Investigation: WebSocket Ownership

### Key Question
Can captain-command safely open its own UserStream without disconnecting captain-online's MarketStream?

### Findings

1. **Separate SignalR hubs:** MarketStream connects to `wss://rtc.topstepx.com/hubs/market`, UserStream connects to `wss://rtc.topstepx.com/hubs/user`. They are independent hubs with their own subscriptions. Cannot share a single `SignalRClient` (rules out Option C).

2. **Official docs silent on connection limits:** The TopStepX API docs do not explicitly document a per-account WebSocket connection limit. However, the docs note "single session per username" causing conflicts.

3. **Existing code asserts one connection:** `captain-command/captain_command/main.py` line 279-283 states: "TopstepX allows ONE concurrent WebSocket per user account across ALL hubs. Any connection from Command sends GatewayLogout to Online, killing signal generation."

4. **GatewayLogout is real:** Both `MarketStream` and `UserStream` handle `GatewayLogout` events. If opening a second connection triggers logout on the first, MarketStream dies and the OR tracker stops receiving quotes — breaking signal generation.

### Decision: Option B — Wire UserStream in captain-online

**Rationale:** Even though the official docs don't confirm the one-connection limit, the risk to live trading is too high. MarketStream is critical for signal generation. By starting UserStream in the same process (captain-online), we:
- Avoid any risk of GatewayLogout cross-talk between processes
- Reuse the already-authenticated token (singleton client)
- Forward events to captain-command via Redis (already the inter-process communication layer)

## Implementation

### Files Changed

| File | Change |
|------|--------|
| `shared/redis_client.py` | Added `CH_USER_EVENTS = "captain:user_events"` constant |
| `captain-online/captain_online/main.py` | Added `_start_user_stream()` function with 4 callbacks; wired in `main()` after MarketStream; added to shutdown handler |
| `captain-command/captain_command/main.py` | Updated `_init_topstep()` docstring and comments to document UserStream ownership |

### Data Flow

```
TopStepX User Hub (wss://rtc.topstepx.com/hubs/user)
  |
  v
captain-online: UserStream (background thread)
  |
  |-- GatewayUserPosition --> update captain:open_positions Redis hash
  |                           (enriches entry_price with brokerage averagePrice)
  |                       --> publish to captain:user_events pub/sub
  |
  |-- GatewayUserTrade -----> publish {type: "trade_update", data: {price, pnl, fees}}
  |                           to captain:user_events pub/sub
  |
  |-- GatewayUserOrder -----> publish {type: "order_update", data: {id, status, type}}
  |                           to captain:user_events (WARNING log if REJECTED)
  |
  |-- GatewayUserAccount ---> publish {type: "account_update", data: {balance}}
                              to captain:user_events pub/sub
```

### Position Enrichment Logic

When `GatewayUserPosition` fires with `averagePrice`:
1. **Guard:** Skip if `size == 0` (position closed) to avoid race with B7 resolution
2. Map `contractId` (e.g. `CON.F.US.EP.M26`) back to asset symbol (e.g. `ES`) using `preload_contracts()` reverse lookup
3. Read all entries from `captain:open_positions` Redis hash
4. Find entries where `asset` matches
5. Update `entry_price` and `actual_entry_price` with brokerage `averagePrice`
6. Write back to Redis hash

This complements (does not replace) the REST-based `receive_fill()` in `b3_api_adapter.py`. The REST call is synchronous at order time; the UserStream provides asynchronous confirmation.

### Redis Hash Race Condition (Mitigated)

The `captain:open_positions` hash is now written by 3 threads: the command listener (`hset` on TAKEN), the main session loop (`hdel` on resolution), and the UserStream callback (`hset` to enrich). The read-modify-write in the UserStream callback could theoretically resurface a position that B7 just resolved. The `size > 0` guard prevents the highest-risk window (position close event overlapping with resolution). The remaining theoretical race (mid-life position update during resolution) has a sub-millisecond window and would self-correct on the next B7 pass.

### Non-Fatal Startup

UserStream failure does NOT block captain-online startup. If account resolution fails or the WebSocket cannot connect, a WARNING is logged and the system continues with MarketStream only. The REST-based fill capture from Session A (P1-2A) remains the primary path.

## Verification

- All 152 unit tests pass
- No changes to MarketStream or OR tracker behavior
- No changes to REST-based fill capture (P1-2A)
- All events logged at INFO level for verification
