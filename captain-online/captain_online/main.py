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
import signal
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.questdb_client import get_connection
from shared.redis_client import (
    get_redis_client, ensure_consumer_group,
    STREAM_COMMANDS, GROUP_ONLINE_COMMANDS,
)
from shared.journal import write_checkpoint, get_last_checkpoint
from shared.contract_resolver import preload_contracts
from captain_online.blocks.b8_or_tracker import ORTracker

ROLE = os.environ.get("CAPTAIN_ROLE", "ONLINE")

# Module-level OR tracker — shared between MarketStream (writer) and orchestrator (reader)
or_tracker = ORTracker()

logging.basicConfig(
    level=logging.INFO,
    format=f"[{ROLE}] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _start_market_streams():
    """Authenticate TopstepX and start a single multi-contract MarketStream.

    Online needs live quotes in quote_cache for B1 (prices, volume),
    B1-features (OHLCV, bid-ask), and B7 (position monitoring).
    """
    from shared.topstep_client import get_topstep_client, TopstepXClientError
    from shared.topstep_stream import MarketStream

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
        logger.error("TopstepX init failed: %s", exc)
        return None
    except Exception as exc:
        logger.error("TopstepX unexpected error: %s", exc, exc_info=True)
        return None


def main():
    logger.info("Starting Captain Online...")

    # Verify infrastructure
    try:
        conn = get_connection()
        conn.close()
        logger.info("QuestDB: connected")
    except Exception as e:
        logger.error("QuestDB: FAILED — %s", e)
        sys.exit(1)

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

    last = get_last_checkpoint(ROLE)
    if last:
        logger.info("Resuming from: %s — next: %s",
                     last["checkpoint"], last["next_action"])

    write_checkpoint(ROLE, "STARTUP", "initialization", "starting_streams")

    # Start market data streams (populates quote_cache for B1, B1-features, B7)
    market_stream = _start_market_streams()

    write_checkpoint(ROLE, "STREAMS_STARTED", "streams_ready", "starting_orchestrator")

    # Start the 24/7 session orchestrator (with OR tracker reference)
    from captain_online.blocks.orchestrator import OnlineOrchestrator
    orchestrator = OnlineOrchestrator(or_tracker=or_tracker)

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received")
        orchestrator.stop()
        if market_stream:
            market_stream.stop()
        write_checkpoint(ROLE, "SHUTDOWN", "running", "shutdown")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info("Starting session orchestrator...")
    orchestrator.start()  # Blocks — runs 24/7 session loop


if __name__ == "__main__":
    main()
