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
import threading
from datetime import datetime
from typing import Any

from shared.questdb_client import get_cursor
from shared.redis_client import get_redis_client
from shared.constants import SYSTEM_TIMEZONE
from shared.topstep_client import get_topstep_client, TopstepXClientError
from shared.topstep_stream import quote_cache
from shared.contract_resolver import resolve_contract_id

logger = logging.getLogger(__name__)

_CONTRACT_ID = os.environ.get("TOPSTEP_CONTRACT_ID", "CON.F.US.EP.H26")

# Lock protecting mutable module-level state so concurrent GUI clients
# receive atomically-consistent financial snapshots (§7 B2).
_state_lock = threading.Lock()

# Module-level reference to UserStream (set by orchestrator on startup)
_user_stream = None
# Module-level account data cache (set from REST at startup, used as fallback
# when the UserStream hasn't received a GatewayUserAccount push yet)
_account_data: dict | None = None


def set_user_stream(stream) -> None:
    """Register the active UserStream for live account data."""
    global _user_stream
    with _state_lock:
        _user_stream = stream


def set_account_data(account: dict) -> None:
    """Cache account data from REST API for api_status fallback."""
    global _account_data
    with _state_lock:
        _account_data = account


# Last known pipeline stage from Online (set by command orchestrator status handler)
_pipeline_stage: str = "WAITING"


def set_pipeline_stage(stage: str) -> None:
    """Update the cached pipeline stage for snapshot inclusion."""
    global _pipeline_stage
    with _state_lock:
        _pipeline_stage = stage

# ---------------------------------------------------------------------------
# Layer 1: Main Dashboard data assembly
# ---------------------------------------------------------------------------


def _get_service_health() -> dict:
    """Ping QuestDB and Redis to determine connectivity status."""
    health = {"questdb": "unknown", "redis": "unknown"}
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
        health["questdb"] = "ok"
    except Exception:
        health["questdb"] = "error"
    try:
        r = get_redis_client()
        r.ping()
        health["redis"] = "ok"
    except Exception:
        health["redis"] = "error"
    return health


def build_dashboard_snapshot(user_id: str) -> dict:
    """Assemble a full dashboard snapshot for a single user.

    Called every 60 s by the orchestrator periodic refresh, and also on
    initial WebSocket connect.

    Returns
    -------
    dict
        Dashboard payload ready for WebSocket JSON push.
    """
    # Snapshot mutable globals atomically so the dashboard payload is
    # internally consistent even when setters fire on another thread.
    with _state_lock:
        stream = _user_stream
        acct = _account_data
        stage = _pipeline_stage

    return {
        "type": "dashboard",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "capital_silo": _get_capital_silo(user_id, stream),
        "open_positions": _get_open_positions(user_id),
        "pending_signals": _get_pending_signals(user_id),
        "aim_states": _get_aim_states(user_id),
        "tsm_status": _get_tsm_status(user_id),
        "decay_alerts": _get_decay_alerts(),
        "warmup_gauges": _get_warmup_gauges(),
        "regime_panel": _get_regime_panel(),
        "notifications": _get_recent_notifications(user_id, limit=100),
        "payout_panel": _get_payout_panel(user_id),
        "scaling_display": _get_scaling_display(user_id),
        "live_market": _get_live_market_data(),
        "api_status": _get_api_connection_status(stream, acct),
        "pipeline_stage": stage,
        "service_health": _get_service_health(),
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


def _get_capital_silo(user_id: str, user_stream=None) -> dict:
    """Fetch capital silo summary — live balance from TopstepX, fallback to P3-D16."""
    result = {}

    # Try live data from UserStream first
    if user_stream and user_stream.account_data:
        ad = user_stream.account_data
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
                       LATEST ON last_updated PARTITION BY user_id
                       WHERE user_id = %s""",
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
            # Find signal IDs that have been acted on (TRADE_TAKEN / TRADE_SKIPPED)
            cur.execute(
                """SELECT DISTINCT event_id FROM p3_session_event_log
                   WHERE user_id = %s AND event_type IN ('TRADE_TAKEN', 'TRADE_SKIPPED')""",
                (user_id,),
            )
            actioned_ids = {row[0] for row in cur.fetchall()}

            cur.execute(
                """SELECT event_id, asset, details, ts
                   FROM p3_session_event_log
                   WHERE user_id = %s AND event_type = 'SIGNAL_RECEIVED'
                   ORDER BY ts DESC LIMIT 20""",
                (user_id,),
            )
            results = []
            for r in cur.fetchall():
                if r[0] in actioned_ids:
                    continue
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
    5: "Order Book Depth", 6: "Economic Calendar", 7: "COT Positioning",
    8: "Cross-Asset Corr", 9: "Cross-Asset Momentum", 10: "Calendar Effects",
    11: "Regime Warning", 12: "Dynamic Costs", 13: "Sensitivity",
    14: "Auto-Expansion", 15: "Opening Volume", 16: "HMM Opportunity",
}

_AIM_TIERS = {
    1: 2, 2: 2, 3: 2, 4: 1, 5: 0, 6: 1, 7: 2,
    8: 1, 9: 2, 10: 2, 11: 1, 12: 1, 13: 3, 14: 3, 15: 1, 16: 0,
}

# AIMs whose external data adapters return None (per F5.9 reconciliation)
_AIM_FEATURE_CONNECTED = {
    1: True, 2: True, 3: False, 4: True, 5: False, 6: True, 7: False,
    8: True, 9: True, 10: True, 11: True, 12: True, 13: True, 14: True,
    15: True, 16: True,
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


def get_aim_detail(aim_id: int) -> dict:
    """Fetch enriched AIM detail for the modal overlay.

    Joins P3-D01 (model states) and P3-D02 (meta weights) per asset
    for the given aim_id.  For AIM-16, also checks P3-D26.
    """
    name = _AIM_NAMES.get(aim_id, f"AIM-{aim_id:02d}")
    tier = _AIM_TIERS.get(aim_id, 0)
    feature_connected = _AIM_FEATURE_CONNECTED.get(aim_id, False)

    per_asset: list[dict] = []
    d01_populated = False
    d02_populated = False

    # --- D01: model states ---
    d01_by_asset: dict[str, dict] = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, status, current_modifier, warmup_progress,
                          last_retrained
                   FROM p3_d01_aim_model_states
                   WHERE aim_id = %s
                   ORDER BY last_updated DESC""",
                (aim_id,),
            )
            for r in cur.fetchall():
                asset = r[0]
                if asset in d01_by_asset:
                    continue
                d01_by_asset[asset] = {
                    "status": r[1],
                    "modifier": r[2],
                    "warmup_progress": r[3],
                    "last_retrained": r[4],
                }
            if d01_by_asset:
                d01_populated = True
    except Exception as exc:
        logger.error("AIM detail D01 query failed: %s", exc, exc_info=True)

    # --- D02: meta weights ---
    d02_by_asset: dict[str, dict] = {}
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, inclusion_flag, inclusion_probability,
                          recent_effectiveness, days_below_threshold
                   FROM p3_d02_aim_meta_weights
                   WHERE aim_id = %s
                   ORDER BY last_updated DESC""",
                (aim_id,),
            )
            for r in cur.fetchall():
                asset = r[0]
                if asset in d02_by_asset:
                    continue
                d02_by_asset[asset] = {
                    "inclusion_flag": r[1],
                    "inclusion_probability": r[2],
                    "recent_effectiveness": r[3],
                    "days_below_threshold": r[4],
                }
            if d02_by_asset:
                d02_populated = True
    except Exception as exc:
        logger.error("AIM detail D02 query failed: %s", exc, exc_info=True)

    # --- D26 check (AIM-16 only) ---
    d26_populated = False
    if aim_id == 16:
        try:
            with get_cursor() as cur:
                cur.execute(
                    "SELECT count() FROM p3_d26_hmm_opportunity_state"
                )
                row = cur.fetchone()
                d26_populated = bool(row and row[0] > 0)
        except Exception:
            pass

    # --- Merge per-asset ---
    all_assets = sorted(set(d01_by_asset.keys()) | set(d02_by_asset.keys()))
    for asset in all_assets:
        d01 = d01_by_asset.get(asset, {})
        d02 = d02_by_asset.get(asset, {})
        # Parse modifier — stored as STRING in QuestDB
        mod_raw = d01.get("modifier")
        try:
            mod_val = float(mod_raw) if mod_raw is not None else None
        except (ValueError, TypeError):
            mod_val = None

        per_asset.append({
            "asset_id": asset,
            "d01_status": d01.get("status"),
            "d01_modifier": mod_val,
            "d01_warmup_progress": d01.get("warmup_progress"),
            "d01_last_retrained": (
                d01["last_retrained"].isoformat()
                if d01.get("last_retrained") else None
            ),
            "d02_inclusion_flag": d02.get("inclusion_flag"),
            "d02_inclusion_probability": d02.get("inclusion_probability"),
            "d02_recent_effectiveness": d02.get("recent_effectiveness"),
            "d02_days_below_threshold": d02.get("days_below_threshold"),
        })

    all_checks = d01_populated and d02_populated and feature_connected
    if aim_id == 16:
        all_checks = all_checks and d26_populated

    return {
        "aim_id": aim_id,
        "aim_name": name,
        "tier": tier,
        "per_asset": per_asset,
        "validation": {
            "d01_populated": d01_populated,
            "d02_populated": d02_populated,
            "d26_populated": d26_populated if aim_id == 16 else None,
            "feature_data_connected": feature_connected,
            "all_checks_pass": all_checks,
        },
    }


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


def _get_regime_panel() -> dict:
    """Fetch regime state from P3-D00 locked_strategy for active assets."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, captain_status, locked_strategy
                   FROM p3_d00_asset_universe
                   WHERE locked_strategy IS NOT NULL
                     AND locked_strategy != '{}'
                   LATEST ON last_updated PARTITION BY asset_id
                   ORDER BY asset_id"""
            )
            assets = []
            for r in cur.fetchall():
                if r[1] not in ("ACTIVE", "WARM_UP", "TRAINING_ONLY"):
                    continue
                strat = json.loads(r[2]) if isinstance(r[2], str) else r[2]
                assets.append({
                    "asset_id": r[0],
                    "regime_class": strat.get("regime_class", "UNKNOWN"),
                    "model_type": strat.get("confidence_flag", "UNKNOWN"),
                    "OO": strat.get("OO"),
                })

            regime_classes = [a["regime_class"] for a in assets]
            model_types = [a["model_type"] for a in assets]
            oo_values = [a["OO"] for a in assets if a["OO"] is not None]

            neutral_count = sum(1 for r in regime_classes if r == "REGIME_NEUTRAL")
            classifier_count = sum(1 for m in model_types if m not in ("NO_CLASSIFIER", "UNKNOWN"))

            return {
                "assets": assets,
                "summary": {
                    "total_active": len(assets),
                    "regime_neutral": neutral_count,
                    "classifiers_trained": classifier_count,
                    "method": "Classifier" if classifier_count > 0 else "Binary Rule",
                    "avg_oo": round(sum(oo_values) / len(oo_values), 4) if oo_values else None,
                },
            }
    except Exception as exc:
        logger.error("Regime panel query failed: %s", exc, exc_info=True)
    return {"assets": [], "summary": {}}


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
                   LATEST ON ts PARTITION BY event_type
                   WHERE event_type = 'CAPACITY_EVALUATION'"""
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


def _get_api_connection_status(user_stream=None, account_data=None) -> dict:
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

    if user_stream:
        result["user_stream"] = user_stream.state.value
        ad = user_stream.account_data
        if ad:
            result["account_id"] = ad.get("id")
            result["account_name"] = ad.get("name")

    # Fallback: use REST account data cached at startup
    if result["account_id"] is None and account_data:
        result["account_id"] = str(account_data.get("id", ""))
        result["account_name"] = account_data.get("name", "")

    # Market stream state is tracked by quote_cache freshness
    contract_id = resolve_contract_id("ES") or _CONTRACT_ID
    quote = quote_cache.get(contract_id)
    if quote:
        result["market_stream"] = "CONNECTED"

    return result


# ---------------------------------------------------------------------------
# Process Monitoring (Processes tab)
# ---------------------------------------------------------------------------

BLOCK_REGISTRY = [
    # --- Captain Online (signal engine, session-triggered) ---
    {
        "block_id": "online-orchestrator",
        "name": "Online Orchestrator",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/orchestrator.py",
        "description": "Session loop: evaluates at NY/LON/APAC opens, sequences B1-B9 per session",
        "trigger": "always_on",
        "trigger_label": "24/7 session loop",
    },
    {
        "block_id": "online-b1",
        "name": "B1 Data Ingestion",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b1_data_ingestion.py",
        "description": "Loads active assets, validates data quality, resolves contracts, computes features",
        "trigger": "session_open",
        "trigger_label": "Session open",
    },
    {
        "block_id": "online-b1f",
        "name": "B1 Feature Computation",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b1_features.py",
        "description": "Computes OHLCV, bid-ask spread, VIX, ATR, skew, volatility per asset",
        "trigger": "per_session",
        "trigger_label": "Per session",
    },
    {
        "block_id": "online-b2",
        "name": "B2 Regime Probability",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b2_regime_probability.py",
        "description": "Classifies market regime (HIGH_VOL / LOW_VOL) via locked classifier or binary rule",
        "trigger": "per_session",
        "trigger_label": "Per session",
    },
    {
        "block_id": "online-b3",
        "name": "B3 AIM Aggregation",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b3_aim_aggregation.py",
        "description": "Aggregates 15 AIM modifiers via Mixture-of-Experts gating with DMA weights",
        "trigger": "per_session",
        "trigger_label": "Per session",
    },
    {
        "block_id": "online-b4",
        "name": "B4 Kelly Sizing",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b4_kelly_sizing.py",
        "description": "Computes optimal contract sizing per asset under regime uncertainty and TSM constraints",
        "trigger": "per_session",
        "trigger_label": "Per user/session",
    },
    {
        "block_id": "online-b5",
        "name": "B5 Trade Selection",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b5_trade_selection.py",
        "description": "Universe-level asset selection using expected edge and correlation filters",
        "trigger": "per_session",
        "trigger_label": "Per user/session",
    },
    {
        "block_id": "online-b5b",
        "name": "B5B Quality Gate",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b5b_quality_gate.py",
        "description": "Filters trades by quality threshold (edge x modifier x maturity)",
        "trigger": "per_session",
        "trigger_label": "Per user/session",
    },
    {
        "block_id": "online-b5c",
        "name": "B5C Circuit Breaker",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b5c_circuit_breaker.py",
        "description": "7-layer circuit breaker: scaling cap, halt, budget, expectancy, Sharpe, regime, manual",
        "trigger": "per_session",
        "trigger_label": "Per user/session",
    },
    {
        "block_id": "online-b6",
        "name": "B6 Signal Output",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b6_signal_output.py",
        "description": "Generates trading signals (direction, TP, SL, sizing) and publishes to Redis",
        "trigger": "per_session",
        "trigger_label": "Per user/session",
    },
    {
        "block_id": "online-b7",
        "name": "B7 Position Monitor",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b7_position_monitor.py",
        "description": "Monitors open positions (P&L, TP/SL proximity, regime shifts, time exits)",
        "trigger": "always_on",
        "trigger_label": "Always-on (10s poll)",
    },
    {
        "block_id": "online-b8",
        "name": "B8 Concentration Monitor",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b8_concentration_monitor.py",
        "description": "Aggregates network-level exposure across users (V1: single-user pass-through)",
        "trigger": "per_session",
        "trigger_label": "Post-session",
    },
    {
        "block_id": "online-b9",
        "name": "B9 Capacity Evaluation",
        "process": "ONLINE",
        "source_file": "captain-online/captain_online/blocks/b9_capacity_evaluation.py",
        "description": "Updates capacity metrics (signal supply, demand, constraints, diversity)",
        "trigger": "per_session",
        "trigger_label": "Post-session",
    },
    # --- Captain Offline (strategic brain, event-driven) ---
    {
        "block_id": "offline-orchestrator",
        "name": "Offline Orchestrator",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/orchestrator.py",
        "description": "Event-driven scheduler: trade outcomes, daily/weekly/monthly/quarterly tasks",
        "trigger": "always_on",
        "trigger_label": "Event-driven + scheduled",
    },
    {
        "block_id": "offline-b1-aim",
        "name": "B1 AIM Lifecycle",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b1_aim_lifecycle.py",
        "description": "AIM state machine: INSTALLED -> COLLECTING -> WARM_UP -> ELIGIBLE -> ACTIVE",
        "trigger": "per_trade",
        "trigger_label": "Per trade + daily + weekly",
    },
    {
        "block_id": "offline-b1-dma",
        "name": "B1 DMA Update",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b1_dma_update.py",
        "description": "Updates AIM inclusion probabilities using Dynamic Model Averaging (lambda=0.99)",
        "trigger": "per_trade",
        "trigger_label": "Per trade",
    },
    {
        "block_id": "offline-b1-drift",
        "name": "B1 Drift Detection",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b1_drift_detection.py",
        "description": "Daily AutoEncoder + ADWIN check for per-AIM concept drift",
        "trigger": "scheduled",
        "trigger_label": "Daily (16:00 ET)",
    },
    {
        "block_id": "offline-b1-hdwm",
        "name": "B1 HDWM Diversity",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b1_hdwm_diversity.py",
        "description": "Weekly: force-reactivate best AIM if all of a seed type are suppressed",
        "trigger": "scheduled",
        "trigger_label": "Weekly (Monday)",
    },
    {
        "block_id": "offline-b1-hmm",
        "name": "B1 HMM Training (AIM-16)",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b1_aim16_hmm.py",
        "description": "Trains 3-state HMM for opportunity regime classification (LOW/NORMAL/HIGH)",
        "trigger": "scheduled",
        "trigger_label": "Weekly/on-demand",
    },
    {
        "block_id": "offline-b2-bocpd",
        "name": "B2 BOCPD Decay",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b2_bocpd.py",
        "description": "Bayesian Online Changepoint Detection for strategy decay monitoring",
        "trigger": "per_trade",
        "trigger_label": "Per trade",
    },
    {
        "block_id": "offline-b2-cusum",
        "name": "B2 CUSUM Decay",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b2_cusum.py",
        "description": "Two-sided CUSUM for persistent mean shift detection (complementary to BOCPD)",
        "trigger": "per_trade",
        "trigger_label": "Per trade + quarterly recal",
    },
    {
        "block_id": "offline-b2-esc",
        "name": "B2 Level Escalation",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b2_level_escalation.py",
        "description": "Decay level 2: sizing reduction. Level 3: halt + P1/P2 rerun + AIM-14",
        "trigger": "per_trade",
        "trigger_label": "Per trade",
    },
    {
        "block_id": "offline-b3",
        "name": "B3 Pseudotrader",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b3_pseudotrader.py",
        "description": "Signal replay engine for historical trade comparison and parameter sensitivity",
        "trigger": "on_demand",
        "trigger_label": "On demand",
    },
    {
        "block_id": "offline-b4",
        "name": "B4 Injection Comparison",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b4_injection.py",
        "description": "Compares candidate strategy vs current: ADOPT if 1.2x better AND pbo < 0.5",
        "trigger": "on_demand",
        "trigger_label": "On command / Level 3",
    },
    {
        "block_id": "offline-b5",
        "name": "B5 Sensitivity Scanner",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b5_sensitivity.py",
        "description": "Monthly perturbation grid for locked strategy parameters; flags FRAGILE",
        "trigger": "scheduled",
        "trigger_label": "Monthly (1st)",
    },
    {
        "block_id": "offline-b6",
        "name": "B6 Auto-Expansion (AIM-14)",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b6_auto_expansion.py",
        "description": "GA search for replacement strategy on Level 3 decay trigger",
        "trigger": "on_demand",
        "trigger_label": "On Level 3 trigger",
    },
    {
        "block_id": "offline-b7",
        "name": "B7 TSM Simulation",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b7_tsm_simulation.py",
        "description": "Block bootstrap Monte Carlo (10K paths) for prop firm pass probability",
        "trigger": "per_trade",
        "trigger_label": "Per trade + on command",
    },
    {
        "block_id": "offline-b8-cb",
        "name": "B8 CB Params",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b8_cb_params.py",
        "description": "Estimates circuit breaker parameters: r_bar, beta_b, sigma, rho_bar",
        "trigger": "per_trade",
        "trigger_label": "Per trade",
    },
    {
        "block_id": "offline-b8-kelly",
        "name": "B8 Kelly Update",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b8_kelly_update.py",
        "description": "Updates EWMA (win_rate, avg_win, avg_loss) and Kelly formula after each trade",
        "trigger": "per_trade",
        "trigger_label": "Per trade",
    },
    {
        "block_id": "offline-b9",
        "name": "B9 System Diagnostic",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/b9_diagnostic.py",
        "description": "8-dimension health check: strategy, features, staleness, AIM, edge, data, pipeline",
        "trigger": "scheduled",
        "trigger_label": "Weekly + monthly",
    },
    {
        "block_id": "offline-bootstrap",
        "name": "Asset Bootstrap",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/bootstrap.py",
        "description": "Initializes new asset: D-22 trades, EWMA, BOCPD/CUSUM, Kelly, Tier 1 AIMs",
        "trigger": "on_demand",
        "trigger_label": "On ASSET_ADDED",
    },
    {
        "block_id": "offline-versioning",
        "name": "Version Snapshot",
        "process": "OFFLINE",
        "source_file": "captain-offline/captain_offline/blocks/version_snapshot.py",
        "description": "Records model versions before updates for auditability and rollback",
        "trigger": "event_driven",
        "trigger_label": "On model update",
    },
    # --- Captain Command (linking layer, always-on) ---
    {
        "block_id": "command-orchestrator",
        "name": "Command Orchestrator",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/orchestrator.py",
        "description": "Always-on event loop: signal stream, Redis pub/sub, scheduler, FastAPI server",
        "trigger": "always_on",
        "trigger_label": "Always-on",
    },
    {
        "block_id": "command-b1",
        "name": "B1 Core Routing",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b1_core_routing.py",
        "description": "Central message bus: signals -> GUI + API, commands -> handlers, alerts -> pub/sub",
        "trigger": "event_driven",
        "trigger_label": "Event-driven",
    },
    {
        "block_id": "command-b2",
        "name": "B2 GUI Data Server",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b2_gui_data_server.py",
        "description": "Dashboard assembly: capital, positions, signals, AIM, TSM, regime, notifications",
        "trigger": "scheduled",
        "trigger_label": "60s refresh + events",
    },
    {
        "block_id": "command-b3",
        "name": "B3 API Adapter",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b3_api_adapter.py",
        "description": "TopstepX integration: REST + WebSocket, 30s health monitoring, auto-reconnect",
        "trigger": "always_on",
        "trigger_label": "30s health check",
    },
    {
        "block_id": "command-b4",
        "name": "B4 TSM Manager",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b4_tsm_manager.py",
        "description": "Loads and validates TSM JSON configs: fee schedule, scaling, payout rules",
        "trigger": "on_demand",
        "trigger_label": "On startup",
    },
    {
        "block_id": "command-b5",
        "name": "B5 Injection Flow",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b5_injection_flow.py",
        "description": "Routes strategy injection: P1/P2 completion -> comparison -> user decision",
        "trigger": "on_demand",
        "trigger_label": "On P1/P2 events",
    },
    {
        "block_id": "command-b6",
        "name": "B6 Reports",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b6_reports.py",
        "description": "11 report types: pre-session, weekly, monthly decay, AIM, strategy, prop firm",
        "trigger": "scheduled",
        "trigger_label": "Scheduled + on-demand",
    },
    {
        "block_id": "command-b7",
        "name": "B7 Notifications",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b7_notifications.py",
        "description": "26 event types, 4 priority levels, Telegram + GUI + email with quiet hours",
        "trigger": "event_driven",
        "trigger_label": "Event-driven",
    },
    {
        "block_id": "command-b8",
        "name": "B8 Reconciliation",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b8_reconciliation.py",
        "description": "Daily 19:00 EST: broker sync, SOD param computation, payout check, daily reset",
        "trigger": "scheduled",
        "trigger_label": "Daily 19:00 EST",
    },
    {
        "block_id": "command-b9",
        "name": "B9 Incident Response",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b9_incident_response.py",
        "description": "Auto-generated incident reports with severity routing (P1 -> P4)",
        "trigger": "event_driven",
        "trigger_label": "Event-driven",
    },
    {
        "block_id": "command-b10",
        "name": "B10 Data Validation",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/blocks/b10_data_validation.py",
        "description": "Validates all user-provided data: asset onboarding, TSM params, decisions",
        "trigger": "event_driven",
        "trigger_label": "On user input",
    },
    {
        "block_id": "command-telegram",
        "name": "Telegram Bot",
        "process": "COMMAND",
        "source_file": "captain-command/captain_command/telegram_bot.py",
        "description": "Telegram integration: notifications + inline decisions (TAKEN/SKIPPED)",
        "trigger": "always_on",
        "trigger_label": "Always-on polling",
    },
]


def _get_locked_strategies() -> list[dict]:
    """Fetch locked strategies from P3-D00 for the Processes tab."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, captain_status, locked_strategy
                   FROM p3_d00_asset_universe
                   WHERE locked_strategy IS NOT NULL
                     AND locked_strategy != '{}'
                   LATEST ON last_updated PARTITION BY asset_id
                   ORDER BY asset_id"""
            )
            results = []
            for r in cur.fetchall():
                strat = json.loads(r[2]) if isinstance(r[2], str) else (r[2] or {})
                results.append({
                    "asset": r[0],
                    "captain_status": r[1],
                    "m": strat.get("m"),
                    "k": strat.get("k"),
                    "oo": strat.get("OO") or strat.get("oo"),
                    "sessions": strat.get("sessions", []),
                })
            return results
    except Exception as exc:
        logger.error("Locked strategies query failed: %s", exc, exc_info=True)
    return []


def build_processes_status(process_health: dict, api_connections: dict) -> dict:
    """Assemble process monitoring data for the Processes tab.

    Parameters
    ----------
    process_health : dict
        Process health state from api module (OFFLINE/ONLINE/COMMAND).
    api_connections : dict
        API adapter connection state from api module.
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "processes": {
            role: {
                "status": info.get("status", "unknown"),
                "timestamp": info.get("timestamp"),
            }
            for role, info in process_health.items()
        },
        "blocks": BLOCK_REGISTRY,
        "locked_strategies": _get_locked_strategies(),
        "api_connections": {
            "connected": sum(
                1 for ac in api_connections.values()
                if ac.get("connected", False)
            ),
            "total": len(api_connections),
        },
    }
