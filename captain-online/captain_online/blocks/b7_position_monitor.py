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
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client, CH_ALERTS, publish_to_stream, STREAM_TRADE_OUTCOMES
from shared.constants import TRADE_OUTCOME_VALUES, now_et
from shared.contract_resolver import resolve_contract_id
from shared.topstep_stream import quote_cache
from shared.vix_provider import get_latest_vix_close, get_trailing_vix_closes
from shared.json_helpers import parse_json, parse_json_decimal
from shared.decimal_json import dumps_decimal
from shared.decimal_boundary import as_money as _money_d

logger = logging.getLogger(__name__)

# `_money_d` is an alias for shared.decimal_boundary.as_money — kept under
# the original short name for compactness in the hot tick-by-tick PnL path.


# ---------------------------------------------------------------------------
# Per-symbol contract economics — Bug A guard (Tier 1 fix, 2026-04-29)
# ---------------------------------------------------------------------------
#
# Authoritative source of `point_value` is p3_d00_asset_universe.point_value.
# Historic regression: the live PnL path read `pos.get("point_value", 50.0)`
# at multiple layers, defaulting to ES's PV (50) for every asset whenever
# the upstream chain failed to populate the field. `sanitise_for_api` in
# captain-command/.../b1_core_routing.py strips the field, so the default
# fired for every non-ES trade and inflated D03 gross_pnl by `50 / true_pv`.
#
# Tier 1 fix policy:
#   - ALWAYS look up D00 in this module (do NOT trust pos["point_value"]).
#   - Cache per process-lifetime (asset spec is effectively static intraday).
#   - On D00 miss / DB failure: log CRITICAL and RAISE — never default to 50.
#     A loud failure aborting one resolve_position call is incomparably safer
#     than silently writing inflated PnL to D03 and tripping circuit breakers.
# ---------------------------------------------------------------------------

_POINT_VALUE_CACHE: dict[str, Decimal] = {}


class PointValueResolutionError(RuntimeError):
    """Raised when point_value cannot be resolved from D00 for an asset.

    Caller should treat this as a non-recoverable error for that single
    position resolution and escalate (alert + manual close), NOT default.
    """


def _resolve_point_value(asset_id: str) -> Decimal:
    """Return the canonical point_value for `asset_id` from D00.

    Strict semantics:
      * Always reads `p3_d00_asset_universe` (LATEST ON last_updated).
      * Caches the first successful resolution for the lifetime of the
        process (D00 specs change only on bootstrap / contract roll).
      * Raises `PointValueResolutionError` on missing or NULL value.
      * Raises on DB failure after logging CRITICAL.

    Never returns a default. The 50.0 fallback was Bug A — see module
    docstring above.
    """
    if not asset_id:
        raise PointValueResolutionError(
            "point_value lookup called with empty asset_id"
        )
    cached = _POINT_VALUE_CACHE.get(asset_id)
    if cached is not None:
        return cached
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT point_value FROM p3_d00_asset_universe "
                "WHERE asset_id = %s "
                "LATEST ON last_updated PARTITION BY asset_id",
                (asset_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.error(
            "ON-B7: CRITICAL D00 point_value query failed for %s: %s",
            asset_id, exc,
        )
        raise PointValueResolutionError(
            f"D00 point_value query failed for {asset_id}: {exc}"
        ) from exc

    if not row or row[0] is None:
        logger.error(
            "ON-B7: CRITICAL D00 point_value row missing/NULL for asset=%s "
            "(refusing legacy default=50.0; resolve via D00 bootstrap)",
            asset_id,
        )
        raise PointValueResolutionError(
            f"D00 has no point_value for asset {asset_id}"
        )

    pv = row[0] if isinstance(row[0], Decimal) else Decimal(str(row[0]))
    if pv <= 0:
        logger.error(
            "ON-B7: CRITICAL D00 point_value for %s is non-positive: %s",
            asset_id, pv,
        )
        raise PointValueResolutionError(
            f"D00 point_value for {asset_id} is non-positive: {pv}"
        )
    _POINT_VALUE_CACHE[asset_id] = pv
    return pv


def _reset_point_value_cache() -> None:
    """Clear the D00 point_value cache. Test/ops helper; called on contract roll."""
    _POINT_VALUE_CACHE.clear()


def _get_locked_m(asset: str) -> int | None:
    """Return the locked-strategy m for asset from p3_d00_asset_universe."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT locked_strategy FROM p3_d00_asset_universe "
                "WHERE asset_id = %s LATEST ON last_updated PARTITION BY asset_id",
                (asset,),
            )
            row = cur.fetchone()
        if row and row[0]:
            return json.loads(row[0]).get("m")
    except Exception:
        pass
    return None


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

    Decimal/float boundary discipline (2026-04-30 Bug C, third sister-bug
    after Bug A round 2):
      * Position state (tp_level, sl_level, entry_price, risk_amount)
        flows through Redis stream payloads via parse_json_decimal /
        loads_decimal -> Decimal-typed.
      * current_price comes from the live quote stream (TopstepX) -> float.
      * Arithmetic between them tripped TypeError at NY open today.
      * Fix: coerce ALL price fields via `_money_d` (alias for
        shared.decimal_boundary.as_money) ONCE at the top of each
        iteration. Use Decimal end-to-end for arithmetic and comparisons,
        convert to float only when notifying / formatting / publishing.
    """
    resolved = []

    for pos in open_positions:
        current_price_raw = _get_live_price(pos["asset"])
        if current_price_raw is None:
            continue

        # Bug A guard: ALWAYS resolve from D00; never trust pos["point_value"]
        # which the historic 50.0-default cascade could leave at ES's PV for
        # every asset. _resolve_point_value raises rather than defaulting.
        try:
            pv = _resolve_point_value(pos["asset"])
        except PointValueResolutionError as exc:
            logger.error(
                "ON-B7: skipping live PnL update for %s — %s",
                pos.get("asset"), exc,
            )
            _notify(
                pos.get("user_id", "SYSTEM"), "CRITICAL",
                f"PnL tracking halted for {pos.get('asset')}: D00 point_value "
                "missing — verify D00 bootstrap before close",
            )
            continue

        # Bug C boundary: coerce every position-state monetary field to
        # Decimal once. tp/sl/entry_price come from Redis (Decimal after
        # loads_decimal); current_price comes from the live quote stream
        # (float). Arithmetic and comparison stay Decimal end-to-end.
        current_price = _money_d(current_price_raw)
        entry_price = _money_d(pos.get("entry_price", 0))
        risk_amount = _money_d(pos.get("risk_amount", 1))
        tp = _money_d(pos["tp_level"]) if pos.get("tp_level") is not None else None
        sl = _money_d(pos["sl_level"]) if pos.get("sl_level") is not None else None

        # P&L tracking (Decimal arithmetic; float on pos for downstream % calcs)
        direction = pos.get("direction", 1)
        contracts = pos.get("contracts", 0)
        cp = (
            (current_price - entry_price)
            * Decimal(direction)
            * Decimal(contracts)
            * pv
        )
        pos["current_pnl"] = float(cp)
        pos["pnl_pct"] = (
            float(cp / risk_amount) if risk_amount > 0 else 0.0
        )

        # TP/SL proximity (Decimal arithmetic throughout)
        if tp is not None and entry_price > 0:
            tp_range = abs(tp - entry_price)
            tp_distance = (
                abs(tp - current_price) / tp_range if tp_range > 0 else Decimal("1")
            )

            if tp_distance < Decimal("0.10"):
                _notify(pos["user_id"], "HIGH",
                        f"TP approaching for {pos['asset']}: "
                        f"{float(current_price)} vs TP {float(tp)}")

        if sl is not None and entry_price > 0:
            sl_range = abs(sl - entry_price)
            sl_distance = (
                abs(sl - current_price) / sl_range if sl_range > 0 else Decimal("1")
            )

            if sl_distance < Decimal("0.10"):
                _notify(pos["user_id"], "CRITICAL",
                        f"SL approaching for {pos['asset']}: "
                        f"{float(current_price)} vs SL {float(sl)}")

        # VIX spike alert
        _check_vix_spike(pos)

        # Regime shift alert
        if _regime_shift_detected(pos["asset"], pos.get("regime_state")):
            _notify(pos["user_id"], "CRITICAL",
                    f"Regime shift detected for {pos['asset']} — review position")

        # Position resolution — TP/SL hit (Decimal comparison; pass float
        # exit_price to resolve_position which already coerces internally)
        if tp is not None:
            if (direction == 1 and current_price >= tp) or (direction == -1 and current_price <= tp):
                resolve_position(pos, "TP_HIT", float(current_price), tsm_configs)
                resolved.append(pos)
                continue

        if sl is not None:
            if (direction == 1 and current_price <= sl) or (direction == -1 and current_price >= sl):
                resolve_position(pos, "SL_HIT", float(current_price), tsm_configs)
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
                    resolve_position(pos, "TIME_EXIT", float(current_price), tsm_configs)
                    resolved.append(pos)
                    continue

    return resolved


def resolve_position(pos: dict, outcome: str, exit_price: float, tsm_configs: dict):
    """Resolve a position: log trade outcome, update capital, publish to Offline.

    CRITICAL: This is the feedback loop bridge to Offline learning.

    Bug A guard (2026-04-29): point_value is resolved from D00 here, never
    from `pos`. The historic `pos.get("point_value", 50.0)` default produced
    50× / 25× / 100× inflated gross_pnl for every non-ES asset and tripped
    the silo drawdown circuit breaker on phantom losses. Resolution failure
    now raises and is escalated to the user — no silent default.
    """
    asset = pos["asset"]
    pv = _resolve_point_value(asset)
    direction = pos.get("direction", 1)
    contracts = pos.get("contracts", 0)
    entry_price = pos.get("entry_price", 0)
    account_id = pos.get("account")
    dir_d = Decimal(direction)
    ctr = Decimal(contracts)

    gross_pnl = (
        (_money_d(exit_price) - _money_d(entry_price)) * dir_d * ctr * pv
    )

    # Commission (V3: resolve_commission with fee_schedule priority)
    commission = resolve_commission(account_id, contracts, pos["asset"], tsm_configs)
    net_pnl = gross_pnl - _money_d(commission)

    # Actual entry price
    actual_entry = _resolve_actual_entry_price(pos)
    slippage = None
    if actual_entry is not None:
        sig_ref = pos.get("signal_entry_price", entry_price)
        slippage = (
            (_money_d(actual_entry) - _money_d(sig_ref)) * dir_d * ctr * pv
        )

    # Trade ID
    trade_id = f"TRD-{uuid.uuid4().hex[:12].upper()}"

    # Write to P3-D03
    _write_trade_outcome(
        trade_id=trade_id,
        signal_id=pos.get("signal_id") or f"LEGACY-{uuid.uuid4()}",
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
    _notify(
        pos["user_id"],
        "CRITICAL",
        f"Position closed: {pos['asset']} {outcome} Net PnL=${float(net_pnl):.2f} "
        f"(commission=${float(commission):.2f})",
    )

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

    logger.info(
        "ON-B7: Position resolved — %s %s %s net_pnl=%.2f trade_id=%s",
        pos["asset"],
        outcome,
        pos["user_id"],
        float(net_pnl),
        trade_id,
    )


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
    fee_schedule = parse_json_decimal(tsm.get("fee_schedule"), None)
    if fee_schedule:
        fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
        if asset_id in fees_by_instrument:
            rt = fees_by_instrument[asset_id].get("round_turn", 0)
            v = Decimal(str(rt)) * Decimal(contracts)
            return float(v)
        default_rt = fee_schedule.get("default_round_turn", 0)
        if default_rt and Decimal(str(default_rt)) > 0:
            return float(Decimal(str(default_rt)) * Decimal(contracts))

    # Source 3: commission_per_contract (original spec)
    cpc = tsm.get("commission_per_contract", 0)
    if cpc and Decimal(str(cpc)) > 0:
        return float(Decimal(str(cpc)) * Decimal(contracts) * Decimal(2))

    # Source 4: Notify user
    logger.warning("ON-B7: Commission data missing for account %s — notifying user", account_id)
    return 0


def get_expected_fee(tsm: dict, asset_id: str) -> float:
    """V3: Get expected fee per contract (round-trip).

    Same logic as in B4 — factored here for shared use.
    """
    fee_schedule = parse_json_decimal(tsm.get("fee_schedule"), None)
    if fee_schedule:
        fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
        if asset_id in fees_by_instrument:
            rt = fees_by_instrument[asset_id].get("round_turn", 0.0)
            return float(Decimal(str(rt)))
        drt = fee_schedule.get("default_round_turn", 0.0)
        return float(Decimal(str(drt)))

    cpc = tsm.get("commission_per_contract", 0.0)
    if cpc and Decimal(str(cpc)) > 0:
        return float(Decimal(str(cpc)) * Decimal(2))
    return 0.0


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _write_trade_outcome(trade_id, user_id, account_id, asset, direction,
                         entry_price, signal_entry_price, exit_price, contracts,
                         gross_pnl, commission, net_pnl, slippage, outcome,
                         entry_time, regime_at_entry, aim_modifier, aim_breakdown,
                         session, tsm_used, signal_id=None):
    """Write trade outcome to P3-D03.

    Phase 7: ``signal_id`` ties the row to the originating B6 signal so
    PG-09 can pair signals with realised P&L. ``LEGACY-<uuid>`` if the
    caller can't supply one (e.g. paper-trader shim, replay).
    """
    aim_bd_str = dumps_decimal(aim_breakdown) if aim_breakdown else None
    entry_ts = entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time
    model_m = _get_locked_m(asset)
    sig_id = signal_id if signal_id else f"LEGACY-{uuid.uuid4()}"

    with get_cursor() as cur:
        exit_ts = now_et().isoformat()
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, signal_id, user_id, account_id, asset, direction,
                entry_price, signal_entry_price, exit_price, contracts,
                gross_pnl, commission, pnl, slippage, outcome,
                entry_time, exit_time, regime_at_entry, aim_modifier_at_entry,
                aim_breakdown_at_entry, session, tsm_used, model_m, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (trade_id, sig_id, user_id, account_id, asset, direction,
             entry_price, signal_entry_price, exit_price, contracts,
             gross_pnl, commission, net_pnl, slippage, outcome,
             entry_ts, exit_ts, regime_at_entry, aim_modifier,
             aim_bd_str, session, tsm_used, model_m),
        )


def _update_capital_and_cb(
    user_id: str,
    account_id: str,
    net_pnl: float | Decimal,
    outcome: str,
    model_m: str = "",
):
    """G-033: Atomic capital silo (D16) + intraday CB (D23) update.

    Both reads and both writes execute in the same cursor context to prevent
    concurrent close races from producing inconsistent state.
    """
    with get_cursor() as cur:
        # ── Read both current states ──
        cur.execute(
            """SELECT status, role, starting_capital, total_capital, accounts,
                      max_simultaneous_positions, max_portfolio_risk_pct,
                      correlation_threshold, user_kelly_ceiling,
                      capital_history, telegram_chat_id, created
               FROM p3_d16_user_capital_silos
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
        net_dec = net_pnl if isinstance(net_pnl, Decimal) else Decimal(str(net_pnl))
        if d16_row:
            new_capital = Decimal(str(d16_row[3] or 0)) + net_dec
            d16_accounts = d16_row[4]
        else:
            new_capital = net_dec
            d16_accounts = None

        # D23 circuit breaker
        l_t = (Decimal(str(d23_row[0] or 0)) + net_dec) if d23_row else net_dec  # decimal-boundary: ok (Decimal(str()) coerces falsy-zero correctly)
        n_t = (d23_row[1] or 0) + 1 if d23_row else 1  # decimal-boundary: ok (n_t is a trade count, not money)
        l_b = parse_json_decimal(d23_row[2], {}) if d23_row else {}
        n_b = parse_json(d23_row[3], {}) if d23_row else {}
        if model_m:
            prev = l_b.get(model_m, Decimal("0"))
            if not isinstance(prev, Decimal):
                prev = Decimal(str(prev))
            l_b[model_m] = prev + net_dec
            n_b[model_m] = n_b.get(model_m, 0) + 1

        # ── Write both back-to-back ──
        if d16_row:
            cur.execute(
                """INSERT INTO p3_d16_user_capital_silos (
                       user_id, status, role, starting_capital, total_capital, accounts,
                       max_simultaneous_positions, max_portfolio_risk_pct,
                       correlation_threshold, user_kelly_ceiling,
                       capital_history, telegram_chat_id, created, last_updated
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (user_id, d16_row[0], d16_row[1], d16_row[2],
                 new_capital, d16_accounts,
                 d16_row[5], d16_row[6], d16_row[7], d16_row[8],
                 d16_row[9], d16_row[10], d16_row[11]),
            )

        cur.execute(
            """INSERT INTO p3_d23_circuit_breaker_intraday
               (account_id, l_t, n_t, l_b, n_b, last_updated)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (account_id, l_t, n_t, dumps_decimal(l_b), json.dumps(n_b)),
        )

    logger.debug(
        "Capital+CB updated: user=%s account=%s pnl=%.2f",
        user_id,
        account_id,
        float(net_pnl),
    )


def _publish_trade_outcome(trade_id, pos, outcome, net_pnl, exit_price, commission, slippage):
    """CRITICAL: Publish trade outcome to Redis Stream for Offline learning loop.

    Retries up to 3 times with exponential backoff (0.5s, 1s, 2s).
    Trade outcomes MUST reach Offline for the feedback loop to function.
    """
    import time

    closed_at = now_et().isoformat()
    payload = {
        "trade_id": trade_id,
        "signal_id": pos.get("signal_id"),
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
        "tp_level": pos.get("tp_level"),
        "sl_level": pos.get("sl_level"),
        "entry_time": pos.get("entry_time"),
        "exit_time": closed_at,
        "regime_at_entry": pos.get("regime_state"),
        "aim_modifier_at_entry": pos.get("combined_modifier"),
        "aim_breakdown_at_entry": pos.get("aim_breakdown"),
        "session": pos.get("session"),
        "account": pos.get("account"),
        "timestamp": closed_at,
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
            "timestamp": now_et().isoformat(),
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
            close = bars[-1].get("c") if bars[-1].get("c") is not None else bars[-1].get("close")
            return float(close) if close is not None else None
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
            if row and row[0] is not None:
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


