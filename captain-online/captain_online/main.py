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

# Token refresh wiring (H-27 fix).
#
# TopstepX JWTs expire ~24h after issue. The REST client (shared/topstep_client.py)
# auto-refreshes via /Auth/validate when token_age_seconds > 20h, but doing so
# INVALIDATES the previously-issued token server-side. The SignalR streams
# (MarketStream, UserStream) embed the token in the connect URL and never see
# the new one — so the next reconnect attempt comes back as HTTP 401 from
# wss://rtc.topstepx.com/hubs/{market,user}, and pysignalr raises
# NegotiationFailure. The streams then enter a permanent reconnect-fail loop
# and stay dead until the captain-online container is restarted.
#
# Fix: refresh proactively every 18h (well before the 20h REST threshold) so
# WE drive the refresh and immediately push the new token to both streams via
# their existing update_token() method (which stop/sleep(1)/start). This
# guarantees streams' tokens stay in sync with REST's token at all times.
_TOKEN_REFRESH_INTERVAL_S = 18 * 3600
_TOKEN_REFRESH_RETRY_DELAY_S = 300  # 5 min on failure


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

# ---------------------------------------------------------------------------
# R1: Bracket child-order capture (defence-in-depth for SL/TP ID resolution)
# ---------------------------------------------------------------------------

_BRACKET_CHILDREN_TTL_S = 30


def _try_capture_bracket_child(
    order_data: dict,
    account_id: int,
    redis_client,
    open_positions_key: str = _REDIS_KEY_OPEN_POSITIONS,
) -> bool:
    """Match a UserStream order to a pending bracket entry and write real IDs.

    Called from _on_order_update for every incoming order.  Only acts on
    LIMIT (type=1, TP child) and STOP (type=4, SL child) orders whose side
    is OPPOSITE to the recorded entry direction.

    Two paths:
    - Position already in Redis  → update sl_order_id / tp_order_id inline.
    - Race (TAKEN not processed) → stage in bracket:children:{acct}:{entry}
      with 30 s TTL; _handle_taken_skipped in the orchestrator applies them.

    Returns True if the order was matched as a bracket child, False otherwise.
    Never raises.
    """
    # Only LIMIT (TP) and STOP (SL) child orders carry real bracket IDs.
    order_type = order_data.get("type")
    if order_type not in (1, 4):
        return False

    if order_data.get("accountId") != account_id:
        return False

    order_id = str(order_data.get("id", ""))
    order_side = order_data.get("side")  # 0=Bid/Buy, 1=Ask/Sell

    pending_key = f"bracket:pending:{account_id}"
    try:
        pending_entries = redis_client.hgetall(pending_key)
    except Exception as exc:
        logger.warning("bracket:pending hgetall failed: %s", exc)
        return False

    if not pending_entries:
        return False

    for entry_oid_str, entry_json in pending_entries.items():
        try:
            entry = json.loads(entry_json)
        except (json.JSONDecodeError, ValueError):
            continue

        entry_side = entry.get("side")  # "BUY" or "SELL"
        # Entry BUY → child orders are SELL (side=1 Ask/Sell)
        # Entry SELL → child orders are BUY  (side=0 Bid/Buy)
        expected_child_side = 1 if entry_side == "BUY" else 0
        if order_side != expected_child_side:
            continue

        signal_id = entry.get("signal_id")
        # type=4 STOP → SL;  type=1 LIMIT → TP
        child_field = "sl_order_id" if order_type == 4 else "tp_order_id"

        try:
            pos_raw = redis_client.hget(open_positions_key, signal_id)
        except Exception:
            pos_raw = None

        if pos_raw is not None:
            # Position exists — update it directly.
            try:
                pos = json.loads(pos_raw)
                pos[child_field] = order_id
                redis_client.hset(open_positions_key, signal_id,
                                  json.dumps(pos, default=str))
                logger.info(
                    "Bracket child captured: signal=%s %s=%s",
                    signal_id, child_field, order_id,
                )
                # Clear pending entry when both children are resolved.
                try:
                    pos2_raw = redis_client.hget(open_positions_key, signal_id)
                    if pos2_raw:
                        pos2 = json.loads(pos2_raw)
                        if (pos2.get("sl_order_id") not in ("BRACKET", None)
                                and pos2.get("tp_order_id") not in ("BRACKET", None)):
                            redis_client.hdel(pending_key, entry_oid_str)
                            logger.info(
                                "Both bracket children resolved for signal=%s"
                                " — pending cleared",
                                signal_id,
                            )
                except Exception:
                    pass
            except Exception as exc:
                logger.warning(
                    "Failed to update position with bracket child: %s", exc,
                )
        else:
            # Race: position not yet in Redis — stage for _handle_taken_skipped.
            children_key = (
                f"bracket:children:{account_id}:{entry_oid_str}"
            )
            try:
                existing_raw = redis_client.get(children_key)
                children = json.loads(existing_raw) if existing_raw else {}
                children[child_field] = order_id
                redis_client.set(children_key, json.dumps(children),
                                 ex=_BRACKET_CHILDREN_TTL_S)
                logger.info(
                    "Bracket child staged (race): signal=%s %s=%s key=%s",
                    signal_id, child_field, order_id, children_key,
                )
            except Exception as exc:
                logger.warning("Failed to stage bracket child: %s", exc)

        return True  # Matched — no need to check further pending entries

    return False


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
            # R1: capture SL/TP child order IDs from UserStream callbacks.
            try:
                _try_capture_bracket_child(data, account_id, redis)
            except Exception as exc:
                logger.warning("bracket child capture failed (non-fatal): %s", exc)
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


def _token_refresh_loop(stop_event: threading.Event,
                        market_stream, user_stream) -> None:
    """Background thread: refresh JWT every 18h and push to both streams.

    Sleeps in 60-second chunks so that container shutdown is responsive
    (stop_event is set in shutdown_handler). On any failure logs and waits
    _TOKEN_REFRESH_RETRY_DELAY_S before retrying — never raises out of the
    thread (would silently kill the daemon).
    """
    from shared.topstep_client import get_topstep_client

    next_refresh_at = time.time() + _TOKEN_REFRESH_INTERVAL_S
    logger.info(
        "Token refresh loop started — next refresh in %dh",
        _TOKEN_REFRESH_INTERVAL_S // 3600,
    )

    while not stop_event.is_set():
        # Sleep in 60s chunks so SIGTERM is observed within ~1 minute.
        if stop_event.wait(timeout=60):
            break
        if time.time() < next_refresh_at:
            continue

        try:
            client = get_topstep_client()
            logger.info("Refreshing TopstepX JWT (proactive H-27 wiring)")
            new_token = client.validate_token()
            if not new_token:
                raise RuntimeError("validate_token returned empty token")

            if market_stream is not None:
                try:
                    market_stream.update_token(new_token)
                    logger.info("MarketStream token updated")
                except Exception:
                    logger.exception("MarketStream.update_token failed")

            if user_stream is not None:
                try:
                    user_stream.update_token(new_token)
                    logger.info("UserStream token updated")
                except Exception:
                    logger.exception("UserStream.update_token failed")

            next_refresh_at = time.time() + _TOKEN_REFRESH_INTERVAL_S
            logger.info(
                "Token refresh complete — next refresh in %dh",
                _TOKEN_REFRESH_INTERVAL_S // 3600,
            )
        except Exception:
            logger.exception(
                "Token refresh failed — retrying in %ds",
                _TOKEN_REFRESH_RETRY_DELAY_S,
            )
            next_refresh_at = time.time() + _TOKEN_REFRESH_RETRY_DELAY_S

    logger.info("Token refresh loop exiting")


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

    # Start JWT refresh background thread (H-27 fix). Refreshes the TopstepX
    # token every 18h and pushes it to both streams via update_token() so
    # MarketStream/UserStream don't end up holding a token that REST has
    # silently invalidated. Without this, streams die with HTTP 401 from the
    # SignalR hub after ~20h of uptime and never recover.
    token_refresh_stop = threading.Event()
    token_refresh_thread = threading.Thread(
        target=_token_refresh_loop,
        args=(token_refresh_stop, market_stream, user_stream),
        daemon=True,
        name="topstep-token-refresh",
    )
    token_refresh_thread.start()
    plog.info("Token refresh loop started (18h interval)", source="auth")

    # Start the 24/7 session orchestrator (with OR tracker reference)
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    orchestrator = OnlineOrchestrator(or_tracker=or_tracker)

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received")
        token_refresh_stop.set()
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
