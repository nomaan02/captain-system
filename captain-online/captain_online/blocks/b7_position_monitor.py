# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B7: Intraday Position Monitoring — P3-PG-27 (Task 3.8 / ON lines 1181-1345).

Monitors all open positions continuously (10s poll):
  - P&L tracking (per-contract, per-position)
  - TP/SL proximity alerts
  - VIX spike alerts
  - Regime shift detection
  - Time-based exit (no overnight for some accounts)
  - Position resolution → P3-D03 trade outcome → Redis captain:trade_outcomes

V3 additions:
  - resolve_commission() reads fee_schedule.fees_by_instrument first (Nomaan_Edits_Fees.md Change 2)
  - get_expected_fee() utility
  - P3-D23 intraday state update after each trade outcome

CRITICAL FEEDBACK LOOP:
  resolve_position() → P3-D03 → Redis captain:trade_outcomes → Offline learning

Reads: P3-D00, P3-D08 (TSM), live market data
Writes: P3-D03 (trade outcomes), P3-D16 (capital silo), P3-D23 (intraday CB state)
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS, publish_to_stream, STREAM_TRADE_OUTCOMES
from shared.constants import TRADE_OUTCOME_VALUES
from shared.contract_resolver import resolve_contract_id
from shared.topstep_stream import quote_cache
from shared.vix_provider import get_latest_vix_close, get_trailing_vix_closes
from shared.json_helpers import parse_json

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10
VIX_SPIKE_Z_THRESHOLD = 2.0  # Spec §2 B7: z-score against 60-day trailing

# Module-level cache for latest regime per asset, set by orchestrator via
# update_regime_cache() before each monitoring pass.
_regime_cache: dict[str, str] = {}


def update_regime_cache(regime_probs: dict) -> None:
    """Called by orchestrator to set latest regime per asset for B7 checks."""
    global _regime_cache
    for asset_id, probs in (regime_probs or {}).items():
        if probs:
            _regime_cache[asset_id] = max(probs, key=probs.get)
        else:
            _regime_cache[asset_id] = "UNKNOWN"


def monitor_positions(open_positions: list[dict], tsm_configs: dict) -> list[dict]:
    """P3-PG-27: Single monitoring pass for all open positions.

    Called every 10 seconds by the orchestrator while positions are open.
    Returns list of resolved positions (removed from open_positions).
    """
    resolved = []

    for pos in open_positions:
        current_price = _get_live_price(pos["asset"])
        if current_price is None:
            continue

        point_value = pos.get("point_value", 50.0)

        # P&L tracking
        direction = pos.get("direction", 1)
        entry_price = pos.get("entry_price", 0)
        contracts = pos.get("contracts", 0)
        pos["current_pnl"] = (current_price - entry_price) * direction * contracts * point_value
        risk_amount = pos.get("risk_amount", 1)
        pos["pnl_pct"] = pos["current_pnl"] / risk_amount if risk_amount > 0 else 0

        # TP/SL proximity
        tp = pos.get("tp_level")
        sl = pos.get("sl_level")

        if tp and entry_price:
            tp_range = abs(tp - entry_price)
            tp_distance = abs(tp - current_price) / tp_range if tp_range > 0 else 1.0

            if tp_distance < 0.10:
                _notify(pos["user_id"], "HIGH",
                        f"TP approaching for {pos['asset']}: {current_price} vs TP {tp}")

        if sl and entry_price:
            sl_range = abs(sl - entry_price)
            sl_distance = abs(sl - current_price) / sl_range if sl_range > 0 else 1.0

            if sl_distance < 0.10:
                _notify(pos["user_id"], "CRITICAL",
                        f"SL approaching for {pos['asset']}: {current_price} vs SL {sl}")

        # VIX spike alert
        _check_vix_spike(pos)

        # Regime shift alert
        if _regime_shift_detected(pos["asset"], pos.get("regime_state")):
            _notify(pos["user_id"], "CRITICAL",
                    f"Regime shift detected for {pos['asset']} — review position")

        # Position resolution — TP/SL hit
        if tp:
            if (direction == 1 and current_price >= tp) or (direction == -1 and current_price <= tp):
                resolve_position(pos, "TP_HIT", current_price, tsm_configs)
                resolved.append(pos)
                continue

        if sl:
            if (direction == 1 and current_price <= sl) or (direction == -1 and current_price >= sl):
                resolve_position(pos, "SL_HIT", current_price, tsm_configs)
                resolved.append(pos)
                continue

        # Time exit — forced close for no-overnight accounts
        tsm = tsm_configs.get(pos.get("account"))
        if tsm and not tsm.get("overnight_allowed", True):
            trading_hours = tsm.get("trading_hours", "")
            close_time = _parse_close_time(trading_hours)
            if close_time:
                buffer_time = close_time - timedelta(minutes=5)
                if datetime.now(ZoneInfo("America/New_York")) >= buffer_time:
                    _notify(pos["user_id"], "CRITICAL",
                            f"TIME EXIT: {pos['asset']} closing — account does not allow overnight")
                    resolve_position(pos, "TIME_EXIT", current_price, tsm_configs)
                    resolved.append(pos)
                    continue

    return resolved


def resolve_position(pos: dict, outcome: str, exit_price: float, tsm_configs: dict):
    """Resolve a position: log trade outcome, update capital, publish to Offline.

    CRITICAL: This is the feedback loop bridge to Offline learning.
    """
    point_value = pos.get("point_value", 50.0)
    direction = pos.get("direction", 1)
    contracts = pos.get("contracts", 0)
    entry_price = pos.get("entry_price", 0)
    account_id = pos.get("account")

    gross_pnl = (exit_price - entry_price) * direction * contracts * point_value

    # Commission (V3: resolve_commission with fee_schedule priority)
    commission = resolve_commission(account_id, contracts, pos["asset"], tsm_configs)
    net_pnl = gross_pnl - commission

    # Actual entry price
    actual_entry = _resolve_actual_entry_price(pos)
    slippage = None
    if actual_entry is not None:
        slippage = (actual_entry - pos.get("signal_entry_price", entry_price)) * direction * contracts * point_value

    # Trade ID
    trade_id = f"TRD-{uuid.uuid4().hex[:12].upper()}"

    # Write to P3-D03
    _write_trade_outcome(
        trade_id=trade_id,
        user_id=pos["user_id"],
        account_id=account_id,
        asset=pos["asset"],
        direction=direction,
        entry_price=actual_entry or entry_price,
        signal_entry_price=pos.get("signal_entry_price", entry_price),
        exit_price=exit_price,
        contracts=contracts,
        gross_pnl=gross_pnl,
        commission=commission,
        net_pnl=net_pnl,
        slippage=slippage,
        outcome=outcome,
        entry_time=pos.get("entry_time"),
        regime_at_entry=pos.get("regime_state"),
        aim_modifier=pos.get("combined_modifier"),
        aim_breakdown=pos.get("aim_breakdown"),
        session=pos.get("session"),
        tsm_used=pos.get("tsm_id"),
    )

    # Notify user
    _notify(pos["user_id"], "CRITICAL",
            f"Position closed: {pos['asset']} {outcome} Net PnL=${net_pnl:.2f} (commission=${commission:.2f})")

    # Atomic capital + CB update (G-033: single cursor, both writes back-to-back)
    _update_capital_and_cb(
        user_id=pos["user_id"],
        account_id=account_id,
        net_pnl=net_pnl,
        outcome=outcome,
        model_m=pos.get("model", ""),
    )

    # CRITICAL: Publish trade outcome to Offline via Redis
    _publish_trade_outcome(trade_id, pos, outcome, net_pnl, exit_price, commission, slippage)

    logger.info("ON-B7: Position resolved — %s %s %s net_pnl=%.2f trade_id=%s",
                pos["asset"], outcome, pos["user_id"], net_pnl, trade_id)


# ---------------------------------------------------------------------------
# V3: Commission resolution with fee_schedule priority
# ---------------------------------------------------------------------------

def resolve_commission(account_id: str, contracts: int, asset_id: str, tsm_configs: dict) -> float:
    """V3: resolve_commission() — read fee_schedule first, fall back to commission_per_contract.

    Per Nomaan_Edits_Fees.md Change 2.
    Chain: API → fee_schedule.fees_by_instrument → commission_per_contract → notify user.
    """
    # Source 1: API fill data (stub for V1)
    api_commission = _get_api_commission(account_id)
    if api_commission is not None:
        return api_commission

    tsm = tsm_configs.get(account_id, {})

    # Source 2: fee_schedule.fees_by_instrument (V3 priority)
    fee_schedule = parse_json(tsm.get("fee_schedule"), None)
    if fee_schedule:
        fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
        if asset_id in fees_by_instrument:
            rt = fees_by_instrument[asset_id].get("round_turn", 0)
            return rt * contracts
        default_rt = fee_schedule.get("default_round_turn", 0)
        if default_rt > 0:
            return default_rt * contracts

    # Source 3: commission_per_contract (original spec)
    cpc = tsm.get("commission_per_contract", 0)
    if cpc > 0:
        return cpc * contracts * 2  # round trip

    # Source 4: Notify user
    logger.warning("ON-B7: Commission data missing for account %s — notifying user", account_id)
    return 0


def get_expected_fee(tsm: dict, asset_id: str) -> float:
    """V3: Get expected fee per contract (round-trip).

    Same logic as in B4 — factored here for shared use.
    """
    fee_schedule = parse_json(tsm.get("fee_schedule"), None)
    if fee_schedule:
        fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
        if asset_id in fees_by_instrument:
            return fees_by_instrument[asset_id].get("round_turn", 0.0)
        return fee_schedule.get("default_round_turn", 0.0)

    cpc = tsm.get("commission_per_contract", 0.0)
    return cpc * 2 if cpc else 0.0


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _write_trade_outcome(trade_id, user_id, account_id, asset, direction,
                         entry_price, signal_entry_price, exit_price, contracts,
                         gross_pnl, commission, net_pnl, slippage, outcome,
                         entry_time, regime_at_entry, aim_modifier, aim_breakdown,
                         session, tsm_used):
    """Write trade outcome to P3-D03."""
    aim_bd_str = json.dumps(aim_breakdown, default=str) if aim_breakdown else None
    entry_ts = entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                entry_price, signal_entry_price, exit_price, contracts,
                gross_pnl, commission, pnl, slippage, outcome,
                entry_time, regime_at_entry, aim_modifier_at_entry,
                aim_breakdown_at_entry, session, tsm_used, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, now())""",
            (trade_id, user_id, account_id, asset, direction,
             entry_price, signal_entry_price, exit_price, contracts,
             gross_pnl, commission, net_pnl, slippage, outcome,
             entry_ts, regime_at_entry, aim_modifier,
             aim_bd_str, session, tsm_used),
        )


def _update_capital_and_cb(user_id: str, account_id: str, net_pnl: float,
                           outcome: str, model_m: str = ""):
    """G-033: Atomic capital silo (D16) + intraday CB (D23) update.

    Both reads and both writes execute in the same cursor context to prevent
    concurrent close races from producing inconsistent state.
    """
    with get_cursor() as cur:
        # ── Read both current states ──
        cur.execute(
            """SELECT total_capital, accounts FROM p3_d16_user_capital_silos
               WHERE user_id = %s
               LATEST ON last_updated PARTITION BY user_id""",
            (user_id,),
        )
        d16_row = cur.fetchone()

        cur.execute(
            """SELECT l_t, n_t, l_b, n_b FROM p3_d23_circuit_breaker_intraday
               WHERE account_id = %s
               LATEST ON last_updated PARTITION BY account_id""",
            (account_id,),
        )
        d23_row = cur.fetchone()

        # ── Compute new states ──
        # D16 capital
        if d16_row:
            new_capital = (d16_row[0] or 0) + net_pnl
            d16_accounts = d16_row[1]
        else:
            new_capital = net_pnl
            d16_accounts = None

        # D23 circuit breaker
        l_t = (d23_row[0] or 0.0) + net_pnl if d23_row else net_pnl
        n_t = (d23_row[1] or 0) + 1 if d23_row else 1
        l_b = parse_json(d23_row[2], {}) if d23_row else {}
        n_b = parse_json(d23_row[3], {}) if d23_row else {}
        if model_m:
            l_b[model_m] = l_b.get(model_m, 0.0) + net_pnl
            n_b[model_m] = n_b.get(model_m, 0) + 1

        # ── Write both back-to-back ──
        if d16_row:
            cur.execute(
                """INSERT INTO p3_d16_user_capital_silos
                   (user_id, total_capital, accounts, last_updated)
                   VALUES (%s, %s, %s, now())""",
                (user_id, new_capital, d16_accounts),
            )

        cur.execute(
            """INSERT INTO p3_d23_circuit_breaker_intraday
               (account_id, l_t, n_t, l_b, n_b, last_updated)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (account_id, l_t, n_t, json.dumps(l_b), json.dumps(n_b)),
        )

    logger.debug("Capital+CB updated: user=%s account=%s pnl=%.2f", user_id, account_id, net_pnl)


def _publish_trade_outcome(trade_id, pos, outcome, net_pnl, exit_price, commission, slippage):
    """CRITICAL: Publish trade outcome to Redis Stream for Offline learning loop.

    Retries up to 3 times with exponential backoff (0.5s, 1s, 2s).
    Trade outcomes MUST reach Offline for the feedback loop to function.
    """
    import time

    payload = {
        "trade_id": trade_id,
        "user_id": pos["user_id"],
        "asset": pos["asset"],
        "direction": pos.get("direction", 1),
        "entry_price": pos.get("entry_price", 0),
        "exit_price": exit_price,
        "contracts": pos.get("contracts", 0),
        "pnl": net_pnl,
        "commission": commission,
        "slippage": slippage,
        "outcome": outcome,
        "regime_at_entry": pos.get("regime_state"),
        "aim_modifier_at_entry": pos.get("combined_modifier"),
        "aim_breakdown_at_entry": pos.get("aim_breakdown"),
        "session": pos.get("session"),
        "account": pos.get("account"),
        "timestamp": datetime.now().isoformat(),
    }
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            publish_to_stream(STREAM_TRADE_OUTCOMES, payload)
            logger.info("ON-B7: Published trade outcome %s to stream", trade_id)
            return
        except Exception as e:
            if attempt < max_attempts:
                delay = 0.5 * (2 ** (attempt - 1))
                logger.warning("ON-B7: Retry %d/%d publishing trade outcome %s: %s (backoff %.1fs)",
                               attempt, max_attempts, trade_id, e, delay)
                time.sleep(delay)
            else:
                logger.error("ON-B7: FAILED to publish trade outcome %s after %d attempts: %s",
                             trade_id, max_attempts, e)


# ---------------------------------------------------------------------------
# Notification / Alert helpers
# ---------------------------------------------------------------------------

def _notify(user_id: str, priority: str, message: str):
    """Send notification via Redis alerts channel."""
    try:
        client = get_redis_client()
        payload = json.dumps({
            "user_id": user_id,
            "priority": priority,
            "message": message,
            "source": "ONLINE_B7",
            "timestamp": datetime.now().isoformat(),
        })
        client.publish(CH_ALERTS, payload)
    except Exception as e:
        logger.error("ON-B7: Failed to send notification: %s", e)


# ---------------------------------------------------------------------------
# Market data stubs
# ---------------------------------------------------------------------------

def _get_live_price(asset_id: str) -> float | None:
    """Get live price from TopstepX stream cache, REST fallback."""
    contract_id = resolve_contract_id(asset_id)
    if not contract_id:
        return None
    # Stream cache (sub-second freshness)
    quote = quote_cache.get(contract_id)
    if quote and quote.get("lastPrice"):
        return float(quote["lastPrice"])
    # REST fallback (1-minute bar)
    try:
        from shared.topstep_client import get_topstep_client, TopstepXClientError
        from datetime import timezone
        client = get_topstep_client()
        now = datetime.now(timezone.utc)
        bars = client.get_bars(
            contract_id, 2, 1,
            (now - timedelta(minutes=5)).isoformat(),
            now.isoformat(),
        )
        if bars:
            return float(bars[-1]["close"])
    except Exception as exc:
        logger.warning("_get_live_price REST fallback for %s: %s", asset_id, exc)
    return None

def _get_api_commission(account_id: str, asset_id: str = "", tsm: dict | None = None) -> float | None:
    """Get commission per contract from TSM fee schedule or D17 fallback."""
    if tsm:
        return get_expected_fee(tsm, asset_id)
    # Fallback: query D17 system params
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT param_value FROM p3_d17_system_monitor_state "
                "WHERE param_key = 'default_commission_per_contract' "
                "LATEST ON last_updated PARTITION BY param_key"
            )
            row = cur.fetchone()
            if row:
                return float(row[0]) * 2  # round-trip
    except Exception:
        logger.debug("_get_api_commission: D17 fallback failed")
    return None

def _resolve_actual_entry_price(pos: dict) -> float | None:
    return pos.get("actual_entry_price")

def _check_vix_spike(pos: dict):
    """Check if VIX z-score > 2.0 against 60-day trailing mean/stdev (spec §2 B7)."""
    try:
        closes = get_trailing_vix_closes(lookback=60)
        if not closes or len(closes) < 10:
            return  # Insufficient history
        current = closes[-1]
        mean_60d = sum(closes) / len(closes)
        stdev_60d = (sum((v - mean_60d) ** 2 for v in closes) / len(closes)) ** 0.5
        if stdev_60d == 0:
            return
        z_score = (current - mean_60d) / stdev_60d
        if z_score > 2.0:
            _notify(pos["user_id"], "HIGH",
                    f"VIX spike: {current:.1f} (z={z_score:.2f}) while {pos['asset']} position open")
    except Exception:
        logger.debug("_check_vix_spike: failed for %s", pos.get("asset"))

def _regime_shift_detected(asset_id: str, regime_at_entry: str | None = None) -> bool:
    """Compare current regime (from cache) against regime at position entry."""
    if not regime_at_entry:
        return False
    current = _regime_cache.get(asset_id)
    if not current or current == "UNKNOWN":
        return False
    return current != regime_at_entry

def _parse_close_time(trading_hours: str) -> datetime | None:
    """Parse close time from trading_hours string (e.g., '09:30-16:00')."""
    if not trading_hours or "-" not in trading_hours:
        return None
    try:
        close_str = trading_hours.split("-")[1].strip()
        h, m = close_str.split(":")
        now = datetime.now(ZoneInfo("America/New_York"))
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except (ValueError, IndexError):
        return None


