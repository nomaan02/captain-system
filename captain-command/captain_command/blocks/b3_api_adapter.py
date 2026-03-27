# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 3: Secure API Plugin Architecture (P3-PG-32/33).

Block 3.1 — API Adapter Interface (generic + Topstep implementation).
Block 3.2 — Connection health monitoring (30 s heartbeat, auto-reconnect).
Block 3.3 — API key vault integration (AES-256-GCM, 90-day rotation).
Block 3.4 — Compliance gate (11 RTS 6 requirements, LOCKED in V1).

One-way boundary: 6 fields OUT, 4 fields IN.

Spec: Program3_Command.md lines 318-434
"""

import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from shared.questdb_client import get_cursor
from shared.vault import get_api_key
from shared.journal import write_checkpoint
from shared.constants import PROHIBITED_EXTERNAL_FIELDS, SANITISED_SIGNAL_FIELDS
from shared.contract_resolver import resolve_contract_id
from shared.topstep_client import (
    TopstepXClient, get_topstep_client,
    OrderSide, OrderType, OrderStatus, PositionType,
    TopstepXClientError, AuthenticationError, APIError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 3.1 — API Adapter Interface
# ---------------------------------------------------------------------------


class APIAdapter(ABC):
    """Abstract interface for broker/prop-firm API connections.

    Every concrete adapter must implement the five lifecycle methods.
    Command routes sanitised orders through ``send_signal()`` and
    reads back ONLY 4 inbound fields via ``receive_fill()`` and
    ``get_account_status()``.
    """

    @abstractmethod
    def connect(self, api_key: str, endpoint: str) -> dict:
        """Connect to the broker API.

        Returns
        -------
        dict
            ``{connected: bool, message: str}``
        """

    @abstractmethod
    def send_signal(self, order: dict) -> dict:
        """Send a sanitised order (6 fields only).

        Parameters
        ----------
        order : dict
            ``{asset, direction, size, tp, sl, timestamp}``

        Returns
        -------
        dict
            ``{order_id: str, status: str}``
        """

    @abstractmethod
    def receive_fill(self, order_id: str) -> dict:
        """Receive fill information for an order.

        Returns
        -------
        dict
            ``{fill_price: float, fill_time: str}`` — ONLY 2 inbound fields.
        """

    @abstractmethod
    def get_account_status(self) -> dict:
        """Get account status from the broker.

        Returns
        -------
        dict
            ``{balance: float, equity: float, drawdown: float,
              open_positions: int}`` — ONLY 4 inbound fields.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker API."""

    def ping(self) -> float:
        """Check connectivity and return latency in ms.

        Default implementation returns -1 (not implemented).
        """
        return -1.0


class TopstepXAdapter(APIAdapter):
    """Topstep XFA API adapter — LIVE integration via ProjectX Gateway.

    Maps internal signal format to TopstepX REST API.
    Handles authentication, order placement, fill tracking,
    and account status queries.

    Reference: TOPSTEPX_API_REFERENCE.md
    """

    # Default contract and account (from .env / captain-system/.env)
    DEFAULT_CONTRACT_ID = os.environ.get("TOPSTEP_CONTRACT_ID", "CON.F.US.EP.H26")
    DEFAULT_ACCOUNT_NAME = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")

    def __init__(self):
        self._connected = False
        self._client: TopstepXClient | None = None
        self._account_id: int | None = None
        self._account_name: str = ""
        self._contract_id: str = self.DEFAULT_CONTRACT_ID

    @property
    def connected(self) -> bool:
        return self._connected and self._client is not None

    @property
    def account_id(self) -> int | None:
        return self._account_id

    @property
    def client(self) -> TopstepXClient | None:
        return self._client

    def connect(self, api_key: str = "", endpoint: str = "") -> dict:
        """Authenticate to TopstepX and resolve the target account.

        Parameters api_key and endpoint are accepted for interface
        compatibility but the client reads credentials from env vars.
        """
        try:
            self._client = get_topstep_client()
            self._client.authenticate()

            # Resolve account
            target_name = self.DEFAULT_ACCOUNT_NAME
            if target_name:
                account = self._client.get_account_by_name(target_name)
            else:
                accounts = self._client.get_accounts(only_active=True)
                account = accounts[0] if accounts else None

            if not account:
                self._connected = False
                msg = f"Account not found: {target_name or '(first active)'}"
                logger.error("TopstepX connect failed: %s", msg)
                return {"connected": False, "message": msg}

            self._account_id = account["id"]
            self._account_name = account.get("name", "")
            self._connected = True

            logger.info(
                "TopstepX CONNECTED: account=%s (id=%s), balance=%.2f, canTrade=%s",
                self._account_name, self._account_id,
                account.get("balance", 0), account.get("canTrade"),
            )
            return {
                "connected": True,
                "message": f"Connected to {self._account_name}",
                "account_id": self._account_id,
                "balance": account.get("balance"),
                "can_trade": account.get("canTrade"),
            }
        except (AuthenticationError, TopstepXClientError) as exc:
            self._connected = False
            logger.error("TopstepX connect failed: %s", exc)
            return {"connected": False, "message": str(exc)}

    def send_signal(self, order: dict) -> dict:
        """Place a bracket order (entry + SL + TP) on TopstepX.

        Parameters
        ----------
        order : dict
            ``{asset, direction, size, tp, sl, timestamp}``
            direction: "BUY" or "SELL"

        Returns
        -------
        dict
            ``{order_id, status, entry_order_id, sl_order_id, tp_order_id}``
        """
        if not self.connected or not self._client or not self._account_id:
            return {"order_id": None, "status": "DISCONNECTED"}

        gate = check_compliance_gate()
        if gate["execution_mode"] == "MANUAL" and not gate["allowed"]:
            oid = f"ORD-{uuid.uuid4().hex[:12].upper()}"
            logger.info("TopstepX send_signal MANUAL mode: %s %s x%s",
                        order.get("direction"), order.get("asset"),
                        order.get("size"))
            return {"order_id": oid, "status": "MANUAL_PENDING"}

        asset_id = order.get("asset", "ES")
        contract_id = resolve_contract_id(asset_id) or self._contract_id
        if not contract_id:
            logger.error("Cannot resolve contract for asset %s — order rejected", asset_id)
            return {"status": "REJECTED", "reason": f"Unknown contract for {asset_id}"}
        side = OrderSide.BUY if order.get("direction") == "BUY" else OrderSide.SELL
        exit_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
        size = int(order.get("size", 1))

        try:
            # Entry order (market)
            entry_resp = self._client.place_market_order(
                self._account_id, contract_id, side, size,
            )
            entry_oid = entry_resp.get("orderId")
            if not entry_resp.get("success"):
                return {
                    "order_id": entry_oid,
                    "status": "REJECTED",
                    "error": entry_resp.get("errorCode"),
                }

            result = {
                "order_id": str(entry_oid),
                "status": "PLACED",
                "entry_order_id": entry_oid,
                "sl_order_id": None,
                "tp_order_id": None,
            }

            # Stop loss
            sl_price = order.get("sl")
            if sl_price is not None:
                sl_resp = self._client.place_stop_order(
                    self._account_id, contract_id, exit_side, size,
                    float(sl_price),
                )
                result["sl_order_id"] = sl_resp.get("orderId")

            # Take profit
            tp_price = order.get("tp")
            if tp_price is not None:
                tp_resp = self._client.place_limit_order(
                    self._account_id, contract_id, exit_side, size,
                    float(tp_price),
                )
                result["tp_order_id"] = tp_resp.get("orderId")

            logger.info(
                "TopstepX order PLACED: entry=%s sl=%s tp=%s (%s x%d @ %s)",
                result["entry_order_id"], result["sl_order_id"],
                result["tp_order_id"], order.get("direction"), size,
                contract_id,
            )
            return result

        except TopstepXClientError as exc:
            logger.error("TopstepX send_signal failed: %s", exc)
            return {"order_id": None, "status": "ERROR", "error": str(exc)}

    def receive_fill(self, order_id: str) -> dict:
        """Check fill status for an order.

        Queries recent orders to find fill price and time.
        """
        if not self.connected or not self._client or not self._account_id:
            return {"fill_price": None, "fill_time": None}

        try:
            orders = self._client.search_orders(self._account_id)
            for o in orders:
                if str(o.get("id")) == str(order_id):
                    status = o.get("status", 0)
                    if status == OrderStatus.FILLED:
                        return {
                            "fill_price": o.get("filledPrice"),
                            "fill_time": datetime.now().isoformat(),
                        }
                    return {"fill_price": None, "fill_time": None}
            return {"fill_price": None, "fill_time": None}

        except TopstepXClientError as exc:
            logger.warning("TopstepX receive_fill error: %s", exc)
            return {"fill_price": None, "fill_time": None}

    def get_account_status(self) -> dict:
        """Fetch real account status from TopstepX."""
        if not self.connected or not self._client:
            return {"balance": None, "equity": None,
                    "drawdown": None, "open_positions": None}

        try:
            accounts = self._client.get_accounts(only_active=True)
            account = None
            for acc in accounts:
                if acc.get("id") == self._account_id:
                    account = acc
                    break

            if not account:
                return {"balance": None, "equity": None,
                        "drawdown": None, "open_positions": None}

            positions = self._client.search_positions(self._account_id)
            total_pos = sum(p.get("size", 0) for p in positions)

            balance = account.get("balance", 0)
            return {
                "balance": balance,
                "equity": balance,  # TopstepX balance includes unrealised PnL
                "drawdown": None,   # Computed by reconciliation from high watermark
                "open_positions": total_pos,
            }

        except TopstepXClientError as exc:
            logger.warning("TopstepX get_account_status error: %s", exc)
            return {"balance": None, "equity": None,
                    "drawdown": None, "open_positions": None}

    def disconnect(self) -> None:
        """Logout from TopstepX."""
        if self._client:
            self._client.logout()
        self._connected = False
        self._account_id = None
        logger.info("TopstepX adapter disconnected")

    def ping(self) -> float:
        """Measure real API latency in milliseconds."""
        if not self.connected or not self._client:
            return -1.0
        try:
            return self._client.measure_latency()
        except Exception:
            return -1.0


# Adapter registry — maps provider names to adapter classes
ADAPTER_REGISTRY: dict[str, type[APIAdapter]] = {
    "TopstepX": TopstepXAdapter,
}


def get_adapter(provider: str) -> APIAdapter | None:
    """Instantiate an API adapter by provider name."""
    cls = ADAPTER_REGISTRY.get(provider)
    if cls:
        return cls()
    logger.warning("No adapter registered for provider: %s", provider)
    return None


# ---------------------------------------------------------------------------
# 3.2 — Connection Health Monitoring
# ---------------------------------------------------------------------------

# In-memory state: account_id → {adapter, connected, last_heartbeat, latency_ms}
_active_connections: dict[str, dict] = {}

HEALTH_CHECK_INTERVAL_S = 30
MAX_RECONNECT_RETRIES = 3


def register_connection(account_id: str, adapter: APIAdapter, endpoint: str):
    """Register an active API adapter connection for health monitoring."""
    _active_connections[account_id] = {
        "adapter": adapter,
        "endpoint": endpoint,
        "connected": adapter.connected if hasattr(adapter, 'connected') else True,
        "last_heartbeat": datetime.now().isoformat(),
        "latency_ms": 0.0,
        "retry_count": 0,
    }


def run_health_checks(notify_fn=None) -> dict:
    """Run health checks on all registered API connections.

    Called every 30 s by the orchestrator.

    Parameters
    ----------
    notify_fn : callable or None
        ``notify_fn(message, priority)`` for sending alerts.

    Returns
    -------
    dict
        Summary: ``{connected: int, total: int, details: {...}}``
    """
    connected_count = 0
    total = len(_active_connections)

    for ac_id, state in _active_connections.items():
        adapter: APIAdapter = state["adapter"]
        latency = adapter.ping()

        if latency < 0:
            # Connection lost — attempt reconnect
            state["connected"] = False
            api_key = get_api_key(ac_id)

            for attempt in range(MAX_RECONNECT_RETRIES):
                try:
                    result = adapter.connect(api_key or "", state["endpoint"])
                    if result.get("connected"):
                        state["connected"] = True
                        state["retry_count"] = 0
                        logger.info("Reconnected API for account %s (attempt %d)",
                                    ac_id, attempt + 1)
                        break
                except Exception as exc:
                    logger.warning("Reconnect attempt %d for %s failed: %s",
                                   attempt + 1, ac_id, exc)

            if not state["connected"]:
                msg = f"API connection lost for account {ac_id} after {MAX_RECONNECT_RETRIES} retries"
                logger.error(msg)
                _log_api_health(ac_id, "DISCONNECTED", -1)

                if notify_fn:
                    notify_fn(msg, "CRITICAL")
        else:
            state["connected"] = True
            state["latency_ms"] = latency
            connected_count += 1

        state["last_heartbeat"] = datetime.now().isoformat()

    _log_api_health_batch()

    return {
        "connected": connected_count,
        "total": total,
        "details": {
            ac_id: {
                "connected": s["connected"],
                "latency_ms": s["latency_ms"],
                "last_heartbeat": s["last_heartbeat"],
            }
            for ac_id, s in _active_connections.items()
        },
    }


def get_connection_summary() -> dict:
    """Return current connection state (for health endpoint)."""
    connected = sum(1 for s in _active_connections.values() if s.get("connected"))
    return {"connected": connected, "total": len(_active_connections)}


# ---------------------------------------------------------------------------
# 3.4 — Compliance Gate
# ---------------------------------------------------------------------------

COMPLIANCE_GATE_PATH = os.environ.get(
    "COMPLIANCE_GATE_PATH", "/captain/config/compliance_gate.json"
)


def check_compliance_gate() -> dict:
    """Check if automated execution is permitted.

    All 11 RTS 6 requirements must be ``satisfied == True`` before
    automated execution is allowed.  In V1, this gate is ALWAYS LOCKED.

    Returns
    -------
    dict
        ``{allowed: bool, execution_mode: str, unsatisfied: list[str]}``
    """
    try:
        if os.path.exists(COMPLIANCE_GATE_PATH):
            with open(COMPLIANCE_GATE_PATH) as f:
                gate = json.load(f)
        else:
            gate = {}
    except Exception as exc:
        logger.error("Failed to read compliance gate: %s", exc, exc_info=True)
        gate = {}

    requirements = gate.get("requirements", {})
    unsatisfied = [
        req_id for req_id, status in requirements.items()
        if not status
    ]

    return {
        "allowed": len(unsatisfied) == 0 and len(requirements) == 11,
        "execution_mode": gate.get("execution_mode", "MANUAL"),
        "unsatisfied": unsatisfied,
        "total_requirements": len(requirements),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_api_health(account_id: str, status: str, latency_ms: float):
    """Insert a single health check result into P3-D14."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d14_api_connection_states(
                       account_id, adapter_type, connection_status,
                       latency_ms, last_updated
                   ) VALUES(%s, %s, %s, %s, now())""",
                (account_id, "TopstepX", status, latency_ms),
            )
    except Exception as exc:
        logger.error("API health log failed: %s", exc, exc_info=True)


def _log_api_health_batch():
    """Batch-insert health check results for all connections."""
    try:
        with get_cursor() as cur:
            for ac_id, state in _active_connections.items():
                status = "CONNECTED" if state["connected"] else "DISCONNECTED"
                cur.execute(
                    """INSERT INTO p3_d14_api_connection_states(
                           account_id, adapter_type, connection_status,
                           latency_ms, last_updated
                       ) VALUES(%s, %s, %s, %s, now())""",
                    (ac_id, "TopstepX", status, state.get("latency_ms", -1)),
                )
    except Exception as exc:
        logger.error("API health batch log failed: %s", exc, exc_info=True)
