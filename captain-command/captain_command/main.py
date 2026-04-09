# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Linking Layer process entry point.

Initializes infrastructure, loads TSM files, starts the Telegram bot
(Phase 6), starts the orchestrator (Redis listener + scheduler) in a
background thread, and runs the FastAPI server (HTTP/WebSocket) in the
main thread.
"""

import logging
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.questdb_client import get_connection
from shared.redis_client import (
    get_redis_client, ensure_consumer_group,
    STREAM_SIGNALS, GROUP_COMMAND_SIGNALS,
)
from shared.journal import write_checkpoint, get_last_checkpoint
from shared.contract_resolver import preload_contracts

ROLE = os.environ.get("CAPTAIN_ROLE", "COMMAND")

logging.basicConfig(
    level=logging.INFO,
    format=f"[{ROLE}] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress httpx request logging — it leaks the Telegram bot token in URLs
logging.getLogger("httpx").setLevel(logging.WARNING)


def verify_connections():
    """Verify QuestDB and Redis are reachable."""
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
    ensure_consumer_group(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS)
    logger.info("Redis Stream consumer groups initialized")


def load_tsm_files():
    """Load all TSM configuration files at startup."""
    from captain_command.blocks.b4_tsm_manager import load_all_tsm_files
    results = load_all_tsm_files()
    valid = sum(1 for r in results if r["validation"]["valid"])
    logger.info("TSM files loaded: %d/%d valid", valid, len(results))
    return results


def _link_tsm_to_account(tsm_results: list[dict], account: dict):
    """Auto-link a discovered TopstepX account to the best matching TSM file.

    Matches on provider=TopstepX, starting_balance, and account stage
    (PRAC → EVAL, XFA → XFA, else → LIVE). Skips if already linked.
    """
    from captain_command.blocks.b4_tsm_manager import _store_tsm_in_d08
    from shared.questdb_client import get_cursor

    account_name = account.get("name", "")
    account_id = str(account["id"])
    balance = account.get("balance", 0)

    # Skip if TSM already exists for this account
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT count() FROM p3_d08_tsm_state WHERE account_id = %s",
                (account_id,),
            )
            row = cur.fetchone()
            if row and row[0] > 0:
                logger.info("TSM already linked for account %s — skipping", account_name)
                return
    except Exception:
        pass  # continue to link attempt

    # Determine stage from account name prefix
    if account_name.startswith("PRAC"):
        target_stage = "STAGE_1"
    elif "XFA" in account_name:
        target_stage = "XFA"
    else:
        target_stage = "LIVE"

    # Find best matching TSM
    best = None
    for r in tsm_results:
        if not r["validation"]["valid"] or r["tsm"] is None:
            continue
        tsm = r["tsm"]
        cls = tsm.get("classification", {})
        if cls.get("provider") != "TopstepX":
            continue
        if cls.get("stage") == target_stage:
            best = tsm
            break
        # Fallback: match on balance
        if best is None and tsm.get("starting_balance") == balance:
            best = tsm

    if best is None:
        logger.warning("No matching TSM found for account %s (stage=%s)", account_name, target_stage)
        return

    # Inject user_id and current balance before storing
    best["user_id"] = os.environ.get("BOOTSTRAP_USER_ID", "primary_user")
    best["current_balance"] = balance

    _store_tsm_in_d08(account_id, best)
    logger.info("TSM auto-linked: account=%s → %s", account_name, best.get("name"))


def start_telegram_bot():
    """Initialize and start the Telegram bot (Phase 6).

    The bot token is loaded from the encrypted vault or TELEGRAM_BOT_TOKEN
    env var. Returns None if no token is available (bot disabled).
    """
    from captain_command.blocks.telegram_bot import create_telegram_bot
    from captain_command.blocks.b1_core_routing import route_command
    from captain_command.api import gui_push

    def _taken_skipped_callback(user_id: str, signal_id: str, action: str):
        """Route inline TAKEN/SKIPPED from Telegram to Command B1."""
        route_command({
            "type": "TAKEN_SKIPPED",
            "action": action,
            "signal_id": signal_id,
            "user_id": user_id,
        }, gui_push_fn=gui_push)

    bot = create_telegram_bot(taken_skipped_callback=_taken_skipped_callback)
    if bot:
        bot.start()
        logger.info("Telegram bot: ACTIVE")
    else:
        logger.info("Telegram bot: DISABLED (no token configured)")
    return bot


def _ensure_telegram_chat_id():
    """Write TELEGRAM_CHAT_ID from env into QuestDB D16 + notification preferences.

    QuestDB is append-only so we insert a new D16 row with the chat_id set
    (queries use LATEST ON last_updated PARTITION BY user_id to get the latest).
    Also saves it as a notification preference so b7 route_notification finds it.
    """
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        logger.info("TELEGRAM_CHAT_ID not set — Telegram notifications will not be delivered")
        return

    from shared.questdb_client import get_cursor
    from captain_command.blocks.b7_notifications import save_user_preferences

    user_id = os.environ.get("BOOTSTRAP_USER_ID", "primary_user")

    # Check if D16 already has this chat_id for this user
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT telegram_chat_id FROM p3_d16_user_capital_silos
                   LATEST ON last_updated PARTITION BY user_id
                   WHERE user_id = %s""",
                (user_id,),
            )
            row = cur.fetchone()
            if row and row[0] == chat_id:
                logger.info("Telegram chat_id already set in D16 for %s", user_id)
                return

            # Read current row to copy all fields
            cur.execute(
                """SELECT user_id, status, role, starting_capital, total_capital,
                          accounts, max_simultaneous_positions, max_portfolio_risk_pct,
                          correlation_threshold, user_kelly_ceiling, capital_history,
                          created
                   FROM p3_d16_user_capital_silos
                   LATEST ON last_updated PARTITION BY user_id
                   WHERE user_id = %s""",
                (user_id,),
            )
            src = cur.fetchone()
            if not src:
                logger.warning("No D16 row for user %s — cannot set telegram_chat_id", user_id)
                return

            # Insert updated row with chat_id
            cur.execute(
                """INSERT INTO p3_d16_user_capital_silos (
                       user_id, status, role, starting_capital, total_capital,
                       accounts, max_simultaneous_positions, max_portfolio_risk_pct,
                       correlation_threshold, user_kelly_ceiling, capital_history,
                       telegram_chat_id, created, last_updated
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())""",
                (src[0], src[1], src[2], src[3], src[4],
                 src[5], src[6], src[7], src[8], src[9], src[10],
                 chat_id, src[11]),
            )
            logger.info("Telegram chat_id written to D16 for user %s", user_id)
    except Exception as exc:
        logger.error("Failed to write telegram_chat_id to D16: %s", exc)

    # Also save as notification preference (b7 checks prefs first)
    try:
        save_user_preferences(user_id, {"telegram_chat_id": chat_id})
        logger.info("Telegram chat_id saved to notification preferences for %s", user_id)
    except Exception as exc:
        logger.error("Failed to save telegram preference: %s", exc)


def _init_topstep():
    """Authenticate TopstepX API for REST operations (orders, accounts).

    ALL WebSocket streams (Market + User) are owned by captain-online.
    TopstepX allows only ONE concurrent WebSocket per user account.
    """
    from shared.topstep_client import get_topstep_client, TopstepXClientError
    from captain_command.blocks.b2_gui_data_server import set_account_data
    from captain_command.blocks.b3_api_adapter import (
        TopstepXAdapter, register_connection,
    )

    market_streams = []
    try:
        client = get_topstep_client()
        client.authenticate()
        logger.info("TopstepX API: authenticated")

        # Resolve account
        account_name = os.environ.get("TOPSTEP_ACCOUNT_NAME", "")
        accounts = client.get_accounts(only_active=True)
        account = None
        for acc in accounts:
            if acc.get("name") == account_name or not account_name:
                account = acc
                break

        if account:
            account_id = account["id"]
            set_account_data(account)
            logger.info("TopstepX account: %s (id=%s, balance=%.2f)",
                        account.get("name"), account_id, account.get("balance", 0))

            # Register B3 adapter for health monitoring
            adapter = TopstepXAdapter()
            adapter.connect()
            register_connection(str(account_id), adapter, "topstepx")

            # Preload all contract IDs (for resolver, NOT for streaming)
            contracts = preload_contracts()
            logger.info("Resolved %d contracts: %s", len(contracts), list(contracts.keys()))

            # NOTE: ALL WebSocket streams are owned by captain-online only.
            # TopstepX allows ONE concurrent WebSocket per user account
            # across ALL hubs (market + user). Any connection from Command
            # sends GatewayLogout to Online, killing signal generation.
            # Command uses REST API for orders and Redis for data.
            logger.info("TopstepX WebSocket streams: SKIPPED (owned by captain-online)")
        else:
            logger.warning("TopstepX: no matching account found")

    except TopstepXClientError as exc:
        logger.error("TopstepX initialization failed: %s", exc)
        return {"account": None}
    except Exception as exc:
        logger.error("TopstepX unexpected error: %s", exc, exc_info=True)
        return {"account": None}

    return {"account": account}


def main():
    logger.info("Starting Captain Command...")

    verify_connections()

    last = get_last_checkpoint(ROLE)
    if last:
        logger.info("Resuming from: %s — next: %s",
                     last["checkpoint"], last["next_action"])

    write_checkpoint(ROLE, "STARTUP", "initialization", "loading_tsm")

    # Load TSM files
    tsm_results = load_tsm_files()

    write_checkpoint(ROLE, "TSM_LOADED", "tsm_ready", "starting_telegram")

    # Start Telegram bot (Phase 6)
    telegram_bot = start_telegram_bot()

    # Ensure TELEGRAM_CHAT_ID from env is written to QuestDB D16 + prefs
    _ensure_telegram_chat_id()

    write_checkpoint(ROLE, "TELEGRAM_STARTED", "telegram_ready", "connecting_topstep")

    # Connect to TopstepX API + start user stream
    topstep_streams = _init_topstep()

    # Auto-link discovered account to matching TSM → writes to P3-D08
    topstep_account = topstep_streams.get("account") if topstep_streams else None
    logger.info("TSM link check: account=%s, tsm_count=%d",
                topstep_account.get("name") if topstep_account else None,
                len(tsm_results) if tsm_results else 0)
    if topstep_account and tsm_results:
        try:
            _link_tsm_to_account(tsm_results, topstep_account)
        except Exception as exc:
            logger.error("TSM auto-link failed: %s", exc, exc_info=True)

    write_checkpoint(ROLE, "TOPSTEP_CONNECTED", "topstep_ready", "starting_orchestrator")

    # Start orchestrator in background thread
    from captain_command.blocks.orchestrator import CommandOrchestrator
    orchestrator = CommandOrchestrator()
    orchestrator.telegram_bot = telegram_bot  # Inject bot for notification routing

    # Register bot and orchestrator with API module for lifespan shutdown + notification endpoints
    from captain_command.api import set_telegram_bot, set_orchestrator
    set_telegram_bot(telegram_bot)
    set_orchestrator(orchestrator)

    orch_thread = threading.Thread(
        target=orchestrator.start, daemon=True, name="cmd-orchestrator"
    )
    orch_thread.start()

    write_checkpoint(ROLE, "ORCHESTRATOR_STARTED", "running", "starting_api_server")

    # Shutdown is handled by FastAPI lifespan in api.py (orchestrator.stop + telegram_bot.stop).
    # No signal.signal() calls here — uvicorn manages SIGTERM/SIGINT via its own event loop.

    # Start FastAPI via uvicorn (main thread)
    import uvicorn
    from captain_command.api import app

    logger.info("Starting API server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
