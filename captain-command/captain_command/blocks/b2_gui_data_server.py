# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 2: GUI Data Server (P3-PG-31, P3-PG-31B).

Layer 1 — Main Dashboard: real-time data server pushed to connected
WebSocket clients.  Refreshes every 60 s + real-time signal/position events.

Layer 2 — System Overview (ADMIN only): network concentration, signal
quality, capacity, diagnostics, action queue, incident log, compliance.

V3 additions:
- Payout panel & scaling display for Topstep accounts (Block 2 GUI).
- P3-D23 intraday state, P3-D25 CB params.

Spec: Program3_Command.md lines 164-315
"""

import json
import logging
import math
import os
from datetime import datetime
from typing import Any

from shared.questdb_client import get_cursor
from shared.constants import SYSTEM_TIMEZONE
from shared.topstep_client import get_topstep_client, TopstepXClientError
from shared.topstep_stream import quote_cache
from shared.contract_resolver import resolve_contract_id

logger = logging.getLogger(__name__)

_CONTRACT_ID = os.environ.get("TOPSTEP_CONTRACT_ID", "CON.F.US.EP.H26")

# Module-level reference to UserStream (set by orchestrator on startup)
_user_stream = None


def set_user_stream(stream) -> None:
    """Register the active UserStream for live account data."""
    global _user_stream
    _user_stream = stream

# ---------------------------------------------------------------------------
# Layer 1: Main Dashboard data assembly
# ---------------------------------------------------------------------------


def build_dashboard_snapshot(user_id: str) -> dict:
    """Assemble a full dashboard snapshot for a single user.

    Called every 60 s by the orchestrator periodic refresh, and also on
    initial WebSocket connect.

    Returns
    -------
    dict
        Dashboard payload ready for WebSocket JSON push.
    """
    return {
        "type": "dashboard",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "capital_silo": _get_capital_silo(user_id),
        "open_positions": _get_open_positions(user_id),
        "pending_signals": _get_pending_signals(user_id),
        "aim_states": _get_aim_states(user_id),
        "tsm_status": _get_tsm_status(user_id),
        "decay_alerts": _get_decay_alerts(),
        "warmup_gauges": _get_warmup_gauges(),
        "notifications": _get_recent_notifications(user_id, limit=100),
        "payout_panel": _get_payout_panel(user_id),
        "scaling_display": _get_scaling_display(user_id),
        "live_market": _get_live_market_data(),
        "api_status": _get_api_connection_status(),
    }


# ---------------------------------------------------------------------------
# Layer 2: System Overview (ADMIN only)
# ---------------------------------------------------------------------------


def build_system_overview() -> dict:
    """Assemble the ADMIN-only System Overview panel data.

    Returns
    -------
    dict
        System overview payload.
    """
    return {
        "type": "system_overview",
        "timestamp": datetime.now().isoformat(),
        "network_concentration": _get_network_concentration(),
        "signal_quality": _get_signal_quality_summary(),
        "capacity_state": _get_capacity_state(),
        "diagnostic_health": _get_diagnostic_health(),
        "action_queue": _get_action_queue(),
        "system_params": _get_system_params(),
        "data_quality": _get_data_quality(),
        "incident_log": _get_recent_incidents(limit=50),
        "compliance_gate": _get_compliance_gate(),
    }


# ---------------------------------------------------------------------------
# V3: Payout Panel (Topstep accounts)
# ---------------------------------------------------------------------------


def _get_payout_panel(user_id: str) -> list[dict]:
    """Get payout recommendation data for all Topstep accounts of a user.

    Reads topstep_state from P3-D08.  Returns a list (one per account
    with ``topstep_optimisation == true``).
    """
    results = []
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT account_id, name, current_balance, starting_balance,
                          max_drawdown_limit, topstep_state
                   FROM p3_d08_tsm_state
                   WHERE user_id = %s AND topstep_optimisation = true""",
                (user_id,),
            )
            rows = cur.fetchall()
            for row in rows:
                ac_id, tsm_name, balance, starting, mdd_limit, ts_state_raw = row
                ts_state = json.loads(ts_state_raw) if ts_state_raw else {}
                profit = balance - starting if balance and starting else 0

                payout_rules = ts_state.get("payout_rules", {})
                max_per = payout_rules.get("max_per_payout", 5000)
                max_pct = 0.50  # 50% of profit
                commission_rate = payout_rules.get("commission_rate", 0.10)
                tier_floor = payout_rules.get("scaling_tier_floor", 4500)

                # W(A) = min(max_per, max_pct * (A - starting))
                w_max = min(max_per, max_pct * max(profit, 0))
                net_amount = w_max * (1 - commission_rate) if w_max > 0 else 0
                profit_after = profit - w_max
                recommended = w_max >= 500 and profit > tier_floor

                # MDD% calculations
                mdd_pct_current = (mdd_limit / balance * 100) if balance and mdd_limit else 0
                balance_after = balance - w_max if balance else 0
                mdd_pct_after = (mdd_limit / balance_after * 100) if balance_after > 0 and mdd_limit else 0

                # Scaling tier lookup
                tier_current = ts_state.get("scaling_tier", "unknown")
                tier_after = ts_state.get("tier_after_payout", tier_current)
                payouts_remaining = ts_state.get("payouts_remaining", 0)

                results.append({
                    "account_id": ac_id,
                    "tsm_name": tsm_name,
                    "recommended": recommended,
                    "amount": round(w_max, 2),
                    "net_after_commission": round(net_amount, 2),
                    "profit_current": round(profit, 2),
                    "profit_after": round(profit_after, 2),
                    "tier_current": tier_current,
                    "tier_after": tier_after,
                    "mdd_pct_current": round(mdd_pct_current, 2),
                    "mdd_pct_after": round(mdd_pct_after, 2),
                    "payouts_remaining": payouts_remaining,
                })
    except Exception as exc:
        logger.error("Payout panel query failed: %s", exc, exc_info=True)

    return results


# ---------------------------------------------------------------------------
# V3: Scaling Display (Topstep accounts)
# ---------------------------------------------------------------------------


def _get_scaling_display(user_id: str) -> list[dict]:
    """Get scaling tier info for all Topstep accounts of a user."""
    results = []
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT account_id, current_balance, starting_balance,
                          topstep_state
                   FROM p3_d08_tsm_state
                   WHERE user_id = %s AND scaling_plan_active = true""",
                (user_id,),
            )
            rows = cur.fetchall()
            for row in rows:
                ac_id, balance, starting, ts_state_raw = row
                ts_state = json.loads(ts_state_raw) if ts_state_raw else {}
                profit = balance - starting if balance and starting else 0

                current_max_micros = ts_state.get("current_max_micros", 0)
                open_micros = ts_state.get("open_positions_micros", 0)
                next_tier_profit = ts_state.get("profit_to_next_tier", 0)
                next_tier_label = ts_state.get("next_tier_label", "")

                results.append({
                    "account_id": ac_id,
                    "active": True,
                    "current_tier": ts_state.get("current_tier_label", ""),
                    "current_max_micros": current_max_micros,
                    "open_positions_micros": open_micros,
                    "available_slots": max(current_max_micros - open_micros, 0),
                    "profit_to_next_tier": round(next_tier_profit, 2),
                    "next_tier_label": next_tier_label,
                })
    except Exception as exc:
        logger.error("Scaling display query failed: %s", exc, exc_info=True)

    return results


# ---------------------------------------------------------------------------
# Dashboard sub-queries
# ---------------------------------------------------------------------------


def _get_capital_silo(user_id: str) -> dict:
    """Fetch capital silo summary — live balance from TopstepX, fallback to P3-D16."""
    result = {}

    # Try live data from UserStream first
    if _user_stream and _user_stream.account_data:
        ad = _user_stream.account_data
        result = {
            "total_capital": ad.get("balance"),
            "daily_pnl": None,       # Computed by reconciliation
            "cumulative_pnl": None,   # Computed by reconciliation
            "status": "LIVE" if ad.get("canTrade") else "RESTRICTED",
            "source": "topstep_live",
        }

    # If no live data, try REST API
    if not result.get("total_capital"):
        try:
            client = get_topstep_client()
            if client.is_authenticated:
                accounts = client.get_accounts(only_active=True)
                if accounts:
                    acc = accounts[0]
                    result = {
                        "total_capital": acc.get("balance"),
                        "daily_pnl": None,
                        "cumulative_pnl": None,
                        "status": "LIVE" if acc.get("canTrade") else "RESTRICTED",
                        "source": "topstep_rest",
                    }
        except TopstepXClientError as exc:
            logger.debug("TopstepX REST fallback for capital silo: %s", exc)

    # Fallback to QuestDB P3-D16
    if not result.get("total_capital"):
        try:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT total_capital, status
                       FROM p3_d16_user_capital_silos
                       WHERE user_id = %s
                       ORDER BY last_updated DESC LIMIT 1""",
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    result = {
                        "total_capital": row[0],
                        "daily_pnl": None,
                        "cumulative_pnl": None,
                        "status": row[1],
                        "source": "questdb",
                    }
        except Exception as exc:
            logger.error("Capital silo query failed: %s", exc, exc_info=True)

    return result


def _get_open_positions(user_id: str) -> list[dict]:
    """Fetch open positions from P3-D03 (outcome is NULL = still open)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT trade_id, asset, direction, entry_price,
                          contracts, account_id, entry_time, pnl
                   FROM p3_d03_trade_outcome_log
                   WHERE user_id = %s AND outcome IS NULL
                   ORDER BY entry_time DESC""",
                (user_id,),
            )
            return [
                {
                    "signal_id": r[0], "asset": r[1], "direction": r[2],
                    "entry_price": r[3], "contracts": r[4], "tp_level": None,
                    "sl_level": None, "account_id": r[5], "entry_time": r[6],
                    "current_pnl": r[7],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Open positions query failed: %s", exc, exc_info=True)
    return []


def _get_pending_signals(user_id: str) -> list[dict]:
    """Fetch recent unacted signals from P3-D17 session_log."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT event_id, asset, details, ts
                   FROM p3_session_event_log
                   WHERE user_id = %s AND event_type = 'SIGNAL_RECEIVED'
                   ORDER BY ts DESC LIMIT 20""",
                (user_id,),
            )
            results = []
            for r in cur.fetchall():
                detail = json.loads(r[2]) if r[2] else {}
                results.append({
                    "signal_id": r[0], "asset": r[1],
                    "timestamp": r[3], **detail,
                })
            return results
    except Exception as exc:
        logger.error("Pending signals query failed: %s", exc, exc_info=True)
    return []


_AIM_NAMES = {
    1: "VRP", 2: "Options Skew", 3: "Gamma Exposure", 4: "IVTS",
    6: "Economic Calendar", 7: "COT Positioning", 8: "Cross-Asset Corr",
    9: "Cross-Asset Momentum", 10: "Calendar Effects", 11: "Regime Warning",
    12: "Dynamic Costs", 13: "Sensitivity", 14: "Auto-Expansion",
    15: "Opening Volume", 16: "HMM Opportunity",
}


def _get_aim_states(user_id: str) -> list[dict]:
    """Fetch AIM states from P3-D01 (latest row per aim_id+asset_id).

    QuestDB LATEST ON PARTITION BY only works with SYMBOL columns, and
    aim_id is INT.  So we fetch all rows ordered by last_updated DESC
    and deduplicate in Python — keeping the first (most recent) row
    per (aim_id, asset_id) pair.
    """
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT aim_id, asset_id, status, warmup_progress,
                          current_modifier
                   FROM p3_d01_aim_model_states
                   ORDER BY last_updated DESC"""
            )
            seen: dict[tuple, dict] = {}
            for r in cur.fetchall():
                key = (r[0], r[1])
                if key in seen:
                    continue  # already have a newer row
                seen[key] = {
                    "aim_id": r[0],
                    "aim_name": _AIM_NAMES.get(r[0], f"AIM-{r[0]:02d}"),
                    "asset_id": r[1],
                    "status": r[2],
                    "warmup_pct": r[3],
                    "meta_weight": None,
                    "modifier": r[4],
                }
            return sorted(seen.values(), key=lambda x: (x["aim_id"], x["asset_id"]))
    except Exception as exc:
        logger.error("AIM states query failed: %s", exc, exc_info=True)
    return []


def _get_tsm_status(user_id: str) -> list[dict]:
    """Fetch TSM status per account from P3-D08 (latest row per account)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT account_id, name, current_balance,
                          max_drawdown_limit, max_daily_loss,
                          daily_loss_used, pass_probability,
                          starting_balance, current_drawdown
                   FROM p3_d08_tsm_state
                   WHERE user_id = %s
                   LATEST ON last_updated PARTITION BY account_id""",
                (user_id,),
            )
            results = []
            for r in cur.fetchall():
                mdd_limit = r[3] or 0
                starting_bal = r[7] or 0
                current_bal = r[2] or 0
                current_dd = r[8] or 0
                # Drawdown used = peak - current (current_drawdown tracks this),
                # or infer from starting_balance if current_drawdown not set
                dd_used = current_dd if current_dd > 0 else max(starting_bal - current_bal, 0)
                mdd_used_pct = (dd_used / mdd_limit * 100) if mdd_limit > 0 else 0

                mll = r[4] or 0
                daily_used = r[5] or 0
                daily_pct = (daily_used / mll * 100) if mll > 0 else 0

                results.append({
                    "account_id": r[0], "tsm_name": r[1],
                    "current_balance": current_bal,
                    "mdd_limit": mdd_limit, "mdd_used_pct": round(min(mdd_used_pct, 100), 1),
                    "daily_loss_limit": mll, "daily_loss_used": daily_used,
                    "daily_loss_pct": round(min(daily_pct, 100), 1),
                    "pass_probability": r[6],
                })
            return results
    except Exception as exc:
        logger.error("TSM status query failed: %s", exc, exc_info=True)
    return []


def _get_decay_alerts() -> list[dict]:
    """Fetch recent decay events from P3-D04."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, bocpd_cp_probability, cusum_c_up_prev,
                          last_updated
                   FROM p3_d04_decay_detector_states
                   WHERE bocpd_cp_probability > 0.5
                   ORDER BY last_updated DESC LIMIT 10"""
            )
            return [
                {
                    "asset": r[0], "cp_prob": r[1], "cusum_stat": r[2],
                    "level": None, "timestamp": r[3],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Decay alerts query failed: %s", exc, exc_info=True)
    return []


def _get_warmup_gauges() -> list[dict]:
    """Fetch warm-up progress from P3-D00 (latest row per asset)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, captain_status, warm_up_progress
                   FROM p3_d00_asset_universe
                   LATEST ON last_updated PARTITION BY asset_id
                   ORDER BY asset_id"""
            )
            return [
                {"asset_id": r[0], "status": r[1], "warmup_pct": r[2]}
                for r in cur.fetchall()
                if r[1] in ("WARM_UP", "ACTIVE", "TRAINING_ONLY")
            ]
    except Exception as exc:
        logger.error("Warmup gauges query failed: %s", exc, exc_info=True)
    return []


def _get_recent_notifications(user_id: str, limit: int = 100) -> list[dict]:
    """Fetch recent notifications from P3-D10."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT notification_id, priority, message, ts, gui_delivered
                   FROM p3_d10_notification_log
                   WHERE user_id IN (%s, 'SYSTEM')
                   ORDER BY ts DESC LIMIT %s""",
                (user_id, limit),
            )
            return [
                {
                    "notif_id": r[0], "priority": r[1], "message": r[2],
                    "timestamp": r[3], "delivered": r[4],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Notifications query failed: %s", exc, exc_info=True)
    return []


# ---------------------------------------------------------------------------
# System Overview sub-queries (ADMIN only)
# ---------------------------------------------------------------------------


def _get_network_concentration() -> dict:
    """Aggregate exposure across all users from P3-D17."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, direction, sum(contracts) as total_contracts,
                          count(DISTINCT user_id) as user_count
                   FROM p3_d03_trade_outcome_log
                   WHERE status = 'OPEN'
                   GROUP BY asset, direction"""
            )
            return {
                "exposures": [
                    {
                        "asset": r[0], "direction": r[1],
                        "total_contracts": r[2], "user_count": r[3],
                    }
                    for r in cur.fetchall()
                ]
            }
    except Exception as exc:
        logger.error("Network concentration query failed: %s", exc, exc_info=True)
    return {"exposures": []}


def _get_signal_quality_summary() -> dict:
    """Signal quality pass rate and distribution from P3-D17."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT count(*) as total,
                          sum(CASE WHEN event_type = 'SIGNAL_RECEIVED' THEN 1 ELSE 0 END) as passed
                   FROM p3_session_event_log
                   WHERE event_type IN ('SIGNAL_RECEIVED', 'SIGNAL_BLOCKED')
                   AND ts > dateadd('d', -7, now())"""
            )
            row = cur.fetchone()
            total = row[0] or 0
            passed = row[1] or 0
            return {
                "total_evaluated": total,
                "passed": passed,
                "pass_rate": round(passed / total, 3) if total > 0 else 0,
            }
    except Exception as exc:
        logger.error("Signal quality summary failed: %s", exc, exc_info=True)
    return {"total_evaluated": 0, "passed": 0, "pass_rate": 0}


def _get_capacity_state() -> dict:
    """Capacity evaluation from P3-D17 (latest from Online B9)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT details FROM p3_session_event_log
                   WHERE event_type = 'CAPACITY_EVALUATION'
                   ORDER BY ts DESC LIMIT 1"""
            )
            row = cur.fetchone()
            if row and row[0]:
                return json.loads(row[0])
    except Exception as exc:
        logger.error("Capacity state query failed: %s", exc, exc_info=True)
    return {}


def _get_diagnostic_health() -> list[dict]:
    """P3-D22 8-dimension diagnostic scores."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT dimension, score, status, details, timestamp
                   FROM p3_d22_system_health_diagnostic
                   WHERE timestamp = (
                       SELECT max(timestamp) FROM p3_d22_system_health_diagnostic
                       WHERE dimension != 'ACTION_ITEM_UPDATE'
                   ) AND dimension != 'ACTION_ITEM_UPDATE'
                   ORDER BY dimension"""
            )
            return [
                {
                    "dimension": r[0], "score": r[1], "status": r[2],
                    "details": r[3], "timestamp": r[4],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Diagnostic health query failed: %s", exc, exc_info=True)
    return []


def _get_action_queue() -> list[dict]:
    """Open action items from P3-D22."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT dimension, status, details, timestamp
                   FROM p3_d22_system_health_diagnostic
                   WHERE status IN ('OPEN', 'STALE', 'CRITICAL')
                   ORDER BY timestamp DESC LIMIT 50"""
            )
            return [
                {
                    "dimension": r[0], "status": r[1],
                    "details": r[2], "timestamp": r[3],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Action queue query failed: %s", exc, exc_info=True)
    return []


def _get_system_params() -> dict:
    """Fetch current system parameters from P3-D17."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT param_key, param_value FROM p3_d17_system_monitor_state"
            )
            return {r[0]: r[1] for r in cur.fetchall()}
    except Exception as exc:
        logger.error("System params query failed: %s", exc, exc_info=True)
    return {}


def _get_data_quality() -> dict:
    """Data freshness and connectivity status."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, captain_status, last_updated
                   FROM p3_d00_asset_universe
                   WHERE captain_status != 'INACTIVE'
                   ORDER BY asset_id"""
            )
            assets = []
            for r in cur.fetchall():
                assets.append({
                    "asset_id": r[0], "status": r[1],
                    "last_data_update": r[2],
                })
            return {"assets": assets}
    except Exception as exc:
        logger.error("Data quality query failed: %s", exc, exc_info=True)
    return {"assets": []}


def _get_recent_incidents(limit: int = 50) -> list[dict]:
    """Fetch recent incidents from P3-D21."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT incident_id, incident_type, severity,
                          component, details, status, timestamp
                   FROM p3_d21_incident_log
                   ORDER BY timestamp DESC LIMIT %s""",
                (limit,),
            )
            return [
                {
                    "incident_id": r[0], "type": r[1], "severity": r[2],
                    "component": r[3], "details": r[4], "status": r[5],
                    "timestamp": r[6],
                }
                for r in cur.fetchall()
            ]
    except Exception as exc:
        logger.error("Incident log query failed: %s", exc, exc_info=True)
    return []


def _get_compliance_gate() -> dict:
    """Read compliance gate status from config file."""
    gate_path = os.environ.get(
        "COMPLIANCE_GATE_PATH", "/captain/config/compliance_gate.json"
    )
    try:
        if os.path.exists(gate_path):
            with open(gate_path) as f:
                return json.load(f)
    except Exception as exc:
        logger.error("Compliance gate read failed: %s", exc, exc_info=True)
    return {"execution_mode": "MANUAL", "requirements": {}}


# ---------------------------------------------------------------------------
# Live TopstepX data (market + API status)
# ---------------------------------------------------------------------------


def build_live_market_update() -> dict:
    """Build a lightweight live_market message for high-frequency push.

    Called every ~1 second by the orchestrator to stream market data
    to the GUI without the overhead of a full dashboard snapshot.
    """
    return {
        "type": "live_market",
        **_get_live_market_data(),
    }


def _get_live_market_data(asset_id: str = "ES") -> dict:
    """Get live market data from TopstepX stream cache for an asset.

    Parameters
    ----------
    asset_id : str
        Asset identifier (e.g. "ES", "NQ").  Defaults to "ES".

    Returns price, bid/ask, volume, and change data when market
    stream is connected and receiving quotes.
    """
    contract_id = resolve_contract_id(asset_id) or _CONTRACT_ID
    quote = quote_cache.get(contract_id)
    if not quote:
        return {"connected": False, "contract_id": contract_id}

    return {
        "connected": True,
        "contract_id": contract_id,
        "last_price": quote.get("lastPrice") or (
            round((quote["bestBid"] + quote["bestAsk"]) / 2, 2)
            if quote.get("bestBid") and quote.get("bestAsk")
            else None
        ),
        "best_bid": quote.get("bestBid"),
        "best_ask": quote.get("bestAsk"),
        "spread": (
            round(quote["bestAsk"] - quote["bestBid"], 2)
            if quote.get("bestAsk") and quote.get("bestBid")
            else None
        ),
        "change": quote.get("change"),
        "change_pct": quote.get("changePercent"),
        "open": quote.get("open"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "volume": quote.get("volume"),
        "timestamp": quote.get("timestamp"),
    }


def _get_api_connection_status() -> dict:
    """Get TopstepX API and stream connection status."""
    from shared.topstep_stream import StreamState

    result = {
        "api_authenticated": False,
        "market_stream": "DISCONNECTED",
        "user_stream": "DISCONNECTED",
        "account_id": None,
        "account_name": None,
    }

    try:
        client = get_topstep_client()
        result["api_authenticated"] = client.is_authenticated
        if client.is_authenticated:
            result["token_age_hours"] = round(
                client.token_age_seconds / 3600, 1
            )
    except Exception:
        pass

    if _user_stream:
        result["user_stream"] = _user_stream.state.value
        ad = _user_stream.account_data
        if ad:
            result["account_id"] = ad.get("id")
            result["account_name"] = ad.get("name")

    # Market stream state is tracked by quote_cache freshness
    contract_id = resolve_contract_id("ES") or _CONTRACT_ID
    quote = quote_cache.get(contract_id)
    if quote:
        result["market_stream"] = "CONNECTED"

    return result
