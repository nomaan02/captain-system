# Captain System — Migrate SignalR Library: signalrcore → pysignalr

## Context

You are modifying the Captain trading system's WebSocket layer. The system connects to TopstepX (prop trading platform) via SignalR WebSocket for real-time ES futures market data.

**The problem:** The current SignalR library (`signalrcore 1.0.2`) is abandoned (last commit 2021), permanently pinned to `websocket-client 0.54.0` due to known socket-closing bugs the author cannot fix. It uses synchronous threading internally, which conflicts with our FastAPI/asyncio architecture. This is the root cause of persistent WebSocket drops.

**The solution:** Replace `signalrcore` with `pysignalr` (v1.3.0, by baking-bad/dipdup-io). pysignalr is:
- Built natively on asyncio + the `websockets` library (v16.x)
- Has built-in 20-second WebSocket-level ping/pong for automatic dead-connection detection
- Supports `access_token_factory` for JWT token refresh on reconnection
- Classified "Production/Stable" on PyPI, actively maintained (4 releases in 18 months)
- Fully typed, 5 contributors

## Reference Document

Read the file `captain-24-7-setup-guide.md` (in the project root or wherever Nomaan has placed it). It contains a detailed research report covering:
- Section "Replace signalrcore with pysignalr immediately" — comparison table and rationale
- Section "TopstepX SignalR connections need specific configuration" — auth patterns, keepalive intervals, re-subscription requirements, token refresh lifecycle
- Section "Docker Compose configuration" — graceful shutdown patterns for WebSocket containers

**Read that file before making any changes.** It is the authoritative reference for this migration.

## Current Architecture

- **File to modify:** `shared/topstep_stream.py`
- **Two stream classes:** `MarketStream` (connects to `rtc.topstepx.com/hubs/market`) and `UserStream` (connects to `rtc.topstepx.com/hubs/user`)
- **Current connection setup uses:**
  ```python
  from signalrcore.hub_connection_builder import HubConnectionBuilder

  HubConnectionBuilder()
      .with_url(full_url, options={"skip_negotiation": True})
      .with_automatic_reconnect({
          "type": "raw",
          "keep_alive_interval": 10,
          "reconnect_interval": 5,
          "max_attempts": 50,
      })
      .build()
  ```
- **Token passed via URL query string:** `wss://rtc.topstepx.com/hubs/market?access_token=TOKEN`
- **Callbacks registered via:** `hub.on("GatewayQuote", handler)`, `hub.on("GatewayTrade", handler)`, etc.
- **Current reconnection logic:** `_on_error()` triggers `_delayed_reconnect()` via threading.Timer. `_on_close()` does the same. `_on_reconnect()` re-subscribes to contracts/accounts.
- **The streams run in signalrcore's internal daemon threads** — separate from FastAPI's asyncio loop.

## pysignalr API Reference

```python
from pysignalr.client import SignalRClient
from pysignalr.messages import CompletionMessage

# Create client
client = SignalRClient(
    url="wss://rtc.topstepx.com/hubs/market",
    access_token_factory=lambda: get_current_token(),  # called on every connect/reconnect
    headers={"User-Agent": "Captain/1.0"},
)

# Register handlers
client.on("GatewayQuote", handle_quote)
client.on("GatewayTrade", handle_trade)
client.on_open(on_connected)
client.on_close(on_disconnected)
client.on_error(on_error)

# Start (async)
await client.run()  # blocks, handles reconnection internally

# Or for more control:
# Run in a background task
task = asyncio.create_task(client.run())

# Send messages
await client.send("SubscribeContractQuotes", [contract_id])

# Stop
await client.stop()  # or task.cancel()
```

Key differences from signalrcore:
- `access_token_factory` is called on EVERY reconnection — token refresh is automatic
- `client.run()` is async — fits naturally into FastAPI's event loop
- No manual `skip_negotiation` needed — pysignalr handles WebSocket transport directly
- Reconnection is built-in with configurable backoff
- The `websockets` library underneath sends ping frames every 20s automatically

## Migration Requirements

### Phase 1: Audit (READ ONLY)

1. Read `shared/topstep_stream.py` completely — understand every method in both `MarketStream` and `UserStream`
2. Read `captain-command/main.py` — understand how streams are started, stopped, and how they interact with the FastAPI lifecycle
3. Read `requirements.txt` — note all signalrcore-related dependencies
4. Identify every import of `signalrcore` across the entire codebase: `grep -r "signalrcore" --include="*.py" .`
5. Identify how callbacks are currently wired (what events, what handlers)
6. Identify how stream state (CONNECTED, DISCONNECTED, RECONNECTING, ERROR) is tracked and consumed by other components

**Produce a migration map:** list every signalrcore API call and its pysignalr equivalent.

### Phase 2: Implementation Plan (STOP AND WAIT for approval)

Propose the changes file-by-file with:
- What changes in `shared/topstep_stream.py`
- What changes in `captain-command/main.py` (stream startup/shutdown lifecycle)
- What changes in `requirements.txt`
- Whether any other files import or depend on signalrcore
- How the async integration works — pysignalr is async but some consumers of the stream data may be synchronous. Explain the bridging strategy.
- How `_delayed_reconnect` logic changes (pysignalr may handle this internally)
- How re-subscription on reconnect works (must re-subscribe to GatewayQuote/GatewayTrade/GatewayDepth for each contract after every reconnection)

### Phase 3: Implementation (after approval)

Execute the migration. Key constraints:

1. **One file at a time, commit after each.** Start with requirements.txt, then topstep_stream.py, then main.py.
2. **Preserve all existing callback logic.** The handlers that process quotes, trades, account updates — none of that business logic changes. Only the transport layer changes.
3. **Preserve the StreamState enum and state tracking.** Other components (health checks, GUI WebSocket, orchestrator) read stream state.
4. **Token refresh must work.** The `access_token_factory` must return the current valid token. If the token has expired or is near expiry, refresh it via `/api/Auth/validate` before returning.
5. **Re-subscribe on every reconnection.** Register an `on_open` handler that re-subscribes to all contract IDs (MarketStream) or account ID (UserStream). SignalR does NOT restore subscriptions after reconnection.
6. **Graceful shutdown.** The SIGTERM handler in main.py must `await client.stop()` cleanly.
7. **Test with the running Docker stack.** After implementation, rebuild captain-command and verify:
   - Both streams connect and receive data
   - Health check still passes
   - GUI WebSocket still works
   - Redis pub/sub channels are active

### Phase 4: Verification

Run these checks and report results:

```bash
# Confirm signalrcore is fully removed
docker exec captain-system-captain-command-1 pip list | grep -iE "signalr|pysignalr|websockets"
# Expected: pysignalr and websockets present, signalrcore ABSENT

# Confirm streams are connected
docker logs captain-system-captain-command-1 --tail 30 | grep -iE "MarketStream|UserStream|CONNECTED"

# Confirm data is flowing
docker logs captain-system-captain-command-1 --tail 50 | grep -iE "quote|trade|tick"

# Confirm Redis channels active
docker exec captain-system-captain-command-1 python -c "import redis; r=redis.Redis(host='redis',port=6379); print(r.pubsub_channels())"
```

## Rules

- **Read the research file first.** It contains critical details about TopstepX's SignalR requirements.
- **Read before writing.** Always read current file contents before proposing changes.
- **Phases 1 and 2 are read-only.** No file modifications until Phase 3 is approved.
- **Do not change business logic.** Only the transport layer (signalrcore → pysignalr) changes.
- **Do not reference QuantConnect.** It is not part of this system.
- **TRADING_ENVIRONMENT must remain "LIVE"** in .env — DEMO is non-functional on TopstepX.
- **Cite file paths and line numbers** for every finding.
- **If pysignalr's API doesn't support something signalrcore does**, flag it explicitly and propose a workaround. Do not silently drop functionality.
