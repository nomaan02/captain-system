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

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS, publish_to_stream, STREAM_TRADE_OUTCOMES
from shared.constants import TRADE_OUTCOME_VALUES
from shared.contract_resolver import resolve_contract_id
from shared.topstep_stream import quote_cache

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10


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
        if _regime_shift_detected(pos["asset"]):
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
                if datetime.now() >= buffer_time:
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

    # Update capital silo
    _update_capital_silo(pos["user_id"], account_id, net_pnl)

    # V3: Update P3-D23 intraday circuit breaker state
    _update_intraday_cb_state(account_id, net_pnl, outcome, model_m=pos.get("model", ""))

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
    fee_schedule = _parse_json(tsm.get("fee_schedule"), None)
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
    fee_schedule = _parse_json(tsm.get("fee_schedule"), None)
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


def _update_capital_silo(user_id: str, account_id: str, net_pnl: float):
    """Update user's capital silo with trade P&L."""
    with get_cursor() as cur:
        # Read current silo
        cur.execute(
            """SELECT total_capital, accounts FROM p3_d16_user_capital_silos
               WHERE user_id = %s ORDER BY last_updated DESC LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            current_capital = (row[0] or 0) + net_pnl
            cur.execute(
                """INSERT INTO p3_d16_user_capital_silos
                   (user_id, total_capital, accounts, last_updated)
                   VALUES (%s, %s, %s, now())""",
                (user_id, current_capital, row[1]),
            )


def _update_intraday_cb_state(account_id: str, net_pnl: float, outcome: str, model_m: str = ""):
    """V3: Update P3-D23 intraday circuit breaker state after trade outcome.

    Per spec: l_t accumulates ALL trade P&L (not just losses).
    n_t counts ALL trades taken today (not consecutive losses).
    l_b/n_b track per-basket (per-model) equivalents.
    """
    with get_cursor() as cur:
        # Load current state
        cur.execute(
            """SELECT l_t, n_t, l_b, n_b FROM p3_d23_circuit_breaker_intraday
               WHERE account_id = %s ORDER BY last_updated DESC LIMIT 1""",
            (account_id,),
        )
        row = cur.fetchone()
        l_t = (row[0] or 0.0) if row else 0.0
        n_t = (row[1] or 0) if row else 0
        l_b = _parse_json(row[2], {}) if row else {}
        n_b = _parse_json(row[3], {}) if row else {}

        # ALL trade P&L — unconditional
        l_t += net_pnl
        n_t += 1

        # Per-basket updates
        if model_m:
            l_b[model_m] = l_b.get(model_m, 0.0) + net_pnl
            n_b[model_m] = n_b.get(model_m, 0) + 1

        cur.execute(
            """INSERT INTO p3_d23_circuit_breaker_intraday
               (account_id, l_t, n_t, l_b, n_b, last_updated)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (account_id, l_t, n_t, json.dumps(l_b), json.dumps(n_b)),
        )


def _publish_trade_outcome(trade_id, pos, outcome, net_pnl, exit_price, commission, slippage):
    """CRITICAL: Publish trade outcome to Redis Stream for Offline learning loop."""
    try:
        publish_to_stream(STREAM_TRADE_OUTCOMES, {
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
        })
        logger.info("ON-B7: Published trade outcome %s to stream", trade_id)
    except Exception as e:
        logger.error("ON-B7: FAILED to publish trade outcome %s: %s", trade_id, e)


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

def _get_api_commission(account_id: str) -> float | None:
    return None

def _resolve_actual_entry_price(pos: dict) -> float | None:
    return pos.get("actual_entry_price")

def _check_vix_spike(pos: dict):
    # TODO: Implement VIX spike detection — read VIX data from stream/REST,
    #       compare against threshold, and notify user if spike detected.
    pass  # Stub for V1

def _regime_shift_detected(asset_id: str) -> bool:
    # TODO: Implement regime shift detection — compare current regime state
    #       (from BOCPD/HMM) against regime at position entry to detect mid-trade shifts.
    return False  # Stub for V1

def _parse_close_time(trading_hours: str) -> datetime | None:
    """Parse close time from trading_hours string (e.g., '09:30-16:00')."""
    if not trading_hours or "-" not in trading_hours:
        return None
    try:
        close_str = trading_hours.split("-")[1].strip()
        h, m = close_str.split(":")
        now = datetime.now()
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except (ValueError, IndexError):
        return None


def _parse_json(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
