"""Trade outcome → GUI WebSocket payload (stream consumer → ``gui_push``)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_trade_closed_ws_payload(data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return ``(user_id, message_body)`` for a ``trade_closed`` push, or None if invalid."""
    uid = data.get("user_id")
    if not uid:
        logger.warning("STREAM trade outcome missing user_id — skipping GUI push")
        return None

    body = {
        "type": "trade_closed",
        "trade_id": data.get("trade_id"),
        "signal_id": data.get("signal_id"),
        "user_id": uid,
        "asset": data.get("asset"),
        "asset_id": data.get("asset"),
        "direction": data.get("direction"),
        "pnl": data.get("pnl"),
        "outcome": data.get("outcome"),
        "entry_price": data.get("entry_price"),
        "exit_price": data.get("exit_price"),
        "contracts": data.get("contracts"),
        "commission": data.get("commission"),
        "tp_level": data.get("tp_level"),
        "sl_level": data.get("sl_level"),
        "entry_time": data.get("entry_time"),
        "exit_time": data.get("exit_time"),
        "timestamp": data.get("timestamp"),
    }
    return uid, body
