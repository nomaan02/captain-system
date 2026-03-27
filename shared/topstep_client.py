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
    STOP_LIMIT = 3
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
            timeout=15,
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
        if not resp.get("success") and not resp.get("token"):
            raise AuthenticationError(
                f"Token validation failed: {resp.get('errorCode', 'unknown')}"
            )
        with self._lock:
            self._token = resp["token"]
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

    def search_contracts(self, search_text: str = "ES") -> list[dict]:
        """Search available contracts."""
        resp = self._post("/Contract/search", {"searchText": search_text})
        return resp.get("contracts", [])

    def get_contract_by_id(self, contract_id: str) -> dict | None:
        """Get contract details by ID (e.g. 'CON.F.US.EP.H26')."""
        resp = self._post("/Contract/searchById",
                          {"contractId": contract_id})
        return resp.get("contract")

    # -- Historical Bars ----------------------------------------------------

    def get_bars(self, contract_id: str, bar_unit: int, bar_unit_number: int,
                 start_date: str, end_date: str) -> list[dict]:
        """Fetch historical OHLCV bars.

        bar_unit: 1=Tick, 2=Minute, 3=Hour, 4=Day, 5=Week, 6=Month
        Dates as ISO8601 strings.
        """
        resp = self._post("/History/bars", {
            "contractId": contract_id,
            "barUnit": bar_unit,
            "barUnitNumber": bar_unit_number,
            "startDate": start_date,
            "endDate": end_date,
        })
        return resp.get("bars", [])

    # -- Orders -------------------------------------------------------------

    def place_order(self, account_id: int, contract_id: str,
                    order_type: int, side: int, size: int,
                    limit_price: float | None = None,
                    stop_price: float | None = None) -> dict:
        """Place an order. Returns {orderId, success, errorCode}."""
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

    def modify_order(self, account_id: int, order_id: int,
                     size: int | None = None,
                     limit_price: float | None = None,
                     stop_price: float | None = None) -> dict:
        """Modify an existing order."""
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
        return self._post("/Order/modify", payload)

    def cancel_order(self, account_id: int, order_id: int) -> dict:
        """Cancel an order."""
        return self._post("/Order/cancel",
                          {"accountId": account_id, "orderId": order_id})

    def search_orders(self, account_id: int,
                      start_timestamp: str | None = None,
                      end_timestamp: str | None = None) -> list[dict]:
        """Search orders by time range (startTimestamp required by API)."""
        payload: dict[str, Any] = {"accountId": account_id}
        if start_timestamp:
            payload["startTimestamp"] = start_timestamp
        else:
            # Default to last 24 hours
            from datetime import timedelta
            dt = datetime.now(timezone.utc) - timedelta(hours=24)
            payload["startTimestamp"] = dt.isoformat()
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
        resp = self._post("/Position/search", {"accountId": account_id})
        return resp.get("positions", [])

    def close_position(self, account_id: int, contract_id: str,
                       size: int) -> dict:
        """Close a position."""
        return self._post("/Position/close", {
            "accountId": account_id,
            "contractId": contract_id,
            "size": size,
        })

    # -- Trades -------------------------------------------------------------

    def search_trades(self, account_id: int,
                      start_timestamp: str | None = None,
                      end_timestamp: str | None = None) -> list[dict]:
        """Get trade history for an account."""
        payload: dict[str, Any] = {"accountId": account_id}
        if start_timestamp:
            payload["startTimestamp"] = start_timestamp
        if end_timestamp:
            payload["endTimestamp"] = end_timestamp
        resp = self._post("/Trade/search", payload)
        return resp.get("trades", [])

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
        """POST to TopstepX API with auto token management."""
        if not skip_refresh:
            self._ensure_token()
        url = f"{BASE_URL}{endpoint}"
        try:
            resp = self._session.post(
                url,
                headers=self._auth_headers(),
                json=payload,
                timeout=15,
            )
            return self._parse_response(resp, endpoint)
        except requests.Timeout:
            raise APIError(f"Timeout on {endpoint}", status_code=408)
        except requests.ConnectionError as e:
            raise APIError(f"Connection error on {endpoint}: {e}")

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
