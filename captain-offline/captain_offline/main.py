# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Offline — Strategic Brain process entry point.

Initializes infrastructure (QuestDB, Redis), then launches the
OfflineOrchestrator which runs the event-driven scheduler and
Redis subscriber for trade outcomes and commands.
"""

import logging
import os
import sys
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.questdb_client import get_connection
from shared.redis_client import (
    get_redis_client, ensure_consumer_group,
    STREAM_TRADE_OUTCOMES, STREAM_COMMANDS,
    GROUP_OFFLINE_OUTCOMES, GROUP_OFFLINE_COMMANDS,
)
from shared.journal import write_checkpoint, get_last_checkpoint

ROLE = os.environ.get("CAPTAIN_ROLE", "OFFLINE")

logging.basicConfig(
    level=logging.INFO,
    format=f"[{ROLE}] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


NUM_AIMS = 16
TIER1_AIMS = {4, 6, 8, 11, 12, 15}


def _seed_aim_states():
    """Ensure all 16 AIMs exist in P3-D01 for every asset in D00.

    Idempotent: only inserts INSTALLED rows for (aim_id, asset_id) pairs
    that have no rows yet. Tier 1 AIMs get BOOTSTRAPPED status.
    """
    from shared.questdb_client import get_cursor
    import time

    try:
        # Get all assets
        with get_cursor() as cur:
            cur.execute("SELECT DISTINCT asset_id FROM p3_d00_asset_universe")
            assets = [r[0] for r in cur.fetchall()]

        if not assets:
            logger.info("No assets in D00 — skipping AIM seed")
            return

        # Get existing (aim_id, asset_id) pairs
        with get_cursor() as cur:
            cur.execute("SELECT DISTINCT aim_id, asset_id FROM p3_d01_aim_model_states")
            existing = {(r[0], r[1]) for r in cur.fetchall()}

        seeded = 0
        for asset_id in assets:
            for aim_id in range(1, NUM_AIMS + 1):
                if (aim_id, asset_id) in existing:
                    continue
                status = "BOOTSTRAPPED" if aim_id in TIER1_AIMS else "INSTALLED"
                warmup = 1.0 if aim_id in TIER1_AIMS else 0.0
                try:
                    with get_cursor() as cur:
                        cur.execute(
                            """INSERT INTO p3_d01_aim_model_states
                               (aim_id, asset_id, status, warmup_progress, last_updated)
                               VALUES (%s, %s, %s, %s, now())""",
                            (aim_id, asset_id, status, warmup),
                        )
                    seeded += 1
                except Exception:
                    time.sleep(0.5)  # QuestDB table busy — brief retry
                    with get_cursor() as cur:
                        cur.execute(
                            """INSERT INTO p3_d01_aim_model_states
                               (aim_id, asset_id, status, warmup_progress, last_updated)
                               VALUES (%s, %s, %s, %s, now())""",
                            (aim_id, asset_id, status, warmup),
                        )
                    seeded += 1

        logger.info("AIM seed complete: %d new rows (%d assets × %d AIMs, %d pre-existing)",
                     seeded, len(assets), NUM_AIMS, len(existing))
    except Exception as exc:
        logger.error("AIM seeding failed: %s", exc, exc_info=True)


def main():
    logger.info("Starting Captain Offline...")

    # Verify QuestDB connection
    try:
        conn = get_connection()
        conn.close()
        logger.info("QuestDB: connected")
    except Exception as e:
        logger.error("QuestDB: FAILED — %s", e)
        sys.exit(1)

    # Verify Redis connection
    try:
        client = get_redis_client()
        client.ping()
        logger.info("Redis: connected")
    except Exception as e:
        logger.error("Redis: FAILED — %s", e)
        sys.exit(1)

    # Initialize Redis Stream consumer groups
    ensure_consumer_group(STREAM_TRADE_OUTCOMES, GROUP_OFFLINE_OUTCOMES)
    ensure_consumer_group(STREAM_COMMANDS, GROUP_OFFLINE_COMMANDS)
    logger.info("Redis Stream consumer groups initialized")

    # Check for recovery from crash
    last = get_last_checkpoint(ROLE)
    if last:
        logger.info("Resuming from: %s — next: %s",
                     last["checkpoint"], last["next_action"])

    write_checkpoint(ROLE, "STARTUP", "initialization", "seeding_aims")

    # Seed all 16 AIMs for every asset in D00 (idempotent — skips if rows exist)
    _seed_aim_states()

    write_checkpoint(ROLE, "AIMS_SEEDED", "aims_ready", "starting_orchestrator")

    # Start the event-driven orchestrator
    from captain_offline.blocks.orchestrator import OfflineOrchestrator
    orchestrator = OfflineOrchestrator()

    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received")
        orchestrator.stop()
        write_checkpoint(ROLE, "SHUTDOWN", "running", "shutdown")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    write_checkpoint(ROLE, "ORCHESTRATOR_STARTED", "running", "event_loop")
    logger.info("Starting orchestrator (event loop + Redis subscriber)...")
    orchestrator.start()  # Blocks — runs scheduler + Redis listener


if __name__ == "__main__":
    main()
