# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""TopstepX real-time SignalR WebSocket streams.

Market hub: live quotes, trades, depth for subscribed contracts.
User hub: account, order, position, trade updates for a watched account.

Reference: TOPSTEPX_API_REFERENCE.md lines 86-134.

Transport: pysignalr (async, built on websockets library with 20s
ping/pong keepalive and automatic reconnection with token factory).
"""

import asyncio
import logging
import threading
import time
from enum import Enum
from typing import Any, Callable

from pysignalr.client import SignalRClient

logger = logging.getLogger(__name__)

import json as _json

MARKET_HUB_URL = "wss://rtc.topstepx.com/hubs/market"
USER_HUB_URL = "wss://rtc.topstepx.com/hubs/user"

# Reconnect with fresh token every 20 hours (token valid ~24h)
TOKEN_REFRESH_INTERVAL_S = 20 * 3600


def _extract_dict(data) -> Any:
    """Extract a dict from SignalR message arguments (may be list of mixed types)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
        for item in data:
            if isinstance(item, str):
                try:
                    parsed = _json.loads(item)
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, TypeError):
                    pass
    return data


class StreamState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Thread-safe quote cache
# ---------------------------------------------------------------------------

class QuoteCache:
    """Thread-safe cache for latest market quotes keyed by contract ID.

    Merges partial updates: TopstepX sends only changed fields per tick,
    so we overlay non-null values onto the existing cache entry.
    """

    def __init__(self):
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def update(self, contract_id: str, quote: dict) -> None:
        with self._lock:
            existing = self._data.get(contract_id)
            if existing is not None:
                for k, v in quote.items():
                    if v is not None:
                        existing[k] = v
            else:
                self._data[contract_id] = dict(quote)

    def get(self, contract_id: str) -> dict | None:
        with self._lock:
            entry = self._data.get(contract_id)
            return dict(entry) if entry else None  # return a copy

    def get_field(self, contract_id: str, field: str,
                  default: Any = None) -> Any:
        with self._lock:
            q = self._data.get(contract_id)
            if q is None:
                return default
            return q.get(field, default)

    def all(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._data)


# Module-level shared cache
quote_cache = QuoteCache()


# ---------------------------------------------------------------------------
# Market Hub Stream
# ---------------------------------------------------------------------------

class MarketStream:
    """SignalR stream for real-time market data (quotes, trades, depth).

    Supports single or multi-contract subscriptions on one WebSocket connection.
    Uses pysignalr (async) running in a dedicated background thread.

    Usage (single contract -- backward compatible):
        stream = MarketStream(token, contract_id="CON.F.US.EP.M26")

    Usage (multi-contract -- one connection, all quotes):
        stream = MarketStream(token, contract_ids=[
            "CON.F.US.EP.M26", "CON.F.US.ENQ.M26", "CON.F.US.USA.M26",
        ])
        stream.start()
        latest_es = quote_cache.get("CON.F.US.EP.M26")
        latest_nq = quote_cache.get("CON.F.US.ENQ.M26")
        stream.stop()
    """

    # Rapid-failure detection: if the connection is open for less than this
    # many seconds before closing, count it as a rapid failure.
    _RAPID_THRESHOLD_S = 10
    _MAX_RAPID_FAILURES = 5

    def __init__(self, token: str,
                 contract_id: str | None = None,
                 contract_ids: list[str] | None = None,
                 on_quote: Callable[[dict], None] | None = None,
                 on_trade: Callable[[dict], None] | None = None,
                 on_depth: Callable[[dict], None] | None = None):
        self._token = token

        # Accept either single contract_id or list of contract_ids
        if contract_ids:
            self._contract_ids = list(contract_ids)
        elif contract_id:
            self._contract_ids = [contract_id]
        else:
            raise ValueError("Must provide contract_id or contract_ids")

        # Backward compat: expose first contract as the "primary"
        self._contract_id = self._contract_ids[0]

        # Build reverse lookup: symbol name -> contract_id
        # For quotes with a "symbol" field (e.g. "ESM6") we map back to the
        # full TopstepX contract ID (e.g. "CON.F.US.EP.M26")
        self._symbol_map: dict[str, str] = {}
        self._build_symbol_map()

        self._on_quote = on_quote
        self._on_trade = on_trade
        self._on_depth = on_depth
        self._client: SignalRClient | None = None
        self._state = StreamState.IDLE
        self._lock = threading.Lock()
        self._last_open_time: float = 0
        self._rapid_failures: int = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._async_task: asyncio.Task | None = None

    def _build_symbol_map(self):
        """Build symbol -> contract_id reverse lookup from contract_ids.json.

        Maps multiple key formats to handle different quote payload shapes:
        - Full contract ID: "CON.F.US.EP.M26" -> "CON.F.US.EP.M26"
        - Contract name:    "ESM6"             -> "CON.F.US.EP.M26"
        - Exchange symbol:  "F.US.EP"          -> "CON.F.US.EP.M26"
        """
        try:
            import json
            from pathlib import Path
            local_path = Path(__file__).resolve().parent.parent / "config" / "contract_ids.json"
            docker_path = Path("/captain/config/contract_ids.json")
            config_path = local_path if local_path.exists() else docker_path

            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                for _asset_id, info in config.get("contracts", {}).items():
                    cid = info.get("contract_id")
                    name = info.get("name")
                    if cid:
                        self._symbol_map[cid] = cid  # identity: CON.F.US.EP.M26
                        if name:
                            self._symbol_map[name] = cid  # name: ESM6
                        # Exchange symbol root: strip "CON." prefix and ".M26" suffix
                        # CON.F.US.EP.M26 -> F.US.EP
                        parts = cid.split(".")
                        if len(parts) >= 4 and parts[0] == "CON":
                            exchange_root = ".".join(parts[1:-1])  # F.US.EP
                            self._symbol_map[exchange_root] = cid
        except Exception as exc:
            logger.debug("Symbol map build from config failed: %s", exc)
        # Ensure all subscribed contract_ids map to themselves
        for cid in self._contract_ids:
            self._symbol_map[cid] = cid
            # Also derive exchange root from subscribed IDs directly
            parts = cid.split(".")
            if len(parts) >= 4 and parts[0] == "CON":
                exchange_root = ".".join(parts[1:-1])
                self._symbol_map[exchange_root] = cid

    @property
    def state(self) -> StreamState:
        return self._state

    def start(self) -> None:
        """Connect to market hub and subscribe to quotes.

        Creates a pysignalr client in a background thread with its own
        event loop.  The client handles reconnection internally; on_open
        re-subscribes to all contracts after every connect/reconnect.
        """
        self._state = StreamState.CONNECTING
        self._rapid_failures = 0
        try:
            self._client = self._create_client(MARKET_HUB_URL)
            self._client.on("GatewayQuote", self._async_handle_quote)
            self._client.on("GatewayTrade", self._async_handle_trade)
            self._client.on("GatewayDepth", self._async_handle_depth)
            self._client.on("GatewayLogout", self._async_handle_logout)
            self._client.on_open(self._async_on_open)
            self._client.on_close(self._async_on_close)
            self._client.on_error(self._async_on_error)

            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True,
                name="market-stream",
            )
            self._thread.start()
        except Exception:
            self._state = StreamState.ERROR
            logger.exception("MarketStream failed to start")
            raise

    def stop(self) -> None:
        """Disconnect from market hub. Thread-safe, called from main thread."""
        if self._state == StreamState.DISCONNECTED:
            return
        self._state = StreamState.DISCONNECTED
        # Cancel the async task to stop pysignalr's run loop
        if self._async_task and not self._async_task.done():
            self._loop.call_soon_threadsafe(self._async_task.cancel)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._client = None
        logger.info("MarketStream stopped (%d contracts)", len(self._contract_ids))

    @property
    def contract_ids(self) -> list[str]:
        """List of subscribed contract IDs."""
        return list(self._contract_ids)

    def add_contract(self, contract_id: str) -> None:
        """Subscribe to an additional contract on the live connection."""
        if contract_id not in self._contract_ids:
            self._contract_ids.append(contract_id)
            self._symbol_map[contract_id] = contract_id
            parts = contract_id.split(".")
            if len(parts) >= 4 and parts[0] == "CON":
                exchange_root = ".".join(parts[1:-1])
                self._symbol_map[exchange_root] = contract_id
            if (self._state == StreamState.CONNECTED
                    and self._client and self._loop
                    and self._loop.is_running()):
                asyncio.run_coroutine_threadsafe(
                    self._client.send("SubscribeContractQuotes", [contract_id]),
                    self._loop,
                )
                logger.info("MarketStream: added subscription for %s", contract_id)

    def update_token(self, new_token: str) -> None:
        """Reconnect with a fresh token (tokens expire ~24h).

        Updates the stored token (picked up by access_token_factory on next
        connect) then restarts the stream.
        """
        logger.info("MarketStream token refresh — reconnecting (%d contracts)",
                     len(self._contract_ids))
        self._token = new_token
        self.stop()
        time.sleep(1)
        self.start()

    # -- Event loop ---------------------------------------------------------

    def _run_loop(self) -> None:
        """Background thread: run the pysignalr client in its own event loop."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception:
            if self._state != StreamState.DISCONNECTED:
                logger.exception("MarketStream event loop exited unexpectedly")
                self._state = StreamState.ERROR

    async def _async_main(self) -> None:
        """Async entry point — stores task ref for cross-thread cancellation."""
        self._async_task = asyncio.current_task()
        try:
            await self._client.run()
        except asyncio.CancelledError:
            logger.debug("MarketStream async task cancelled")
        except Exception:
            if self._state != StreamState.DISCONNECTED:
                raise

    # -- Async callbacks (pysignalr interface) ------------------------------

    async def _async_on_open(self) -> None:
        """Called on every connect AND reconnect — (re-)subscribes here."""
        self._state = StreamState.CONNECTED
        self._last_open_time = time.time()
        logger.info("MarketStream CONNECTED — subscribing to %d contract(s)",
                     len(self._contract_ids))
        for cid in self._contract_ids:
            try:
                await self._client.send("SubscribeContractQuotes", [cid])
                logger.debug("Subscribed to %s", cid)
            except Exception as exc:
                logger.warning("Failed to subscribe to %s: %s", cid, exc)

    async def _async_on_close(self) -> None:
        """Rapid-failure detection — stops reconnect after repeated fast drops."""
        if self._state == StreamState.DISCONNECTED:
            return

        # Detect rapid connect/disconnect cycles (e.g. market closed, auth expired)
        uptime = time.time() - self._last_open_time if self._last_open_time else 0
        if self._last_open_time and uptime < self._RAPID_THRESHOLD_S:
            self._rapid_failures += 1
        else:
            self._rapid_failures = 0

        if self._rapid_failures >= self._MAX_RAPID_FAILURES:
            self._state = StreamState.DISCONNECTED
            logger.warning(
                "MarketStream: %d rapid failures (uptime <%.0fs each) — "
                "stopping reconnect (market likely closed or token expired)",
                self._rapid_failures, self._RAPID_THRESHOLD_S,
            )
            # Cancel the run task to stop pysignalr from reconnecting
            if self._async_task and not self._async_task.done():
                self._async_task.cancel()
            return

        self._state = StreamState.RECONNECTING
        if self._rapid_failures > 0:
            logger.info("MarketStream closed (rapid failure %d/%d) — reconnecting",
                        self._rapid_failures, self._MAX_RAPID_FAILURES)
        else:
            logger.warning("MarketStream connection closed — will reconnect")

    async def _async_on_error(self, error) -> None:
        """Log error; pysignalr handles reconnection internally."""
        logger.error("MarketStream error: %s", error)
        if self._state != StreamState.DISCONNECTED:
            self._state = StreamState.RECONNECTING

    async def _async_handle_logout(self, *args) -> None:
        logger.warning("MarketStream GatewayLogout received: %s", args)

    async def _async_handle_quote(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_quote(data)

    async def _async_handle_trade(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_trade(data)

    async def _async_handle_depth(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_depth(data)

    # -- Business logic handlers (UNCHANGED) --------------------------------

    def _handle_quote(self, data) -> None:
        """Process GatewayQuote event.

        For multi-contract streams, identifies which contract the quote
        belongs to via the 'symbol' or 'contractId' field in the payload.
        """
        data = _extract_dict(data)
        if isinstance(data, dict):
            contract_id = self._resolve_quote_contract(data)
            quote_cache.update(contract_id, data)
        if self._on_quote:
            self._on_quote(data)

    def _resolve_quote_contract(self, data: dict) -> str:
        """Map incoming quote data to a contract_id for cache storage."""
        # 1. Direct contractId field
        cid = data.get("contractId") or data.get("contract_id")
        if cid and cid in self._symbol_map:
            return self._symbol_map[cid]

        # 2. Symbol field (e.g. "ESM6" -> "CON.F.US.EP.M26")
        symbol = data.get("symbol") or data.get("symbolId")
        if symbol and symbol in self._symbol_map:
            return self._symbol_map[symbol]

        # 3. Single-contract stream — use the one we know
        if len(self._contract_ids) == 1:
            return self._contract_ids[0]

        # 4. Fallback — log warning and use primary
        logger.warning("Could not identify contract for quote: %s",
                       {k: data.get(k) for k in ("symbol", "symbolId", "contractId")})
        return self._contract_ids[0]

    def _handle_trade(self, data) -> None:
        data = _extract_dict(data)
        if self._on_trade:
            self._on_trade(data)

    def _handle_depth(self, data) -> None:
        data = _extract_dict(data)
        if self._on_depth:
            self._on_depth(data)

    # -- Client builder -----------------------------------------------------

    def _create_client(self, hub_url: str) -> SignalRClient:
        """Create pysignalr client for TopstepX.

        TopstepX requires skip_negotiation (direct WebSocket) with the
        access token as a query parameter in the URL.  Token refresh
        is handled by update_token() which stops/restarts the stream,
        creating a new client with the fresh token in the URL.
        """
        url_with_token = f"{hub_url}?access_token={self._token}"
        client = SignalRClient(
            url=url_with_token,
            headers={"User-Agent": "Captain/1.0"},
        )
        client._transport._skip_negotiation = True
        return client


# ---------------------------------------------------------------------------
# User Hub Stream
# ---------------------------------------------------------------------------

class UserStream:
    """SignalR stream for real-time user data (accounts, orders, positions, trades).

    Uses pysignalr (async) running in a dedicated background thread.

    Usage:
        stream = UserStream(token, account_id=12345)
        stream.start()
        # ... later ...
        stream.stop()
    """

    _RAPID_THRESHOLD_S = 10
    _MAX_RAPID_FAILURES = 5

    def __init__(self, token: str, account_id: int,
                 on_account_update: Callable[[dict], None] | None = None,
                 on_order_update: Callable[[dict], None] | None = None,
                 on_position_update: Callable[[dict], None] | None = None,
                 on_trade_update: Callable[[dict], None] | None = None):
        self._token = token
        self._account_id = account_id
        self._on_account_update = on_account_update
        self._on_order_update = on_order_update
        self._on_position_update = on_position_update
        self._on_trade_update = on_trade_update
        self._client: SignalRClient | None = None
        self._state = StreamState.IDLE
        self._account_cache: dict[str, Any] = {}
        self._positions_cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._last_open_time: float = 0
        self._rapid_failures: int = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._async_task: asyncio.Task | None = None

    @property
    def state(self) -> StreamState:
        return self._state

    @property
    def account_data(self) -> dict:
        with self._lock:
            return dict(self._account_cache)

    @property
    def positions(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._positions_cache)

    def start(self) -> None:
        """Connect to user hub and subscribe to all user events."""
        self._state = StreamState.CONNECTING
        self._rapid_failures = 0
        try:
            self._client = self._create_client(USER_HUB_URL)
            self._client.on("GatewayUserAccount",
                            self._async_handle_account)
            self._client.on("GatewayUserOrder",
                            self._async_handle_order)
            self._client.on("GatewayUserPosition",
                            self._async_handle_position)
            self._client.on("GatewayUserTrade",
                            self._async_handle_trade)
            self._client.on("GatewayLogout",
                            self._async_handle_logout)
            self._client.on_open(self._async_on_open)
            self._client.on_close(self._async_on_close)
            self._client.on_error(self._async_on_error)

            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True,
                name="user-stream",
            )
            self._thread.start()
        except Exception:
            self._state = StreamState.ERROR
            logger.exception("UserStream failed to start")
            raise

    def stop(self) -> None:
        """Disconnect from user hub. Thread-safe, called from main thread."""
        if self._state == StreamState.DISCONNECTED:
            return
        self._state = StreamState.DISCONNECTED
        if self._async_task and not self._async_task.done():
            self._loop.call_soon_threadsafe(self._async_task.cancel)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._client = None
        logger.info("UserStream stopped for account %s", self._account_id)

    def update_token(self, new_token: str) -> None:
        """Reconnect with a fresh token.

        Updates the stored token (picked up by access_token_factory on next
        connect) then restarts the stream.
        """
        logger.info("UserStream token refresh — reconnecting")
        self._token = new_token
        self.stop()
        time.sleep(1)
        self.start()

    # -- Event loop ---------------------------------------------------------

    def _run_loop(self) -> None:
        """Background thread: run the pysignalr client in its own event loop."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception:
            if self._state != StreamState.DISCONNECTED:
                logger.exception("UserStream event loop exited unexpectedly")
                self._state = StreamState.ERROR

    async def _async_main(self) -> None:
        """Async entry point — stores task ref for cross-thread cancellation."""
        self._async_task = asyncio.current_task()
        try:
            await self._client.run()
        except asyncio.CancelledError:
            logger.debug("UserStream async task cancelled")
        except Exception:
            if self._state != StreamState.DISCONNECTED:
                raise

    # -- Async callbacks (pysignalr interface) ------------------------------

    async def _async_on_open(self) -> None:
        """Called on every connect AND reconnect — (re-)subscribes here."""
        self._state = StreamState.CONNECTED
        self._last_open_time = time.time()
        logger.info("UserStream CONNECTED — subscribing to account %s",
                     self._account_id)
        try:
            await self._client.send("SubscribeAccounts", [])
            await self._client.send("SubscribeOrders", [self._account_id])
            await self._client.send("SubscribePositions", [self._account_id])
            await self._client.send("SubscribeTrades", [self._account_id])
        except Exception as exc:
            logger.warning("UserStream subscription failed: %s", exc)

    async def _async_on_close(self) -> None:
        """Rapid-failure detection — stops reconnect after repeated fast drops."""
        if self._state == StreamState.DISCONNECTED:
            return

        uptime = time.time() - self._last_open_time if self._last_open_time else 0
        if self._last_open_time and uptime < self._RAPID_THRESHOLD_S:
            self._rapid_failures += 1
        else:
            self._rapid_failures = 0

        if self._rapid_failures >= self._MAX_RAPID_FAILURES:
            self._state = StreamState.DISCONNECTED
            logger.warning(
                "UserStream: %d rapid failures — stopping reconnect "
                "(market likely closed or token expired)",
                self._rapid_failures,
            )
            if self._async_task and not self._async_task.done():
                self._async_task.cancel()
            return

        self._state = StreamState.RECONNECTING
        if self._rapid_failures > 0:
            logger.info("UserStream closed (rapid failure %d/%d) — reconnecting",
                        self._rapid_failures, self._MAX_RAPID_FAILURES)
        else:
            logger.warning("UserStream connection closed — will reconnect")

    async def _async_on_error(self, error) -> None:
        """Log error; pysignalr handles reconnection internally."""
        logger.error("UserStream error: %s", error)
        if self._state != StreamState.DISCONNECTED:
            self._state = StreamState.RECONNECTING

    async def _async_handle_logout(self, *args) -> None:
        logger.warning("UserStream GatewayLogout received: %s", args)

    async def _async_handle_account(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_account(data)

    async def _async_handle_order(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_order(data)

    async def _async_handle_position(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_position(data)

    async def _async_handle_trade(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_trade(data)

    # -- Business logic handlers (UNCHANGED) --------------------------------

    def _handle_account(self, data) -> None:
        data = _extract_dict(data)
        if isinstance(data, dict):
            with self._lock:
                self._account_cache = data
        if self._on_account_update:
            self._on_account_update(data)

    def _handle_order(self, data) -> None:
        data = _extract_dict(data)
        if self._on_order_update:
            self._on_order_update(data)

    def _handle_position(self, data) -> None:
        data = _extract_dict(data)
        if isinstance(data, dict):
            pos_id = str(data.get("id", ""))
            with self._lock:
                if data.get("size", 0) == 0:
                    self._positions_cache.pop(pos_id, None)
                else:
                    self._positions_cache[pos_id] = data
        if self._on_position_update:
            self._on_position_update(data)

    def _handle_trade(self, data) -> None:
        data = _extract_dict(data)
        if self._on_trade_update:
            self._on_trade_update(data)

    # -- Client builder -----------------------------------------------------

    def _create_client(self, hub_url: str) -> SignalRClient:
        """Create pysignalr client for TopstepX.

        TopstepX requires skip_negotiation (direct WebSocket) with the
        access token as a query parameter in the URL.  Token refresh
        is handled by update_token() which stops/restarts the stream,
        creating a new client with the fresh token in the URL.
        """
        url_with_token = f"{hub_url}?access_token={self._token}"
        client = SignalRClient(
            url=url_with_token,
            headers={"User-Agent": "Captain/1.0"},
        )
        client._transport._skip_negotiation = True
        return client
