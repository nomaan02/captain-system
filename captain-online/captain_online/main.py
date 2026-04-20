# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Online — Signal Engine process entry point.

Initializes infrastructure, starts market streams for all active contracts,
then launches the 24/7 session orchestrator.
"""

import logging
import os
import sys
import json
import signal
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.questdb_client import get_connection, wait_for_questdb
from shared.redis_client import (
    get_redis_client, ensure_consumer_group,
    STREAM_COMMANDS, GROUP_ONLINE_COMMANDS,
    CH_USER_EVENTS,
)
from shared.journal import write_checkpoint, get_last_checkpoint
from shared.contract_resolver import preload_contracts
from shared.process_logger import ProcessLogger
from captain_online.blocks.b8_or_tracker import ORTracker

ROLE = os.environ.get("CAPTAIN_ROLE", "ONLINE")

# Module-level OR tracker — shared between MarketStream (writer) and orchestrator (reader)
or_tracker = ORTracker()

logging.basicConfig(
    level=logging.INFO,
    format=f"[{ROLE}] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


_TOPSTEP_MAX_ATTEMPTS = 3
_TOPSTEP_RETRY_DELAY_S = 5


def _start_market_streams():
    """Authenticate TopstepX and start a single multi-contract MarketStream.

    Online needs live quotes in quote_cache for B1 (prices, volume),
    B1-features (OHLCV, bid-ask), and B7 (position monitoring).

    Retries up to 3 times with 5s delay between attempts.
    Returns the MarketStream on success, None on final failure.
    """
    from shared.topstep_client import get_topstep_client, TopstepXClientError
    from shared.topstep_stream import MarketStream

    for attempt in range(1, _TOPSTEP_MAX_ATTEMPTS + 1):
        try:
            client = get_topstep_client()
            client.authenticate()
            logger.info("TopstepX API: authenticated")

            contracts = preload_contracts()
            logger.info("Resolved %d contracts: %s", len(contracts), list(contracts.keys()))

            if not contracts:
                logger.warning("No contracts resolved — market data unavailable")
                return None

            stream = MarketStream(
                token=client.current_token,
                contract_ids=list(contracts.values()),
                on_quote=or_tracker.on_quote,
            )
            stream.start()
            logger.info("MarketStream STARTED for %d contracts", len(contracts))
            return stream

        except TopstepXClientError as exc:
            if attempt < _TOPSTEP_MAX_ATTEMPTS:
                logger.warning(
                    "TopstepX init attempt %d/%d failed: %s — retrying in %ds",
                    attempt, _TOPSTEP_MAX_ATTEMPTS, exc, _TOPSTEP_RETRY_DELAY_S,
                )
                time.sleep(_TOPSTEP_RETRY_DELAY_S)
            else:
                logger.error(
                    "TopstepX init failed after %d attempts: %s",
                    _TOPSTEP_MAX_ATTEMPTS, exc,
                )
        except Exception as exc:
            if attempt < _TOPSTEP_MAX_ATTEMPTS:
                logger.warning(
                    "TopstepX init attempt %d/%d unexpected error: %s — retrying in %ds",
                    attempt, _TOPSTEP_MAX_ATTEMPTS, exc, _TOPSTEP_RETRY_DELAY_S,
                )
                time.sleep(_TOPSTEP_RETRY_DELAY_S)
            else:
                logger.error(
                    "TopstepX init failed after %d attempts: %s",
                    _TOPSTEP_MAX_ATTEMPTS, exc, exc_info=True,
                )
    return None


# Redis hash key — same constant as in online orchestrator (captain:open_positions)
_REDIS_KEY_OPEN_POSITIONS = "captain:open_positions"


def _start_user_stream():
    """Start UserStream for real-time order/position/trade updates.

    UserStream connects to a SEPARATE SignalR hub (wss://...hubs/user) from
    MarketStream (wss://...hubs/market).  Both run in captain-online to avoid
    GatewayLogout conflicts — TopstepX may only allow one WebSocket session
    per account.  Callbacks publish events to Redis for cross-process use.

    Returns the UserStream on success, None on failure (non-fatal).
    """
    from shared.topstep_client import get_topstep_client, TopstepXClientError
    from shared.topstep_stream import UserStream

    try:
        client = get_topstep_client()  # Singleton — already authenticated

        account_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")
        accounts = client.get_accounts(only_active=True)
        account = None
        for acc in accounts:
            if acc.get("name") == account_name or not account_name:
                account = acc
                break

        if not account:
            logger.warning("UserStream: no matching account — skipping")
            return None

        account_id = account["id"]
        redis = get_redis_client()

        # Reverse map: contract_id -> asset symbol (for position matching)
        contract_to_asset = {}
        try:
            contracts = preload_contracts()
            for asset_id, cid in contracts.items():
                contract_to_asset[cid] = asset_id
        except Exception:
            pass

        def _on_position_update(data):
            if not isinstance(data, dict):
                return
            pos_size = data.get("size", 0)
            logger.info("UserStream POSITION: contract=%s size=%s avgPrice=%s",
                        data.get("contractId"), pos_size,
                        data.get("averagePrice"))
            avg_price = data.get("averagePrice")
            cid = str(data.get("contractId", ""))
            asset = contract_to_asset.get(cid)

            # Enrich matching position in Redis with brokerage fill price.
            # Skip when size=0 (position closed) to avoid race with B7
            # resolution which deletes the hash entry concurrently.
            if avg_price and asset and pos_size:
                try:
                    stored = redis.hgetall(_REDIS_KEY_OPEN_POSITIONS)
                    for sig_id, raw in stored.items():
                        key = sig_id if isinstance(sig_id, str) else sig_id.decode()
                        val = raw if isinstance(raw, str) else raw.decode()
                        try:
                            pos = json.loads(val)
                            if pos.get("asset") == asset:
                                pos["actual_entry_price"] = avg_price
                                pos["entry_price"] = avg_price
                                redis.hset(
                                    _REDIS_KEY_OPEN_POSITIONS, key,
                                    json.dumps(pos, default=str),
                                )
                                logger.info("Position %s enriched: brokerage avgPrice=%s",
                                            key, avg_price)
                        except (json.JSONDecodeError, ValueError):
                            pass
                except Exception as exc:
                    logger.error("Failed to update position from UserStream: %s", exc)

            try:
                redis.publish(CH_USER_EVENTS, json.dumps(
                    {"type": "position_update", "data": data}, default=str))
            except Exception as exc:
                logger.error("Failed to publish position event: %s", exc)

        def _on_trade_update(data):
            if not isinstance(data, dict):
                return
            logger.info("UserStream TRADE: price=%s pnl=%s fees=%s",
                        data.get("price"), data.get("profitAndLoss"),
                        data.get("fees"))
            try:
                redis.publish(CH_USER_EVENTS, json.dumps(
                    {"type": "trade_update", "data": data}, default=str))
            except Exception as exc:
                logger.error("Failed to publish trade event: %s", exc)

        def _on_order_update(data):
            if not isinstance(data, dict):
                return
            status = data.get("status")
            logger.info("UserStream ORDER: id=%s status=%s type=%s",
                        data.get("id"), status, data.get("type"))
            if status in (6, "REJECTED"):
                logger.warning("UserStream ORDER REJECTED: id=%s data=%s",
                               data.get("id"), data)
            try:
                redis.publish(CH_USER_EVENTS, json.dumps(
                    {"type": "order_update", "data": data}, default=str))
            except Exception as exc:
                logger.error("Failed to publish order event: %s", exc)

        def _on_account_update(data):
            if not isinstance(data, dict):
                return
            logger.info("UserStream ACCOUNT: balance=%s", data.get("balance"))
            try:
                redis.publish(CH_USER_EVENTS, json.dumps(
                    {"type": "account_update", "data": data}, default=str))
            except Exception as exc:
                logger.error("Failed to publish account event: %s", exc)

        stream = UserStream(
            token=client.current_token,
            account_id=account_id,
            on_position_update=_on_position_update,
            on_trade_update=_on_trade_update,
            on_order_update=_on_order_update,
            on_account_update=_on_account_update,
        )
        stream.start()
        logger.info("UserStream STARTED for account %s (id=%s)",
                     account.get("name"), account_id)
        return stream

    except TopstepXClientError as exc:
        logger.error("UserStream init failed (TopstepX): %s", exc)
        return None
    except Exception as exc:
        logger.error("UserStream init failed: %s", exc, exc_info=True)
        return None


def main():
    logger.info("Starting Captain Online...")
    plog = ProcessLogger("ONLINE", get_redis_client())

    # Wait for QuestDB to be reachable before any DB operation
    if not wait_for_questdb(30):
        logger.critical("QuestDB unreachable after 30s — aborting")
        sys.exit(2)

    try:
        client = get_redis_client()
        client.ping()
        logger.info("Redis: connected")
    except Exception as e:
        logger.error("Redis: FAILED — %s", e)
        sys.exit(1)

    # Initialize Redis Stream consumer groups
    ensure_consumer_group(STREAM_COMMANDS, GROUP_ONLINE_COMMANDS)
    logger.info("Redis Stream consumer groups initialized")
    plog.info("QuestDB + Redis verified", source="main")

    last = get_last_checkpoint(ROLE)
    if last:
        next_action = last.get("next_action", "")
        if next_action not in ("shutdown", "initialization", ""):
            logger.warning("CRASH RECOVERY: last checkpoint=%s next=%s — "
                           "previous session did not shut down cleanly",
                           last["checkpoint"], next_action)
            write_checkpoint(ROLE, "CRASH_RECOVERY", next_action, "restarting")
        else:
            logger.info("Clean restart — last checkpoint: %s", last["checkpoint"])

    write_checkpoint(ROLE, "STARTUP", "initialization", "starting_streams")

    # Start market data streams (populates quote_cache for B1, B1-features, B7)
    market_stream = _start_market_streams()
    if market_stream:
        plog.info("MarketStream started \u2014 live quotes active", source="stream")
    else:
        logger.critical("TopstepX authentication failed — cannot trade without market data")
        plog.error("MarketStream FAILED after retries — exiting", source="stream")
        sys.exit(1)

    # Start user event stream (position/trade/order updates from brokerage)
    # Non-fatal: system can operate without real-time user events
    user_stream = _start_user_stream()
    if user_stream:
        plog.info("UserStream started — real-time fills active", source="stream")
    else:
        logger.warning("UserStream not started — brokerage events unavailable")

    write_checkpoint(ROLE, "STREAMS_STARTED", "streams_ready", "starting_orchestrator")

    # Start the 24/7 session orchestrator (with OR tracker reference)
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    orchestrator = OnlineOrchestrator(or_tracker=or_tracker)

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received")
        orchestrator.stop()
        if user_stream:
            user_stream.stop()
        if market_stream:
            market_stream.stop()
        write_checkpoint(ROLE, "SHUTDOWN", "running", "shutdown")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    plog.info("Online orchestrator started \u2014 24/7 session loop", source="orchestrator")
    logger.info("Starting session orchestrator...")
    orchestrator.start()  # Blocks — runs 24/7 session loop


if __name__ == "__main__":
    main()
