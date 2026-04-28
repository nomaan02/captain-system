# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""TopstepX REST API client shared across Captain processes.

All REST calls go through requests.post() to https://api.topstepx.com/api/...
Reference: TOPSTEPX_API_REFERENCE.md in project root.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.topstepx.com/api"

# Token refresh threshold — revalidate 4 hours before expiry (~24h token)
TOKEN_REFRESH_THRESHOLD_S = 20 * 3600  # 20 hours
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_BASE_DELAY_S = 1.0  # exponential backoff: 1s, 2s, 4s


class TopstepXClientError(Exception):
    """Base exception for TopstepX API errors."""


class AuthenticationError(TopstepXClientError):
    """Authentication failed."""


class APIError(TopstepXClientError):
    """API request failed."""

    def __init__(self, message: str, error_code: str | None = None,
                 status_code: int | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Enum constants (from TOPSTEPX_API_REFERENCE.md lines 27-35)
# ---------------------------------------------------------------------------

class OrderSide:
    BUY = 0   # Bid
    SELL = 1  # Ask


class OrderType:
    UNKNOWN = 0
    LIMIT = 1
    MARKET = 2
    STOP = 4
    TRAILING_STOP = 5
    JOIN_BID = 6
    JOIN_ASK = 7


class OrderStatus:
    NONE = 0
    OPEN = 1
    FILLED = 2
    CANCELLED = 3
    EXPIRED = 4
    REJECTED = 5
    PENDING = 6


class PositionType:
    UNDEFINED = 0
    LONG = 1
    SHORT = 2


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TopstepXClient:
    """Thread-safe REST client for TopstepX / ProjectX Gateway API."""

    def __init__(self, username: str | None = None, api_key: str | None = None,
                 environment: str | None = None):
        self._username = username or os.environ.get("TOPSTEP_USERNAME", "")
        self._api_key = api_key or os.environ.get("TOPSTEP_API_KEY", "")
        self._environment = environment or os.environ.get("TRADING_ENVIRONMENT", "LIVE")
        self._token: str | None = None
        self._token_acquired_at: float = 0.0
        self._lock = threading.Lock()
        self._session = requests.Session()

    # -- Auth ---------------------------------------------------------------

    def authenticate(self) -> str:
        """Login with API key. Returns JWT token."""
        resp = self._session.post(
            f"{BASE_URL}/Auth/loginKey",
            headers={"Content-Type": "application/json"},
            json={"userName": self._username, "apiKey": self._api_key},
            timeout=10,
        )
        data = self._parse_response(resp, "Auth/loginKey")
        if not data.get("success") and not data.get("token"):
            raise AuthenticationError(
                f"Login failed: {data.get('errorCode', 'unknown')}"
            )
        with self._lock:
            self._token = data["token"]
            self._token_acquired_at = time.time()
        logger.info("TopstepX authenticated as %s (env=%s)",
                     self._username, self._environment)
        return self._token

    def validate_token(self) -> str:
        """Refresh token via /Auth/validate. Returns new token."""
        resp = self._post("/Auth/validate", {}, skip_refresh=True)
        if not resp.get("success") and not resp.get("newToken"):
            raise AuthenticationError(
                f"Token validation failed: {resp.get('errorCode', 'unknown')}"
            )
        new_token = resp.get("newToken")
        if new_token is None:
            raise AuthenticationError(
                "Token validation response missing 'newToken' field"
            )
        with self._lock:
            self._token = new_token
            self._token_acquired_at = time.time()
        logger.debug("TopstepX token refreshed")
        return self._token

    def logout(self) -> bool:
        """End session."""
        try:
            resp = self._post("/Auth/logout", {}, skip_refresh=True)
            return resp.get("success", False)
        except Exception:
            logger.debug("Logout request failed (session may already be closed)")
            return False
        finally:
            with self._lock:
                self._token = None

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    @property
    def current_token(self) -> str | None:
        return self._token

    @property
    def token_age_seconds(self) -> float:
        if self._token_acquired_at == 0:
            return float("inf")
        return time.time() - self._token_acquired_at

    # -- Accounts -----------------------------------------------------------

    def get_accounts(self, only_active: bool = True) -> list[dict]:
        """Search accounts. Returns list of account dicts."""
        resp = self._post("/Account/search",
                          {"onlyActiveAccounts": only_active})
        return resp.get("accounts", [])

    def get_account_by_name(self, name: str) -> dict | None:
        """Find a specific account by name (e.g. '150KTC-V2-551001-19064435')."""
        accounts = self.get_accounts(only_active=True)
        for acc in accounts:
            if acc.get("name") == name:
                return acc
        return None

    # -- Contracts ----------------------------------------------------------

    def search_contracts(self, search_text: str = "ES",
                         live: bool | None = None) -> list[dict]:
        """Search available contracts.

        Per ProjectX Gateway API spec, `live` is REQUIRED. Defaults to
        False (sim/eval data subscription) — overridable per-call or via
        TOPSTEP_LIVE_DATA=true env. The flag refers to the *data*
        subscription, not the trading environment; most accounts (incl.
        all Combine eval accounts) only have the sim subscription.
        """
        resp = self._post("/Contract/search", {
            "searchText": search_text,
            "live": self._resolve_live_flag(live),
        })
        return resp.get("contracts", [])

    def get_contract_by_id(self, contract_id: str) -> dict | None:
        """Get contract details by ID (e.g. 'CON.F.US.EP.M26')."""
        resp = self._post("/Contract/searchById",
                          {"contractId": contract_id})
        return resp.get("contract")

    # -- Historical Bars ----------------------------------------------------

    def get_bars(self, contract_id: str, bar_unit: int, bar_unit_number: int,
                 start_date: str, end_date: str,
                 limit: int = 20000,
                 include_partial_bar: bool = False,
                 live: bool | None = None) -> list[dict]:
        """Fetch historical OHLCV bars via /History/retrieveBars.

        bar_unit: 1=Second, 2=Minute, 3=Hour, 4=Day, 5=Week, 6=Month
        start_date / end_date: ISO8601 (date-only accepted; normalised to
            midnight UTC). Per ProjectX spec these map to startTime/endTime.
        limit: max bars to retrieve (spec cap is 20000).
        include_partial_bar: include the in-progress current bar.
        live: True for LIVE data feed, False for sim. Defaults to False
            since most TopstepX accounts (all Combine evals) only have
            the sim/historical feed; a True request without an active
            live data subscription returns bars=[] silently with HTTP 200.
            Override per-call or set TOPSTEP_LIVE_DATA=true.
        """
        resolved_live = self._resolve_live_flag(live)
        resp = self._post("/History/retrieveBars", {
            "contractId": contract_id,
            "live": resolved_live,
            "startTime": self._normalise_iso_datetime(start_date),
            "endTime": self._normalise_iso_datetime(end_date),
            "unit": bar_unit,
            "unitNumber": bar_unit_number,
            "limit": limit,
            "includePartialBar": include_partial_bar,
        })
        bars = resp.get("bars", [])
        if not bars:
            logger.debug(
                "retrieveBars returned 0 bars: contract=%s live=%s "
                "window=%s..%s success=%s errorCode=%s errorMessage=%s",
                contract_id, resolved_live,
                self._normalise_iso_datetime(start_date),
                self._normalise_iso_datetime(end_date),
                resp.get("success"), resp.get("errorCode"),
                resp.get("errorMessage"),
            )
        return bars

    def _resolve_live_flag(self, live: bool | None) -> bool:
        """Return value for ProjectX `live` flag (data-subscription toggle).

        Precedence: explicit kwarg > TOPSTEP_LIVE_DATA env > False default.

        IMPORTANT: this controls the *market-data subscription*, not the
        trading environment. TRADING_ENVIRONMENT=LIVE does NOT imply a live
        data subscription — Combine eval accounts run on the sim feed even
        when trading the live platform. Defaulting to False prevents silent
        empty responses on the common case.
        """
        if live is not None:
            return live
        env_override = os.environ.get("TOPSTEP_LIVE_DATA", "").strip().lower()
        if env_override in ("1", "true", "yes"):
            return True
        return False

    @staticmethod
    def _normalise_iso_datetime(value: str) -> str:
        """Accept date or datetime; return ISO datetime suitable for the API.

        ProjectX `/History/retrieveBars` requires `startTime`/`endTime` as
        ISO8601 datetimes. If the caller passes just `YYYY-MM-DD`, append
        `T00:00:00Z` so ASP.NET model binding accepts it.
        """
        if not value:
            return value
        if "T" in value:
            return value
        return f"{value}T00:00:00Z"

    # -- Orders -------------------------------------------------------------

    def place_order(self, account_id: int, contract_id: str,
                    order_type: int, side: int, size: int,
                    limit_price: float | None = None,
                    stop_price: float | None = None,
                    trail_price: float | None = None,
                    custom_tag: str | None = None,
                    stop_loss_bracket: dict | None = None,
                    take_profit_bracket: dict | None = None) -> dict:
        """Place an order. Returns {orderId, success, errorCode}.

        Bracket params attach atomic SL/TP to the entry via the exchange.
        Each is ``{"ticks": <int>, "type": <int>}`` per TopstepX API spec.
        """
        payload: dict[str, Any] = {
            "accountId": account_id,
            "contractId": contract_id,
            "type": order_type,
            "side": side,
            "size": size,
        }
        if limit_price is not None:
            payload["limitPrice"] = limit_price
        if stop_price is not None:
            payload["stopPrice"] = stop_price
        if trail_price is not None:
            payload["trailPrice"] = trail_price
        if custom_tag is not None:
            payload["customTag"] = custom_tag
        if stop_loss_bracket is not None:
            payload["stopLossBracket"] = stop_loss_bracket
        if take_profit_bracket is not None:
            payload["takeProfitBracket"] = take_profit_bracket
        return self._post("/Order/place", payload)

    def place_market_order(self, account_id: int, contract_id: str,
                           side: int, size: int) -> dict:
        """Convenience: place a market order."""
        return self.place_order(account_id, contract_id,
                                OrderType.MARKET, side, size)

    def place_limit_order(self, account_id: int, contract_id: str,
                          side: int, size: int,
                          limit_price: float) -> dict:
        """Convenience: place a limit order."""
        return self.place_order(account_id, contract_id,
                                OrderType.LIMIT, side, size,
                                limit_price=limit_price)

    def place_stop_order(self, account_id: int, contract_id: str,
                         side: int, size: int,
                         stop_price: float) -> dict:
        """Convenience: place a stop order."""
        return self.place_order(account_id, contract_id,
                                OrderType.STOP, side, size,
                                stop_price=stop_price)

    def place_bracket_order(self, account_id: int, contract_id: str,
                            side: int, size: int,
                            sl_ticks: int, tp_ticks: int) -> dict:
        """Place a market entry with atomic SL+TP brackets.

        The exchange attaches SL and TP relative to the fill price.
        SL uses Stop (type 4) for guaranteed fill; TP uses Limit (type 1).
        Brackets are OCO — one triggers, the other cancels automatically.

        Callers MUST pass positive magnitudes for ``sl_ticks`` and ``tp_ticks``
        (i.e. the absolute tick distance between fill and the bracket). The
        TopstepX engine requires the bracket ticks to be a *signed* offset
        from the fill price:

        - BUY (long):  SL is below fill -> negative; TP is above -> positive
        - SELL (short): SL is above fill -> positive; TP is below -> negative

        Sending the wrong sign returns ``errorCode 2``: "Invalid stop loss
        ticks (N). Ticks should be less than zero when longing." (and the
        symmetric case for shorting). This method handles the sign so all
        callers can keep working with positive magnitudes.
        """
        sl_mag = abs(int(sl_ticks))
        tp_mag = abs(int(tp_ticks))
        if side == OrderSide.BUY:
            sl_signed = -sl_mag
            tp_signed = tp_mag
        elif side == OrderSide.SELL:
            sl_signed = sl_mag
            tp_signed = -tp_mag
        else:
            raise ValueError(
                f"place_bracket_order: invalid side={side}; "
                f"expected {OrderSide.BUY} (BUY) or {OrderSide.SELL} (SELL)"
            )
        return self.place_order(
            account_id, contract_id,
            OrderType.MARKET, side, size,
            stop_loss_bracket={"ticks": sl_signed, "type": OrderType.STOP},
            take_profit_bracket={"ticks": tp_signed, "type": OrderType.LIMIT},
        )

    def modify_order(self, account_id: int, order_id: int,
                     size: int | None = None,
                     limit_price: float | None = None,
                     stop_price: float | None = None,
                     trail_price: float | None = None) -> dict:
        """Modify an existing order.

        Per ProjectX spec, all of size/limitPrice/stopPrice/trailPrice are
        Optional — at least one should be provided in practice.
        """
        payload: dict[str, Any] = {
            "accountId": account_id,
            "orderId": order_id,
        }
        if size is not None:
            payload["size"] = size
        if limit_price is not None:
            payload["limitPrice"] = limit_price
        if stop_price is not None:
            payload["stopPrice"] = stop_price
        if trail_price is not None:
            payload["trailPrice"] = trail_price
        return self._post("/Order/modify", payload)

    def cancel_order(self, account_id: int, order_id: int) -> dict:
        """Cancel an order."""
        return self._post("/Order/cancel",
                          {"accountId": account_id, "orderId": order_id})

    def search_orders(self, account_id: int,
                      start_timestamp: str | None = None,
                      end_timestamp: str | None = None) -> list[dict]:
        """Search orders by time range.

        Per ProjectX spec, startTimestamp is REQUIRED. Defaults to last 24h
        if caller omits it.
        """
        payload: dict[str, Any] = {
            "accountId": account_id,
            "startTimestamp": start_timestamp or self._default_start_timestamp(),
        }
        if end_timestamp:
            payload["endTimestamp"] = end_timestamp
        resp = self._post("/Order/search", payload)
        return resp.get("orders", [])

    def search_open_orders(self, account_id: int) -> list[dict]:
        """Get currently open/working orders for an account."""
        resp = self._post("/Order/searchOpen", {"accountId": account_id})
        return resp.get("orders", [])

    # -- Positions ----------------------------------------------------------

    def search_positions(self, account_id: int) -> list[dict]:
        """Get open positions for an account."""
        resp = self._post("/Position/searchOpen", {"accountId": account_id})
        return resp.get("positions", [])

    def close_position(self, account_id: int, contract_id: str,
                       size: int | None = None) -> dict:
        """Close (or partially close) a position.

        Per ProjectX spec there are TWO endpoints:
        - /Position/closeContract        — full close, payload {accountId, contractId}
        - /Position/partialCloseContract — partial, payload {accountId, contractId, size}

        If `size` is None, performs a full close. Otherwise partial.
        The previous /Position/close endpoint does not exist; calls to it
        404'd silently and let naked positions linger.
        """
        if size is None:
            return self._post("/Position/closeContract", {
                "accountId": account_id,
                "contractId": contract_id,
            })
        return self._post("/Position/partialCloseContract", {
            "accountId": account_id,
            "contractId": contract_id,
            "size": int(size),
        })

    # -- Trades -------------------------------------------------------------

    def search_trades(self, account_id: int,
                      start_timestamp: str | None = None,
                      end_timestamp: str | None = None) -> list[dict]:
        """Get trade history for an account.

        Per ProjectX spec, startTimestamp is REQUIRED. Defaults to last 24h
        if caller omits it (matches search_orders convention).
        """
        payload: dict[str, Any] = {
            "accountId": account_id,
            "startTimestamp": start_timestamp or self._default_start_timestamp(),
        }
        if end_timestamp:
            payload["endTimestamp"] = end_timestamp
        resp = self._post("/Trade/search", payload)
        return resp.get("trades", [])

    @staticmethod
    def _default_start_timestamp() -> str:
        """ISO datetime 24 hours ago — used as fallback startTimestamp."""
        from datetime import timedelta
        dt = datetime.now(timezone.utc) - timedelta(hours=24)
        return dt.isoformat()

    # -- Internal -----------------------------------------------------------

    def _ensure_token(self) -> None:
        """Authenticate if no token, or refresh if stale."""
        if self._token is None:
            self.authenticate()
            return
        if self.token_age_seconds > TOKEN_REFRESH_THRESHOLD_S:
            logger.info("Token age %.0fh — refreshing",
                        self.token_age_seconds / 3600)
            self.validate_token()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _post(self, endpoint: str, payload: dict,
              skip_refresh: bool = False) -> dict:
        """POST to TopstepX API with auto token management and 429 backoff."""
        if not skip_refresh:
            self._ensure_token()
        url = f"{BASE_URL}{endpoint}"
        for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
            try:
                resp = self._session.post(
                    url,
                    headers=self._auth_headers(),
                    json=payload,
                    timeout=10,
                )
                if resp.status_code == 429:
                    if attempt < RATE_LIMIT_MAX_RETRIES:
                        retry_after = resp.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else (
                            RATE_LIMIT_BASE_DELAY_S * (2 ** attempt)
                        )
                        logger.warning("429 rate-limited on %s — retry %d/%d in %.1fs",
                                       endpoint, attempt + 1, RATE_LIMIT_MAX_RETRIES, delay)
                        time.sleep(delay)
                        continue
                    raise APIError(f"Rate limited on {endpoint} after {RATE_LIMIT_MAX_RETRIES} retries",
                                   status_code=429)
                return self._parse_response(resp, endpoint)
            except requests.Timeout:
                raise APIError(f"Timeout on {endpoint}", status_code=408)
            except requests.ConnectionError as e:
                raise APIError(f"Connection error on {endpoint}: {e}")
        raise APIError(f"Exhausted retries on {endpoint}", status_code=429)

    @staticmethod
    def _parse_response(resp: requests.Response, endpoint: str) -> dict:
        """Parse JSON response, raise on HTTP errors (404 returns empty dict)."""
        if resp.status_code == 404:
            # Some endpoints return 404 for empty results (no positions, etc.)
            return {}
        if resp.status_code >= 400:
            try:
                data = resp.json()
            except ValueError:
                data = {}
            raise APIError(
                f"{endpoint} returned {resp.status_code}: "
                f"{data.get('errorCode', resp.text[:200])}",
                error_code=data.get("errorCode"),
                status_code=resp.status_code,
            )
        try:
            return resp.json()
        except ValueError:
            raise APIError(f"{endpoint} returned non-JSON: {resp.text[:200]}")

    def measure_latency(self) -> float:
        """Measure round-trip latency to API in milliseconds."""
        self._ensure_token()
        start = time.time()
        try:
            self._session.post(
                f"{BASE_URL}/Auth/validate",
                headers=self._auth_headers(),
                json={},
                timeout=10,
            )
            return (time.time() - start) * 1000
        except Exception:
            return -1.0


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-init, thread-safe)
# ---------------------------------------------------------------------------

_client_instance: TopstepXClient | None = None
_client_lock = threading.Lock()


def get_topstep_client() -> TopstepXClient:
    """Get or create the module-level TopstepX client singleton."""
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = TopstepXClient()
    return _client_instance
