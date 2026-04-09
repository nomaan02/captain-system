# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Phase 6: Telegram Bot (NotificationSpec.md §3).

Full Telegram bot with:
- 7 commands: /status, /signals, /positions, /reports, /tsm, /mute, /help
- Inline TAKEN/SKIPPED buttons on signal notifications
- Chat ID whitelisting (only registered users)
- Rate limiting (60 messages/hour per user)
- Security: no strategy details in messages
- Bot token from encrypted vault (never in code)

Spec: NotificationSpec.md lines 79-119
"""

import asyncio
import json
import logging
import os
import time
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable

from shared.questdb_client import get_cursor
from shared.constants import SYSTEM_TIMEZONE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter — max 60 messages per hour per user (spec §3.3)
# ---------------------------------------------------------------------------

_rate_window: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 60
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds


def _check_rate_limit(chat_id: str) -> bool:
    """Return True if the message is allowed (under rate limit)."""
    now = time.time()
    window = _rate_window[chat_id]
    # Prune expired entries
    _rate_window[chat_id] = [t for t in window if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_window[chat_id]) >= RATE_LIMIT_MAX:
        return False
    _rate_window[chat_id].append(now)
    return True


# ---------------------------------------------------------------------------
# Chat ID whitelisting
# ---------------------------------------------------------------------------


def _get_whitelisted_chat_ids() -> dict[str, str]:
    """Return {chat_id: user_id} mapping of registered users.

    Only users with telegram_chat_id in P3-D16 are allowed.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT DISTINCT telegram_chat_id, user_id
                   FROM p3_d16_user_capital_silos
                   WHERE telegram_chat_id IS NOT NULL
                     AND status = 'ACTIVE'"""
            )
            return {str(row[0]): row[1] for row in cur.fetchall() if row[0]}
    except Exception as exc:
        logger.error("Failed to load whitelisted chat IDs: %s", exc)
        return {}


def _get_user_for_chat_id(chat_id: str) -> str | None:
    """Lookup user_id for a Telegram chat_id."""
    whitelist = _get_whitelisted_chat_ids()
    return whitelist.get(str(chat_id))


# ---------------------------------------------------------------------------
# Data query helpers for bot commands
# ---------------------------------------------------------------------------


def _query_system_status() -> dict:
    """Query system status for /status command."""
    result = {
        "active_assets": 0,
        "warmup_assets": 0,
        "open_positions": 0,
        "system_status": "ACTIVE",
    }
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT captain_status, count() FROM p3_d00_asset_universe "
                "WHERE captain_status IN ('ACTIVE', 'WARM_UP') GROUP BY captain_status"
            )
            for row in cur.fetchall():
                if row[0] == "ACTIVE":
                    result["active_assets"] = row[1]
                elif row[0] == "WARM_UP":
                    result["warmup_assets"] = row[1]

            cur.execute(
                "SELECT count() FROM p3_d03_trade_outcome_log "
                "WHERE exit_time IS NULL"
            )
            row = cur.fetchone()
            result["open_positions"] = row[0] if row else 0
    except Exception as exc:
        logger.error("System status query failed: %s", exc)
        result["system_status"] = "DEGRADED"
    return result


def _query_latest_signals(user_id: str) -> list[dict]:
    """Query latest session signals for /signals command.

    SECURITY: Only returns asset, direction, confidence — NO strategy details.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, details, ts
                   FROM p3_session_event_log
                   WHERE user_id = %s AND event_type = 'SIGNAL_RECEIVED'
                   ORDER BY ts DESC LIMIT 10""",
                (user_id,),
            )
            signals = []
            for row in cur.fetchall():
                details = json.loads(row[1]) if row[1] else {}
                signals.append({
                    "asset": row[0],
                    "direction": details.get("direction", "—"),
                    "confidence": details.get("confidence_tier", "—"),
                    "time": str(row[2])[:19] if row[2] else "—",
                })
            return signals
    except Exception as exc:
        logger.error("Signals query failed: %s", exc)
        return []


def _query_open_positions(user_id: str) -> list[dict]:
    """Query open positions for /positions command.

    Returns: asset, direction, current P&L, TP/SL proximity.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, direction, entry_price, tp_level, sl_level,
                          contracts, point_value, account_id
                   FROM p3_d03_trade_outcome_log
                   WHERE user_id = %s AND exit_time IS NULL
                   ORDER BY entry_time DESC""",
                (user_id,),
            )
            positions = []
            for row in cur.fetchall():
                positions.append({
                    "asset": row[0],
                    "direction": row[1],
                    "entry": row[2],
                    "tp": row[3],
                    "sl": row[4],
                    "contracts": row[5],
                    "account": row[7],
                })
            return positions
    except Exception as exc:
        logger.error("Positions query failed: %s", exc)
        return []


def _query_recent_reports(user_id: str) -> list[dict]:
    """Query recent reports for /reports command."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT event_id, details, ts
                   FROM p3_session_event_log
                   WHERE user_id = %s AND event_type = 'REPORT_GENERATED'
                   ORDER BY ts DESC LIMIT 5""",
                (user_id,),
            )
            reports = []
            for row in cur.fetchall():
                details = json.loads(row[1]) if row[1] else {}
                reports.append({
                    "report_id": row[0],
                    "type": details.get("report_type", "—"),
                    "time": str(row[2])[:19] if row[2] else "—",
                })
            return reports
    except Exception as exc:
        logger.error("Reports query failed: %s", exc)
        return []


def _query_tsm_status(user_id: str) -> list[dict]:
    """Query TSM status for /tsm command."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT account_id, mdd_pct_used, mll_pct_used,
                          pass_probability, account_balance
                   FROM p3_d08_tsm_state
                   WHERE user_id = %s
                   ORDER BY timestamp DESC""",
                (user_id,),
            )
            accounts = []
            seen = set()
            for row in cur.fetchall():
                acct = row[0]
                if acct in seen:
                    continue
                seen.add(acct)
                accounts.append({
                    "account": acct,
                    "mdd_used_pct": round(float(row[1] or 0) * 100, 1),
                    "mll_used_pct": round(float(row[2] or 0) * 100, 1),
                    "pass_prob": round(float(row[3] or 0) * 100, 1),
                    "balance": float(row[4] or 0),
                })
            return accounts
    except Exception as exc:
        logger.error("TSM status query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Mute state management
# ---------------------------------------------------------------------------

# In-memory mute state: {chat_id: unmute_timestamp}
_mute_until: dict[str, float] = {}


def _set_mute(chat_id: str, hours: float):
    """Mute non-CRITICAL notifications for N hours."""
    _mute_until[str(chat_id)] = time.time() + (hours * 3600)


def _is_muted(chat_id: str) -> bool:
    """Check if a chat is currently muted."""
    unmute = _mute_until.get(str(chat_id))
    if unmute is None:
        return False
    if time.time() >= unmute:
        del _mute_until[str(chat_id)]
        return False
    return True


# ---------------------------------------------------------------------------
# Telegram Bot class — uses python-telegram-bot
# ---------------------------------------------------------------------------


class CaptainTelegramBot:
    """Telegram bot for Captain notification system.

    Runs in its own thread with an asyncio event loop.

    Parameters
    ----------
    bot_token : str
        Telegram Bot API token (from vault or env).
    taken_skipped_callback : callable or None
        Called when user taps TAKEN/SKIPPED inline button:
        ``callback(user_id, signal_id, action)``
    """

    def __init__(self, bot_token: str,
                 taken_skipped_callback: Callable | None = None):
        self._token = bot_token
        self._taken_skipped_callback = taken_skipped_callback
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._application = None
        self.running = False

    def start(self):
        """Start the bot in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._run_bot, daemon=True, name="telegram-bot",
        )
        self._thread.start()
        self.running = True
        logger.info("Telegram bot thread started")

    def stop(self):
        """Stop the bot gracefully."""
        self.running = False
        if self._application:
            try:
                if self._loop and not self._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self._application.stop(), self._loop
                    )
            except Exception:
                pass
        logger.info("Telegram bot stopped")

    def _run_bot(self):
        """Run the bot's async event loop in this thread."""
        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                CallbackQueryHandler,
                ContextTypes,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error(
                "python-telegram-bot not installed. "
                "Run: pip install python-telegram-bot"
            )
            return

        async def _check_auth(update: Update) -> str | None:
            """Verify chat ID is whitelisted. Returns user_id or None."""
            chat_id = str(update.effective_chat.id)
            user_id = _get_user_for_chat_id(chat_id)
            if not user_id:
                await update.message.reply_text(
                    "Unauthorized. Register your Telegram chat ID in Captain GUI."
                )
                _log_bot_interaction(chat_id, "UNAUTHORIZED", "blocked")
                return None
            return user_id

        # --- /status ---
        async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = await _check_auth(update)
            if not user_id:
                return
            status = _query_system_status()
            text = (
                f"Captain: {status['system_status']}.\n"
                f"Assets: {status['active_assets']} active, "
                f"{status['warmup_assets']} warming up.\n"
                f"Open positions: {status['open_positions']}."
            )
            await update.message.reply_text(text)
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_STATUS", "sent"
            )

        # --- /signals ---
        async def cmd_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = await _check_auth(update)
            if not user_id:
                return
            signals = _query_latest_signals(user_id)
            if not signals:
                await update.message.reply_text("No recent signals.")
                return
            lines = ["Latest signals:"]
            for s in signals[:5]:
                lines.append(
                    f"  {s['asset']} — {s['direction']} — {s['confidence']}"
                )
            await update.message.reply_text("\n".join(lines))
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_SIGNALS", "sent"
            )

        # --- /positions ---
        async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = await _check_auth(update)
            if not user_id:
                return
            positions = _query_open_positions(user_id)
            if not positions:
                await update.message.reply_text("No open positions.")
                return
            lines = ["Open positions:"]
            for p in positions:
                lines.append(
                    f"  {p['asset']} — {p['direction']} — "
                    f"{p['contracts']} contracts @ {p['entry']}"
                )
            await update.message.reply_text("\n".join(lines))
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_POSITIONS", "sent"
            )

        # --- /reports ---
        async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = await _check_auth(update)
            if not user_id:
                return
            reports = _query_recent_reports(user_id)
            if not reports:
                await update.message.reply_text("No recent reports. Check GUI.")
                return
            lines = ["Recent reports:"]
            for r in reports:
                lines.append(f"  {r['type']} — {r['time']}")
            lines.append("\nView full reports in the Captain GUI.")
            await update.message.reply_text("\n".join(lines))
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_REPORTS", "sent"
            )

        # --- /tsm ---
        async def cmd_tsm(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = await _check_auth(update)
            if not user_id:
                return
            accounts = _query_tsm_status(user_id)
            if not accounts:
                await update.message.reply_text("No TSM accounts configured.")
                return
            lines = ["TSM Status:"]
            for a in accounts:
                lines.append(
                    f"  {a['account']}:\n"
                    f"    MDD used: {a['mdd_used_pct']}%\n"
                    f"    MLL used: {a['mll_used_pct']}%\n"
                    f"    Pass probability: {a['pass_prob']}%"
                )
            await update.message.reply_text("\n".join(lines))
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_TSM", "sent"
            )

        # --- /mute ---
        async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = await _check_auth(update)
            if not user_id:
                return
            hours = 1.0
            if context.args:
                try:
                    hours = float(context.args[0])
                except (ValueError, IndexError):
                    pass
            hours = max(0.1, min(hours, 24))
            _set_mute(str(update.effective_chat.id), hours)
            await update.message.reply_text(
                f"Non-CRITICAL notifications muted for {hours:.1f} hours. "
                f"CRITICAL alerts will still be delivered."
            )
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_MUTE",
                f"muted {hours}h",
            )

        # --- /help ---
        async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
            text = (
                "Captain Bot Commands:\n"
                "/status — System status summary\n"
                "/signals — Latest signals (no strategy details)\n"
                "/positions — Open positions\n"
                "/reports — Recent reports\n"
                "/tsm — TSM account status (MDD%, MLL%, pass probability)\n"
                "/mute <hours> — Mute non-CRITICAL notifications\n"
                "/help — This help message"
            )
            await update.message.reply_text(text)
            _log_bot_interaction(
                str(update.effective_chat.id), "CMD_HELP", "sent"
            )

        # --- Inline button callback (TAKEN/SKIPPED) ---
        async def inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()

            chat_id = str(query.message.chat.id)
            user_id = _get_user_for_chat_id(chat_id)
            if not user_id:
                await query.edit_message_text("Unauthorized.")
                return

            # Callback data format: "TAKEN:signal_id" or "SKIPPED:signal_id"
            parts = query.data.split(":", 1)
            if len(parts) != 2:
                return

            action, signal_id = parts[0], parts[1]
            if action not in ("TAKEN", "SKIPPED"):
                return

            # Confirm — no trade details echoed (spec §3.3)
            await query.edit_message_text(f"Confirmed: {action}.")

            # Route to Command B1 via callback
            if self._taken_skipped_callback:
                try:
                    self._taken_skipped_callback(user_id, signal_id, action)
                except Exception as exc:
                    logger.error(
                        "TAKEN/SKIPPED callback failed: %s", exc, exc_info=True
                    )

            _log_bot_interaction(chat_id, f"INLINE_{action}", signal_id)

        # --- Unknown command handler ---
        async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "Unknown command. Use /help for available commands."
            )

        # Build application
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        app_builder = ApplicationBuilder().token(self._token)
        self._application = app_builder.build()

        # Register handlers
        self._application.add_handler(CommandHandler("status", cmd_status))
        self._application.add_handler(CommandHandler("signals", cmd_signals))
        self._application.add_handler(CommandHandler("positions", cmd_positions))
        self._application.add_handler(CommandHandler("reports", cmd_reports))
        self._application.add_handler(CommandHandler("tsm", cmd_tsm))
        self._application.add_handler(CommandHandler("mute", cmd_mute))
        self._application.add_handler(CommandHandler("help", cmd_help))
        self._application.add_handler(CallbackQueryHandler(inline_callback))
        self._application.add_handler(
            MessageHandler(filters.COMMAND, unknown_cmd)
        )

        logger.info("Telegram bot polling started")
        # stop_signals=() prevents run_polling from registering OS signal
        # handlers, which only work on the main thread.
        self._application.run_polling(drop_pending_updates=True, stop_signals=())

    # ------------------------------------------------------------------
    # Send message API (called by notification router)
    # ------------------------------------------------------------------

    def send_message(self, chat_id: str, text: str, priority: str = "LOW",
                     inline_buttons: list[tuple[str, str]] | None = None) -> bool:
        """Send a Telegram message to a specific chat.

        Parameters
        ----------
        chat_id : str
            Target Telegram chat ID.
        text : str
            Message text (plain text, no strategy details).
        priority : str
            Notification priority level.
        inline_buttons : list of (label, callback_data) or None
            Inline keyboard buttons.

        Returns
        -------
        bool
            True if sent successfully.
        """
        if not self._token:
            return False

        # Rate limit check
        if not _check_rate_limit(chat_id):
            logger.warning(
                "Rate limit exceeded for chat %s — dropping %s message",
                chat_id, priority,
            )
            return False

        # Mute check (CRITICAL bypasses mute)
        if priority != "CRITICAL" and _is_muted(chat_id):
            logger.debug("Chat %s is muted — skipping %s message", chat_id, priority)
            return False

        try:
            import urllib.request
            import urllib.parse

            # Build inline keyboard JSON if buttons provided
            reply_markup = ""
            if inline_buttons:
                keyboard = [[
                    {"text": label, "callback_data": data}
                    for label, data in inline_buttons
                ]]
                reply_markup_json = json.dumps({"inline_keyboard": keyboard})
                reply_markup = f"&reply_markup={urllib.parse.quote(reply_markup_json)}"

            url = (
                f"https://api.telegram.org/bot{self._token}/sendMessage"
                f"?chat_id={urllib.parse.quote(str(chat_id))}"
                f"&text={urllib.parse.quote(text)}"
                f"&parse_mode=HTML"
                f"{reply_markup}"
            )

            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(
                        "Telegram sent [%s] to chat %s", priority, chat_id
                    )
                    return True
                else:
                    logger.warning(
                        "Telegram API %d for chat %s", resp.status, chat_id
                    )
                    return False
        except Exception as exc:
            logger.error("Telegram send failed for chat %s: %s", chat_id, exc)
            return False

    def send_signal_notification(self, chat_id: str, asset: str,
                                 direction: str, confidence: str,
                                 signal_id: str) -> bool:
        """Send a signal notification with inline TAKEN/SKIPPED buttons.

        SECURITY: Only sends asset, direction, confidence — no strategy details.
        Spec: NotificationSpec.md §3.2
        """
        text = f"Signal: {asset} — {direction} — {confidence} confidence"
        buttons = [
            ("TAKEN", f"TAKEN:{signal_id}"),
            ("SKIPPED", f"SKIPPED:{signal_id}"),
        ]
        return self.send_message(
            chat_id, text, priority="HIGH", inline_buttons=buttons,
        )


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def _log_bot_interaction(chat_id: str, interaction_type: str, details: str):
    """Log all bot interactions to P3-D17 session_event_log (spec §3.3)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_session_event_log(
                       ts, user_id, event_type, event_id, asset, details
                   ) VALUES(%s, %s, %s, %s, %s, %s)""",
                (
                    datetime.now().isoformat(),
                    f"TG:{chat_id}",
                    f"TELEGRAM_{interaction_type}",
                    "",
                    "",
                    json.dumps({"details": details}),
                ),
            )
    except Exception as exc:
        logger.error("Bot interaction log failed: %s", exc)


# ---------------------------------------------------------------------------
# Factory: create bot from vault or env
# ---------------------------------------------------------------------------


def create_telegram_bot(
    taken_skipped_callback: Callable | None = None,
) -> CaptainTelegramBot | None:
    """Create a Telegram bot instance using token from vault or env.

    Token lookup order:
    1. Vault key "telegram_bot_token"
    2. Environment variable TELEGRAM_BOT_TOKEN

    Returns None if no token is available.
    """
    token = None

    # Try vault first (spec: bot token in encrypted vault)
    try:
        from shared.vault import load_vault
        vault = load_vault()
        token = vault.get("telegram_bot_token")
    except Exception:
        pass

    # Fall back to env var
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    if not token:
        logger.warning(
            "No Telegram bot token found — bot disabled. "
            "Set TELEGRAM_BOT_TOKEN env var or store in vault."
        )
        return None

    return CaptainTelegramBot(
        bot_token=token,
        taken_skipped_callback=taken_skipped_callback,
    )
